import asyncio
import logging
from typing import Dict, List
from datetime import datetime
import grpc.aio
from services.fleet_api import FleetAPI
from common_types import Task, TaskStep, TaskStatus, StepStatus, StepResult, get_error_message
from services.fleet_api import (
    DefaultCmd, SpeakCmd, MoveToPoseCmd, Move2LocationCmd,
    MoveShelfCmd, ReturnShelfCmd
)
from dependencies import get_bio_sensor_client
from settings.config import get_runtime_settings

logger = logging.getLogger("kachaka.task_runtime")

# --- global states ---
tasks_db: Dict[str, Task] = {}
engines: Dict[str, "TaskEngine"] = {}
task_queues: Dict[str, asyncio.Queue] = {}
current_tasks: Dict[str, str] = {}  # robot_id -> task_id
global_queue: asyncio.Queue = asyncio.Queue()
available_robots_queue: asyncio.Queue = asyncio.Queue()

async def retry_with_backoff(func, max_retries=None, base_delay=None, max_delay=None):
    """Retry function with exponential backoff for robot operations"""
    # Use runtime settings defaults if not provided
    if max_retries is None or base_delay is None or max_delay is None:
        cfg = get_runtime_settings()
        if max_retries is None:
            max_retries = cfg.get("robot_max_retries", 3)
        if base_delay is None:
            base_delay = cfg.get("robot_retry_base_delay", 2.0)
        if max_delay is None:
            max_delay = cfg.get("robot_retry_max_delay", 10.0)

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except grpc.aio.AioRpcError as e:
            if attempt == max_retries:
                # Final attempt failed, re-raise the error
                raise e

            # Check if error is retryable
            if e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.RESOURCE_EXHAUSTED]:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(f"gRPC error {e.code()} ({e.details()}), retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})")
                await asyncio.sleep(delay)
            else:
                # Non-retryable error, re-raise immediately
                raise e
        except Exception as e:
            # Non-gRPC error, don't retry
            raise e

class TaskEngine:
    def __init__(self, fleet_api: FleetAPI, robot_id: str):
        self.fleet = fleet_api
        self.robot_id = robot_id

    async def run_task(self, task: Task) -> Task:
        logger.info(f"===> Starting task: {task.task_id} on robot {task.robot_id}")
        task.status = TaskStatus.IN_PROGRESS
        current_tasks[task.robot_id] = task.task_id # Mark robot as busy
        self.task_start_time = datetime.now().strftime("%Y%m%d%H%M%S")

        try:
            step_index = 0
            skipped_steps = set()  # Track steps to skip due to conditional logic
            skip_reasons = {}  # Track the error details that caused steps to be skipped

            while step_index < len(task.steps):
                step = task.steps[step_index]

                if task.status == TaskStatus.CANCELLED:
                    logger.info(f"[!] Task {task.task_id} on robot {self.robot_id} cancelled mid-execution")
                    break

                # Check if this step should be skipped
                if step.step_id in skipped_steps:
                    logger.info(f"[SKIP] Robot {self.robot_id}, Step {step.step_id} skipped due to conditional logic")
                    step.status = StepStatus.SKIPPED

                    # Get the error details that caused this step to be skipped
                    skip_reason = skip_reasons.get(step.step_id, {})

                    # Special handling for bio_scan: record error in database
                    if step.action == "bio_scan":
                        try:
                            client = get_bio_sensor_client()
                            error_data = {
                                "error_source": skip_reason.get("failed_step_id"),
                                "original_error_code": skip_reason.get("error_code"),
                                "original_error_message": skip_reason.get("error_message"),
                                "status": "N/A",
                                "bpm": None,
                                "rpm": None,
                                "details": "機器人無法移動到床邊",
                                "bed_id": self.target_bed
                            }

                            taskid = f"{self.task_start_time}-{self.target_bed}-0"
                            client._save_scan_data(
                                task_id=taskid,
                                data=error_data,
                                retry_count=0,
                                is_valid=False
                            )
                            logger.info(f"[SKIP] Bio scan error recorded in database for task {task.task_id}")
                        except Exception as e:
                            logger.error(f"[SKIP] Failed to record bio scan error in database: {str(e)}")

                    step.result = StepResult(
                        success=False,
                        error_code=skip_reason.get("error_code", 0),
                        error_message=skip_reason.get("error_message", "Step skipped due to previous step failure"),
                        data={
                            "reason": "conditional_skip",
                            "caused_by_step": skip_reason.get("failed_step_id"),
                            "original_error": skip_reason.get("original_error")
                        },
                        timestamp=datetime.now().isoformat()
                    )
                    step_index += 1
                    continue

                logger.info(f"---> Robot {self.robot_id}, Step: {step.step_id} | Action: {step.action}")
                step.status = StepStatus.EXECUTING

                try:
                    skip_reason = skip_reasons.get(step.step_id) if step.step_id in skip_reasons else None
                    step_result = await self._execute_step(step, skip_reason)
                    step.result = step_result
                    step.status = StepStatus.SUCCESS if step_result.success else StepStatus.FAIL

                    if step_result.success:
                        logger.info(f"[✓] Robot {self.robot_id}, Step {step.step_id} completed successfully")
                    else:
                        logger.warning(f"[!] Robot {self.robot_id}, Step {step.step_id} failed: {step_result.error_message} (code: {step_result.error_code})")

                        # --- SHELF DROP DETECTION (error 14606) ---
                        if step.action == "move_shelf" and step_result.error_code == 14606:
                            logger.error(f"[SHELF DROP] Error 14606 detected on robot {self.robot_id}, pausing task")

                            # Extract room info from location_id
                            location_id = step.params.get("location_id", "unknown")
                            shelf_id = step.params.get("shelf_id", "unknown")

                            # Store shelf-drop context in task metadata
                            task.metadata = {
                                "shelf_drop": True,
                                "shelf_id": shelf_id,
                                "bed_key": location_id,
                                "room": location_id,
                                "dropped_at": datetime.now().isoformat(),
                            }
                            task.status = TaskStatus.SHELF_DROPPED

                            # Send Telegram notification immediately
                            try:
                                from services.telegram_service import send_telegram_message
                                await send_telegram_message(
                                    f"⚠️ 架子可能掉落在 {location_id} 附近，請協助歸位"
                                )
                            except Exception as tg_err:
                                logger.error(f"Failed to send shelf-drop Telegram: {tg_err}")

                            # Robot return home
                            try:
                                cmd = DefaultCmd()
                                await self.fleet.return_home(self.robot_id, cmd)
                                logger.info(f"[SHELF DROP] Robot {self.robot_id} sent home")
                            except Exception as rh_err:
                                logger.error(f"[SHELF DROP] Failed to send robot home: {rh_err}")

                            break  # Pause the task

                        # Handle conditional logic: add steps to skip list if this step failed
                        if step.skip_on_failure:
                            skipped_steps.update(step.skip_on_failure)
                            logger.info(f"[CONDITIONAL] Step {step.step_id} failed, will skip steps: {step.skip_on_failure}")

                            # Store error details for each step that will be skipped
                            for skip_step_id in step.skip_on_failure:
                                skip_reasons[skip_step_id] = {
                                    "failed_step_id": step.step_id,
                                    "error_code": step_result.error_code,
                                    "error_message": step_result.error_message,
                                    "original_error": step_result.data,
                                }

                        # Check if this is a critical failure (no skip logic defined)
                        if not step.skip_on_failure:
                            task.status = TaskStatus.FAILED
                            break

                except Exception as e:
                    logger.error(f"[X] Robot {self.robot_id}, Exception in step {step.step_id}: {str(e)}", exc_info=True)
                    step.result = StepResult(
                        success=False,
                        error_code=-1,
                        error_message=f"TaskEngine exception: {str(e)}",
                        data={"step_id": step.step_id, "action": step.action},
                        timestamp=datetime.now().isoformat()
                    )
                    step.status = StepStatus.FAIL

                    # Handle conditional logic for exceptions too
                    if step.skip_on_failure:
                        skipped_steps.update(step.skip_on_failure)
                        logger.info(f"[CONDITIONAL] Step {step.step_id} exception, will skip steps: {step.skip_on_failure}")

                        for skip_step_id in step.skip_on_failure:
                            skip_reasons[skip_step_id] = {
                                "failed_step_id": step.step_id,
                                "error_code": step.result.error_code,
                                "error_message": step.result.error_message,
                                "original_error": step.result.data,
                            }
                    else:
                        task.status = TaskStatus.FAILED
                        break

                step_index += 1

            if task.status == TaskStatus.IN_PROGRESS:
                task.status = TaskStatus.DONE
                logger.info(f"===> Task {task.task_id} completed successfully on robot {self.robot_id}")

            # Send Telegram notification on task completion/failure
            if task.status in (TaskStatus.DONE, TaskStatus.FAILED):
                try:
                    from services.telegram_service import send_telegram_message
                    status_label = "✅ 巡房完成" if task.status == TaskStatus.DONE else "❌ 巡房失敗"
                    await send_telegram_message(f"{status_label} - Task {task.task_id}")
                except Exception as tg_err:
                    logger.error(f"Failed to send task-completion Telegram: {tg_err}")

        finally:
            current_tasks.pop(self.robot_id, None)
            logger.info(f"Robot {self.robot_id} is now free. Signaling availability.")
            await available_robots_queue.put(self.robot_id)
        return task

    async def _execute_step(self, step: TaskStep, skip_reason=None) -> StepResult:
        action = step.action
        params = step.params
        print("Robot ID: " + self.robot_id)
        try:
            if action == "speak":
                cmd = SpeakCmd()
                cmd.speak_text = params["speak_text"]
                api_result = await self.fleet.speak(self.robot_id, cmd)

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code),
                    data={"speak_text": cmd.speak_text},
                    timestamp=datetime.now().isoformat()
                )
            elif action == "move_to_pose":
                cmd = MoveToPoseCmd()
                cmd.x = float(params["x"])
                cmd.y = float(params["y"])
                cmd.yaw = float(params["yaw"])
                api_result = await self.fleet.move_to_pose(self.robot_id, cmd)

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code),
                    data={"x": cmd.x, "y": cmd.y, "yaw": cmd.yaw},
                    timestamp=datetime.now().isoformat()
                )
            elif action == "move_to_location":
                cmd = Move2LocationCmd()
                cmd.location_id = params["location_id"]
                api_result = await retry_with_backoff(
                    lambda: self.fleet.move_to_location(self.robot_id, cmd),
                    max_retries=2  # Fewer retries for movement commands
                )

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code),
                    data={"location_id": cmd.location_id},
                    timestamp=datetime.now().isoformat()
                )
            elif action == "dock_shelf":
                cmd = DefaultCmd()
                api_result = await retry_with_backoff(
                    lambda: self.fleet.dock_shelf(self.robot_id, cmd),
                    max_retries=2
                )

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code),
                    data={},
                    timestamp=datetime.now().isoformat()
                )
            elif action == "undock_shelf":
                cmd = DefaultCmd()
                api_result = await retry_with_backoff(
                    lambda: self.fleet.undock_shelf(self.robot_id, cmd),
                    max_retries=2
                )

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code),
                    data={},
                    timestamp=datetime.now().isoformat()
                )
            elif action == "move_shelf":
                cmd = MoveShelfCmd()
                cmd.shelf_id = params["shelf_id"]
                cmd.location_id = params["location_id"]

                # move_shelf always comes before bio_scan
                # so the context should be preserved for bio_scan.
                self.target_bed = params['location_id'];

                # Get full pb2.Result from Kachaka API with retry logic
                api_result = await retry_with_backoff(
                    lambda: self.fleet.move_shelf(self.robot_id, cmd)
                )

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code),
                    data={"shelf_id": cmd.shelf_id, "location_id": cmd.location_id},
                    timestamp=datetime.now().isoformat()
                )
            elif action == "return_shelf":
                cmd = ReturnShelfCmd()
                cmd.shelf_id = params["shelf_id"]
                api_result = await retry_with_backoff(
                    lambda: self.fleet.return_shelf(self.robot_id, cmd)
                )

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code),
                    data={"shelf_id": cmd.shelf_id},
                    timestamp=datetime.now().isoformat()
                )
            elif action == "return_home":
                cmd = DefaultCmd()
                api_result = await self.fleet.return_home(self.robot_id, cmd)

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code),
                    data={},
                    timestamp=datetime.now().isoformat()
                )
            elif action == "bio_scan":
                client = get_bio_sensor_client()
                scan_result = await client.get_valid_scan_data(target_bed=self.target_bed, task_id=self.task_start_time)
                print('bio_scan result: ', scan_result)

                # Check if bio scan was successful (valid data was obtained)
                success = scan_result is not None
                if success:
                    logger.info(f"Bio scan completed successfully for robot {self.robot_id}")
                else:
                    logger.warning(f"Bio scan failed - no valid data obtained for robot {self.robot_id}")

                return StepResult(
                    success=success,
                    error_code=0 if success else -1,
                    error_message="Bio scan completed successfully" if success else "No valid data obtained",
                    data=scan_result,
                    timestamp=datetime.now().isoformat()
                )
            elif action == "wait":
                seconds = float(params.get("seconds", "1.0"))
                await asyncio.sleep(seconds)

                return StepResult(
                    success=True,
                    error_code=0,
                    error_message="Wait completed successfully",
                    data={"seconds": seconds},
                    timestamp=datetime.now().isoformat()
                )
            else:
                logger.error(f"Unknown action: {action} for robot {self.robot_id}")
                return StepResult(
                    success=False,
                    error_code=-1,
                    error_message=f"Unknown action: {action}",
                    data={"action": action},
                    timestamp=datetime.now().isoformat()
                )
        except grpc.aio.AioRpcError as e:
            logger.error(f"[X] gRPC error during action {action} for robot {self.robot_id}: {e.code()} - {e.details()}")
            return StepResult(
                success=False,
                error_code=int(e.code().value[0]) if hasattr(e.code(), 'value') else -1,
                error_message=f"gRPC error {e.code()}: {e.details()}",
                data={"action": action, "params": params, "grpc_code": e.code().name},
                timestamp=datetime.now().isoformat()
            )
        except ValueError as e:
            logger.error(f"[!] Robot {self.robot_id} not found: {str(e)}")
            return StepResult(
                success=False,
                error_code=-1,
                error_message=f"Robot {self.robot_id} not found: {str(e)}",
                data={"action": action, "params": params},
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            logger.error(f"[X] Unexpected error during action {action} for robot {self.robot_id}: {str(e)}", exc_info=True)
            return StepResult(
                success=False,
                error_code=-1,
                error_message=f"Unexpected error: {str(e)}",
                data={"action": action, "params": params},
                timestamp=datetime.now().isoformat()
            )

async def dispatcher():
    logger.info("Dispatcher started. Waiting for tasks and available robots...")
    while True:
        task_to_assign = None
        robot_to_assign_task_to = None
        try:
            task_to_assign = await global_queue.get()
            logger.info(f"Dispatcher: Got task {task_to_assign.task_id} from global_queue.")

            # Check if task has a preferred robot_id
            if task_to_assign.robot_id:
                preferred_robot = task_to_assign.robot_id
                logger.info(f"Dispatcher: Task {task_to_assign.task_id} has preferred robot: {preferred_robot}")

                robot_specific_queue = task_queues[preferred_robot]
                task_to_assign.status = TaskStatus.QUEUED
                await robot_specific_queue.put(task_to_assign)
                tasks_db[task_to_assign.task_id] = task_to_assign
                logger.info(f"Dispatcher: Assigned task {task_to_assign.task_id} to preferred robot {preferred_robot}.")
            else:
                logger.info(f"Dispatcher: Task {task_to_assign.task_id} has no preferred robot. Assigning to any available robot.")
                robot_to_assign_task_to = await available_robots_queue.get()
                logger.info(f"Dispatcher: Robot {robot_to_assign_task_to} signaled availability.")
                if robot_to_assign_task_to in task_queues and robot_to_assign_task_to not in current_tasks:
                    robot_specific_queue = task_queues[robot_to_assign_task_to]
                    task_to_assign.robot_id = robot_to_assign_task_to
                    task_to_assign.status = TaskStatus.QUEUED
                    await robot_specific_queue.put(task_to_assign)
                    tasks_db[task_to_assign.task_id] = task_to_assign
                    logger.info(f"Dispatcher: Assigned task {task_to_assign.task_id} to robot {robot_to_assign_task_to}.")
                else:
                    logger.warning(f"Dispatcher: Robot {robot_to_assign_task_to} signaled but was unsuitable or already busy. Re-queueing task {task_to_assign.task_id}.")
                    await global_queue.put(task_to_assign)
                    task_to_assign = None
                    if robot_to_assign_task_to in task_queues:
                        logger.info(f"Dispatcher: Re-adding robot {robot_to_assign_task_to} to available_robots_queue as it was suitable but task assignment failed this cycle.")
                        await available_robots_queue.put(robot_to_assign_task_to)
        except Exception as e:
            logger.error(f"Dispatcher error: {str(e)}", exc_info=True)
            if task_to_assign:
                logger.info(f"Re-queueing task {task_to_assign.task_id} due to dispatcher error.")
                await global_queue.put(task_to_assign)
            if robot_to_assign_task_to and robot_to_assign_task_to in task_queues:
                logger.info(f"Re-queueing robot {robot_to_assign_task_to} signal due to dispatcher error.")
                await available_robots_queue.put(robot_to_assign_task_to)
        finally:
            if task_to_assign:
                global_queue.task_done()
            if robot_to_assign_task_to:
                available_robots_queue.task_done()

async def task_worker(robot_id: str):
    queue = task_queues[robot_id]
    engine = engines[robot_id]
    logger.info(f"Task worker started for robot {robot_id}")
    while True:
        task = await queue.get()
        logger.info(f"Robot {robot_id} worker: got task {task.task_id} from its queue.")
        if task.status != TaskStatus.CANCELLED:
            updated_task = await engine.run_task(task)
            tasks_db[task.task_id] = updated_task
        else:
            logger.info(f"Robot {robot_id} worker: task {task.task_id} was already cancelled. Not running.")
        queue.task_done()

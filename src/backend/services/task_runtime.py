import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import grpc.aio
from services.fleet_api import FleetAPI
from common_types import Task, TaskStep, TaskStatus, StepStatus, StepResult, get_error_message, get_now
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
        self._shelf_names: Dict[str, str] = {}
        self._location_names: Dict[str, str] = {}
        self._shelf_dropped = False
        self._shelf_monitor_stop = False
        self._shelf_monitor_task: Optional[asyncio.Task] = None

    async def _refresh_name_cache(self):
        """Fetch shelf/location names from robot for readable logs"""
        try:
            shelves = await self.fleet.get_shelves(self.robot_id)
            self._shelf_names = {s.id: s.name for s in shelves}
            locations = await self.fleet.get_locations(self.robot_id)
            self._location_names = {l.id: l.name for l in locations}
        except Exception as e:
            logger.warning(f"Failed to refresh name cache: {e}")

    def _format_params(self, params: Dict[str, Any]) -> str:
        """Format step params with resolved names for shelf_id/location_id"""
        if not params:
            return ""
        parts = []
        for k, v in params.items():
            if k == "shelf_id" and v in self._shelf_names:
                parts.append(f"{k}={v}({self._shelf_names[v]})")
            elif k == "location_id" and v in self._location_names:
                parts.append(f"{k}={v}({self._location_names[v]})")
            else:
                parts.append(f"{k}={v}")
        return ", ".join(parts)

    async def _monitor_shelf(self):
        """Background coroutine that polls get_moving_shelves_id() every 3s.
        Sets _shelf_dropped flag if the robot no longer carries a shelf."""
        logger.info(f"[SHELF MONITOR] Started for robot {self.robot_id}")
        while not self._shelf_monitor_stop:
            await asyncio.sleep(3)
            if self._shelf_monitor_stop:
                break
            try:
                shelf_id = await self.fleet.get_moving_shelves_id(self.robot_id)
                if not shelf_id:
                    logger.warning(f"[SHELF MONITOR] Robot {self.robot_id} no longer carrying a shelf — shelf dropped!")
                    self._shelf_dropped = True
                    # Cancel the in-flight command so the blocked _execute_step returns quickly
                    try:
                        client = self.fleet.manager.get_robot_client(self.robot_id)
                        if client:
                            await client.cancel_command()
                            logger.info(f"[SHELF MONITOR] Cancelled current command on robot {self.robot_id}")
                    except Exception as ce:
                        logger.debug(f"[SHELF MONITOR] cancel_command failed (non-critical): {ce}")
                    break
            except Exception as e:
                logger.debug(f"[SHELF MONITOR] Transient error polling shelf for robot {self.robot_id}: {e}")
        logger.info(f"[SHELF MONITOR] Stopped for robot {self.robot_id}")

    async def _stop_shelf_monitor(self):
        """Stop the shelf monitor background task."""
        self._shelf_monitor_stop = True
        if self._shelf_monitor_task is not None:
            self._shelf_monitor_task.cancel()
            try:
                await self._shelf_monitor_task
            except asyncio.CancelledError:
                pass
            self._shelf_monitor_task = None
        logger.info(f"[SHELF MONITOR] Cleaned up for robot {self.robot_id}")

    async def _handle_shelf_drop(self, task: Task, step_index: int,
                                   trigger_step: Optional["TaskStep"] = None,
                                   error_code: int = 0):
        """Handle shelf drop: collect remaining beds, notify, record DB, send robot home."""
        await self._stop_shelf_monitor()

        # Cancel any in-flight robot command immediately
        try:
            client = self.fleet.manager.get_robot_client(self.robot_id)
            if client:
                await client.cancel_command()
                logger.info(f"[SHELF DROP] Cancelled current command on robot {self.robot_id}")
        except Exception as ce:
            logger.debug(f"[SHELF DROP] cancel_command failed (non-critical): {ce}")

        source = f"error {error_code}" if error_code else "polling monitor"
        logger.error(f"[SHELF DROP] Detected via {source} on robot {self.robot_id}, pausing task")

        location_id = trigger_step.params.get("location_id", "unknown") if trigger_step else "unknown"
        shelf_id = trigger_step.params.get("shelf_id", "unknown") if trigger_step else "unknown"

        if shelf_id == "unknown":
            shelf_id = getattr(self, "_current_shelf_id", "unknown")

        # Query current shelf position
        shelf_pose = None
        try:
            shelves = await self.fleet.get_shelves(self.robot_id)
            from google.protobuf.json_format import MessageToDict
            for s in shelves:
                s_dict = MessageToDict(s, preserving_proto_field_name=True)
                if s_dict.get("id") == shelf_id:
                    pose = s_dict.get("pose", {})
                    shelf_pose = {"x": pose.get("x", 0), "y": pose.get("y", 0), "theta": pose.get("theta", 0)}
                    logger.info(f"[SHELF DROP] Shelf {shelf_id} pose: {shelf_pose}")
                    break
        except Exception as e:
            logger.warning(f"[SHELF DROP] Failed to get shelf pose: {e}")

        # Collect remaining unprocessed beds
        remaining_beds = []
        collected_step_ids = set()

        # Current bed: from skip_on_failure bio_scan step of trigger
        if trigger_step and trigger_step.skip_on_failure:
            for skip_id in trigger_step.skip_on_failure:
                skip_step = next((s for s in task.steps if s.step_id == skip_id), None)
                if skip_step and skip_step.action == "bio_scan":
                    remaining_beds.append({
                        "bed_key": skip_step.params.get("bed_key", ""),
                        "location_id": location_id,
                    })
                    collected_step_ids.add(skip_id)

        # Future unprocessed bio_scan steps (PENDING or SKIPPED due to move failure)
        for future_step in task.steps[step_index + 1:]:
            if (future_step.action == "bio_scan"
                    and future_step.status in (StepStatus.PENDING, StepStatus.SKIPPED)
                    and future_step.step_id not in collected_step_ids):
                future_loc = ""
                for ms in task.steps:
                    if ms.action == "move_shelf" and ms.skip_on_failure and future_step.step_id in ms.skip_on_failure:
                        future_loc = ms.params.get("location_id", "")
                        break
                remaining_beds.append({
                    "bed_key": future_step.params.get("bed_key", ""),
                    "location_id": future_loc,
                })

        # If no trigger step (polling detection), also include the current executing bio_scan
        if not trigger_step:
            current_step = task.steps[step_index] if step_index < len(task.steps) else None
            if current_step and current_step.action == "bio_scan" and current_step.status == StepStatus.EXECUTING:
                remaining_beds.insert(0, {
                    "bed_key": current_step.params.get("bed_key", ""),
                    "location_id": getattr(self, "target_bed", ""),
                })

        # Store shelf-drop context in task metadata
        task.metadata = {
            "shelf_drop": True,
            "shelf_id": shelf_id,
            "bed_key": location_id,
            "room": location_id,
            "dropped_at": get_now().isoformat(),
            "remaining_beds": remaining_beds,
            "shelf_pose": shelf_pose,
        }
        task.status = TaskStatus.SHELF_DROPPED

        # Send Telegram notification
        try:
            from services.telegram_service import send_telegram_message
            await send_telegram_message("⚠️ 貨架掉落，請協助歸位")
        except Exception as tg_err:
            logger.error(f"Failed to send shelf-drop Telegram: {tg_err}")

        # Record skipped bio_scan steps to DB
        if trigger_step and trigger_step.skip_on_failure:
            for skip_id in trigger_step.skip_on_failure:
                skip_step = next((s for s in task.steps if s.step_id == skip_id), None)
                if skip_step and skip_step.action == "bio_scan":
                    try:
                        client = get_bio_sensor_client()
                        if client:
                            error_data = {
                                "status": "N/A",
                                "bpm": None,
                                "rpm": None,
                                "details": "貨架掉落，巡房中斷",
                                "bed_id": getattr(self, "target_bed", ""),
                                "bed_name": skip_step.params.get("bed_key"),
                            }
                            client._save_scan_data(
                                task_id=self.current_task_id,
                                data=error_data,
                                retry_count=0,
                                is_valid=False,
                            )
                            skip_step.status = StepStatus.SKIPPED
                            logger.info(f"[SHELF DROP] Recorded skipped bio_scan {skip_id} in database")
                    except Exception as db_err:
                        logger.error(f"[SHELF DROP] Failed to record skipped bio_scan: {db_err}")

        # Mark remaining unprocessed bio_scan steps
        for remaining in task.steps[step_index + 1:]:
            if remaining.action == "bio_scan" and remaining.status == StepStatus.PENDING:
                try:
                    client = get_bio_sensor_client()
                    if client:
                        error_data = {
                            "status": "N/A",
                            "bpm": None,
                            "rpm": None,
                            "details": "貨架掉落，巡房中斷",
                            "bed_id": remaining.params.get("location_id", ""),
                            "bed_name": remaining.params.get("bed_key"),
                        }
                        client._save_scan_data(
                            task_id=self.current_task_id,
                            data=error_data,
                            retry_count=0,
                            is_valid=False,
                        )
                        remaining.status = StepStatus.SKIPPED
                        logger.info(f"[SHELF DROP] Recorded skipped bio_scan {remaining.step_id} in database")
                except Exception as db_err:
                    logger.error(f"[SHELF DROP] Failed to record skipped bio_scan: {db_err}")

        # Robot return home
        try:
            cmd = DefaultCmd()
            await self.fleet.return_home(self.robot_id, cmd)
            logger.info(f"[SHELF DROP] Robot {self.robot_id} sent home")
        except Exception as rh_err:
            logger.error(f"[SHELF DROP] Failed to send robot home: {rh_err}")

    async def run_task(self, task: Task) -> Task:
        logger.info(f"===> Starting task: {task.task_id} on robot {task.robot_id}")
        await self._refresh_name_cache()
        task.status = TaskStatus.IN_PROGRESS
        current_tasks[task.robot_id] = task.task_id # Mark robot as busy
        self.current_task_id = task.task_id
        self.task_start_time = get_now().strftime("%Y%m%d%H%M%S")
        self._shelf_dropped = False
        self._shelf_monitor_stop = False
        self._shelf_monitor_task = None

        try:
            step_index = 0
            skipped_steps = set()  # Track steps to skip due to conditional logic
            skip_reasons = {}  # Track the error details that caused steps to be skipped

            while step_index < len(task.steps):
                step = task.steps[step_index]

                if task.status == TaskStatus.CANCELLED:
                    logger.info(f"[!] Task {task.task_id} on robot {self.robot_id} cancelled mid-execution")
                    break

                # --- SHELF DROP via polling monitor ---
                if self._shelf_dropped:
                    await self._handle_shelf_drop(task, step_index)
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
                            if client is None:
                                logger.warning("[SKIP] Bio scan skipped - MQTT client not available")
                                step_index += 1
                                continue
                            error_data = {
                                "error_source": skip_reason.get("failed_step_id"),
                                "original_error_code": skip_reason.get("error_code"),
                                "original_error_message": skip_reason.get("error_message"),
                                "status": "N/A",
                                "bpm": None,
                                "rpm": None,
                                "details": "機器人無法移動到床邊",
                                "bed_id": self.target_bed,
                                "bed_name": step.params.get("bed_key"),
                            }

                            client._save_scan_data(
                                task_id=self.current_task_id,
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
                        timestamp=get_now().isoformat()
                    )
                    step_index += 1
                    continue

                params_str = self._format_params(step.params)
                logger.info(f"---> Robot {self.robot_id}, Step: {step.step_id} | Action: {step.action}({params_str})")
                step.status = StepStatus.EXECUTING

                try:
                    skip_reason = skip_reasons.get(step.step_id) if step.step_id in skip_reasons else None
                    step_result = await self._execute_step(step, skip_reason)
                    step.result = step_result
                    step.status = StepStatus.SUCCESS if step_result.success else StepStatus.FAIL

                    # Shelf drop detected during step execution — handle immediately
                    if self._shelf_dropped:
                        await self._handle_shelf_drop(task, step_index, trigger_step=step)
                        break

                    if step_result.success:
                        logger.info(f"[✓] Robot {self.robot_id}, Step {step.step_id} completed successfully")
                    else:
                        logger.warning(f"[!] Robot {self.robot_id}, Step {step.step_id} failed: {step_result.error_message} (code: {step_result.error_code})")

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

                        # Non-critical actions: failure should NOT terminate the entire task
                        elif step.action in ("bio_scan", "wait", "speak", "return_shelf"):
                            logger.warning(f"[NON-CRITICAL] Step {step.step_id} ({step.action}) failed, continuing to next step")

                        # Critical failure: no skip logic and not a non-critical action
                        else:
                            task.status = TaskStatus.FAILED
                            break

                except Exception as e:
                    logger.error(f"[X] Robot {self.robot_id}, Exception in step {step.step_id}: {str(e)}", exc_info=True)
                    step.result = StepResult(
                        success=False,
                        error_code=-1,
                        error_message=f"TaskEngine exception: {str(e)}",
                        data={"step_id": step.step_id, "action": step.action},
                        timestamp=get_now().isoformat()
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
                    elif step.action in ("bio_scan", "wait", "speak", "return_shelf"):
                        logger.warning(f"[NON-CRITICAL] Step {step.step_id} ({step.action}) exception, continuing to next step")
                    else:
                        task.status = TaskStatus.FAILED
                        break

                step_index += 1

            if task.status == TaskStatus.IN_PROGRESS:
                task.status = TaskStatus.DONE
                logger.info(f"===> Task {task.task_id} completed successfully on robot {self.robot_id}")

        finally:
            await self._stop_shelf_monitor()
            # Always send patrol summary when task ends
            try:
                from services.telegram_service import send_telegram_message
                bio_steps = [s for s in task.steps if s.action == "bio_scan"]
                total_beds = len(bio_steps)
                success_beds = sum(1 for s in bio_steps if s.status == StepStatus.SUCCESS)
                await send_telegram_message(f"✅ 巡房完成\n本次巡房 {total_beds} 床，成功讀取 {success_beds} 床")
            except Exception as tg_err:
                logger.error(f"Failed to send task-completion Telegram: {tg_err}")
            current_tasks.pop(self.robot_id, None)
            logger.info(f"Robot {self.robot_id} is now free. Signaling availability.")
            await available_robots_queue.put(self.robot_id)
        return task

    def _build_error_context(self, params: Dict[str, Any]) -> Dict[str, str]:
        """Build template context for error message placeholders"""
        ctx: Dict[str, str] = {}
        shelf_id = params.get("shelf_id", "")
        if shelf_id:
            name = self._shelf_names.get(shelf_id, shelf_id)
            ctx["shelf"] = f"{name}({shelf_id})" if name != shelf_id else shelf_id
        location_id = params.get("location_id", "")
        if location_id:
            name = self._location_names.get(location_id, location_id)
            ctx["location"] = f"{name}({location_id})" if name != location_id else location_id
        return ctx

    async def _execute_step(self, step: TaskStep, skip_reason=None) -> StepResult:
        action = step.action
        params = step.params
        error_ctx = self._build_error_context(params)
        try:
            if action == "speak":
                cmd = SpeakCmd()
                cmd.speak_text = params["speak_text"]
                api_result = await self.fleet.speak(self.robot_id, cmd)

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code, action, error_ctx),
                    data={"speak_text": cmd.speak_text},
                    timestamp=get_now().isoformat()
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
                    error_message=get_error_message(api_result.error_code, action, error_ctx),
                    data={"x": cmd.x, "y": cmd.y, "yaw": cmd.yaw},
                    timestamp=get_now().isoformat()
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
                    error_message=get_error_message(api_result.error_code, action, error_ctx),
                    data={"location_id": cmd.location_id},
                    timestamp=get_now().isoformat()
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
                    error_message=get_error_message(api_result.error_code, action, error_ctx),
                    data={},
                    timestamp=get_now().isoformat()
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
                    error_message=get_error_message(api_result.error_code, action, error_ctx),
                    data={},
                    timestamp=get_now().isoformat()
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

                # Start shelf monitor after first successful move_shelf
                if api_result.success and self._shelf_monitor_task is None:
                    self._current_shelf_id = cmd.shelf_id
                    self._shelf_monitor_stop = False
                    self._shelf_dropped = False
                    self._shelf_monitor_task = asyncio.create_task(self._monitor_shelf())

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code, action, error_ctx),
                    data={"shelf_id": cmd.shelf_id, "location_id": cmd.location_id},
                    timestamp=get_now().isoformat()
                )
            elif action == "return_shelf":
                cmd = ReturnShelfCmd()
                cmd.shelf_id = params["shelf_id"]
                api_result = await retry_with_backoff(
                    lambda: self.fleet.return_shelf(self.robot_id, cmd)
                )

                # Stop shelf monitor after successful return_shelf
                if api_result.success:
                    await self._stop_shelf_monitor()

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code, action, error_ctx),
                    data={"shelf_id": cmd.shelf_id},
                    timestamp=get_now().isoformat()
                )
            elif action == "return_home":
                cmd = DefaultCmd()
                api_result = await self.fleet.return_home(self.robot_id, cmd)

                return StepResult(
                    success=api_result.success,
                    error_code=api_result.error_code,
                    error_message=get_error_message(api_result.error_code, action, error_ctx),
                    data={},
                    timestamp=get_now().isoformat()
                )
            elif action == "bio_scan":
                client = get_bio_sensor_client()
                if client is None:
                    return StepResult(
                        success=False,
                        error_code=-1,
                        error_message="Bio-sensor MQTT client is not available (mqtt_enabled=false)",
                        data={},
                        timestamp=get_now().isoformat()
                    )
                bed_key = params.get("bed_key")
                scan_result = await client.get_valid_scan_data(target_bed=self.target_bed, task_id=self.current_task_id, bed_name=bed_key)
                logger.info(f"Bio scan result for robot {self.robot_id}: {scan_result}")

                # Check if bio scan returned valid data
                success = scan_result is not None and scan_result.get("data") is not None
                if success:
                    logger.info(f"Bio scan completed successfully for robot {self.robot_id}")
                else:
                    logger.warning(f"Bio scan failed - no valid data obtained for robot {self.robot_id}")

                return StepResult(
                    success=success,
                    error_code=0 if success else -1,
                    error_message="Bio scan completed successfully" if success else "No valid data obtained after all retries",
                    data=scan_result or {},
                    timestamp=get_now().isoformat()
                )
            elif action == "wait":
                seconds = float(params.get("seconds", "1.0"))
                await asyncio.sleep(seconds)

                return StepResult(
                    success=True,
                    error_code=0,
                    error_message="Wait completed successfully",
                    data={"seconds": seconds},
                    timestamp=get_now().isoformat()
                )
            else:
                logger.error(f"Unknown action: {action} for robot {self.robot_id}")
                return StepResult(
                    success=False,
                    error_code=-1,
                    error_message=f"Unknown action: {action}",
                    data={"action": action},
                    timestamp=get_now().isoformat()
                )
        except grpc.aio.AioRpcError as e:
            logger.error(f"[X] gRPC error during action {action} for robot {self.robot_id}: {e.code()} - {e.details()}")
            return StepResult(
                success=False,
                error_code=int(e.code().value[0]) if hasattr(e.code(), 'value') else -1,
                error_message=f"gRPC error {e.code()}: {e.details()}",
                data={"action": action, "params": params, "grpc_code": e.code().name},
                timestamp=get_now().isoformat()
            )
        except ValueError as e:
            logger.error(f"[!] Robot {self.robot_id} not found: {str(e)}")
            return StepResult(
                success=False,
                error_code=-1,
                error_message=f"Robot {self.robot_id} not found: {str(e)}",
                data={"action": action, "params": params},
                timestamp=get_now().isoformat()
            )
        except Exception as e:
            logger.error(f"[X] Unexpected error during action {action} for robot {self.robot_id}: {str(e)}", exc_info=True)
            return StepResult(
                success=False,
                error_code=-1,
                error_message=f"Unexpected error: {str(e)}",
                data={"action": action, "params": params},
                timestamp=get_now().isoformat()
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

                if preferred_robot not in task_queues:
                    logger.error(f"Dispatcher: Preferred robot '{preferred_robot}' has no task queue (not registered). Failing task.")
                    task_to_assign.status = TaskStatus.FAILED
                    tasks_db[task_to_assign.task_id] = task_to_assign
                    continue

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

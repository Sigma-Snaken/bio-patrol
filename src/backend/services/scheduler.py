"""
Scheduler Service
Manages recurring patrol tasks using APScheduler, driven by schedule.json.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class TaskSchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False

    async def start(self):
        """Start the scheduler and load schedules from JSON."""
        if not self.is_running:
            self.scheduler.start()
            self.is_running = True
            logger.info("Task scheduler started")
            await self.reload_from_json()

    async def stop(self):
        """Stop the scheduler."""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("Task scheduler stopped")

    async def reload_from_json(self):
        """
        Read schedule.json and sync APScheduler jobs.
        Removes all existing patrol jobs, then re-creates jobs for enabled entries.
        """
        from settings.config import SCHEDULE_FILE
        from settings.defaults import DEFAULT_SCHEDULE
        from utils.json_io import load_json

        data = load_json(SCHEDULE_FILE, DEFAULT_SCHEDULE)
        schedules = data.get("schedules", [])

        # Remove all existing patrol-schedule jobs
        existing_jobs = self.scheduler.get_jobs()
        for job in existing_jobs:
            if job.id.startswith("patrol_"):
                self.scheduler.remove_job(job.id)
                logger.info(f"Removed scheduler job: {job.id}")

        # Add jobs for each enabled schedule
        added = 0
        for entry in schedules:
            schedule_id = entry.get("id", "")
            enabled = entry.get("enabled", False)
            time_str = entry.get("time", "")
            schedule_type = entry.get("type", "daily")

            if not enabled or not time_str or not schedule_id:
                continue

            try:
                hour, minute = map(int, time_str.split(":"))
            except (ValueError, TypeError):
                logger.warning(f"Invalid time format for schedule '{schedule_id}': {time_str}")
                continue

            job_id = f"patrol_{schedule_id}"

            if schedule_type == "daily":
                self.scheduler.add_job(
                    func=self._run_patrol,
                    trigger=CronTrigger(hour=hour, minute=minute),
                    id=job_id,
                    args=[schedule_id],
                    replace_existing=True,
                )
            elif schedule_type == "weekday":
                self.scheduler.add_job(
                    func=self._run_patrol,
                    trigger=CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute),
                    id=job_id,
                    args=[schedule_id],
                    replace_existing=True,
                )
            else:
                # Treat as daily fallback
                self.scheduler.add_job(
                    func=self._run_patrol,
                    trigger=CronTrigger(hour=hour, minute=minute),
                    id=job_id,
                    args=[schedule_id],
                    replace_existing=True,
                )

            added += 1
            logger.info(f"Scheduled patrol '{schedule_id}' at {time_str} ({schedule_type})")

        logger.info(f"Schedule reload complete: {added} active schedule(s) from {len(schedules)} total")

    async def _run_patrol(self, schedule_id: str):
        """Execute a scheduled patrol by creating a patrol task."""
        logger.info(f"Scheduled patrol triggered: {schedule_id}")
        try:
            from settings.config import PATROL_FILE, BEDS_FILE, get_runtime_settings
            from settings.defaults import DEFAULT_PATROL, DEFAULT_BEDS
            from utils.json_io import load_json
            from common_types import Task, TaskStep, TaskStatus, StepStatus, generate_task_id
            from services.task_runtime import tasks_db, submit_task

            patrol_cfg = load_json(PATROL_FILE, DEFAULT_PATROL)
            beds_cfg = load_json(BEDS_FILE, DEFAULT_BEDS)
            cfg = get_runtime_settings()
            shelf_id = cfg.get("shelf_id", "S_04")
            beds_order = patrol_cfg.get("beds_order", [])
            beds_map = beds_cfg.get("beds", {})

            enabled_beds = [b for b in beds_order if b.get("enabled", False)]
            if not enabled_beds:
                logger.warning(f"Scheduled patrol '{schedule_id}' skipped: no enabled beds")
                return

            steps = []
            step_counter = 0

            for bed_entry in enabled_beds:
                bed_key = bed_entry["bed_key"]
                bed_info = beds_map.get(bed_key, {})
                location_id = bed_info.get("location_id", bed_key)

                move_step_id = f"move_{step_counter}"
                action_step_id = f"action_{step_counter}"

                steps.append(TaskStep(
                    step_id=move_step_id,
                    action="move_shelf",
                    params={"shelf_id": shelf_id, "location_id": location_id},
                    status=StepStatus.PENDING,
                    skip_on_failure=[action_step_id],
                ))
                steps.append(TaskStep(
                    step_id=action_step_id,
                    action="bio_scan",
                    params={},
                    status=StepStatus.PENDING,
                ))
                step_counter += 1

            # Final return_shelf
            steps.append(TaskStep(
                step_id=f"return_{step_counter}",
                action="return_shelf",
                params={"shelf_id": shelf_id},
                status=StepStatus.PENDING,
            ))

            task = Task(
                task_id=generate_task_id(),
                robot_id="kachaka",
                steps=steps,
                status=TaskStatus.QUEUED,
            )
            await submit_task(task)
            logger.info(
                f"Scheduled patrol '{schedule_id}' created task {task.task_id} "
                f"with {len(enabled_beds)} beds"
            )

        except Exception as e:
            logger.error(f"Error executing scheduled patrol '{schedule_id}': {e}", exc_info=True)


# Global scheduler instance
scheduler_service = TaskSchedulerService()

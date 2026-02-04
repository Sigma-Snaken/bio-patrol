"""
Settings API Router
Handles system configuration, beds, patrol, and schedule management.
"""
import uuid
import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from settings.config import (
    SETTINGS_FILE, BEDS_FILE, PATROL_FILE, SCHEDULE_FILE,
    get_runtime_settings,
)
from settings.defaults import DEFAULT_SETTINGS, DEFAULT_BEDS, DEFAULT_PATROL, DEFAULT_SCHEDULE
from utils.json_io import load_json, save_json
from common_types import (
    Task, TaskStep, TaskStatus, StepStatus, generate_task_id,
)
from services.task_runtime import tasks_db, global_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Settings & Config"])


# ═══════════════════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/settings")
async def get_settings():
    """Return merged DEFAULT_SETTINGS + settings.json"""
    return get_runtime_settings()


@router.post("/settings")
async def save_settings(body: dict):
    """Merge incoming JSON into settings.json and save."""
    current = load_json(SETTINGS_FILE, {})
    current.update(body)
    save_json(SETTINGS_FILE, current)
    return {"status": "ok", "data": get_runtime_settings()}


# ═══════════════════════════════════════════════════════════════════════════
# BEDS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/beds")
async def get_beds():
    """Return beds.json (or generate default)."""
    data = load_json(BEDS_FILE, DEFAULT_BEDS)
    if not data or data == {}:
        data = DEFAULT_BEDS
    return data


@router.post("/beds")
async def save_beds(body: dict):
    """Save beds.json."""
    save_json(BEDS_FILE, body)
    return {"status": "ok", "data": body}


# ═══════════════════════════════════════════════════════════════════════════
# PATROL
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/patrol")
async def get_patrol():
    """Return patrol.json."""
    data = load_json(PATROL_FILE, DEFAULT_PATROL)
    if not data or data == {}:
        data = DEFAULT_PATROL
    return data


@router.post("/patrol")
async def save_patrol(body: dict):
    """Save patrol.json."""
    save_json(PATROL_FILE, body)
    return {"status": "ok", "data": body}


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULE
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/schedule")
async def get_schedule():
    """Return schedule.json."""
    data = load_json(SCHEDULE_FILE, DEFAULT_SCHEDULE)
    if not data or data == {}:
        data = DEFAULT_SCHEDULE
    return data


@router.post("/schedule")
async def save_schedule(body: dict):
    """Save schedule.json."""
    save_json(SCHEDULE_FILE, body)
    # Reload schedules in the scheduler service
    try:
        from services.scheduler import scheduler_service
        await scheduler_service.reload_from_json()
    except Exception as e:
        logger.warning(f"Failed to reload scheduler after save: {e}")
    return {"status": "ok", "data": body}


@router.delete("/schedule/{schedule_id}")
async def delete_schedule_entry(schedule_id: str):
    """Remove a single schedule entry by its id."""
    data = load_json(SCHEDULE_FILE, DEFAULT_SCHEDULE)
    schedules = data.get("schedules", [])
    original_len = len(schedules)
    schedules = [s for s in schedules if s.get("id") != schedule_id]
    if len(schedules) == original_len:
        raise HTTPException(status_code=404, detail=f"Schedule '{schedule_id}' not found")
    data["schedules"] = schedules
    save_json(SCHEDULE_FILE, data)
    # Reload schedules
    try:
        from services.scheduler import scheduler_service
        await scheduler_service.reload_from_json()
    except Exception as e:
        logger.warning(f"Failed to reload scheduler after delete: {e}")
    return {"status": "ok", "data": data}


# ═══════════════════════════════════════════════════════════════════════════
# PATROL START  (patrol mode vs demo mode)
# ═══════════════════════════════════════════════════════════════════════════

class PatrolStartRequest(BaseModel):
    mode: str = "patrol"  # "patrol" or "demo"


@router.post("/patrol/start")
async def start_patrol(req: PatrolStartRequest):
    """
    Start a patrol run.
    - patrol: move_shelf + bio_scan per enabled bed
    - demo: move_shelf + wait(5s) per enabled bed (no bio_scan)
    """
    patrol_cfg = load_json(PATROL_FILE, DEFAULT_PATROL)
    beds_cfg = load_json(BEDS_FILE, DEFAULT_BEDS)
    shelf_id = patrol_cfg.get("shelf_id", "S_04")
    beds_order = patrol_cfg.get("beds_order", [])
    beds_map = beds_cfg.get("beds", {})

    enabled_beds = [b for b in beds_order if b.get("enabled", False)]
    if not enabled_beds:
        raise HTTPException(status_code=400, detail="No enabled beds in patrol config")

    steps = []
    step_counter = 0

    for bed_entry in enabled_beds:
        bed_key = bed_entry["bed_key"]
        bed_info = beds_map.get(bed_key, {})
        location_id = bed_info.get("location_id", bed_key)

        move_step_id = f"move_{step_counter}"
        action_step_id = f"action_{step_counter}"

        # move_shelf step — skip_on_failure points to the action step
        move_step = TaskStep(
            step_id=move_step_id,
            action="move_shelf",
            params={"shelf_id": shelf_id, "location_id": location_id},
            status=StepStatus.PENDING,
            skip_on_failure=[action_step_id],
        )
        steps.append(move_step)

        if req.mode == "demo":
            action_step = TaskStep(
                step_id=action_step_id,
                action="wait",
                params={"seconds": 5},
                status=StepStatus.PENDING,
            )
        else:
            action_step = TaskStep(
                step_id=action_step_id,
                action="bio_scan",
                params={},
                status=StepStatus.PENDING,
            )
        steps.append(action_step)
        step_counter += 1

    # Final return_shelf step
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
    tasks_db[task.task_id] = task
    asyncio.create_task(global_queue.put(task))
    logger.info(f"Patrol started (mode={req.mode}): task {task.task_id} with {len(enabled_beds)} beds")
    return {"status": "ok", "task_id": task.task_id, "mode": req.mode, "beds_count": len(enabled_beds)}


# ═══════════════════════════════════════════════════════════════════════════
# SHELF DROP RECOVERY
# ═══════════════════════════════════════════════════════════════════════════

class RecoverShelfRequest(BaseModel):
    shelf_id: str
    location_id: str


@router.post("/patrol/recover-shelf")
async def recover_shelf(req: RecoverShelfRequest):
    """
    Recovery endpoint after shelf-drop (error 14606).
    Robot re-finds and moves the shelf to the given location.
    """
    try:
        from dependencies import get_fleet
        from services.fleet_api import MoveShelfCmd
        fleet = get_fleet()
        cmd = MoveShelfCmd()
        cmd.shelf_id = req.shelf_id
        cmd.location_id = req.location_id
        result = await fleet.move_shelf("kachaka", cmd)

        if result.success:
            # Clear shelf_drop status from any active task
            for task in tasks_db.values():
                if task.status and task.status.value == "shelf_dropped":
                    task.status = TaskStatus.DONE
                    break
            return {"status": "ok", "message": "Shelf recovered successfully"}
        else:
            return {"status": "error", "message": f"Recovery failed: error {result.error_code}"}
    except Exception as e:
        logger.error(f"Shelf recovery failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

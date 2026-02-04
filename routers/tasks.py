from fastapi import APIRouter, HTTPException
router = APIRouter(prefix='/api', tags=['Tasks Scheduler'])

import uuid
import asyncio

import logging
logger = logging.getLogger(__name__)

from typing import List

from common_types import Task, TaskStatus, validate_task_conditional_logic
from services.task_runtime import tasks_db, global_queue, current_tasks


# --- RESTful APIs Interfaces ---
@router.post("/tasks", response_model=Task)
async def create_task(task_input: Task):
    task_id = str(uuid.uuid4())

    # Default robot_id to "kachaka" (single robot system)
    if not task_input.robot_id:
        task_input.robot_id = "kachaka"

    # Validate conditional logic in task definition
    validation_errors = validate_task_conditional_logic(task_input)
    if validation_errors:
        error_message = f"Task validation failed: {'; '.join(validation_errors)}"
        logger.warning(f"Task creation failed: {error_message}")
        raise HTTPException(status_code=400, detail=error_message)
    
    # Create a new task instance from the input, preserving robot_id if specified
    new_task = Task(
        task_id=task_id, 
        steps=task_input.steps, 
        status=TaskStatus.QUEUED,
        robot_id=task_input.robot_id  # Preserve robot_id from input
    )
    tasks_db[task_id] = new_task
    # Use asyncio.create_task for non-blocking put if global_queue could be full (though default is infinite)
    asyncio.create_task(global_queue.put(new_task)) 
    logger.info(f"Task {task_id} created and added to global_queue.")
    return new_task

@router.get("/tasks", response_model=List[Task])
def list_tasks():
    return list(tasks_db.values())

@router.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: str):
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.post("/tasks/{task_id}/cancel", response_model=Task)
async def cancel_task(task_id: str):
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    logger.info(f"Attempting to cancel task {task_id}. Current status: {task.status}")
    if task.status in [TaskStatus.DONE, TaskStatus.FAILED]:
        logger.warning(f"Cannot cancel task {task_id}: already finished (status: {task.status}).")
        raise HTTPException(status_code=400, detail=f"Cannot cancel a finished task (status: {task.status})")
    
    if task.status == TaskStatus.CANCELLED:
        logger.info(f"Task {task_id} is already cancelled.")
        return task # Already cancelled

    task.status = TaskStatus.CANCELLED
    tasks_db[task_id] = task # Update in DB
    logger.info(f"Task {task_id} status set to CANCELLED.")
    
    # If task was in a robot's specific queue but not yet started by worker,
    # the worker will see CANCELLED status when it picks it up.
    # If it was in global_queue, dispatcher might still pick it up, assign robot_id,
    # then worker will see CANCELLED.
    # If it was IN_PROGRESS, TaskEngine's step loop will see CANCELLED.
    return task

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == TaskStatus.IN_PROGRESS and task.robot_id in current_tasks and current_tasks[task.robot_id] == task_id:
        raise HTTPException(status_code=400, detail="Cannot delete a task that is currently in progress. Cancel it first.")
    
    # Attempt to cancel if it's in a state that can be cancelled
    if task.status not in [TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED]:
        task.status = TaskStatus.CANCELLED
        logger.info(f"Task {task_id} marked as CANCELLED before deletion.")

    tasks_db.pop(task_id, None)
    logger.info(f"Task {task_id} deleted from tasks_db.")
    return {"message": f"Task {task_id} deleted (or marked as cancelled if it was active)."}

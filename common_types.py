"""
common_types.py
集中定義所有專案共用的型別、Enum、工具函式與型別別名，供各模組 import 使用。
"""
from enum import Enum
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from datetime import datetime

# Common Enum
class StepStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAIL = "fail"
    SKIPPED = "skipped"

class TaskStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SHELF_DROPPED = "shelf_dropped"

# Enhanced Result Models
class StepResult(BaseModel):
    success: bool
    error_code: int = 0
    error_message: str = ""
    data: Optional[Dict[str, Any]] = None
    timestamp: str = ""

# Common Pydantic Model
class TaskStep(BaseModel):
    step_id: str
    action: str
    params: Dict[str, Any]
    status: StepStatus = StepStatus.PENDING
    result: Optional[StepResult] = None
    skip_on_failure: Optional[List[str]] = None  # Step IDs to skip if this step fails

class Task(BaseModel):
    task_id: str = ""
    robot_id: Optional[str] = None
    steps: List[TaskStep]
    status: TaskStatus = TaskStatus.QUEUED
    metadata: Optional[Dict[str, Any]] = None

class Robot(BaseModel):
    robot_id: str

# Kachaka Error Code Dictionary
KACHAKA_ERROR_CODES = {
    0: "Success",
    21051: "Robot paused",
    21052: "Step detected", 
    14606: "Not docked with furniture",
    14605: "Cannot place furniture on charging dock",
    -1: "Internal error or exception",
    # Add more error codes as needed
}

# 其他可擴充型別或工具函式
# 例如: 統一的 API 回應格式、錯誤型別、ID 產生器等

def get_error_message(error_code: int) -> str:
    """Get user-friendly error message for Kachaka error code"""
    return KACHAKA_ERROR_CODES.get(error_code, f"Unknown error code: {error_code}")

def validate_task_conditional_logic(task: "Task") -> List[str]:
    """
    Validate task conditional logic and return list of validation errors
    """
    errors = []
    step_ids = {step.step_id for step in task.steps}
    
    for step in task.steps:
        if step.skip_on_failure:
            # Check if all skip targets exist
            for skip_target in step.skip_on_failure:
                if skip_target not in step_ids:
                    errors.append(f"Step '{step.step_id}' references non-existent skip target '{skip_target}'")
                
                # Check for self-reference
                if skip_target == step.step_id:
                    errors.append(f"Step '{step.step_id}' cannot skip itself")
    
    return errors

def generate_task_id() -> str:
    import uuid
    return str(uuid.uuid4())

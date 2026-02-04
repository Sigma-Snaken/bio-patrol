# gRPC Error Handling & Retry Logic

## Problem

The system experienced frequent gRPC `UNAVAILABLE` errors with "Not ready" messages during `move_shelf` operations, causing task failures.

## Solution

### Retry with Exponential Backoff (`task_runtime.py`)

Critical robot operations are wrapped with retry logic:

- `move_shelf` — 3 retries, 2.0s base delay
- `return_shelf` — 3 retries, 2.0s base delay
- `move_to_location` — 2 retries
- `dock_shelf` / `undock_shelf` — 2 retries

Retryable gRPC error codes: `UNAVAILABLE`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`.
Non-retryable errors fail immediately.

Backoff formula: `delay = min(base_delay * 2^attempt, max_delay)`

### Robot Readiness Validation (`fleet_api.py`)

- `check_robot_readiness()` validates robot state before operations
- `wait_for_robot_ready()` polls with configurable timeout
- Connection testing with automatic status updates

### Shelf Drop Recovery

Error code 14606 triggers:
1. Task marked as `SHELF_DROPPED`
2. Robot returns to home location
3. Telegram alert sent to operator
4. UI modal shown to user

## Configuration

Retry parameters are set in `data/config/settings.json`:

```json
{
  "robot_max_retries": 3,
  "robot_retry_base_delay": 2.0,
  "robot_retry_max_delay": 10.0
}
```

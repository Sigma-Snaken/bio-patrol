# Design: Integrate kachaka_core into bio-patrol

**Date**: 2026-02-23
**Status**: Approved

## Problem

bio-patrol directly uses `kachaka_api.aio.KachakaApiClient` (async), bypassing `kachaka_core`. This causes:

1. **No command_id tracking** — cannot verify which command's result is returned, leading to racing condition risks in shelf monitoring and cancel scenarios
2. **Async black box** — `await client.move_shelf(...)` blocks the coroutine with no visibility into command lifecycle (PENDING/RUNNING/COMPLETED)
3. **Duplicated logic** — retry, resolver patching, error handling reimplemented separately from kachaka_core
4. **No metrics** — no RTT, poll counts, or success rates for monitoring
5. **Network instability risk** — async transport layer loses deterministic control when network quality is poor

## Decision

**Sync communication layer + async application layer.**

- Communication layer: Use `kachaka_core` (synchronous `RobotController` with `command_id` tracking, `@with_retry`, background polling)
- Application layer: Bridge via `asyncio.to_thread()` in bio-patrol's `FleetAPI`
- `kachaka_core` stays pure synchronous — no async dependency added

## Architecture

### Before

```
Router → TaskEngine → FleetAPI → RobotManager → aio.KachakaApiClient
                                    ↑ Reimplemented:
                                    - retry_with_backoff()
                                    - _patch_resolver()
                                    - check_robot_readiness()
                                    - No command_id tracking
```

### After

```
Router → TaskEngine → FleetAPI → kachaka_core (sync)
              │           │
              │           ├─ asyncio.to_thread(ctrl.move_to_location, ...)
              │           ├─ asyncio.to_thread(ctrl.move_shelf, ...)
              │           └─ asyncio.to_thread(queries.get_status, ...)
              │
              └─ shelf monitor: asyncio.to_thread(queries.get_moving_shelf, ...)
                                + cancel via KachakaCommands (independent gRPC call)
```

### Layer responsibilities

| Layer | Responsibility | Async? |
|-------|---------------|--------|
| **kachaka_core** | Connection pooling, command_id tracking, retry, polling, metrics | Sync |
| **FleetAPI** | `to_thread()` bridge, multi-robot management | Async wrapper |
| **TaskEngine** | Patrol flow, shelf monitoring, step scheduling, error recovery | Async |
| **Router** | HTTP API, SSE streaming | Async |

## FleetAPI redesign

```python
class FleetAPI:
    def __init__(self):
        self._connections: Dict[str, KachakaConnection] = {}
        self._controllers: Dict[str, RobotController] = {}
        self._queries: Dict[str, KachakaQueries] = {}

    async def register_robot(self, robot_id: str, ip: str, name: str = ""):
        conn = KachakaConnection.get(ip)
        result = await asyncio.to_thread(conn.ping)
        if not result["ok"]:
            raise ConnectionError(f"Robot {ip}: {result['error']}")
        await asyncio.to_thread(conn.ensure_resolver)
        ctrl = RobotController(conn)
        ctrl.start()
        self._connections[robot_id] = conn
        self._controllers[robot_id] = ctrl
        self._queries[robot_id] = KachakaQueries(conn)

    async def move_shelf(self, robot_id, shelf, location, timeout=120.0):
        ctrl = self._controllers[robot_id]
        return await asyncio.to_thread(ctrl.move_shelf, shelf, location, timeout=timeout)

    async def cancel_command(self, robot_id):
        conn = self._connections[robot_id]
        cmds = KachakaCommands(conn)
        return await asyncio.to_thread(cmds.cancel_command)

    async def get_status(self, robot_id):
        ctrl = self._controllers[robot_id]
        state = ctrl.state  # thread-safe snapshot
        return {
            "pose": {"x": state.pose_x, "y": state.pose_y, "theta": state.pose_theta},
            "battery": state.battery_pct,
            "is_command_running": state.is_command_running,
        }
```

## Cancel mechanism

Cancel operates on the **robot**, not the controller. When shelf monitor detects a drop:

1. Sets `_shelf_dropped = True` (flag)
2. Calls `KachakaCommands.cancel_command()` → tells robot to stop
3. `RobotController._execute_command` polling loop detects state change → returns `error_code=10001` (interrupted)
4. TaskEngine checks `_shelf_dropped` flag first (authoritative), error_code second (supplementary)

### Dual error disambiguation

| Scenario | `_shelf_dropped` | error_code | Handling |
|----------|------------------|------------|----------|
| Monitor detects first → cancel | `True` | 10001 (interrupted) | Shelf drop flow |
| Robot detects first → command fails | `True` (monitor also detects) | Shelf-related code | Shelf drop flow |
| User cancels task | `False` | 10001 | Normal cancel flow |
| Other command failure | `False` | Other code | Error handling flow |

## TaskEngine changes

### Modified

- `_execute_step()`: Uses `self.fleet.xxx()` returning dicts instead of protobuf Results
- `_make_result()`: Simplified — reads from dict, no protobuf parsing
- `_monitor_shelf()`: Uses `self.fleet.get_moving_shelf()` returning dict
- `_handle_shelf_drop()`: cancel via `self.fleet.cancel_command()`, no direct client access

### Deleted

- `retry_with_backoff()` — replaced by kachaka_core `@with_retry`
- `get_error_message()` — replaced by kachaka_core `_resolve_error_description`
- `MoveShelfCmd` and similar dataclasses — replaced by direct parameters

### Unchanged

- Shelf monitor 3s polling logic and `_shelf_dropped` flag
- Step scheduling (step loop, skip_on_failure)
- SSE event streaming
- Telegram notifications
- Database recording

### Metrics integration

```python
# At task completion
ctrl = self.fleet._controllers[self.robot_id]
m = ctrl.metrics
task.metadata["metrics"] = {
    "poll_count": m.poll_count,
    "avg_rtt_ms": sum(m.poll_rtt_list) / len(m.poll_rtt_list) if m.poll_rtt_list else 0,
    "poll_success_rate": m.poll_success_count / m.poll_count if m.poll_count else 1.0,
}
ctrl.reset_metrics()
```

## Dependency management

### Installation

```bash
pip install -e /home/snaken/CodeBase/kachaka-sdk-toolkit
```

### Docker

```dockerfile
COPY kachaka-sdk-toolkit /app/kachaka-sdk-toolkit
RUN pip install -e /app/kachaka-sdk-toolkit
```

## Files affected

### Deleted

| File | Reason |
|------|--------|
| `services/robot_manager.py` | Replaced by `KachakaConnection` pool |

### Heavily simplified

| File | Change |
|------|--------|
| `services/fleet_api.py` | ~580 → ~150 lines. Remove direct SDK calls, retry logic, readiness polling, resolver management |
| `services/task_runtime.py` | ~640 → ~450 lines. Remove `retry_with_backoff()`, `get_error_message()`, intermediate dataclasses |
| `dependencies.py` | Remove `RobotManager` references |

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Sync client in async app | `to_thread()` isolates sync calls; FastAPI event loop not blocked |
| Thread consumption with multiple robots | ~2 threads per robot (controller + executor). 10 robots = ~20 threads, acceptable |
| `KachakaConnection` pool keyed by IP, not robot_id | FleetAPI maintains `robot_id → IP` mapping |
| Protobuf direct usage in `_query_shelf_pose()` | Replace with `queries.list_shelves()` returning dict |

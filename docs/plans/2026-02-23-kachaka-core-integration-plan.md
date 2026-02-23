# kachaka_core Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace bio-patrol's direct async SDK usage with sync kachaka_core (RobotController + KachakaCommands + KachakaQueries), bridged via `asyncio.to_thread()`.

**Architecture:** Sync communication layer (kachaka_core handles connection, retry, command_id, metrics) + async application layer (FleetAPI bridges via `to_thread()`, TaskEngine orchestrates patrol flow). RobotManager deleted; FleetAPI manages kachaka_core objects directly.

**Tech Stack:** kachaka_core (sync), asyncio.to_thread, FastAPI, kachaka-api gRPC SDK

**Design doc:** `docs/plans/2026-02-23-kachaka-core-integration-design.md`

---

### Task 1: Add kachaka_core dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `Dockerfile`

**Step 1: Add kachaka-core to pyproject.toml**

In `pyproject.toml`, add `kachaka-core` as a local path dependency:

```toml
[project]
dependencies = [
    "fastapi==0.115.6",
    "grpcio==1.66.1",
    "kachaka-api==3.10.6",
    "protobuf==5.27.2",
    "paho-mqtt==2.1.0",
    "httpx>=0.27.0",
    "uvicorn==0.34.0",
    "apscheduler>=3.10.4",
    "kachaka-core",
]

[tool.uv.sources]
kachaka-core = { path = "../kachaka-sdk-toolkit", editable = true }
```

**Step 2: Install and verify import**

Run: `cd /home/snaken/CodeBase/bio-patrol && uv sync`
Then: `uv run python -c "from kachaka_core import KachakaConnection, KachakaCommands, KachakaQueries, RobotController; print('OK')"`
Expected: `OK`

**Step 3: Update Dockerfile**

Add kachaka-sdk-toolkit copy and install before the `uv sync` step:

```dockerfile
# ---------- builder ----------
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy kachaka-sdk-toolkit (local dependency)
COPY kachaka-sdk-toolkit/ /app/kachaka-sdk-toolkit/

# Install dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
```

**Step 4: Commit**

```bash
git add pyproject.toml Dockerfile
git commit -m "feat: add kachaka-core as local dependency"
```

---

### Task 2: Rewrite FleetAPI — core command methods

**Files:**
- Rewrite: `src/backend/services/fleet_api.py`

This is the largest change. FleetAPI becomes a thin async bridge over kachaka_core sync objects.

**Step 1: Write the new FleetAPI**

Replace `src/backend/services/fleet_api.py` entirely:

```python
"""FleetAPI — async bridge over kachaka_core (sync).

All robot commands go through kachaka_core's RobotController (command_id
verified, retry-safe, metrics-instrumented). Async callers use
asyncio.to_thread() so the FastAPI event loop is never blocked.
"""
import asyncio
import logging
import time
from typing import Dict, Optional

from kachaka_core import (
    KachakaConnection,
    KachakaCommands,
    KachakaQueries,
    RobotController,
)

logger = logging.getLogger(__name__)


# ── Robot metadata ──────────────────────────────────────────────────
class _RobotSlot:
    """Per-robot objects managed by FleetAPI."""
    __slots__ = ("robot_id", "ip", "name", "conn", "ctrl", "cmds", "queries", "status", "registered_at")

    def __init__(self, robot_id: str, ip: str, name: str,
                 conn: KachakaConnection, ctrl: RobotController,
                 cmds: KachakaCommands, queries: KachakaQueries):
        self.robot_id = robot_id
        self.ip = ip
        self.name = name
        self.conn = conn
        self.ctrl = ctrl
        self.cmds = cmds
        self.queries = queries
        self.status = "online"
        self.registered_at = time.time()


class FleetAPI:
    def __init__(self):
        self._robots: Dict[str, _RobotSlot] = {}

    # ── helpers ─────────────────────────────────────────────────────
    def _get(self, robot_id: str) -> _RobotSlot:
        slot = self._robots.get(robot_id)
        if not slot:
            raise ValueError(f"Robot {robot_id} not found")
        return slot

    # ── lifecycle ───────────────────────────────────────────────────
    async def register_robot(self, robot_id: str, ip: str, name: str = "") -> bool:
        if robot_id in self._robots:
            logger.warning(f"Robot {robot_id} already registered")
            return False

        conn = KachakaConnection.get(ip)
        ping = await asyncio.to_thread(conn.ping)
        if not ping["ok"]:
            logger.error(f"Robot {ip} ping failed: {ping.get('error')}")
            raise ConnectionError(f"Robot {ip}: {ping.get('error')}")

        await asyncio.to_thread(conn.ensure_resolver)

        ctrl = RobotController(conn)
        ctrl.start()
        cmds = KachakaCommands(conn)
        queries = KachakaQueries(conn)

        self._robots[robot_id] = _RobotSlot(robot_id, ip, name, conn, ctrl, cmds, queries)
        logger.info(f"Registered robot {robot_id} at {ip} via kachaka_core")
        return True

    async def unregister_robot(self, robot_id: str) -> bool:
        slot = self._robots.pop(robot_id, None)
        if not slot:
            return False
        slot.ctrl.stop()
        KachakaConnection.remove(slot.ip)
        logger.info(f"Unregistered robot {robot_id}")
        return True

    # ── status ──────────────────────────────────────────────────────
    async def get_robot_status(self, robot_id: str) -> Optional[Dict]:
        slot = self._robots.get(robot_id)
        if not slot:
            return None
        return {
            "id": slot.robot_id,
            "url": slot.ip,
            "name": slot.name,
            "status": slot.status,
            "last_seen": slot.registered_at,
        }

    async def get_all_robots(self) -> Dict[str, Dict]:
        return {
            rid: {
                "id": s.robot_id, "url": s.ip, "name": s.name,
                "status": s.status, "last_seen": s.registered_at,
            }
            for rid, s in self._robots.items()
        }

    async def update_robot_status(self, robot_id: str, status: str) -> bool:
        slot = self._robots.get(robot_id)
        if not slot:
            return False
        slot.status = status
        return True

    # ── controller state (from background polling) ──────────────────
    def get_controller_state(self, robot_id: str):
        """Thread-safe snapshot of RobotController's background state."""
        return self._get(robot_id).ctrl.state

    def get_metrics(self, robot_id: str):
        """Return controller metrics (poll RTT, counts, etc.)."""
        return self._get(robot_id).ctrl.metrics

    def reset_metrics(self, robot_id: str):
        self._get(robot_id).ctrl.reset_metrics()

    # ── movement commands (via RobotController — command_id verified) ─
    async def move_to_location(self, robot_id: str, location: str,
                                timeout: float = 120.0) -> dict:
        ctrl = self._get(robot_id).ctrl
        return await asyncio.to_thread(
            ctrl.move_to_location, location, timeout=timeout
        )

    async def move_shelf(self, robot_id: str, shelf: str, location: str,
                          timeout: float = 120.0) -> dict:
        ctrl = self._get(robot_id).ctrl
        return await asyncio.to_thread(
            ctrl.move_shelf, shelf, location, timeout=timeout
        )

    async def return_shelf(self, robot_id: str, shelf: str = "",
                            timeout: float = 60.0) -> dict:
        ctrl = self._get(robot_id).ctrl
        return await asyncio.to_thread(
            ctrl.return_shelf, shelf, timeout=timeout
        )

    async def return_home(self, robot_id: str, timeout: float = 60.0) -> dict:
        ctrl = self._get(robot_id).ctrl
        return await asyncio.to_thread(ctrl.return_home, timeout=timeout)

    # ── simple commands (via KachakaCommands — @with_retry) ─────────
    async def speak(self, robot_id: str, text: str) -> dict:
        cmds = self._get(robot_id).cmds
        return await asyncio.to_thread(cmds.speak, text)

    async def dock_shelf(self, robot_id: str) -> dict:
        cmds = self._get(robot_id).cmds
        return await asyncio.to_thread(cmds.dock_shelf)

    async def undock_shelf(self, robot_id: str) -> dict:
        cmds = self._get(robot_id).cmds
        return await asyncio.to_thread(cmds.undock_shelf)

    async def move_to_pose(self, robot_id: str, x: float, y: float,
                            yaw: float) -> dict:
        cmds = self._get(robot_id).cmds
        return await asyncio.to_thread(cmds.move_to_pose, x, y, yaw)

    async def cancel_command(self, robot_id: str) -> dict:
        cmds = self._get(robot_id).cmds
        return await asyncio.to_thread(cmds.cancel_command)

    # ── queries (via KachakaQueries — @with_retry) ──────────────────
    async def get_pose(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.get_pose)

    async def get_battery_info(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.get_battery)

    async def get_locations(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.list_locations)

    async def get_shelves(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.list_shelves)

    async def get_moving_shelf(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.get_moving_shelf)

    async def get_command_state(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.get_command_state)

    async def get_last_command_result(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.get_last_command_result)

    async def get_errors(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.get_errors)

    async def get_status(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.get_status)

    async def get_serial_number(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.get_serial_number)

    async def get_map(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.get_map)

    async def get_map_list(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.list_maps)

    async def get_speaker_volume(self, robot_id: str) -> dict:
        q = self._get(robot_id).queries
        return await asyncio.to_thread(q.get_speaker_volume)

    # ── raw SDK access (for endpoints not in kachaka_core) ──────────
    def get_raw_client(self, robot_id: str):
        """Return the underlying KachakaApiClient for advanced/ROS endpoints.
        Use sparingly — prefer kachaka_core wrappers for standard operations."""
        return self._get(robot_id).conn.sdk
```

**Step 2: Verify syntax**

Run: `cd /home/snaken/CodeBase/bio-patrol && uv run python -c "import ast; ast.parse(open('src/backend/services/fleet_api.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/backend/services/fleet_api.py
git commit -m "refactor: rewrite FleetAPI as async bridge over kachaka_core"
```

---

### Task 3: Rewrite TaskEngine — remove duplicated logic

**Files:**
- Modify: `src/backend/services/task_runtime.py`

**Step 1: Remove `retry_with_backoff` and Cmd imports**

Delete `retry_with_backoff()` function (lines 39-64).
Remove Cmd dataclass imports (lines 8-11):
```python
# DELETE these lines:
from services.fleet_api import (
    DefaultCmd, SpeakCmd, MoveToPoseCmd, Move2LocationCmd,
    MoveShelfCmd, ReturnShelfCmd
)
```
Also remove `import grpc.aio` (line 5) — no longer needed since kachaka_core handles gRPC errors.

**Step 2: Rewrite `_refresh_name_cache()`**

kachaka_core queries return dicts, not protobuf objects:

```python
async def _refresh_name_cache(self):
    """Fetch shelf/location names from robot for readable logs."""
    try:
        result = await self.fleet.get_shelves(self.robot_id)
        if result.get("ok"):
            self._shelf_names = {s["id"]: s["name"] for s in result.get("shelves", [])}
        result = await self.fleet.get_locations(self.robot_id)
        if result.get("ok"):
            self._location_names = {l["id"]: l["name"] for l in result.get("locations", [])}
    except Exception as e:
        logger.warning(f"Failed to refresh name cache: {e}")
```

**Step 3: Rewrite `_monitor_shelf()` cancel pattern**

Replace direct `fleet.manager.get_robot_client()` access with `fleet.cancel_command()`:

```python
async def _monitor_shelf(self):
    """Background coroutine: polls get_moving_shelf() every 3s."""
    logger.info(f"[SHELF MONITOR] Started for robot {self.robot_id}")
    while not self._shelf_monitor_stop:
        await asyncio.sleep(3)
        if self._shelf_monitor_stop:
            break
        try:
            result = await self.fleet.get_moving_shelf(self.robot_id)
            shelf_id = result.get("shelf_id") if result.get("ok") else None
            if not shelf_id:
                logger.warning(f"[SHELF MONITOR] Robot {self.robot_id} no longer carrying a shelf!")
                self._shelf_dropped = True
                try:
                    await self.fleet.cancel_command(self.robot_id)
                    logger.info(f"[SHELF MONITOR] Cancelled current command on robot {self.robot_id}")
                except Exception as ce:
                    logger.debug(f"[SHELF MONITOR] cancel_command failed (non-critical): {ce}")
                break
        except Exception as e:
            logger.debug(f"[SHELF MONITOR] Transient error: {e}")
    logger.info(f"[SHELF MONITOR] Stopped for robot {self.robot_id}")
```

**Step 4: Rewrite `_query_shelf_pose()`**

Remove protobuf MessageToDict usage:

```python
async def _query_shelf_pose(self, shelf_id: str) -> Optional[dict]:
    """Query current shelf position from the robot."""
    try:
        result = await self.fleet.get_shelves(self.robot_id)
        if result.get("ok"):
            for s in result.get("shelves", []):
                if s.get("id") == shelf_id:
                    pose = s.get("pose", {})
                    shelf_pose = {"x": pose.get("x", 0), "y": pose.get("y", 0), "theta": pose.get("theta", 0)}
                    logger.info(f"[SHELF DROP] Shelf {shelf_id} pose: {shelf_pose}")
                    return shelf_pose
    except Exception as e:
        logger.warning(f"[SHELF DROP] Failed to get shelf pose: {e}")
    return None
```

**Step 5: Rewrite `_handle_shelf_drop()` cancel + return_home**

Replace direct client access and Cmd usage:

```python
# In _handle_shelf_drop(), replace:
#   client = self.fleet.manager.get_robot_client(self.robot_id)
#   if client: await client.cancel_command()
# With:
try:
    await self.fleet.cancel_command(self.robot_id)
    logger.info(f"[SHELF DROP] Cancelled current command on robot {self.robot_id}")
except Exception as ce:
    logger.debug(f"[SHELF DROP] cancel_command failed (non-critical): {ce}")

# Replace:
#   cmd = DefaultCmd()
#   await self.fleet.return_home(self.robot_id, cmd)
# With:
try:
    await self.fleet.return_home(self.robot_id)
    logger.info(f"[SHELF DROP] Robot {self.robot_id} sent home")
except Exception as rh_err:
    logger.error(f"[SHELF DROP] Failed to send robot home: {rh_err}")
```

**Step 6: Rewrite `_make_result()` for dict responses**

kachaka_core returns `{"ok": bool, "error_code": int, "error": str, ...}`:

```python
def _make_result(self, api_result: dict, action: str, data: dict) -> StepResult:
    """Create StepResult from kachaka_core dict result."""
    return StepResult(
        success=api_result.get("ok", False),
        error_code=api_result.get("error_code", 0),
        error_message=api_result.get("error", "") if not api_result.get("ok") else "",
        data=data,
        timestamp=get_now().isoformat(),
    )
```

**Step 7: Rewrite `_execute_step()` — all action handlers**

Replace every Cmd-based call with direct parameter FleetAPI calls:

```python
async def _execute_step(self, step: TaskStep, skip_reason=None) -> StepResult:
    action = step.action
    params = step.params
    try:
        if action == "speak":
            result = await self.fleet.speak(self.robot_id, params["speak_text"])
            return self._make_result(result, action, {"speak_text": params["speak_text"]})

        elif action == "move_to_pose":
            result = await self.fleet.move_to_pose(
                self.robot_id, float(params["x"]), float(params["y"]), float(params["yaw"])
            )
            return self._make_result(result, action, {"x": params["x"], "y": params["y"], "yaw": params["yaw"]})

        elif action == "move_to_location":
            result = await self.fleet.move_to_location(self.robot_id, params["location_id"])
            return self._make_result(result, action, {"location_id": params["location_id"]})

        elif action == "dock_shelf":
            result = await self.fleet.dock_shelf(self.robot_id)
            return self._make_result(result, action, {})

        elif action == "undock_shelf":
            result = await self.fleet.undock_shelf(self.robot_id)
            return self._make_result(result, action, {})

        elif action == "move_shelf":
            self.target_bed = params["location_id"]
            result = await self.fleet.move_shelf(
                self.robot_id, params["shelf_id"], params["location_id"]
            )

            if result.get("ok") and self._shelf_monitor_task is None:
                self._current_shelf_id = params["shelf_id"]
                self._shelf_monitor_stop = False
                self._shelf_dropped = False
                self._shelf_monitor_task = asyncio.create_task(self._monitor_shelf())

            return self._make_result(result, action, {"shelf_id": params["shelf_id"], "location_id": params["location_id"]})

        elif action == "return_shelf":
            await self._stop_shelf_monitor()
            result = await self.fleet.return_shelf(self.robot_id, params["shelf_id"])
            return self._make_result(result, action, {"shelf_id": params["shelf_id"]})

        elif action == "return_home":
            result = await self.fleet.return_home(self.robot_id)
            return self._make_result(result, action, {})

        elif action == "bio_scan":
            # unchanged — no robot command
            client = get_bio_sensor_client()
            if client is None:
                return StepResult(
                    success=False, error_code=-1,
                    error_message="Bio-sensor MQTT client is not available",
                    data={}, timestamp=get_now().isoformat()
                )
            bed_key = params.get("bed_key")
            scan_result = await client.get_valid_scan_data(
                target_bed=self.target_bed, task_id=self.current_task_id, bed_name=bed_key
            )
            success = scan_result is not None and scan_result.get("data") is not None
            return StepResult(
                success=success,
                error_code=0 if success else -1,
                error_message="Bio scan completed" if success else "No valid data after retries",
                data=scan_result or {},
                timestamp=get_now().isoformat(),
            )

        elif action == "wait":
            seconds = float(params.get("seconds", "1.0"))
            await asyncio.sleep(seconds)
            return StepResult(
                success=True, error_code=0, error_message="",
                data={"seconds": seconds}, timestamp=get_now().isoformat()
            )

        else:
            return StepResult(
                success=False, error_code=-1,
                error_message=f"Unknown action: {action}",
                data={"action": action}, timestamp=get_now().isoformat()
            )

    except Exception as e:
        logger.error(f"[X] Error during {action} for robot {self.robot_id}: {e}", exc_info=True)
        return StepResult(
            success=False, error_code=-1,
            error_message=f"Exception: {e}",
            data={"action": action, "params": params},
            timestamp=get_now().isoformat(),
        )
```

Note: The `except` block is simplified — no more `grpc.aio.AioRpcError` handling since kachaka_core returns dicts, never raises gRPC exceptions to callers.

**Step 8: Update `run_task()` finally block**

Replace Cmd-based cleanup:

```python
# In finally block, replace:
#   cmd = ReturnShelfCmd(); cmd.shelf_id = ...; await self.fleet.return_shelf(self.robot_id, cmd)
#   home_cmd = DefaultCmd(); await self.fleet.return_home(self.robot_id, home_cmd)
# With:
if task.status == TaskStatus.CANCELLED and getattr(self, "_current_shelf_id", None):
    try:
        await self.fleet.return_shelf(self.robot_id, self._current_shelf_id)
        logger.info(f"[{tag}] Cancelled: returned shelf {self._current_shelf_id}")
        await self.fleet.return_home(self.robot_id)
        logger.info(f"[{tag}] Cancelled: robot sent home")
    except Exception as e:
        logger.error(f"[{tag}] Cancelled cleanup error: {e}")
```

**Step 9: Add metrics collection at task completion**

After the step loop completes, before the finally block:

```python
# Collect metrics at task completion (before finally)
try:
    m = self.fleet.get_metrics(self.robot_id)
    if task.metadata is None:
        task.metadata = {}
    task.metadata["metrics"] = {
        "poll_count": m.poll_count,
        "avg_rtt_ms": round(sum(m.poll_rtt_list) / len(m.poll_rtt_list), 1) if m.poll_rtt_list else 0,
        "poll_success_rate": round(m.poll_success_count / m.poll_count, 3) if m.poll_count else 1.0,
    }
    self.fleet.reset_metrics(self.robot_id)
except Exception:
    pass
```

**Step 10: Remove `_build_error_context()` method**

No longer needed — kachaka_core provides enriched error descriptions from firmware.

**Step 11: Verify syntax**

Run: `cd /home/snaken/CodeBase/bio-patrol && uv run python -c "import ast; ast.parse(open('src/backend/services/task_runtime.py').read()); print('OK')"`
Expected: `OK`

**Step 12: Commit**

```bash
git add src/backend/services/task_runtime.py
git commit -m "refactor: rewrite TaskEngine to use kachaka_core via FleetAPI bridge"
```

---

### Task 4: Update routers — response format migration

**Files:**
- Modify: `src/backend/routers/tasks.py`
- Modify: `src/backend/routers/kachaka.py`

**Step 1: Fix tasks.py cancel — use FleetAPI.cancel_command()**

In `routers/tasks.py`, replace lines 74-82:

```python
# Before:
#   client = fleet.manager.get_robot_client(task.robot_id)
#   if client: await client.cancel_command()

# After:
try:
    from dependencies import get_fleet
    fleet = get_fleet()
    await fleet.cancel_command(task.robot_id)
    logger.info(f"Sent cancel_command to robot {task.robot_id} for task {task_id}")
except Exception as e:
    logger.warning(f"Failed to send cancel_command for task {task_id}: {e}")
```

**Step 2: Rewrite kachaka.py — remove protobuf conversions**

kachaka_core returns dicts, so `MessageToDict`/`MessageToJson` are no longer needed for most endpoints. Update each endpoint to return dicts directly.

Key changes:
- Remove `from google.protobuf.json_format import MessageToJson, MessageToDict`
- All command endpoints: replace `res.success` with `res.get("ok")`
- Query endpoints now return dicts — return them directly
- Remove all Cmd dataclass imports and usage — pass parameters directly
- For ROS/advanced endpoints (IMU, odometry, laser, cameras), use `fleet.get_raw_client()` to access the underlying sync SDK

**Step 3: Remove Cmd re-exports from kachaka.py**

Delete the Cmd import block:
```python
# DELETE:
from services.fleet_api import (
    DefaultCmd, SpeakCmd, MoveToPoseCmd, Move2LocationCmd,
    MoveShelfCmd, ReturnShelfCmd, ResetShelfPoseCmd
)
```

Replace the command endpoint request bodies with simple Pydantic models defined locally or accept query parameters.

**Step 4: Verify syntax**

Run: `uv run python -c "import ast; ast.parse(open('src/backend/routers/tasks.py').read()); ast.parse(open('src/backend/routers/kachaka.py').read()); print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add src/backend/routers/tasks.py src/backend/routers/kachaka.py
git commit -m "refactor: update routers for kachaka_core dict responses"
```

---

### Task 5: Update main.py and dependencies.py

**Files:**
- Modify: `src/backend/main.py`
- Modify: `src/backend/dependencies.py`

**Step 1: Update dependencies.py**

Remove `RobotManager` reference (no longer needed):

```python
from services.fleet_api import FleetAPI
from services.bio_sensor_mqtt import BioSensorMQTTClient

fleet_instance: FleetAPI = None

def get_fleet() -> FleetAPI:
    global fleet_instance
    if fleet_instance is None:
        fleet_instance = FleetAPI()
    return fleet_instance

# ... bio_sensor_client unchanged ...
```

**Step 2: Update main.py — remove error code loading**

kachaka_core fetches error descriptions from firmware on-demand, so `load_robot_error_codes` is no longer needed.

Remove lines 115-122 from `lifespan()`:
```python
# DELETE this block:
try:
    from common_types import load_robot_error_codes
    error_codes = await fleet_client.get_error_code(robot_id)
    load_robot_error_codes(error_codes)
    logger.info(f"Loaded {len(error_codes)} error codes from robot '{robot_id}'")
except Exception as ec_err:
    logger.warning(f"Failed to load error codes from robot '{robot_id}': {ec_err}")
```

**Step 3: Update main.py logging config**

Remove `"services.robot_manager"` from log routing (line 56) since the file will be deleted.

**Step 4: Update main.py lifespan — add shutdown cleanup**

Add controller stop on shutdown:

```python
# In the cleanup section after yield:
if bio_sensor_client:
    bio_sensor_client.stop()
await scheduler_service.stop()
# Stop robot controllers
try:
    await fleet_client.unregister_robot(robot_id)
except Exception:
    pass
logger.info("Application shutdown: Clean up completed.")
```

**Step 5: Verify syntax**

Run: `uv run python -c "import ast; ast.parse(open('src/backend/main.py').read()); ast.parse(open('src/backend/dependencies.py').read()); print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add src/backend/main.py src/backend/dependencies.py
git commit -m "refactor: update main.py and dependencies for kachaka_core"
```

---

### Task 6: Clean up — delete robot_manager.py, dead code in common_types.py

**Files:**
- Delete: `src/backend/services/robot_manager.py`
- Modify: `src/backend/common_types.py`

**Step 1: Delete robot_manager.py**

```bash
git rm src/backend/services/robot_manager.py
```

**Step 2: Remove dead error code infrastructure from common_types.py**

Remove:
- `KACHAKA_ERROR_CODES` dict (lines 54-61)
- `_robot_error_codes` dict (lines 65-66)
- `load_robot_error_codes()` function (lines 67-69)
- `get_error_message()` function (lines 71-90)

These are replaced by kachaka_core's `_resolve_error_description()` which queries firmware directly.

**Step 3: Verify no remaining imports of deleted items**

Run: `grep -rn "robot_manager\|get_error_message\|load_robot_error_codes\|KACHAKA_ERROR_CODES\|_robot_error_codes" src/backend/ --include="*.py"`
Expected: no output

**Step 4: Verify app starts**

Run: `cd /home/snaken/CodeBase/bio-patrol && uv run python -c "from services.fleet_api import FleetAPI; from services.task_runtime import TaskEngine; print('imports OK')"`
Expected: `imports OK`

**Step 5: Commit**

```bash
git add -A
git commit -m "cleanup: delete robot_manager.py, remove dead error code infrastructure"
```

---

### Task 7: Smoke test with robot

This task requires a live robot connection.

**Step 1: Start the application**

Run: `cd /home/snaken/CodeBase/bio-patrol && uv run uvicorn main:app --host 0.0.0.0 --port 8000 --app-dir src/backend`

Expected: Application starts, logs show:
- `Registered robot kachaka at <ip> via kachaka_core`
- No import errors

**Step 2: Test robot status endpoint**

Run: `curl -s http://localhost:8000/kachaka/robots | python3 -m json.tool`
Expected: Robot listed with status

**Step 3: Test a simple command**

Run: `curl -s -X POST http://localhost:8000/kachaka/kachaka/command/speak -H 'Content-Type: application/json' -d '{"text": "test"}'`
Expected: Robot speaks, response shows `{"ok": true, ...}`

**Step 4: Run a patrol task**

Submit a simple 2-step patrol via the frontend or API and verify:
- Commands execute with command_id tracking (check logs for `command_id`)
- Shelf monitor starts after move_shelf
- Metrics appear in task metadata after completion

**Step 5: Test cancel**

Start a patrol, then cancel via API. Verify:
- Robot stops
- Shelf returned
- Robot sent home
- Logs show `error_code=10001` (interrupted)

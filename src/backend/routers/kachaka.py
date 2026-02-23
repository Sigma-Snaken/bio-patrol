from fastapi import APIRouter, Response, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel
from services.fleet_api import FleetAPI
from dependencies import get_fleet

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/kachaka', tags=['KACHAKA Robot Fleet'])

# ---------------------------------------------------------------------------
# Request models for command endpoints
# ---------------------------------------------------------------------------

class SpeakRequest(BaseModel):
    text: str

class MoveToLocationRequest(BaseModel):
    location_id: str

class MoveToPoseRequest(BaseModel):
    x: float
    y: float
    yaw: float

class MoveShelfRequest(BaseModel):
    shelf_id: str
    location_id: str

class ReturnShelfRequest(BaseModel):
    shelf_id: str

class ResetShelfPoseRequest(BaseModel):
    shelf_id: str

# ====== Fleet Management APIs ======

@router.get("/robots")
async def get_all_robots(fleet: FleetAPI = Depends(get_fleet)):
    """Get all registered robots"""
    return await fleet.get_all_robots()

@router.post("/robots/register")
async def register_robot(robot_id: str, url: str, name: Optional[str] = None, fleet: FleetAPI = Depends(get_fleet)):
    """Register a new robot instance"""
    result = await fleet.register_robot(robot_id, url, name)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to register robot")
    return {"message": "Robot registered successfully"}

@router.get("/robots/{robot_id}")
async def get_robot_status(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot status"""
    status = await fleet.get_robot_status(robot_id)
    if not status:
        raise HTTPException(status_code=404, detail="Robot not found")
    return status

@router.put("/robots/{robot_id}/status")
async def update_robot_status(robot_id: str, status: str, fleet: FleetAPI = Depends(get_fleet)):
    """Update robot status"""
    result = await fleet.update_robot_status(robot_id, status)
    if not result:
        raise HTTPException(status_code=404, detail="Robot not found")
    return {"message": "Robot status updated successfully"}

@router.delete("/robots/{robot_id}")
async def unregister_robot(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Unregister an existing robot instance"""
    result = await fleet.unregister_robot(robot_id)
    if not result:
        raise HTTPException(status_code=404, detail="Robot not found")
    return {"message": "Robot unregistered successfully"}

# ====== Robot Info APIs ======

@router.get("/{robot_id}/serial_number")
async def serial_number(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot serial number"""
    try:
        return await fleet.get_serial_number(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/version")
async def version(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot version"""
    try:
        client = fleet.get_raw_client(robot_id)
        res = await asyncio.to_thread(client.get_robot_version)
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/pose")
async def robot_pose(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot pose"""
    try:
        return await fleet.get_pose(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/battery")
async def battery(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot battery info"""
    try:
        return await fleet.get_battery_info(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/error/json")
async def error_code_in_json(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot error code in JSON format"""
    try:
        client = fleet.get_raw_client(robot_id)
        res = await asyncio.to_thread(client.get_robot_error_code)
        return Response(content=json.dumps(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/error")
async def error(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot error info"""
    try:
        return await fleet.get_errors(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/map")
async def png_map(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot map"""
    try:
        return await fleet.get_map(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/map_list")
async def map_list(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot map list"""
    try:
        return await fleet.get_map_list(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/export_map")
async def export_map(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Export robot map"""
    try:
        from google.protobuf.json_format import MessageToJson
        client = fleet.get_raw_client(robot_id)
        res = await asyncio.to_thread(client.export_map)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/import_map")
async def import_map(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Import robot map"""
    try:
        from google.protobuf.json_format import MessageToJson
        client = fleet.get_raw_client(robot_id)
        res = await asyncio.to_thread(client.import_map)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ====== ROS-level endpoints (raw SDK client) ======

@router.get("/{robot_id}/imu")
async def ros_imu_info(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot IMU info"""
    try:
        from google.protobuf.json_format import MessageToJson
        client = fleet.get_raw_client(robot_id)
        res = await asyncio.to_thread(client.get_ros_imu)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/odometry")
async def ros_odometry(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot odometry info"""
    try:
        from google.protobuf.json_format import MessageToJson
        client = fleet.get_raw_client(robot_id)
        res = await asyncio.to_thread(client.get_ros_odometry)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/wheel/odometry")
async def ros_wheel_odometry(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot wheel odometry info"""
    try:
        from google.protobuf.json_format import MessageToJson
        client = fleet.get_raw_client(robot_id)
        res = await asyncio.to_thread(client.get_ros_wheel_odometry)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/laser/scan")
async def ros_laser_scan(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot laser scan info"""
    try:
        from google.protobuf.json_format import MessageToJson
        client = fleet.get_raw_client(robot_id)
        res = await asyncio.to_thread(client.get_ros_laser_scan)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ====== Query APIs (kachaka_core — returns dicts) ======

@router.get("/{robot_id}/locations")
async def locations(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot locations"""
    try:
        return await fleet.get_locations(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/shelves")
async def shelves(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot shelves"""
    try:
        return await fleet.get_shelves(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/shelves/moving")
async def moving_shelf(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get moving shelf ID"""
    try:
        return await fleet.get_moving_shelf(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ====== Robot Command APIs ======

@router.post("/{robot_id}/command/speak")
async def speak(robot_id: str, req: SpeakRequest, fleet: FleetAPI = Depends(get_fleet)):
    """Send speak command to robot"""
    try:
        return await fleet.speak(robot_id, req.text)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{robot_id}/command/move_to_location")
async def move_to_location(robot_id: str, req: MoveToLocationRequest, fleet: FleetAPI = Depends(get_fleet)):
    """Move robot to specified location"""
    try:
        return await fleet.move_to_location(robot_id, req.location_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{robot_id}/command/move_to_pose")
async def move_to_pose(robot_id: str, req: MoveToPoseRequest, fleet: FleetAPI = Depends(get_fleet)):
    """Move robot to specified pose"""
    try:
        return await fleet.move_to_pose(robot_id, req.x, req.y, req.yaw)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{robot_id}/command/dock_shelf")
async def dock_shelf(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Dock robot to shelf"""
    try:
        return await fleet.dock_shelf(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{robot_id}/command/undock_shelf")
async def undock_shelf(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Undock robot from shelf"""
    try:
        return await fleet.undock_shelf(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{robot_id}/command/move_shelf")
async def move_shelf(robot_id: str, req: MoveShelfRequest, fleet: FleetAPI = Depends(get_fleet)):
    """Move shelf to specified location"""
    try:
        return await fleet.move_shelf(robot_id, req.shelf_id, req.location_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{robot_id}/command/return_shelf")
async def return_shelf(robot_id: str, req: ReturnShelfRequest, fleet: FleetAPI = Depends(get_fleet)):
    """Return shelf to its original position"""
    try:
        return await fleet.return_shelf(robot_id, req.shelf_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{robot_id}/command/reset_shelf_pose")
async def reset_shelf_pose(robot_id: str, req: ResetShelfPoseRequest, fleet: FleetAPI = Depends(get_fleet)):
    """Reset shelf pose"""
    try:
        client = fleet.get_raw_client(robot_id)
        res = await asyncio.to_thread(client.reset_shelf_pose, req.shelf_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{robot_id}/command/return_home")
async def return_home(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Return robot to home position"""
    try:
        return await fleet.return_home(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ====== Command State APIs ======

@router.get("/{robot_id}/command/state")
async def command_state(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get command state"""
    try:
        return await fleet.get_command_state(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/command/last")
async def last_command_result(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get last command result"""
    try:
        return await fleet.get_last_command_result(robot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

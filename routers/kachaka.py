from fastapi import APIRouter, Response, HTTPException, Depends
from typing import Optional
from services.fleet_api import FleetAPI
from dependencies import get_fleet

router = APIRouter(prefix='/kachaka', tags=['KACHAKA Robot Fleet'])

import logging
logger = logging.getLogger(__name__)

# ====== APIs ======
from google.protobuf.json_format import MessageToJson, MessageToDict
import json

# Fleet Management APIs
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

# Get Robot Info APIs
@router.get("/{robot_id}/serial_number")
async def serial_number(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot serial number"""
    try:
        res = await fleet.get_serial_number(robot_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/version")
async def version(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot version"""
    try:
        res = await fleet.get_version(robot_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/pose")
async def robot_pose(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot pose"""
    try:
        res = await fleet.get_pose(robot_id)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/battery")
async def battery(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot battery info"""
    try:
        res = await fleet.get_battery_info(robot_id)
        res = json.dumps({ "remaining_percentage": res[0], "power_supply_status": res[1] })
        return Response(content=res, media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/error/json")
async def error_code_in_json(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot error code in JSON format"""
    try:
        res = await fleet.get_error_code(robot_id)
        return Response(content=json.dumps(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/error")
async def error(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot error info"""
    try:
        res = await fleet.get_error(robot_id)
        errs = [MessageToDict(p) for p in res]
        return Response(content=json.dumps(errs), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/map")
async def png_map(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot map"""
    try:
        res = await fleet.get_png_map(robot_id)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/export_map")
async def export_map(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """export robot map"""
    try:
        res = await fleet.export_map(robot_id)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/import_map")
async def import_map(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """import robot map"""
    try:
        res = await fleet.import_map(robot_id)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/imu")
async def ros_imu_info(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot IMU info"""
    try:
        res = await fleet.get_ros_imu(robot_id)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/odometry")
async def ros_odometry(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot odometry info"""
    try:
        res = await fleet.get_ros_odometry(robot_id)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/wheel/odometry")
async def ros_wheel_odometry(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot wheel odometry info"""
    try:
        res = await fleet.get_ros_wheel_odometry(robot_id)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/laser/scan")
async def ros_laser_scan(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot laser scan info"""
    try:
        res = await fleet.get_ros_laser_scan(robot_id)
        return Response(content=MessageToJson(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/locations")
async def locations(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot locations"""
    try:
        res = await fleet.get_locations(robot_id)
        locations = [MessageToDict(p) for p in res]
        return Response(content=json.dumps(locations), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/shelves")
async def shelves(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get robot shelves"""
    try:
        res = await fleet.get_shelves(robot_id)
        shelves = [MessageToDict(p) for p in res]
        return Response(content=json.dumps(shelves), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{robot_id}/shelves/moving")
async def moving_shelf(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get moving shelf ID"""
    try:
        res = await fleet.get_moving_shelf_id(robot_id)
        return Response(content=json.dumps(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# --- Robot Control APIs ---
from services.fleet_api import (
    DefaultCmd, SpeakCmd, MoveToPoseCmd, Move2LocationCmd,
    MoveShelfCmd, ReturnShelfCmd, ResetShelfPoseCmd
)

# Speak
@router.post("/{robot_id}/command/speak")
async def speak(robot_id: str, cmd: SpeakCmd, fleet: FleetAPI = Depends(get_fleet)):
    """Send speak command to robot"""
    try:
        res = await fleet.speak(robot_id, cmd)
        return Response(content=json.dumps({"success": res.success}), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Move to location
@router.post("/{robot_id}/command/move_to_location")
async def move_to_location(robot_id: str, cmd: Move2LocationCmd, fleet: FleetAPI = Depends(get_fleet)):
    """Move robot to specified location"""
    try:
        res = await fleet.move_to_location(robot_id, cmd)
        return Response(content=json.dumps({"success": res.success}), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Move to pose
@router.post("/{robot_id}/command/move_to_pose")
async def move_to_pose(robot_id: str, cmd: MoveToPoseCmd, fleet: FleetAPI = Depends(get_fleet)):
    """Move robot to specified pose"""
    try:
        res = await fleet.move_to_pose(robot_id, cmd)
        return Response(content=json.dumps({"success": res.success}), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Dock Shelf
@router.post("/{robot_id}/command/dock_shelf")
async def dock_shelf(robot_id: str, cmd: DefaultCmd, fleet: FleetAPI = Depends(get_fleet)):
    """Dock robot to shelf"""
    try:
        res = await fleet.dock_shelf(robot_id, cmd)
        return Response(content=json.dumps({"success": res.success}), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Undock Shelf
@router.post("/{robot_id}/command/undock_shelf")
async def undock_shelf(robot_id: str, cmd: DefaultCmd, fleet: FleetAPI = Depends(get_fleet)):
    """Undock robot from shelf"""
    try:
        res = await fleet.undock_shelf(robot_id, cmd)
        return Response(content=json.dumps({"success": res.success}), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Move Shelf
@router.post("/{robot_id}/command/move_shelf")
async def move_shelf(robot_id: str, cmd: MoveShelfCmd, fleet: FleetAPI = Depends(get_fleet)):
    """Move shelf to specified location"""
    try:
        res = await fleet.move_shelf(robot_id, cmd)
        return Response(content=json.dumps({"success": res.success}), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Return Shelf
@router.post("/{robot_id}/command/return_shelf")
async def return_shelf(robot_id: str, cmd: ReturnShelfCmd, fleet: FleetAPI = Depends(get_fleet)):
    """Return shelf to its original position"""
    try:
        res = await fleet.return_shelf(robot_id, cmd)
        return Response(content=json.dumps({"success": res.success}), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Reset Shelf Pose
@router.post("/{robot_id}/command/reset_shelf_pose")
async def reset_shelf_pose(robot_id: str, cmd: ResetShelfPoseCmd, fleet: FleetAPI = Depends(get_fleet)):
    """Reset shelf pose"""
    try:
        res = await fleet.reset_shelf_pose(robot_id, cmd)
        return Response(content=json.dumps({"success": res.success}), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Return Home
@router.post("/{robot_id}/command/return_home")
async def return_home(robot_id: str, cmd: DefaultCmd, fleet: FleetAPI = Depends(get_fleet)):
    """Return robot to home position"""
    try:
        res = await fleet.return_home(robot_id, cmd)
        return Response(content=json.dumps({"success": res.success}), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Command state
@router.get("/{robot_id}/command/state")
async def command_state(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get command state"""
    try:
        state, command =  await fleet.get_command_state(robot_id)
        res = {"state": state, "command": MessageToDict(command)}
        return Response(content=json.dumps(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Last command result
@router.get("/{robot_id}/command/last")
async def last_command_result(robot_id: str, fleet: FleetAPI = Depends(get_fleet)):
    """Get last command result"""
    try:
        result, command =  await fleet.get_last_command_result(robot_id)
        res = {"result": MessageToDict(result), "command": MessageToDict(command)}
        return Response(content=json.dumps(res), media_type='application/json')
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

from services.robot_manager import RobotManager
from typing import Optional, Dict
from pydantic import BaseModel
import time
import logging
import os
import asyncio
import grpc.aio
from settings.config import get_runtime_settings

logger = logging.getLogger(__name__)

class DefaultCmd(BaseModel):
    cancel_all: Optional[bool] = True
    tts_on_success: Optional[str] = ""
    title: Optional[str] = ""

class MoveShelfCmd(DefaultCmd):
    shelf_id: str = "S01"
    location_id: str = "L01"

class ReturnShelfCmd(DefaultCmd):
    shelf_id: str = "S01"

class ResetShelfPoseCmd(DefaultCmd):
    shelf_id: str = "S01"

class Move2LocationCmd(DefaultCmd):
    location_id: str = "L01"

class MoveToPoseCmd(DefaultCmd):
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0

class SpeakCmd(DefaultCmd):
    speak_text: str = ""

class FleetAPI:
    def __init__(self):
        self.manager = RobotManager()


    async def register_robot(self, robot_id: str, url: str, name: str = "") -> bool:
        """Register a new robot instance"""
        return await self.manager.register_robot(robot_id, url, name)

    async def unregister_robot(self, robot_id: str) -> bool:
        """Unregister an existing robot instance"""
        return self.manager.unregister_robot(robot_id)

    async def get_robot_status(self, robot_id: str) -> Optional[Dict]:
        """Get robot status"""
        config = self.manager.get_robot_config(robot_id)
        if not config:
            return None
        
        return {
            "id": config.id,
            "url": config.url,
            "name": config.name,
            "status": config.status,
            "last_seen": config.last_seen
        }

    async def get_all_robots(self) -> Dict[str, Dict]:
        """Get all registered robots"""
        robots = self.manager.get_all_robots()
        print("get all robots")
        print(robots)
        return {
            robot_id: {
                "id": config.id,
                "url": config.url,
                "name": config.name,
                "status": config.status,
                "last_seen": config.last_seen
            }
            for robot_id, config in robots.items()
        }

    async def wait(self, robot_id: str, seconds: str) -> bool:
        """Wait for specified seconds"""
        print(f"[FleetAPI] Robot {robot_id} waiting for {seconds} seconds")
        time.sleep(float(seconds))
        return True

    async def get_serial_number(self, robot_id: str):
        """Get robot serial number"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_robot_serial_number()
        return res

    async def update_robot_status(self, robot_id: str, status: str) -> bool:
        """Update robot status"""
        return self.manager.update_robot_status(robot_id, status) 

    async def check_robot_readiness(self, robot_id: str, timeout: float = None) -> bool:
        """Check if robot is ready to accept commands with timeout"""
        if timeout is None:
            cfg = get_runtime_settings()
            timeout = cfg.get("robot_readiness_check_timeout", 8.0)
            
        client = self.manager.get_robot_client(robot_id)
        if not client:
            logger.error(f"Robot {robot_id} client not found")
            return False
        
        config = self.manager.get_robot_config(robot_id)
        if not config:
            logger.error(f"Robot {robot_id} config not found")
            return False
        
        # Check if robot status is online
        if config.status != "online":
            logger.warning(f"Robot {robot_id} status is {config.status}, not online")
            return False
        
        # Test robot connectivity with a simple command (get pose)
        try:
            await asyncio.wait_for(client.get_robot_pose(), timeout=timeout)
            logger.debug(f"Robot {robot_id} readiness check passed")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Robot {robot_id} readiness check timed out after {timeout}s")
            config.status = "timeout"
            return False
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                logger.warning(f"Robot {robot_id} is not ready (UNAVAILABLE)")
                config.status = "offline"
                return False
            else:
                logger.error(f"Robot {robot_id} readiness check failed with gRPC error: {e.code()} - {e.details()}")
                return False
        except Exception as e:
            logger.error(f"Robot {robot_id} readiness check failed: {str(e)}")
            return False

    async def wait_for_robot_ready(self, robot_id: str, max_wait: float = None, check_interval: float = None) -> bool:
        """Wait for robot to become ready with polling"""
        if max_wait is None or check_interval is None:
            cfg = get_runtime_settings()
            if max_wait is None:
                max_wait = cfg.get("robot_wait_for_ready_timeout", 15.0)
            if check_interval is None:
                check_interval = cfg.get("robot_readiness_check_interval", 2.0)
            
        start_time = time.time()
        while time.time() - start_time < max_wait:
            if await self.check_robot_readiness(robot_id, timeout=5.0):
                return True
            logger.info(f"Robot {robot_id} not ready, waiting {check_interval}s before retry...")
            await asyncio.sleep(check_interval)
        
        logger.error(f"Robot {robot_id} did not become ready within {max_wait}s")
        return False

    async def get_version(self, robot_id: str):
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")

        res = await client.get_robot_version()
        return res

    async def get_pose(self, robot_id: str):
        """Get robot pose"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_robot_pose()
        return res

    async def get_battery_info(self, robot_id: str):
        """Get robot battery info"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_battery_info()
        return res

    async def get_error_code(self, robot_id: str):
        """Get robot error code"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_robot_error_code()
        return res

    async def get_error(self, robot_id: str):
        """Get robot error info"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_error()
        return res

    async def get_png_map(self, robot_id: str):
        """Get robot map"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_png_map()
        return res

    async def export_map(self, robot_id: str):
        """Export robot map""" 
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        current_map_id = await client.get_current_map_id()
        output_file_path = os.path.join(os.getcwd(), f"{robot_id}_map_export.kmap")
        res = await client.export_map(current_map_id, output_file_path)
        return res

    async def import_map(self, robot_id: str):
        """Import robot map""" 
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        import_file_path = os.path.join(os.getcwd(), f"normal_map_export.kmap")
        print("------ import file path: -----")
        print(import_file_path)
        res = await client.import_map(import_file_path)
        return res

    async def get_ros_imu(self, robot_id: str):
        """Get robot IMU info"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_ros_imu()
        return res

    async def get_ros_odometry(self, robot_id: str):
        """Get robot odometry info"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_ros_odometry()
        return res

    async def get_ros_wheel_odometry(self, robot_id: str):
        """Get robot wheel odometry info"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_ros_wheel_odometry()
        return res

    async def get_ros_laser_scan(self, robot_id: str):
        """Get robot laser scan info"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_ros_laser_scan()
        return res

    async def get_front_camera_ros_info(self, robot_id: str):
        """Get front camera info"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_front_camera_ros_info()
        return res

    async def get_front_camera_ros_image(self, robot_id: str):
        """Get front camera image"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_front_camera_ros_image()
        return res

    async def get_front_camera_ros_compressed(self, robot_id: str):
        """Get front camera compressed image"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_front_camera_ros_compressed()
        return res

    async def get_back_camera_ros_info(self, robot_id: str):
        """Get back camera info"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_back_camera_ros_info()
        return res

    async def get_back_camera_ros_image(self, robot_id: str):
        """Get back camera image"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_back_camera_ros_image()
        return res

    async def get_back_camera_ros_compressed(self, robot_id: str):
        """Get back camera compressed image"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_back_camera_ros_compressed()
        return res

    async def get_tof_camera_ros_info(self, robot_id: str):
        """Get TOF camera info"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_tof_camera_ros_info()
        return res

    async def get_tof_camera_ros_image(self, robot_id: str):
        """Get TOF camera image"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_tof_camera_ros_image()
        return res

    async def get_tof_camera_ros_compressed(self, robot_id: str):
        """Get TOF camera compressed image"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_tof_camera_ros_compressed()
        return res

    async def get_locations(self, robot_id: str):
        """Get robot locations"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_locations()
        return res
        
    async def get_shelves(self, robot_id: str):
        """Get robot shelves"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_shelves()
        return res

    async def get_moving_shelves_id(self, robot_id: str):
        """Get moving shelf ID"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_moving_shelf_id()
        return res

    async def get_command_state(self, robot_id: str):
        """Get command state"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_command_state()
        return res

    async def get_last_command_result(self, robot_id: str):
        """Get last command result"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.get_last_command_result()
        return res

    async def speak(self, robot_id: str, cmd: SpeakCmd):
        """Speak command"""
        client = self.manager.get_robot_client(robot_id)
        print(client)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.speak(                        
                        cmd.speak_text,
                        cancel_all=cmd.cancel_all,
                        tts_on_success=cmd.tts_on_success,
                        title=cmd.title,
                    )
        return res

    async def move_to_pose(self, robot_id: str, cmd: MoveToPoseCmd):
        """Move to pose command"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.move_to_pose(                        
                        cmd.x,
                        cmd.y,
                        cmd.yaw,
                        cancel_all=cmd.cancel_all,
                        tts_on_success=cmd.tts_on_success,
                        title=cmd.title,
                    )
        return res

    async def move_to_location(self, robot_id: str, cmd: Move2LocationCmd):
        """Move to location command"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.move_to_location(                        
                        cmd.location_id,
                        cancel_all=cmd.cancel_all,
                        tts_on_success=cmd.tts_on_success,
                        title=cmd.title,
                    )
        return res

    async def dock_shelf(self, robot_id: str, cmd: DefaultCmd):
        """Dock shelf command"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.dock_shelf(                        
                        cancel_all=cmd.cancel_all,
                        tts_on_success=cmd.tts_on_success,
                        title=cmd.title,
                    )
        return res

    async def undock_shelf(self, robot_id: str, cmd: DefaultCmd):
        """Undock shelf command"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.undock_shelf(                        
                        cancel_all=cmd.cancel_all,
                        tts_on_success=cmd.tts_on_success,
                        title=cmd.title,
                    )
        return res

    async def move_shelf(self, robot_id: str, cmd: MoveShelfCmd):
        """Move shelf command"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        # Ensure resolver is initialized before shelf operations
        resolver_ready = await self.manager.ensure_robot_resolver(robot_id)
        if not resolver_ready:
            raise ValueError(f"Robot {robot_id} resolver not available - cannot resolve shelf/location IDs")
        
        # Check robot readiness before attempting shelf operations
        if not await self.check_robot_readiness(robot_id):
            # Try to wait for robot to become ready
            logger.info(f"Robot {robot_id} not ready for move_shelf, waiting...")
            if not await self.wait_for_robot_ready(robot_id):
                raise ValueError(f"Robot {robot_id} is not ready to accept move_shelf commands")
        
        res = await client.move_shelf(                        
                        cmd.shelf_id,
                        cmd.location_id,
                        cancel_all=cmd.cancel_all,
                        tts_on_success=cmd.tts_on_success,
                        title=cmd.title,
                    )
        return res

    async def return_shelf(self, robot_id: str, cmd: ReturnShelfCmd):
        """Return shelf command"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        # Ensure resolver is initialized before shelf operations
        resolver_ready = await self.manager.ensure_robot_resolver(robot_id)
        if not resolver_ready:
            raise ValueError(f"Robot {robot_id} resolver not available - cannot resolve shelf IDs")
        
        # Check robot readiness before attempting shelf operations
        if not await self.check_robot_readiness(robot_id):
            # Try to wait for robot to become ready
            logger.info(f"Robot {robot_id} not ready for return_shelf, waiting...")
            if not await self.wait_for_robot_ready(robot_id):
                raise ValueError(f"Robot {robot_id} is not ready to accept return_shelf commands")
        
        res = await client.return_shelf(                        
                        cmd.shelf_id,
                        cancel_all=cmd.cancel_all,
                        tts_on_success=cmd.tts_on_success,
                        title=cmd.title,
                    )
        return res

    async def reset_shelf_pose(self, robot_id: str, cmd: ResetShelfPoseCmd):
        """Reset shelf pose command"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        # Ensure resolver is initialized before shelf operations
        resolver_ready = await self.manager.ensure_robot_resolver(robot_id)
        if not resolver_ready:
            raise ValueError(f"Robot {robot_id} resolver not available - cannot resolve shelf IDs")
        
        res = await client.reset_shelf_pose(                        
                        shelf_id=cmd.shelf_id,
                    )
        return res

    async def return_home(self, robot_id: str, cmd: DefaultCmd):
        """Return home command"""
        client = self.manager.get_robot_client(robot_id)
        if not client:
            raise ValueError(f"Robot {robot_id} not found")
        
        res = await client.return_home(                        
                        cancel_all=cmd.cancel_all,
                        tts_on_success=cmd.tts_on_success,
                        title=cmd.title,
                    )
        return res


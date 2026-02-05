from typing import Dict, Optional
from dataclasses import dataclass
from kachaka_api import aio
import logging
import time
import asyncio

logger = logging.getLogger(__name__)

@dataclass
class RobotConfig:
    id: str
    url: str
    name: str = ""
    status: str = "offline"
    last_seen: float = 0.0


class RobotManager:
    def __init__(self):
        self._robots: Dict[str, RobotConfig] = {}
        self._clients: Dict[str, aio.KachakaApiClient] = {}

    async def register_robot(self, robot_id: str, url: str, name: str = "") -> bool:
        """Register a new robot instance with lazy initialization"""
        if robot_id in self._robots:
            logger.warning(f"Robot {robot_id} already registered")
            return False

        self._robots[robot_id] = RobotConfig(
            id=robot_id,
            url=url,
            name=name
        )
        
        # Create client but don't initialize resolver yet (lazy initialization)
        client = aio.KachakaApiClient(url)
        self._clients[robot_id] = client
        
        # Initialize resolver in background without blocking startup
        import asyncio
        asyncio.create_task(self._initialize_resolver_async(robot_id, client))
        
        logger.info(f"Registered robot {robot_id} at {url} (resolver will be initialized asynchronously)")
        return True
    
    def _patch_resolver(self, client: aio.KachakaApiClient):
        """Patch resolver to also match by ID and use logger instead of print()"""
        resolver = client.resolver

        def get_shelf_id_by_name(shelf_name_or_id: str) -> str:
            for shelf in resolver.shelves:
                if shelf.name == shelf_name_or_id:
                    return shelf.id
            for shelf in resolver.shelves:
                if shelf.id == shelf_name_or_id:
                    return shelf.id
            logger.warning(f"Shelf not found by name or ID: {shelf_name_or_id}")
            return shelf_name_or_id

        def get_location_id_by_name(location_name_or_id: str) -> str:
            for location in resolver.locations:
                if location.name == location_name_or_id:
                    return location.id
            for location in resolver.locations:
                if location.id == location_name_or_id:
                    return location.id
            logger.warning(f"Location not found by name or ID: {location_name_or_id}")
            return location_name_or_id

        resolver.get_shelf_id_by_name = get_shelf_id_by_name
        resolver.get_location_id_by_name = get_location_id_by_name

    async def _initialize_resolver_async(self, robot_id: str, client: aio.KachakaApiClient):
        """Initialize robot resolver asynchronously without blocking startup"""
        try:
            # Add timeout to prevent hanging
            await asyncio.wait_for(client.update_resolver(), timeout=10.0)
            self._patch_resolver(client)
            logger.info(f"Robot {robot_id} resolver initialized successfully")
            
            # Update robot status to online
            if robot_id in self._robots:
                self._robots[robot_id].status = "online"
                
        except asyncio.TimeoutError:
            logger.warning(f"Robot {robot_id} resolver initialization timed out - will retry on first use")
            if robot_id in self._robots:
                self._robots[robot_id].status = "timeout"
        except Exception as e:
            logger.error(f"Failed to initialize resolver for robot {robot_id}: {e}")
            if robot_id in self._robots:
                self._robots[robot_id].status = "offline"

    def unregister_robot(self, robot_id: str) -> bool:
        """Unregister an existing robot instance"""
        if robot_id not in self._robots:
            logger.warning(f"Robot {robot_id} not found")
            return False

        del self._robots[robot_id]
        del self._clients[robot_id]
        logger.info(f"Unregistered robot {robot_id}")
        return True

    def get_robot_client(self, robot_id: str) -> Optional[aio.KachakaApiClient]:
        """Get Kachaka API client for a specific robot"""
        return self._clients.get(robot_id)
    
    async def ensure_robot_resolver(self, robot_id: str) -> bool:
        """Ensure robot resolver is initialized before use"""
        client = self._clients.get(robot_id)
        if not client:
            return False
            
        config = self._robots.get(robot_id)
        if not config:
            return False
            
        # If robot is already online, resolver should be ready
        if config.status == "online":
            return True
            
        # Try to initialize resolver if not done yet
        if config.status in ["offline", "timeout", ""]:
            try:
                await asyncio.wait_for(client.update_resolver(), timeout=5.0)
                self._patch_resolver(client)
                config.status = "online"
                logger.info(f"Robot {robot_id} resolver initialized on-demand")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize resolver for robot {robot_id}: {e}")
                config.status = "offline"
                return False
                
        return config.status == "online"

    def get_robot_config(self, robot_id: str) -> Optional[RobotConfig]:
        """Get robot configuration"""
        return self._robots.get(robot_id)

    def get_all_robots(self) -> Dict[str, RobotConfig]:
        """Get all registered robots"""
        return self._robots.copy()

    def update_robot_status(self, robot_id: str, status: str) -> bool:
        """Update robot status"""
        if robot_id not in self._robots:
            logger.warning(f"Robot {robot_id} not found")
            return False

        self._robots[robot_id].status = status
        self._robots[robot_id].last_seen = time.time()
        logger.info(f"Updated robot {robot_id} status to {status}")
        return True

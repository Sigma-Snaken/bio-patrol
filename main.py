from fastapi import FastAPI
from fastapi.responses import RedirectResponse
import routers.kachaka as kachaka
import routers.tasks as tasks
import routers.settings as settings_router
import routers.bio_sensor as bio_sensor
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio
import logging
import os
import sys
import traceback

from services.task_runtime import (
    engines, task_queues, available_robots_queue, dispatcher, task_worker, TaskEngine
)
from services.scheduler import scheduler_service
from dependencies import get_fleet, get_bio_sensor_client

# Configure logging for executable - use AppData to avoid startup folder issues
def get_log_file_path():
    """Get log file path in AppData to avoid startup folder permission issues."""
    if getattr(sys, 'frozen', False):
        appdata = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        log_dir = os.path.join(appdata, 'BioPatrol', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, 'kachaka_debug.log')
    else:
        return 'kachaka_debug.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(get_log_file_path(), mode='w')
    ]
)
logger = logging.getLogger("kachaka.main")

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application lifespan...")
    bio_sensor_client = None
    try:
        # Bio-sensor MQTT client
        from settings.config import get_runtime_settings
        cfg = get_runtime_settings()

        if cfg.get("mqtt_enabled"):
            try:
                bio_sensor_client = get_bio_sensor_client()
                bio_sensor_client.start()
                logger.info("Bio-sensor MQTT client started successfully")
            except Exception as e:
                logger.error(f"Failed to start bio-sensor MQTT client: {e}")
        else:
            logger.info("Bio-sensor MQTT client disabled (mqtt_enabled=false)")

        # Single robot registration from runtime settings
        robot_ip = cfg.get("robot_ip", "192.168.204.37:26400")
        robot_id = "kachaka"

        fleet_client = get_fleet()
        try:
            await fleet_client.register_robot(robot_id, robot_ip, "Kachaka Care")
            engines[robot_id] = TaskEngine(fleet_client, robot_id)
            task_queues[robot_id] = asyncio.Queue()
            asyncio.create_task(task_worker(robot_id))
            logger.info(f"Robot '{robot_id}' registered at {robot_ip}")
            await available_robots_queue.put(robot_id)
        except Exception as e:
            logger.error(f"Failed to register robot '{robot_id}': {e}")
            logger.info(f"Continuing with graceful degradation for robot {robot_id}")

        logger.info("Application startup: Initializing dispatcher.")
        asyncio.create_task(dispatcher())

        # Start task scheduler
        logger.info("Starting task scheduler...")
        await scheduler_service.start()

        yield

        # Cleanup
        if bio_sensor_client:
            bio_sensor_client.stop()
        await scheduler_service.stop()
        logger.info("Application shutdown: Clean up completed.")
    except Exception as e:
        logger.error(f"Error during application startup: {e}")
        logger.error(traceback.format_exc())
        raise

app = FastAPI(
    title="Bio Patrol",
    description="Kachaka robot bio-sensor patrol system",
    version="1.0.0",
    lifespan=lifespan
)

public_path = get_resource_path("public")
if os.path.exists(public_path):
    app.mount("/ui", StaticFiles(directory=public_path, html=True), name="ui")
else:
    logger.warning(f"Public directory not found at {public_path}, UI will not be available")

@app.get("/", tags=["Entry"])
async def root():
    return RedirectResponse(url="/ui/")

# Include routers
app.include_router(tasks.router)
app.include_router(kachaka.router)
app.include_router(settings_router.router)
app.include_router(bio_sensor.router)

if __name__ == "__main__":
    try:
        logger.info("Starting Bio Patrol...")
        logger.info(f"Python executable: {sys.executable}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"PyInstaller frozen: {getattr(sys, 'frozen', False)}")

        import uvicorn
        from settings.config import get_runtime_settings, get_port

        port = get_port()
        logger.info(f"Starting server on port {port}")

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info"
        )
    except ImportError as e:
        logger.error(f"Import error: {e}")
        logger.error("Missing required module - check PyInstaller hidden imports")
        logger.error(traceback.format_exc())
        input("Press Enter to exit...")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error starting application: {e}")
        logger.error(traceback.format_exc())
        input("Press Enter to exit...")
        sys.exit(1)

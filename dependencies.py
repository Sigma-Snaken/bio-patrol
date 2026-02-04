from services.fleet_api import FleetAPI
from services.bio_sensor_mqtt import BioSensorMQTTClient

# Global fleet instance
fleet_instance: FleetAPI = None

def get_fleet() -> FleetAPI:
    """Dependency function to get the fleet instance"""
    global fleet_instance
    if fleet_instance is None:
        fleet_instance = FleetAPI()
    return fleet_instance

# Global bio-sensor client
bio_sensor_client: BioSensorMQTTClient = None

def get_bio_sensor_client() -> BioSensorMQTTClient:
    """Get the global MQTT client instance. Returns None if mqtt_enabled is false."""
    global bio_sensor_client
    if bio_sensor_client is None:
        from settings.config import get_runtime_settings
        cfg = get_runtime_settings()
        if not cfg.get("mqtt_enabled"):
            return None
        bio_sensor_client = BioSensorMQTTClient(
            broker=cfg.get("mqtt_broker", "localhost"),
            port=cfg.get("mqtt_port", 1883),
            topic=cfg.get("mqtt_topic", "/data-test/demo/wisleep-eck/org/201906078")
        )
    return bio_sensor_client

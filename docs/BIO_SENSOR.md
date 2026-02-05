# Bio-Sensor MQTT Integration

MQTT-based physiological sensor (WiSleep) integration for Bio Patrol.

## How It Works

1. The bio-sensor publishes vital signs (heart rate, respiration) to an MQTT topic
2. `BioSensorMQTTClient` subscribes and stores the latest reading in memory
3. During patrol, `get_valid_scan_data()` waits for a valid reading (status=4, bpm>0, rpm>0)
4. Each scan attempt is persisted to SQLite (`data/sensor_data.db`) for history

## Configuration

Edit `data/config/settings.json`:

```json
{
  "mqtt_enabled": true,
  "mqtt_broker": "localhost",
  "mqtt_port": 1883,
  "mqtt_topic": "/data-test/demo/wisleep-eck/org/201906078"
}
```

With Docker Compose, set `mqtt_broker` to `"mqtt-broker"` (the container name).

### Scan Parameters

| Setting | Default | Description |
|---------|---------|-------------|
| `bio_scan_initial_wait` | 120 | Seconds to wait before first read |
| `bio_scan_wait_time` | 10 | Seconds between retries |
| `bio_scan_retry_count` | 19 | Max retry attempts |
| `bio_scan_valid_status` | 4 | Status code for valid reading |

## Database Schema

Scan records are stored in SQLite (`data/sensor_data.db`), table `sensor_scan_data`:

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key (auto-increment) |
| `location_id` | TEXT | Robot target location ID |
| `bed_name` | TEXT | Bed name (e.g. 101-1) |
| `bpm` | REAL | Heart rate |
| `rpm` | REAL | Respiration rate |
| `status` | INTEGER | Sensor status code (4 = valid) |
| `is_valid` | INTEGER | Whether the reading is valid (1/0) |
| `retry_count` | INTEGER | Number of retries before this reading |
| `details` | TEXT | Additional info (e.g. skip reason) |
| `scanned_at` | TEXT | ISO timestamp |

## Testing with Mosquitto

```bash
# Start broker
docker compose up mqtt-broker

# Publish test data
mosquitto_pub -h localhost -p 1883 \
  -t "/data-test/demo/wisleep-eck/org/201906078" \
  -m '{"records":[{"status":4,"bpm":72,"rpm":16}]}'
```

Verify:

```bash
curl http://localhost:8000/api/bio-sensor/latest
```

## Sample Data

```json
{
  "status": "success",
  "data": {
    "records": [
      {
        "status": 4,
        "bpm": 84,
        "rpm": 14,
        "sn": "201906078",
        "signal": "64/100",
        "quality": "99/100",
        "ssid": "B03-1"
      }
    ]
  }
}
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/bio-sensor/latest` | Latest MQTT sensor reading |
| `GET` | `/api/bio-sensor/scan-history` | Historical scan records from SQLite |

## Generating Fake Data

For testing the scan history UI without a real sensor:

```bash
PYTHONPATH=src/backend python src/backend/utils/generate_fake_sensor_data.py
```

# Bio-Sensor MQTT Integration

This document describes how to integrate and test the MQTT-based bio-sensor with the Kachaka Command Center.

## Configuration

Update your `.env.local` file with the following MQTT settings:

```ini
# MQTT Configuration
MQTT_ENABLED=true
MQTT_BROKER_IP= <broker_ip>
MQTT_BROKER_PORT= <broker_port>
MQTT_TOPIC= <topic>
```

## Testing with Mock Sensor

### 1. Start the Mock MQTT Broker and Publisher

Run the mock MQTT broker and publisher to simulate bio-sensor data:

```bash
# Install Mosquitto MQTT broker (if not already installed)
# For Windows: https://mosquitto.org/download/

# Start the broker (in a separate terminal)
mosquitto -v

# In another terminal, run the mock sensor publisher
python tests/mock_bio_sensor.py --broker localhost --port 1883 --topic /data-test/demo/wisleep-eck/org/201906078 --interval 2
```

### 2. Start the Application

In a new terminal, start the FastAPI application:

```bash
# on Windows Env.
.venv\Scripts\Activate.ps1
python run.py 
```

### 3. Access Bio-Sensor Data

You can access the latest bio-sensor data via the API:

```bash
curl http://localhost:8000/api/bio-sensor/latest
```

### Bio-sensor sample data

```json
{
  "status": "success",
  "data": {
    "records": [
      {
        "a-HR": 0,
        "a-RR": 0,
        "ch1_status": 2,
        "status": 2,
        "bpm": 84,
        "rpm": 14,
        "sn": "201906078",
        "user_id": "d08ab880-469c-11f0-854c-edb89fd99d50",
        "b_id": "201906078",
        "dt": 1750395632,
        "ms": 1750395632380,
        "signal": "64/100",
        "quality": "99/100",
        "noise": "0/100",
        "ssid": "B03-1",
        "Signal_Strength": 2.9608584999999996,
        "beginTime": 1750394485,
        "leavingDuration": 0
      }
    ]
  }
}
```

## Integrating with a Real Sensor

1. Ensure your bio-sensor is configured to publish data to the MQTT broker at the specified topic.
2. Update the MQTT broker settings in your `.env` file to match your sensor's configuration.
3. The application will automatically connect to the broker and start receiving data.

## API Endpoints

- `GET /api/bio-sensor/latest` - Get the latest bio-sensor data

## Configuration

You can configure the MQTT topic and broker settings in the `.env` file. The application will automatically reconnect if the connection is lost.

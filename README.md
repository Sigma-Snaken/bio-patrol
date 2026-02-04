# Bio Patrol

Automated bio-sensor patrol system built on the Kachaka robot platform. The robot autonomously navigates between beds on a configurable schedule, docking a sensor shelf at each location to collect physiological data (heart rate, respiration) via MQTT, then returns the shelf home.

## Architecture

```
FastAPI (backend)  ──  gRPC  ──  Kachaka Robot
       │
       ├── MQTT ── Bio-sensor (WiSleep)
       ├── APScheduler (patrol scheduling)
       ├── SQLite (scan history)
       └── Telegram (alerts)

Vanilla JS SPA (frontend)
```

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, Python 3.12 |
| Robot API | gRPC via `kachaka-api` |
| Bio-sensor | MQTT (`paho-mqtt`) |
| Scheduling | APScheduler |
| Database | SQLite (scan history) |
| Frontend | Vanilla JS SPA |
| Notifications | Telegram Bot API |
| Deployment | Docker (amd64 + arm64) / PyInstaller |

## Quick Start

### Docker (recommended)

```bash
docker compose up app
```

The app will be available at `http://localhost:8000`.

### Local Development

```bash
uv sync
PYTHONPATH=src/backend uv run uvicorn main:app --app-dir src/backend --reload
```

## Configuration

Runtime JSON configs live in `data/config/`, merged with defaults from `src/backend/settings/defaults.py`.

| File | Purpose |
|------|---------|
| `data/config/settings.json` | Robot IP, MQTT broker, Telegram config, retry params |
| `data/config/beds.json` | Room/bed layout |
| `data/config/patrol.json` | Shelf ID, patrol order |
| `data/config/schedule.json` | Scheduled patrol times (daily/weekday) |

## Project Structure

```
bio-patrol/
├── src/
│   ├── backend/                 # Python FastAPI backend
│   │   ├── main.py              # App entry, lifespan, router mounting
│   │   ├── common_types.py      # Shared models & enums
│   │   ├── dependencies.py      # DI: get_fleet, get_bio_sensor_client
│   │   ├── routers/
│   │   │   ├── kachaka.py       # Robot control endpoints
│   │   │   ├── tasks.py         # Task CRUD
│   │   │   ├── settings.py      # Config + patrol + schedule APIs
│   │   │   └── bio_sensor.py    # Bio-sensor data endpoints
│   │   ├── services/
│   │   │   ├── fleet_api.py     # Robot fleet abstraction
│   │   │   ├── robot_manager.py # Robot lifecycle
│   │   │   ├── task_runtime.py  # Task execution engine
│   │   │   ├── scheduler.py     # APScheduler integration
│   │   │   ├── bio_sensor_mqtt.py # MQTT client
│   │   │   └── telegram_service.py # Telegram notifications
│   │   ├── settings/
│   │   │   ├── config.py        # Config loading & paths
│   │   │   └── defaults.py      # Default settings
│   │   └── utils/
│   │       ├── json_io.py       # JSON file helpers
│   │       └── generate_fake_sensor_data.py
│   │
│   └── frontend/                # Static web SPA
│       ├── index.html
│       ├── css/style.css
│       ├── js/
│       └── assets/
│
├── data/                        # Runtime data (Docker volume)
│   ├── config/                  # JSON configs
│   │   ├── settings.json
│   │   ├── beds.json
│   │   ├── patrol.json
│   │   └── schedule.json
│   └── sensor_data.db           # SQLite (created at runtime)
│
├── tests/
├── build/                       # PyInstaller specs
├── docs/
├── protos/                      # gRPC proto reference
├── .github/workflows/docker.yml # CI: multi-arch Docker builds
├── Dockerfile                   # Multi-stage, ARM-ready
├── docker-compose.yml
├── pyproject.toml
└── uv.lock
```

## API Overview

| Endpoint | Description |
|----------|-------------|
| `GET /api/settings` | Runtime settings |
| `GET /api/patrol/status` | Current patrol status |
| `POST /api/patrol/start` | Start patrol |
| `POST /api/tasks` | Create a task |
| `GET /api/tasks` | List all tasks |
| `GET /api/bio-sensor/latest` | Latest MQTT sensor data |
| `GET /api/bio-sensor/scan-history` | Historical scan records |
| `GET /kachaka/{robot_id}/battery` | Robot battery info |
| `POST /kachaka/{robot_id}/command/move_to_location` | Move robot |

## License

Apache-2.0

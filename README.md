# Bio Patrol

Automated bio-sensor patrol system for the Kachaka robot platform.

The robot autonomously navigates between hospital beds on a configurable schedule, docking a sensor shelf at each bed to collect physiological data (heart rate, respiration rate) via MQTT, then returns the shelf home. Alerts are sent via Telegram on anomalies or hardware errors.

## Architecture

```
                          gRPC
  ┌──────────┐      ┌──────────────┐
  │ Frontend │      │ Kachaka Robot│
  │  (SPA)   │      └──────┬───────┘
  └────┬─────┘             │
       │ HTTP         gRPC │
       ▼                   ▼
  ┌────────────────────────────────┐
  │         FastAPI Backend        │
  │                                │
  │  Scheduler ─── Task Engine     │
  │       │            │           │
  │  MQTT Client   Fleet API       │
  │       │                        │
  │  SQLite (scan history)         │
  │  Telegram (alerts)             │
  └───────────┬────────────────────┘
              │ MQTT
       ┌──────┴──────┐
       │  Bio-sensor  │
       │  (WiSleep)   │
       └─────────────┘
```

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, Python 3.12 |
| Robot API | gRPC (`kachaka-api`) |
| Bio-sensor | MQTT (`paho-mqtt`) |
| Scheduling | APScheduler |
| Database | SQLite |
| Frontend | Vanilla JS SPA |
| Notifications | Telegram Bot API (`httpx`) |
| Deployment | Docker (amd64 + arm64) |

## Quick Start

### Docker

```bash
docker compose up app
```

### Local Development

```bash
uv sync
PYTHONPATH=src/backend uv run uvicorn main:app --app-dir src/backend --reload
```

App runs at http://localhost:8000 (UI at `/ui/`).

## Production Deployment

See [`deploy/README.md`](deploy/README.md) for Docker Compose production setup, including ARM64 targets (Nvidia Jetson, Raspberry Pi).

## Configuration

Runtime configs live in `data/config/`, merged with defaults at startup.

| File | Purpose |
|------|---------|
| `data/config/settings.json` | Robot IP, MQTT broker, Telegram tokens, scan retry params |
| `data/config/beds.json` | Room/bed layout and numbering |
| `data/config/patrol.json` | Shelf ID, patrol route (bed order) |
| `data/config/schedule.json` | Scheduled patrol times (`daily` / `weekday`) |

Defaults are defined in [`src/backend/settings/defaults.py`](src/backend/settings/defaults.py).

## Project Structure

```
bio-patrol/
├── src/
│   ├── backend/
│   │   ├── main.py                 # App entry, lifespan, router mounting
│   │   ├── common_types.py         # Shared models & enums
│   │   ├── dependencies.py         # DI: get_fleet, get_bio_sensor_client
│   │   ├── routers/
│   │   │   ├── kachaka.py          # Robot control endpoints
│   │   │   ├── tasks.py            # Task CRUD & queue
│   │   │   ├── settings.py         # Config, beds, patrol, schedule APIs
│   │   │   └── bio_sensor.py       # Sensor data & scan history
│   │   ├── services/
│   │   │   ├── fleet_api.py        # Multi-robot fleet abstraction
│   │   │   ├── robot_manager.py    # Robot client lifecycle
│   │   │   ├── task_runtime.py     # Task execution engine
│   │   │   ├── scheduler.py        # APScheduler integration
│   │   │   ├── bio_sensor_mqtt.py  # MQTT client + SQLite persistence
│   │   │   └── telegram_service.py # Telegram alert notifications
│   │   ├── settings/
│   │   │   ├── config.py           # Config loading & file paths
│   │   │   └── defaults.py         # Default values for all settings
│   │   └── utils/
│   │       ├── json_io.py          # JSON read/write helpers
│   │       └── generate_fake_sensor_data.py
│   │
│   └── frontend/                   # Vanilla JS SPA
│       ├── index.html
│       ├── css/style.css
│       ├── js/
│       │   ├── script.js           # Main UI logic
│       │   ├── dataService.js      # API client
│       │   ├── dynamicParams.js    # Dynamic form params
│       │   ├── mockData.js         # Frontend mock data
│       │   └── script.sim.js       # Simulation mode
│       ├── img/
│       └── assets/icons/
│
├── data/                           # Runtime data (Docker volume)
│   └── config/                     # JSON configs
│
├── deploy/                         # Production deployment configs
│   ├── docker-compose.prod.yml
│   ├── mosquitto.conf
│   ├── data/config/                # Template configs for deployment
│   └── README.md
│
├── docs/                           # Documentation & diagrams
├── .github/workflows/docker.yml    # CI: multi-arch Docker builds
├── Dockerfile                      # Multi-stage, ARM64-ready
├── docker-compose.yml              # Local development
├── pyproject.toml
└── uv.lock
```

## API

### Settings & Config

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/settings` | Get runtime settings |
| `PUT` | `/api/settings` | Update settings |
| `GET` | `/api/beds` | Get bed layout |
| `PUT` | `/api/beds` | Update bed layout |
| `GET` | `/api/patrol` | Get patrol config |
| `PUT` | `/api/patrol` | Update patrol config |
| `GET` | `/api/schedule` | Get scheduled patrols |
| `PUT` | `/api/schedule` | Update schedule |

### Patrol & Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/patrol/start` | Start a patrol run |
| `GET` | `/api/patrol/status` | Current patrol status |
| `POST` | `/api/tasks` | Create a task |
| `GET` | `/api/tasks` | List all tasks |
| `GET` | `/api/tasks/{task_id}` | Get task detail |

### Bio-sensor

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/bio-sensor/latest` | Latest MQTT sensor reading |
| `GET` | `/api/bio-sensor/scan-history` | Historical scan records |

### Robot Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/kachaka/robots` | List registered robots |
| `GET` | `/kachaka/{robot_id}/battery` | Battery status |
| `POST` | `/kachaka/{robot_id}/command/move_to_location` | Move robot |
| `POST` | `/kachaka/{robot_id}/command/move_shelf` | Move shelf |
| `POST` | `/kachaka/{robot_id}/command/return_shelf` | Return shelf home |
| `POST` | `/kachaka/{robot_id}/command/speak` | Text-to-speech |

## CI/CD

GitHub Actions (`.github/workflows/docker.yml`) automatically builds and pushes multi-arch Docker images on push to `main`:

- Platforms: `linux/amd64`, `linux/arm64`
- Registry: `ghcr.io/sigma-snaken/bio-patrol`
- Cache: GitHub Actions cache (`type=gha`)

## License

Apache-2.0

# Bio Patrol

Kachaka 機器人自動巡房系統 — 搭載生理感測器，自動巡視病房床位，透過 MQTT 收集心率/呼吸數據，異常時即時 Telegram 通報。

## 系統架構

```
                          gRPC (protobuf)
  ┌──────────┐      ┌──────────────────┐
  │ Frontend │      │  Kachaka Robot   │
  │  (SPA)   │      │  192.168.x.x    │
  └────┬─────┘      └──────┬───────────┘
       │ HTTP/SSE      gRPC│
       v                   v
  ┌───────────────────────────────────────┐
  │           FastAPI Backend             │
  │                                       │
  │  ┌───────────┐   ┌────────────────┐  │
  │  │ Scheduler │──▶│  Task Engine   │  │
  │  │(APScheduler)  │  (TaskEngine)  │  │
  │  └───────────┘   └───────┬────────┘  │
  │                          │           │
  │  ┌────────────┐   ┌──────┴────────┐  │
  │  │ MQTT Client│   │   Fleet API   │  │
  │  │(paho-mqtt) │   │(RobotManager) │  │
  │  └─────┬──────┘   └──────────────┘  │
  │        │                             │
  │  ┌─────┴──────┐  ┌───────────────┐  │
  │  │   SQLite   │  │   Telegram    │  │
  │  │(scan hist) │  │  (httpx)      │  │
  │  └────────────┘  └───────────────┘  │
  └───────────┬───────────────────────────┘
              │ MQTT
       ┌──────┴──────┐
       │  Bio-sensor │
       │  (WiSleep)  │
       └─────────────┘
```

## 技術棧

| 層級 | 技術 |
|------|------|
| Backend | FastAPI, Python 3.12, uvicorn |
| Robot API | gRPC / protobuf (`kachaka-api`) |
| Bio-sensor | MQTT (`paho-mqtt 2.x`) |
| Scheduling | APScheduler |
| Database | SQLite |
| Frontend | Vanilla JS SPA, Canvas (地圖渲染) |
| Notifications | Telegram Bot API (`httpx`) |
| Deployment | Docker multi-arch (amd64 + arm64) |

## 快速開始

### Docker (推薦)

```bash
docker compose up
```

### 本地開發

```bash
uv sync
PYTHONPATH=src/backend uv run uvicorn main:app --app-dir src/backend --reload
```

服務啟動於 http://localhost:8000

## 核心功能

### 自動巡房

- 依排程或手動觸發巡房任務
- 機器人攜帶感測器貨架依序移動到各床位
- 每個床位停留讀取生理數據（心率、呼吸率）
- 數據存入 SQLite，異常時 Telegram 通報

### 貨架掉落偵測

巡房過程中持續監控貨架搬運狀態：

- **偵測方式**：背景 polling (`get_moving_shelf_id()`) 每 3 秒檢查
- **觸發時**：查詢貨架當前位置 → 記錄座標到 task metadata
- **前端顯示**：彈出警示視窗，內嵌地圖標示掉落位置（紅色標記）
- **恢復選項**：僅歸位感測器 / 歸位並繼續巡房（剩餘床位）

### 移動錯誤處理

- move_shelf / return_shelf 失敗 → 跳過關聯的 bio_scan 步驟
- 被跳過的 bio_scan 記錄到 DB（status=N/A, 原因=機器人無法移動到床邊）
- gRPC transient errors 自動 exponential backoff 重試

### 地圖系統

- 從機器人抓取地圖（protobuf → PNG + metadata）
- Canvas 渲染：地圖底圖 + 機器人即時位置 + 貨架掉落標記
- 支援 pan/zoom（滑鼠 + 觸控）

## 設定

Runtime 設定檔位於 `data/config/`，啟動時與 defaults 合併：

| 檔案 | 用途 |
|------|------|
| `settings.json` | Robot IP, MQTT broker, Telegram tokens, scan 參數 |
| `beds.json` | 病房 / 床位配置 |
| `patrol.json` | 巡房路線（床位順序、啟用狀態） |
| `schedule.json` | 排程巡房時間 |

預設值定義於 [`src/backend/settings/defaults.py`](src/backend/settings/defaults.py)。

## 專案結構

```
bio-patrol/
├── src/
│   ├── backend/
│   │   ├── main.py                 # App entry, lifespan, router mount
│   │   ├── common_types.py         # Task, Step, Status enums
│   │   ├── dependencies.py         # DI: fleet, bio_sensor client
│   │   ├── routers/
│   │   │   ├── kachaka.py          # Robot control endpoints
│   │   │   ├── tasks.py            # Task CRUD & queue
│   │   │   ├── settings.py         # Config, maps, beds, patrol API
│   │   │   └── bio_sensor.py       # Sensor data & scan history
│   │   ├── services/
│   │   │   ├── fleet_api.py        # Fleet abstraction (multi-robot)
│   │   │   ├── robot_manager.py    # Robot client lifecycle & resolver
│   │   │   ├── task_runtime.py     # Task execution engine
│   │   │   ├── scheduler.py        # APScheduler integration
│   │   │   ├── bio_sensor_mqtt.py  # MQTT client + SQLite
│   │   │   └── telegram_service.py # Telegram notifications
│   │   ├── settings/
│   │   │   ├── config.py           # Config loading & paths
│   │   │   └── defaults.py         # Default values
│   │   └── utils/
│   │       └── json_io.py          # JSON read/write helpers
│   │
│   └── frontend/                   # Vanilla JS SPA
│       ├── index.html
│       ├── css/style.css
│       └── js/
│           ├── script.js           # Main UI + map rendering
│           └── dataService.js      # API client (axios)
│
├── data/                           # Runtime data (Docker volume)
│   ├── config/                     # JSON configs
│   └── maps/                       # Map PNG + metadata
│
├── deploy/                         # Production deployment
│   ├── docker-compose.prod.yml
│   └── README.md
│
├── docs/                           # Documentation
│   ├── task_runtime_flow.md        # Task engine flow diagrams
│   ├── BIO_SENSOR.md              # MQTT sensor integration
│   └── GRPC_ERROR_FIX_SUMMARY.md  # Error handling & retry
│
├── Dockerfile                      # Multi-stage, ARM64-ready
├── docker-compose.yml              # Local development
├── pyproject.toml
└── uv.lock
```

## API 端點

### 設定 & 配置

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET/PUT` | `/api/settings` | Runtime 設定 |
| `GET/PUT` | `/api/beds` | 床位配置 |
| `GET/PUT` | `/api/patrol` | 巡房路線 |
| `GET/PUT` | `/api/schedule` | 排程設定 |
| `GET` | `/api/maps` | 地圖列表 |
| `POST` | `/api/maps/fetch` | 從機器人抓取地圖 |

### 巡房 & 任務

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/patrol/start` | 啟動巡房 |
| `GET` | `/api/tasks` | 任務列表 |
| `GET` | `/api/tasks/{id}` | 任務詳情 |
| `POST` | `/api/tasks/{id}/resume` | 恢復中斷的巡房 |

### Bio-sensor

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/bio-sensor/latest` | 最新感測器讀數 |
| `GET` | `/api/bio-sensor/scan-history` | 歷史掃描紀錄 |

### Robot Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/kachaka/robots` | 已註冊機器人列表 |
| `GET` | `/kachaka/{id}/battery` | 電池狀態 |
| `GET` | `/kachaka/{id}/pose` | 機器人位置 |
| `POST` | `/kachaka/{id}/command/move_shelf` | 搬運貨架 |
| `POST` | `/kachaka/{id}/command/return_shelf` | 歸還貨架 |
| `POST` | `/kachaka/{id}/command/return_home` | 返回充電座 |

## 部署

見 [`deploy/README.md`](deploy/README.md)。

CI/CD 透過 GitHub Actions (`.github/workflows/docker.yml`) 自動建置 multi-arch Docker image：

- Platforms: `linux/amd64`, `linux/arm64`
- Registry: `ghcr.io/sigma-snaken/bio-patrol`

## 詳細文件

| 文件 | 內容 |
|------|------|
| [`docs/task_runtime_flow.md`](docs/task_runtime_flow.md) | Task Engine 完整流程圖 & 錯誤處理 |
| [`docs/BIO_SENSOR.md`](docs/BIO_SENSOR.md) | MQTT 感測器整合說明 |
| [`docs/GRPC_ERROR_FIX_SUMMARY.md`](docs/GRPC_ERROR_FIX_SUMMARY.md) | gRPC 錯誤處理 & 重試邏輯 |

## License

Apache-2.0

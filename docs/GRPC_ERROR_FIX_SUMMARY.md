# gRPC Error Handling & Retry Logic

## 重試機制 (`retry_with_backoff`)

關鍵的機器人操作使用 exponential backoff 重試：

| 操作 | 最大重試次數 | 說明 |
|------|-------------|------|
| `move_shelf` | 3 | 搬運貨架到目標位置 |
| `return_shelf` | 3 | 歸還貨架到原位 |
| `move_to_location` | 2 | 移動到指定地點 |
| `dock_shelf` / `undock_shelf` | 2 | 對接/脫離貨架 |

可重試的 gRPC error codes：`UNAVAILABLE`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`。
其他 error codes 立即失敗，不重試。

Backoff 公式：`delay = min(base_delay * 2^attempt, max_delay)`

## 移動錯誤處理

`move_shelf` / `return_shelf` 失敗（包含 error code 14606/10001/11005 移動中斷）走正常的 `skip_on_failure` 流程：

1. 跳過關聯的 `bio_scan` 步驟
2. 被跳過的 bio_scan 記錄到 DB（status=N/A, details="機器人無法移動到床邊"）
3. 巡房繼續執行下一個床位

## 貨架掉落偵測

貨架掉落**僅由背景 polling monitor 偵測**（非 error code）：

1. `_monitor_shelf()` 每 3 秒呼叫 `get_moving_shelf_id()`
2. 回傳空值 → 設定 `_shelf_dropped = True`
3. 主迴圈偵測到 → `_handle_shelf_drop()`
4. 查詢貨架位置（`get_shelves()`）→ 記錄 `shelf_pose` 到 task metadata
5. Task 狀態設為 `SHELF_DROPPED`，機器人返回充電座
6. Telegram 通報 + 前端彈出警示視窗（含地圖標示掉落位置）

### Shelf Monitor 生命週期

- **啟動**：`move_shelf` 成功後啟動背景 polling
- **停止**：
  - `return_shelf` 執行前即停止（進入 return_shelf 步驟時，先呼叫 `_stop_shelf_monitor()` 再執行指令，之後不再監控）
  - `_handle_shelf_drop()` 內部停止
  - `run_task()` finally 區塊兜底停止

## Robot 就緒驗證

- `check_robot_readiness()` 在操作前驗證機器人狀態
- `wait_for_robot_ready()` 可配置 timeout 的 polling 等待
- 連線測試時自動更新機器人狀態

## 設定

重試參數在 `data/config/settings.json`：

```json
{
  "robot_max_retries": 3,
  "robot_retry_base_delay": 2.0,
  "robot_retry_max_delay": 10.0
}
```

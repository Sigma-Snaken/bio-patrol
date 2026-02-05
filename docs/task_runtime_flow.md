# Task Runtime 流程圖與錯誤處理

> 對應檔案：`src/backend/services/task_runtime.py`

---

## 1. 整體調度架構 (Dispatcher + Worker)

```
                         ┌─────────────────┐
                         │   API 提交 Task  │
                         └────────┬────────┘
                                  │
                                  v
                         ┌─────────────────┐
                         │  global_queue    │
                         └────────┬────────┘
                                  │
                         ┌────────v────────┐
                         │   dispatcher()   │
                         │  (永久 loop)     │
                         └────────┬────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │ task.robot_id 有值?         │
                    ├── YES ──┐                  ├── NO ──┐
                    │         v                  │        v
                    │  robot 有 queue?            │  等待 available_robots_queue
                    │  ├─ NO → FAILED            │        │
                    │  └─ YES                    │        v
                    │     │                      │  robot 可用且不忙?
                    │     v                      │  ├─ NO → 重新入列
                    │  放入 robot queue           │  └─ YES
                    │  status = QUEUED            │     │
                    │                            │     v
                    │                            │  放入 robot queue
                    │                            │  status = QUEUED
                    └────────────┬───────────────┘
                                 │
                    ┌────────────v───────────────┐
                    │  task_worker(robot_id)      │
                    │  (每個 robot 一個 worker)    │
                    │  等待 queue.get()            │
                    └────────────┬───────────────┘
                                 │
                    task.status == CANCELLED?
                    ├─ YES → 跳過，不執行
                    └─ NO  → engine.run_task(task)
```

---

## 2. `run_task()` 主迴圈

```
run_task(task)
    │
    ├── _refresh_name_cache()        ← 失敗只 warn，不中斷
    ├── status = IN_PROGRESS
    ├── 重設 shelf monitor 狀態
    │
    v
┌══════════════════════════════════════════════════════════════════════┐
║  while step_index < len(task.steps):                               ║
║      │                                                             ║
║      ├─── [CHECK 1] status == CANCELLED?                           ║
║      │    └─ YES → break                                           ║
║      │                                                             ║
║      ├─── [CHECK 2] _shelf_dropped flag == True?  ← 背景 polling   ║
║      │    └─ YES → _handle_shelf_drop() → break                   ║
║      │                                                             ║
║      ├─── [CHECK 3] step_id in skipped_steps?                      ║
║      │    └─ YES → 記錄 SKIPPED + DB → continue  (見 §3)          ║
║      │                                                             ║
║      ├─── step.status = EXECUTING                                  ║
║      │                                                             ║
║      ├─── try:                                                     ║
║      │    │   step_result = _execute_step(step)                    ║
║      │    │                                                        ║
║      │    ├── success?                                              ║
║      │    │   └─ YES → log ✓ → step_index++                       ║
║      │    │                                                        ║
║      │    └── FAIL → 進入錯誤分流 (見 §4)                           ║
║      │                                                             ║
║      └─── except Exception:                                        ║
║           └── 進入例外分流 (見 §5)                                   ║
║                                                                    ║
║      step_index++                                                  ║
╚══════════════════════════════════════════════════════════════════════╝
    │
    ├── status still IN_PROGRESS? → status = DONE
    │
    v
┌── finally ──────────────────────────────────┐
│  1. _stop_shelf_monitor()                   │
│  2. Telegram 巡房摘要 (成功/總數)            │
│  3. current_tasks 移除 robot                │
│  4. available_robots_queue.put(robot_id)    │
└─────────────────────────────────────────────┘
```

---

## 3. Conditional Skip 流程 (`step_id in skipped_steps`)

```
step 被標記為 skipped (因前一個 step 失敗的 skip_on_failure)
    │
    ├── step.action == "bio_scan"?
    │   └─ YES → 寫入 DB 記錄 (status=N/A, details="機器人無法移動到床邊")
    │            MQTT client 不可用則只 warn
    │
    ├── step.status = SKIPPED
    ├── step.result = 帶有 conditional_skip 原因的 StepResult
    └── continue → 下一個 step
```

---

## 4. Step 失敗分流 (`step_result.success == False`)

```
step_result 失敗
    │
    ├─── [路徑 A] 有 skip_on_failure 條件跳過邏輯
    │    條件: step.skip_on_failure 非空
    │    │
    │    ├── 將 skip_on_failure 中的 step_id 加入 skipped_steps
    │    ├── 記錄每個要跳過的 step 的失敗原因 → skip_reasons
    │    └── 繼續下一步 (不中斷 task)
    │
    │    典型場景:
    │    - move_shelf 失敗 (含 14606/10001/11005 移動中斷)
    │      → 跳過關聯的 bio_scan → DB 記錄「機器人無法移動到床邊」
    │
    ├─── [路徑 B] 非關鍵動作失敗
    │    條件: action in (bio_scan, wait, speak, return_shelf)
    │    │
    │    └── log warning，繼續下一步
    │
    └─── [路徑 C] 關鍵失敗
         條件: 以上皆不符合
         │
         └── task.status = FAILED → break
```

**優先級順序**: A > B > C（依 if/elif 順序判斷）

---

## 5. Step 例外分流 (`except Exception`)

```
_execute_step 拋出未預期的例外
    │
    ├── step.result = error_code=-1 的 StepResult
    ├── step.status = FAIL
    │
    ├─── [路徑 A'] 有 skip_on_failure
    │    └── 同 §4 路徑 A
    │
    ├─── [路徑 B'] 非關鍵動作
    │    └── 同 §4 路徑 B，繼續下一步
    │
    └─── [路徑 C'] 關鍵失敗
         └── task.status = FAILED → break
```

---

## 6. 貨架掉落處理 (`_handle_shelf_drop`)

貨架掉落**僅由背景 polling monitor 偵測**（`_monitor_shelf()` 發現機器人不再搬運貨架）。
移動指令的 error code (14606/10001/11005) 走正常的 skip_on_failure 流程，不觸發貨架掉落。

```
┌──────────────────────────────────────────┐
│  觸發來源: Polling Monitor               │
│  _monitor_shelf() 背景 task              │
│  每 3 秒 get_moving_shelves_id()         │
│  回傳空值 → _shelf_dropped = True        │
│  → 主迴圈 CHECK 2 偵測到                 │
└──────────────────┬───────────────────────┘
                   │
                   v
     _handle_shelf_drop(task, step_index)
                   │
     ┌─────────────┼──────────────────────────────────┐
     │             │                                   │
     v             v                                   v
_stop_shelf     解析 shelf_id                     蒐集 remaining_beds
_monitor        (從 _current_shelf_id 取得)            │
                   │                      ┌────────────┼────────────┐
                   v                      │            │            │
            查詢貨架位置               目前 EXECUTING   所有未來      無 trigger_step?
            get_shelves()              的 bio_scan     pending      └─ 目前 EXECUTING
            找到匹配的 shelf            也加入         bio_scan        bio_scan 加入
            → shelf_pose = {x,y,theta}                steps
                   │                      └────────────┼────────────┘
                   v                                   │
          ┌────────────────────────────────┐            │
          │ task.metadata = {              │            │
          │   shelf_drop: true,            │            │
          │   shelf_id,                    │            │
          │   shelf_pose: {x, y, theta},  │ ◄──────────┘
          │   remaining_beds: [...],       │
          │   dropped_at: "..."            │
          │ }                              │
          │ task.status = SHELF_DROPPED    │
          └────────────┬───────────────────┘
                       │
         ┌─────────────┼─────────────────┐
         v             v                  v
  Telegram 通知    DB 記錄所有           Robot return_home
  "貨架掉落，      被跳過的 bio_scan     (失敗只 log error)
   請協助歸位"     (status=N/A,
  (失敗只 log)     "貨架掉落，巡房中斷")
```

### 前端顯示

shelf_pose 座標透過 task metadata 傳遞到前端：

```
Frontend polling (每 2 秒):
  checkShelfDrop()
  ├── 找到 shelf_dropped task
  │   ├── shelfDropPose = meta.shelf_pose
  │   ├── 繪製 mini-map (drawShelfDropMiniMap)
  │   │   └── 地圖底圖 + 紅色 ✕ 標記在貨架座標
  │   ├── 顯示剩餘未巡床位
  │   └── 顯示操作按鈕 (歸位/恢復巡房)
  └── 無 → shelfDropPose = null, 隱藏 overlay

drawMap() (每 frame):
  ├── 繪製地圖底圖
  ├── 繪製機器人位置
  └── 如果 shelfDropPose 有值 → 繪製紅色 ✕ 標記 (主地圖上也可見)
```

---

## 7. 貨架 Monitor 生命週期

```
                  move_shelf 成功
                  且 monitor 未啟動
                        │
                        ├── _current_shelf_id = shelf_id  ← 記住搬運中的貨架
                        │
                        v
              asyncio.create_task(_monitor_shelf)
                        │
           ┌────────────v────────────┐
           │  每 3 秒 loop:          │
           │  get_moving_shelves_id()│
           ├──────────┬─────────────┤
           │          │             │
           │     有 shelf_id    沒有 shelf_id
           │     (正常)          │
           │      │              v
           │      │         _shelf_dropped = True
           │      │         break
           │      v             │
           │   繼續 polling     │
           │                    │
           │  transient error → │
           │  吞掉，繼續 poll   │
           └────────────────────┘
                        │
        停止時機 (3 個):
        ├── return_shelf 執行前 → _stop_shelf_monitor()
        │   (進入 return_shelf 步驟即停止，之後不再監控)
        ├── _handle_shelf_drop() 內部呼叫
        └── run_task finally 區塊
```

---

## 8. `_execute_step` 內部錯誤處理

```
_execute_step(step)
    │
    ├── try:
    │   ├── speak / move_to_pose      → 直接呼叫 API
    │   ├── move_to_location          → retry_with_backoff (max 2 次)
    │   ├── dock_shelf / undock_shelf  → retry_with_backoff (max 2 次)
    │   ├── move_shelf                → retry_with_backoff (預設 3 次)
    │   │                               成功 → 啟動 shelf monitor
    │   │                               + 記住 _current_shelf_id
    │   ├── return_shelf              → 先停止 shelf monitor
    │   │                               → retry_with_backoff (預設 3 次)
    │   ├── return_home               → 直接呼叫 API
    │   ├── bio_scan                  → MQTT client 取資料
    │   │                               client=None → 立即回傳失敗
    │   ├── wait                      → asyncio.sleep
    │   └── 未知 action               → 回傳 error_code=-1
    │
    ├── except gRPC AioRpcError       → 回傳 gRPC error code
    ├── except ValueError             → Robot not found
    └── except Exception              → 回傳 error_code=-1
```

---

## 9. `retry_with_backoff` 重試邏輯

```
retry_with_backoff(func, max_retries, base_delay, max_delay)
    │
    for attempt in 0..max_retries:
        │
        ├── try: await func()
        │   └── 成功 → return result
        │
        ├── except AioRpcError:
        │   ├── 最後一次? → re-raise
        │   ├── code in (UNAVAILABLE, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED)?
        │   │   └─ YES → sleep(min(base_delay * 2^attempt, max_delay))
        │   │            繼續重試
        │   └── 其他 gRPC code → 立即 re-raise (不重試)
        │
        └── except Exception → 立即 re-raise (不重試)
```

---

## 10. Resolver Patch (name/ID 解析)

kachaka SDK 的 `ShelfLocationResolver` 原生只支援 `.name` 查詢。
`RobotManager._patch_resolver()` 在 resolver 初始化後 monkey-patch：

```
get_shelf_id_by_name(value)
    ├── 先比對 shelf.name == value → 回傳 shelf.id
    ├── 再比對 shelf.id == value   → 回傳 shelf.id  ← patch 新增
    └── 都沒有 → logger.warning (取代原本的 bare print())

get_location_id_by_name(value)
    └── 同上邏輯
```

---

## 11. 最終狀態總結

| 結束狀態 | 觸發條件 |
|---|---|
| `DONE` | 所有步驟跑完，status 仍為 IN_PROGRESS |
| `FAILED` | 關鍵步驟失敗（無 skip_on_failure 且非 non-critical） |
| `CANCELLED` | 外部設定 task.status = CANCELLED |
| `SHELF_DROPPED` | 貨架掉落（polling monitor 偵測到機器人不再搬運貨架） |

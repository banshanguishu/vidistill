# vidistill v2.0.0 多人共用设计文档

- **创建日期**：2026-05-15
- **作者**：libo.gou@dreambigcareer.com
- **状态**：设计已确认，待实现
- **前置文档**：[2026-05-12-vidistill-design.md](./2026-05-12-vidistill-design.md)（v1 原始设计）

## 1. 背景与目标

vidistill v1 部署到内网服务器后，团队多人想要同时使用。v1 的"单任务硬拒绝"在多人场景下表现为：第 2 个人提交时收到 409，认为系统卡死。本次升级让 10 人能共享同一实例，又不引入额外的并发资源压力和 API 额度风险。

### 目标

- 多人同时使用同一实例（团队规模 ~10 人）
- 任务自动排队，用户能看到自己的队列位置和"我的任务"列表
- 重启后已完成的任务和文件不丢
- 不引入新容器、不引入新外部依赖服务（Redis / Celery / 数据库服务等）
- API 额度消耗和限速风险与 v1 完全相同

### 非目标（明确不做）

- ❌ 真正并发跑多个 pipeline（坚持后端单 worker 串行）
- ❌ 登录、账号、权限系统
- ❌ 自动重试失败任务
- ❌ 队列优先级、插队、抢占
- ❌ WebSocket 实时推送（继续轮询）
- ❌ 移动端 / 暗色模式 / 国际化
- ❌ 监控告警系统
- ❌ 备份过期任务

## 2. 关键决策摘要

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 并发模型 | 后端**单 worker 串行**，前端**任务排队** | 不增加 CPU / 带宽 / API 额度消耗 |
| 队列总上限 | 10（运行 1 + 排队 9） | 防止极端情况下队列无限堆积 |
| 用户识别 | **匿名 cookie**（`visitor_id`） | 不引入登录，但能列出"我的任务" |
| 数据持久化 | **SQLite 单文件** | 标准库，零新依赖，重启数据保留 |
| 队列实现 | `asyncio.Queue` + 单 worker 协程 | 零新依赖，与 FastAPI 异步模型契合 |
| 历史保留 | **7 天自动清理** | 控制磁盘和列表长度 |
| 重启策略 | 中断任务一律 mark failed，**不恢复** | 防止重复消耗 API 额度，实现简单 |
| 文件访问 | 凭 job_id 公开下载，**不校验 visitor** | 保留分享链接能力（内网信任环境） |
| 前端框架 | 继续 Jinja2 + 原生 JS | 不引入 SPA 框架 |

## 3. 技术栈变更

相对 v1 的**新增**：

| 项 | 选型 | 说明 |
|----|------|------|
| 持久化 | Python 标准库 `sqlite3` | 单文件，挂载到 docker volume |
| Cookie 中间件 | FastAPI `BaseHTTPMiddleware` | 自写 ~30 行 |
| Spinner | 纯 CSS `@keyframes` | ~15 行 CSS，不引入图标库 |

**不引入**：Redis、Celery、APScheduler、SQLAlchemy、Alembic、jQuery、Vue、Bootstrap、Tailwind、HTMX、Font Awesome、Playwright。

`pyproject.toml` 依赖列表保持不变。

## 4. 架构总览

```
┌──────────────────────┐
│ HTTP 层               │
│  POST /jobs          │──┐
│  GET  /jobs/{id}     │  │
│  GET  /my/jobs       │  │
│  DELETE /jobs/{id}   │  │
│  GET  /jobs/{id}/    │  │
│       download/{fmt} │  │
└──────────────────────┘  │
                          ▼
              ┌────────────────────┐
              │ SqliteJobStore     │  ←─→  vidistill.db
              │ + asyncio.Queue    │
              └────────────────────┘
                          ▲
                          │
              ┌────────────────────┐
              │ 单 worker 协程      │  ──→ pipeline.process_video()
              │ while True:         │       │
              │   job = q.get()     │       ▼
              │   to_thread(...)   │   yt-dlp / ffmpeg / DashScope
              └────────────────────┘
                          ▲
                          │
              ┌────────────────────┐
              │ cleanup 协程        │
              │ every 1h            │
              │ delete > 7d         │
              └────────────────────┘
```

### 协程生命周期（FastAPI lifespan）

启动顺序：

1. 初始化 SQLite schema（`CREATE TABLE IF NOT EXISTS`）
2. **僵尸任务清理 SQL**：所有 `status NOT IN ('done', 'failed', 'cancelled')` 的旧任务被标记为 `failed: 服务重启时中断`
3. 创建 `asyncio.Queue(maxsize=9)`
4. 启动 worker 协程
5. 启动 cleanup 协程

关闭顺序：

1. lifespan 显式 `cancel()` worker 协程和 cleanup 协程，等待 ~1 秒优雅退出
2. 关闭 SQLite 连接
3. 正在跑的 process_video（在线程池里）会被强制中断，但下次启动时会被启动顺序的步骤 2 标记为 failed

## 5. 数据模型

### 5.1 SQLite Schema

文件位置：`{output_dir}/vidistill.db`（默认 `/tmp/vidistill/vidistill.db`，挂载 docker volume 持久化）

```sql
CREATE TABLE IF NOT EXISTS jobs (
    job_id           TEXT PRIMARY KEY,
    visitor_id       TEXT NOT NULL,
    url              TEXT NOT NULL,
    video_title      TEXT,
    style            TEXT NOT NULL,           -- 'short' | 'chapters'
    status           TEXT NOT NULL,           -- 见 5.3
    progress         INTEGER NOT NULL DEFAULT 0,
    error            TEXT,
    md_path          TEXT,
    html_path        TEXT,
    pdf_path         TEXT,
    created_at       TEXT NOT NULL,           -- ISO8601
    started_at       TEXT,                    -- worker 拾起的时刻
    finished_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_visitor_created ON jobs(visitor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_status          ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_created_at      ON jobs(created_at);
```

### 5.2 设计取舍

- **不存队列本身**：队列只在内存 `asyncio.Queue`。重启时按 §4 的僵尸清理 SQL 处理
- **`output_paths` 三字段平铺**而非 JSON：便于 SQL 直接判定可用格式
- **PDF 字段允许 NULL**：与 v1 "PDF 是 best-effort" 一致
- **不引入 ORM**：标准库 `sqlite3` 写原生 SQL，十几条够用
- **连接策略**：模块级单连接 + `check_same_thread=False` + `threading.Lock`
- **schema 演进**：未来加字段用 `ALTER TABLE ADD COLUMN` + try/except 忽略 duplicate，不引入 Alembic

### 5.3 状态枚举

```python
Status = Literal[
    "queued",       # 在 asyncio.Queue，未轮到
    "pending",      # worker 已拾起，即将进入 fetching
    "fetching",
    "transcribing",
    "summarizing",
    "rendering",
    "done",         # 终态
    "failed",       # 终态
    "cancelled",    # 终态
]
```

`queued` 和 `cancelled` 是 v2 新增。

### 5.4 状态转换图

```
                 [POST /jobs]
                       │
                       ▼
                   queued ───[DELETE]──→ cancelled
                       │                     │
                  [worker get]               │
                       │                     │
                       ▼                     │
                   pending                   │
                       │                     │
                       ▼                     │
                   fetching                  │
                       │                     │
             ┌─────────┴─────────┐           │
             │（有字幕）         │（无字幕） │
             │                   ▼           │
             │              transcribing     │
             │                   │           │
             └─────────┬─────────┘           │
                       ▼                     │
                  summarizing                │
                       │                     │
                       ▼                     │
                   rendering                 │
                       │                     │
                       ▼                     │
                     done                    │
                                             │
        (任意阶段异常)→ failed               │
                                             │
                       ▼                     ▼
              [7 天后被 cleanup 删除]
```

## 6. 用户识别（visitor cookie）

### 6.1 机制

新增 `vidistill/middleware.py` 提供 `VisitorCookieMiddleware`：

```python
class VisitorCookieMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        visitor_id = request.cookies.get("visitor_id")
        is_new = False
        if not visitor_id:
            visitor_id = secrets.token_urlsafe(16)
            is_new = True
        request.state.visitor_id = visitor_id
        response = await call_next(request)
        if is_new:
            response.set_cookie(
                "visitor_id",
                visitor_id,
                max_age=63072000,       # 2 年
                httponly=True,
                samesite="lax",
                path="/",
                # 不设 secure，因为内网部署是 http
            )
        return response
```

`build_app()` 里 `app.add_middleware(VisitorCookieMiddleware)`。

### 6.2 关联策略

| 端点 | 是否校验 visitor_id |
|------|---------------------|
| `POST /jobs` | 仅记录 visitor_id 进 SQLite |
| `GET /jobs/{id}` | ❌ 不校验（保留分享） |
| `GET /jobs/{id}/download/{fmt}` | ❌ 不校验（保留分享） |
| `GET /my/jobs` | ✓ 仅返回当前 visitor 的任务 |
| `DELETE /jobs/{id}` | ✓ 必须是创建者，否则 403 |

### 6.3 边界场景

| 场景 | 行为 |
|------|------|
| 用户清浏览器数据 | 新 visitor_id；旧任务在"我的列表"消失，但凭 job_id 链接仍可访问 |
| 同事共用一台电脑 | 同一 visitor_id，看到的"我的任务"混在一起（内网工具可接受） |
| 公司电脑 + 家里电脑 | 两个 visitor_id，各自列表独立 |
| Cookie 被禁用 | 每次请求新 id，"我的任务"永远空。UI 提示"如看不到历史，请开启 Cookie" |

## 7. HTTP API 规范

### 7.1 端点总览

| 方法 | 路径 | v1 | v2 |
|------|------|----|----|
| GET | `/` | 提交表单页 | 提交表单 + "我的任务"列表 |
| POST | `/jobs` | 创建 / 满则 409 | 创建入队 / 队满则 429 |
| GET | `/jobs/{job_id}` | 查状态 | 查状态，新增 `queue_position` 字段 |
| GET | `/jobs/{job_id}/download/{fmt}` | 下载 | **不变** |
| GET | `/my/jobs` | — | **新增** |
| DELETE | `/jobs/{job_id}` | — | **新增**：取消排队中任务 |

### 7.2 `POST /jobs`

**请求**：

```json
{"url": "https://www.bilibili.com/video/BVxxx", "style": "chapters"}
```

**响应码与 body**：

| 情况 | 状态码 | body |
|------|--------|------|
| yt-dlp 取元数据失败 | 422 | `{"detail": "..."}` |
| 时长 > 30 分钟 | 422 | `{"detail": "视频时长 X 分钟，超过 30 分钟上限"}` |
| 队列已满（队列内 + 运行中 = 10） | **429** | `{"detail": "队列已满（10 个），请稍后再试"}` |
| 成功 | 200 | `{"job_id": "...", "queue_position": 3}` |

**`queue_position` 定义**：包含正在运行的那个任务在内，本任务在等待序列中的位置（1-indexed）。

公式（仅当 status='queued' 时计算）：

```
queue_position = (SELECT COUNT(*) FROM jobs
                  WHERE status='queued' AND created_at < self.created_at)
               + 1
               + (1 if exists job with status in non-terminal-non-queued else 0)
```

示例：
- 当前没人在跑、我是第一个排队的 → `queue_position = 1`
- 当前有 1 个在跑、我前面无排队 → `queue_position = 2`
- 当前有 1 个在跑、我前面还有 2 个排队 → `queue_position = 4`

### 7.3 `GET /jobs/{job_id}`

```json
{
  "job_id": "abc123def456",
  "status": "queued",
  "progress": 0,
  "queue_position": 3,
  "error": null,
  "video_title": "...",
  "available_formats": ["md", "html"]
}
```

`queue_position`：仅 `status=queued` 时有意义（其他状态为 `null`）。计算公式与示例见 §7.2。

### 7.4 `GET /my/jobs`

```json
{
  "jobs": [
    {
      "job_id": "...",
      "video_title": "...",
      "status": "done",
      "queue_position": null,
      "progress": 100,
      "created_at": "2026-05-15T10:00:00",
      "available_formats": ["md", "html", "pdf"]
    }
  ],
  "system": {
    "active_count": 3,
    "active_max": 10,
    "queue_full": false
  }
}
```

- 仅返回当前 visitor 且 `created_at >= now() - 7 days` 的，按 `created_at DESC`
- 不分页（7 天 ~ 几十条直接全返回）
- `system.active_count` = 当前正在跑 + 队列中等待的总和（含义与 §7.2 "队列已满"判定一致）
- `system.queue_full` = `(active_count >= active_max)`，前端据此置灰提交按钮

### 7.5 `DELETE /jobs/{job_id}`

| 情况 | 状态码 | body |
|------|--------|------|
| job_id 不存在 | 404 | `{"detail": "任务不存在"}` |
| visitor_id 不匹配 | 403 | `{"detail": "无权操作此任务"}` |
| 任务状态不是 queued | 409 | `{"detail": "任务已开始处理，无法取消"}` |
| 成功 | 200 | `{"ok": true}` |

**实现策略**：标记 SQLite `status='cancelled'`。`asyncio.Queue` 不支持移除元素，所以 worker 在 `get()` 出任务后**先查 SQLite 状态**，若为 `cancelled` 就 skip。

### 7.6 异常映射（统一 handler）

```python
@app.exception_handler(VidistillError)
async def handle_vidistill_error(request, exc):
    mapping = {
        QueueFullError: 429,
        JobNotFoundError: 404,
        JobNotCancellableError: 409,
        JobAccessDeniedError: 403,
        VideoFetchError: 422,
    }
    return JSONResponse(
        {"detail": str(exc)},
        status_code=mapping.get(type(exc), 500),
    )
```

业务层抛领域异常，路由不写 `raise HTTPException`。

### 7.7 新增异常类（`exceptions.py`）

```python
class QueueFullError(VidistillError): ...
class JobNotFoundError(VidistillError): ...
class JobNotCancellableError(VidistillError): ...
class JobAccessDeniedError(VidistillError): ...
```

## 8. 队列与 Worker 协程

### 8.1 队列结构

```python
queue: asyncio.Queue[str] = asyncio.Queue(maxsize=9)  # 排队上限 9
```

- 队列只存 `job_id`
- 实际任务数据在 SQLite
- **总上限 10 = 队列 9 + 运行中 1**

### 8.2 Worker 协程

```python
async def _worker_loop(store, queue, config):
    while True:
        job_id = await queue.get()
        try:
            job = store.get(job_id)
            if not job or job.status == "cancelled":
                continue
            store.update(job_id, status="pending", started_at=datetime.now())
            await asyncio.to_thread(
                process_video,
                job_id=job_id, url=job.url, style=job.style,
                store=store, config=config,
            )
        except Exception:
            logger.exception("[worker] job=%s crashed outside pipeline", job_id)
            store.update(job_id, status="failed", error="worker 异常")
        finally:
            queue.task_done()
```

### 8.3 关键设计

- **单 worker**：保证 "同一时刻最多 1 个 pipeline"
- **`asyncio.to_thread`**：把 v1 同步的 `process_video`（内含 yt-dlp / ffmpeg / SDK 调用）扔进线程池，**避免阻塞 event loop**
- **双层异常隔离**：`process_video` 内部已 try/except 写 `failed` 状态，worker 层是双保险；**任何异常都不能让 worker 退出**
- **不重启 worker**：一次 `create_task` 终生，直到 app shutdown

## 9. 后台清理协程

### 9.1 频率

每 **1 小时**触发一次。不是每 7 天 —— 这样新部署 / 重启后短时间内就能处理积压。

### 9.2 实现

```python
async def _cleanup_loop(store, output_dir):
    while True:
        try:
            cutoff = datetime.now() - timedelta(days=7)
            stale = store.list_older_than(cutoff)  # 仅终态
            for job in stale:
                shutil.rmtree(output_dir / job.job_id, ignore_errors=True)
                store.delete(job.job_id)
            logger.info("[cleanup] removed %d stale jobs", len(stale))
        except Exception:
            logger.exception("[cleanup] tick failed, will retry next hour")
        await asyncio.sleep(3600)
```

### 9.3 关键

- 只清理终态任务（`done` / `failed` / `cancelled`）
- 先删文件后删 DB 记录（避免 "DB 没了文件还在" 的磁盘泄漏）
- 异常吃掉、log、下一小时再试 —— 协程绝不退出

## 10. 前端 UI

### 10.1 整体布局

保持 v1 的极简风格，**不引入 SPA 框架**。

```
┌─────────────────────────────────────────────────┐
│  vidistill                                       │
├─────────────────────────────────────────────────┤
│  ▢ 视频 URL ____________________  [短摘要 ▼]   │
│  [ 开始处理 ]                                    │
│                                                  │
│  ⚠ 队列已满 / ✓ 当前队列：3 / 10                │
├─────────────────────────────────────────────────┤
│  我的任务（最近 7 天）                           │
│  ┌───────────────────────────────────────────┐  │
│  │ 标题            状态         操作          │  │
│  ├───────────────────────────────────────────┤  │
│  │ 某 B 站视频    ⟳ 排队中 #3  [取消]        │  │
│  │ 某 YouTube     ⟳ 处理中 65% [查看]        │  │
│  │ 某讲座          已完成      [md][html][pdf]│  │
│  │ 某新闻          失败 ⓘ      [重试]         │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 10.2 模板拆分

```
templates/
├── base.html             # 整体框架（CSS、字体引入）
├── index.html            # 主页（提交表单 + 我的任务列表）
├── _form.html            # 提交表单 partial
├── _my_jobs.html         # 任务列表 partial（可独立刷新）
├── _status_label.html    # 状态文案 partial（详情页与列表共用）
└── job_detail.html       # 任务详情页（保留 v1，新加队列位置）
```

### 10.3 状态显示规则

| status | 列表显示 | spinner | 操作 |
|--------|---------|--------|------|
| `queued` | "排队中 #N" | ✓ | [取消] |
| `pending` / `fetching` / `transcribing` / `summarizing` / `rendering` | "处理中 X%" | ✓ | [查看详情] |
| `done` | "已完成" | ✗ | [md] [html] [pdf]（pdf 为 NULL 时灰） |
| `failed` | "失败 ⓘ"（hover 显示 error） | ✗ | [重新提交] |
| `cancelled` | "已取消" | ✗ | — |

### 10.4 状态文案（详情页）

| status | 文案 |
|--------|------|
| `queued` | "正在排队（第 N 位）..." |
| `pending` | "即将开始..." |
| `fetching` | "正在抓取视频信息..." |
| `transcribing` | "正在转写音频..." |
| `summarizing` | "正在生成摘要..." |
| `rendering` | "正在渲染输出..." |

集中在 `_status_label.html`，前后端共用（详情页 SSR 初始渲染 + JS 轮询切换）。

### 10.5 Spinner

```css
.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid #e0e0e0;
  border-top-color: #4a90e2;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  vertical-align: middle;
  margin-right: 6px;
}
@keyframes spin { to { transform: rotate(360deg); } }
```

出现位置：
1. 提交按钮按下后到收到响应前
2. 任务列表里非终态状态文字前
3. 详情页非终态时的进度条上方（稍大尺寸）

### 10.6 JS 与轮询

- 一个 `app.js` 文件，约 80 行原生 JS
- 主页"我的任务"：每 **3 秒** `GET /my/jobs`，仅当列表里有非终态任务时轮询（全部完成停止）
- 详情页：每 **2 秒** `GET /jobs/{id}`
- 队列满提示通过 `GET /my/jobs` 响应里的 `system` 字段，**不单独发请求**

### 10.7 样式

复用 v1 现有 CSS（如果有 base.css 就扩展，否则写一个 ~150 行）。**不引入 Bootstrap / Tailwind**。中文字体配置沿用 v1。

## 11. 错误处理

### 11.1 异常体系

沿用 v1 `VidistillError` 基类，新增 v2 特有异常（已在 §7.7 列出）。

### 11.2 边界场景清单

| 场景 | 期望行为 |
|------|---------|
| worker 跑到一半 docker stop | 启动时 SQL 把该任务 mark failed |
| SQLite 文件被外部进程锁定 | 抛 `OperationalError`，路由返回 500，不重试 |
| 队列 9 个排着，第 3 个被取消 | 状态变 cancelled，worker 拾起时 skip，后面的 queue_position 自动减 1 |
| 同一 visitor 短时间内提交 5 个相同 URL | 不去重，全部入队 |
| 用户在详情页等到 done，cleanup 协程刚好删了 | 浏览器轮询返回 404，前端提示"任务已过期" |
| `output_dir` 磁盘满 | yt-dlp/ffmpeg 抛 IOError → `VideoFetchError` → 任务 failed（沿用 v1 `min_free_disk_mb` 检查） |
| DashScope API 限流 | 抛错落到 `TranscriptionError` / `SummarizationError`，任务 failed，**不重试** |
| visitor 提交后立刻关浏览器 | 任务正常入队、正常跑、文件生成。下次同 visitor 打开仍能看到 |

## 12. 测试策略

### 12.1 单元测试（`tests/unit/`）

| 文件 | 覆盖范围 |
|------|---------|
| `test_jobs_sqlite.py` | SqliteJobStore CRUD、按 visitor 过滤、按时间清理、queue_position 计算、僵尸清理 SQL |
| `test_middleware.py` | visitor cookie 首次下发 + 后续透传 + 注入 request.state |
| `test_queue.py` | 入队 / 满判定 / cancelled skip 逻辑（不跑真 pipeline） |
| `test_routes_v2.py` | 各端点状态码 / Pydantic 校验 / 异常 handler 映射 |
| `test_cleanup.py` | mock 时间触发清理一次，验证 7 天前的终态任务被删 |

### 12.2 集成测试（`tests/integration/`）

| 文件 | 覆盖范围 |
|------|---------|
| `test_full_pipeline.py` | 单任务端到端（沿用 v1，调整 store 注入） |
| `test_concurrent_submit.py` | **新增**：两个 visitor 各提交 5 个任务，验证队列顺序、互不可见、第 11 个 429 |
| `test_restart_recovery.py` | **新增**：mock in-progress 任务到 SQLite，build_app() 后变 failed |

### 12.3 测试工具

- fixture 用 `SqliteJobStore(":memory:")`
- `asyncio.Queue` 在大部分测试里 mock 化，不真启 worker
- 沿用 v1 的 `tests/fixtures/*.json`（yt-dlp / Paraformer / Qwen 响应）

### 12.4 不做的测试

- ❌ 负载测试（10 人手点 = 极低吞吐量）
- ❌ 真实并发的 SQLite 写入竞态（单 worker 写不竞）
- ❌ 浏览器端 E2E（Playwright 之类）

## 13. 部署变更

### 13.1 docker-compose 调整

需要确保 `{output_dir}` 挂载为具名 volume（v1 已有）。SQLite 文件 `vidistill.db` 会自动落到该 volume 下，重启保留。

无新增容器。无环境变量变更。

### 13.2 数据迁移

v1 → v2 升级：v1 没有持久化数据，首次启动 v2 时 `CREATE TABLE IF NOT EXISTS` 即可，**无需迁移脚本**。

### 13.3 回滚策略

如需回滚 v1：停 v2 容器、启 v1 容器即可。v1 不读 SQLite 文件，v2 留下的 `vidistill.db` 会被忽略（保留在 volume 里，不影响 v1 运行）。

## 14. 开发量估算

| 阶段 | 工作量 |
|------|--------|
| SqliteJobStore + schema | 0.5 天 |
| Cookie 中间件 + visitor 注入 | 0.5 天 |
| asyncio.Queue + worker 协程 + 替换 BackgroundTasks | 1 天 |
| 7 天清理协程 + 启动时僵尸清理 | 0.5 天 |
| 前端"我的任务"列表 + 队列位置 + Spinner | 1 天 |
| 测试改造（单元 + 集成 + 新增） | 1 天 |
| **合计** | **约 4.5 个工作日** |

## 15. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| `asyncio.to_thread` 把同步 SDK 调用扔线程池后，SQLite 连接被多线程触碰 | 数据损坏 | `check_same_thread=False` + 模块级 `threading.Lock` 包裹所有写操作 |
| worker 协程异常退出导致全队列死锁 | 系统假死 | 双层 try/except，worker 主循环异常被吃掉 |
| 用户提交相同 URL 重复消耗 API 额度 | 浪费 token | 不做去重（spec 明确）；用户教育层面解决 |
| `asyncio.Queue` 队列里的任务被 `cancelled` 后 worker 仍然拾起 | 浪费一次 get/skip | worker 拾起后查 SQLite 状态先 skip，开销极低 |
| cleanup 协程异常导致磁盘堆积 | 长期可观磁盘泄漏 | 异常被吃掉但记 log；运维查看日志能发现 |
| 浏览器 Cookie 被禁用 | "我的任务"永远空 | UI 提示语 |

## 16. 验收标准

- [ ] 10 个浏览器同时打开页面，提交 10 个任务，第 11 个收到 429
- [ ] 提交后立刻看到自己的任务出现在"我的任务"列表
- [ ] 排队任务能看到正确的 `queue_position`，前面完成后位置正确递减
- [ ] DELETE 取消排队中任务有效，且不影响后续任务执行
- [ ] DELETE 已在 running 的任务返回 409
- [ ] 不同 visitor 互相看不到对方"我的任务"，但凭 job_id 可互相访问任务详情和下载文件
- [ ] docker restart 后，已完成任务在"我的任务"列表中仍可见、文件仍可下载
- [ ] docker restart 时正在跑的任务被标记为 failed
- [ ] 8 天前的终态任务被自动清理，文件和 DB 记录都消失
- [ ] 全部 `pytest` 通过

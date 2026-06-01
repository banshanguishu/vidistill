# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在本仓库工作时提供指引。

## 项目形态

视频 URL → AI 摘要 → Markdown / HTML / PDF，作为团队内网共享的 web 工具（~10 人规模）。**最初是单人版（v1），升级到 v2 多人共用，之后又做了前后端分离**，但后端仍刻意保持最小化：不引入 Redis / Celery / 关系型数据库服务、不做登录鉴权、不做失败重试、不做真正的并发 pipeline。**对于"为了（后端）健壮性加 X"的提议保持警惕** — spec 故意拒绝了大多数这类增加。

**前端已从内嵌 Jinja2 模板拆分为独立的 React + TypeScript + TailwindCSS v4 + Vite 工程**（同源单容器部署，详见 2026-06-01 设计）。这是对"极简"原则在前端上的一次**有意例外**——目的是让 UI 定制和后续前端开发更顺手；后端边界、契约、最小化原则不变。

权威设计文档（按时间顺序）：

- `docs/superpowers/specs/2026-05-12-vidistill-design.md` — v1 原始设计
- `docs/superpowers/plans/2026-05-12-vidistill.md` — v1 实现计划
- `docs/superpowers/specs/2026-05-15-vidistill-v2-concurrent-design.md` — **v2 多人共用设计（当前后端架构）**
- `docs/superpowers/plans/2026-05-15-vidistill-v2.md` — v2 实现计划
- `docs/superpowers/specs/2026-06-01-frontend-backend-separation-design.md` — **前后端分离设计（当前前端架构）**
- `docs/superpowers/plans/2026-06-01-frontend-backend-separation.md` — 前后端分离实现计划

当代码看起来不对劲时，先看 spec 再"修复"。冲突时以更晚的 spec 为准：v2 取代 v1；2026-06-01 spec 取代 v2 中"前端=Jinja2+原生JS、不引入 SPA 框架"的决策（仅前端这一点，后端仍以 v2 为准）。

## 常用命令

```powershell
# 后端
poetry install
poetry run uvicorn vidistill.main:app --reload --port 8000   # 后端 :8000
poetry run pytest                                            # 全部后端测试
poetry run pytest tests/unit/test_jobs.py                    # 单文件
poetry run pytest tests/unit/test_jobs.py::test_name -v      # 单条用例

# 前端（独立工程，在 frontend/ 下，需要 Node 20+）
cd frontend; npm install
cd frontend; npm run dev      # Vite dev server :5173，API 代理到 :8000 —— 开发时浏览器开 :5173
cd frontend; npm run build    # tsc --noEmit + vite build，产出 frontend/dist（供 FastAPI 同源托管）

# 容器（多阶段构建会自动编译前端，无需先 npm run build）
docker build -t vidistill . ; docker run -p 8000:8000 --env-file .env vidistill
```

**本地开发要同时跑两个进程**：后端 `uvicorn :8000` + 前端 `npm run dev :5173`，浏览器开 **:5173**（不是 8000）。

`.env` 中需要 `DASHSCOPE_API_KEY`（从 `.env.example` 复制），并且 PATH 上要有 `ffmpeg`（Windows 用 `winget install ffmpeg`）。`pyproject.toml` 中配置了 `pythonpath = ["src"]` 与 `asyncio_mode = "auto"`。

发布前的手动冒烟测试清单：`docs/smoke-test-checklist.md`。

反馈数据查询脚本：`scripts/show_feedback.py`（或容器内 `show_feedback.sh` 包装器）。

## 架构

请求流程仍是严格分层：`routes.py`（HTTP） → `pipeline.py`（编排） → `adapters/*`（外部 I/O） → `renderers/*`（文件输出）。三层在测试中独立 mock，写代码时务必保持边界干净。

但 v2 在 HTTP 层和 store 层之间多了一个**异步队列 + 单 worker 协程**：

```
HTTP 请求 → SqliteJobStore + asyncio.Queue → 单 worker 协程 → pipeline.process_video()
                                          ↑
                                          └─ cleanup 协程（每小时）
```

### 模块职责

- **`main.py`** — `build_app()` 工厂；模块级 `app` 是 uvicorn 加载的入口。**不再有全局 `_GLOBAL_STORE`**，每次 `build_app()` 都新建一个 `JobStore`，store / queue / worker_task / cleanup_task 都挂在 `app.state` 上。`build_app(output_dir=tmp_path)` 会同时把 `log_dir` 和 `db_path` 重定向到 `tmp_path` 供测试使用；`build_app(frontend_dist_dir=...)` 可覆盖前端构建产物目录（测试用）。启动时通过 `JobStore.mark_zombies_failed()` 把上次进程残留的非终态任务标记为 `failed`。FastAPI `lifespan` 负责启动 / 取消 worker 协程和 cleanup 协程。**若 `frontend_dist_dir/assets` 存在，会 `app.mount("/assets", StaticFiles(...))` 托管前端打包后的 JS/CSS/字体**（守卫挂载：目录不存在时不挂，回落到兜底页）。
- **`routes.py`** — 七个端点：
  - `GET /` 托管前端 SPA（`frontend/dist/index.html`）；未构建时返回兜底 HTML（提示去 `npm run build` 或用 Vite dev server）。Jinja2 已移除
  - `POST /jobs` 创建任务，超过 10 个 active 返回 **429** `QueueFullError`
  - `GET /jobs/{id}` 查询状态
  - `DELETE /jobs/{id}` 取消任务（仅 `queued` 状态可取消，必须是创建者的 visitor_id）
  - `GET /jobs/{id}/download/{fmt}` 下载文件（**不校验 visitor**，凭 job_id 公开下载，保留分享能力）
  - `GET /my/jobs` 列出当前 visitor 7 天内的任务 + 系统繁忙状态
  - `POST /feedback` 收集用户反馈（写入 SQLite `feedback` 表）
- **`pipeline.py`** — `process_video()` 走相位：`fetching` → `transcribing`（有字幕则跳过） → `summarizing` → `rendering` → `done`。每个任务都渲染**全部三种格式**，用户下载时再选。`md` 和 `html` 必出；`pdf` best-effort（缺 GTK 时 WeasyPrint 报错会被吞，`output_paths["pdf"] = None`）。无论成功失败，`_cleanup_intermediate` 都会删掉中间音频 / 字幕文件。
- **`jobs.py`** — `JobStore` 现在是 **SQLite 后端**（不是内存），单连接 + `threading.Lock` 保证线程安全。schema 见 `_SCHEMA` 常量，包含 `jobs` 和 `feedback` 两张表。重启后任务数据保留；非终态任务由 `mark_zombies_failed()` 在启动时一次性标记为 failed（不做断点续跑，避免重复消耗 API 额度）。**没有 `try_acquire_slot` / `release_slot`**，并发控制移到了路由层（用 `count_active()` 判断 + `asyncio.Queue(maxsize=9)` 把关）。
- **`queue_worker.py`** — `worker_loop(store, queue, config)`：单协程串行从 `asyncio.Queue` 取 job，调 `asyncio.to_thread(process_video, ...)`。**只允许一个 pipeline 同时跑**（即使队列里排了多个）。worker 在拿到任务后把状态从 `queued` 改成 `pending` 并写 `started_at`，完成后写 `finished_at`。取消的任务会被跳过。
- **`cleanup.py`** — `cleanup_loop` 每 3600 秒（1 小时）跑一次 `cleanup_once`，删除创建时间 > 7 天的终态任务记录及其输出目录。
- **`middleware.py`** — `VisitorCookieMiddleware`：给每个请求注入 `request.state.visitor_id`，首次访问时下发 cookie（`max_age=2y`、`httponly`、`samesite=lax`）。
- **`models.py`** — 集中的数据类型定义（`JobState`、`Summary`、`Chapter`、`TranscriptSegment`、`VideoMetadata`、`Style`、`Format`、`JobStatus` 字面量）。`JobState` v2 新增 `visitor_id` / `started_at` / `finished_at`。
- **`logging_setup.py`** — `setup_logging(log_dir)`：写 `<log_dir>/vidistill.log` + 控制台。模块级 `_CONFIGURED` 保证幂等（TestClient 反复 setup 也只会注册一次 handler）。
- **`exceptions.py`** — 全部领域错误继承 `VidistillError`，由 `main._install_exception_handlers` 统一映射到 HTTP 状态码：`QueueFullError → 429`、`JobNotFoundError → 404`、`JobNotCancellableError → 409`、`JobAccessDeniedError → 403`、`VideoFetchError → 422`，其它 500。
- **`adapters/video.py`** — yt-dlp 包装。`fetch_metadata` 取元数据做时长校验；`fetch_subtitle` 依次尝试 `zh` / `zh-CN` / `en` VTT；`download_audio` 两步走：yt-dlp 抓原始音频 → 显式 `ffmpeg` 调用重采样到 **16 kHz mono mp3**（Paraformer-realtime-v2 要求；`_resample_to_16k_mono` 拆出来方便测试 patch）。yt-dlp 错误信息会先 `_clean()` 去掉 ANSI 转义。
- **`adapters/asr.py`** — DashScope `Recognition`（paraformer-realtime-v2）。**realtime** 模型接收本地文件路径；batch 模型需要公网 HTTPS URL，我们没有。**别切回 batch**。
- **`adapters/llm.py`** — Qwen 通过 OpenAI SDK 走 DashScope 兼容模式端点，`response_format={"type": "json_object"}`。`prompts.py` 中的 prompt 约束 `short` 与 `chapters` 两种风格的 JSON schema。
- **`renderers/`** — `markdown.py` 是内容形状和文件名清洗（`sanitize_filename`）的 source of truth，其它地方都复用。`html.py` 把 markdown 结果套进中文字体友好的模板。`pdf.py` 在 `pipeline._get_renderer` 内**懒加载**（`from vidistill.renderers import pdf ...`），**绝对不要在模块顶部 import**，否则 Windows 没 GTK 时开发服务器直接挂。
- **`frontend/`** — 独立的 **React + TypeScript + TailwindCSS v4 + Vite** 前端工程（取代了原 `templates/index.html`，Jinja2 与 `templates/` 已删除）。`src/api.ts` 封装 7 个端点（相对路径、同源，cookie 自动带）；`src/components/` 的 `SubmitForm` / `MyJobs` / `FeedbackModal` + `src/hooks/useMyJobs.ts` 一一对应原来三段 Alpine 逻辑；全局字体用 **Fontsource 自托管的站酷快乐体**（`@fontsource/zcool-kuaile`，同源、不依赖 Google CDN，换字体只改 `src/index.css` 里的 `font-family`）；视觉用 Tailwind 工具类 + `src/index.css` 里少量渐变/动画 class。后端 `config.frontend_dist_dir` 默认指向 `<repo>/frontend/dist`（容器内 `/app/frontend/dist`）。

## 编辑前要知道的约束

- **音频必须是 16 kHz mono mp3** — ASR adapter 的硬性要求。改 `video.download_audio` 时务必保留显式 ffmpeg 重采样这一步。
- **后端单 worker 串行**（v2 spec 明确写出的非目标之一）。`queue_worker.worker_loop` 只跑一个协程，靠 `await queue.get()` 阻塞实现串行。**别为了"支持并发"改成多 worker**。
- **队列总上限 10**（运行 1 + 排队 9）— `routes.create_job` 用 `JobStore.count_active() >= 10` 作为闸口，超出抛 `QueueFullError`（429）。`asyncio.Queue(maxsize=9)` 在 `main.py` 的 lifespan 中创建，put 时若意外满了会回滚状态并报错。
- **视频时长上限 30 分钟**（`config.max_video_duration_seconds = 1800`）— 在 `pipeline.process_video` 拿到 yt-dlp 元数据后立即校验，下载前就拦掉。
- **匿名 visitor cookie**（不是登录）：`/my/jobs` 和 `DELETE /jobs/{id}` 用它做归属判断；`/jobs/{id}/download/{fmt}` 故意**不校验**，方便分享。改这个权限策略前先看 v2 spec 决策表。
- **重启策略：中断任务一律 fail，不恢复**。`mark_zombies_failed` 在启动时执行，是 v2 spec 明确的决定（防止重复消耗 API 额度）。别擅自加"断点续跑"。
- **过期清理：7 天**（`cleanup._RETENTION_DAYS`、`cleanup._INTERVAL_SECONDS = 3600`）。清理的是终态任务（done / failed / cancelled）的数据库记录和 `output_dir / job_id` 目录。
- **输出目录** — 默认 `/tmp/vidistill`（Linux / 容器内），测试中通过 `build_app(output_dir=tmp_path)` 覆盖。每个任务都有自己的 `{output_dir}/{job_id}/` 子目录。**`db_path` 默认就是 `output_dir / "vidistill.db"`**，所以 `build_app(output_dir=...)` 会一起搬迁数据库。
- **PDF 是 best-effort**。Windows 开发机没 GTK 时 PDF 渲染会失败，下载端点对 `fmt=pdf` 返回 404 并带清晰提示。**别擅自把它改成"整个任务 fail"**，需要先改 spec。
- **领域错误全部继承 `VidistillError`**（`exceptions.py`）。pipeline 捕获这些写到 `error` 字段；其它异常会被打成"未预期错误: …"。adapter 中要抛具名异常，别把底层库错误透出去。
- **前端是同源 SPA**：生产由 FastAPI 同源托管构建产物，dev 由 Vite 代理。**别重新引入 Jinja2**，也**别把前端改成跨域独立部署**——`visitor` cookie 是 `httponly` + `samesite=lax` 的同源 cookie，跨域会破坏 `/my/jobs` 和取消任务的归属判断。改部署形态前先看 2026-06-01 spec。

## 前端开发流程

- `frontend/` 是独立 Vite 工程；dev 时**后端 + 前端各跑一个进程**（见"常用命令"）。
- `vite.config.ts` 把 `/jobs`、`/my`、`/feedback` 代理到 **`http://127.0.0.1:8000`**（**故意用 127.0.0.1 而非 localhost**：Windows 上 Node 可能把 `localhost` 解析成 IPv6 `::1`，而 uvicorn 默认只监听 IPv4，会导致代理连不上后端）。
- dev 模式首屏 HTML 由 Vite 提供、**不经后端**，所以 `visitor` cookie 在**第一次 API 调用**时才种（生产模式首屏由后端返回、即时种）；两者最终归属一致，无功能影响。
- **换字体**：改 `frontend/src/index.css` 的 `font-family`（候选字体需先 `npm i @fontsource/<id>` 并在 `src/main.tsx` 加一行 `import`）。
- **没有前端测试框架**（首版有意不引入）。前端健康判据 = `npx tsc --noEmit` + `npm run build` 通过 + 对照 `docs/smoke-test-checklist.md` 人工冒烟。

## 部署

**同源单容器**：FastAPI 在 8000 端口同时提供 API 和前端 SPA。流程与分离前一致，脚本无需改动：

1. **本地**：`vidistill/` 下跑 `build_and_push.bat` —— `docker build` + push 到 `192.168.1.252:15000/vidistill:latest`。
2. **服务器**：跑 `deploy.sh` —— `docker pull` + `docker-compose down/up -d`。

- **镜像是多阶段 Dockerfile**：`node:20-slim` 阶段 `npm ci` + `npm run build` → 把 `frontend/dist` 复制进 Python 阶段的 `/app/frontend/dist`。**本地不需要先 `npm run build`**，`docker build` 会自己编译前端；但构建时**需要联网**装 npm 依赖。node 阶段是 build-time only，不进最终镜像，所以推送的镜像只比从前大 1~2MB（体积大头是 ffmpeg / WeasyPrint / 思源黑体）。
- `.dockerignore` 排除 `node_modules` / `frontend/dist`，避免把宿主（Windows）依赖拷进 Linux 构建上下文。
- `docker-compose.yml`：端口 `8000:8000`；env `DASHSCOPE_API_KEY`（服务器 `.env`）、`LOG_DIR=/var/log/vidistill`；卷 `./logs→/var/log/vidistill`、`./data→/tmp/vidistill`（SQLite db + 任务产物持久化）。**前端 dist 打进镜像、不走卷**。

## 测试布局

- `tests/unit/` — adapter 与 renderer 的单元测试，全部 mock；不需要网络也不需要 ffmpeg（重采样步骤被 patch）。覆盖 `cleanup` / `models` / `middleware` / `queue_worker` / `exceptions` / `store_sqlite` 等模块。
- `tests/integration/`
  - `test_pipeline.py`、`test_routes.py` — 用 `tests/fixtures/` 下的 JSON fixture（yt-dlp metadata、Paraformer 响应、Qwen 响应）在 adapter 边界 mock 后跑完整流程。
  - `test_concurrent_submit.py` — 并发提交时队列上限和位置计算的集成验证。
  - `test_my_jobs.py` — `/my/jobs` 接口 + visitor cookie 的端到端测试。
  - `test_restart_recovery.py` — 重启后僵尸任务清理的回归测试。
- `tests/conftest.py` 通过 autouse fixture 设置 `DASHSCOPE_API_KEY=test-key`，确保 `load_config()` 不会因为缺 key 报错。

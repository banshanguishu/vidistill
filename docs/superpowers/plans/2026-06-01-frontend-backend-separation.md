# 前后端分离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把单一 Jinja2 模板前端拆成独立的 React + TypeScript + Tailwind + Vite 工程，由 FastAPI 同源托管构建产物，功能 1:1 保留并做视觉焕新。

**Architecture:** 后端 7 个 JSON 端点、队列、单 worker、SQLite、cleanup、visitor cookie **完全不变**；只把 `GET /` 从渲染 Jinja2 改为托管 `frontend/dist/index.html`（无构建产物时返回兜底页），并挂载 `/assets` 静态目录。前端是单页 React 应用，三个现有 Alpine 逻辑映射为 `SubmitForm` / `MyJobs` / `FeedbackModal`，通过相对路径同源调用 API（cookie 自动携带）。

**Tech Stack:** 后端 FastAPI（不新增 Python 依赖，移除 jinja2）；前端 React 18 + TypeScript + Vite 6 + TailwindCSS v4 + `@radix-ui/react-dialog`。

---

## 实现约定（务必先读）

1. **后端任务用 pytest TDD**（先写失败测试 → 看红 → 实现 → 看绿 → 提交）。
2. **前端任务无测试框架**（spec 决定首版不引入 Vitest）。前端任务的"验证"步骤统一为：
   - `cd frontend && npx tsc --noEmit`（类型检查，期望 0 error）
   - `cd frontend && npm run build`（期望生成 `dist/`，无报错）
   - 功能对等的最终核对放在 Task 16 的人工冒烟。
3. **shadcn/ui 的落地方式**：不跑交互式 CLI，直接用 Tailwind v4 + Radix Dialog 原语手写组件（即 shadcn 的底层）。这是对 spec 第 2 节"组件=shadcn/ui"的可确定执行版实现，效果等价。
4. **Tailwind 用 v4**（`@tailwindcss/vite` 插件，CSS-first，无需 `tailwind.config.js` / `postcss.config.js`）。spec 第 4 节文件结构里列的 `tailwind.config.js` 在 v4 下不需要，以本计划为准。
5. **每个任务结束都提交**。后端在 `develop` 分支上工作（已是当前分支）。

---

## 文件结构

**后端（修改）**
- `src/vidistill/config.py` — 新增 `frontend_dist_dir` 字段
- `src/vidistill/main.py` — `build_app` 增加 `frontend_dist_dir` 覆盖参数 + 挂载 `/assets`
- `src/vidistill/routes.py` — `index()` 改为托管 SPA / 兜底页，移除 Jinja2
- `src/vidistill/templates/index.html` — Task 16 删除
- `pyproject.toml` — Task 16 移除 `jinja2`
- `tests/integration/test_routes.py` — 新增 SPA 托管相关测试
- `tests/unit/test_config.py` — 新增默认 dist 路径测试

**前端（新建，全部在 `frontend/` 下）**
- `frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig.json`、`frontend/index.html`、`frontend/.gitignore`
- `frontend/src/main.tsx`、`frontend/src/index.css`、`frontend/src/App.tsx`
- `frontend/src/types.ts`、`frontend/src/api.ts`
- `frontend/src/hooks/useMyJobs.ts`
- `frontend/src/components/SubmitForm.tsx`、`MyJobs.tsx`、`FeedbackModal.tsx`

**部署**
- `Dockerfile` — 改多阶段

---

# Phase A — 后端（TDD）

### Task 1: Config 新增 `frontend_dist_dir` + build_app 覆盖参数

**Files:**
- Modify: `src/vidistill/config.py`
- Modify: `src/vidistill/main.py:43-89`
- Test: `tests/unit/test_config.py`、`tests/integration/test_routes.py`

- [ ] **Step 1: 写失败测试（config 默认路径）**

在 `tests/unit/test_config.py` 末尾追加：

```python
def test_config_default_frontend_dist_points_to_repo_frontend(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from vidistill.config import load_config

    cfg = load_config()
    assert cfg.frontend_dist_dir.name == "dist"
    assert cfg.frontend_dist_dir.parent.name == "frontend"
```

在 `tests/integration/test_routes.py` 末尾追加：

```python
def test_build_app_accepts_frontend_dist_override(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from vidistill.main import build_app

    fe = tmp_path / "fe_dist"
    app = build_app(output_dir=tmp_path, frontend_dist_dir=fe)
    assert app.state.config.frontend_dist_dir == fe
```

- [ ] **Step 2: 运行测试看红**

Run: `poetry run pytest tests/unit/test_config.py::test_config_default_frontend_dist_points_to_repo_frontend tests/integration/test_routes.py::test_build_app_accepts_frontend_dist_override -v`
Expected: FAIL（`Config` 无 `frontend_dist_dir` / `build_app` 无该参数）

- [ ] **Step 3: 实现 config 字段**

在 `src/vidistill/config.py` 顶部 import 区下方加入工厂函数，并给 `Config` 增加字段：

```python
def _default_frontend_dist() -> Path:
    # config.py 位于 <repo>/src/vidistill/config.py → parents[2] 为仓库根
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"
```

在 `Config` 数据类中（与其它字段并列）加入：

```python
    frontend_dist_dir: Path = field(default_factory=_default_frontend_dist)
```

（`field` 已从 dataclasses 导入；`Path` 已导入。）

- [ ] **Step 4: 实现 build_app 覆盖参数 + 挂载占位**

修改 `src/vidistill/main.py` 的 `build_app` 签名与 config 处理：

```python
def build_app(
    config: Optional[Config] = None,
    output_dir: Optional[Path] = None,
    frontend_dist_dir: Optional[Path] = None,
) -> FastAPI:
    if config is None:
        config = load_config()
    if output_dir is not None:
        config = replace(
            config,
            output_dir=output_dir,
            log_dir=output_dir,
            db_path=output_dir / "vidistill.db",
        )
        config.output_dir.mkdir(parents=True, exist_ok=True)
    if frontend_dist_dir is not None:
        config = replace(config, frontend_dist_dir=frontend_dist_dir)
```

（函数体其余部分暂不动；`/assets` 挂载在 Task 4 加。）

- [ ] **Step 5: 运行测试看绿**

Run: `poetry run pytest tests/unit/test_config.py tests/integration/test_routes.py -v`
Expected: PASS（含原有用例）

- [ ] **Step 6: 提交**

```bash
git add src/vidistill/config.py src/vidistill/main.py tests/unit/test_config.py tests/integration/test_routes.py
git commit -m "feat(config): 新增 frontend_dist_dir + build_app 覆盖参数"
```

---

### Task 2: `GET /` 在无构建产物时返回兜底页（移除 Jinja2 渲染）

**Files:**
- Modify: `src/vidistill/routes.py:45-52`
- Test: `tests/integration/test_routes.py`

- [ ] **Step 1: 写失败测试**

在 `tests/integration/test_routes.py` 追加：

```python
def test_get_root_fallback_when_no_build(client):
    # client fixture 用 build_app(output_dir=tmp_path)，frontend_dist 指向真实仓库路径，
    # 测试环境通常未构建 → 返回兜底页。
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "vidistill" in r.text.lower()
```

> 注：若运行测试的开发机恰好已构建过 `frontend/dist`，本用例与 `test_get_root_returns_html` 都会拿到真实 SPA 的 `index.html`（其 `<title>` 含 `vidistill`），断言依旧成立。

- [ ] **Step 2: 运行看当前行为**

Run: `poetry run pytest tests/integration/test_routes.py::test_get_root_fallback_when_no_build -v`
Expected: 现状下 `index()` 仍走 Jinja2 模板（模板存在则 PASS，但我们要替换实现）。继续 Step 3。

- [ ] **Step 3: 替换 `index()` 实现**

在 `src/vidistill/routes.py`：删除 `get_templates()` 函数与 `Jinja2Templates` 相关 import；调整 responses import 为：

```python
from fastapi.responses import FileResponse, HTMLResponse
```

加入兜底页常量与新的 `index`：

```python
_FALLBACK_HTML = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>vidistill</title></head>
<body style="font-family: sans-serif; max-width: 640px; margin: 4rem auto; padding: 0 1.5rem; color:#333; line-height:1.6;">
<h1>vidistill</h1>
<p>前端尚未构建。</p>
<ul>
<li>生产 / 预览：<code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>，然后刷新本页。</li>
<li>本地开发：另开终端 <code>cd frontend &amp;&amp; npm run dev</code>，访问 <a href="http://localhost:5173">http://localhost:5173</a>（已配置代理到本服务）。</li>
</ul>
</body></html>"""


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    dist_index = request.app.state.config.frontend_dist_dir / "index.html"
    if dist_index.exists():
        return FileResponse(str(dist_index), media_type="text/html")
    return HTMLResponse(_FALLBACK_HTML)
```

（确认 `Jinja2Templates` 的 import 已删；`Path` 仍被 download 端点使用，保留。）

- [ ] **Step 4: 运行测试看绿**

Run: `poetry run pytest tests/integration/test_routes.py -v`
Expected: PASS（含 `test_get_root_returns_html` 与新增用例）

- [ ] **Step 5: 提交**

```bash
git add src/vidistill/routes.py tests/integration/test_routes.py
git commit -m "feat(routes): GET / 改为托管 SPA，无构建时返回兜底页"
```

---

### Task 3: `GET /` 在有构建产物时返回 `dist/index.html`

**Files:**
- Test: `tests/integration/test_routes.py`
- （实现已在 Task 2 完成，本任务补测试验证 dist 分支）

- [ ] **Step 1: 写失败测试**

```python
def test_get_root_serves_dist_index_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from fastapi.testclient import TestClient
    from vidistill.main import build_app

    fe = tmp_path / "fe_dist"
    fe.mkdir(parents=True)
    (fe / "index.html").write_text(
        "<!doctype html><title>vidistill</title><div id=root>BUILT_SPA_MARKER</div>",
        encoding="utf-8",
    )
    app = build_app(output_dir=tmp_path, frontend_dist_dir=fe)
    with TestClient(app) as c:
        r = c.get("/")
    assert r.status_code == 200
    assert "BUILT_SPA_MARKER" in r.text
```

- [ ] **Step 2: 运行看绿**

Run: `poetry run pytest tests/integration/test_routes.py::test_get_root_serves_dist_index_when_present -v`
Expected: PASS（Task 2 的实现已支持该分支）

- [ ] **Step 3: 提交**

```bash
git add tests/integration/test_routes.py
git commit -m "test(routes): 覆盖 GET / 托管已构建 dist 的分支"
```

---

### Task 4: 挂载 `/assets` 静态目录

**Files:**
- Modify: `src/vidistill/main.py`（`build_app` 末尾、`return app` 之前）
- Test: `tests/integration/test_routes.py`

- [ ] **Step 1: 写失败测试**

```python
def test_assets_served_when_dist_present(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from fastapi.testclient import TestClient
    from vidistill.main import build_app

    fe = tmp_path / "fe_dist"
    (fe / "assets").mkdir(parents=True)
    (fe / "assets" / "app-abc123.js").write_text("console.log('hi')", encoding="utf-8")
    app = build_app(output_dir=tmp_path, frontend_dist_dir=fe)
    with TestClient(app) as c:
        r = c.get("/assets/app-abc123.js")
    assert r.status_code == 200
    assert "console.log" in r.text
```

- [ ] **Step 2: 运行看红**

Run: `poetry run pytest tests/integration/test_routes.py::test_assets_served_when_dist_present -v`
Expected: FAIL（404，未挂载 `/assets`）

- [ ] **Step 3: 实现挂载**

在 `src/vidistill/main.py` 顶部 import 区加：

```python
from fastapi.staticfiles import StaticFiles
```

在 `build_app` 中 `app.include_router(router)` 之后、`return app` 之前加：

```python
    assets_dir = config.frontend_dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
```

- [ ] **Step 4: 运行测试看绿**

Run: `poetry run pytest tests/integration/test_routes.py -v`
Expected: PASS

- [ ] **Step 5: 跑一遍全部后端测试确认无回归**

Run: `poetry run pytest -q`
Expected: 全绿

- [ ] **Step 6: 提交**

```bash
git add src/vidistill/main.py tests/integration/test_routes.py
git commit -m "feat(main): dist 存在时挂载 /assets 静态目录"
```

---

# Phase B — 前端脚手架

### Task 5: Vite + React + TS 脚手架可构建

**Files:**
- Create: `frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig.json`、`frontend/index.html`、`frontend/.gitignore`
- Create: `frontend/src/main.tsx`、`frontend/src/index.css`、`frontend/src/App.tsx`

- [ ] **Step 1: 写 `frontend/package.json`**

```json
{
  "name": "vidistill-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "typecheck": "tsc --noEmit",
    "preview": "vite preview"
  },
  "dependencies": {
    "@radix-ui/react-dialog": "^1.1.4",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.6.3",
    "vite": "^6.0.7"
  }
}
```

- [ ] **Step 2: 写 `frontend/vite.config.ts`**

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/jobs': 'http://localhost:8000',
      '/my': 'http://localhost:8000',
      '/feedback': 'http://localhost:8000',
    },
  },
  build: { outDir: 'dist' },
})
```

- [ ] **Step 3: 写 `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "types": ["vite/client"]
  },
  "include": ["src"]
}
```

- [ ] **Step 4: 写 `frontend/index.html`**

```html
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>vidistill — 视频内容 AI 总结</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: 写 `frontend/.gitignore`**

```gitignore
node_modules
dist
*.local
.DS_Store
```

- [ ] **Step 6: 写 `frontend/src/index.css`**

```css
@import "tailwindcss";
```

- [ ] **Step 7: 写 `frontend/src/main.tsx`**

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 8: 写占位 `frontend/src/App.tsx`**

```tsx
export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 p-10 text-gray-800">
      <h1 className="text-3xl font-bold tracking-tight text-blue-600">vidistill</h1>
      <p className="mt-2 text-gray-500">脚手架就绪</p>
    </div>
  )
}
```

- [ ] **Step 9: 安装依赖并构建**

Run: `cd frontend && npm install && npm run build`
Expected: 生成 `frontend/dist/`，无报错；`dist/index.html` 含 `vidistill`，`dist/assets/` 下有 hash 命名的 JS/CSS。

- [ ] **Step 10: 提交**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/tsconfig.json frontend/index.html frontend/.gitignore frontend/src/main.tsx frontend/src/index.css frontend/src/App.tsx
git commit -m "feat(frontend): Vite+React+TS+Tailwind v4 脚手架"
```

---

### Task 6: 类型与 API client

**Files:**
- Create: `frontend/src/types.ts`、`frontend/src/api.ts`

- [ ] **Step 1: 写 `frontend/src/types.ts`**

```ts
export type Style = 'short' | 'chapters'

export type JobStatus =
  | 'queued' | 'pending' | 'fetching' | 'transcribing'
  | 'summarizing' | 'rendering' | 'done' | 'failed' | 'cancelled'

export type Format = 'md' | 'html' | 'pdf'

export interface CreateJobResponse {
  job_id: string
  queue_position: number
}

export interface JobStatusResponse {
  job_id: string
  status: JobStatus
  progress: number
  queue_position: number | null
  error: string | null
  video_title: string
  available_formats: Format[]
}

export interface MyJob {
  job_id: string
  video_title: string
  status: JobStatus
  progress: number
  queue_position: number | null
  created_at: string
  available_formats: Format[]
}

export interface MyJobsResponse {
  jobs: MyJob[]
  system: { active_count: number; active_max: number; queue_full: boolean }
}
```

- [ ] **Step 2: 写 `frontend/src/api.ts`**

```ts
import type {
  CreateJobResponse, JobStatusResponse, MyJobsResponse, Style,
} from './types'

async function parseError(resp: Response): Promise<string> {
  try {
    const data = await resp.json()
    return data.detail || `错误 ${resp.status}`
  } catch {
    return `错误 ${resp.status}`
  }
}

export async function createJob(url: string, style: Style): Promise<CreateJobResponse> {
  const resp = await fetch('/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, style }),
  })
  if (!resp.ok) throw new Error(await parseError(resp))
  return resp.json()
}

export async function getJob(jobId: string): Promise<JobStatusResponse> {
  const resp = await fetch(`/jobs/${jobId}`)
  if (!resp.ok) throw new Error(await parseError(resp))
  return resp.json()
}

export async function cancelJob(jobId: string): Promise<void> {
  await fetch(`/jobs/${jobId}`, { method: 'DELETE' })
}

export async function getMyJobs(): Promise<MyJobsResponse> {
  const resp = await fetch('/my/jobs')
  if (!resp.ok) throw new Error(await parseError(resp))
  return resp.json()
}

export async function sendFeedback(content: string, contact: string | null): Promise<void> {
  const resp = await fetch('/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, contact }),
  })
  if (!resp.ok) throw new Error(await parseError(resp))
}

export function downloadUrl(jobId: string, fmt: string): string {
  return `/jobs/${jobId}/download/${fmt}`
}
```

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 error

- [ ] **Step 4: 提交**

```bash
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "feat(frontend): API 类型定义与 client 封装"
```

---

# Phase C — 功能对等（映射现有 Alpine 逻辑）

### Task 7: SubmitForm 组件（表单 + 轮询 + 状态机）

**Files:**
- Create: `frontend/src/components/SubmitForm.tsx`

对应现有 `vidistillApp()`。必须保留：6 个阶段（idle / submitting / polling / ready / error_input / error_processing）、2s 轮询、阶段中文文案、队列位置、进度条、`beforeunload` 提醒、PDF 不可用禁用按钮、done/failed/cancelled 处理、重试与重置。

- [ ] **Step 1: 写 `frontend/src/components/SubmitForm.tsx`**

```tsx
import { useEffect, useRef, useState } from 'react'
import type { Format, JobStatus, Style } from '../types'
import { createJob, downloadUrl, getJob } from '../api'

type Phase = 'idle' | 'submitting' | 'polling' | 'ready' | 'error_input' | 'error_processing'

const STATUS_LABELS: Record<string, (pos: number | null) => string> = {
  queued: (pos) => (pos ? `正在排队（第 ${pos} 位）...` : '正在排队...'),
  pending: () => '即将开始...',
  fetching: () => '正在抓取视频信息...',
  transcribing: () => '正在转写音频...',
  summarizing: () => '正在生成摘要...',
  rendering: () => '正在渲染输出...',
}

const STYLE_OPTIONS = [
  ['short', '短摘要', '3-5 句核心要点 + 5-10 条 bullet。适合快速判断"这视频值不值得看"。'],
  ['chapters', '章节笔记', '按视频章节切分，每章一段总结 + bullet，带时间戳。适合反复查阅。'],
] as const

export function SubmitForm({ onJobCreated }: { onJobCreated?: () => void }) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [url, setUrl] = useState('')
  const [style, setStyle] = useState<Style>('chapters')
  const [jobId, setJobId] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState<JobStatus>('pending')
  const [queuePosition, setQueuePosition] = useState<number | null>(null)
  const [videoTitle, setVideoTitle] = useState('')
  const [availableFormats, setAvailableFormats] = useState<Format[]>([])
  const [errorMessage, setErrorMessage] = useState('')
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (phase === 'submitting' || phase === 'polling') {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [phase])

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current) }, [])

  const stopPolling = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
  }

  const reset = () => {
    stopPolling()
    setPhase('idle'); setUrl(''); setJobId(null); setProgress(0)
    setErrorMessage(''); setVideoTitle(''); setAvailableFormats([])
  }

  const poll = async (id: string) => {
    try {
      const data = await getJob(id)
      setStatus(data.status)
      setProgress(data.progress)
      setVideoTitle(data.video_title || '')
      setAvailableFormats(data.available_formats || [])
      setQueuePosition(data.queue_position)
      if (data.status === 'done') { stopPolling(); setPhase('ready') }
      else if (data.status === 'failed') { stopPolling(); setErrorMessage(data.error || '处理失败'); setPhase('error_processing') }
      else if (data.status === 'cancelled') { stopPolling(); reset() }
    } catch {
      // 瞬时网络错误，继续轮询
    }
  }

  const startPolling = (id: string) => {
    timerRef.current = window.setInterval(() => poll(id), 2000)
    poll(id)
  }

  const submit = async () => {
    setPhase('submitting'); setErrorMessage('')
    try {
      const data = await createJob(url, style)
      setJobId(data.job_id)
      setQueuePosition(data.queue_position)
      setPhase('polling')
      onJobCreated?.()
      startPolling(data.job_id)
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : '提交失败')
      setPhase('error_input')
    }
  }

  const statusLabel = () => (STATUS_LABELS[status] ? STATUS_LABELS[status](queuePosition) : status)

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      {(phase === 'idle' || phase === 'submitting' || phase === 'error_input') && (
        <div>
          <label htmlFor="url" className="block font-semibold mb-1">视频链接</label>
          <input
            id="url" type="url" value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=... 或 https://www.bilibili.com/video/..."
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-sm text-gray-500 mt-1">支持 YouTube、Bilibili 等 yt-dlp 兼容平台。视频时长不超过 30 分钟。</p>

          <label className="block font-semibold mt-4 mb-2">总结形态</label>
          <div className="flex flex-wrap gap-3">
            {STYLE_OPTIONS.map(([val, title, desc]) => (
              <label key={val}
                className={`flex-1 min-w-[240px] cursor-pointer rounded-md border p-3 transition ${style === val ? 'border-blue-500 bg-blue-50' : 'border-gray-300'}`}>
                <input type="radio" name="style" value={val} checked={style === val} onChange={() => setStyle(val)} className="hidden" />
                <strong className="block">{title}</strong>
                <span className="text-sm text-gray-600">{desc}</span>
              </label>
            ))}
          </div>

          <button onClick={submit} disabled={phase === 'submitting' || !url}
            className="mt-6 w-full rounded-md bg-blue-600 py-3 font-semibold text-white transition hover:bg-blue-700 disabled:bg-gray-400">
            {phase === 'submitting' ? '提交中...' : '开始生成'}
          </button>
          {phase === 'error_input' && (
            <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-red-700">{errorMessage}</div>
          )}
        </div>
      )}

      {phase === 'polling' && (
        <div>
          <div className="font-semibold">{videoTitle || '处理中'}</div>
          <div className="mt-2 flex items-center gap-2 text-sm text-gray-600">
            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-200 border-t-blue-600" />
            <span>{statusLabel()}</span>
          </div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded bg-gray-200">
            <div className="h-full bg-blue-600 transition-all" style={{ width: `${progress}%` }} />
          </div>
          <div className="mt-1 text-sm text-gray-500">{progress}%</div>
        </div>
      )}

      {phase === 'ready' && jobId && (
        <div>
          <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-green-700">总结完成！</div>
          <div className="mt-2 font-semibold">{videoTitle}</div>
          <div className="mt-3 flex flex-wrap gap-2">
            <a className="flex-1 min-w-[140px] rounded-md bg-green-700 px-4 py-2 text-center font-semibold text-white hover:bg-green-800" href={downloadUrl(jobId, 'md')} download>下载 Markdown</a>
            <a className="flex-1 min-w-[140px] rounded-md bg-green-700 px-4 py-2 text-center font-semibold text-white hover:bg-green-800" href={downloadUrl(jobId, 'html')} download>下载 HTML</a>
            {availableFormats.includes('pdf') ? (
              <a className="flex-1 min-w-[140px] rounded-md bg-green-700 px-4 py-2 text-center font-semibold text-white hover:bg-green-800" href={downloadUrl(jobId, 'pdf')} download>下载 PDF</a>
            ) : (
              <button disabled title="PDF 需在服务器环境（含 GTK/字体库）生成；本地 Windows 环境无法生成。Docker 部署后可用。"
                className="flex-1 min-w-[140px] cursor-not-allowed rounded-md bg-gray-300 px-4 py-2 text-center font-semibold text-gray-600">下载 PDF（不可用）</button>
            )}
          </div>
          <button onClick={reset} className="mt-4 rounded-md bg-gray-600 px-4 py-2 text-white hover:bg-gray-700">再来一个</button>
        </div>
      )}

      {phase === 'error_processing' && (
        <div>
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-red-700">{errorMessage}</div>
          <div className="mt-4 flex gap-2">
            <button onClick={() => { setErrorMessage(''); submit() }} className="rounded-md bg-gray-600 px-4 py-2 text-white hover:bg-gray-700">重试</button>
            <button onClick={reset} className="rounded-md bg-gray-600 px-4 py-2 text-white hover:bg-gray-700">换一个视频</button>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 error

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/SubmitForm.tsx
git commit -m "feat(frontend): SubmitForm 表单+轮询+状态机"
```

---

### Task 8: useMyJobs hook + MyJobs 组件

**Files:**
- Create: `frontend/src/hooks/useMyJobs.ts`、`frontend/src/components/MyJobs.tsx`

对应现有 `myJobsApp()`。必须保留：3s 轮询、无活动任务时停止轮询、`poke()` 提交后立即刷新并重启轮询、状态 badge 语义色、`queued` 可取消、`done` 显示 MD/HTML/PDF（按 `available_formats`）、空列表 cookie 提示、队列指示器。

- [ ] **Step 1: 写 `frontend/src/hooks/useMyJobs.ts`**

```ts
import { useCallback, useEffect, useRef, useState } from 'react'
import type { MyJob } from '../types'
import { getMyJobs } from '../api'

const TERMINAL = ['done', 'failed', 'cancelled']
const isTerminal = (s: string) => TERMINAL.includes(s)

export function useMyJobs() {
  const [jobs, setJobs] = useState<MyJob[]>([])
  const [activeCount, setActiveCount] = useState(0)
  const [queueFull, setQueueFull] = useState(false)
  const timerRef = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await getMyJobs()
      setJobs(data.jobs || [])
      setActiveCount(data.system.active_count)
      setQueueFull(data.system.queue_full)
      const hasActive = data.system.active_count > 0
      const hasNonTerminal = (data.jobs || []).some((j) => !isTerminal(j.status))
      if (!hasActive && !hasNonTerminal && timerRef.current) {
        clearInterval(timerRef.current); timerRef.current = null
      }
    } catch {
      // 瞬时错误，忽略
    }
  }, [])

  const ensurePolling = useCallback(() => {
    if (!timerRef.current) timerRef.current = window.setInterval(refresh, 3000)
  }, [refresh])

  const poke = useCallback(() => { refresh(); ensurePolling() }, [refresh, ensurePolling])

  useEffect(() => {
    refresh(); ensurePolling()
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [refresh, ensurePolling])

  return { jobs, activeCount, queueFull, refresh, poke }
}
```

- [ ] **Step 2: 写 `frontend/src/components/MyJobs.tsx`**

```tsx
import type { MyJob } from '../types'
import { downloadUrl } from '../api'

const TERMINAL = ['done', 'failed', 'cancelled']
const isTerminal = (s: string) => TERMINAL.includes(s)

function statusLabel(j: MyJob): string {
  switch (j.status) {
    case 'queued': return j.queue_position ? `排队中 #${j.queue_position}` : '排队中'
    case 'pending': return '即将开始'
    case 'fetching':
    case 'transcribing':
    case 'summarizing':
    case 'rendering': return `处理中 ${j.progress}%`
    case 'done': return '已完成'
    case 'failed': return '失败'
    case 'cancelled': return '已取消'
    default: return j.status
  }
}

function badgeClass(status: string): string {
  switch (status) {
    case 'queued': return 'bg-blue-100 text-blue-700'
    case 'done': return 'bg-green-100 text-green-700'
    case 'failed': return 'bg-red-100 text-red-700'
    case 'cancelled': return 'bg-gray-100 text-gray-500'
    default: return 'bg-orange-100 text-orange-700'
  }
}

interface Props {
  jobs: MyJob[]
  activeCount: number
  queueFull: boolean
  onCancel: (jobId: string) => void
}

export function MyJobs({ jobs, activeCount, queueFull, onCancel }: Props) {
  return (
    <div className="flex max-h-[500px] flex-col overflow-hidden rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold">我的任务（最近 7 天）</h2>

      {queueFull && (
        <div className="mt-2 self-start rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-sm text-red-700">⚠ 当前队列已满（10 / 10），请稍后再提交</div>
      )}
      {!queueFull && activeCount > 0 && (
        <div className="mt-2 self-start rounded-md border border-blue-200 bg-blue-50 px-3 py-1.5 text-sm text-blue-700">✓ 当前队列：{activeCount} / 10</div>
      )}

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto">
        {jobs.length > 0 ? (
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="border-b-2 border-gray-200 py-2 pr-2">标题</th>
                <th className="w-[120px] border-b-2 border-gray-200 py-2 pr-2">状态</th>
                <th className="w-[200px] border-b-2 border-gray-200 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.job_id} className="hover:bg-gray-50">
                  <td className="break-words border-b border-gray-100 py-3 pr-2">{j.video_title || j.job_id}</td>
                  <td className="whitespace-nowrap border-b border-gray-100 py-3 pr-2">
                    <span title={j.status === 'failed' ? '处理失败' : ''}
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${badgeClass(j.status)}`}>
                      {!isTerminal(j.status) && (
                        <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border-[1.5px] border-current border-t-transparent opacity-70" />
                      )}
                      {statusLabel(j)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap border-b border-gray-100 py-3">
                    {j.status === 'queued' && (
                      <button onClick={() => onCancel(j.job_id)}
                        className="rounded-md border border-red-500 px-3 py-1.5 text-xs font-medium text-red-500 transition hover:bg-red-500 hover:text-white">取消</button>
                    )}
                    {j.status === 'done' && (
                      <span className="flex flex-wrap gap-1">
                        <a href={downloadUrl(j.job_id, 'md')} download className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700">MD</a>
                        <a href={downloadUrl(j.job_id, 'html')} download className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700">HTML</a>
                        {j.available_formats.includes('pdf') && (
                          <a href={downloadUrl(j.job_id, 'pdf')} download className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700">PDF</a>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="mt-2 text-sm text-gray-500">暂无任务。如果之前提交过却看不到，请检查浏览器是否启用 Cookie。</div>
        )}
      </div>
    </div>
  )
}
```

> 说明：`/my/jobs` 响应不含 `error` 字段，原前端 `j.error` 在此处恒为 undefined、实际只显示"处理失败"，本实现与之一致，非回归。

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 error

- [ ] **Step 4: 提交**

```bash
git add frontend/src/hooks/useMyJobs.ts frontend/src/components/MyJobs.tsx
git commit -m "feat(frontend): useMyJobs hook + MyJobs 列表组件"
```

---

### Task 9: FeedbackModal 组件（Radix Dialog）

**Files:**
- Create: `frontend/src/components/FeedbackModal.tsx`

对应现有 `feedbackApp()`。必须保留：打开重置、必填内容、选填联系方式、提交、成功后 2s 自动关闭、错误展示、Esc/点遮罩关闭（Radix 自带）。

- [ ] **Step 1: 写 `frontend/src/components/FeedbackModal.tsx`**

```tsx
import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { sendFeedback } from '../api'

export function FeedbackModal() {
  const [open, setOpen] = useState(false)
  const [content, setContent] = useState('')
  const [contact, setContact] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')

  const onOpenChange = (o: boolean) => {
    setOpen(o)
    if (o) { setContent(''); setContact(''); setSubmitted(false); setError('') }
  }

  const submit = async () => {
    if (!content.trim()) return
    setSubmitting(true); setError('')
    try {
      await sendFeedback(content.trim(), contact.trim() || null)
      setSubmitted(true)
      setTimeout(() => setOpen(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Trigger asChild>
        <button className="font-medium text-blue-600 hover:underline">💬 点此反馈</button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[90vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          {!submitted ? (
            <>
              <Dialog.Title className="mb-3 text-lg font-semibold">反馈问题或建议</Dialog.Title>
              <Dialog.Description className="sr-only">提交你遇到的问题或建议</Dialog.Description>
              <label className="mb-1 mt-3 block text-sm font-medium">问题描述 <span className="text-red-600">*</span></label>
              <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder="请描述你遇到的问题或想提的建议..."
                className="min-h-[120px] w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
              <label className="mb-1 mt-3 block text-sm font-medium">联系方式（选填）</label>
              <input type="text" value={contact} onChange={(e) => setContact(e.target.value)} placeholder="邮箱或微信号，方便我回复你"
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
              {error && <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
              <div className="mt-5 flex justify-end gap-3">
                <Dialog.Close asChild>
                  <button className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">取消</button>
                </Dialog.Close>
                <button onClick={submit} disabled={!content.trim() || submitting}
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-400">
                  {submitting ? '提交中...' : '提交'}
                </button>
              </div>
            </>
          ) : (
            <div className="py-8 text-center text-lg font-medium text-green-700">✓ 已收到反馈，感谢！</div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 error

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/FeedbackModal.tsx
git commit -m "feat(frontend): FeedbackModal 反馈弹窗（Radix Dialog）"
```

---

### Task 10: App 组装布局

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 重写 `frontend/src/App.tsx`**

```tsx
import { cancelJob } from './api'
import { SubmitForm } from './components/SubmitForm'
import { MyJobs } from './components/MyJobs'
import { FeedbackModal } from './components/FeedbackModal'
import { useMyJobs } from './hooks/useMyJobs'

export default function App() {
  const my = useMyJobs()
  return (
    <div className="min-h-screen bg-gray-50 text-gray-800">
      <div className="mx-auto max-w-3xl px-6 py-10">
        <header className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight">vidistill</h1>
          <p className="mt-1 text-gray-500">粘贴视频链接 → AI 总结 → 下载</p>
          <p className="mt-1 flex items-center gap-1 text-sm text-gray-400">
            <span>使用中遇到问题或想提建议？</span>
            <FeedbackModal />
          </p>
        </header>

        <SubmitForm onJobCreated={my.poke} />

        <div className="mt-6">
          <MyJobs
            jobs={my.jobs}
            activeCount={my.activeCount}
            queueFull={my.queueFull}
            onCancel={async (id) => { await cancelJob(id); my.refresh() }}
          />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 类型检查 + 构建**

Run: `cd frontend && npm run build`
Expected: 0 error，`dist/` 生成成功

- [ ] **Step 3: 提交**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): App 组装布局，串联表单/任务列表/反馈"
```

---

# Phase D — 联调、部署、清理

### Task 11: 本地联调（dev proxy 验证）

**Files:** 无（验证步骤）

- [ ] **Step 1: 启动后端**

Run（终端 A）: `poetry run uvicorn vidistill.main:app --reload --port 8000`
Expected: 启动成功，监听 8000

- [ ] **Step 2: 启动前端 dev server**

Run（终端 B）: `cd frontend && npm run dev`
Expected: Vite 监听 5173

- [ ] **Step 3: 浏览器验证代理与基本交互**

打开 `http://localhost:5173`：
- 页面渲染正常（标题、表单、"我的任务"卡片、反馈链接）。
- 打开开发者工具 Network，提交一个无效 URL（如 `not-a-url`）→ 应收到 422 且表单内显示错误（验证 `/jobs` 代理 + 错误展示）。
- 确认刷新后 `document.cookie` 不可见（httponly 正常），且 `/my/jobs` 请求带上了 cookie（第二次请求起 Request Headers 含 `Cookie: visitor_id=...`）。
- 打开反馈弹窗，提交一条 → 成功提示 2s 后自动关闭（验证 `/feedback` 代理）。

> 真实视频的端到端在 Task 16 冒烟里跑（需要 `DASHSCOPE_API_KEY` 与网络）。

- [ ] **Step 4: 无需提交（纯验证）**

---

### Task 12: Dockerfile 多阶段构建

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: 重写 `Dockerfile`**

```dockerfile
# --- 前端构建阶段 ---
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 后端运行阶段 ---
FROM python:3.12-slim-bookworm

# System deps: ffmpeg for audio extraction, WeasyPrint runtime libs, fonts for CJK PDF,
# sqlite3 CLI for ad-hoc feedback/jobs queries via `docker exec`
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    sqlite3 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

ENV POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY src ./src
RUN poetry install --only-root

# 前端构建产物（与 config._default_frontend_dist 的 /app/frontend/dist 对齐）
COPY --from=frontend /fe/dist ./frontend/dist

RUN mkdir -p /tmp/vidistill

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src
EXPOSE 8000

CMD ["uvicorn", "vidistill.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: 构建镜像**

Run: `docker build -t vidistill .`
Expected: 构建成功（前端阶段产出 dist，后端阶段复制到 `/app/frontend/dist`）

- [ ] **Step 3: 运行并验证 SPA 被托管**

Run: `docker run -d -p 8000:8000 --env-file .env --name vidistill-test vidistill`
然后浏览器访问 `http://localhost:8000`：
- 返回真实 SPA（非兜底页），页面正常渲染。
- 静态资源 `GET /assets/...` 返回 200。

清理：`docker rm -f vidistill-test`

> Windows 开发机若本地不便跑 docker，本任务可在部署机执行；但 `npm run build` 与后端 `pytest` 必须先在本地通过。

- [ ] **Step 4: 提交**

```bash
git add Dockerfile
git commit -m "build: Dockerfile 多阶段构建，托管前端 dist"
```

---

### Task 13: 清理 Jinja2 模板与依赖 + 全量回归 + 人工冒烟

**Files:**
- Delete: `src/vidistill/templates/index.html`（及空的 `templates/` 目录）
- Modify: `pyproject.toml`（移除 `jinja2`）

- [ ] **Step 1: 删除旧模板**

```bash
git rm src/vidistill/templates/index.html
```
（若 `templates/` 目录已空，git 会自动不再跟踪。）

- [ ] **Step 2: 移除 jinja2 依赖**

编辑 `pyproject.toml`，删除这一行：
```toml
jinja2 = "^3.1"
```

- [ ] **Step 3: 更新锁文件并安装**

Run: `poetry lock --no-update && poetry install`
Expected: 成功；jinja2 若无其它依赖引用则被移除（被传递依赖保留也无妨）。

- [ ] **Step 4: 全量后端测试**

Run: `poetry run pytest -q`
Expected: 全绿（含 `test_get_root_returns_html`、新增 SPA 用例）

- [ ] **Step 5: 前端最终构建**

Run: `cd frontend && npm run build`
Expected: 0 error

- [ ] **Step 6: 人工冒烟（对照 `docs/smoke-test-checklist.md`）**

用 docker 镜像或 `uvicorn`（已构建 dist）逐条核对功能对等，重点：
- 提交真实视频 → 轮询进度 → 完成 → 下载 MD / HTML（PDF 视环境）。
- 队列位置展示；同时提交多个看排队。
- 取消 queued 任务。
- "我的任务"列表状态/徽章/下载/取消、空列表提示。
- 反馈提交成功。
- 提交无效 URL → 422 错误展示；超 30 分钟视频 → 422 提示；队列满 → 429 提示。
- 处理中关闭标签页 → 浏览器拦截确认。

- [ ] **Step 7: 提交**

```bash
git add pyproject.toml poetry.lock
git commit -m "chore: 移除 Jinja2 模板与依赖，前端已迁移至 React SPA"
```

---

## 自审：Spec 覆盖对照

| Spec 要求 | 对应任务 |
|---|---|
| §5.1 `GET /` 托管 SPA + 兜底页 | Task 2、3 |
| §5.2 挂载 `/assets` | Task 4 |
| §5.3 后端 API/队列/cookie 不变 | 全程不触碰，Task 4/13 跑全量回归确认 |
| §6 三个 Alpine 逻辑 1:1 映射 + 行为清单 | Task 7（SubmitForm）、8（MyJobs）、9（FeedbackModal）、10（App） |
| §7 dev proxy | Task 5（vite.config）、Task 11（验证） |
| §8 多阶段 Docker | Task 12 |
| §9 视觉方向（蓝主色/克制现代/响应式） | Task 7–10 的 Tailwind 实现 |
| §10 验证策略（后端绿 + tsc/build + 冒烟） | 各任务验证步骤 + Task 13 |
| 移除 jinja2 + 删模板 | Task 13 |
| `frontend_dist_dir` 配置 + build_app 覆盖（测试可注入） | Task 1 |

**占位符扫描**：无 TBD/TODO；所有代码步骤给出完整代码。
**类型一致性**：`Style`/`JobStatus`/`Format`/`MyJob` 等类型在 `types.ts` 定义，`api.ts`、组件、hook 引用一致；`downloadUrl(jobId, fmt)`、`createJob(url, style)`、`getMyJobs()`、`useMyJobs()` 返回的 `{jobs, activeCount, queueFull, refresh, poke}` 在 App/MyJobs 使用一致。

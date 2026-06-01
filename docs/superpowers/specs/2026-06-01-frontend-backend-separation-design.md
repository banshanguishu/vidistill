# vidistill 前后端分离设计文档

- **创建日期**：2026-06-01
- **作者**：libo.gou@dreambigcareer.com
- **状态**：设计已确认，待实现
- **前置文档**：
  - [2026-05-15-vidistill-v2-concurrent-design.md](./2026-05-15-vidistill-v2-concurrent-design.md)（v2 多人共用设计，当前后端架构）
  - [2026-05-12-vidistill-design.md](./2026-05-12-vidistill-design.md)（v1 原始设计）

## 1. 背景与目标

当前前端是单个 Jinja2 模板 `templates/index.html`（内联 CSS + Alpine.js CDN + 原生 JS），由 FastAPI 在 `GET /` 直接渲染。界面观感较差，且模板与后端耦合（Jinja2 渲染），定制 UI、日后加新功能时前端不好施展。

本次升级把前端拆成独立的现代前端工程（React + TypeScript + TailwindCSS + Vite），后端退化为纯 JSON API + 静态托管，从而让 UI 定制和后续前端功能开发更顺手。**硬约束：不破坏任何现有功能。**

> **本设计有意推翻 v2 spec 的一条决策**：v2 决策表中"前端框架 = 继续 Jinja2 + 原生 JS"、非目标中"不引入 Vue / Tailwind / SPA 框架"。本文档就前端栈这一点取代 v2；后端架构（单 worker / 队列 / SQLite / cookie / 清理 / 重启策略）一律沿用 v2，不变。

### 目标

- 前端独立成 React + TS + Tailwind + Vite 工程，组件化、可维护、便于后续加功能。
- 视觉焕新：功能全部保留，用 Tailwind 重做一套更现代、克制的界面。
- 后端 7 个 JSON 端点、队列、worker、SQLite、cleanup、visitor cookie **完全不变**。
- 仍保持**单 Docker、单进程、同源**部署。
- 现有后端测试全部保持绿。

### 非目标（明确不做）

- ❌ 改动后端架构（单 worker 串行 / 队列上限 10 / SQLite / 7 天清理 / 重启 fail 全不变）。
- ❌ 登录、账号、鉴权（继续匿名 visitor cookie）。
- ❌ 前端路由库（仅单页，不需要 React Router）。
- ❌ 前端状态管理库（Redux / Zustand 等，`useState` + 自定义 hook 足够）。
- ❌ 跨域 / 独立前端部署（坚持同源单容器，cookie / CORS 不动）。
- ❌ WebSocket 实时推送（继续轮询，间隔与现状一致）。
- ❌ 前端 CI（项目目前没有 CI；要加另议）。
- ❌ 后期反复调 UI——视觉方向一次定稿（用户明确不希望后期再调）。

## 2. 关键决策摘要

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 前端栈 | React + TypeScript + TailwindCSS + Vite | 用户指定 |
| 组件/样式 | Tailwind + **shadcn/ui** | Radix 无样式组件复制进项目，开箱现代+可访问，便于后续加功能 |
| 部署 | FastAPI 托管 Vite 构建产物，**同源单容器** | cookie / CORS 完全不用改，最贴合现有单 Docker 部署，"不破坏功能"风险最低 |
| 视觉范围 | 迁移同时做视觉焕新（盲盒，作者全权决定） | 用户出发点即"界面太丑" |
| 构建产物入镜像 | **多阶段 Docker**（node 构建 → 复制 dist 进 Python 镜像） | dist 不进 git，可复现 |
| 仓库结构 | monorepo，`frontend/` 独立目录 | 前后端同仓，部署简单 |
| 后端 | 7 个 API 端点 + 队列 + worker + SQLite + cleanup + cookie **不变** | 不破坏现有功能 |

## 3. 技术栈变更

**前端新增**：

| 项 | 选型 |
|----|------|
| 框架 | React 18 + TypeScript |
| 构建 | Vite |
| 样式 | TailwindCSS |
| 组件 | shadcn/ui（Radix primitives，复制进项目） |

**后端变更**：

- 移除 `jinja2` 依赖与 `templates/index.html`（迁移完成后）。
- 不新增任何 Python 运行时依赖；`StaticFiles` 是 Starlette 自带。

**仍不引入**：Redis / Celery / SQLAlchemy（后端照旧）；前端不引入 React Router、状态管理库、前端测试框架（首版）。

## 4. 仓库结构

```
vidistill/
├── src/vidistill/        # 后端，基本不动
│   ├── routes.py         # GET / 改为托管 SPA / 兜底页；其余端点不变
│   ├── main.py           # build_app 挂载 StaticFiles
│   └── templates/        # 迁移完成后删除
├── frontend/             # 新增前端工程
│   ├── index.html        # Vite 入口，<title>vidistill</title>
│   ├── package.json
│   ├── vite.config.ts    # dev proxy 到 :8000
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api.ts             # 7 个端点的 fetch 封装
│   │   ├── components/        # SubmitForm / MyJobs / FeedbackModal / ui(shadcn)
│   │   └── hooks/             # useJob / useMyJobs
│   └── dist/             # 构建产物（.gitignore）
├── Dockerfile            # 改成多阶段
└── docs/
```

`.gitignore` 新增 `frontend/node_modules/` 与 `frontend/dist/`。

## 5. 后端改动（最小化）

### 5.1 `GET /`：托管 SPA + 兜底页

- 若 `frontend/dist/index.html` 存在 → 返回它（生产 / 已构建场景）。
- 若不存在（测试 / 未构建的开发机）→ 返回**兜底 HTML**，内容提示「前端未构建：请 `cd frontend && npm run build`，或开发时用 Vite dev server（http://localhost:5173）」。

> 兜底页文案必须包含字符串 `vidistill`，以保证现有测试 `test_routes.py::test_get_root_returns_html`（断言返回 `text/html` 且含 `vidistill`）不改动也能绿。

### 5.2 静态资源托管

- `build_app` 中：若 `dist` 存在，`app.mount("/assets", StaticFiles(directory=dist/"assets"))` 托管打包后的 JS/CSS（Vite 默认把带 hash 的产物放在 `assets/`）。
- 其它根级静态文件（favicon、vite.svg 等）按需单独路由或一并托管。
- 应用是单页、无客户端路由，因此只需 `GET /` 提供入口；不实现 SPA 通配兜底（YAGNI）。已注册的 API 路径之外的未知路径，沿用 FastAPI 默认 404 行为即可。

### 5.3 不变的部分（关键）

- `POST /jobs`、`GET /jobs/{id}`、`DELETE /jobs/{id}`、`GET /jobs/{id}/download/{fmt}`、`GET /my/jobs`、`POST /feedback` —— **请求/响应契约、状态码、错误映射全部不变**。
- `VisitorCookieMiddleware` 不变：它对所有请求（含静态文件）生效，首次访问页面即种 cookie（`httponly` + `samesite=lax` + 同源）。
- 队列、单 worker、SQLite store、cleanup、exceptions 映射全部不变。

## 6. 前端结构（功能 1:1 映射现有 Alpine 逻辑）

现有 `index.html` 内有三个 Alpine "app"，逐一映射为 React 组件 + hook：

| 现有 Alpine | React 对应 | 必须保留的行为 |
|---|---|---|
| `vidistillApp()` | `<SubmitForm>` + `useJob(jobId)` | 提交 → 2s 轮询 `GET /jobs/{id}`；`queued/pending/fetching/transcribing/summarizing/rendering` 各阶段中文状态文案 + 进度条；队列位置展示；`beforeunload` 处理中离开提醒；`done` → 下载区；`failed` → 错误 + 重试/换一个；`cancelled` → reset |
| `myJobsApp()` | `<MyJobs>` + `useMyJobs()` | 3s 轮询 `GET /my/jobs`；状态 badge（排队/处理/完成/失败/取消语义色）；失败 badge 悬停显示 error；`queued` 可取消（`DELETE`）；`done` 显示 MD/HTML/PDF 下载（PDF 视 `available_formats`）；空列表提示检查 cookie；无活动任务时停止轮询 |
| `feedbackApp()` | `<FeedbackModal>`（shadcn Dialog） | 打开/关闭；必填内容 + 选填联系方式；提交 `POST /feedback`；成功提示 2s 后自动关闭；错误展示 |

- **`api.ts`**：封装 7 个端点的 `fetch`，全部相对路径、同源，无需手动带 cookie（浏览器同源自动带）。
- **PDF 不可用**：`available_formats` 不含 `pdf` 时，下载 PDF 按钮禁用并带提示（与现状一致）。

## 7. 开发工作流

- 后端：`poetry run uvicorn vidistill.main:app --reload --port 8000`（不变）。
- 前端：`cd frontend && npm install && npm run dev`（默认 :5173）。
- `vite.config.ts` 配 proxy：把 `/jobs`、`/my`、`/feedback` 前缀请求转发到 `http://localhost:8000`。
- **已知差异（无功能影响）**：dev 模式首屏 HTML 由 Vite 提供、不经后端，故 cookie 在**第一次 API 调用**时才被后端种下；生产模式首屏由后端返回、即时种 cookie。两者最终都能正常归属任务。

## 8. Docker（多阶段）

```dockerfile
# --- 前端构建阶段 ---
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build            # 产出 /fe/dist

# --- 后端运行阶段（现有镜像，基本不变）---
FROM python:3.12-slim-bookworm
# ffmpeg / weasyprint 运行库 / fonts-noto-cjk / sqlite3 等照旧
...
COPY src ./src
COPY --from=frontend /fe/dist ./frontend/dist
...
CMD ["uvicorn", "vidistill.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- 后端运行阶段的系统依赖（ffmpeg、WeasyPrint 库、CJK 字体、sqlite3 CLI）全部保留。
- `dist` 路径需与后端读取路径一致（`/app/frontend/dist`）。

## 9. 视觉方向（盲盒，作者定稿）

- 中性克制的现代风：白底 + 单一主色（沿用现蓝 `#1a73e8` 系，保持品牌延续）、圆角卡片、清晰阴影。
- 状态用语义色 badge（排队/处理/完成/失败/取消），与现有配色含义一致。
- 表单 + 任务列表两栏/堆叠响应式自适应，移动端可用。
- 一次做到"干净、专业、不花哨"，不留半成品（用户明确不希望后期反复调）。

## 10. 测试 &「不破坏」验证策略

- **后端测试全部保持绿**（API 未动）。`test_get_root_returns_html` 靠 5.1 的兜底页保持兼容，不改测试。
- **前端最小验证**：`tsc` 类型检查通过 + `vite build` 通过即视为基本健康（首版不引入 Vitest，符合项目极简取向）。
- **人工冒烟**：迁移完成后对照 `docs/smoke-test-checklist.md` 逐条跑一遍，确认功能对等（提交、轮询、下载三格式、取消、我的任务、反馈、队列满 429、PDF 不可用提示等）。

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 替换 `GET /` 导致老测试挂 | 兜底页含 `vidistill`，测试不改即绿（已验证断言逻辑） |
| dist 路径在容器内对不上 | spec 固定为 `/app/frontend/dist`，后端按此读取 |
| dev 与 prod cookie 种植时机不同 | 已分析：仅首屏时机差异，最终归属一致，无功能影响 |
| 视觉焕新掩盖功能回归 | 实现时先做到功能对等再上样式；最后人工冒烟逐条核对 |
| 误删后端逻辑 | 后端仅改 `routes.index` + `main.build_app` 托管静态；其余文件不动 |

## 12. 实现顺序建议（交由 writing-plans 细化）

1. 后端：`GET /` 兜底页 + StaticFiles 托管（dist 不存在也能跑），后端测试保持绿。
2. 前端脚手架：Vite + React + TS + Tailwind + shadcn/ui，`api.ts`，dev proxy。
3. 功能迁移：SubmitForm / MyJobs / FeedbackModal 达到功能对等（先不纠结样式）。
4. 视觉焕新：按第 9 节定稿。
5. Docker 多阶段；本地构建 + 容器内验证。
6. 删除 `templates/index.html` 与 `jinja2` 依赖；人工冒烟。

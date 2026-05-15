# vidistill 设计文档

- **创建日期**：2026-05-12
- **作者**：libo.gou@dreambigcareer.com
- **状态**：设计已确认，待实现

## 1. 概述

vidistill 是一个 Web 工具：给定一个 http(s):// 的视频链接（YouTube、B 站等 `yt-dlp` 支持的平台），抽取视频内容、调 LLM 生成总结，输出为 Markdown / HTML / PDF 文件供用户下载。

工具部署到公司内网服务器，初期供个人使用。

## 2. 目标与非目标

### 目标

- 输入一个视频 URL，输出该视频的 AI 总结文件
- 支持两种总结形态：**短摘要**（A）和 **章节笔记**（B，默认）
- 支持三种输出格式：**Markdown**（默认）/ HTML / PDF
- 通过单个 Docker 容器部署
- 单人使用、零数据库、零外部状态服务

### 非目标（明确不做）

- 不支持多用户登录与权限
- 不做任务历史记录与全文检索
- 不做并发任务（同时刻同进程只跑一个 pipeline，后来者排队）
- 不做视频内容审查
- 不做超过 30 分钟的视频
- 不做自动重试（失败由用户手动点重试）

## 3. 技术栈

| 层 | 选型 |
|---|---|
| 项目管理 | Poetry（`pyproject.toml`） |
| Web 框架 | FastAPI（异步原生，配合 `BackgroundTasks`） |
| 模板/前端 | Jinja2 单模板 + Alpine.js（CDN 引入） |
| 视频抓取 | yt-dlp（Python 包） |
| 音频处理 | ffmpeg（系统依赖） |
| ASR | 阿里百炼 Paraformer-v2（dashscope SDK） |
| LLM | 阿里百炼 Qwen（openai SDK + compatible-mode 端点） |
| Markdown 渲染 | markdown-it-py |
| PDF 生成 | WeasyPrint |
| 中文字体 | 思源黑体（容器内打包） |
| 容器 | 基于 `python:3.12-slim`，单进程 |

### 关键依赖说明

- **ffmpeg** 是系统级二进制（非 Python 包，Poetry 管不了）：本机开发用 `winget install ffmpeg` / `scoop install ffmpeg`；Docker 镜像里 `apt-get install -y ffmpeg`
- **API Key**：通过环境变量 `DASHSCOPE_API_KEY` 注入，启动时校验缺失即 fail fast
- **百炼端点**：LLM 走 `https://dashscope.aliyuncs.com/compatible-mode/v1`；ASR 走 DashScope 原生 SDK，两者用同一个 API Key

## 4. 架构总览

单 Docker 容器，单 FastAPI 进程。Web 请求和后台任务跑在同一个 Python 进程内，用 FastAPI 的 `BackgroundTasks` 异步执行视频处理 pipeline。

```
┌─────────────────────────────────────────────────────────┐
│                  Docker 容器                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │           FastAPI 进程（单进程）                    │  │
│  │                                                   │  │
│  │  ┌──────────────┐    ┌──────────────────────┐     │  │
│  │  │  Web 路由     │    │  内存任务表           │     │  │
│  │  │  /            │◀──▶│  Dict[job_id,        │     │  │
│  │  │  /jobs        │    │  JobState]           │     │  │
│  │  │  /jobs/{id}   │    └──────────────────────┘     │  │
│  │  │  /download    │                                 │  │
│  │  └──────┬───────┘                                  │  │
│  │         │ 提交任务                                  │  │
│  │         ▼                                          │  │
│  │  ┌────────────────────────────────────────────┐    │  │
│  │  │  POST /jobs 同步阶段：                     │    │  │
│  │  │  - yt-dlp 拿 metadata + 时长校验           │    │  │
│  │  │  - 校验失败 → 立即 422                     │    │  │
│  │  │  - 校验通过 → 入 BackgroundTask 异步执行   │    │  │
│  │  ├────────────────────────────────────────────┤    │  │
│  │  │  BackgroundTask: process_video()           │    │  │
│  │  │  1. 试取字幕 → 失败则下载音频 + ffmpeg     │    │  │
│  │  │  2. Paraformer ASR 转写                    │    │  │
│  │  │  3. Qwen 按 A/B 形态总结                   │    │  │
│  │  │  4. 渲染 md / html / pdf                   │    │  │
│  │  │  5. 写到 /tmp/vidistill/{job_id}/output.*  │    │  │
│  │  └────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  系统依赖: ffmpeg, 思源黑体                              │
│  存储: /tmp/vidistill/  (容器重启清空)                   │
└─────────────────────────────────────────────────────────┘
                          ▲
                          │ HTTP (公司内网)
                          │
                       浏览器
                  （Jinja2 + Alpine.js）
```

### 关键架构决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 单进程 vs 多 worker | 单进程 | 单人单任务，无并发 |
| 任务队列 | 内存 `Dict[str, JobState]` | 单人无持久化需求 |
| 数据库 | 无 | 无历史功能 |
| 同步 vs 异步 | FastAPI BackgroundTasks | 任务 5-10 分钟必须异步；轻量到不需要 Celery |
| 历史/恢复 | 无（关 tab 即丢） | 用户明确选 A，简化设计 |

## 5. 核心组件

### 5.1 项目结构

```
vidistill/
├── pyproject.toml             # Poetry 配置
├── poetry.lock
├── Dockerfile
├── docker-compose.yml         # 仅本地开发用
├── .env.example
├── README.md
├── docs/
│   └── superpowers/specs/2026-05-12-vidistill-design.md
├── src/
│   └── vidistill/
│       ├── __init__.py
│       ├── main.py            # FastAPI 入口
│       ├── routes.py          # HTTP 路由
│       ├── jobs.py            # 任务状态管理（内存 dict + 锁）
│       ├── pipeline.py        # 编排
│       ├── prompts.py         # A/B 形态 prompt 模板
│       ├── config.py          # 环境变量加载
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── video.py       # yt-dlp 封装
│       │   ├── asr.py         # Paraformer 封装
│       │   └── llm.py         # Qwen 封装
│       ├── renderers/
│       │   ├── __init__.py
│       │   ├── markdown.py
│       │   ├── html.py
│       │   └── pdf.py
│       └── templates/
│           └── index.html
├── static/
│   └── (Alpine.js CDN 引入，无本地静态资源)
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

### 5.2 模块职责与接口契约

| 模块 | 输入 | 输出 | 失败时 |
|---|---|---|---|
| `adapters/video.py` | URL | `VideoMetadata(title, duration, has_subtitle)`、字幕文本或音频文件路径 | 抛 `VideoFetchError` |
| `adapters/asr.py` | 音频文件路径 | `List[TranscriptSegment]`（带时间戳） | 抛 `ASRError` |
| `adapters/llm.py` | 转写片段 + style（A/B） | `Summary` dataclass | 抛 `LLMError` |
| `renderers/*.py` | `Summary` dataclass | 输出文件路径 | 抛 `RenderError` |
| `pipeline.py` | URL + 选项 | 更新 `JobState`、最终写文件路径 | 捕获以上异常 → 设 `status=failed` + error 信息 |
| `jobs.py` | - | 线程安全的状态读写 | - |
| `routes.py` | HTTP 请求 | JSON / 模板 / 文件流 | 422 / 404 / 409 / 500 |

### 5.3 数据契约

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

@dataclass
class VideoMetadata:
    title: str
    duration: int          # 秒
    has_subtitle: bool
    url: str

@dataclass
class TranscriptSegment:
    start: float           # 秒
    end: float
    text: str

@dataclass
class Chapter:
    timestamp: float       # 秒
    title: str
    summary: str
    bullets: list[str]

@dataclass
class Summary:
    style: Literal["short", "chapters"]
    video_title: str
    video_url: str
    short_summary: str | None       # A 形态：3-5 句
    bullets: list[str] | None       # A 形态：要点列表
    chapters: list[Chapter] | None  # B 形态：章节列表

@dataclass
class JobState:
    job_id: str
    url: str
    style: Literal["short", "chapters"]
    format: Literal["md", "html", "pdf"]
    status: Literal["pending", "fetching", "transcribing", "summarizing", "rendering", "done", "failed"]
    progress: int                   # 0-100
    error: str | None
    output_path: str | None
    created_at: datetime
```

`status` 细分到 pipeline 阶段，前端展示"正在转写..."这类具体信息。

## 6. 数据流

### 6.1 完整用户请求生命周期

```
浏览器                          FastAPI                     外部服务
───────                        ─────────                   ──────────

1. GET /
                  ──────▶  返回 index.html

2. POST /jobs { url, style, format }
                  ──────▶  ① yt-dlp 拿 metadata
                                            ──────▶ YouTube/B站
                           ② duration ≤ 30min 校验
                              超过 → 422
                           ③ 生成 job_id (uuid)
                           ④ 写 JobState(status=pending)
                           ⑤ BackgroundTasks.add_task(pipeline)
                  ◀──────  { job_id }

3. GET /jobs/{id}（每 2 秒）
                  ──────▶  读 JobState
                  ◀──────  { status, progress }

   后端 pipeline 异步推进：
   - fetching      → progress 10
     - 有字幕 → 直接拿字幕（跳过 ASR）progress 50
     - 无字幕 → 下载音频 + ffmpeg 抽 mp3
   - transcribing  → progress 30 → 调 Paraformer → progress 60
   - summarizing   → progress 70 → 调 Qwen → progress 90
   - rendering     → progress 95 → 写 /tmp/vidistill/{job_id}/output.{ext}
   - done          → progress 100, output_path set

4. status=done 后前端显示"下载"按钮
   GET /jobs/{id}/download
                  ──────▶  FileResponse(output_path)
                           Content-Disposition: attachment;
                              filename="{video_title}.{ext}"
                  ◀──────  文件流

5. 浏览器存到本地下载夹
```

### 6.2 关键设计点

| 点 | 设计 | 理由 |
|---|---|---|
| 进度报告 | pipeline 每阶段更新 progress（10/30/50/70/95/100） | 分阶段反馈 |
| 字幕优先 | fetching 阶段先试字幕，成功跳过 ASR | 省钱省时 |
| 30 分钟硬限制 | POST 阶段即拒，不入 pipeline | 减少无效消耗 |
| 轮询间隔 | 2 秒 | 简单可靠 |
| 文件不删 | 运行期不主动删，容器重启自动清 `/tmp` | 用户可重下 |
| 错误传递 | 抛异常 → 写 `JobState.error` → 前端展示 | 错误对用户可见 |
| 任务串行 | 同进程同时刻只跑 1 个 pipeline | 单人版的合理简化 |

### 6.3 前端状态机（Alpine.js）

```
idle  ──提交──▶  submitting  ──收到 job_id──▶  polling
                      │
                      └──422──▶  error_input
polling  ──status=done──▶  ready_to_download
polling  ──status=failed──▶  error_processing
ready_to_download / error_*  ──"再来一次"按钮──▶  idle
```

## 7. 错误处理

### 7.1 错误分类

| 错误来源 | 触发场景 | 后端行为 | 前端展示 |
|---|---|---|---|
| URL 校验 | 空 URL、不是 http(s)://、格式错 | POST 返回 422 | "请输入有效的视频链接" |
| metadata 失败 | 链接失效、视频被删、需登录、平台不支持 | POST 返回 422 + 简化错误 | "无法访问该视频：{原因}" |
| 时长超限 | metadata duration > 1800 秒 | POST 返回 422 | "视频时长 {X} 分钟，超过 30 分钟上限" |
| 音频下载失败 | yt-dlp 网络错、视频流被切 | pipeline 标 failed | "处理失败：视频音频下载失败" + 重试 |
| ASR 失败 | 百炼 API 错误、超时、quota | pipeline 标 failed | 显示 API 错误码 + 重试 |
| LLM 失败 | API 错误、超长 context | pipeline 标 failed | 显示原因 + 重试 |
| 渲染失败 | 字体缺失、HTML 解析错 | pipeline 标 failed | "文件生成失败" |
| 整体超时 | pipeline 总耗时 > 30 分钟 | `asyncio.wait_for` 包裹 | "任务超时" |
| 文件不存在 | 容器重启后前端仍持 job_id | GET /download 返回 404 | "文件已失效，请重新提交" |
| 非法文件名字符 | 视频标题含 `/\:*?"<>|` 或 emoji | 文件名 sanitize 替换为 `_` | 文件名干净 |

### 7.2 防御性设计

1. **API Key 缺失检测**：`config.py` 启动时读环境变量，缺失即抛错退出（fail fast）
2. **磁盘空间防护**：每次 pipeline 开始前检查 `/tmp/vidistill/` 剩余空间，<500MB 拒绝新任务
3. **并发简化**：单进程同时刻只跑 1 个 pipeline，第二个排队（status=pending）
4. **临时文件清理**：pipeline 的 `finally` 块删中间产物（音频文件等），只留最终输出
5. **重试按钮**：失败状态下前端显示"重试"，重新 POST 同样的 URL

### 7.3 显式不处理

| 不处理 | 理由 |
|---|---|
| 视频版权水印 | 只总结文字，不在意画面 |
| 多语言字幕语言检测 | 百炼 ASR 自动识别中英混合 |
| 视频内容审查 | 公司内网单人使用 |
| API key 用尽优雅降级 | 直接报错让用户充值 |
| 自动重试网络抖动 | 让用户手动重试，避免循环烧钱 |

## 8. 测试策略

测试目标是"防回归 + 关键路径走通"，不追求覆盖率指标。

### 8.1 测试分层

| 层级 | 工具 | 覆盖 | 是否 mock 外部 |
|---|---|---|---|
| 单元 | pytest | adapters、renderers、prompts、jobs 纯函数 | 是 |
| 集成 | pytest + httpx + FastAPI TestClient | HTTP 路由 + pipeline 编排 | 是 |
| 手工 smoke | 浏览器 | 端到端 | 否（真调 API） |

### 8.2 测试树

```
tests/
├── unit/
│   ├── test_video_adapter.py
│   │   - metadata 解析（fixture JSON）
│   │   - 字幕优先逻辑
│   │   - 时长边界（29:59 通过 / 30:01 拒）
│   │   - 错误分类 → VideoFetchError
│   ├── test_asr_adapter.py
│   │   - List[TranscriptSegment] 解析
│   │   - 百炼错误 → ASRError
│   ├── test_llm_adapter.py
│   │   - A/B prompt 拼装
│   │   - JSON 输出 → Summary 解析
│   │   - JSON 解析失败 fallback
│   ├── test_renderers.py
│   │   - Summary → Markdown 快照
│   │   - MD → HTML 含必要 meta
│   │   - HTML → PDF 文件非空 + 首页含标题
│   │   - 文件名 sanitize
│   ├── test_prompts.py
│   │   - 模板渲染（样例 transcript）
│   └── test_jobs.py
│       - 并发读写线程安全
│       - status 转换合法性
├── integration/
│   ├── test_routes.py
│   │   - POST /jobs 成功流（mock pipeline）
│   │   - POST /jobs URL 不合法 → 422
│   │   - POST /jobs 超时长 → 422
│   │   - GET /jobs/{id} 各 status 返回
│   │   - GET /download done → 文件
│   │   - GET /download 未完成 → 409
│   │   - GET /download 文件不存在 → 404
│   └── test_pipeline.py
│       - 字幕路径（跳过 ASR）
│       - ASR 兜底路径
│       - 每阶段异常传播
│       - 30 分钟总超时
└── fixtures/
    ├── yt_dlp_metadata_youtube.json
    ├── yt_dlp_metadata_bilibili.json
    ├── paraformer_response_short.json
    ├── qwen_response_chapters.json
    └── qwen_response_short.json
```

### 8.3 TDD 节奏

按 `superpowers:test-driven-development` 纪律：

1. 每个 adapter / renderer 先写 `test_*.py` 跑红
2. 实现到测试变绿，提交
3. pipeline 也是先写"按顺序调用各 adapter"的 mock 测试，再实现编排

### 8.4 手工 smoke 测试清单

每次发布前手跑一遍：

- [ ] 5 分钟 YouTube 视频（有自动字幕） → md 输出
- [ ] 5 分钟 B 站视频（无字幕、走 ASR） → pdf 输出（验证中文字体）
- [ ] A 形态短摘要 + B 形态章节笔记 各一次
- [ ] 35 分钟视频 → 立即被拒
- [ ] 失效链接 → 错误信息可读
- [ ] 中途关浏览器再开 → 显示空白（Q11 符合预期）

### 8.5 CI 跑什么

仅跑单元 + 集成测试（mock 外部 API，零成本零网络）。Smoke 测试本地手跑，需真 API key。

## 9. 部署

部署细节后期再细化，本设计只确认前置条件：

- 单个 Docker 镜像，基于 `python:3.12-slim`
- 镜像内装 ffmpeg + 思源黑体
- 镜像启动一个 FastAPI 进程，绑定 `0.0.0.0:8000`
- 通过环境变量 `DASHSCOPE_API_KEY` 注入凭据
- 公司内网访问，无需反向代理（直接暴露 8000 端口或公司有统一网关）

镜像大小预估 ~400MB。

## 10. 关键决策记录

| 决策 | 选择 | 备选 | 理由 |
|---|---|---|---|
| 内容提取 | 字幕优先 + ASR 兜底 | 仅字幕 / 多模态 | B 站很多视频无字幕；多模态对总结目标 overkill |
| 总结形态 | A 短摘要 + B 章节笔记，前端切换默认 B | 仅 B / 仅详细稿件 | 用户可选；详细稿件价值低 |
| LLM/ASR vendor | 阿里百炼（Qwen + Paraformer） | OpenAI / Anthropic / 全自建 | 用户已有 key；中文 ASR 比 Whisper 好；一个 key 走天下 |
| 规模 | 单人单进程 | 多 worker + 登录 | 当前用户基数 1；扩展工程量 ~1-2 天 |
| 平台范围 | yt-dlp 兼容即支持（best effort） | 仅 YouTube + B 站 | 用户接受失败时给清晰提示 |
| 数据库 | 无 | SQLite | 用户明确要极简，无历史功能 |
| 关 tab 处理 | 直接丢弃 | localStorage 恢复 | 用户选 A 极简 |
| 视频时长上限 | 30 分钟硬限制 | 无限 / 软提示 | 用户明确指定 |
| 前后端栈 | Python 全栈（FastAPI + Jinja2 + Alpine） | Node + TS / React SPA | 视频生态（yt-dlp、WeasyPrint）Python 原生最顺 |
| 包管理 | Poetry | pip + requirements.txt / uv | 用户指定 |
| PDF 引擎 | WeasyPrint | Puppeteer / wkhtmltopdf | 纯 Python，无浏览器依赖，镜像更小 |

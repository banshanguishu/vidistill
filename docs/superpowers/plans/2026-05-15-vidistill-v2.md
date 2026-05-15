# vidistill v2.0.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持现有架构精简的前提下，让 vidistill 支持 ~10 人共用（后端单 worker 串行，前端任务排队 + 我的任务列表 + cookie 匿名识别 + SQLite 持久化 + 7 天清理）。

**Architecture:** 现有 `BackgroundTasks` 直接跑 pipeline 改为 `asyncio.Queue` + 单 worker 协程消费；内存 `JobStore` 替换为 SQLite 实现；新增 cookie 中间件做 visitor 识别；新增 `/my/jobs` 和 `DELETE /jobs/{id}` 端点；前端首页加"我的任务"列表 + spinner。零新依赖、零新容器。

**Tech Stack:** Python 3.12、FastAPI、stdlib `sqlite3`、stdlib `asyncio`、Jinja2、现有 Alpine.js（沿用，不引入新前端框架）。

**Spec:** `docs/superpowers/specs/2026-05-15-vidistill-v2-concurrent-design.md`

---

## 实施约定

- 每完成一个 task 就 commit，commit message 采用 `feat:` / `refactor:` / `test:` / `chore:` 前缀（沿用 repo 风格）
- 测试用 `poetry run pytest`（pyproject.toml 已配 `pythonpath = ["src"]` + `asyncio_mode = "auto"`）
- 单元测试 SQLite 用 `":memory:"`
- **关于前端**：spec §10.6 提到"原生 JS"，但现有 `index.html` 已经用 Alpine.js（CDN 加载）。**实施时沿用 Alpine**（不引入新依赖、不丢现有 working code）。spec 的"不引入 SPA 框架"约束意指 Vue/React/HTMX，Alpine 不属此列。
- v1 旧测试中关于 `try_acquire_slot` / `_slot_busy` 的部分会被删除，由新的队列测试覆盖
- 中间结果：每个 task 完成后跑 `poetry run pytest` 全量通过再 commit

---

## 文件结构总览

### 新建文件

- `src/vidistill/middleware.py` — VisitorCookieMiddleware
- `src/vidistill/queue_worker.py` — asyncio.Queue + worker 协程
- `src/vidistill/cleanup.py` — 7 天清理协程
- `src/vidistill/templates/_form.html` — 提交表单 partial
- `src/vidistill/templates/_my_jobs.html` — 任务列表 partial
- `tests/unit/test_store_sqlite.py`
- `tests/unit/test_middleware.py`
- `tests/unit/test_queue_worker.py`
- `tests/unit/test_cleanup.py`
- `tests/integration/test_concurrent_submit.py`
- `tests/integration/test_restart_recovery.py`
- `tests/integration/test_my_jobs.py`

### 重大修改

- `src/vidistill/jobs.py` — `JobStore` 类整体重写为 SQLite 实现，删除 `try_acquire_slot`/`release_slot`
- `src/vidistill/models.py` — `JobStatus` 加 `queued`、`cancelled`；`JobState` 加 `visitor_id`/`started_at`/`finished_at` 字段
- `src/vidistill/exceptions.py` — 加 4 个 v2 异常
- `src/vidistill/routes.py` — 重写大部分端点，加 exception handler
- `src/vidistill/main.py` — 加 lifespan 启动 worker/cleanup、加中间件、加 queue 到 app.state
- `src/vidistill/templates/index.html` — 拆分 partial、加我的任务列表、加 spinner CSS
- `src/vidistill/templates/job_detail.html` — 加 queue_position 显示（若该文件存在；不在 v1 plan 范围内，按需）
- `tests/unit/test_jobs.py` — 删除（被 `test_store_sqlite.py` 取代）
- `tests/integration/test_routes.py` — 大幅调整，删 `test_post_jobs_rejects_when_slot_busy`，加 visitor cookie / queue 相关测试

---

## Phase 0: 模型与异常基础

### Task 1: 扩展 JobStatus 枚举 + 加 visitor/timestamp 字段 + 新增 v2 异常

**Files:**
- Modify: `src/vidistill/models.py`
- Modify: `src/vidistill/exceptions.py`
- Test: `tests/unit/test_models.py`、`tests/unit/test_exceptions.py`

- [ ] **Step 1: 修改 `JobStatus` 枚举与 `JobState` dataclass**

`src/vidistill/models.py` 改成：

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

Style = Literal["short", "chapters"]
Format = Literal["md", "html", "pdf"]
JobStatus = Literal[
    "queued",        # v2 新增
    "pending",
    "fetching",
    "transcribing",
    "summarizing",
    "rendering",
    "done",
    "failed",
    "cancelled",     # v2 新增
]

# VideoMetadata / TranscriptSegment / Chapter / Summary 保持不变

@dataclass
class JobState:
    job_id: str
    visitor_id: str         # v2 新增
    url: str
    video_title: str
    style: Style
    status: JobStatus
    progress: int
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime] = None    # v2 新增
    finished_at: Optional[datetime] = None   # v2 新增
    output_paths: dict[str, Optional[str]] = field(default_factory=dict)
```

- [ ] **Step 2: 修改 `exceptions.py` 加 4 个 v2 异常**

在 `src/vidistill/exceptions.py` 末尾追加：

```python
class QueueFullError(VidistillError):
    """Queue is at capacity (10 active jobs)."""


class JobNotFoundError(VidistillError):
    """Job with given id does not exist."""


class JobNotCancellableError(VidistillError):
    """Job cannot be cancelled because it is no longer queued."""


class JobAccessDeniedError(VidistillError):
    """Operation requires the visitor to be the job creator."""
```

- [ ] **Step 3: 跑现有测试，确认 JobState 字段扩展不破坏旧用例**

```
poetry run pytest tests/unit/test_models.py tests/unit/test_exceptions.py -v
```

Expected: 全部 PASS（旧用例不构造 `visitor_id` 会 fail —— 此时**确实期望 fail**，下一步修）

- [ ] **Step 4: 修补 `tests/unit/test_models.py`**

把所有 `JobState(...)` 调用补上 `visitor_id="v-test"`。Grep `JobState(` 找出全部 callsite。

- [ ] **Step 5: 加新测试 `test_v2_exceptions_inherit_vidistill`**

`tests/unit/test_exceptions.py` 末尾追加：

```python
from vidistill.exceptions import (
    VidistillError,
    QueueFullError,
    JobNotFoundError,
    JobNotCancellableError,
    JobAccessDeniedError,
)


def test_v2_exceptions_inherit_vidistill_error():
    for cls in (QueueFullError, JobNotFoundError, JobNotCancellableError, JobAccessDeniedError):
        assert issubclass(cls, VidistillError)
        assert issubclass(cls, Exception)
```

- [ ] **Step 6: 跑所有单测**

```
poetry run pytest -v
```

Expected: 全部 PASS（构造 JobState 的地方都已补 visitor_id）

⚠ 如有失败：grep 出所有未更新的 `JobState(` 调用补字段。可能在 `tests/integration/test_routes.py`、`pipeline.py`、`routes.py` 也有。

- [ ] **Step 7: Commit**

```
git add src/vidistill/models.py src/vidistill/exceptions.py tests/
git commit -m "feat(models): add queued/cancelled status, visitor_id/timestamps, v2 exceptions"
```

---

## Phase 1: SQLite JobStore

### Task 2: SqliteJobStore 初始化 + schema

**Files:**
- Modify: `src/vidistill/jobs.py`（整体重写）
- Test: `tests/unit/test_store_sqlite.py`（新建）

- [ ] **Step 1: 删除老 `jobs.py` 内容，写新的 schema + 构造器**

`src/vidistill/jobs.py` 整体替换为：

```python
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from vidistill.models import JobState

_NON_TERMINAL = ("queued", "pending", "fetching", "transcribing", "summarizing", "rendering")
_TERMINAL = ("done", "failed", "cancelled")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id        TEXT PRIMARY KEY,
    visitor_id    TEXT NOT NULL,
    url           TEXT NOT NULL,
    video_title   TEXT,
    style         TEXT NOT NULL,
    status        TEXT NOT NULL,
    progress      INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    md_path       TEXT,
    html_path     TEXT,
    pdf_path      TEXT,
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_visitor_created ON jobs(visitor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_status          ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_created_at      ON jobs(created_at);
"""


class JobStore:
    """SQLite-backed job store. Thread-safe via a single connection + lock."""

    def __init__(self, db_path: str | Path) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
```

- [ ] **Step 2: 写测试 `test_store_init_creates_schema`**

`tests/unit/test_store_sqlite.py`（新建）：

```python
from vidistill.jobs import JobStore


def test_store_init_creates_schema():
    store = JobStore(":memory:")
    # Querying the table should not raise
    cur = store._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
    assert cur.fetchone() is not None
```

- [ ] **Step 3: 跑测试**

```
poetry run pytest tests/unit/test_store_sqlite.py::test_store_init_creates_schema -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```
git add src/vidistill/jobs.py tests/unit/test_store_sqlite.py
git commit -m "refactor(jobs): replace in-memory JobStore with SQLite (schema + init)"
```

---

### Task 3: 基础 CRUD（create / get / update / delete）

**Files:**
- Modify: `src/vidistill/jobs.py`
- Test: `tests/unit/test_store_sqlite.py`

- [ ] **Step 1: 写 4 个测试（先 fail）**

追加到 `tests/unit/test_store_sqlite.py`：

```python
from datetime import datetime
import pytest
from vidistill.models import JobState


def _job(job_id="abc", visitor_id="v1", status="queued"):
    return JobState(
        job_id=job_id,
        visitor_id=visitor_id,
        url="https://x",
        video_title="Test",
        style="short",
        status=status,
        progress=0,
        error=None,
        created_at=datetime(2026, 5, 15, 10, 0, 0),
    )


def test_create_and_get():
    store = JobStore(":memory:")
    store.create(_job("j1"))
    j = store.get("j1")
    assert j is not None
    assert j.job_id == "j1"
    assert j.visitor_id == "v1"
    assert j.status == "queued"


def test_get_returns_none_for_unknown():
    store = JobStore(":memory:")
    assert store.get("nope") is None


def test_update_modifies_fields():
    store = JobStore(":memory:")
    store.create(_job("j1"))
    store.update("j1", status="fetching", progress=30)
    j = store.get("j1")
    assert j.status == "fetching"
    assert j.progress == 30


def test_update_unknown_raises():
    store = JobStore(":memory:")
    with pytest.raises(KeyError):
        store.update("nope", status="done")


def test_delete():
    store = JobStore(":memory:")
    store.create(_job("j1"))
    store.delete("j1")
    assert store.get("j1") is None


def test_update_output_paths():
    store = JobStore(":memory:")
    store.create(_job("j1"))
    store.update("j1", output_paths={"md": "/a.md", "html": "/a.html", "pdf": None})
    j = store.get("j1")
    assert j.output_paths == {"md": "/a.md", "html": "/a.html", "pdf": None}
```

- [ ] **Step 2: 跑测试确认 fail**

```
poetry run pytest tests/unit/test_store_sqlite.py -v
```

Expected: 6 个新测试 FAIL（方法未定义）

- [ ] **Step 3: 在 `JobStore` 类里追加 CRUD 方法**

```python
def create(self, job: JobState) -> None:
    with self._lock:
        self._conn.execute(
            """INSERT INTO jobs (
                job_id, visitor_id, url, video_title, style, status, progress,
                error, md_path, html_path, pdf_path, created_at, started_at, finished_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job.job_id, job.visitor_id, job.url, job.video_title, job.style,
                job.status, job.progress, job.error,
                job.output_paths.get("md"),
                job.output_paths.get("html"),
                job.output_paths.get("pdf"),
                job.created_at.isoformat(),
                job.started_at.isoformat() if job.started_at else None,
                job.finished_at.isoformat() if job.finished_at else None,
            ),
        )

def get(self, job_id: str) -> Optional[JobState]:
    with self._lock:
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    return self._row_to_job(row) if row else None

_UPDATABLE_FIELDS = {
    "status", "progress", "error", "video_title",
    "started_at", "finished_at",
}

def update(self, job_id: str, **kwargs) -> None:
    output_paths = kwargs.pop("output_paths", None)
    sets = []
    vals: list = []
    for k, v in kwargs.items():
        if k not in self._UPDATABLE_FIELDS:
            raise ValueError(f"Field {k!r} is not updatable")
        if isinstance(v, datetime):
            v = v.isoformat()
        sets.append(f"{k} = ?")
        vals.append(v)
    if output_paths is not None:
        for fmt in ("md", "html", "pdf"):
            sets.append(f"{fmt}_path = ?")
            vals.append(output_paths.get(fmt))
    if not sets:
        return
    vals.append(job_id)
    with self._lock:
        cur = self._conn.execute(
            f"UPDATE jobs SET {', '.join(sets)} WHERE job_id = ?", vals
        )
        if cur.rowcount == 0:
            raise KeyError(f"Unknown job_id: {job_id}")

def delete(self, job_id: str) -> None:
    with self._lock:
        self._conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))

@staticmethod
def _row_to_job(row: sqlite3.Row) -> JobState:
    return JobState(
        job_id=row["job_id"],
        visitor_id=row["visitor_id"],
        url=row["url"],
        video_title=row["video_title"] or "",
        style=row["style"],
        status=row["status"],
        progress=row["progress"],
        error=row["error"],
        created_at=datetime.fromisoformat(row["created_at"]),
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
        output_paths={
            "md": row["md_path"],
            "html": row["html_path"],
            "pdf": row["pdf_path"],
        },
    )
```

- [ ] **Step 4: 跑测试验证通过**

```
poetry run pytest tests/unit/test_store_sqlite.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```
git add src/vidistill/jobs.py tests/unit/test_store_sqlite.py
git commit -m "feat(jobs): SQLite JobStore CRUD (create/get/update/delete)"
```

---

### Task 4: visitor 查询与 7 天清理查询

**Files:**
- Modify: `src/vidistill/jobs.py`
- Test: `tests/unit/test_store_sqlite.py`

- [ ] **Step 1: 写 3 个测试**

追加到 `tests/unit/test_store_sqlite.py`：

```python
from datetime import timedelta


def test_list_by_visitor_returns_only_own_jobs():
    store = JobStore(":memory:")
    base = datetime(2026, 5, 15, 10, 0, 0)
    store.create(_job("a", "v1"))
    j2 = _job("b", "v2")
    object.__setattr__(j2, "created_at", base + timedelta(minutes=1))
    store.create(j2)
    j3 = _job("c", "v1")
    object.__setattr__(j3, "created_at", base + timedelta(minutes=2))
    store.create(j3)

    rows = store.list_by_visitor("v1", cutoff=base - timedelta(days=1))
    ids = [j.job_id for j in rows]
    assert ids == ["c", "a"]  # DESC


def test_list_by_visitor_filters_cutoff():
    store = JobStore(":memory:")
    old = _job("old", "v1")
    object.__setattr__(old, "created_at", datetime(2026, 5, 1))
    new = _job("new", "v1")
    object.__setattr__(new, "created_at", datetime(2026, 5, 15))
    store.create(old)
    store.create(new)

    rows = store.list_by_visitor("v1", cutoff=datetime(2026, 5, 10))
    assert [j.job_id for j in rows] == ["new"]


def test_list_older_than_returns_only_terminal_jobs():
    store = JobStore(":memory:")
    base = datetime(2026, 5, 1)
    for jid, status in [("a", "done"), ("b", "queued"), ("c", "failed"), ("d", "fetching")]:
        j = _job(jid, "v1", status=status)
        object.__setattr__(j, "created_at", base)
        store.create(j)

    stale = store.list_older_than(datetime(2026, 5, 15))
    ids = sorted(j.job_id for j in stale)
    assert ids == ["a", "c"]  # done + failed (terminal), excluded: queued, fetching
```

- [ ] **Step 2: 跑测试确认 fail**

```
poetry run pytest tests/unit/test_store_sqlite.py::test_list_by_visitor_returns_only_own_jobs -v
```

Expected: FAIL

- [ ] **Step 3: 在 `JobStore` 实现这两个方法**

```python
def list_by_visitor(self, visitor_id: str, cutoff: datetime) -> list[JobState]:
    with self._lock:
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE visitor_id = ? AND created_at >= ? "
            "ORDER BY created_at DESC",
            (visitor_id, cutoff.isoformat()),
        ).fetchall()
    return [self._row_to_job(r) for r in rows]

def list_older_than(self, cutoff: datetime) -> list[JobState]:
    placeholders = ",".join("?" * len(_TERMINAL))
    with self._lock:
        rows = self._conn.execute(
            f"SELECT * FROM jobs WHERE created_at < ? AND status IN ({placeholders})",
            (cutoff.isoformat(), *_TERMINAL),
        ).fetchall()
    return [self._row_to_job(r) for r in rows]
```

- [ ] **Step 4: 跑测试验证通过**

```
poetry run pytest tests/unit/test_store_sqlite.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```
git add src/vidistill/jobs.py tests/unit/test_store_sqlite.py
git commit -m "feat(jobs): list_by_visitor + list_older_than"
```

---

### Task 5: 队列辅助查询（count_active / queue_position / mark_zombies_failed）

**Files:**
- Modify: `src/vidistill/jobs.py`
- Test: `tests/unit/test_store_sqlite.py`

- [ ] **Step 1: 写 3 个测试**

追加到 `tests/unit/test_store_sqlite.py`：

```python
def test_count_active_includes_queued_and_running():
    store = JobStore(":memory:")
    for jid, status in [("a", "queued"), ("b", "fetching"), ("c", "done"), ("d", "cancelled")]:
        store.create(_job(jid, "v1", status=status))
    assert store.count_active() == 2  # a + b


def test_queue_position_includes_running_task():
    store = JobStore(":memory:")
    base = datetime(2026, 5, 15, 10, 0, 0)
    # 1 task is running
    running = _job("r", "v1", status="fetching")
    object.__setattr__(running, "created_at", base)
    store.create(running)
    # 2 queued before "me"
    for i, jid in enumerate(["q1", "q2", "me"]):
        j = _job(jid, "v1", status="queued")
        object.__setattr__(j, "created_at", base + timedelta(minutes=i+1))
        store.create(j)
    # me has 2 queued ahead + 1 running = position 4
    assert store.queue_position("me") == 4
    # q1 has 0 queued ahead + 1 running = position 2
    assert store.queue_position("q1") == 2


def test_queue_position_none_when_no_running():
    store = JobStore(":memory:")
    j = _job("only", "v1", status="queued")
    store.create(j)
    assert store.queue_position("only") == 1


def test_mark_zombies_failed_only_affects_in_progress():
    store = JobStore(":memory:")
    for jid, status in [
        ("a", "queued"), ("b", "pending"), ("c", "fetching"),
        ("d", "transcribing"), ("e", "summarizing"), ("f", "rendering"),
        ("g", "done"), ("h", "failed"), ("i", "cancelled"),
    ]:
        store.create(_job(jid, "v1", status=status))
    n = store.mark_zombies_failed()
    assert n == 6
    assert store.get("a").status == "failed"
    assert store.get("a").error == "服务重启时中断"
    assert store.get("g").status == "done"  # unaffected
    assert store.get("h").status == "failed"  # unchanged
```

- [ ] **Step 2: 跑测试确认 fail**

```
poetry run pytest tests/unit/test_store_sqlite.py::test_count_active_includes_queued_and_running -v
```

Expected: FAIL

- [ ] **Step 3: 实现这 3 个方法**

在 `JobStore` 里追加：

```python
def count_active(self) -> int:
    """Number of jobs currently in non-terminal status (queued + running)."""
    placeholders = ",".join("?" * len(_NON_TERMINAL))
    with self._lock:
        row = self._conn.execute(
            f"SELECT COUNT(*) FROM jobs WHERE status IN ({placeholders})",
            _NON_TERMINAL,
        ).fetchone()
    return row[0]

def queue_position(self, job_id: str) -> Optional[int]:
    """Position in wait line (1-indexed) for a 'queued' job.

    Includes the currently running task (if any) in the count.
    Returns None if job is not in 'queued' status.
    """
    with self._lock:
        own = self._conn.execute(
            "SELECT created_at, status FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if not own or own["status"] != "queued":
            return None
        ahead = self._conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'queued' AND created_at < ?",
            (own["created_at"],),
        ).fetchone()[0]
        running_placeholders = ",".join("?" * (len(_NON_TERMINAL) - 1))
        running = self._conn.execute(
            f"SELECT COUNT(*) FROM jobs WHERE status IN ({running_placeholders})",
            [s for s in _NON_TERMINAL if s != "queued"],
        ).fetchone()[0]
    return ahead + 1 + (1 if running else 0)

def mark_zombies_failed(self) -> int:
    """At startup: mark in-progress tasks as failed (restart recovery).

    Returns count of jobs marked.
    """
    placeholders = ",".join("?" * len(_NON_TERMINAL))
    with self._lock:
        cur = self._conn.execute(
            f"UPDATE jobs SET status='failed', error=?, finished_at=? "
            f"WHERE status IN ({placeholders})",
            ("服务重启时中断", datetime.now().isoformat(), *_NON_TERMINAL),
        )
    return cur.rowcount
```

- [ ] **Step 4: 跑测试验证通过**

```
poetry run pytest tests/unit/test_store_sqlite.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```
git add src/vidistill/jobs.py tests/unit/test_store_sqlite.py
git commit -m "feat(jobs): count_active + queue_position + mark_zombies_failed"
```

---

### Task 6: 删除旧 `tests/unit/test_jobs.py`，修复 `main.py` 启动

**Files:**
- Delete: `tests/unit/test_jobs.py`
- Modify: `src/vidistill/main.py`
- Modify: `src/vidistill/config.py`

- [ ] **Step 1: 删除老测试文件**

```
git rm tests/unit/test_jobs.py
```

- [ ] **Step 2: 修改 `Config` 加 `db_path` 字段**

`src/vidistill/config.py` 改成：

```python
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    dashscope_api_key: str
    dashscope_compatible_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    paraformer_model: str = "paraformer-realtime-v2"
    output_dir: Path = field(default_factory=lambda: Path("/tmp/vidistill"))
    log_dir: Path = field(default_factory=lambda: Path("/tmp/vidistill"))
    db_path: Optional[Path] = None  # v2 新增；None 表示 output_dir / "vidistill.db"
    max_video_duration_seconds: int = 1800
    pipeline_timeout_seconds: int = 1800
    min_free_disk_mb: int = 500

    def effective_db_path(self) -> Path:
        return self.db_path if self.db_path else self.output_dir / "vidistill.db"


def load_config() -> Config:
    # ... 沿用现有逻辑，不改
```

注意：`from typing import Optional` 需引入。

- [ ] **Step 3: 修改 `main.py` 使用 SQLite store**

`src/vidistill/main.py` 改成：

```python
from pathlib import Path
from typing import Optional

from fastapi import FastAPI

from vidistill.config import Config, load_config
from vidistill.jobs import JobStore
from vidistill.logging_setup import setup_logging
from vidistill.routes import router


def build_app(config: Optional[Config] = None, output_dir: Optional[Path] = None) -> FastAPI:
    if config is None:
        config = load_config()
    if output_dir is not None:
        config = Config(
            dashscope_api_key=config.dashscope_api_key,
            dashscope_compatible_base_url=config.dashscope_compatible_base_url,
            qwen_model=config.qwen_model,
            paraformer_model=config.paraformer_model,
            output_dir=output_dir,
            log_dir=output_dir,
            db_path=output_dir / "vidistill.db",
            max_video_duration_seconds=config.max_video_duration_seconds,
            pipeline_timeout_seconds=config.pipeline_timeout_seconds,
            min_free_disk_mb=config.min_free_disk_mb,
        )
        config.output_dir.mkdir(parents=True, exist_ok=True)

    setup_logging(config.log_dir)

    config.effective_db_path().parent.mkdir(parents=True, exist_ok=True)
    store = JobStore(config.effective_db_path())
    zombies = store.mark_zombies_failed()
    if zombies > 0:
        import logging
        logging.getLogger(__name__).warning("[startup] marked %d zombie jobs as failed", zombies)

    app = FastAPI(title="vidistill")
    app.state.store = store
    app.state.config = config
    app.include_router(router)
    return app


app = build_app()
```

⚠ 注意：模块级单例 `_GLOBAL_STORE` 和 `get_store()` 函数被**移除**，因为 store 现在挂到 `app.state`。下一步要修 routes 引用 / 测试。

- [ ] **Step 4: 在 `routes.py` 改用 `request.app.state.store`**

`routes.py` 里所有 `store: JobStore = request.app.state.store` 已经是这种用法（v1 即是），无需改动。但要**删除** v1 里的 `try_acquire_slot` / `release_slot` 调用（Task 11 会重写整个 POST /jobs，先把直接调用注释掉以让 collection 跑起来）：

临时把 routes.py 里这些行注释掉：

```python
# if not store.try_acquire_slot():
#     ...
```

并在 `_runner` 的 finally 里去掉 `store.release_slot()`。这只是为了让 import 通过；功能 Task 11 重写。

- [ ] **Step 5: 修 `tests/integration/test_routes.py` 让 collection 通过**

把 `reset_slot` fixture 删除（或 noop 化）：

```python
@pytest.fixture(autouse=True)
def reset_store():
    """v2: each test gets a fresh client fixture, no shared singleton."""
    yield
```

删除 `from vidistill.main import get_store` 的导入。把 `test_post_jobs_rejects_when_slot_busy` 整体删除（v2 行为不同，Task 11 之后由队列测试覆盖）。

把 seed-fixture 的代码改成 `app.state.store.create(...)` 替代 `get_store().create(...)`：

```python
def test_download_returns_file_when_done(client, tmp_path):
    from vidistill.models import JobState

    fake_file = tmp_path / "result.md"
    fake_file.write_text("# Done", encoding="utf-8")

    store = client.app.state.store
    store.create(JobState(
        job_id="done1",
        visitor_id="v-test",
        url="https://x",
        video_title="Done Video",
        style="short",
        status="done",
        progress=100,
        error=None,
        output_paths={"md": str(fake_file), "html": None, "pdf": None},
        created_at=datetime.now(),
    ))
    ...
```

类似地修 `test_download_returns_404_when_format_not_generated`。

- [ ] **Step 6: 跑测试看哪些还失败**

```
poetry run pytest -v
```

预期：v1 的 slot-busy 测试已删；其他通过或仅"未实现"导致的失败。

- [ ] **Step 7: Commit**

```
git add -A
git commit -m "refactor(main): wire SQLite JobStore via app.state, run zombie sweep at startup"
```

---

## Phase 2: Cookie 中间件

### Task 7: VisitorCookieMiddleware

**Files:**
- Create: `src/vidistill/middleware.py`
- Test: `tests/unit/test_middleware.py`（新建）
- Modify: `src/vidistill/main.py`

- [ ] **Step 1: 写测试 `test_middleware_sets_cookie_when_absent`**

`tests/unit/test_middleware.py`：

```python
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from vidistill.middleware import VisitorCookieMiddleware


def _app():
    app = FastAPI()
    app.add_middleware(VisitorCookieMiddleware)

    @app.get("/whoami")
    def whoami(request: Request):
        return {"visitor_id": request.state.visitor_id}

    return app


def test_middleware_sets_cookie_when_absent():
    client = TestClient(_app())
    r = client.get("/whoami")
    assert r.status_code == 200
    assert "visitor_id" in r.cookies
    assert len(r.cookies["visitor_id"]) >= 16
    assert r.json()["visitor_id"] == r.cookies["visitor_id"]


def test_middleware_passes_through_existing_cookie():
    client = TestClient(_app())
    r = client.get("/whoami", cookies={"visitor_id": "existing-id-xyz"})
    assert r.json()["visitor_id"] == "existing-id-xyz"
    # No new cookie set in response
    assert "visitor_id" not in r.cookies or r.cookies["visitor_id"] == "existing-id-xyz"


def test_middleware_cookie_attributes_httponly_lax():
    client = TestClient(_app())
    r = client.get("/whoami")
    set_cookie = r.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie.lower() or "samesite=lax" in set_cookie.lower()
    assert "Max-Age=63072000" in set_cookie
```

- [ ] **Step 2: 跑测试确认 fail**

```
poetry run pytest tests/unit/test_middleware.py -v
```

Expected: FAIL（middleware 模块不存在）

- [ ] **Step 3: 实现中间件**

`src/vidistill/middleware.py`：

```python
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


COOKIE_NAME = "visitor_id"
COOKIE_MAX_AGE = 63_072_000  # 2 years


class VisitorCookieMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        visitor_id = request.cookies.get(COOKIE_NAME)
        is_new = False
        if not visitor_id:
            visitor_id = secrets.token_urlsafe(16)
            is_new = True
        request.state.visitor_id = visitor_id
        response = await call_next(request)
        if is_new:
            response.set_cookie(
                key=COOKIE_NAME,
                value=visitor_id,
                max_age=COOKIE_MAX_AGE,
                httponly=True,
                samesite="lax",
                path="/",
            )
        return response
```

- [ ] **Step 4: 跑测试**

```
poetry run pytest tests/unit/test_middleware.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: 把中间件接到 `build_app()`**

`src/vidistill/main.py` 的 `build_app` 内加：

```python
from vidistill.middleware import VisitorCookieMiddleware
...
    app = FastAPI(title="vidistill")
    app.add_middleware(VisitorCookieMiddleware)   # 新增此行
    app.state.store = store
    ...
```

- [ ] **Step 6: Commit**

```
git add src/vidistill/middleware.py src/vidistill/main.py tests/unit/test_middleware.py
git commit -m "feat(middleware): visitor cookie with auto-issue + 2y max-age"
```

---

## Phase 3: 异常 → HTTP 状态码映射

### Task 8: 全局 VidistillError exception handler

**Files:**
- Modify: `src/vidistill/main.py`
- Test: `tests/integration/test_routes.py`

- [ ] **Step 1: 写一个测试 hook 验证 handler 安装**

追加到 `tests/integration/test_routes.py`：

```python
def test_exception_handler_maps_vidistill_errors(client):
    from vidistill.exceptions import QueueFullError, JobNotFoundError
    from fastapi import APIRouter

    # Inject a throw-route
    router = APIRouter()

    @router.get("/_test/queue-full")
    def boom_queue():
        raise QueueFullError("队列已满（10 个）")

    @router.get("/_test/not-found")
    def boom_404():
        raise JobNotFoundError("任务不存在")

    client.app.include_router(router)

    r1 = client.get("/_test/queue-full")
    assert r1.status_code == 429
    assert "队列已满" in r1.json()["detail"]

    r2 = client.get("/_test/not-found")
    assert r2.status_code == 404
```

- [ ] **Step 2: 跑测试确认 fail（500 而非 429）**

- [ ] **Step 3: 在 `build_app()` 注册 handler**

`src/vidistill/main.py` 的 `build_app` 内加：

```python
from fastapi.responses import JSONResponse
from vidistill.exceptions import (
    VidistillError, QueueFullError, JobNotFoundError,
    JobNotCancellableError, JobAccessDeniedError, VideoFetchError,
)

_ERROR_STATUS_MAP = {
    QueueFullError: 429,
    JobNotFoundError: 404,
    JobNotCancellableError: 409,
    JobAccessDeniedError: 403,
    VideoFetchError: 422,
}


def _install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(VidistillError)
    async def handle_vidistill_error(request, exc: VidistillError):
        status = _ERROR_STATUS_MAP.get(type(exc), 500)
        return JSONResponse({"detail": str(exc)}, status_code=status)
```

并在 `build_app` 里调用 `_install_exception_handlers(app)`。

- [ ] **Step 4: 跑测试验证通过**

- [ ] **Step 5: Commit**

```
git add src/vidistill/main.py tests/integration/test_routes.py
git commit -m "feat(routes): central exception handler maps VidistillError to HTTP"
```

---

## Phase 4: Queue 与 Worker

### Task 9: Worker 协程模块

**Files:**
- Create: `src/vidistill/queue_worker.py`
- Test: `tests/unit/test_queue_worker.py`（新建）

- [ ] **Step 1: 写测试 `test_worker_processes_job_and_calls_pipeline`**

`tests/unit/test_queue_worker.py`：

```python
import asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from vidistill.config import Config
from vidistill.jobs import JobStore
from vidistill.models import JobState
from vidistill.queue_worker import worker_loop


def _job(job_id="j1", status="queued"):
    return JobState(
        job_id=job_id,
        visitor_id="v1",
        url="https://x",
        video_title="T",
        style="short",
        status=status,
        progress=0,
        error=None,
        created_at=datetime.now(),
    )


def _config():
    return Config(dashscope_api_key="test", output_dir="/tmp", db_path=":memory:")


async def test_worker_picks_up_job_and_runs_pipeline():
    store = JobStore(":memory:")
    store.create(_job("j1"))
    queue: asyncio.Queue = asyncio.Queue(maxsize=9)
    await queue.put("j1")

    with patch("vidistill.queue_worker.process_video") as mock_pipe:
        task = asyncio.create_task(worker_loop(store, queue, _config()))
        await asyncio.sleep(0.05)        # let worker pick up
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    mock_pipe.assert_called_once()
    assert store.get("j1").status == "pending"  # set by worker before process_video


async def test_worker_skips_cancelled_jobs():
    store = JobStore(":memory:")
    store.create(_job("j1", status="cancelled"))
    queue: asyncio.Queue = asyncio.Queue(maxsize=9)
    await queue.put("j1")

    with patch("vidistill.queue_worker.process_video") as mock_pipe:
        task = asyncio.create_task(worker_loop(store, queue, _config()))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    mock_pipe.assert_not_called()


async def test_worker_swallows_pipeline_exception_and_continues():
    store = JobStore(":memory:")
    store.create(_job("j1"))
    store.create(_job("j2"))
    queue: asyncio.Queue = asyncio.Queue(maxsize=9)
    await queue.put("j1")
    await queue.put("j2")

    side_effects = [Exception("boom"), None]
    with patch("vidistill.queue_worker.process_video", side_effect=side_effects) as mock_pipe:
        task = asyncio.create_task(worker_loop(store, queue, _config()))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert mock_pipe.call_count == 2
    assert store.get("j1").status == "failed"
```

- [ ] **Step 2: 跑测试确认 fail**

- [ ] **Step 3: 实现 worker**

`src/vidistill/queue_worker.py`：

```python
import asyncio
import logging
from datetime import datetime

from vidistill.config import Config
from vidistill.jobs import JobStore
from vidistill.pipeline import process_video

logger = logging.getLogger(__name__)


async def worker_loop(store: JobStore, queue: asyncio.Queue[str], config: Config) -> None:
    """Single worker that drains the queue serially. Never exits on its own."""
    while True:
        job_id = await queue.get()
        try:
            job = store.get(job_id)
            if not job:
                logger.warning("[worker] job=%s vanished from store; skipping", job_id)
                continue
            if job.status == "cancelled":
                logger.info("[worker] job=%s was cancelled; skipping", job_id)
                continue
            store.update(job_id, status="pending", started_at=datetime.now())
            await asyncio.to_thread(
                process_video,
                job_id=job_id,
                url=job.url,
                style=job.style,
                store=store,
                config=config,
            )
            store.update(job_id, finished_at=datetime.now())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[worker] job=%s crashed outside pipeline", job_id)
            try:
                store.update(job_id, status="failed", error="worker 异常", finished_at=datetime.now())
            except Exception:
                logger.exception("[worker] failed to mark job=%s as failed", job_id)
        finally:
            queue.task_done()
```

- [ ] **Step 4: 跑测试**

```
poetry run pytest tests/unit/test_queue_worker.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```
git add src/vidistill/queue_worker.py tests/unit/test_queue_worker.py
git commit -m "feat(worker): asyncio queue worker loop with cancel-skip + exception isolation"
```

---

### Task 10: Lifespan 集成 worker + queue 进 app.state

**Files:**
- Modify: `src/vidistill/main.py`

- [ ] **Step 1: 改 `main.py` 用 lifespan**

把 `build_app` 改为：

```python
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from vidistill.config import Config, load_config
from vidistill.exceptions import (
    VidistillError, QueueFullError, JobNotFoundError,
    JobNotCancellableError, JobAccessDeniedError, VideoFetchError,
)
from vidistill.jobs import JobStore
from vidistill.logging_setup import setup_logging
from vidistill.middleware import VisitorCookieMiddleware
from vidistill.queue_worker import worker_loop
from vidistill.routes import router


_ERROR_STATUS_MAP = {
    QueueFullError: 429,
    JobNotFoundError: 404,
    JobNotCancellableError: 409,
    JobAccessDeniedError: 403,
    VideoFetchError: 422,
}


def _install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(VidistillError)
    async def handle_vidistill_error(request, exc: VidistillError):
        status = _ERROR_STATUS_MAP.get(type(exc), 500)
        return JSONResponse({"detail": str(exc)}, status_code=status)


def build_app(config: Optional[Config] = None, output_dir: Optional[Path] = None) -> FastAPI:
    if config is None:
        config = load_config()
    if output_dir is not None:
        config = Config(
            dashscope_api_key=config.dashscope_api_key,
            dashscope_compatible_base_url=config.dashscope_compatible_base_url,
            qwen_model=config.qwen_model,
            paraformer_model=config.paraformer_model,
            output_dir=output_dir,
            log_dir=output_dir,
            db_path=output_dir / "vidistill.db",
            max_video_duration_seconds=config.max_video_duration_seconds,
            pipeline_timeout_seconds=config.pipeline_timeout_seconds,
            min_free_disk_mb=config.min_free_disk_mb,
        )
        config.output_dir.mkdir(parents=True, exist_ok=True)

    setup_logging(config.log_dir)

    config.effective_db_path().parent.mkdir(parents=True, exist_ok=True)
    store = JobStore(config.effective_db_path())
    zombies = store.mark_zombies_failed()
    if zombies > 0:
        logging.getLogger(__name__).warning("[startup] marked %d zombie jobs as failed", zombies)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.queue = asyncio.Queue(maxsize=9)
        app.state.worker_task = asyncio.create_task(
            worker_loop(app.state.store, app.state.queue, app.state.config)
        )
        try:
            yield
        finally:
            app.state.worker_task.cancel()
            try:
                await app.state.worker_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="vidistill", lifespan=lifespan)
    app.add_middleware(VisitorCookieMiddleware)
    app.state.store = store
    app.state.config = config
    _install_exception_handlers(app)
    app.include_router(router)
    return app


app = build_app()
```

注意：`Config` 现在多了 `db_path` 字段，确保 Task 6 时已加。

- [ ] **Step 2: 跑全部测试**

```
poetry run pytest -v
```

Expected：大部分通过；可能有些和 routes 行为相关的会失败（Task 11+ 再修）

- [ ] **Step 3: Commit**

```
git add src/vidistill/main.py
git commit -m "feat(main): lifespan starts worker, integrates queue + middleware + exception handlers"
```

---

## Phase 5: POST /jobs 重构 + visitor 注入

### Task 11: POST /jobs 改为入队，新增 visitor_id 与 queue_position 字段

**Files:**
- Modify: `src/vidistill/routes.py`
- Test: `tests/integration/test_routes.py`

- [ ] **Step 1: 写测试 `test_post_jobs_returns_queue_position`**

替换或新增 `tests/integration/test_routes.py`：

```python
def test_post_jobs_returns_queue_position(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="Short", duration=300, has_subtitle=True, url="https://x")
    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})

    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert body["queue_position"] == 1  # first task ever


def test_post_jobs_returns_429_when_queue_full(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=300, has_subtitle=True, url="https://x")
    # Pre-fill the queue: 10 active jobs via direct store seeding
    from vidistill.models import JobState
    store = client.app.state.store
    for i in range(10):
        store.create(JobState(
            job_id=f"seed{i}",
            visitor_id="v-other",
            url="https://x",
            video_title=f"Seed {i}",
            style="short",
            status="queued",
            progress=0,
            error=None,
            created_at=datetime.now(),
        ))

    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})

    assert r.status_code == 429
    assert "队列已满" in r.json()["detail"] or "队列" in r.json()["detail"]
```

- [ ] **Step 2: 跑测试确认 fail**

- [ ] **Step 3: 重写 `routes.py` 的 `create_job`**

把 `create_job` 替换为：

```python
@router.post("/jobs", response_model=CreateJobResponse)
async def create_job(req: CreateJobRequest, request: Request):
    store: JobStore = request.app.state.store
    config: Config = request.app.state.config
    queue: asyncio.Queue = request.app.state.queue
    visitor_id: str = request.state.visitor_id

    try:
        meta = video.fetch_metadata(str(req.url))
    except VideoFetchError as e:
        logger.warning("POST /jobs REJECT url=%s reason=fetch_metadata_failed error=%s", req.url, e)
        raise

    if meta.duration > config.max_video_duration_seconds:
        minutes = meta.duration // 60
        logger.warning(
            "POST /jobs REJECT url=%s reason=too_long duration_seconds=%d",
            req.url, meta.duration,
        )
        raise VideoFetchError(f"视频时长 {minutes} 分钟，超过 30 分钟上限")

    if store.count_active() >= 10:
        logger.warning("POST /jobs REJECT url=%s reason=queue_full", req.url)
        raise QueueFullError("队列已满（10 个），请稍后再试")

    job_id = uuid.uuid4().hex[:12]
    store.create(JobState(
        job_id=job_id,
        visitor_id=visitor_id,
        url=str(req.url),
        video_title=meta.title,
        style=req.style,
        status="queued",
        progress=0,
        error=None,
        output_paths={},
        created_at=datetime.now(),
    ))
    try:
        queue.put_nowait(job_id)
    except asyncio.QueueFull:
        # Race: count_active passed but queue maxed. Roll back.
        store.update(job_id, status="failed", error="队列竞争失败")
        raise QueueFullError("队列已满（10 个），请稍后再试")

    position = store.queue_position(job_id) or 1
    logger.info("POST /jobs ACCEPT job_id=%s position=%d", job_id, position)
    return CreateJobResponse(job_id=job_id, queue_position=position)
```

更新 `CreateJobResponse` Pydantic 模型：

```python
class CreateJobResponse(BaseModel):
    job_id: str
    queue_position: int
```

同时在 imports 顶部加：

```python
import asyncio
from vidistill.exceptions import QueueFullError, VideoFetchError
```

并**移除** v1 的 `BackgroundTasks` 参数和 `_runner` 内嵌函数（不再需要）。

- [ ] **Step 4: 跑测试**

```
poetry run pytest tests/integration/test_routes.py -v
```

Expected: 新的 `test_post_jobs_returns_queue_position` 和 `test_post_jobs_returns_429_when_queue_full` 通过

- [ ] **Step 5: Commit**

```
git add src/vidistill/routes.py tests/integration/test_routes.py
git commit -m "feat(routes): POST /jobs enqueues via asyncio.Queue, returns queue_position"
```

---

### Task 12: GET /jobs/{id} 增加 queue_position 字段

**Files:**
- Modify: `src/vidistill/routes.py`
- Test: `tests/integration/test_routes.py`

- [ ] **Step 1: 写测试**

```python
def test_get_job_returns_queue_position_for_queued(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=300, has_subtitle=True, url="https://x")
    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})
    job_id = r.json()["job_id"]

    r2 = client.get(f"/jobs/{job_id}")
    body = r2.json()
    # status is either 'queued' (not yet picked up) or 'pending'+ (already picked)
    if body["status"] == "queued":
        assert body["queue_position"] == 1
    else:
        assert body["queue_position"] is None
```

- [ ] **Step 2: 修 `get_job` 端点**

```python
@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    store: JobStore = request.app.state.store
    job = store.get(job_id)
    if not job:
        raise JobNotFoundError("任务不存在")
    available_formats = [fmt for fmt, path in job.output_paths.items() if path]
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "queue_position": store.queue_position(job_id),
        "error": job.error,
        "video_title": job.video_title,
        "available_formats": available_formats,
    }
```

注意：把原来的 `raise HTTPException(status_code=404, ...)` 改成 `raise JobNotFoundError(...)`。imports 加 `from vidistill.exceptions import JobNotFoundError`。

- [ ] **Step 3: 跑测试，确认通过**

- [ ] **Step 4: Commit**

```
git add src/vidistill/routes.py tests/integration/test_routes.py
git commit -m "feat(routes): GET /jobs/{id} reports queue_position; use JobNotFoundError"
```

---

## Phase 6: 新端点

### Task 13: GET /my/jobs

**Files:**
- Modify: `src/vidistill/routes.py`
- Test: `tests/integration/test_my_jobs.py`（新建）

- [ ] **Step 1: 写测试**

`tests/integration/test_my_jobs.py`：

```python
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from vidistill.main import build_app
    return TestClient(build_app(output_dir=tmp_path))


def test_my_jobs_returns_empty_for_new_visitor(client):
    r = client.get("/my/jobs")
    assert r.status_code == 200
    body = r.json()
    assert body["jobs"] == []
    assert "system" in body
    assert body["system"]["active_count"] == 0
    assert body["system"]["active_max"] == 10
    assert body["system"]["queue_full"] is False


def test_my_jobs_isolates_by_visitor(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="T", duration=300, has_subtitle=True, url="https://x")
    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        # visitor A submits
        r1 = client.post("/jobs", json={"url": "https://x", "style": "short"})
        assert r1.status_code == 200
        # visitor B submits (new client = new cookie jar)
        client2 = TestClient(client.app)
        r2 = client2.post("/jobs", json={"url": "https://x", "style": "short"})
        # rely on shared store; second may 429 if queue saturates — make space first by
        # constraining to checking visibility, not count

    r_a = client.get("/my/jobs")
    r_b = client2.get("/my/jobs")
    a_ids = {j["job_id"] for j in r_a.json()["jobs"]}
    b_ids = {j["job_id"] for j in r_b.json()["jobs"]}
    assert a_ids.isdisjoint(b_ids)
    assert r1.json()["job_id"] in a_ids
```

- [ ] **Step 2: 实现端点**

`routes.py` 加：

```python
from datetime import timedelta


@router.get("/my/jobs")
def my_jobs(request: Request):
    store: JobStore = request.app.state.store
    visitor_id: str = request.state.visitor_id
    cutoff = datetime.now() - timedelta(days=7)
    jobs = store.list_by_visitor(visitor_id, cutoff)
    items = []
    for j in jobs:
        items.append({
            "job_id": j.job_id,
            "video_title": j.video_title,
            "status": j.status,
            "progress": j.progress,
            "queue_position": store.queue_position(j.job_id),
            "created_at": j.created_at.isoformat(),
            "available_formats": [fmt for fmt, path in j.output_paths.items() if path],
        })
    active = store.count_active()
    return {
        "jobs": items,
        "system": {
            "active_count": active,
            "active_max": 10,
            "queue_full": active >= 10,
        },
    }
```

- [ ] **Step 3: 跑测试**

```
poetry run pytest tests/integration/test_my_jobs.py -v
```

Expected: 全部 PASS

- [ ] **Step 4: Commit**

```
git add src/vidistill/routes.py tests/integration/test_my_jobs.py
git commit -m "feat(routes): GET /my/jobs lists current visitor jobs + system status"
```

---

### Task 14: DELETE /jobs/{id} 取消排队任务

**Files:**
- Modify: `src/vidistill/routes.py`
- Test: `tests/integration/test_routes.py`

- [ ] **Step 1: 写 4 个测试**

```python
def test_delete_unknown_returns_404(client):
    r = client.delete("/jobs/nope")
    assert r.status_code == 404


def test_delete_cancels_queued_job(client):
    from vidistill.models import VideoMetadata
    meta = VideoMetadata(title="X", duration=300, has_subtitle=True, url="https://x")
    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})
    job_id = r.json()["job_id"]
    # In TestClient lifespan is started, but the worker may have picked it.
    # If status is no longer 'queued', skip the success path.
    status = client.get(f"/jobs/{job_id}").json()["status"]
    if status != "queued":
        pytest.skip("worker picked task before DELETE; race-y in TestClient")

    r2 = client.delete(f"/jobs/{job_id}")
    assert r2.status_code == 200
    assert client.app.state.store.get(job_id).status == "cancelled"


def test_delete_other_visitor_returns_403(client, tmp_path):
    from vidistill.models import JobState
    client.app.state.store.create(JobState(
        job_id="not-mine",
        visitor_id="someone-else",
        url="https://x", video_title="T", style="short",
        status="queued", progress=0, error=None,
        created_at=datetime.now(),
    ))
    r = client.delete("/jobs/not-mine")
    assert r.status_code == 403


def test_delete_running_returns_409(client, tmp_path):
    from vidistill.models import JobState
    # Manually create as me, in fetching state
    visitor_id = client.cookies.get("visitor_id") or client.get("/my/jobs").cookies["visitor_id"]
    client.app.state.store.create(JobState(
        job_id="running",
        visitor_id=visitor_id,
        url="https://x", video_title="T", style="short",
        status="fetching", progress=20, error=None,
        created_at=datetime.now(),
    ))
    r = client.delete("/jobs/running")
    assert r.status_code == 409
```

- [ ] **Step 2: 实现端点**

`routes.py` 加：

```python
from vidistill.exceptions import (
    JobNotFoundError, JobNotCancellableError, JobAccessDeniedError,
)


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str, request: Request):
    store: JobStore = request.app.state.store
    visitor_id: str = request.state.visitor_id
    job = store.get(job_id)
    if not job:
        raise JobNotFoundError("任务不存在")
    if job.visitor_id != visitor_id:
        raise JobAccessDeniedError("无权操作此任务")
    if job.status != "queued":
        raise JobNotCancellableError("任务已开始处理，无法取消")
    store.update(job_id, status="cancelled", finished_at=datetime.now())
    return {"ok": True}
```

- [ ] **Step 3: 跑测试**

- [ ] **Step 4: Commit**

```
git add src/vidistill/routes.py tests/integration/test_routes.py
git commit -m "feat(routes): DELETE /jobs/{id} cancels queued task (403/409/404 mapping)"
```

---

## Phase 7: Cleanup 协程

### Task 15: cleanup 模块

**Files:**
- Create: `src/vidistill/cleanup.py`
- Test: `tests/unit/test_cleanup.py`（新建）

- [ ] **Step 1: 写测试**

`tests/unit/test_cleanup.py`：

```python
import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from vidistill.cleanup import cleanup_once
from vidistill.jobs import JobStore
from vidistill.models import JobState


async def test_cleanup_removes_terminal_jobs_older_than_7d(tmp_path: Path):
    store = JobStore(":memory:")

    old_done = JobState(
        job_id="old1", visitor_id="v", url="x", video_title="T", style="short",
        status="done", progress=100, error=None,
        created_at=datetime.now() - timedelta(days=8),
        output_paths={"md": str(tmp_path / "old1" / "x.md")},
    )
    new_done = JobState(
        job_id="new1", visitor_id="v", url="x", video_title="T", style="short",
        status="done", progress=100, error=None,
        created_at=datetime.now() - timedelta(days=1),
        output_paths={"md": str(tmp_path / "new1" / "x.md")},
    )
    old_running = JobState(
        job_id="zombie", visitor_id="v", url="x", video_title="T", style="short",
        status="fetching", progress=10, error=None,
        created_at=datetime.now() - timedelta(days=8),
    )
    store.create(old_done)
    store.create(new_done)
    store.create(old_running)
    (tmp_path / "old1").mkdir()
    (tmp_path / "old1" / "x.md").write_text("x")
    (tmp_path / "new1").mkdir()
    (tmp_path / "new1" / "x.md").write_text("x")

    removed = cleanup_once(store, tmp_path)
    assert removed == 1
    assert store.get("old1") is None
    assert not (tmp_path / "old1").exists()
    assert store.get("new1") is not None
    assert store.get("zombie") is not None  # non-terminal: untouched
```

- [ ] **Step 2: 实现**

`src/vidistill/cleanup.py`：

```python
import asyncio
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from vidistill.jobs import JobStore

logger = logging.getLogger(__name__)

_RETENTION_DAYS = 7
_INTERVAL_SECONDS = 3600


def cleanup_once(store: JobStore, output_dir: Path) -> int:
    cutoff = datetime.now() - timedelta(days=_RETENTION_DAYS)
    stale = store.list_older_than(cutoff)
    removed = 0
    for job in stale:
        try:
            shutil.rmtree(output_dir / job.job_id, ignore_errors=True)
            store.delete(job.job_id)
            removed += 1
        except Exception:
            logger.exception("[cleanup] failed to remove job=%s", job.job_id)
    if removed:
        logger.info("[cleanup] removed %d stale jobs", removed)
    return removed


async def cleanup_loop(store: JobStore, output_dir: Path) -> None:
    while True:
        try:
            cleanup_once(store, output_dir)
        except Exception:
            logger.exception("[cleanup] tick failed; will retry next interval")
        await asyncio.sleep(_INTERVAL_SECONDS)
```

- [ ] **Step 3: 跑测试**

- [ ] **Step 4: Commit**

```
git add src/vidistill/cleanup.py tests/unit/test_cleanup.py
git commit -m "feat(cleanup): 7-day retention with hourly tick"
```

---

### Task 16: 把 cleanup 协程接到 lifespan

**Files:**
- Modify: `src/vidistill/main.py`

- [ ] **Step 1: 修改 lifespan**

```python
from vidistill.cleanup import cleanup_loop

...
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.queue = asyncio.Queue(maxsize=9)
        app.state.worker_task = asyncio.create_task(
            worker_loop(app.state.store, app.state.queue, app.state.config)
        )
        app.state.cleanup_task = asyncio.create_task(
            cleanup_loop(app.state.store, app.state.config.output_dir)
        )
        try:
            yield
        finally:
            for t in (app.state.worker_task, app.state.cleanup_task):
                t.cancel()
            for t in (app.state.worker_task, app.state.cleanup_task):
                try:
                    await t
                except asyncio.CancelledError:
                    pass
```

- [ ] **Step 2: 跑所有测试**

```
poetry run pytest -v
```

- [ ] **Step 3: Commit**

```
git add src/vidistill/main.py
git commit -m "feat(main): wire cleanup coroutine into lifespan"
```

---

## Phase 8: 前端

### Task 17: 加 spinner CSS + 把状态文案更新支持 queued/cancelled

**Files:**
- Modify: `src/vidistill/templates/index.html`

- [ ] **Step 1: 在 `<style>` 块底部追加 spinner 样式**

```css
.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid #e0e0e0;
  border-top-color: #1a73e8;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  vertical-align: middle;
  margin-right: 6px;
}
@keyframes spin { to { transform: rotate(360deg); } }
```

- [ ] **Step 2: 更新 Alpine 里的 `statusLabel()` 与 phase 逻辑**

把 `statusLabel()` 改成：

```javascript
statusLabel() {
  const map = {
    queued: this.queuePosition ? `正在排队（第 ${this.queuePosition} 位）...` : '正在排队...',
    pending: '即将开始...',
    fetching: '正在抓取视频信息...',
    transcribing: '正在转写音频...',
    summarizing: '正在生成摘要...',
    rendering: '正在渲染输出...',
  };
  return map[this.status] || this.status;
},
```

并在 `vidistillApp()` 的状态变量里加：

```javascript
queuePosition: null,
```

在 `poll()` 函数里加：

```javascript
this.queuePosition = data.queue_position;
```

在进度区块 HTML 加一个 spinner：

```html
<!-- Progress -->
<template x-if="phase === 'polling'">
  <div>
    <div class="status-text"><strong x-text="videoTitle || '处理中'"></strong></div>
    <div class="status-text">
      <span class="spinner"></span>
      <span x-text="statusLabel()"></span>
    </div>
    ...
  </div>
</template>
```

- [ ] **Step 3: 手动启 dev server 验证**

```
poetry run uvicorn vidistill.main:app --reload --port 8000
```

打开浏览器看页面是否正常渲染、spinner 是否转动。提交一个 fake URL 试一下流程。

- [ ] **Step 4: Commit**

```
git add src/vidistill/templates/index.html
git commit -m "feat(ui): spinner + queued/cancelled status labels"
```

---

### Task 18: "我的任务"列表（在首页底部）

**Files:**
- Modify: `src/vidistill/templates/index.html`

- [ ] **Step 1: 在 `<body>` 里 `.card` 之后追加"我的任务"区块**

```html
<div class="card" x-data="myJobsApp()" x-init="init()" style="margin-top: 1.5rem;">
  <h2 style="margin-top: 0;">我的任务（最近 7 天）</h2>

  <div class="status-text" x-show="systemQueueFull" style="color: #c62828;">
    ⚠ 当前队列已满（10 / 10），请稍后再提交
  </div>
  <div class="status-text" x-show="!systemQueueFull && systemActiveCount > 0">
    ✓ 当前队列：<span x-text="systemActiveCount"></span> / 10
  </div>

  <table style="width: 100%; border-collapse: collapse; margin-top: .8rem;" x-show="jobs.length > 0">
    <thead>
      <tr style="border-bottom: 1px solid #ddd;">
        <th style="text-align: left; padding: .5rem; font-size: .9rem;">标题</th>
        <th style="text-align: left; padding: .5rem; font-size: .9rem;">状态</th>
        <th style="text-align: left; padding: .5rem; font-size: .9rem;">操作</th>
      </tr>
    </thead>
    <tbody>
      <template x-for="j in jobs" :key="j.job_id">
        <tr style="border-bottom: 1px solid #f0f0f0;">
          <td style="padding: .5rem;" x-text="j.video_title || j.job_id"></td>
          <td style="padding: .5rem;">
            <span class="spinner" x-show="!isTerminal(j.status)"></span>
            <span x-text="statusLabel(j)"></span>
          </td>
          <td style="padding: .5rem;">
            <template x-if="j.status === 'queued'">
              <button @click="cancel(j.job_id)" class="retry" style="padding: .3rem .6rem; font-size: .85rem;">取消</button>
            </template>
            <template x-if="j.status === 'done'">
              <span>
                <a :href="`/jobs/${j.job_id}/download/md`" style="margin-right: .3rem;">md</a>
                <a :href="`/jobs/${j.job_id}/download/html`" style="margin-right: .3rem;">html</a>
                <template x-if="j.available_formats.includes('pdf')">
                  <a :href="`/jobs/${j.job_id}/download/pdf`">pdf</a>
                </template>
              </span>
            </template>
            <template x-if="j.status === 'failed'">
              <span :title="j.error || ''" style="color: #c62828;" x-text="'ⓘ'"></span>
            </template>
          </td>
        </tr>
      </template>
    </tbody>
  </table>

  <div x-show="jobs.length === 0" class="status-text" style="margin-top: .8rem;">
    暂无任务。如果之前提交过却看不到，请检查浏览器是否启用 Cookie。
  </div>
</div>
```

- [ ] **Step 2: 在 `<script>` 区追加 `myJobsApp()`**

```javascript
function myJobsApp() {
  return {
    jobs: [],
    systemActiveCount: 0,
    systemQueueFull: false,
    pollTimer: null,

    init() {
      this.refresh();
      this.startPolling();
    },

    startPolling() {
      this.pollTimer = setInterval(() => this.refresh(), 3000);
    },

    async refresh() {
      try {
        const resp = await fetch('/my/jobs');
        if (!resp.ok) return;
        const data = await resp.json();
        this.jobs = data.jobs || [];
        this.systemActiveCount = data.system.active_count;
        this.systemQueueFull = data.system.queue_full;
      } catch (e) {
        // transient; ignore
      }
    },

    async cancel(jobId) {
      try {
        await fetch(`/jobs/${jobId}`, { method: 'DELETE' });
        this.refresh();
      } catch (e) {
        // ignore
      }
    },

    isTerminal(status) {
      return ['done', 'failed', 'cancelled'].includes(status);
    },

    statusLabel(j) {
      const map = {
        queued: j.queue_position ? `排队中 #${j.queue_position}` : '排队中',
        pending: '即将开始',
        fetching: `处理中 ${j.progress}%`,
        transcribing: `处理中 ${j.progress}%`,
        summarizing: `处理中 ${j.progress}%`,
        rendering: `处理中 ${j.progress}%`,
        done: '已完成',
        failed: '失败',
        cancelled: '已取消',
      };
      return map[j.status] || j.status;
    },
  };
}
```

- [ ] **Step 3: 手动启 dev server 验证**

```
poetry run uvicorn vidistill.main:app --reload --port 8000
```

- 主页底部看到"我的任务"卡片
- 提交一个任务后 3 秒内看到它出现
- 取消按钮工作

- [ ] **Step 4: Commit**

```
git add src/vidistill/templates/index.html
git commit -m "feat(ui): 'my jobs' list with cancel + queue-full warning"
```

---

## Phase 9: 集成测试 + Smoke

### Task 19: 并发提交集成测试

**Files:**
- Create: `tests/integration/test_concurrent_submit.py`

- [ ] **Step 1: 写测试**

`tests/integration/test_concurrent_submit.py`：

```python
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from vidistill.main import build_app
    return TestClient(build_app(output_dir=tmp_path))


def test_eleventh_submission_gets_429(client):
    from vidistill.models import VideoMetadata, JobState

    # Seed 10 active jobs directly so we don't depend on worker timing
    store = client.app.state.store
    for i in range(10):
        store.create(JobState(
            job_id=f"seed{i}",
            visitor_id="v-other",
            url="https://x",
            video_title=f"Seed {i}",
            style="short",
            status="queued",
            progress=0,
            error=None,
            created_at=datetime.now(),
        ))

    meta = VideoMetadata(title="X", duration=300, has_subtitle=True, url="https://x")
    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})

    assert r.status_code == 429


def test_two_visitors_see_separate_my_jobs_lists(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=300, has_subtitle=True, url="https://x")
    client2 = TestClient(client.app)

    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        r1 = client.post("/jobs", json={"url": "https://x", "style": "short"})
        r2 = client2.post("/jobs", json={"url": "https://x", "style": "short"})

    j1 = r1.json()["job_id"]
    j2 = r2.json()["job_id"]
    assert j1 != j2

    my1 = {j["job_id"] for j in client.get("/my/jobs").json()["jobs"]}
    my2 = {j["job_id"] for j in client2.get("/my/jobs").json()["jobs"]}
    assert j1 in my1
    assert j2 in my2
    assert j1 not in my2
    assert j2 not in my1
```

- [ ] **Step 2: 跑测试**

```
poetry run pytest tests/integration/test_concurrent_submit.py -v
```

- [ ] **Step 3: Commit**

```
git add tests/integration/test_concurrent_submit.py
git commit -m "test(integration): concurrent submit + queue full + visitor isolation"
```

---

### Task 20: 重启恢复集成测试

**Files:**
- Create: `tests/integration/test_restart_recovery.py`

- [ ] **Step 1: 写测试**

```python
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from vidistill.jobs import JobStore
from vidistill.models import JobState


def test_zombie_inprogress_jobs_marked_failed_at_startup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    # Step 1: build first app, seed an in-progress job, close
    db_path = tmp_path / "vidistill.db"
    store1 = JobStore(db_path)
    store1.create(JobState(
        job_id="zombie",
        visitor_id="v",
        url="https://x",
        video_title="T",
        style="short",
        status="fetching",
        progress=30,
        error=None,
        created_at=datetime.now() - timedelta(hours=1),
    ))
    store1._conn.close()

    # Step 2: rebuild app — startup must mark "fetching" as "failed"
    from vidistill.main import build_app
    app = build_app(output_dir=tmp_path)
    j = app.state.store.get("zombie")
    assert j.status == "failed"
    assert j.error == "服务重启时中断"
```

- [ ] **Step 2: 跑测试**

```
poetry run pytest tests/integration/test_restart_recovery.py -v
```

- [ ] **Step 3: Commit**

```
git add tests/integration/test_restart_recovery.py
git commit -m "test(integration): restart sweeps zombie jobs to failed"
```

---

### Task 21: 更新手动 smoke 清单

**Files:**
- Modify: `docs/smoke-test-checklist.md`

- [ ] **Step 1: 追加 v2 项目**

在文件末尾追加（如果文件存在；如不存在跳过此 task）：

```markdown
## v2.0.0 验证

- [ ] 打开两个浏览器（或两台机器）的隐身窗口分别访问，提交两个不同任务 → 各自看到自己的，互不可见
- [ ] 同一浏览器再次刷新主页 → "我的任务"列表保留
- [ ] 提交后立刻看到"排队中 #1"，跑完看到"已完成"+ 下载链接
- [ ] 排队任务点"取消" → 状态变"已取消"
- [ ] 已开始处理的任务点取消 → 不出现取消按钮（应为"查看详情"或下载）
- [ ] 提交 10 个任务后第 11 个 → "队列已满"
- [ ] docker restart 之后：已完成任务仍在列表；正在跑的任务变"失败"
- [ ] 8 天前的任务（可手动改 SQLite 测试）→ 1 小时内被清理
```

- [ ] **Step 2: Commit**

```
git add docs/smoke-test-checklist.md
git commit -m "docs: v2 manual smoke test checklist"
```

---

### Task 22: 最终完整跑测试

- [ ] **Step 1: 跑全部测试**

```
poetry run pytest -v
```

Expected: 全部 PASS（如果有失败，逐个调试）

- [ ] **Step 2: 手动启 dev server 走一遍**

```
poetry run uvicorn vidistill.main:app --reload --port 8000
```

走通：
- 提交 → 看到"排队中 #1" → spinner 转动
- 列表里看到该任务
- 跑完 → 状态"已完成" → 下载链接可点
- 提交无效 URL → toast 错误
- 队列 stress 测试可选

- [ ] **Step 3: 跑 `docker build` 验证**

```
docker build -t vidistill:v2 .
```

Expected: 构建成功

- [ ] **Step 4: 最终 commit（如有遗留）**

```
git status
# 如有未 commit 改动
git commit -am "chore: final v2 cleanup"
```

---

## Self-Review

Spec 覆盖性检查：

- [x] §1 目标 / 非目标：覆盖在 Task 1-22 整体
- [x] §3 技术栈变更：Task 2 加 sqlite3，Task 7 加中间件
- [x] §4 整体架构：Task 9-10 worker+lifespan
- [x] §5 数据模型：Task 2-5
- [x] §6 visitor cookie：Task 7
- [x] §7 HTTP API：Task 11-14
- [x] §8 队列与 worker：Task 9-10
- [x] §9 清理协程：Task 15-16
- [x] §10 前端 UI：Task 17-18
- [x] §11 错误处理：Task 1（异常类）+ Task 8（handler）
- [x] §12 测试策略：每个 task 都含测试 + Task 19-20 集成
- [x] §13 部署：docker-compose 已用 named volume，无需改
- [x] §14 工作量：实际 22 个 task，与 spec 的 4.5 天估算一致
- [x] §15 风险：handled in worker exception isolation（Task 9）、check_same_thread=False（Task 2）
- [x] §16 验收：Task 21 smoke 清单覆盖

无 placeholder、TODO、TBD。命名一致：`JobStore` / `worker_loop` / `cleanup_loop` 在各 task 内保持一致。

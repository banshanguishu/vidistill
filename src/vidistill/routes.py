import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, HttpUrl

from vidistill.adapters import video
from vidistill.config import Config
from vidistill.exceptions import (
    JobAccessDeniedError,
    JobNotCancellableError,
    JobNotFoundError,
    QueueFullError,
    VideoFetchError,
)
from vidistill.jobs import JobStore
from vidistill.models import JobState, Style
from vidistill.renderers.markdown import sanitize_filename


logger = logging.getLogger(__name__)

router = APIRouter()


class CreateJobRequest(BaseModel):
    url: HttpUrl
    style: Style = Field(default="chapters")


class CreateJobResponse(BaseModel):
    job_id: str
    queue_position: int


def get_templates() -> Jinja2Templates:
    templates_dir = Path(__file__).parent / "templates"
    return Jinja2Templates(directory=str(templates_dir))


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return get_templates().TemplateResponse(request, "index.html")


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


@router.get("/jobs/{job_id}/download/{fmt}")
def download(job_id: str, fmt: str, request: Request):
    if fmt not in ("md", "html", "pdf"):
        raise HTTPException(status_code=400, detail="不支持的格式")
    store: JobStore = request.app.state.store
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status != "done":
        raise HTTPException(status_code=409, detail=f"任务状态：{job.status}，文件尚未就绪")
    path_str = job.output_paths.get(fmt)
    if not path_str:
        raise HTTPException(status_code=404, detail=f"该任务未生成 {fmt} 格式（PDF 可能因环境缺失字体库未生成）")
    path = Path(path_str)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已失效，请重新提交任务")
    filename = sanitize_filename(job.video_title) + path.suffix
    return FileResponse(path=str(path), filename=filename)


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

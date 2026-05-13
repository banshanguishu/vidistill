import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, HttpUrl

from vidistill.adapters import video
from vidistill.config import Config
from vidistill.exceptions import VideoFetchError
from vidistill.jobs import JobStore
from vidistill.models import JobState, Style
from vidistill.pipeline import process_video
from vidistill.renderers.markdown import sanitize_filename


router = APIRouter()


class CreateJobRequest(BaseModel):
    url: HttpUrl
    style: Style = Field(default="chapters")


class CreateJobResponse(BaseModel):
    job_id: str


def get_templates() -> Jinja2Templates:
    templates_dir = Path(__file__).parent / "templates"
    return Jinja2Templates(directory=str(templates_dir))


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return get_templates().TemplateResponse(request, "index.html")


@router.post("/jobs", response_model=CreateJobResponse)
def create_job(
    req: CreateJobRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    store: JobStore = request.app.state.store
    config: Config = request.app.state.config

    try:
        meta = video.fetch_metadata(str(req.url))
    except VideoFetchError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if meta.duration > config.max_video_duration_seconds:
        minutes = meta.duration // 60
        raise HTTPException(
            status_code=422,
            detail=f"视频时长 {minutes} 分钟，超过 30 分钟上限",
        )

    if not store.try_acquire_slot():
        raise HTTPException(status_code=409, detail="另一个任务正在处理中，请稍后再试")

    job_id = uuid.uuid4().hex[:12]
    store.create(JobState(
        job_id=job_id,
        url=str(req.url),
        video_title=meta.title,
        style=req.style,
        status="pending",
        progress=0,
        error=None,
        output_paths={},
        created_at=datetime.now(),
    ))

    def _runner():
        try:
            process_video(
                job_id=job_id,
                url=str(req.url),
                style=req.style,
                store=store,
                config=config,
            )
        finally:
            store.release_slot()

    background_tasks.add_task(_runner)
    return CreateJobResponse(job_id=job_id)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    store: JobStore = request.app.state.store
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    available_formats = [fmt for fmt, path in job.output_paths.items() if path]
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
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

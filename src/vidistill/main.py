import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from vidistill.config import Config, load_config
from vidistill.exceptions import (
    VidistillError,
    QueueFullError,
    JobNotFoundError,
    JobNotCancellableError,
    JobAccessDeniedError,
    VideoFetchError,
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
        config = replace(
            config,
            output_dir=output_dir,
            log_dir=output_dir,
            db_path=output_dir / "vidistill.db",
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

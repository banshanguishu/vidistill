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

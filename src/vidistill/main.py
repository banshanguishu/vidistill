from pathlib import Path
from typing import Optional

from fastapi import FastAPI

from vidistill.config import Config, load_config
from vidistill.jobs import JobStore
from vidistill.logging_setup import setup_logging
from vidistill.routes import router


_GLOBAL_STORE = JobStore()


def get_store() -> JobStore:
    """Module-level accessor used by tests that seed jobs directly."""
    return _GLOBAL_STORE


def build_app(config: Optional[Config] = None, output_dir: Optional[Path] = None) -> FastAPI:
    """Construct a FastAPI app. Factored out so tests can inject overrides."""
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
            max_video_duration_seconds=config.max_video_duration_seconds,
            pipeline_timeout_seconds=config.pipeline_timeout_seconds,
            min_free_disk_mb=config.min_free_disk_mb,
        )
        config.output_dir.mkdir(parents=True, exist_ok=True)

    setup_logging(config.log_dir)

    app = FastAPI(title="vidistill")
    app.state.store = _GLOBAL_STORE
    app.state.config = config
    app.include_router(router)
    return app


app = build_app()

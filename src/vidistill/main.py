import logging
from dataclasses import replace
from pathlib import Path
from typing import Optional

from fastapi import FastAPI

from vidistill.config import Config, load_config
from vidistill.jobs import JobStore
from vidistill.logging_setup import setup_logging
from vidistill.middleware import VisitorCookieMiddleware
from vidistill.routes import router


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

    app = FastAPI(title="vidistill")
    app.add_middleware(VisitorCookieMiddleware)
    app.state.store = store
    app.state.config = config
    app.include_router(router)
    return app


app = build_app()

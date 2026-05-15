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

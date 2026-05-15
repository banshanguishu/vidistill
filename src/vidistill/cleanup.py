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

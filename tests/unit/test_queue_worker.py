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

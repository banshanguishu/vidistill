import threading
from datetime import datetime

import pytest

from vidistill.jobs import JobStore, SingleSlotBusyError
from vidistill.models import JobState


def _job(job_id="abc"):
    return JobState(
        job_id=job_id,
        url="https://x",
        style="short",
        format="md",
        status="pending",
        progress=0,
        error=None,
        output_path=None,
        created_at=datetime.now(),
    )


def test_create_and_get():
    store = JobStore()
    store.create(_job("j1"))
    fetched = store.get("j1")
    assert fetched is not None
    assert fetched.job_id == "j1"


def test_get_returns_none_for_unknown():
    store = JobStore()
    assert store.get("nope") is None


def test_update_modifies_fields():
    store = JobStore()
    store.create(_job("j1"))
    store.update("j1", status="transcribing", progress=30)
    j = store.get("j1")
    assert j.status == "transcribing"
    assert j.progress == 30


def test_update_unknown_raises():
    store = JobStore()
    with pytest.raises(KeyError):
        store.update("nope", status="done")


def test_concurrent_updates_are_safe():
    store = JobStore()
    store.create(_job("j1"))

    def worker(p):
        for _ in range(100):
            store.update("j1", progress=p)

    threads = [threading.Thread(target=worker, args=(p,)) for p in (10, 50, 90)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = store.get("j1")
    assert final.progress in (10, 50, 90)


def test_single_slot_acquire_and_release():
    store = JobStore()
    with store.acquire_slot():
        with pytest.raises(SingleSlotBusyError):
            with store.acquire_slot():
                pass

    # after release, can acquire again
    with store.acquire_slot():
        pass

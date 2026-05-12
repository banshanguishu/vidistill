import threading
from dataclasses import replace
from typing import Optional

from vidistill.models import JobState


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._slot_busy = False

    def create(self, job: JobState) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get(self, job_id: str) -> Optional[JobState]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown job_id: {job_id}")
            self._jobs[job_id] = replace(self._jobs[job_id], **kwargs)

    def try_acquire_slot(self) -> bool:
        with self._lock:
            if self._slot_busy:
                return False
            self._slot_busy = True
            return True

    def release_slot(self) -> None:
        with self._lock:
            self._slot_busy = False

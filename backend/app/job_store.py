"""Async file-job store: submit → poll → fetch pattern for Heroku's 30s limit.

Jobs run as background asyncio tasks.  Results are kept in-process with a TTL.
Phase 3 replaces this with a Redis-backed worker via a message broker.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class Job:
    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress_current: int = 0
    progress_total: int = 0
    result_filename: str | None = None
    result_content_type: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    completed_at: float | None = None
    _result_data: bytes | str | None = field(default=None, repr=False)


class JobStore:
    """In-process async job store with TTL-based cleanup."""

    def __init__(
        self,
        result_ttl_seconds: int = 3600,
        max_jobs: int = 200,
    ) -> None:
        self.result_ttl_seconds = result_ttl_seconds
        self.max_jobs = max_jobs
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def _cleanup(self) -> None:
        """Remove expired and excess jobs."""
        now = time.monotonic()
        expired = [
            jid
            for jid, job in self._jobs.items()
            if job.completed_at is not None
            and now - job.completed_at > self.result_ttl_seconds
        ]
        for jid in expired:
            self._jobs.pop(jid, None)
            task = self._tasks.pop(jid, None)
            if task and not task.done():
                task.cancel()

        # Enforce cap: remove oldest completed jobs first
        while len(self._jobs) > self.max_jobs:
            completed = [
                (jid, j)
                for jid, j in self._jobs.items()
                if j.status in (JobStatus.COMPLETE, JobStatus.FAILED)
            ]
            if not completed:
                break
            oldest_id = min(completed, key=lambda x: x[1].created_at)[0]
            self._jobs.pop(oldest_id, None)
            self._tasks.pop(oldest_id, None)

    def create_job(self) -> Job:
        """Create a new pending job and return it."""
        self._cleanup()
        job_id = uuid.uuid4().hex
        job = Job(job_id=job_id)
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Job | None:
        self._cleanup()
        return self._jobs.get(job_id)

    def set_running(self, job_id: str, total_chunks: int) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.RUNNING
            job.progress_total = total_chunks

    def update_progress(self, job_id: str, current: int) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.progress_current = current

    def set_complete(
        self,
        job_id: str,
        data: bytes | str,
        filename: str,
        content_type: str,
    ) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.COMPLETE
            job._result_data = data
            job.result_filename = filename
            job.result_content_type = content_type
            job.completed_at = time.monotonic()

    def set_failed(self, job_id: str, error: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error = error
            job.completed_at = time.monotonic()

    def get_result_data(self, job_id: str) -> bytes | str | None:
        job = self._jobs.get(job_id)
        if job and job.status == JobStatus.COMPLETE:
            return job._result_data
        return None

    def register_task(self, job_id: str, task: asyncio.Task[None]) -> None:
        self._tasks[job_id] = task

    def status_dict(self, job_id: str) -> dict[str, Any]:
        """Return a JSON-serializable status dict for the polling endpoint."""
        job = self.get_job(job_id)
        if job is None:
            return {"job_id": job_id, "status": "not_found"}
        result: dict[str, Any] = {
            "job_id": job.job_id,
            "status": job.status.value,
            "progress_current": job.progress_current,
            "progress_total": job.progress_total,
        }
        if job.status == JobStatus.COMPLETE:
            result["filename"] = job.result_filename
            result["content_type"] = job.result_content_type
        elif job.status == JobStatus.FAILED:
            result["error"] = job.error
        return result

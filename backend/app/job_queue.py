"""Simple in-process job queue: one worker, bounded size, results kept with a TTL.

State is lost on restart. A broker with a separate worker can replace this later.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable

from .backends import TranslationError

logger = logging.getLogger(__name__)

Progress = Callable[[int, int], None]
Work = Callable[[Progress], Awaitable[bytes]]


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class QueueFullError(RuntimeError):
    pass


@dataclass
class Job:
    job_id: str
    filename: str
    media_type: str
    work: Work | None
    key: str | None = None
    status: JobStatus = JobStatus.PENDING
    progress_current: int = 0
    progress_total: int = 0
    result: bytes | None = None
    error: str | None = None
    finished_at: float | None = None
    task: asyncio.Task[bytes] | None = None

    def set_progress(self, current: int, total: int) -> None:
        self.progress_current, self.progress_total = current, total

    def finish(
        self, status: JobStatus, result: bytes | None = None, error: str | None = None
    ) -> None:
        self.status, self.result, self.error = status, result, error
        self.finished_at = time.monotonic()
        self.work = None  # release the uploaded document


class JobQueue:
    def __init__(
        self, max_queued: int = 10, result_ttl_seconds: int = 3600, max_stored: int = 100
    ):
        self.result_ttl_seconds = result_ttl_seconds
        self.max_stored = max_stored
        self._queue: asyncio.Queue[Job] = asyncio.Queue(maxsize=max_queued)
        self._jobs: dict[str, Job] = {}
        self._worker: asyncio.Task[None] | None = None

    @property
    def size(self) -> int:
        return self._queue.qsize()

    def start(self) -> None:
        self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)

    async def join(self) -> None:
        await self._queue.join()

    def find(self, key: str) -> Job | None:
        """The waiting, running or successful job with this key. Failed jobs are retried."""
        self._cleanup()
        return next(
            (j for j in self._jobs.values() if j.key == key and j.status != JobStatus.FAILED),
            None,
        )

    def submit(self, work: Work, filename: str, media_type: str, key: str | None = None) -> Job:
        self._cleanup()
        job = Job(uuid.uuid4().hex, filename, media_type, work, key)
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull as exc:
            raise QueueFullError from exc
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        self._cleanup()
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.finished_at is not None:
            return False
        if job.task:
            job.task.cancel()
        job.finish(JobStatus.FAILED, error="Cancelled")
        return True

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if job.work is not None:  # None means cancelled while waiting
                    await self._process(job, job.work)
            finally:
                self._queue.task_done()

    async def _process(self, job: Job, work: Work) -> None:
        job.status = JobStatus.RUNNING
        job.task = asyncio.ensure_future(work(job.set_progress))
        # wait() does not raise, so cancelling one job leaves the worker running
        try:
            await asyncio.wait([job.task])
        except asyncio.CancelledError:
            job.task.cancel()
            raise
        if job.task.cancelled():
            return
        error = job.task.exception()
        if error is None:
            job.finish(JobStatus.COMPLETE, result=job.task.result())
        else:
            logger.error("File job %s failed", job.job_id, exc_info=error)
            message = (
                error.public_message
                if isinstance(error, TranslationError)
                else TranslationError.public_message
            )
            job.finish(JobStatus.FAILED, error=message)
        job.task = None

    def _cleanup(self) -> None:
        """Drop expired results, then the oldest ones above the cap."""
        finished = sorted(
            (j for j in self._jobs.values() if j.finished_at is not None),
            key=lambda j: j.finished_at,
        )
        expired_before = time.monotonic() - self.result_ttl_seconds
        excess = len(finished) - self.max_stored
        for index, job in enumerate(finished):
            if index < excess or job.finished_at < expired_before:
                del self._jobs[job.job_id]

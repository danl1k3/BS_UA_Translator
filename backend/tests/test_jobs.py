import asyncio

import pytest
from app.job_queue import JobQueue, JobStatus, QueueFullError
from tests.fakes import FakeBackend, QuotaExceededError, make_client, submit, wait_for_job


async def _done(progress):
    progress(1, 1)
    return b"ok"


async def _drain(queue):
    await asyncio.wait_for(queue.join(), 1)


@pytest.mark.asyncio
async def test_jobs_run_one_at_a_time_in_order():
    queue = JobQueue()
    events = []

    def job(name):
        async def run(progress):
            events.append(f"start {name}")
            await asyncio.sleep(0.01)
            events.append(f"end {name}")
            return b""

        return run

    queue.start()
    queue.submit(job("a"), "a.txt", "text/plain")
    queue.submit(job("b"), "b.txt", "text/plain")
    await _drain(queue)
    await queue.stop()
    assert events == ["start a", "end a", "start b", "end b"]


@pytest.mark.asyncio
async def test_queue_is_bounded():
    queue = JobQueue(max_queued=1)
    queue.submit(_done, "a", "text/plain")
    with pytest.raises(QueueFullError):
        queue.submit(_done, "b", "text/plain")


@pytest.mark.asyncio
async def test_cancelling_a_running_job_stops_it_and_the_worker_continues():
    queue = JobQueue()
    started = asyncio.Event()

    async def forever(progress):
        started.set()
        await asyncio.sleep(60)
        return b""

    queue.start()
    first = queue.submit(forever, "a", "text/plain")
    second = queue.submit(_done, "b", "text/plain")
    await started.wait()
    assert queue.cancel(first.job_id)
    await _drain(queue)
    await queue.stop()
    assert (first.status, second.status) == (JobStatus.FAILED, JobStatus.COMPLETE)


@pytest.mark.asyncio
async def test_finished_jobs_expire_and_are_capped():
    queue = JobQueue(result_ttl_seconds=60, max_stored=2)
    queue.start()
    jobs = [queue.submit(_done, str(i), "text/plain") for i in range(3)]
    await _drain(queue)
    await queue.stop()
    assert queue.get(jobs[0].job_id) is None
    assert queue.get(jobs[2].job_id) is not None
    jobs[2].finished_at -= 120
    assert queue.get(jobs[2].job_id) is None


def test_submit_poll_fetch_reports_progress():
    with make_client() as client:
        job_id = submit(client, "привіт.txt").json()["job_id"]
        status = wait_for_job(client, job_id)
        assert status["status"] == "complete"
        assert (status["progress_current"], status["progress_total"]) == (1, 1)
        assert status["filename"] == "привіт_translated.txt"
        result = client.get("/translate/file/result", params={"job_id": job_id})
        assert result.text == "DOBAR DAN."
        assert "filename*=UTF-8''" in result.headers["content-disposition"]


def test_failed_job_shows_safe_message():
    with make_client(FakeBackend(QuotaExceededError("secret details"))) as client:
        job_id = submit(client).json()["job_id"]
        status = wait_for_job(client, job_id)
        assert status["error"] == QuotaExceededError.public_message
        result = client.get("/translate/file/result", params={"job_id": job_id})
        assert result.status_code == 409


@pytest.mark.parametrize("path", ["status", "result"])
def test_unknown_job(path):
    with make_client() as client:
        resp = client.get(f"/translate/file/{path}", params={"job_id": "nope"})
        assert resp.status_code == 404


def test_upload_limits():
    with make_client(max_upload_bytes=10, max_file_chars=5) as client:
        assert submit(client, data=b"x" * 100_000).status_code == 413  # by Content-Length
        assert submit(client, data=b"x" * 11).status_code == 413
        assert submit(client, data=b"x" * 8).status_code == 413  # too much text
        assert submit(client, name="a.exe").status_code == 415


def test_upload_without_content_length_is_rejected():
    with make_client() as client:
        resp = client.post(
            "/translate/file/submit",
            content=iter([b"x"]),
            headers={"Content-Type": "multipart/form-data; boundary=x"},
        )
        assert resp.status_code == 411


def test_unsupported_language_pair():
    with make_client() as client:
        resp = client.post(
            "/translate/file/submit",
            params={"source_lang": "eng_Latn"},
            files={"upload_file": ("a.txt", b"x")},
        )
        assert resp.status_code == 400

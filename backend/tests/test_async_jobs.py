"""Tests for the async file job submit/poll/fetch pattern."""

import io
import time

from app.config import Settings
from app.job_store import JobStatus, JobStore
from app.main import create_app
from fastapi.testclient import TestClient

from tests.test_endpoints import MockBackend


def _client(**kwargs) -> TestClient:
    settings = Settings(**kwargs)
    app = create_app(settings=settings, backend=MockBackend())
    return TestClient(app)


def test_job_store_lifecycle():
    store = JobStore(result_ttl_seconds=3600, max_jobs=10)
    job = store.create_job()
    assert job.status == JobStatus.PENDING

    store.set_running(job.job_id, total_chunks=5)
    assert store.get_job(job.job_id).status == JobStatus.RUNNING

    store.update_progress(job.job_id, 3)
    status = store.status_dict(job.job_id)
    assert status["progress_current"] == 3
    assert status["progress_total"] == 5

    store.set_complete(job.job_id, b"result data", "test.txt", "text/plain")
    assert store.get_job(job.job_id).status == JobStatus.COMPLETE
    assert store.get_result_data(job.job_id) == b"result data"


def test_job_store_ttl_cleanup():
    store = JobStore(result_ttl_seconds=1, max_jobs=10)
    job = store.create_job()
    store.set_complete(job.job_id, "data", "f.txt", "text/plain")

    # Simulate expiry
    store._jobs[job.job_id].completed_at = time.monotonic() - 10
    assert store.get_job(job.job_id) is None


def test_job_store_max_jobs_cap():
    store = JobStore(result_ttl_seconds=3600, max_jobs=2)
    j1 = store.create_job()
    store.set_complete(j1.job_id, "a", "a.txt", "text/plain")
    j2 = store.create_job()
    store.set_complete(j2.job_id, "b", "b.txt", "text/plain")
    j3 = store.create_job()
    store.set_complete(j3.job_id, "c", "c.txt", "text/plain")

    # Oldest completed job should be evicted
    assert store.get_job(j1.job_id) is None
    assert store.get_job(j2.job_id) is not None or store.get_job(j3.job_id) is not None


def test_submit_poll_fetch():
    client = _client()

    # Submit
    resp = client.post(
        "/translate/file/submit",
        files={"upload_file": ("hello.txt", io.BytesIO(b"Dobar dan."), "text/plain")},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert job_id

    # Poll until complete (in tests this should be instant since MockBackend is sync-like)
    import time as _time

    for _ in range(20):
        status_resp = client.get(f"/translate/file/status?job_id={job_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        if data["status"] == "complete":
            break
        _time.sleep(0.1)
    else:
        raise AssertionError("Job did not complete in time")

    assert data["filename"] == "hello_translated.txt"

    # Fetch result
    result_resp = client.get(f"/translate/file/result?job_id={job_id}")
    assert result_resp.status_code == 200
    assert "[bos_Latn->ukr_Cyrl] Dobar dan." in result_resp.text


def test_status_not_found():
    client = _client()
    resp = client.get("/translate/file/status?job_id=nonexistent")
    assert resp.status_code == 404


def test_result_not_found():
    client = _client()
    resp = client.get("/translate/file/result?job_id=nonexistent")
    assert resp.status_code == 404

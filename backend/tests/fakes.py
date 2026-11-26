import time

from app.backends import QuotaExceededError, TranslatorBackend
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


class FakeBackend(TranslatorBackend):
    """Upper-cases every line, like the Space keeps one output line per input line."""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[str] = []

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        self.calls.append(text)
        if self.error:
            raise self.error
        return text.upper()

    async def check_health(self) -> dict[str, object]:
        return {"status": "Normal", "reachable": True}


def make_client(backend: FakeBackend | None = None, **settings) -> TestClient:
    settings.setdefault("rate_limit_burst", 100)
    cfg = Settings(_env_file=None, **settings)
    return TestClient(create_app(settings=cfg, backend=backend or FakeBackend()))


def submit(client: TestClient, name: str = "a.txt", data: bytes = b"Dobar dan."):
    return client.post("/translate/file/submit", files={"upload_file": (name, data)})


def wait_for_job(client: TestClient, job_id: str) -> dict:
    for _ in range(200):
        status = client.get("/translate/file/status", params={"job_id": job_id}).json()
        if status["status"] in ("complete", "failed"):
            return status
        time.sleep(0.01)
    raise AssertionError("Job did not finish")


__all__ = ["FakeBackend", "QuotaExceededError", "make_client", "submit", "wait_for_job"]

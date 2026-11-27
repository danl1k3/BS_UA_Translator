import asyncio
import threading
import time

from app.backends import TranslationError
from fakes import FakeBackend, make_client, submit, wait_for_job


class SlowBackend(FakeBackend):
    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        result = await super().translate(text, source_lang, target_lang)
        await asyncio.sleep(0.5)
        return result


def translate(client, text="Dobar dan.", **extra):
    return client.post("/translate/stream", json={"text": text, **extra}).text


def test_repeated_text_is_answered_without_calling_backend():
    backend = FakeBackend()
    with make_client(backend) as client:
        first = translate(client)
        second = translate(client)
    assert "event: notice" not in first
    assert "This text is already translated" in second
    assert "DOBAR DAN." in second
    assert len(backend.calls) == 1


def test_other_direction_is_a_new_translation():
    backend = FakeBackend()
    with make_client(backend) as client:
        translate(client)
        translate(client, source_lang="ukr_Cyrl", target_lang="bos_Latn")
    assert len(backend.calls) == 2


def test_another_visitor_learns_nothing_about_earlier_text():
    backend = FakeBackend()
    with make_client(backend) as client:
        translate(client)
        client.cookies.clear()
        other = translate(client)
    assert "event: notice" not in other
    assert len(backend.calls) == 2


def test_failed_text_can_be_retried():
    backend = FakeBackend(error=TranslationError("boom"))
    with make_client(backend) as client:
        translate(client)
        backend.error = None
        retry = translate(client)
    assert "DOBAR DAN." in retry
    assert "event: notice" not in retry


def test_text_in_progress_is_not_sent_twice():
    backend = SlowBackend()
    with make_client(backend) as client:
        translate(client, "Prvi.")  # gets the session cookie
        first = threading.Thread(target=translate, args=(client,))
        first.start()
        while len(backend.calls) < 2:
            time.sleep(0.01)
        second = translate(client)
        first.join()
        after = translate(client)
    assert "This text is already being translated" in second
    assert "event: message" not in second
    assert "This text is already translated" in after
    assert len(backend.calls) == 2


def test_repeated_file_returns_the_running_then_finished_job():
    backend = SlowBackend()
    with make_client(backend) as client:
        first = submit(client).json()
        running = submit(client).json()
        wait_for_job(client, first["job_id"])
        finished = submit(client).json()
    assert first["duplicate"] is None
    assert running["job_id"] == finished["job_id"] == first["job_id"]
    assert running["duplicate"] == "processing"
    assert finished["duplicate"] == "complete"
    assert len(backend.calls) == 1


def test_file_of_another_visitor_gets_its_own_job():
    with make_client() as client:
        first = submit(client).json()
        client.cookies.clear()
        other = submit(client).json()
    assert other["job_id"] != first["job_id"]
    assert other["duplicate"] is None


def test_failed_file_can_be_submitted_again():
    backend = FakeBackend(error=TranslationError("boom"))
    with make_client(backend) as client:
        first = submit(client).json()
        wait_for_job(client, first["job_id"])
        again = submit(client).json()
    assert again["job_id"] != first["job_id"]
    assert again["duplicate"] is None

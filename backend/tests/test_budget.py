from app.backends import QuotaExceededError, TranslationError
from app.budget import DailyBudget
from fakes import FakeBackend, make_client, submit, wait_for_job

TEXT = "Dobar dan."  # 10 characters


def translate(client, text=TEXT, ip="203.0.113.1"):
    return client.post(
        "/translate/stream", json={"text": text}, headers={"X-Forwarded-For": ip}
    ).text


def test_budget_is_per_key_and_refundable():
    budget = DailyBudget(limit=10)
    assert budget.try_spend("a", 6)
    assert not budget.try_spend("a", 5)
    assert budget.try_spend("b", 10)
    budget.refund("a", 6)
    assert budget.try_spend("a", 10)


def test_budget_resets_a_day_after_first_use(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("app.budget.time.monotonic", lambda: now[0])
    budget = DailyBudget(limit=10)
    assert budget.try_spend("a", 10)
    now[0] += 86399
    assert not budget.try_spend("a", 1)
    now[0] += 2
    assert budget.try_spend("a", 10)


def test_budget_forgets_the_oldest_key_when_full():
    budget = DailyBudget(limit=10, max_entries=2)
    for key in ("a", "b", "c"):
        budget.try_spend(key, 10)
    assert budget.try_spend("a", 10)
    assert not budget.try_spend("c", 1)


def test_text_over_the_daily_limit_is_not_translated():
    backend = FakeBackend()
    with make_client(backend, daily_chars_per_ip=15) as client:
        translate(client)
        refused = translate(client, "Laku noc.")
        other_ip = translate(client, "Laku noc.", ip="203.0.113.2")
    assert "event: limit" in refused
    assert "your daily limit" in refused
    assert "LAKU NOC." in other_ip
    assert len(backend.calls) == 2


def test_repeated_text_costs_nothing():
    with make_client(daily_chars_per_ip=15) as client:
        translate(client)
        assert "DOBAR DAN." in translate(client)


def test_used_up_shared_quota_is_a_limit_event_and_is_refunded():
    backend = FakeBackend(error=QuotaExceededError("quota"))
    with make_client(backend, daily_chars_per_ip=15) as client:
        first = translate(client)
        backend.error = None
        second = translate(client)
    assert "event: limit" in first
    assert "shared translation limit" in first
    assert "DOBAR DAN." in second


def test_failed_translation_is_refunded():
    backend = FakeBackend(error=TranslationError("boom"))
    with make_client(backend, daily_chars_per_ip=15) as client:
        assert "event: error" in translate(client)
        backend.error = None
        assert "DOBAR DAN." in translate(client)


def test_file_over_the_daily_limit_is_refused():
    backend = FakeBackend()
    with make_client(backend, daily_chars_per_ip=15) as client:
        wait_for_job(client, submit(client).json()["job_id"])
        repeat = submit(client)
        refused = submit(client, "b.txt", b"Laku noc.")
    assert repeat.status_code == 200
    assert refused.status_code == 429
    assert "your daily limit" in refused.json()["detail"]
    assert len(backend.calls) == 1


def test_failed_file_is_refunded():
    backend = FakeBackend(error=TranslationError("boom"))
    with make_client(backend, daily_chars_per_ip=15) as client:
        wait_for_job(client, submit(client).json()["job_id"])
        assert submit(client).status_code == 200


def test_direct_call_is_prepared_without_spending_anything():
    backend = FakeBackend()
    settings = {"daily_chars_per_ip": 0, "remote_inference_url": "https://owner-space.hf.space/"}
    with make_client(backend, **settings) as client:
        response = client.post(
            "/translate/direct",
            json={
                "text": "Prva. Druga.\n\nTre​ca.",
                "source_lang": "ukr_Cyrl",
                "target_lang": "bos_Latn",
            },
        )
    assert response.json() == {
        "url": "https://owner-space.hf.space",
        "direction": "ua-bs",
        "batches": ["Prva.\nDruga.\nTreca."],
        "layout": [2, 0, 1],
    }
    assert response.headers["cache-control"] == "no-store"
    assert backend.calls == []


def test_direct_call_checks_input():
    with make_client(remote_inference_url="https://owner-space.hf.space") as client:
        assert client.post("/translate/direct", json={"text": " "}).status_code == 400
        too_long = client.post("/translate/direct", json={"text": "a" * 2001})
    assert too_long.status_code == 422

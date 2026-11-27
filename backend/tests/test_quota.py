import httpx
import pytest
from app.backends import GradioBackend
from fakes import FakeBackend, make_client

PAYLOAD = {"base": 300, "current": 205.5, "resetsAt": "2026-11-28T09:00:00.000Z"}


def backend_with(handler, token="hf_test"):
    transport = httpx.MockTransport(handler)
    return GradioBackend("https://space.example", api_token=token, transport=transport)


@pytest.mark.asyncio
async def test_reads_quota_of_the_token_owner():
    seen = []

    def handler(request):
        seen.append((str(request.url), request.headers["authorization"]))
        return httpx.Response(200, json=PAYLOAD)

    backend = backend_with(handler)
    expected = {
        "remaining_seconds": 205,
        "total_seconds": 300,
        "resets_at": "2026-11-28T09:00:00.000Z",
    }
    assert await backend.get_quota() == expected
    assert await backend.get_quota() == expected  # cached
    assert seen == [("https://huggingface.co/api/spaces/zero-gpu/quota", "Bearer hf_test")]


@pytest.mark.asyncio
async def test_negative_remaining_is_shown_as_zero():
    backend = backend_with(lambda r: httpx.Response(200, json={"base": 300, "current": -4}))
    quota = await backend.get_quota()
    assert quota["remaining_seconds"] == 0
    assert quota["resets_at"] is None


@pytest.mark.asyncio
async def test_unreadable_quota_is_none():
    for response in (
        httpx.Response(403, json={"error": "forbidden"}),
        httpx.Response(200, json={"unexpected": 1}),
        httpx.Response(200, text="not json"),
    ):
        assert await backend_with(lambda r, response=response: response).get_quota() is None


@pytest.mark.asyncio
async def test_no_token_means_no_request():
    def handler(request):
        raise AssertionError("must not be called")

    assert await backend_with(handler, token="").get_quota() is None


@pytest.mark.asyncio
async def test_translation_refreshes_the_quota():
    remaining = iter([300, 290])

    def handler(request):
        if request.url.host == "huggingface.co":
            return httpx.Response(200, json={"base": 300, "current": next(remaining)})
        if request.method == "POST":
            return httpx.Response(200, json={"event_id": "1"})
        return httpx.Response(200, text='event: complete\ndata: ["x"]\n\n')

    backend = backend_with(handler)
    assert (await backend.get_quota())["remaining_seconds"] == 300
    await backend.translate("a", "bos_Latn", "ukr_Cyrl")
    assert (await backend.get_quota())["remaining_seconds"] == 290


def test_quota_endpoint():
    class Backend(FakeBackend):
        async def get_quota(self):
            return {"remaining_seconds": 5, "total_seconds": 300, "resets_at": None}

    with make_client(Backend()) as client:
        response = client.get("/quota")
    assert response.json()["quota"]["remaining_seconds"] == 5
    assert response.headers["cache-control"] == "no-store"
    with make_client() as client:
        assert client.get("/quota").json() == {"quota": None}

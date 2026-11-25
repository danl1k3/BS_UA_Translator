import time
from unittest.mock import MagicMock

from app.backends import TranslatorBackend
from app.file_translator import FileTranslationManager


class _DummyBackend(TranslatorBackend):
    async def translate_stream(self, text, source_lang, target_lang):
        yield text


def _make_file_manager(**kwargs) -> FileTranslationManager:
    return FileTranslationManager(
        queue_manager=MagicMock(),
        backend=_DummyBackend(),
        **kwargs,
    )


def test_distribute_to_runs_empty_or_zero_length():
    fm = _make_file_manager()
    runs = [{"text": ""}, {"text": ""}]
    assert fm._distribute_to_runs("Привіт світ", runs) == ["Привіт світ", ""]


def test_distribute_to_runs_preserves_word_boundaries():
    fm = _make_file_manager()
    runs = [
        {"text": "Hello ", "bold": True},
        {"text": "world!", "bold": False},
    ]
    allocated = fm._distribute_to_runs("Привіт світе!", runs)
    assert len(allocated) == 2
    assert "".join(allocated) == "Привіт світе!"
    for part in allocated:
        assert not part.endswith("При")
        assert not part.startswith("віт")


def test_distribute_to_runs_single_run():
    fm = _make_file_manager()
    runs = [{"text": "Some long text here"}]
    assert fm._distribute_to_runs("Якийсь довгий текст тут", runs) == [
        "Якийсь довгий текст тут"
    ]


def test_results_ttl_and_size_cap():
    fm = _make_file_manager(result_ttl_seconds=1, max_stored_results=2)
    fm._store_result("job1", {"data": "a"})
    fm._store_result("job2", {"data": "b"})
    fm._store_result("job3", {"data": "c"})

    assert fm.fetch_result("job1") is None
    assert fm.fetch_result("job2") is not None
    assert fm.fetch_result("job3") is not None

    fm._results["job2"]["created_at"] = time.monotonic() - 10
    assert fm.fetch_result("job2") is None

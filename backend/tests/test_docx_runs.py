from unittest.mock import MagicMock

from app.file_translator import FileTranslationManager


def _make_file_manager() -> FileTranslationManager:
    return FileTranslationManager(queue_manager=MagicMock(), translator=MagicMock())


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

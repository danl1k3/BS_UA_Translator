import re
from unittest.mock import MagicMock, patch

from app.translator import NLLBTranslator


def _make_translator() -> NLLBTranslator:
    with patch("os.path.exists", return_value=True):
        t = NLLBTranslator.__new__(NLLBTranslator)
        t.sentence_regex = re.compile(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s")
        t.sp = MagicMock()
        t.translators = {}
        return t


def test_split_empty_and_whitespace():
    t = _make_translator()
    assert t._split_into_sentences("") == []
    assert t._split_into_sentences("   \n\t  ") == []


def test_split_single_sentence():
    t = _make_translator()
    assert t._split_into_sentences("Zdravo svijete.") == ["Zdravo svijete."]


def test_split_multiple_sentences():
    t = _make_translator()
    text = "Prva rečenica. Druga rečenica! Treća rečenica?"
    assert t._split_into_sentences(text) == [
        "Prva rečenica.",
        "Druga rečenica!",
        "Treća rečenica?",
    ]


def test_split_preserves_abbreviations():
    t = _make_translator()
    text = "Dr. Petrović je došao. Sve je u redu."
    assert t._split_into_sentences(text) == [
        "Dr. Petrović je došao.",
        "Sve je u redu.",
    ]

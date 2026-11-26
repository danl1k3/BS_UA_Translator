import pytest
from app.backends import TranslationError
from app.batching import MAX_BATCH_CHARS, MAX_SEGMENT_CHARS, split_segments, translate_texts
from tests.fakes import FakeBackend


async def _translate(texts, backend=None, **kwargs):
    return await translate_texts(
        backend or FakeBackend(), texts, "bos_Latn", "ukr_Cyrl", **kwargs
    )


def test_splits_sentences_and_keeps_abbreviations():
    assert split_segments("Dr. Petrović je došao. Sve je u redu!") == [
        "Dr. Petrović je došao.",
        "Sve je u redu!",
    ]
    assert split_segments("   ") == []


@pytest.mark.parametrize(
    "sentence",
    [
        "riječ, " * 100,  # long sentence with clauses
        "riječ " * 100,  # no punctuation
        "x" * 1000,  # no spaces at all
    ],
)
def test_long_sentence_is_cut_below_the_model_limit(sentence):
    segments = split_segments(sentence)
    assert all(len(s) <= MAX_SEGMENT_CHARS for s in segments)
    assert "".join(segments).replace(" ", "") == sentence.replace(" ", "")


def test_long_sentence_is_cut_at_a_clause_boundary():
    first = "a" * 150 + ","
    assert split_segments(f"{first} {'b' * 150}.") == [first, "b" * 150 + "."]


@pytest.mark.asyncio
async def test_preserves_line_breaks_and_text_boundaries():
    result = await _translate(["Jedan. Dva.\n\nTri.", "", "Četiri."])
    assert result == ["JEDAN. DVA.\n\nTRI.", "", "ČETIRI."]


@pytest.mark.asyncio
async def test_many_paragraphs_share_few_calls():
    backend = FakeBackend()
    texts = [f"Rečenica broj {i} u dokumentu." for i in range(300)]
    progress = []
    result = await _translate(texts, backend, on_progress=lambda *p: progress.append(p))
    assert result == [t.upper() for t in texts]
    assert len(backend.calls) <= 6
    assert all(len(call) <= MAX_BATCH_CHARS for call in backend.calls)
    total = len(backend.calls)
    assert progress == [(i, total) for i in range(total + 1)]


@pytest.mark.asyncio
async def test_unexpected_line_count_is_an_error():
    class Merging(FakeBackend):
        async def translate(self, text, source_lang, target_lang):
            return "one line"

    with pytest.raises(TranslationError):
        await _translate(["Jedan. Dva."], Merging())

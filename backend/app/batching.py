"""Fit text into the limits of the model and the Space.

The Space cuts every sentence at 128 tokens and every request at 2000 characters.
Text is therefore sent as one short segment per line, batched into few requests.
"""

import re
from typing import Callable

from .backends import TranslationError, TranslatorBackend

# Dense text (numbers, URLs) is about 2 characters per token with the NLLB tokenizer.
MAX_SEGMENT_CHARS = 220
MAX_BATCH_CHARS = 2000

# Same rule the Space uses, so it does not split our segments differently.
_SENTENCE_END = re.compile(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s")


def _cut_point(sentence: str) -> int:
    """Where to cut a long sentence: after a clause, else at a space, else anywhere."""
    window = sentence[: MAX_SEGMENT_CHARS + 1]
    for pattern in (r"[,;:](?=\s)", r"(?=\s)"):
        ends = [m.end() for m in re.finditer(pattern, window)]
        # Ignore very early boundaries, they would produce tiny fragments
        ends = [e for e in ends if MAX_SEGMENT_CHARS // 3 <= e <= MAX_SEGMENT_CHARS]
        if ends:
            return ends[-1]
    return MAX_SEGMENT_CHARS


def split_segments(line: str) -> list[str]:
    """Split one line into sentences no longer than MAX_SEGMENT_CHARS."""
    segments: list[str] = []
    for sentence in _SENTENCE_END.split(line.strip()):
        sentence = sentence.strip()
        while len(sentence) > MAX_SEGMENT_CHARS:
            cut = _cut_point(sentence)
            segments.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            segments.append(sentence)
    return segments


def _batches(segments: list[str]) -> list[list[str]]:
    batches: list[list[str]] = []
    size = 0
    for segment in segments:
        if not batches or size + len(segment) + 1 > MAX_BATCH_CHARS:
            batches.append([])
            size = -1
        batches[-1].append(segment)
        size += len(segment) + 1
    return batches


async def translate_texts(
    backend: TranslatorBackend,
    texts: list[str],
    source_lang: str,
    target_lang: str,
    on_progress: Callable[[int, int], None] = lambda done, total: None,
) -> list[str]:
    """Translate several texts together, keeping their line breaks."""
    layout = [[split_segments(line) for line in text.split("\n")] for text in texts]
    batches = _batches([s for lines in layout for line in lines for s in line])

    translated: list[str] = []
    on_progress(0, len(batches))
    for number, batch in enumerate(batches, start=1):
        result = await backend.translate("\n".join(batch), source_lang, target_lang)
        lines = result.split("\n")
        if len(lines) != len(batch):
            raise TranslationError(f"Expected {len(batch)} lines, got {len(lines)}")
        translated.extend(line.strip() for line in lines)
        on_progress(number, len(batches))

    pieces = iter(translated)
    return [
        "\n".join(" ".join(next(pieces) for _ in line) for line in lines) for lines in layout
    ]

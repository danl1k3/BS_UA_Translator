import re

SENTENCE_REGEX = re.compile(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s")


def split_sentences(text: str) -> list[str]:
    """Split input text into individual sentences."""
    cleaned = text.strip()
    if not cleaned:
        return []
    sentences = SENTENCE_REGEX.split(cleaned)
    return [s.strip() for s in sentences if s.strip()]

"""Clean user input before it is translated or put into a file name.

Only invisible characters are removed. Visible text, markup included, is left as
it is: it is data to translate, and the frontend escapes it on output.
"""

import re
import unicodedata

# Soft hyphen, zero-width space, word joiner, BOM and text-direction controls.
# Zero-width (non-)joiners stay: emoji and some scripts need them.
_INVISIBLE = re.compile("[­​‎‏‪-‮⁠⁦-⁩﻿]")
_LINE_BREAKS = re.compile("\r\n|\r| | ")
MAX_FILE_STEM_CHARS = 100


def _clean_char(char: str) -> str:
    if char in "\n\t":
        return char
    category = unicodedata.category(char)
    if category == "Cc":
        return " " if char.isspace() else ""
    return "" if category == "Cs" else char


def clean_text(text: str) -> str:
    """Normalize line breaks and Unicode, drop control and invisible characters."""
    text = _INVISIBLE.sub("", _LINE_BREAKS.sub("\n", text))
    return unicodedata.normalize("NFC", "".join(map(_clean_char, text)))


def clean_filename(name: str) -> str:
    """A short file name without path parts, keeping the extension."""
    name = re.split(r"[/\\]", clean_text(name))[-1]
    name = " ".join(name.split())
    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""
    stem = stem.strip(". ")[:MAX_FILE_STEM_CHARS] or "document"
    return f"{stem}{dot}{extension}"

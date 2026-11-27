"""Read uploaded files into translatable texts and rebuild them afterwards."""

import html
import io
import os
import re
import zipfile
from dataclasses import dataclass
from typing import Callable

from docx import Document
from docx.oxml.ns import qn
from docx.text.run import Run

MAX_DOCX_UNPACKED_BYTES = 30 * 1024 * 1024
# Runs holding these would lose them if their text were replaced
_OBJECTS_IN_RUN = "./w:drawing | ./w:pict | ./w:object | ./w:fldChar | ./w:footnoteReference"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocumentError(ValueError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ParsedDocument:
    texts: list[str]
    build: Callable[[list[str]], bytes]
    media_type: str


def _decode(raw: bytes, source_lang: str) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        legacy = "cp1251" if source_lang == "ukr_Cyrl" else "cp1250"
        return raw.decode(legacy, errors="replace")


def _parse_txt(raw: bytes, source_lang: str) -> ParsedDocument:
    text = _decode(raw, source_lang)
    newline = "\r\n" if "\r\n" in text else "\n"
    return ParsedDocument(
        [text.replace("\r\n", "\n")],
        lambda result: result[0].replace("\n", newline).encode(),
        "text/plain; charset=utf-8",
    )


def _parse_html(raw: bytes, source_lang: str) -> ParsedDocument:
    """Keeps paragraph text only; the result is a list of <p> elements."""
    text = _decode(raw, source_lang)
    parts = re.findall(r"<p\b[^>]*>(.*?)</p>", text, flags=re.S | re.I)
    if not parts:
        parts = re.split(r"\n\s*\n", text)
    cleaned = [html.unescape(re.sub(r"<[^>]+>", "", part)).strip() for part in parts]
    return ParsedDocument(
        [" ".join(part.split()) for part in cleaned if part],
        lambda result: "\n".join(
            f"<p>{html.escape(part, quote=False)}</p>" for part in result
        ).encode(),
        "text/html; charset=utf-8",
    )


def _distribute(translated: str, lengths: list[int]) -> list[str]:
    """Split text between runs in proportion to their lengths, keeping words whole."""
    scale = len(translated) / sum(lengths)
    boundaries = [sum(lengths[: i + 1]) * scale for i in range(len(lengths))]
    pieces = [""] * len(lengths)
    position = 0
    for token in re.split(r"(\s+)", translated):
        middle = position + len(token) / 2
        index = next((i for i, b in enumerate(boundaries) if middle <= b), len(lengths) - 1)
        pieces[index] += token
        position += len(token)
    return pieces


def _parse_docx(raw: bytes, source_lang: str) -> ParsedDocument:
    """Translates body paragraphs. Runs without text or with objects are not touched."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(i.file_size for i in archive.infolist()) > MAX_DOCX_UNPACKED_BYTES:
                raise DocumentError(413, "The document is too large")
        document = Document(io.BytesIO(raw))
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError(400, "Could not read the .docx file") from exc

    paragraphs: list[list[Run]] = []
    for paragraph in document.paragraphs:
        # Includes runs inside hyperlinks, which paragraph.runs leaves out
        elements = paragraph._p.xpath("./w:r | ./w:hyperlink/w:r")
        runs = [
            Run(e, paragraph)
            for e in elements
            if e.find(qn("w:t")) is not None and not e.xpath(_OBJECTS_IN_RUN)
        ]
        if "".join(run.text for run in runs).strip():
            paragraphs.append(runs)

    def build(result: list[str]) -> bytes:
        for runs, translated in zip(paragraphs, result, strict=True):
            pieces = _distribute(translated, [len(run.text) or 1 for run in runs])
            for run, piece in zip(runs, pieces):
                run.text = piece
        out = io.BytesIO()
        document.save(out)
        return out.getvalue()

    texts = ["".join(run.text for run in runs) for runs in paragraphs]
    return ParsedDocument(texts, build, DOCX_TYPE)


_PARSERS = {".txt": _parse_txt, ".html": _parse_html, ".htm": _parse_html, ".docx": _parse_docx}


def parse_document(filename: str, raw: bytes, source_lang: str) -> ParsedDocument:
    parser = _PARSERS.get(os.path.splitext(filename.lower())[1])
    if parser is None:
        raise DocumentError(415, "This file type is not supported")
    document = parser(raw, source_lang)
    if not any(text.strip() for text in document.texts):
        raise DocumentError(400, "The file has no text to translate")
    return document

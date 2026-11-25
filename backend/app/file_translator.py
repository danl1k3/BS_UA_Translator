import asyncio
import base64
import io
import logging
import os
import re
import time
from typing import AsyncGenerator, List, Tuple

from docx import Document as DocxDocument
from fastapi import UploadFile

from .backends import TranslatorBackend

logger = logging.getLogger(__name__)


class FileTranslationManager:
    """Manages file parsing, chunked concurrent translation, and document reconstruction."""

    def __init__(
        self,
        queue_manager,
        backend: TranslatorBackend,
        max_chunk_chars: int = 800,
        concurrency: int = 4,
        result_ttl_seconds: int = 3600,
        max_stored_results: int = 100,
    ):
        self.queue_manager = queue_manager
        self.backend = backend
        self.max_chunk_chars = max_chunk_chars
        self.sema = asyncio.Semaphore(concurrency)
        self.result_ttl_seconds = result_ttl_seconds
        self.max_stored_results = max_stored_results
        self._results: dict[str, dict] = {}

    def _cleanup_results(self) -> None:
        """Evict expired results and enforce max_stored_results cap."""
        now = time.monotonic()
        expired = [
            k
            for k, v in self._results.items()
            if now - v.get("created_at", 0) > self.result_ttl_seconds
        ]
        for k in expired:
            self._results.pop(k, None)

        while len(self._results) > self.max_stored_results:
            oldest_key = min(
                self._results, key=lambda k: self._results[k].get("created_at", 0)
            )
            self._results.pop(oldest_key, None)

    def _store_result(self, job_id: str, entry: dict) -> None:
        self._cleanup_results()
        entry["created_at"] = time.monotonic()
        self._results[job_id] = entry
        self._cleanup_results()

    def fetch_result(self, job_id: str):
        """Return stored result by job_id if present and not expired, else None."""
        self._cleanup_results()
        return self._results.get(job_id)

    def _extract_document_parts(
        self, raw: bytes, filename: str | None, content_type: str | None
    ) -> tuple[list[str], list[dict], list[list[dict]], bool, bool]:
        lower_name = (filename or "").lower()
        is_docx = lower_name.endswith(".docx") or (
            bool(content_type) and "word" in (content_type or "").lower()
        )
        if is_docx:
            doc = DocxDocument(io.BytesIO(raw))
            paragraphs: list[str] = []
            para_meta: list[dict] = []
            para_runs: list[list[dict]] = []
            for p in doc.paragraphs:
                paragraphs.append(p.text or "")
                try:
                    style_name = p.style.name
                except Exception:
                    style_name = None
                para_meta.append({"style": style_name})
                para_runs.append(
                    [
                        {
                            "text": r.text or "",
                            "bold": bool(r.bold),
                            "italic": bool(r.italic),
                            "underline": bool(r.underline),
                        }
                        for r in p.runs
                    ]
                )
            return paragraphs, para_meta, para_runs, True, False

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        paragraphs, is_html = self._split_into_paragraphs(text, content_type)
        return paragraphs, [], [], False, is_html

    def _build_chunks(self, paragraphs: list[str]) -> List[Tuple[int, int, str]]:
        chunks: List[Tuple[int, int, str]] = []
        for p_idx, para in enumerate(paragraphs):
            sentences = self.backend.split_into_sentences(para)
            if not sentences:
                continue
            cur: list[str] = []
            cur_len = 0
            c_idx = 0
            for s in sentences:
                if cur_len + len(s) + 1 > self.max_chunk_chars and cur:
                    chunks.append((p_idx, c_idx, " ".join(cur)))
                    c_idx += 1
                    cur = [s]
                    cur_len = len(s)
                else:
                    cur.append(s)
                    cur_len += len(s) + 1
            if cur:
                chunks.append((p_idx, c_idx, " ".join(cur)))
        return chunks

    @staticmethod
    def _reconstruct_paragraphs(
        paragraphs_count: int,
        chunks: List[Tuple[int, int, str]],
        translated_chunks: dict[Tuple[int, int], str],
    ) -> list[str]:
        para_map: dict[int, list[tuple[int, str]]] = {}
        for p_idx, c_idx, _ in chunks:
            para_map.setdefault(p_idx, []).append(
                (c_idx, translated_chunks.get((p_idx, c_idx), ""))
            )

        reconstructed: list[str] = []
        for p_idx in range(paragraphs_count):
            items = sorted(para_map.get(p_idx, []), key=lambda x: x[0])
            joined = " ".join(txt for _, txt in items).strip()
            reconstructed.append(joined)
        return reconstructed

    def _build_docx_bytes(
        self,
        raw: bytes,
        reconstructed: list[str],
        para_meta: list[dict],
        para_runs: list[list[dict]],
        apply_heading_bold: bool = False,
    ) -> bytes:
        try:
            orig_doc = DocxDocument(io.BytesIO(raw))
        except Exception:
            new_doc = DocxDocument()
            for para_text in reconstructed:
                new_doc.add_paragraph(para_text)
            out = io.BytesIO()
            new_doc.save(out)
            return out.getvalue()

        for idx, para_text in enumerate(reconstructed):
            runs_meta = para_runs[idx] if idx < len(para_runs) else None
            p = (
                orig_doc.paragraphs[idx]
                if idx < len(orig_doc.paragraphs)
                else orig_doc.add_paragraph()
            )
            style_name = para_meta[idx].get("style") if idx < len(para_meta) else None
            is_heading = False
            if apply_heading_bold and isinstance(style_name, str):
                sn = style_name.lower()
                is_heading = sn.startswith("heading") or "title" in sn or "header" in sn

            if runs_meta and any(r.get("text") for r in runs_meta):
                allocated = self._distribute_to_runs(para_text, runs_meta)
                while len(p.runs) < len(allocated):
                    p.add_run("")
                for i, run_meta in enumerate(runs_meta):
                    text_piece = allocated[i] if i < len(allocated) else ""
                    try:
                        p.runs[i].text = text_piece
                        p.runs[i].bold = (
                            bool(run_meta.get("bold")) or is_heading
                            if apply_heading_bold
                            else run_meta.get("bold")
                        )
                        p.runs[i].italic = run_meta.get("italic")
                        p.runs[i].underline = run_meta.get("underline")
                    except Exception:
                        try:
                            p.runs[i].text = text_piece
                        except Exception:
                            pass
            else:
                if p.runs:
                    try:
                        p.runs[0].text = para_text
                        for r in p.runs[1:]:
                            r.text = ""
                    except Exception:
                        p.text = para_text
                else:
                    p.text = para_text

            if style_name:
                try:
                    p.style = style_name
                except Exception:
                    pass

        out = io.BytesIO()
        orig_doc.save(out)
        return out.getvalue()

    async def process_upload(
        self, upload_file: UploadFile, source_lang: str, target_lang: str
    ) -> str | bytes:
        raw = await upload_file.read()
        paragraphs, para_meta, para_runs, is_docx, is_html = self._extract_document_parts(
            raw, upload_file.filename, upload_file.content_type
        )
        chunks = self._build_chunks(paragraphs)
        translated_chunks: dict[Tuple[int, int], str] = {}

        async def translate_and_store(par_idx: int, ch_idx: int, chunk_text: str):
            async with self.sema:
                collected = []
                async for piece in self.queue_manager.stream_translation(
                    chunk_text, target_lang, source_lang
                ):
                    collected.append(piece)
                translated_chunks[(par_idx, ch_idx)] = "".join(collected).strip()

        tasks = [
            asyncio.create_task(translate_and_store(p, c, t)) for (p, c, t) in chunks
        ]
        try:
            if tasks:
                await asyncio.gather(*tasks)
        except BaseException:
            for t in tasks:
                t.cancel()
            raise

        reconstructed = self._reconstruct_paragraphs(
            len(paragraphs), chunks, translated_chunks
        )

        if is_docx:
            return self._build_docx_bytes(raw, reconstructed, para_meta, para_runs)
        if is_html:
            return "\n".join(f"<p>{self._escape_html(p)}</p>" for p in reconstructed)
        return "\n\n".join(reconstructed)

    def _split_into_paragraphs(self, text: str, content_type: str | None):
        is_html = False
        if content_type and "html" in content_type.lower():
            is_html = True
            paras = re.findall(r"<p[^>]*>(.*?)</p>", text, flags=re.S | re.I)
            if paras:
                cleaned = [self._strip_tags(p).strip() for p in paras if p.strip()]
                return cleaned, is_html
            body = re.sub(r"<[^>]+>", "", text)
            parts = re.split(r"\n\s*\n", body)
            return [p.strip() for p in parts if p.strip()], is_html

        parts = re.split(r"\n\s*\n", text)
        return [p.strip() for p in parts if p.strip()], is_html

    @staticmethod
    def _strip_tags(html: str) -> str:
        return re.sub(r"<[^>]+>", "", html)

    @staticmethod
    def _escape_html(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _distribute_to_runs(self, translated: str, runs_meta: List[dict]) -> List[str]:
        """Distribute translated paragraph text into runs preserving word boundaries."""
        total_orig = sum(len(r.get("text", "")) for r in runs_meta)
        num_runs = len(runs_meta)
        if total_orig == 0 or num_runs == 0:
            return [translated] + [""] * max(0, num_runs - 1)

        tlen = len(translated)
        boundaries: list[float] = []
        acc_orig = 0
        for run in runs_meta:
            acc_orig += len(run.get("text", ""))
            boundaries.append((acc_orig / total_orig) * tlen)

        if boundaries:
            boundaries[-1] = tlen

        tokens = [t for t in re.split(r"(\s+)", translated) if t]
        allocated = [""] * num_runs
        curr_pos = 0
        for token in tokens:
            midpoint = curr_pos + len(token) / 2
            assigned_run = num_runs - 1
            for i in range(num_runs):
                if midpoint <= boundaries[i]:
                    assigned_run = i
                    break
            allocated[assigned_run] += token
            curr_pos += len(token)

        return allocated

    def _translated_filename(self, filename: str | None) -> str:
        if not filename:
            return "translated"
        base, ext = os.path.splitext(filename)
        if not ext:
            return f"{base}_translated"
        return f"{base}_translated{ext}"

    async def process_upload_stream(
        self,
        upload_file: UploadFile,
        source_lang: str,
        target_lang: str,
        job_id: str | None = None,
        debug: bool = False,
    ) -> AsyncGenerator[dict, None]:
        """Async generator yielding progress and completion events during file translation."""
        raw = await upload_file.read()
        paragraphs, para_meta, para_runs, is_docx, _ = self._extract_document_parts(
            raw, upload_file.filename, upload_file.content_type
        )
        chunks = self._build_chunks(paragraphs)
        translated_fn = self._translated_filename(upload_file.filename)

        if not chunks:
            yield {
                "event": "complete",
                "job_id": job_id,
                "filename": translated_fn,
                "content_type": upload_file.content_type,
            }
            return

        translated_chunks: dict[Tuple[int, int], str] = {}
        total_chunks = len(chunks)
        completed_chunks = 0
        event_queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def translate_task(p_idx: int, c_idx: int, chunk_text: str):
            nonlocal completed_chunks
            try:
                async with self.sema:
                    collected = []
                    async for piece in self.queue_manager.stream_translation(
                        chunk_text, target_lang, source_lang
                    ):
                        collected.append(piece)
                        await event_queue.put(
                            {
                                "event": "progress",
                                "paragraph": p_idx,
                                "chunk": c_idx,
                                "data": piece,
                                "current": completed_chunks,
                                "total": total_chunks,
                            }
                        )
                    translated_chunks[(p_idx, c_idx)] = "".join(collected).strip()
                    completed_chunks += 1
                    await event_queue.put(
                        {
                            "event": "progress",
                            "paragraph": p_idx,
                            "chunk": c_idx,
                            "current": completed_chunks,
                            "total": total_chunks,
                            "status": "done",
                        }
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Chunk %s:%s translation failed", p_idx, c_idx)
                await event_queue.put(
                    {"event": "error", "data": "File translation failed"}
                )
                raise

        tasks = [asyncio.create_task(translate_task(p, c, t)) for (p, c, t) in chunks]

        async def monitor_tasks():
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                await event_queue.put(None)

        monitor_task = asyncio.create_task(monitor_tasks())
        had_error = False

        try:
            while True:
                ev = await event_queue.get()
                if ev is None:
                    break
                yield ev
                if ev.get("event") == "error":
                    had_error = True
                    for t in tasks:
                        t.cancel()
                    break
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
            if not monitor_task.done():
                monitor_task.cancel()
            await asyncio.gather(*tasks, monitor_task, return_exceptions=True)

        if had_error:
            return

        try:
            yield {"event": "processing", "data": "Збираємо перекладений документ..."}
            reconstructed = self._reconstruct_paragraphs(
                len(paragraphs), chunks, translated_chunks
            )

            if is_docx:
                data_bytes = self._build_docx_bytes(
                    raw,
                    reconstructed,
                    para_meta,
                    para_runs,
                    apply_heading_bold=True,
                )
                content_type = (
                    upload_file.content_type
                    or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
                if debug:
                    b64 = base64.b64encode(data_bytes).decode("ascii")
                    yield {
                        "event": "complete",
                        "filename": translated_fn,
                        "content_type": upload_file.content_type,
                        "data": b64,
                    }
                else:
                    if job_id:
                        self._store_result(
                            job_id,
                            {
                                "data": data_bytes,
                                "content_type": content_type,
                                "filename": translated_fn,
                                "is_binary": True,
                            },
                        )
                    yield {
                        "event": "complete",
                        "job_id": job_id,
                        "filename": translated_fn,
                        "content_type": upload_file.content_type,
                    }
            else:
                final_text = "\n\n".join(reconstructed)
                if debug:
                    yield {
                        "event": "complete",
                        "filename": translated_fn,
                        "content_type": upload_file.content_type,
                        "data": final_text,
                    }
                else:
                    if job_id:
                        self._store_result(
                            job_id,
                            {
                                "data": final_text,
                                "content_type": upload_file.content_type or "text/plain",
                                "filename": translated_fn,
                                "is_binary": False,
                            },
                        )
                    yield {
                        "event": "complete",
                        "job_id": job_id,
                        "filename": translated_fn,
                        "content_type": upload_file.content_type,
                    }
        except Exception:
            logger.exception("Error reconstructing translated file")
            yield {"event": "error", "data": "File reconstruction failed"}

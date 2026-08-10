import asyncio
import os
import re
import io
import base64
from typing import List, Tuple, AsyncGenerator
from fastapi import UploadFile
from docx import Document as DocxDocument


class FileTranslationManager:
    """
    Менеджер для перекладу завантажених файлів.
    Алгоритм (спрощено):
    - читає файл (текст/plain або HTML)
    - розбиває на параграфи
    - розбиває параграфи на речення (через NLLBTranslator._split_into_sentences)
    - групує речення в чанки по символах
    - відправляє чанки в `queue_manager.stream_translation` і збирає переклад
    - збирає назад перекладені чанки, зберігаючи розділення на параграфи
    """

    def __init__(self, queue_manager, translator, max_chunk_chars: int = 800, concurrency: int = 4):
        self.queue_manager = queue_manager
        self.translator = translator
        self.max_chunk_chars = max_chunk_chars
        self.sema = asyncio.Semaphore(concurrency)
        # job_id -> {data, content_type, filename, is_binary}
        self._results: dict[str, dict] = {}

    async def process_upload(self, upload_file: UploadFile, source_lang: str, target_lang: str) -> str:
        raw = await upload_file.read()
        try:
            text = raw.decode('utf-8')
        except Exception:
            # fallback: latin-1
            text = raw.decode('latin-1')

        filename = (upload_file.filename or '').lower()
        # Support docx
        if filename.endswith('.docx') or (upload_file.content_type and 'word' in (upload_file.content_type or '')):
            # parse docx preserving paragraph-level and run-level styles
            bio = io.BytesIO(raw)
            doc = DocxDocument(bio)
            paragraphs = []
            para_meta = []
            para_runs = []
            for p in doc.paragraphs:
                paragraphs.append(p.text or '')
                # store style name to preserve later
                style_name = None
                try:
                    style_name = p.style.name
                except Exception:
                    style_name = None
                para_meta.append({'style': style_name})

                runs = []
                for r in p.runs:
                    runs.append({
                        'text': r.text or '',
                        'bold': bool(r.bold),
                        'italic': bool(r.italic),
                        'underline': bool(r.underline),
                    })
                para_runs.append(runs)
            is_html = False
        else:
            paragraphs, is_html = self._split_into_paragraphs(text, upload_file.content_type)

        # Prepare chunks: list of (para_idx, chunk_idx, chunk_text)
        chunks: List[Tuple[int, int, str]] = []
        for p_idx, para in enumerate(paragraphs):
            sentences = self.translator._split_into_sentences(para)
            if not sentences:
                continue
            cur = []
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

        # Translate chunks concurrently but limited by semaphore
        translated_chunks = {}

        async def translate_and_store(par_idx: int, ch_idx: int, chunk_text: str):
            async with self.sema:
                # queue_manager.stream_translation returns AsyncGenerator
                collected = []
                async for piece in self.queue_manager.stream_translation(chunk_text, target_lang, source_lang):
                    collected.append(piece)
                translated_chunks[(par_idx, ch_idx)] = "".join(collected).strip()

        tasks = [asyncio.create_task(translate_and_store(p, c, t)) for (p, c, t) in chunks]
        if tasks:
            await asyncio.gather(*tasks)

        # Reconstruct paragraphs from translated chunks
        para_map = {}
        for (p_idx, c_idx, _text) in chunks:
            para_map.setdefault(p_idx, []).append((c_idx, translated_chunks.get((p_idx, c_idx), "")))

        reconstructed = []
        for p_idx in range(len(paragraphs)):
            parts = []
            items = para_map.get(p_idx, [])
            items.sort(key=lambda x: x[0])
            for _, txt in items:
                parts.append(txt)
            reconstructed.append("\n\n".join([p for p in (" ".join(parts).strip(),) if p]))

        if filename.endswith('.docx'):
            # Update the original docx in-place to preserve relationships, images, styles.
            bio = io.BytesIO(raw)
            try:
                orig_doc = DocxDocument(bio)
            except Exception:
                # fallback: build a new doc if original cannot be opened
                new_doc = DocxDocument()
                for para_text in reconstructed:
                    new_doc.add_paragraph(para_text)
                out = io.BytesIO()
                new_doc.save(out)
                out.seek(0)
                return out.getvalue()

            # Iterate paragraphs and replace run texts keeping formatting
            for idx, para_text in enumerate(reconstructed):
                runs_meta = para_runs[idx] if 'para_runs' in locals() and idx < len(para_runs) else None
                p = orig_doc.paragraphs[idx] if idx < len(orig_doc.paragraphs) else orig_doc.add_paragraph()
                if runs_meta and any(r.get('text') for r in runs_meta):
                    allocated = self._distribute_to_runs(para_text, runs_meta)
                    # ensure we have enough runs in the original paragraph
                    # if not, extend with new runs
                    while len(p.runs) < len(allocated):
                        p.add_run('')
                    for i, run_meta in enumerate(runs_meta):
                        text_piece = allocated[i] if i < len(allocated) else ''
                        try:
                            p.runs[i].text = text_piece
                            p.runs[i].bold = run_meta.get('bold')
                            p.runs[i].italic = run_meta.get('italic')
                            p.runs[i].underline = run_meta.get('underline')
                        except Exception:
                            try:
                                p.runs[i].text = text_piece
                            except Exception:
                                pass
                else:
                    # fallback: set paragraph text by replacing runs
                    if p.runs:
                        # put all text into first run and clear others
                        try:
                            p.runs[0].text = para_text
                            for r in p.runs[1:]:
                                r.text = ''
                        except Exception:
                            p.text = para_text
                    else:
                        p.text = para_text

                # apply paragraph style if available
                try:
                    if 'para_meta' in locals() and idx < len(para_meta):
                        style_name = para_meta[idx].get('style')
                        if style_name:
                            p.style = style_name
                except Exception:
                    pass

            out = io.BytesIO()
            orig_doc.save(out)
            out.seek(0)
            return out.getvalue()

        if is_html:
            # If original was html, wrap translated paragraphs with <p> tags
            html = "\n".join(f"<p>{self._escape_html(p)}</p>" for p in reconstructed)
            return html

        return "\n\n".join(reconstructed)

    def _split_into_paragraphs(self, text: str, content_type: str):
        # crude detection for html
        is_html = False
        if content_type and 'html' in content_type.lower():
            is_html = True
            # find <p>...</p> blocks
            paras = re.findall(r'<p[^>]*>(.*?)</p>', text, flags=re.S | re.I)
            if paras:
                # strip tags inside paragraphs
                cleaned = [self._strip_tags(p).strip() for p in paras if p.strip()]
                return cleaned, is_html
            # fallback: remove tags and treat whole body
            body = re.sub(r'<[^>]+>', '', text)
            parts = re.split(r'\n\s*\n', body)
            return [p.strip() for p in parts if p.strip()], is_html

        # plain text: split by blank lines
        parts = re.split(r'\n\s*\n', text)
        return [p.strip() for p in parts if p.strip()], is_html

    @staticmethod
    def _strip_tags(html: str) -> str:
        return re.sub(r'<[^>]+>', '', html)

    @staticmethod
    def _escape_html(text: str) -> str:
        return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

    def _distribute_to_runs(self, translated: str, runs_meta: List[dict]) -> List[str]:
        """Distribute translated paragraph text into runs according to original run lengths,
        preserving word boundaries."""
        total_orig = sum(len(r.get('text', '')) for r in runs_meta)
        num_runs = len(runs_meta)
        if total_orig == 0 or num_runs == 0:
            return [translated] + [''] * (num_runs - 1)

        # compute cumulative target boundaries in the translated string
        tlen = len(translated)
        boundaries = []
        acc_orig = 0
        for i in range(num_runs):
            orig_len = len(runs_meta[i].get('text', ''))
            acc_orig += orig_len
            boundaries.append((acc_orig / total_orig) * tlen)
        
        # ensure the last boundary is exactly tlen
        if boundaries:
            boundaries[-1] = tlen

        # Split into tokens (words and whitespaces) to avoid breaking words
        tokens = re.split(r'(\s+)', translated)
        tokens = [t for t in tokens if t]

        allocated = [''] * num_runs
        curr_pos = 0
        for token in tokens:
            midpoint = curr_pos + len(token) / 2
            # Find which run this token belongs to based on its midpoint
            assigned_run = 0
            for i in range(num_runs):
                if midpoint <= boundaries[i]:
                    assigned_run = i
                    break
            else:
                assigned_run = num_runs - 1
            
            allocated[assigned_run] += token
            curr_pos += len(token)

        return allocated

    def _translated_filename(self, filename: str | None) -> str:
        if not filename:
            return 'translated'
        base, ext = os.path.splitext(filename)
        if not ext:
            return f"{base}_translated"
        return f"{base}_translated{ext}"

    async def process_upload_stream(self, upload_file: UploadFile, source_lang: str, target_lang: str, job_id: str | None = None, debug: bool = True) -> AsyncGenerator[dict, None]:
        """Async generator that yields progress events during file translation.
        Emits dicts with keys: event (progress|chunk|complete|error), data (str or base64), paragraph, chunk
        """
        raw = await upload_file.read()
        try:
            text = raw.decode('utf-8')
        except Exception:
            text = raw.decode('latin-1')

        filename = (upload_file.filename or '').lower()
        is_docx = filename.endswith('.docx') or (upload_file.content_type and 'word' in (upload_file.content_type or ''))

        if is_docx:
            bio = io.BytesIO(raw)
            doc = DocxDocument(bio)
            paragraphs = [p.text or '' for p in doc.paragraphs]
            para_meta = []
            para_runs = []
            for p in doc.paragraphs:
                try:
                    style_name = p.style.name
                except Exception:
                    style_name = None
                para_meta.append({'style': style_name})
                runs = []
                for r in p.runs:
                    runs.append({
                        'text': r.text or '',
                        'bold': bool(r.bold),
                        'italic': bool(r.italic),
                        'underline': bool(r.underline),
                    })
                para_runs.append(runs)
        else:
            paragraphs, _ = self._split_into_paragraphs(text, upload_file.content_type)

        chunks: List[Tuple[int, int, str]] = []
        for p_idx, para in enumerate(paragraphs):
            sentences = self.translator._split_into_sentences(para)
            if not sentences:
                continue
            cur = []
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

        if not chunks:
            # yield complete immediately if nothing to translate
            yield {'event': 'complete', 'job_id': job_id, 'filename': self._translated_filename(upload_file.filename), 'content_type': upload_file.content_type}
            return

        translated_chunks = {}
        total_chunks = len(chunks)
        completed_chunks = 0
        event_queue = asyncio.Queue()

        async def translate_task(p_idx: int, c_idx: int, chunk_text: str):
            nonlocal completed_chunks
            try:
                async with self.sema:
                    collected = []
                    async for piece in self.queue_manager.stream_translation(chunk_text, target_lang, source_lang):
                        collected.append(piece)
                        # current progress: how many chunks already fully done
                        await event_queue.put({
                            'event': 'progress',
                            'paragraph': p_idx,
                            'chunk': c_idx,
                            'data': piece,
                            'current': completed_chunks,
                            'total': total_chunks
                        })
                    translated_chunks[(p_idx, c_idx)] = "".join(collected).strip()
                    completed_chunks += 1
                    # chunk finished event
                    await event_queue.put({
                        'event': 'progress',
                        'paragraph': p_idx,
                        'chunk': c_idx,
                        'current': completed_chunks,
                        'total': total_chunks,
                        'status': 'done'
                    })
            except Exception as e:
                await event_queue.put({'event': 'error', 'data': f"Chunk {p_idx}:{c_idx} error: {str(e)}"})

        # Start all tasks concurrently (semaphore within will limit active execution)
        tasks = [asyncio.create_task(translate_task(p, c, t)) for (p, c, t) in chunks]

        async def monitor_tasks():
            await asyncio.gather(*tasks, return_exceptions=True)
            await event_queue.put(None) # end of events

        asyncio.create_task(monitor_tasks())

        try:
            while True:
                ev = await event_queue.get()
                if ev is None:
                    break
                yield ev
                if ev.get('event') == 'error':
                    # optional: cancel other tasks on first error
                    # for t in tasks: t.cancel()
                    pass
        except asyncio.CancelledError:
            for t in tasks: t.cancel()
            raise

        # Reconstruction logic
        try:
            yield {'event': 'processing', 'data': 'Збираємо перекладений документ...'}
            para_map = {}
            for (p_idx, c_idx, _text) in chunks:
                para_map.setdefault(p_idx, []).append((c_idx, translated_chunks.get((p_idx, c_idx), "")))

            reconstructed = []
            for p_idx in range(len(paragraphs)):
                parts = []
                items = para_map.get(p_idx, [])
                items.sort(key=lambda x: x[0])
                for _, txt in items:
                    parts.append(txt)
                reconstructed.append("\n\n".join([p for p in (" ".join(parts).strip(),) if p]))

            if is_docx:
                bio = io.BytesIO(raw)
                try:
                    orig_doc = DocxDocument(bio)
                except Exception:
                    new_doc = DocxDocument()
                    for para_text in reconstructed:
                        new_doc.add_paragraph(para_text)
                    out = io.BytesIO()
                    new_doc.save(out)
                    out.seek(0)
                    data_bytes = out.read()
                    if debug:
                        translated_filename = self._translated_filename(upload_file.filename)
                        b64 = base64.b64encode(data_bytes).decode('ascii')
                        yield {'event': 'complete', 'filename': translated_filename, 'content_type': upload_file.content_type, 'data': b64}
                    else:
                        if job_id:
                            self._results[job_id] = {
                                'data': data_bytes,
                                'content_type': upload_file.content_type or 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                                'filename': self._translated_filename(upload_file.filename),
                                'is_binary': True,
                            }
                        yield {'event': 'complete', 'job_id': job_id, 'filename': self._translated_filename(upload_file.filename), 'content_type': upload_file.content_type}
                    return

                for idx, para_text in enumerate(reconstructed):
                    runs_meta = para_runs[idx] if 'para_runs' in locals() and idx < len(para_runs) else None
                    p = orig_doc.paragraphs[idx] if idx < len(orig_doc.paragraphs) else orig_doc.add_paragraph()
                    if runs_meta and any(r.get('text') for r in runs_meta):
                        allocated = self._distribute_to_runs(para_text, runs_meta)
                        while len(p.runs) < len(allocated):
                            p.add_run('')
                        for i, meta in enumerate(runs_meta):
                            text_piece = allocated[i] if i < len(allocated) else ''
                            try:
                                p.runs[i].text = text_piece
                                try:
                                    style_name = para_meta[idx].get('style') if 'para_meta' in locals() and idx < len(para_meta) else None
                                    is_heading = False
                                    if style_name and isinstance(style_name, str):
                                        sn = style_name.lower()
                                        if sn.startswith('heading') or 'title' in sn or 'header' in sn:
                                            is_heading = True
                                except Exception:
                                    is_heading = False

                                bold_val = bool(meta.get('bold')) or is_heading
                                p.runs[i].bold = bold_val
                                p.runs[i].italic = meta.get('italic')
                                p.runs[i].underline = meta.get('underline')
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
                                    r.text = ''
                            except Exception:
                                p.text = para_text
                        else:
                            p.text = para_text

                out = io.BytesIO()
                orig_doc.save(out)
                out.seek(0)
                data_bytes = out.read()
                if debug:
                    translated_filename = self._translated_filename(upload_file.filename)
                    b64 = base64.b64encode(data_bytes).decode('ascii')
                    yield {'event': 'complete', 'filename': translated_filename, 'content_type': upload_file.content_type, 'data': b64}
                else:
                    if job_id:
                        self._results[job_id] = {
                            'data': data_bytes,
                            'content_type': upload_file.content_type or 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            'filename': self._translated_filename(upload_file.filename),
                            'is_binary': True,
                        }
                    yield {'event': 'complete', 'job_id': job_id, 'filename': self._translated_filename(upload_file.filename), 'content_type': upload_file.content_type}
            else:
                final_text = "\n\n".join(reconstructed)
                if debug:
                    translated_filename = self._translated_filename(upload_file.filename)
                    yield {'event': 'complete', 'filename': translated_filename, 'content_type': upload_file.content_type, 'data': final_text}
                else:
                    if job_id:
                        self._results[job_id] = {
                            'data': final_text,
                            'content_type': upload_file.content_type or 'text/plain',
                            'filename': self._translated_filename(upload_file.filename),
                            'is_binary': False,
                        }
                    yield {'event': 'complete', 'job_id': job_id, 'filename': self._translated_filename(upload_file.filename), 'content_type': upload_file.content_type}
        except Exception as e:
            yield {'event': 'error', 'data': str(e)}

    def fetch_result(self, job_id: str):
        """Return stored result by job_id or None."""
        return self._results.get(job_id)

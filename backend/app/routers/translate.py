import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..backends import LANGUAGE_PAIRS, TranslationError
from ..batching import translate_texts
from ..documents import DocumentError, parse_document
from ..history import content_key
from ..http_utils import make_content_disposition_header
from ..job_queue import Job, JobStatus, QueueFullError
from ..sanitize import clean_filename, clean_text

logger = logging.getLogger(__name__)
router = APIRouter()

TEXT_DONE = "Цей текст уже перекладено."
TEXT_RUNNING = "Цей текст уже перекладається. Зачекайте на результат."


class TranslationRequest(BaseModel):
    text: str = Field(..., max_length=2000)
    source_lang: str = Field("bos_Latn", description="Код мови оригіналу (наприклад, bos_Latn)")
    target_lang: str = Field("ukr_Cyrl", description="Код цільової мови (наприклад, ukr_Cyrl)")


def _check_languages(source_lang: str, target_lang: str) -> None:
    if (source_lang, target_lang) not in LANGUAGE_PAIRS:
        raise HTTPException(status_code=400, detail="Непідтримувана пара мов")


@router.post("/translate/stream")
async def translate_stream(body: TranslationRequest, request: Request):
    """Text translation over SSE; keep-alive pings are sent while the GPU works.

    A `notice` event tells the visitor that the same text is already done or running.
    """
    text = clean_text(body.text).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текст порожній")
    _check_languages(body.source_lang, body.target_lang)
    backend = request.app.state.backend
    history = request.app.state.history
    direction = LANGUAGE_PAIRS[body.source_lang, body.target_lang]
    key = content_key(request.state.visitor, direction, text.encode())

    # A client disconnect cancels this generator and with it the Space request.
    async def event_generator():
        result = history.result(key)
        if result is not None:
            yield {"event": "notice", "data": TEXT_DONE}
        elif history.is_running(key):
            yield {"event": "notice", "data": TEXT_RUNNING}
            yield {"event": "end", "data": "[DONE]"}
            return
        else:
            try:
                # Nothing is awaited between the check above and this mark
                with history.running(key):
                    [result] = await translate_texts(
                        backend, [text], body.source_lang, body.target_lang
                    )
                    history.save(key, result)
            except TranslationError as exc:
                logger.warning("Translation failed: %s", exc)
                yield {"event": "error", "data": exc.public_message}
                return
            except Exception:
                logger.exception("Translation failed")
                yield {"event": "error", "data": TranslationError.public_message}
                return
        yield {"event": "message", "data": result}
        yield {"event": "end", "data": "[DONE]"}

    return EventSourceResponse(event_generator())


@router.post("/translate/file/submit")
async def submit_file_job(
    upload_file: UploadFile,
    request: Request,
    source_lang: str = "bos_Latn",
    target_lang: str = "ukr_Cyrl",
):
    """Validate a file and queue it for translation. Returns a job_id at once."""
    _check_languages(source_lang, target_lang)
    settings = request.app.state.settings
    backend = request.app.state.backend

    raw = await upload_file.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Файл завеликий")

    filename = clean_filename(upload_file.filename or "")
    try:
        document = await asyncio.to_thread(parse_document, filename, raw, source_lang)
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if sum(map(len, document.texts)) > settings.max_file_chars:
        limit = settings.max_file_chars
        raise HTTPException(status_code=413, detail=f"Забагато тексту (ліміт {limit} символів)")

    async def work(progress):
        translated = await translate_texts(
            backend, document.texts, source_lang, target_lang, progress
        )
        return await asyncio.to_thread(document.build, translated)

    base, ext = os.path.splitext(filename)
    jobs = request.app.state.jobs
    direction = LANGUAGE_PAIRS[source_lang, target_lang]
    # The extension is part of the key: it decides how the same bytes are read
    key = content_key(request.state.visitor, f"{direction}{ext.lower()}", raw)
    job = jobs.find(key)
    if job is not None:
        duplicate = "complete" if job.status == JobStatus.COMPLETE else "processing"
        return {"job_id": job.job_id, "status": job.status, "duplicate": duplicate}
    try:
        job = jobs.submit(work, f"{base}_translated{ext}", document.media_type, key)
    except QueueFullError as exc:
        raise HTTPException(
            status_code=503, detail="Черга заповнена. Спробуйте пізніше."
        ) from exc
    return {"job_id": job.job_id, "status": job.status, "duplicate": None}


def _find_job(request: Request, job_id: str) -> Job:
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/translate/file/status")
async def get_file_job_status(job_id: str, request: Request):
    """Poll the status and progress of a file job."""
    job = _find_job(request, job_id)
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
        "filename": job.filename,
        "error": job.error,
    }


@router.get("/translate/file/result")
async def get_translated_file(job_id: str, request: Request):
    """Download the translated file of a completed job."""
    job = _find_job(request, job_id)
    if job.status != JobStatus.COMPLETE:
        raise HTTPException(status_code=409, detail=job.error or "Job still in progress")
    return Response(
        job.result,
        media_type=job.media_type,
        headers=make_content_disposition_header(job.filename),
    )


@router.delete("/translate/file/job", status_code=204)
async def cancel_file_job(job_id: str, request: Request):
    """Cancel a queued or running job so it stops using GPU quota."""
    if not request.app.state.jobs.cancel(job_id):
        raise HTTPException(status_code=404, detail="Job not found")

import io
import json
import logging
import os
import uuid
import zipfile

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..http_utils import make_content_disposition_header

logger = logging.getLogger(__name__)
router = APIRouter()


class TranslationRequest(BaseModel):
    text: str = Field(..., max_length=2000)
    source_lang: str = Field("bos_Latn", description="Код мови оригіналу (наприклад, bos_Latn)")
    target_lang: str = Field("ukr_Cyrl", description="Код цільової мови (наприклад, ukr_Cyrl)")


class _InMemoryUpload:
    def __init__(self, filename: str | None, content_type: str | None, data: bytes):
        self.filename = filename
        self.content_type = content_type
        self._data = data

    async def read(self) -> bytes:
        return self._data


async def _read_and_validate_upload(upload_file: UploadFile, request: Request) -> bytes:
    """Validate file extension and size limit, returning raw file bytes."""
    settings = request.app.state.settings
    filename = upload_file.filename or ""
    _, ext = os.path.splitext(filename.lower())
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=415, detail="Unsupported file type")

    raw_bytes = await upload_file.read()
    if len(raw_bytes) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    return raw_bytes


@router.post("/translate/stream")
async def translate_stream(request: TranslationRequest, raw_request: Request):
    """Streaming text translation endpoint (SSE)."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Текст порожній")

    queue_manager = raw_request.app.state.queue_manager

    async def event_generator():
        stream = queue_manager.stream_translation(
            request.text,
            request.target_lang,
            source_lang=request.source_lang,
        )
        try:
            async for chunk in stream:
                if await raw_request.is_disconnected():
                    break
                yield {"event": "message", "data": chunk}
            else:
                yield {"event": "end", "data": "[DONE]"}
        except Exception:
            logger.exception("Streaming translation failed")
            yield {"event": "error", "data": "Translation failed"}
        finally:
            await stream.aclose()

    return EventSourceResponse(event_generator())


@router.get("/translate/file/result")
async def get_translated_file(job_id: str, request: Request):
    """Return stored translated file for given job_id."""
    file_manager = request.app.state.file_manager
    res = file_manager.fetch_result(job_id)
    if not res:
        raise HTTPException(status_code=404, detail="Result not found")

    data = res["data"]
    content_type = res.get("content_type", "application/octet-stream")
    filename = res.get("filename", f"result_{job_id}")
    headers = make_content_disposition_header(filename)

    if res.get("is_binary"):
        return StreamingResponse(io.BytesIO(data), media_type=content_type, headers=headers)
    return StreamingResponse(
        io.StringIO(data), media_type=content_type or "text/plain", headers=headers
    )


@router.post("/translate/file")
async def translate_file(
    upload_file: UploadFile,
    request: Request,
    source_lang: str = "bos_Latn",
    target_lang: str = "ukr_Cyrl",
    debug: bool = False,
):
    """Translate an uploaded file and return it directly (or a ZIP with metadata if debug=true)."""
    if not upload_file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    raw_bytes = await _read_and_validate_upload(upload_file, request)
    inmem = _InMemoryUpload(upload_file.filename, upload_file.content_type, raw_bytes)
    file_manager = request.app.state.file_manager

    try:
        translated = await file_manager.process_upload(inmem, source_lang, target_lang)
        base, ext = os.path.splitext(upload_file.filename or "translated")
        translated_filename = f"{base}_translated{ext}"
        is_binary = isinstance(translated, (bytes, bytearray))

        if debug:
            bio = io.BytesIO()
            with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                if is_binary:
                    zf.writestr(translated_filename, translated)
                else:
                    zf.writestr(translated_filename, str(translated).encode("utf-8"))

                meta = {
                    "filename": translated_filename,
                    "content_type": upload_file.content_type,
                    "translated_preview": str(translated)[:10000],
                }
                zf.writestr(
                    "translation_meta.json",
                    json.dumps(meta, ensure_ascii=False, indent=2),
                )
            bio.seek(0)
            headers = make_content_disposition_header(f"{base}_translated.zip")
            return StreamingResponse(bio, media_type="application/zip", headers=headers)

        headers = make_content_disposition_header(translated_filename)
        if is_binary:
            return StreamingResponse(
                io.BytesIO(translated),
                media_type=upload_file.content_type or "application/octet-stream",
                headers=headers,
            )
        return StreamingResponse(
            io.StringIO(str(translated)),
            media_type=upload_file.content_type or "text/plain",
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("File translation failed")
        raise HTTPException(status_code=500, detail="Translation failed")


@router.post("/translate/file/stream")
async def translate_file_stream(
    upload_file: UploadFile,
    raw_request: Request,
    source_lang: str = "bos_Latn",
    target_lang: str = "ukr_Cyrl",
    debug: bool = False,
):
    """Stream progress events (SSE) during file translation."""
    raw_bytes = await _read_and_validate_upload(upload_file, raw_request)
    inmem = _InMemoryUpload(upload_file.filename, upload_file.content_type, raw_bytes)
    job_id = uuid.uuid4().hex
    file_manager = raw_request.app.state.file_manager

    async def event_generator():
        stream = file_manager.process_upload_stream(
            inmem, source_lang, target_lang, job_id=job_id, debug=debug
        )
        try:
            async for ev in stream:
                if await raw_request.is_disconnected():
                    break
                event_name = ev.get("event", "message")
                if isinstance(ev, dict):
                    payload_obj = {k: v for k, v in ev.items() if k != "event"}
                    try:
                        payload = json.dumps(payload_obj, ensure_ascii=False)
                    except Exception:
                        payload = str(payload_obj)
                else:
                    payload = str(ev)
                yield {"event": event_name, "data": payload}
        except Exception:
            logger.exception("Streaming file translation failed")
            yield {"event": "error", "data": "Translation failed"}
        finally:
            await stream.aclose()

    return EventSourceResponse(event_generator())

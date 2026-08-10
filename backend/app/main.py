import os
import sys
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field

# --- НАЛАШТУВАННЯ CUDA DLL ДЛЯ WINDOWS ---
MODEL_PATH = os.getenv("MODEL_PATH", "./models/nllb_int8")
TOKENIZER_PATH = os.getenv("TOKENIZER_PATH", "./models/nllb_int8/sentencepiece.bpe.model")

def setup_windows_dlls():
    """Додає шляхи до DLL у системний пошук Windows для підтримки GPU."""
    if sys.platform != "win32":
        return
    added_paths = []
    abs_model_path = os.path.abspath(MODEL_PATH)
    if os.path.exists(abs_model_path):
        os.add_dll_directory(abs_model_path)
        added_paths.append(abs_model_path)

    try:
        import nvidia.cublas
        import nvidia.cudnn
        for package in [nvidia.cublas, nvidia.cudnn]:
            pkg_dirs = getattr(package, "__path__", [])
            if not pkg_dirs and hasattr(package, "__file__"):
                pkg_dirs = [os.path.dirname(package.__file__)]
            for base_path in pkg_dirs:
                os.add_dll_directory(base_path)
                added_paths.append(base_path)
                lib_path = os.path.join(base_path, "lib")
                if os.path.isdir(lib_path):
                    os.add_dll_directory(lib_path)
                    added_paths.append(lib_path)
    except ImportError:
        pass

    if added_paths:
        os.environ["PATH"] = ";".join(added_paths) + ";" + os.environ["PATH"]

setup_windows_dlls()


def _load_dotenv_if_exists() -> Optional[str]:
    """If a .env file exists in the backend root, load simple KEY=VALUE pairs into os.environ."""
    try:
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
        if not os.path.exists(env_path):
            return None
        with open(env_path, 'r', encoding='utf-8') as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
        return env_path
    except Exception:
        return None


_load_dotenv_if_exists()

from .translator import NLLBTranslator
from .monitor import HealthChecker
from .queue_manager import TranslationQueueManager
from .file_translator import FileTranslationManager
import uuid
import os
import json

app = FastAPI(title="NLLB Windows Translator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

health_checker = HealthChecker()
translator = NLLBTranslator(model_path=MODEL_PATH, tokenizer_path=TOKENIZER_PATH)
queue_manager = TranslationQueueManager(translator, health_checker)
file_manager = FileTranslationManager(queue_manager, translator)

class TranslationRequest(BaseModel):
    text: str = Field(..., max_length=2000)
    source_lang: str = Field("bos_Latn", description="Код мови оригіналу (наприклад, bos_Latn)")
    target_lang: str = Field("ukr_Cyrl", description="Код цільової мови (наприклад, ukr_Cyrl)")

@app.get("/health")
async def get_health():
    """Повертає стан здоров'я системи."""
    return queue_manager.get_current_status()

@app.post("/translate/stream")
async def translate_stream(request: TranslationRequest, raw_request: Request):
    """Ендпоінт для стрімінгового перекладу (SSE)."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Текст порожній")

    async def event_generator():
        try:
            # Передаємо нові параметри мови в менеджер черги
            async for chunk in queue_manager.stream_translation(
                request.text, 
                request.target_lang,
                source_lang=request.source_lang
            ):
                if await raw_request.is_disconnected():
                    break
                yield {"event": "message", "data": chunk}
            yield {"event": "end", "data": "[DONE]"}
        except Exception as e:
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())


@app.get('/translate/file/result')
async def get_translated_file(job_id: str):
    """Return stored translated file for given job_id."""
    res = file_manager.fetch_result(job_id)
    if not res:
        raise HTTPException(status_code=404, detail='Result not found')

    data = res['data']
    content_type = res.get('content_type', 'application/octet-stream')
    filename = res.get('filename', f'result_{job_id}')

    from fastapi.responses import StreamingResponse
    import io
    from urllib.parse import quote

    def make_cd_header(name: str) -> dict:
        # Build Content-Disposition with ASCII fallback and RFC5987 filename*
        try:
            name.encode('latin-1')
            fallback = name
        except Exception:
            # replace non-ascii chars with underscore for fallback
            fallback = ''.join((c if ord(c) < 128 else '_') for c in name)
        pct = quote(name, safe='')
        return {"Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{pct}"}

    if res.get('is_binary'):
        buf = io.BytesIO(data)
        headers = make_cd_header(filename)
        return StreamingResponse(buf, media_type=content_type, headers=headers)
    else:
        # text
        text = data
        headers = make_cd_header(filename)
        return StreamingResponse(io.StringIO(text), media_type=content_type or 'text/plain', headers=headers)


@app.post("/translate/file")
async def translate_file(upload_file: UploadFile, source_lang: str = "bos_Latn", target_lang: str = "ukr_Cyrl", debug: bool = True):
    """Endpoint для перекладу завантажених файлів.
    Returns the translated file as an attachment. If `debug=true`, returns a ZIP
    containing the translated file plus a translation JSON file with metadata.
    """
    if not upload_file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    try:
        translated = await file_manager.process_upload(upload_file, source_lang, target_lang)
        base, ext = os.path.splitext(upload_file.filename or 'translated')
        translated_filename = f"{base}_translated{ext}"

        # If the translator returned bytes -> binary (docx), otherwise treat as text
        is_binary = isinstance(translated, (bytes, bytearray))

        import io
        from fastapi.responses import StreamingResponse
        import zipfile

        if debug:
            # package translated file + JSON metadata into a zip
            bio = io.BytesIO()
            with zipfile.ZipFile(bio, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
                if is_binary:
                    zf.writestr(translated_filename, translated)
                else:
                    # ensure str -> bytes
                    zf.writestr(translated_filename, str(translated).encode('utf-8'))

                # attach a JSON with the raw translated text (for inspection)
                import json
                meta = {
                    'filename': translated_filename,
                    'content_type': upload_file.content_type,
                    'translated_preview': str(translated)[:10000],
                }
                zf.writestr('translation_meta.json', json.dumps(meta, ensure_ascii=False, indent=2))
            bio.seek(0)
            from urllib.parse import quote
            def make_cd_header_name(name: str) -> dict:
                try:
                    name.encode('latin-1')
                    fallback = name
                except Exception:
                    fallback = ''.join((c if ord(c) < 128 else '_') for c in name)
                pct = quote(name, safe='')
                return {"Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{pct}"}

            headers = make_cd_header_name(f"{base}_translated.zip")
            return StreamingResponse(bio, media_type='application/zip', headers=headers)
        else:
            # return raw translated file as attachment
            if is_binary:
                bio = io.BytesIO(translated)
                from urllib.parse import quote
                def _cd(name: str) -> dict:
                    try:
                        name.encode('latin-1')
                        fallback = name
                    except Exception:
                        fallback = ''.join((c if ord(c) < 128 else '_') for c in name)
                    pct = quote(name, safe='')
                    return {"Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{pct}"}

                headers = _cd(translated_filename)
                return StreamingResponse(bio, media_type=upload_file.content_type or 'application/octet-stream', headers=headers)
            else:
                # text
                text = str(translated)
                from urllib.parse import quote
                def _cd2(name: str) -> dict:
                    try:
                        name.encode('latin-1')
                        fallback = name
                    except Exception:
                        fallback = ''.join((c if ord(c) < 128 else '_') for c in name)
                    pct = quote(name, safe='')
                    return {"Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{pct}"}

                headers = _cd2(translated_filename)
                return StreamingResponse(io.StringIO(text), media_type=upload_file.content_type or 'text/plain', headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/translate/file/stream")
async def translate_file_stream(upload_file: UploadFile, source_lang: str = "bos_Latn", target_lang: str = "ukr_Cyrl", debug: bool = True, raw_request: Request = None):
    """Stream progress events (SSE) during file translation."""
    # Read the uploaded file into memory immediately to avoid UploadFile being closed
    try:
        raw_bytes = await upload_file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read upload: {e}")

    class _InMemoryUpload:
        def __init__(self, filename, content_type, data: bytes):
            self.filename = filename
            self.content_type = content_type
            self._data = data

        async def read(self):
            return self._data

    inmem = _InMemoryUpload(upload_file.filename, upload_file.content_type, raw_bytes)
    # create job id for this upload
    job_id = uuid.uuid4().hex

    async def event_generator():
        try:
            async for ev in file_manager.process_upload_stream(inmem, source_lang, target_lang, job_id=job_id, debug=debug):
                if raw_request is not None and await raw_request.is_disconnected():
                    break
                event_name = ev.get('event', 'message')
                # Always serialize payloads as JSON when they are dicts so the frontend
                # can reliably parse filename/content_type/data for complete events.
                if isinstance(ev, dict):
                    payload_obj = {k: v for k, v in ev.items() if k != 'event'}
                    try:
                        payload = json.dumps(payload_obj, ensure_ascii=False)
                    except Exception:
                        # fallback to string conversion
                        payload = str(payload_obj)
                else:
                    payload = str(ev)
                yield {"event": event_name, "data": payload}
        except Exception as e:
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
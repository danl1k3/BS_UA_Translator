# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Neural translation app (default Bosnian `bos_Latn` → Ukrainian `ukr_Cyrl`) built on NLLB-200 distilled 600M (int8 CTranslate2 model), a FastAPI backend and a React frontend. Comments, docstrings and UI strings are largely in Ukrainian. No tests exist in the repo.

## Commands

Backend (from `backend/`; Python 3.10 in Docker, root `pyproject.toml` declares >=3.12 but has no deps):
- `pip install -r requirements.txt` (`requirements_nllb.txt` is a UTF-16 pip-freeze of a Windows venv)
- `uvicorn app.main:app --reload --port 8000`
- Requires a CTranslate2 model dir at `backend/models/nllb_int8/` (git-ignored) containing `sentencepiece.bpe.model`. Override via `MODEL_PATH` / `TOKENIZER_PATH` env vars or a `backend/.env` (simple KEY=VALUE, loaded manually in `main.py`).
- `python copy_cuda_dlls.py` — Windows-only helper that copies cuBLAS/cuDNN DLLs into the model dir.

Frontend (from `frontend/`): `npm run dev`, `npm run build` (runs `tsc -b` first), `npm run lint`.

Full stack: `docker compose up --build` (backend needs the NVIDIA container toolkit; mounts `./backend/models`; frontend served by nginx on port 80).

## Architecture

Backend request flow: `main.py` (routes) → `FileTranslationManager` (file endpoints only) → `TranslationQueueManager` → `NLLBTranslator`.

- `translator.py`: loads the same model on both `cuda` and `cpu` CTranslate2 translators (either may fail to init and is skipped). `translate_stream` splits text into sentences by regex and translates one sentence at a time (beam 4, repetition penalty 1.2), yielding each as it finishes. Source lang code is prepended as a token and the target lang as `target_prefix`.
- `queue_manager.py`: picks a device per request using `HealthChecker`, enforces separate GPU (4) / CPU (8) semaphores, and runs the sync generator in an executor to expose it as an async stream. Errors are yielded inline as `[Помилка: ...]` text rather than raised.
- `monitor.py`: NVML/psutil metrics; GPU free VRAM < 500 MB → "Slow Mode", routes to CPU. Also supplies `/health`.
- `file_translator.py`: parses uploads (plain text, HTML, `.docx` via python-docx preserving paragraph styles and run formatting through `_distribute_to_runs`), groups sentences into ~800-char chunks, translates them concurrently through the queue manager, and reassembles. `process_upload_stream` emits progress events; finished results are held in an in-memory `_results` dict keyed by `job_id` and fetched via `GET /translate/file/result`.
- Endpoints: `GET /health`, `POST /translate/stream` (SSE), `POST /translate/file`, `POST /translate/file/stream` (SSE progress), `GET /translate/file/result`. Note `debug` defaults to `true` on file endpoints, which wraps output in a ZIP with `translation_meta.json`.

Frontend (`frontend/src`): `App.tsx` with `components/TextTranslator.tsx` and `components/FileUploader.tsx`, plus hooks `useStreaming` (SSE text translation) and `useHealth`.

## Gotchas

- API base URL is inconsistent: `FileUploader.tsx` uses `VITE_API_URL` (default `http://localhost:8000`, baked in at build time via docker-compose build arg), but `useStreaming.ts` and `useHealth.ts` fetch relative paths (`/translate/stream`, `/health`). Neither `vite.config.ts` nor `nginx.conf` defines a proxy, so those relative calls only work if one is added.
- CORS is wide open (`allow_origins=["*"]`); no auth. README TODOs: better infrastructure, refactor, security, user accounts.
- `main.py` contains Windows DLL-path setup (`setup_windows_dlls`) that runs at import time, and the Content-Disposition header helper is duplicated several times inline.

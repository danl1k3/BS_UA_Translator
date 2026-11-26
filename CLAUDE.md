# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
It describes the `heroku-hf-spaces` branch (Option A in `PLAN.md`).

## Overview

Bosnian (`bos_Latn`) ↔ Ukrainian (`ukr_Cyrl`) translation. A React frontend talks to a slim FastAPI gateway (Heroku), which calls a Gradio ZeroGPU Space (`Danlike/NLLB-200-600-endpoint`, fine-tuned NLLB-200 600M) over HTTP. The gateway runs no model. The Space code lives on Hugging Face, not here. Comments, docstrings and UI strings are largely in Ukrainian.

## Commands

From the repo root:
- `pip install -r backend/requirements-dev.txt` (Python 3.12, exact pins; keep Docker and CI in step)
- `pytest` (all) or `pytest backend/tests/test_batching.py -k name` (one)
- `ruff check backend`
- `cd backend && uvicorn app.main:app --reload --port 8000` — needs `REMOTE_INFERENCE_URL` (see `backend/.env.example`)

From `frontend/`: `npm run dev`, `npm test` (Node 22.18+), `npm run lint`, `npm run build` (runs `tsc -b` first).

Full stack: `docker compose up --build` (frontend on port 80; backend bound to localhost only).

## Architecture

Backend (`backend/app/`):
- `main.py`: `create_app(settings, backend)`; middleware order is CORS (outermost) → rate limit → request size check (all POSTs). Tests inject a fake backend (`tests/fakes.py`).
- `backends.py`: `TranslatorBackend` interface, `GradioBackend` (submit to `/gradio_api/call/translate`, read the SSE result; health via `/config`, cached 30 s, no GPU), error types with a user-safe `public_message`, and `LANGUAGE_PAIRS`.
- `batching.py`: the single translation path for text and files. Splits into sentences, cuts long ones to 220 characters, sends one segment per line in batches of up to 2000 characters, then restores line breaks.
- `documents.py`: parses `.txt`, `.html`, `.docx` into a list of texts plus a `build` function. DOCX: body paragraphs only; formatting is kept by redistributing words over runs.
- `job_queue.py`: in-process queue, one worker (the Space handles one request at a time), bounded, results kept with a TTL, cancellable.
- `routers/`: `GET /health`, `POST /translate/stream` (SSE: `message`, `end`, `error`), `POST /translate/file/submit`, `GET /translate/file/status`, `GET /translate/file/result`, `DELETE /translate/file/job`.

Frontend (`frontend/src/`): `api.ts` (all requests go through `apiFetch`), `sse.ts`, hooks `useTranslate` and `useHealth`, components `TextTranslator`, `FileUploader` (submit, poll, download), `InferenceStatusBadge`.

## Constraints

- The Space truncates sentences above 128 tokens and requests above 2000 characters; `batching.py` exists to respect this and relies on the Space returning one line per input line.
- Every visitor spends the daily ZeroGPU quota of the `REMOTE_API_TOKEN` owner: avoid extra calls, never send the token to the browser.
- Upload limit is 3 MB / 20,000 characters (`config.py`). `nginx.conf` `client_max_body_size` and `FileUploader.tsx` must match.
- Queue, results and rate limit counters are in memory: run a single instance and process; state is lost on restart.
- The rate limiter trusts only the rightmost `X-Forwarded-For` entry, so the backend must sit behind a proxy (Heroku router, nginx). Only POST requests are limited.
- `VITE_API_URL` is baked in at build time; empty means same origin (nginx or Vite proxy). A separate frontend origin must be listed in `CORS_ORIGINS`.
- Client errors must stay generic; details go to server logs.

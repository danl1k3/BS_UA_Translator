# Roadmap (alternative): text-only translation

Same goal as `PLAN.md`, but file translation (txt/html/docx) is removed to simplify the project.
Work on branches, one PR per phase (or sub-phase), merge into `main`.

## What changes compared to `PLAN.md`
- Removed: `file_translator.py`, the `/translate/file*` endpoints, `FileUploader.tsx`, `python-docx`, `python-multipart`, upload limits, the in-memory `_results` store, async file jobs.
- Heroku's 30 s / 55 s request limits stop being a design constraint: text is capped (currently 2000 chars) and streams over SSE.
- The queue and broker (Phase 3) become optional, since there are no long-running jobs.
- Trade-off: less impressive feature set (no docx with preserved formatting), but a smaller surface for bugs and far less code to test and maintain. Can be added back later as a separate phase.

## Deployment options

The backend talks to inference only through a `TranslatorBackend` interface (Phase 1), so both options share the same code.
Measured RAM of the int8 model: about 800 MB, so a VPS needs at least 2 GB.

### Option A: Split services (gateway + hosted inference)
- **Gateway:** FastAPI on a Heroku Basic dyno (about $7/month, does not sleep). Slim image: no `ctranslate2`, `sentencepiece`, `pynvml`, no CUDA.
- **Inference:** the model on HF Space, called through a `RemoteBackend`. May cold-start; the UI needs a "waking up" state and timeouts.
- **Cache and rate-limit counters:** Upstash Redis (watch per-command billing: 1-2 commands per request).
- **Database:** Heroku Postgres (about $5/month), used later for accounts.
- **Frontend:** static hosting or an nginx container.
- Streaming caveat: the remote API may return the whole text at once instead of streaming; decide whether the UI fakes streaming, or the inference endpoint is made a generator.

### Option B: Monolith on one VPS
- Whole stack via docker compose on a 2-4 GB VPS (student credit; verify current terms), with nginx, domain, HTTPS (Let's Encrypt), swap file.
- Local CTranslate2 backend on CPU (`inter_threads` configurable), SSE streaming kept as is.
- Redis in compose (or Upstash).

Document the choice and the trade-offs in an ADR.

## Phase 1: Clean-up and tests
- [ ] Root `.gitignore`, `backend/models/.gitkeep`; remove the obsolete `version:` key from `docker-compose.yml`.
- [ ] Delete `pyproject.toml` (or fix it) and the UTF-16 `requirements_nllb.txt`.
- [ ] Remove file translation (backend modules and endpoints, frontend component, dependencies); update README and `CLAUDE.md`.
- [ ] Fix the API URL mismatch: one `API_BASE` in the frontend, Vite dev proxy, proxy config for `/translate` and `/health`.
- [ ] Introduce `TranslatorBackend` with `LocalBackend` (CTranslate2) and `RemoteBackend` (HTTP/client call, run off the event loop).
- [ ] Split backend requirements: gateway (slim) vs. local inference.
- [ ] Correctness fixes:
  - [ ] Raise translation errors instead of yielding `[Помилка…]` into the output text; proper SSE `error` events.
  - [ ] Cancel inference when the client disconnects.
  - [ ] Generic error messages to clients, details in server logs.
  - [ ] Fix CORS (no `*` with credentials).
  - [ ] Fix the device-selection race and the double model load in `LocalBackend`.
- [ ] pytest tests: sentence splitting, endpoints with a mocked backend, SSE format, error paths.
- [ ] CI (GitHub Actions): ruff, pytest, `npm run lint`, `npm run build`.
- [ ] Small refactor: split `main.py` (config, routers, Windows DLL setup in its own module); `pydantic-settings` instead of the hand-rolled `.env` loader; remove TypeScript `any`; configurable CPU threads.

## Phase 2: Minimal live demo
- [ ] Simple rate limiting: per-IP limit plus a signed anonymous-session cookie (counters in Redis for Option A, or nginx/in-process for Option B).
- [ ] Graceful handling of slow or unavailable inference in the UI (loading state, timeouts, clear errors).
- [ ] Dockerfiles: non-root user, healthcheck, consistent versions; CPU-only compose profile.
- [ ] Deploy (Option A or B), domain and HTTPS.
- [ ] README with: description and screenshot/GIF, live link, architecture diagram, quick start, how to reproduce, API table, evaluation scores (base vs. fine-tuned), link to the paper, limitations, license and model credits.
- [ ] Replace the Vite template `frontend/README.md`.
- [ ] Put converter, fine-tuning and evaluation scripts in a `training/` folder with its own `requirements.txt`, outside the Docker build context; link model and dataset on HuggingFace.
- [ ] Put the tokenizer next to the converted model on HuggingFace; document the NLLB licence (CC-BY-NC) and credit Meta.

## Phase 3: Cache
- [ ] Redis cache for repeated sentences.
- [ ] (Optional) Message broker and worker: only worth adding if a real async workload appears (e.g. batch translation API, or file translation returns).

## Phase 4: Observability
- [ ] Prometheus metrics (latency, errors, tokens/s, inference cold starts), Grafana dashboards, structured logs, tracing across services.
- [ ] Dependabot and dependency scanning.

## Phase 5: ML pipeline (separate repo)
- [ ] Move `training/` to its own repo.
- [ ] DVC for data and pipeline stages (prep, train, convert, eval); MLflow for experiments and model registry.
- [ ] Data collection: crawl plus quality filtering (language ID, alignment, deduplication, licence check).
- [ ] Scheduled retraining (cron/Prefect/Airflow) with an evaluation gate: a new model replaces the old only if it beats it on a fixed held-out test set.
- [ ] Human-corrected translations only as training data (e.g. a "suggest a better translation" feature), not raw model output.

## Phase 6: Accounts and quotas
- [ ] User accounts (Postgres, JWT or sessions) and per-user rate limits/quotas.

## Optional / later
- [ ] Bring file translation back as its own phase (async jobs, TTL'd results).
- [ ] Bosnian-aware sentence splitter.
- [ ] GPU request batching in the local backend.
- [ ] More ADR notes for main decisions.

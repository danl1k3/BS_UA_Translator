# Roadmap

Goal: a portfolio-ready project, first as a minimal live demo, then growing toward a production-grade ML service.
Work on branches, one PR per phase (or sub-phase), merge into `main`.

## Deployment options

The backend talks to inference only through a `TranslatorBackend` interface (Phase 1), so both options share the same code.
Measured RAM of the int8 model: about 800 MB, so a VPS needs at least 2 GB.

### Option A: Split services (gateway + hosted inference)
- **Gateway:** FastAPI on a Heroku Basic dyno (about $7/month, does not sleep). Slim image: no `ctranslate2`, `sentencepiece`, `pynvml`, no CUDA.
- **Inference:** the model on HF Space, called through a `RemoteBackend`. May cold-start; the UI needs a "waking up" state and timeouts.
- **Cache / rate-limit counters / job results:** Upstash Redis (watch per-command billing: 1-2 commands per request).
- **Database:** Heroku Postgres (about $5/month, fits the remaining credit); used later for accounts.
- **Frontend:** built into the gateway image and served by FastAPI on the same dyno (one origin, no CORS). It can move to a CDN or static hosting later via `VITE_API_URL` and `CORS_ORIGINS`.
- Constraints to design for: Heroku 30 s first-byte limit and 55 s idle limit (long file jobs must be async: submit job, then poll/stream status); ephemeral filesystem (job results go to Redis with a TTL, or object storage for big files).
- Pros: multiple services with clear boundaries (light I/O-bound gateway vs. memory-hungry model), cheap, covered by student credit. Cons: two platforms to debug, inference cold starts.

### Option B: Monolith on one VPS
- Whole stack via docker compose on a 2-4 GB VPS (student credit: Azure, DigitalOcean or similar; verify current terms), with nginx, domain, HTTPS (Let's Encrypt), swap file.
- Local CTranslate2 backend on CPU (`inter_threads` configurable), SSE streaming and progress kept as they are.
- Redis in compose (or Upstash).
- Pros: one place to operate, no cold starts, shows deployment skills. Cons: slower inference on 1-2 vCPUs, credit runs out, single point of failure.

Document the choice and the trade-offs in an ADR (monolith vs. services, why this split).

## Phase 1: Clean-up and tests
- [ ] Root `.gitignore`, `backend/models/.gitkeep`; remove the obsolete `version:` key from `docker-compose.yml`.
- [ ] Delete `pyproject.toml` (or fix it) and the UTF-16 `requirements_nllb.txt`.
- [ ] Fix the API URL mismatch: one `API_BASE` in the frontend, Vite dev proxy, proxy config for `/translate` and `/health`.
- [ ] Introduce `TranslatorBackend` with `LocalBackend` (CTranslate2) and `RemoteBackend` (HTTP/client call, run off the event loop); everything else depends only on the interface.
- [ ] Split backend requirements: gateway (slim) vs. local inference.
- [ ] Correctness fixes:
  - [ ] Raise translation errors instead of yielding `[Помилка…]` into the output text.
  - [ ] `debug` defaults to `false` on file endpoints; return the translated file directly.
  - [ ] Upload size and file type limits.
  - [ ] TTL and size cap for `_results`, with cleanup.
  - [ ] Cancel running tasks on client disconnect.
  - [ ] Generic error messages to clients, details in server logs.
  - [ ] Fix CORS (no `*` with credentials).
- [ ] Write pytest tests before refactoring: sentence splitting, docx run distribution, endpoints with a mocked backend.
- [ ] CI (GitHub Actions): ruff, pytest, `npm run lint`, `npm run build`.
- [ ] Small refactor: split `main.py` (config, routers, one Content-Disposition helper, Windows DLL setup in its own module); `pydantic-settings` instead of the hand-rolled `.env` loader; remove TypeScript `any`; configurable CPU threads.

## Phase 2: Minimal live demo
- [ ] Simple rate limiting: per-IP limit plus a signed anonymous-session cookie (counters in Redis for Option A, or nginx/in-process for Option B).
- [ ] Graceful handling of slow or unavailable inference in the UI (loading state, timeouts, clear errors).
- [ ] Async file jobs: submit, poll/stream status, fetch result; results stored with a TTL (required by Heroku's request limits).
- [ ] Dockerfiles: non-root user, healthcheck, consistent versions; CPU-only compose profile.
- [ ] Deploy (Option A or B), domain and HTTPS.
- [ ] README with: description and screenshot/GIF, live link, architecture diagram, quick start, how to reproduce, API table, evaluation scores (base vs. fine-tuned), link to the paper, limitations, license and model credits.
- [ ] Replace the Vite template `frontend/README.md`.
- [ ] Put converter, fine-tuning and evaluation scripts in a `training/` folder with its own `requirements.txt`, outside the Docker build context; link model and dataset on HuggingFace.
- [ ] Put the tokenizer next to the converted model on HuggingFace; document the NLLB licence (CC-BY-NC) and credit Meta.

## Phase 3: Cache and queue
- [ ] Redis cache for repeated sentences.
- [ ] Message broker (RabbitMQ, or Redis-backed worker) for file jobs, with a separate worker process.

## Phase 4: Observability
- [ ] Prometheus metrics (latency, queue depth, errors, tokens/s, inference cold starts), Grafana dashboards, structured logs, tracing across services.
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
- [ ] Bosnian-aware sentence splitter.
- [ ] GPU request batching in the local backend.
- [ ] More ADR notes for main decisions (why CTranslate2, why RabbitMQ and not Kafka).

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .backends import GradioBackend, TranslatorBackend
from .config import Settings
from .job_queue import JobQueue
from .rate_limiter import RateLimitMiddleware
from .routers.health import router as health_router
from .routers.translate import router as translate_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_MULTIPART_OVERHEAD_BYTES = 64 * 1024


def create_backend(settings: Settings) -> TranslatorBackend:
    return GradioBackend(
        base_url=settings.remote_inference_url,
        timeout=settings.remote_timeout_seconds,
        api_token=settings.remote_api_token,
    )


def create_app(
    settings: Settings | None = None,
    backend: TranslatorBackend | None = None,
) -> FastAPI:
    """Create and configure the gateway FastAPI application."""
    cfg = settings or Settings()

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        if fastapi_app.state.backend is None:
            fastapi_app.state.backend = create_backend(cfg)
        fastapi_app.state.jobs.start()
        yield
        await fastapi_app.state.jobs.stop()

    app = FastAPI(title="BalkanTranslate Gateway API", lifespan=lifespan)
    app.state.settings = cfg
    app.state.backend = backend
    app.state.jobs = JobQueue(
        max_queued=cfg.max_queued_jobs,
        result_ttl_seconds=cfg.result_ttl_seconds,
        max_stored=cfg.max_stored_results,
    )

    # Middleware added later wraps the earlier ones.
    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        """Refuse large requests before the body is read or spooled to disk."""
        if request.method == "POST":
            length = request.headers.get("content-length", "")
            if not length.isdigit():
                return JSONResponse({"detail": "Content-Length required"}, status_code=411)
            if int(length) > cfg.max_upload_bytes + _MULTIPART_OVERHEAD_BYTES:
                return JSONResponse({"detail": "Файл завеликий"}, status_code=413)
        return await call_next(request)

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=cfg.rate_limit_rpm,
        burst=cfg.rate_limit_burst,
        cookie_secret=cfg.cookie_secret,
    )
    @app.middleware("http")
    async def forbid_caching_api(request: Request, call_next):
        """Translations and job states must not be stored by a CDN or a browser."""
        response = await call_next(request)
        if request.url.path == "/health" or request.url.path.startswith("/translate/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # Outermost: preflights are answered first and error responses keep CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(translate_router)
    # Mounted last so that API routes take precedence
    if Path(cfg.static_dir).is_dir():
        app.mount("/", StaticFiles(directory=cfg.static_dir, html=True), name="frontend")
    return app


app = create_app()

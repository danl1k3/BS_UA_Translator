import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .backends import RemoteBackend, TranslatorBackend
from .config import Settings
from .file_translator import FileTranslationManager
from .monitor import HealthChecker
from .queue_manager import TranslationQueueManager
from .rate_limiter import RateLimitMiddleware
from .routers.health import router as health_router
from .routers.translate import router as translate_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _create_backend(settings: Settings) -> TranslatorBackend:
    return RemoteBackend(
        base_url=settings.remote_inference_url,
        timeout=settings.remote_timeout_seconds,
        api_token=settings.remote_api_token,
    )


def _wire_dependencies(
    app: FastAPI, cfg: Settings, active_backend: TranslatorBackend
) -> None:
    health_checker = HealthChecker()
    queue_manager = TranslationQueueManager(
        active_backend,
        health_checker,
        max_concurrency=cfg.max_concurrent_translations,
    )
    file_manager = FileTranslationManager(
        queue_manager,
        active_backend,
        result_ttl_seconds=cfg.result_ttl_seconds,
        max_stored_results=cfg.max_stored_results,
    )
    app.state.settings = cfg
    app.state.backend = active_backend
    app.state.health_checker = health_checker
    app.state.queue_manager = queue_manager
    app.state.file_manager = file_manager


def create_app(
    settings: Settings | None = None,
    backend: TranslatorBackend | None = None,
) -> FastAPI:
    """Create and configure the Heroku gateway FastAPI application."""
    cfg = settings or Settings()

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        if getattr(fastapi_app.state, "backend", None) is None:
            _wire_dependencies(fastapi_app, cfg, _create_backend(cfg))
        yield

    app = FastAPI(title="BalkanTranslate Gateway API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=cfg.rate_limit_rpm,
        burst=cfg.rate_limit_burst,
        cookie_secret=cfg.cookie_secret,
    )

    if backend is not None:
        _wire_dependencies(app, cfg, backend)

    app.include_router(health_router)
    app.include_router(translate_router)
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

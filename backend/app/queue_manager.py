import asyncio
import logging
from typing import AsyncGenerator

from .backends import TranslatorBackend
from .monitor import HealthChecker

logger = logging.getLogger(__name__)


class TranslationQueueManager:
    """Manages concurrency and delegates translation requests to a TranslatorBackend."""

    def __init__(
        self,
        backend: TranslatorBackend,
        monitor: HealthChecker,
        max_concurrency: int = 16,
    ):
        self.backend = backend
        self.monitor = monitor
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.active_tasks_count = 0

    async def get_current_status(self):
        """Return current gateway and inference health status for /health."""
        status = self.monitor.get_status(queue_size=self.active_tasks_count)
        remote_health = await self.backend.check_health()
        if remote_health is not None:
            status["inference"] = remote_health
            if remote_health.get("reachable") is False:
                status["status"] = remote_health.get("status", "Waking up")
        return status

    async def stream_translation(
        self, text: str, target_lang: str, source_lang: str
    ) -> AsyncGenerator[str, None]:
        """Acquire semaphore and stream translation chunks from the backend."""
        self.active_tasks_count += 1
        try:
            async with self.semaphore:
                async for chunk in self.backend.translate_stream(
                    text, source_lang, target_lang
                ):
                    yield chunk
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Translation error in queue manager")
            raise
        finally:
            self.active_tasks_count -= 1

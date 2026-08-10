import asyncio
from typing import AsyncGenerator
from .translator import NLLBTranslator
from .monitor import HealthChecker

class TranslationQueueManager:
    """
    Клас для керування чергою та розподілу навантаження.
    Оновлено для підтримки вибору мови-джерела.
    """

    def __init__(self, translator: NLLBTranslator, monitor: HealthChecker):
        self.translator = translator
        self.monitor = monitor
        self.gpu_semaphore = asyncio.Semaphore(4)
        self.cpu_semaphore = asyncio.Semaphore(8)
        self.active_tasks_count = 0

    def get_current_status(self):
        """Повертає поточний стан системи для /health ендпоінту."""
        return self.monitor.get_status(queue_size=self.active_tasks_count)
    async def stream_translation(self, text: str, target_lang: str, source_lang: str) -> AsyncGenerator[str, None]:
        """Обробляє запит, передаючи параметри мов у двигун."""
        self.active_tasks_count += 1
        status_info = self.monitor.get_status(queue_size=self.active_tasks_count - 1)
        recommended_device = status_info["device"]
        
        try:
            if recommended_device == "cuda" and not self.gpu_semaphore.locked():
                async with self.gpu_semaphore:
                    async for chunk in self._execute_inference(text, source_lang, target_lang, "cuda"):
                        yield chunk
            else:
                async with self.cpu_semaphore:
                    async for chunk in self._execute_inference(text, source_lang, target_lang, "cpu"):
                        yield chunk
        finally:
            self.active_tasks_count -= 1

    async def _execute_inference(self, text: str, source_lang: str, target_lang: str, device: str) -> AsyncGenerator[str, None]:
        """Запускає процес генерації в окремому потоці."""
        loop = asyncio.get_running_loop()
        sync_gen = self.translator.translate_stream(text, source_lang, target_lang, device=device)

        def safe_next():
            try:
                return next(sync_gen)
            except StopIteration:
                return None
            except Exception as e:
                return e

        while True:
            result = await loop.run_in_executor(None, safe_next)
            if result is None: break
            if isinstance(result, Exception):
                yield f" [Помилка: {str(result)}] "
                break
            yield result
            await asyncio.sleep(0.01)
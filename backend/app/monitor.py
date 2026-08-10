import psutil
import pynvml
import time
from typing import Dict, Any

class HealthChecker:
    """
    Модуль для моніторингу ресурсів системи (CPU, RAM, VRAM).
    Допомагає визначити, чи здатна система обробити запит на GPU.
    """

    def __init__(self):
        # Ініціалізація NVML для моніторингу NVIDIA GPU
        self.gpu_available = False
        try:
            pynvml.nvmlInit()
            self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.gpu_available = True
        except Exception as e:
            print(f"GPU мониторинг недоступний: {e}")

        # Для розрахунку ETA
        self.avg_time_per_char = 0.005  # Базовий час на 1 символ (в секундах)
        self.last_requests_times = []

    def get_gpu_metrics(self) -> Dict[str, Any]:
        """Отримує дані про стан відеопам'яті."""
        if not self.gpu_available:
            return {"free_vram": 0, "total_vram": 0, "usage_percent": 0}

        info = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
        return {
            "free_vram": info.free / (1024**2),  # в МБ
            "total_vram": info.total / (1024**2),
            "usage_percent": (info.used / info.total) * 100
        }

    def get_system_metrics(self) -> Dict[str, Any]:
        """Отримує загальні дані про CPU та RAM."""
        return {
            "cpu_usage": psutil.cpu_percent(interval=None),
            "ram_usage": psutil.virtual_memory().percent,
            "free_ram": psutil.virtual_memory().available / (1024**2)
        }

    def get_status(self, queue_size: int = 0) -> Dict[str, Any]:
        """
        Визначає статус системи та рекомендований девайс.
        Логіка згідно ТЗ: якщо free_vram < 500MB -> Slow Mode.
        """
        gpu = self.get_gpu_metrics()
        sys = self.get_system_metrics()
        
        # Визначаємо режим роботи
        mode = "Normal"
        recommended_device = "cuda" if self.gpu_available else "cpu"

        if self.gpu_available and gpu["free_vram"] < 500:
            mode = "Slow Mode (Low VRAM)"
            recommended_device = "cpu"
        elif sys["cpu_usage"] > 90:
            mode = "Overloaded"
            recommended_device = "cuda" if self.gpu_available else "cpu"

        # Розрахунок ETA (приблизний)
        eta = (queue_size + 1) * 1.5 # Базово 1.5 сек на запит

        return {
            "status": mode,
            "device": recommended_device,
            "metrics": {
                "gpu": gpu,
                "system": sys
            },
            "queue_size": queue_size,
            "eta_seconds": round(eta, 1),
            "warning": "Велика черга. Використовується режим енергозбереження (CPU)." if recommended_device == "cpu" and self.gpu_available else None
        }

    def __del__(self):
        if self.gpu_available:
            try:
                pynvml.nvmlShutdown()
            except:
                pass
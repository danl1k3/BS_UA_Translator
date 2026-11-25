from typing import Any, Dict

import psutil


class HealthChecker:
    """Monitors gateway CPU/RAM and queue depth."""

    def get_system_metrics(self) -> Dict[str, Any]:
        """Return CPU and RAM usage metrics for the gateway dyno."""
        return {
            "cpu_usage": psutil.cpu_percent(interval=None),
            "ram_usage": psutil.virtual_memory().percent,
            "free_ram": psutil.virtual_memory().available / (1024**2),
        }

    def get_status(self, queue_size: int = 0) -> Dict[str, Any]:
        """Determine gateway status and estimated queue wait time."""
        sys_metrics = self.get_system_metrics()
        mode = "Overloaded" if sys_metrics["cpu_usage"] > 90 else "Normal"
        eta = (queue_size + 1) * 1.5

        return {
            "status": mode,
            "device": "remote",
            "metrics": {
                "system": sys_metrics,
            },
            "queue_size": queue_size,
            "eta_seconds": round(eta, 1),
            "warning": None,
        }

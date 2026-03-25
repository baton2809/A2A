import logging
import os

log = logging.getLogger(__name__)


class Config:
    """Настройки gateway из переменных окружения."""

    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    otel_endpoint: str = os.getenv("OTEL_ENDPOINT", "http://localhost:4317")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Начальные провайдеры: "name:url:weight,name2:url2:weight2"
    providers_raw: str = os.getenv("PROVIDERS", "")

    def initial_providers(self) -> list[dict]:
        """Разбирает PROVIDERS из env в список словарей."""
        result = []
        for entry in self.providers_raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            if len(parts) < 2:
                log.warning("Некорректная запись провайдера: %s", entry)
                continue
            name = parts[0]
            # URL может содержать ':', поэтому собираем его обратно
            # Формат: name:scheme:host:port:weight или name:url:weight
            if len(parts) == 3:
                name, url, weight = parts[0], parts[1], parts[2]
            elif len(parts) >= 4:
                name = parts[0]
                weight = parts[-1]
                url = ":".join(parts[1:-1])
            else:
                name, url, weight = parts[0], parts[1], "1"
            try:
                result.append({"name": name, "url": url, "weight": int(weight)})
            except ValueError:
                result.append({"name": name, "url": url, "weight": 1})
        return result


cfg = Config()

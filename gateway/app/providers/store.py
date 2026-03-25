import collections
import json
import logging
import time

import redis.asyncio as aioredis

from ..config import cfg
from .schema import LLMProvider

log = logging.getLogger(__name__)

_REDIS_KEY = "gw:providers"
_EMA_ALPHA = 0.2              # коэффициент сглаживания EMA задержки
_OPEN_THRESHOLD = 5           # ошибок подряд до открытия circuit breaker
_BASE_COOLDOWN_S = 60.0       # начальная пауза при открытом circuit breaker
_RPM_WINDOW_S = 60.0          # окно подсчёта RPM


class ProviderStore:
    """
    Хранилище провайдеров с Redis-бэкендом.
    При недоступности Redis работает с in-memory кешем.
    """

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._cache: dict[str, LLMProvider] = {}
        # Скользящее окно RPM: имя провайдера → deque timestamp'ов запросов
        self._rpm_window: dict[str, collections.deque] = collections.defaultdict(collections.deque)

    async def connect(self) -> None:
        try:
            self._redis = aioredis.from_url(cfg.redis_url, decode_responses=True)
            await self._redis.ping()
            log.info("ProviderStore подключён к Redis: %s", cfg.redis_url)
        except Exception as exc:
            log.warning("Redis недоступен (%s), работаю in-memory", exc)
            self._redis = None

    # ------------------------------------------------------------------ #
    # CRUD                                                                  #
    # ------------------------------------------------------------------ #

    async def add(self, provider: LLMProvider) -> None:
        self._cache[provider.name] = provider
        if self._redis:
            try:
                await self._redis.hset(_REDIS_KEY, provider.name, provider.model_dump_json())
            except Exception:
                pass

    async def remove(self, name: str) -> bool:
        existed = name in self._cache
        self._cache.pop(name, None)
        if self._redis:
            try:
                await self._redis.hdel(_REDIS_KEY, name)
            except Exception:
                pass
        return existed

    async def all(self) -> list[LLMProvider]:
        """Возвращает список всех провайдеров, синхронизируясь с Redis."""
        if self._redis:
            try:
                raw = await self._redis.hgetall(_REDIS_KEY)
                providers = [LLMProvider.model_validate(json.loads(v)) for v in raw.values()]
                self._cache = {p.name: p for p in providers}
            except Exception:
                pass
        return list(self._cache.values())

    async def available(self) -> list[LLMProvider]:
        """Провайдеры без открытого circuit breaker и без превышения RPM лимита."""
        now = time.time()
        result = []
        for p in await self.all():
            if p.cooldown_until >= now:
                continue
            if p.request_limit > 0 and self._current_rpm(p.name, now) >= p.request_limit:
                log.debug("Провайдер %s: RPM лимит достигнут (%d)", p.name, p.request_limit)
                continue
            result.append(p)
        return result

    def _current_rpm(self, name: str, now: float) -> int:
        """Количество запросов к провайдеру за последние 60 секунд."""
        dq = self._rpm_window[name]
        cutoff = now - _RPM_WINDOW_S
        while dq and dq[0] < cutoff:
            dq.popleft()
        return len(dq)

    def record_request(self, name: str) -> None:
        """Фиксирует факт отправки запроса провайдеру (для RPM-счётчика)."""
        self._rpm_window[name].append(time.time())

    # ------------------------------------------------------------------ #
    # Обновление runtime-состояния                                         #
    # ------------------------------------------------------------------ #

    async def record_ok(self, name: str, latency: float) -> None:
        """Обновляет EMA задержки и сбрасывает счётчик ошибок."""
        providers = await self.all()
        for p in providers:
            if p.name != name:
                continue
            if p.latency_ema == 0.0:
                p.latency_ema = latency
            else:
                p.latency_ema = _EMA_ALPHA * latency + (1 - _EMA_ALPHA) * p.latency_ema
            p.error_streak = 0
            p.healthy = True
            await self.add(p)
            break

    async def record_error(self, name: str) -> None:
        """Увеличивает счётчик ошибок, при необходимости открывает circuit breaker."""
        providers = await self.all()
        for p in providers:
            if p.name != name:
                continue
            p.error_streak += 1
            if p.error_streak >= _OPEN_THRESHOLD:
                p.healthy = False
                # cooldown удваивается с каждым новым открытием: 60 → 120 → 240 → 480 (cap 600)
                multiplier = 2 ** (p.error_streak - _OPEN_THRESHOLD)
                cooldown = min(_BASE_COOLDOWN_S * multiplier, 600.0)
                p.cooldown_until = time.time() + cooldown
                log.warning(
                    "Circuit breaker открыт для %s (streak=%d, cooldown=%.0fs)",
                    name, p.error_streak, cooldown
                )
            await self.add(p)
            break


store = ProviderStore()

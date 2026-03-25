"""
RoutingEngine — основная точка выбора провайдера.

Алгоритм:
1. Из пула выбираем только доступных (cooldown_until в прошлом).
2. Новые провайдеры без замеров EMA идут первыми — получают первый реальный замер.
3. Из остальных — минимальная EMA-задержка с 10% допуском (случайный выбор среди лучших).
4. Если все на паузе (крайний случай) — возвращаем того, чей cooldown заканчивается раньше.
"""

import time

from ..providers.schema import LLMProvider
from .base import BaseRouter
from .weighted import WeightedRouter

_fallback = WeightedRouter()


class RoutingEngine(BaseRouter):

    def pick(self, providers: list[LLMProvider]) -> LLMProvider | None:
        if not providers:
            return None

        now = time.time()
        available = [p for p in providers if p.cooldown_until < now]

        if not available:
            # Все на паузе — берём того, кто восстановится раньше всех
            return min(providers, key=lambda p: p.cooldown_until)

        # Высокоприоритетные провайдеры имеют преимущество
        max_priority = max(p.priority for p in available)
        if max_priority > 0:
            top = [p for p in available if p.priority == max_priority]
        else:
            top = available

        # Новые провайдеры без замеров идут первыми
        fresh = [p for p in top if p.latency_ema == 0.0]
        if fresh:
            return _fallback.pick(fresh)

        # Наименьшая EMA с 10% допуском для случайного выбора среди лучших
        min_ema = min(p.latency_ema for p in top)
        best = [p for p in top if p.latency_ema <= min_ema * 1.1]
        return _fallback.pick(best)

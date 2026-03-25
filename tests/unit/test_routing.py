"""Тесты стратегий маршрутизации."""
import pytest

from gateway.app.providers.schema import LLMProvider
from gateway.app.routing.engine import RoutingEngine
from gateway.app.routing.round_robin import RoundRobinRouter
from gateway.app.routing.weighted import WeightedRouter


def make_provider(
    name: str,
    latency: float = 0.0,
    cooldown: float = 0.0,
    priority: int = 0,
) -> LLMProvider:
    return LLMProvider(
        name=name, url=f"http://{name}:9000",
        latency_ema=latency, cooldown_until=cooldown, priority=priority,
    )


class TestRoundRobin:
    def test_cycles_through_providers(self):
        rr = RoundRobinRouter()
        providers = [make_provider("a"), make_provider("b"), make_provider("c")]
        selected = [rr.pick(providers).name for _ in range(6)]
        assert selected == ["a", "b", "c", "a", "b", "c"]

    def test_returns_none_on_empty(self):
        rr = RoundRobinRouter()
        assert rr.pick([]) is None

    def test_single_provider(self):
        rr = RoundRobinRouter()
        p = make_provider("only")
        assert rr.pick([p]).name == "only"
        assert rr.pick([p]).name == "only"


class TestWeighted:
    def test_returns_from_list(self):
        wr = WeightedRouter()
        providers = [make_provider("a"), make_provider("b")]
        for _ in range(20):
            result = wr.pick(providers)
            assert result.name in ("a", "b")

    def test_returns_none_on_empty(self):
        assert WeightedRouter().pick([]) is None

    def test_single_provider_always_selected(self):
        wr = WeightedRouter()
        p = make_provider("solo", latency=0.5)
        for _ in range(10):
            assert wr.pick([p]).name == "solo"


class TestRoutingEngine:
    def test_prefers_fresh_provider(self):
        engine = RoutingEngine()
        p_fresh = make_provider("fresh", latency=0.0)
        p_old = make_provider("old", latency=2.0)
        # Свежий провайдер (без замеров) должен получить приоритет
        selected = engine.pick([p_old, p_fresh])
        assert selected.name == "fresh"

    def test_prefers_lower_latency(self):
        engine = RoutingEngine()
        fast = make_provider("fast", latency=0.1)
        slow = make_provider("slow", latency=1.5)
        assert engine.pick([fast, slow]).name == "fast"

    def test_skips_providers_on_cooldown(self):
        import time
        engine = RoutingEngine()
        on_cooldown = make_provider("cooling", latency=0.1, cooldown=time.time() + 9999)
        available = make_provider("available", latency=5.0)
        result = engine.pick([on_cooldown, available])
        assert result.name == "available"

    def test_falls_back_when_all_on_cooldown(self):
        import time
        engine = RoutingEngine()
        p1 = make_provider("p1", cooldown=time.time() + 100)
        p2 = make_provider("p2", cooldown=time.time() + 200)
        result = engine.pick([p1, p2])
        # Должен вернуть хоть кого-то (того, чей cooldown меньше)
        assert result is not None
        assert result.name == "p1"

    def test_priority_overrides_latency(self):
        engine = RoutingEngine()
        # Медленный, но высокоприоритетный провайдер должен победить быстрый
        fast_low = make_provider("fast-low", latency=0.05, priority=0)
        slow_high = make_provider("slow-high", latency=2.0, priority=10)
        for _ in range(10):
            assert engine.pick([fast_low, slow_high]).name == "slow-high"

    def test_empty_returns_none(self):
        assert RoutingEngine().pick([]) is None

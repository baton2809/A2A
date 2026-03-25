"""Тесты ProviderStore."""
import time

import pytest

from gateway.app.providers.schema import LLMProvider
from gateway.app.providers.store import ProviderStore


@pytest.fixture
def store():
    s = ProviderStore()
    # Без Redis — in-memory режим
    return s


def make_p(name: str) -> LLMProvider:
    return LLMProvider(name=name, url=f"http://{name}:9000")


@pytest.mark.asyncio
async def test_add_and_list(store):
    await store.add(make_p("alpha"))
    await store.add(make_p("beta"))
    names = {p.name for p in await store.all()}
    assert names == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_remove(store):
    await store.add(make_p("temp"))
    ok = await store.remove("temp")
    assert ok is True
    assert not any(p.name == "temp" for p in await store.all())


@pytest.mark.asyncio
async def test_remove_nonexistent(store):
    assert await store.remove("ghost") is False


@pytest.mark.asyncio
async def test_record_ok_updates_ema(store):
    await store.add(make_p("x"))
    await store.record_ok("x", 0.5)
    providers = await store.all()
    p = next(p for p in providers if p.name == "x")
    assert p.latency_ema == pytest.approx(0.5, abs=0.01)
    assert p.error_streak == 0
    assert p.healthy is True


@pytest.mark.asyncio
async def test_ema_smoothing(store):
    await store.add(make_p("y"))
    await store.record_ok("y", 1.0)  # ema = 1.0 (first sample)
    await store.record_ok("y", 0.0)  # ema = 0.2 * 0.0 + 0.8 * 1.0 = 0.8
    providers = await store.all()
    p = next(p for p in providers if p.name == "y")
    assert p.latency_ema == pytest.approx(0.8, abs=0.01)


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold(store):
    await store.add(make_p("cb"))
    for _ in range(5):  # threshold = 5
        await store.record_error("cb")
    providers = await store.all()
    p = next(p for p in providers if p.name == "cb")
    assert p.healthy is False
    assert p.cooldown_until > time.time()


@pytest.mark.asyncio
async def test_available_excludes_cooldown(store):
    await store.add(make_p("good"))
    bad = LLMProvider(name="bad", url="http://bad:9000", cooldown_until=time.time() + 9999)
    await store.add(bad)
    available = await store.available()
    names = {p.name for p in available}
    assert "good" in names
    assert "bad" not in names


@pytest.mark.asyncio
async def test_available_excludes_rpm_exceeded(store):
    """Провайдер с исчерпанным RPM лимитом не попадает в available()."""
    limited = LLMProvider(name="limited", url="http://limited:9000", request_limit=3)
    await store.add(limited)
    # Фиксируем 3 запроса — ровно на лимите
    store.record_request("limited")
    store.record_request("limited")
    store.record_request("limited")
    available = await store.available()
    assert not any(p.name == "limited" for p in available)


@pytest.mark.asyncio
async def test_unlimited_provider_always_available(store):
    """Провайдер с request_limit=0 (безлимитный) всегда доступен."""
    unlimited = LLMProvider(name="unlimited", url="http://unlimited:9000", request_limit=0)
    await store.add(unlimited)
    for _ in range(1000):
        store.record_request("unlimited")
    available = await store.available()
    assert any(p.name == "unlimited" for p in available)

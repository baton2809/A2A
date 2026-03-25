"""A2A Agent Registry — регистрация и обнаружение агентов с фоновым health-check."""
import asyncio
import logging
import time

import httpx
from fastapi import FastAPI

from .api import router as agents_router
from .registry import registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)

app = FastAPI(title="Agent Registry", version="1.0.0")
app.include_router(agents_router)

_HEALTH_INTERVAL = 30.0  # seconds


@app.get("/healthz")
async def healthz():
    agents = await registry.list_all()
    return {"status": "ok", "service": "agent-registry", "agents": len(agents)}


@app.on_event("startup")
async def on_startup():
    await registry.connect()
    asyncio.create_task(_health_loop())
    log.info("Agent Registry запущен (health check каждые %.0fs)", _HEALTH_INTERVAL)


async def _health_loop():
    """Периодически проверяет /healthz у каждого зарегистрированного агента."""
    await asyncio.sleep(5.0)  # wait for services to start
    while True:
        try:
            agents = await registry.list_all()
            for agent in agents:
                healthy = await _ping(agent.url)
                if healthy != agent.healthy:
                    status = "восстановлен" if healthy else "недоступен"
                    log.info("Агент %s %s", agent.name, status)
                await registry.update_health(agent.name, healthy, time.time())
        except Exception as exc:
            log.error("Health loop error: %s", exc)
        await asyncio.sleep(_HEALTH_INTERVAL)


async def _ping(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/healthz")
            return resp.status_code == 200
    except Exception:
        return False

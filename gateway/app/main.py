import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from .api import auth, chat, health, providers
from .auth.guard import JWTGuard
from .config import cfg
from .providers.schema import LLMProvider
from .providers.store import store
from .providers.watcher import watch_providers
from .telemetry.metrics import init_telemetry

logging.basicConfig(
    level=getattr(logging, cfg.log_level, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)

app = FastAPI(
    title="LLM Gateway",
    description="Проксирует запросы к LLM-провайдерам с балансировкой, guardrails и метриками",
    version="2.0.0",
)

# JWT middleware (applied before routing)
app.add_middleware(JWTGuard)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(providers.router)

FastAPIInstrumentor.instrument_app(app)


@app.on_event("startup")
async def on_startup() -> None:
    init_telemetry()
    await store.connect()

    # Регистрируем начальных провайдеров из env
    for p_data in cfg.initial_providers():
        provider = LLMProvider(**p_data)
        await store.add(provider)
        log.info("Провайдер зарегистрирован: %s → %s (weight=%d)", provider.name, provider.url, provider.weight)

    asyncio.create_task(watch_providers())
    log.info("LLM Gateway v2 запущен (auth + guardrails enabled)")

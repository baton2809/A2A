import asyncio
import logging
import time

import httpx

from .store import store

log = logging.getLogger(__name__)


async def watch_providers(interval: float = 15.0) -> None:
    """
    Фоновая задача: периодически проверяет /healthz у каждого провайдера.

    Логика:
    - 200 OK → восстанавливаем провайдер (сбрасываем cooldown и error_streak).
    - Не 200 / ошибка сети + провайдер НЕ в cooldown → фиксируем ошибку.
    - Не 200 / ошибка сети + провайдер УЖЕ в cooldown → ничего не делаем,
      чтобы error_streak не рос и cooldown не удваивался во время паузы.
    """
    await asyncio.sleep(3.0)  # даём сервисам время подняться
    log.info("Provider watcher запущен (интервал=%.0fs)", interval)

    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            providers = await store.all()
            now = time.time()

            for p in providers:
                in_cooldown = p.cooldown_until > now
                try:
                    resp = await client.get(f"{p.url}/healthz")
                    if resp.status_code == 200:
                        if not p.healthy or in_cooldown:
                            p.healthy = True
                            p.error_streak = 0
                            p.cooldown_until = 0.0
                            await store.add(p)
                            log.info("Провайдер %s восстановлен", p.name)
                    elif not in_cooldown:
                        await store.record_error(p.name)
                except Exception as exc:
                    log.debug("Провайдер %s недоступен: %s", p.name, exc)
                    if not in_cooldown:
                        await store.record_error(p.name)

            await asyncio.sleep(interval)

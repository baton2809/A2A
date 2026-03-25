"""Реестр агентов с Redis и in-memory резервом, поиском по навыкам и тегам."""
import logging
import os

import redis.asyncio as redis

from .models import AgentCard

log = logging.getLogger(__name__)

_REDIS_KEY = "a2a:agents"


class AgentRegistry:
    def __init__(self):
        self._redis: redis.Redis | None = None
        self._cache: dict[str, AgentCard] = {}

    async def connect(self) -> None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        try:
            self._redis = redis.from_url(url, decode_responses=True)
            await self._redis.ping()
            log.info("AgentRegistry: подключение к Redis (%s)", url)
        except Exception as exc:
            log.warning("AgentRegistry: Redis недоступен (%s), используем in-memory", exc)
            self._redis = None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def add(self, card: AgentCard) -> None:
        self._cache[card.name] = card
        if self._redis:
            try:
                await self._redis.hset(_REDIS_KEY, card.name, card.model_dump_json())
            except Exception as exc:
                log.warning("AgentRegistry: Redis write error: %s", exc)

    async def get(self, name: str) -> AgentCard | None:
        if self._redis:
            try:
                raw = await self._redis.hget(_REDIS_KEY, name)
                if raw:
                    return AgentCard.model_validate_json(raw)
            except Exception:
                pass
        return self._cache.get(name)

    async def list_all(self) -> list[AgentCard]:
        if self._redis:
            try:
                data = await self._redis.hgetall(_REDIS_KEY)
                cards = [AgentCard.model_validate_json(v) for v in data.values()]
                self._cache = {c.name: c for c in cards}
                return cards
            except Exception:
                pass
        return list(self._cache.values())

    async def remove(self, name: str) -> bool:
        existed = name in self._cache
        self._cache.pop(name, None)
        if self._redis:
            try:
                deleted = await self._redis.hdel(_REDIS_KEY, name)
                if deleted:
                    existed = True
            except Exception:
                pass
        return existed

    async def update_health(self, name: str, healthy: bool, checked_at: float) -> None:
        card = await self.get(name)
        if card:
            card.healthy = healthy
            card.last_checked = checked_at
            await self.add(card)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self, skill: str | None = None, tag: str | None = None
    ) -> list[AgentCard]:
        agents = await self.list_all()
        result = []
        for agent in agents:
            if skill:
                kw = skill.lower()
                if not any(
                    kw in s.name.lower() or kw in s.description.lower()
                    for s in agent.skills
                ):
                    continue
            if tag:
                kw = tag.lower()
                if not any(kw in t.lower() for s in agent.skills for t in s.tags):
                    continue
            result.append(agent)
        return result


# Синглтон
registry = AgentRegistry()

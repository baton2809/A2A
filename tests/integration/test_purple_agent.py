"""Интеграционные тесты Purple Agent."""
import os

import httpx
import pytest

PURPLE_AGENT_URL = os.getenv("PURPLE_AGENT_URL", "http://localhost:8020")


@pytest.mark.integration
class TestPurpleAgent:
    async def test_healthz(self):
        async with httpx.AsyncClient(base_url=PURPLE_AGENT_URL) as client:
            resp = await client.get("/healthz")
            assert resp.status_code == 200

    async def test_agent_card(self):
        async with httpx.AsyncClient(base_url=PURPLE_AGENT_URL) as client:
            resp = await client.get("/.well-known/agent-card.json")
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "Purple Agent"
            assert "skills" in data
            assert len(data["skills"]) > 0

    async def test_tasks_send(self):
        async with httpx.AsyncClient(base_url=PURPLE_AGENT_URL, timeout=30.0) as client:
            resp = await client.post(
                "/tasks/send",
                json={"message": {"parts": [{"type": "text", "text": "Hello Purple Agent!"}]}},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "id" in data or "status" in data

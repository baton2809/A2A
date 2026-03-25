"""Интеграционные тесты реестра агентов."""
import os

import httpx
import pytest

REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8010")


@pytest.mark.integration
class TestAgentRegistry:
    async def test_healthz(self):
        async with httpx.AsyncClient(base_url=REGISTRY_URL) as client:
            resp = await client.get("/healthz")
            assert resp.status_code == 200

    async def test_list_agents(self):
        async with httpx.AsyncClient(base_url=REGISTRY_URL) as client:
            resp = await client.get("/agents")
            assert resp.status_code == 200
            assert "agents" in resp.json()

    async def test_agent_crud(self):
        agent_card = {
            "agent_card": {
                "name": "test-agent",
                "description": "Test agent for integration tests",
                "url": "http://localhost:9999",
                "version": "1.0.0",
                "skills": [{"id": "test", "name": "Test Skill", "description": "A test skill"}],
            }
        }
        async with httpx.AsyncClient(base_url=REGISTRY_URL) as client:
            # Создать
            resp = await client.post("/agents", json=agent_card)
            assert resp.status_code == 201

            # Прочитать
            resp = await client.get("/agents/test-agent")
            assert resp.status_code == 200
            assert resp.json()["name"] == "test-agent"

            # Список
            resp = await client.get("/agents")
            assert resp.status_code == 200
            names = [a["name"] for a in resp.json()["agents"]]
            assert "test-agent" in names

            # Удалить
            resp = await client.delete("/agents/test-agent")
            assert resp.status_code == 200

            # Проверить удаление
            resp = await client.get("/agents/test-agent")
            assert resp.status_code == 404

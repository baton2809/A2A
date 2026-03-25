"""Интеграционные тесты управления провайдерами."""
import os

import httpx
import pytest

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")


@pytest.mark.integration
class TestProviders:
    async def test_list_providers(self, auth_headers):
        async with httpx.AsyncClient(base_url=GATEWAY_URL) as client:
            resp = await client.get("/providers", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data          # API использует "items", а не "providers"
            assert len(data["items"]) >= 2  # mock-fast и mock-slow

    async def test_register_and_delete_provider(self, auth_headers):
        async with httpx.AsyncClient(base_url=GATEWAY_URL) as client:
            # Зарегистрировать
            resp = await client.post(
                "/providers",
                headers=auth_headers,
                json={"name": "test-provider", "url": "http://localhost:9999", "models": ["test"]},
            )
            assert resp.status_code == 201

            # Проверить наличие в списке
            resp = await client.get("/providers", headers=auth_headers)
            names = [p["name"] for p in resp.json()["items"]]
            assert "test-provider" in names

            # Удалить
            resp = await client.delete("/providers/test-provider", headers=auth_headers)
            assert resp.status_code == 200

            # Проверить удаление
            resp = await client.get("/providers", headers=auth_headers)
            names = [p["name"] for p in resp.json()["items"]]
            assert "test-provider" not in names

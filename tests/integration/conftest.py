"""Integration test fixtures."""
import os

import httpx
import pytest

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8010")
PURPLE_AGENT_URL = os.getenv("PURPLE_AGENT_URL", "http://localhost:8020")


@pytest.fixture
async def auth_token():
    """Get a valid JWT token from the gateway."""
    async with httpx.AsyncClient(base_url=GATEWAY_URL) as client:
        resp = await client.post("/auth/token", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200, f"Failed to get token: {resp.text}"
        return resp.json()["access_token"]


@pytest.fixture
async def auth_headers(auth_token):
    """Headers with Authorization bearer token."""
    return {"Authorization": f"Bearer {auth_token}"}

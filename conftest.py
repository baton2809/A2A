"""Root conftest — shared fixtures for all tests."""
import os

import pytest

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")


@pytest.fixture
def gateway_url():
    return GATEWAY_URL

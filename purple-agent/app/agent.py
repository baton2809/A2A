"""Purple Agent core logic with JWT caching, retry, and configurable model."""
import asyncio
import base64
import json
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8000")
GATEWAY_USER = os.getenv("GATEWAY_USER", "admin")
GATEWAY_PASS = os.getenv("GATEWAY_PASS", "admin")
LLM_MODEL = os.getenv("LLM_MODEL", "mock")

MAX_RETRIES = 3
RETRY_BACKOFFS = [0.5, 1.0, 2.0]

# Module-level JWT cache
_token_cache: dict = {"token": None, "expires_at": 0.0}


def _invalidate_token():
    """Clear cached JWT token."""
    _token_cache["token"] = None
    _token_cache["expires_at"] = 0.0


async def get_gateway_token() -> str:
    """Get JWT token from gateway, using cache when possible."""
    # Return cached token if still valid (60s safety margin)
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GATEWAY_URL}/auth/token",
            json={"username": GATEWAY_USER, "password": GATEWAY_PASS},
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]

        # Decode expiry from JWT payload (base64 middle segment)
        try:
            payload = token.split(".")[1]
            # Add padding
            payload += "=" * (4 - len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            expires_at = claims.get("exp", time.time() + 3600)
        except Exception:
            expires_at = time.time() + 3600

        _token_cache["token"] = token
        _token_cache["expires_at"] = expires_at
        logger.info("JWT token cached, expires at %s", expires_at)
        return token


async def _request_with_retry(method: str, url: str, token: str, **kwargs) -> httpx.Response:
    """Make HTTP request with retry and backoff. Invalidates JWT on 401."""
    last_error = None
    current_token = token

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method, url,
                    headers={"Authorization": f"Bearer {current_token}"},
                    **kwargs,
                )
                if resp.status_code == 401 and attempt < MAX_RETRIES - 1:
                    logger.warning("Got 401, refreshing JWT token (attempt %d)", attempt + 1)
                    _invalidate_token()
                    current_token = await get_gateway_token()
                    continue
                return resp
        except httpx.RequestError as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                backoff = RETRY_BACKOFFS[attempt]
                logger.warning("Request failed (attempt %d), retrying in %.1fs: %s", attempt + 1, backoff, e)
                await asyncio.sleep(backoff)
            else:
                raise

    raise last_error  # Should not reach here, but just in case


async def process_message(message: str) -> str:
    """Process a user message through the LLM gateway."""
    try:
        token = await get_gateway_token()
        resp = await _request_with_retry(
            "POST",
            f"{GATEWAY_URL}/v1/chat/completions",
            token,
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "You are Purple Agent, a helpful AI assistant from ITMO University."},
                    {"role": "user", "content": message},
                ],
            },
            timeout=30.0,
        )
        result = resp.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("Failed to process message: %s", e)
        return f"Purple Agent received your message: '{message[:100]}'. (Gateway unavailable: {str(e)[:50]})"


async def process_message_stream(message: str):
    """Stream a response through the LLM gateway."""
    try:
        token = await get_gateway_token()
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{GATEWAY_URL}/v1/chat/completions",
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are Purple Agent, a helpful AI assistant from ITMO University."},
                        {"role": "user", "content": message},
                    ],
                    "stream": True,
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=60.0,
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            chunk = json.loads(line[6:])
                            content = chunk["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass
    except Exception as e:
        logger.error("Stream failed: %s", e)
        yield f"Purple Agent: gateway unavailable ({str(e)[:50]})"

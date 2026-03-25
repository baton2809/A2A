"""
OpenAI-совместимый Mock LLM сервер.
Имитирует задержку реального провайдера, поддерживает streaming.
"""

import asyncio
import json
import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .responses import approx_tokens, build_reply

PROVIDER_NAME = os.getenv("PROVIDER_NAME", "mock")
LATENCY_MS = int(os.getenv("LATENCY_MS", "100"))
PORT = int(os.getenv("PORT", "9000"))

app = FastAPI(title=f"Mock LLM [{PROVIDER_NAME}]")


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "provider": PROVIDER_NAME, "latency_ms": LATENCY_MS}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages: list[dict] = body.get("messages", [])
    stream: bool = body.get("stream", False)

    # имитируем задержку провайдера
    await asyncio.sleep(LATENCY_MS / 1000.0)

    reply = build_reply(messages)
    cid = f"chatcmpl-{uuid.uuid4().hex[:16]}"
    created = int(time.time())
    n_in = sum(approx_tokens(m.get("content", "")) for m in messages)
    n_out = approx_tokens(reply)

    if stream:
        return StreamingResponse(
            _sse_stream(cid, created, reply),
            media_type="text/event-stream",
            headers={"X-Provider": PROVIDER_NAME},
        )

    return JSONResponse(
        {
            "id": cid,
            "object": "chat.completion",
            "created": created,
            "model": f"{PROVIDER_NAME}-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": n_in,
                "completion_tokens": n_out,
                "total_tokens": n_in + n_out,
            },
        },
        headers={"X-Provider": PROVIDER_NAME},
    )


async def _sse_stream(cid: str, created: int, text: str):
    words = text.split()
    for i, word in enumerate(words):
        delta = {"content": word + " "}
        if i == 0:
            delta["role"] = "assistant"

        chunk = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": f"{PROVIDER_NAME}-model",
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.03)

    final = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": f"{PROVIDER_NAME}-model",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"

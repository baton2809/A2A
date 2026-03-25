"""
Основной эндпоинт: проксирует запросы к LLM-провайдерам.

Поддерживает:
- потоковую передачу (Server-Sent Events)
- маршрутизацию по имени модели
- автоматический retry с другим провайдером при ошибке
- guardrails: блокировка prompt-injection и сканирование секретов в ответе
- inline оценку качества ответа (EvalResult -> MLFlow)
- запись метрик OTel
"""

import json
import logging
import time
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..evaluation import evaluate_response, log_to_mlflow
from ..guardrails.scanner import detect_injection, detect_secrets
from ..models import CompletionRequest
from ..providers.store import store
from ..routing.engine import RoutingEngine
from ..telemetry import metrics as m

log = logging.getLogger(__name__)
router = APIRouter(tags=["completions"])
_router = RoutingEngine()

_MAX_ATTEMPTS = 3


@router.post("/v1/chat/completions")
async def completions(req: Request, body: CompletionRequest):
    req_id = req.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    log.info("[%s] model=%s stream=%s", req_id, body.model, body.stream)

    # --- Guardrail: prompt injection check ---
    user_text = " ".join(
        msg.content for msg in body.messages if isinstance(msg.content, str)
    )
    matched = detect_injection(user_text)
    if matched:
        m.provider_errors_total.add(1, {"provider": "guardrail", "reason": "injection"})
        log.warning("[%s] Prompt injection blocked: %r", req_id, matched)
        raise HTTPException(400, f"Запрос отклонён: обнаружен prompt injection ({matched!r})")

    providers = await store.available()
    if not providers:
        raise HTTPException(503, "Нет доступных провайдеров")

    # Сначала пробуем провайдеров, явно поддерживающих модель
    matching = [p for p in providers if body.model in p.models or "*" in p.models]
    pool = matching or providers

    tried: set[str] = set()

    for attempt in range(min(_MAX_ATTEMPTS, len(pool))):
        candidates = [p for p in pool if p.name not in tried]
        if not candidates:
            break

        provider = _router.pick(candidates)
        if not provider:
            break
        tried.add(provider.name)

        target_url = f"{provider.url}/v1/chat/completions"
        payload = {
            "model": body.model,
            "messages": [msg.model_dump() for msg in body.messages],
            "stream": body.stream,
            "temperature": body.temperature,
            **({"max_tokens": body.max_tokens} if body.max_tokens else {}),
        }

        store.record_request(provider.name)
        m.requests_total.add(1, {"provider": provider.name, "model": body.model})
        t0 = time.monotonic()

        if body.stream:
            m.active_requests.add(1, {"provider": provider.name})
            return StreamingResponse(
                _stream(target_url, payload, provider.name, provider.timeout_s, req_id, t0),
                media_type="text/event-stream",
                headers={"X-Request-ID": req_id, "X-Provider": provider.name},
            )

        m.active_requests.add(1, {"provider": provider.name})
        try:
            async with httpx.AsyncClient(timeout=provider.timeout_s) as client:
                resp = await client.post(target_url, json=payload)
            elapsed = time.monotonic() - t0

        except httpx.RequestError as exc:
            log.warning(
                "[%s] Провайдер %s: сетевая ошибка (попытка %d): %s",
                req_id, provider.name, attempt + 1, exc,
            )
            await store.record_error(provider.name)
            m.provider_errors_total.add(1, {"provider": provider.name, "reason": "network"})
            m.active_requests.add(-1, {"provider": provider.name})
            continue

        m.active_requests.add(-1, {"provider": provider.name})

        m.response_codes_total.add(
            1, {"provider": provider.name, "status": str(resp.status_code)}
        )

        if resp.status_code >= 500:
            log.warning(
                "[%s] Провайдер %s вернул %d (попытка %d)",
                req_id, provider.name, resp.status_code, attempt + 1,
            )
            await store.record_error(provider.name)
            m.provider_errors_total.add(
                1, {"provider": provider.name, "reason": f"http_{resp.status_code}"}
            )
            continue

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)

        # Успех
        await store.record_ok(provider.name, elapsed)
        m.request_latency.record(elapsed, {"provider": provider.name})
        m.ttft.record(elapsed, {"provider": provider.name})

        data = resp.json()
        usage = data.get("usage", {})
        if usage:
            n_in = usage.get("prompt_tokens", 0)
            n_out = usage.get("completion_tokens", 0)
            m.tokens_in_total.add(n_in, {"provider": provider.name})
            m.tokens_out_total.add(n_out, {"provider": provider.name})
            if n_out > 0:
                m.tpot.record(elapsed / n_out, {"provider": provider.name})
            cost = n_out * provider.price_per_token
            if cost > 0:
                m.request_cost_usd.add(cost, {"provider": provider.name, "model": body.model})

        # --- Secret scan на ответе ---
        response_text = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        secrets_found = detect_secrets(response_text)
        if secrets_found:
            log.warning(
                "[%s] Секреты в ответе провайдера %s: %s",
                req_id, provider.name, secrets_found,
            )
            m.provider_errors_total.add(
                1, {"provider": provider.name, "reason": "secret_leak"}
            )
            # Редактируем ответ
            response_text = "[REDACTED: response contained sensitive data]"
            data["choices"][0]["message"]["content"] = response_text

        # --- Inline evaluation + стоимость запроса ---
        n_in_eval = usage.get("prompt_tokens", 0) if usage else 0
        n_out_eval = usage.get("completion_tokens", 0) if usage else 0
        eval_result = evaluate_response(
            user_text, response_text, elapsed * 1000,
            tokens_in=n_in_eval,
            tokens_out=n_out_eval,
            price_per_token=provider.price_per_token,
        )
        log_to_mlflow(eval_result, provider.name, body.model)

        log.info("[%s] OK via %s in %.3fs", req_id, provider.name, elapsed)
        return JSONResponse(data, headers={"X-Request-ID": req_id, "X-Provider": provider.name})

    raise HTTPException(502, f"Все провайдеры недоступны (попыток: {len(tried)})")


async def _stream(
    url: str,
    payload: dict,
    provider_name: str,
    timeout_s: float,
    req_id: str,
    t0: float,
):
    """
    Пробрасывает SSE-поток от провайдера клиенту.
    Клиент создаётся здесь — он живёт всё время стриминга.
    """
    first = True
    chunk_count = 0
    first_token_at = 0.0

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            async with client.stream("POST", url, json=payload, timeout=60.0) as resp:
                m.response_codes_total.add(
                    1, {"provider": provider_name, "status": str(resp.status_code)}
                )
                if resp.status_code != 200:
                    await store.record_error(provider_name)
                    yield f"data: {json.dumps({'error': f'Provider returned {resp.status_code}'})}\n\n"
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        yield "\n"
                        continue

                    if line.startswith("data: "):
                        token_data = line[6:]

                        if token_data.strip() == "[DONE]":
                            now = time.monotonic()
                            total = now - t0
                            ttft_s = first_token_at - t0 if first_token_at else total
                            if chunk_count > 1:
                                m.tpot.record(
                                    (now - first_token_at) / chunk_count,
                                    {"provider": provider_name},
                                )
                            m.request_latency.record(total, {"provider": provider_name})
                            await store.record_ok(provider_name, total)
                            # MLFlow: логируем streaming-метрики
                            log_to_mlflow(
                                None,  # EvalResult не нужен — передаём raw metrics
                                provider_name,
                                payload.get("model", "unknown"),
                                extra={
                                    "stream_chunks": chunk_count,
                                    "ttft_ms": ttft_s * 1000,
                                    "total_latency_ms": total * 1000,
                                },
                            )
                            yield "data: [DONE]\n\n"
                            break

                        now = time.monotonic()
                        if first:
                            m.ttft.record(now - t0, {"provider": provider_name})
                            first_token_at = now
                            first = False
                        chunk_count += 1

                        yield f"data: {token_data}\n\n"

    except httpx.RequestError as exc:
        log.warning("[%s] Стриминг прерван: %s", req_id, exc)
        await store.record_error(provider_name)
        m.provider_errors_total.add(1, {"provider": provider_name, "reason": "stream_error"})
    finally:
        m.active_requests.add(-1, {"provider": provider_name})

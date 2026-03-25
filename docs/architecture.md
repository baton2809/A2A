# Архитектура LLM Agent Platform

## Обзор системы

```
+---------------------------------------------------------------------+
|                       LLM Agent Platform                            |
|                                                                     |
|  +----------+    JWT     +--------------------------------------+  |
|  |  Client  |----------->|           Gateway :8080              |  |
|  | (curl /  |           |  +------------+  +-----------------+ |  |
|  |  Agent)  |<----------|  |  JWT Guard |  |   Guardrails    | |  |
|  +----------+  Response |  |(middleware)|  | injection+secret| |  |
|                          |  +------------+  +-----------------+ |  |
|  +----------+   A2A      |  +--------------------------------+  |  |
|  | Purple   |----------->|  |        RoutingEngine           |  |  |
|  | Agent    |           |  |   EMA latency + circuit breaker |  |  |
|  | :8020    |           |  +--------+---------------+--------+  |  |
|  +----------+           +-----------+---------------+------------+  |
|       |                             |               |               |
|  +----+------+             +--------+---+  +--------+----+         |
|  |  Agent    |             | mock-fast  |  |  mock-slow  |         |
|  | Registry  |             |  :9001     |  |  :9002      |         |
|  |  :8010    |             +------------+  +-------------+         |
|  +-----+-----+                                                      |
|        |            +------------------------------------------+   |
|  +-----+------+     |             Infrastructure               |   |
|  |   Redis    |     |  OTel Collector:4317 -> Prometheus:9090  |   |
|  |  :6379     |     |  Grafana:3000          MLFlow:5050       |   |
|  +------------+     +------------------------------------------+   |
+---------------------------------------------------------------------+
```

## Поток запроса

```
Client
  |
  v
[JWT Guard middleware]
  -- нет/неверный токен -> 401

[detect_injection(prompt)]
  -- инъекция найдена -> 400 + метрика guardrail/injection

[RoutingEngine.pick(candidates)]
  1. Фильтр по имени модели (или "*")
  2. Исключить провайдеры в cooldown
  3. Новые (latency_ema == 0) идут первыми
  4. Lowest EMA с tolerance +-10%
  5. Fallback: ближайший к выходу из cooldown

[httpx.AsyncClient -> Provider /v1/chat/completions]

  stream=True:
    StreamingResponse (SSE pass-through)
    transfer-encoding: chunked
    Соединение НЕ разрывается между токенами
    TTFT фиксируется по первому чанку
    TPOT = (now - first_token_at) / chunk_count

  stream=False:
    detect_secrets(response) -> редактировать если найдено
    evaluate_response(prompt, response, latency_ms)
    log_to_mlflow(eval_result, provider, model)
    JSONResponse
```

## Поддержка потокового чтения (SSE streaming)

Балансировщик поддерживает SSE без разрыва соединений:

- `httpx.AsyncClient` создаётся внутри генератора `_stream()`, а не снаружи.
  Это критично: `async with client` закрывает клиент при выходе из блока, поэтому
  если создать клиент до `StreamingResponse` — соединение закроется раньше, чем
  FastAPI начнёт читать генератор.
- `client.stream("POST", url, ...)` держит TCP-соединение открытым на всё время генерации.
- `aiter_lines()` читает построчно без буферизации всего ответа в памяти.
- `transfer-encoding: chunked` — клиент получает токены по мере генерации, не ждёт полного ответа.

Проверка:
```bash
curl -D - http://localhost:8080/v1/chat/completions ...
# HTTP/1.1 200 OK
# transfer-encoding: chunked
# x-provider: mock-fast
# content-type: text/event-stream
```

## Компоненты

### Gateway (port 8080)

| Модуль | Файл | Назначение |
|---|---|---|
| JWT auth | `auth/tokens.py`, `auth/guard.py` | HS256, 60 мин TTL |
| Guardrails | `guardrails/scanner.py` | 19 injection + 8 secret паттернов |
| Routing | `routing/engine.py` | EMA + circuit breaker + priority |
| Round-Robin | `routing/round_robin.py` | `itertools.count()` |
| Weighted | `routing/weighted.py` | `random.choices(weights)` |
| Provider store | `providers/store.py` | Redis + in-memory fallback, RPM лимиты |
| Health watcher | `providers/watcher.py` | Фоновый поллинг /healthz |
| Evaluation | `evaluation.py` | Jaccard similarity, структура MD |
| Metrics | `telemetry/metrics.py` | OTel SDK -> Prometheus |

### Circuit Breaker

```
Closed --(>=5 ошибок)--> Open (cooldown)
  ^                           |
  |                    2^(n-5) x 60s (max 600s)
  +---(200 OK <- /healthz)----+
```

Параметры: threshold=5, base=60s, cap=600s, EMA alpha=0.2

### Agent Registry (port 8010)

- CRUD для A2A Agent Card (`name`, `description`, `url`, `skills`, `tags`)
- Поиск по `skill` (имя/описание) и `tag`
- Фоновый health check каждые 30 секунд
- Redis-backed, in-memory fallback

### Purple Agent (port 8020)

- A2A `/tasks/send` (sync) + `/tasks/stream` (SSE)
- JWT cache + автообновление при 401
- Retry с backoff: 0.5s -> 1.0s -> 2.0s (max 3 попытки)
- Redis-backed task storage (TTL 1h)

## Стратегии балансировки — сравнение

| Стратегия | Реализация | Плюсы | Минусы |
|---|---|---|---|
| Round-Robin | `itertools.count() % N` | Простота, равномерность | Игнорирует задержку и здоровье |
| Weighted | `random.choices(weights)` | Управляемое распределение нагрузки | Статичный вес, нет адаптации |
| EMA Latency | `latency_ema` alpha=0.2 | Адаптируется к реальной задержке | Медленная реакция на резкие изменения |
| Priority | поле `priority` | Явный приоритет провайдера | Нужна ручная настройка |
| Health-Aware | Circuit breaker + EMA | Автоотключает сбойные, предпочитает быстрые | Сложнее в отладке |

Используется в продакшне: `RoutingEngine` — комбинирует все пять стратегий.

### Поведение при сбоях

```
Нормальная работа:
  mock-fast (60ms EMA)  -> ~85% запросов
  mock-slow (350ms EMA) -> ~15% запросов

После 5 ошибок mock-fast:
  mock-fast -> cooldown 60s
  mock-slow -> 100% запросов (нет разрыва для клиента)

После восстановления mock-fast:
  EMA сбрасывается -> 0 (новый провайдер имеет приоритет)
  Трафик постепенно возвращается
```

## Телеметрия

| Метрика | Тип | Labels |
|---|---|---|
| `llm_gw_requests_total` | Counter | provider, model |
| `llm_gw_provider_errors_total` | Counter | provider, reason |
| `llm_gw_response_codes_total` | Counter | provider, status |
| `llm_gw_tokens_input_total` | Counter | provider |
| `llm_gw_tokens_output_total` | Counter | provider |
| `llm_gw_request_latency_seconds` | Histogram | provider |
| `llm_gw_ttft_seconds` | Histogram | provider |
| `llm_gw_tpot_seconds` | Histogram | provider |
| `llm_gw_active_requests` | UpDownCounter | provider |
| `llm_gw_process_cpu_percent` | Gauge | — |
| `llm_gw_process_memory_mb` | Gauge | — |

Grafana дашборд: http://localhost:3000 (admin/admin)
Prometheus: http://localhost:9090
MLFlow: http://localhost:5050

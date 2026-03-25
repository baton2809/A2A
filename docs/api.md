# API Documentation

## Gateway (port 8080)

### Authentication

#### `POST /auth/token`
Получить JWT-токен. **Не требует авторизации.**

**Request:**
```json
{"username": "admin", "password": "admin"}
```
**Response:**
```json
{"access_token": "eyJhbGci...", "token_type": "bearer"}
```
**Errors:** `401` — неверные учётные данные.

---

### Chat Completions

#### `POST /v1/chat/completions`
OpenAI-совместимый endpoint. **Требует JWT.**

**Headers:** `Authorization: Bearer <token>`

**Request:**
```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "Explain load balancing"}
  ],
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 500
}
```

**Response (non-streaming):**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "model": "mock-fast-model",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Load balancing is..."},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 8, "completion_tokens": 42, "total_tokens": 50}
}
```
**Response headers:** `X-Request-ID`, `X-Provider`

**Response (streaming):** `Content-Type: text/event-stream`, `Transfer-Encoding: chunked`
```
data: {"id":"chatcmpl-abc","choices":[{"delta":{"content":"Load "},...}]}

data: {"id":"chatcmpl-abc","choices":[{"delta":{"content":"balancing "},...}]}

data: [DONE]
```

**Errors:**
- `400` — prompt injection обнаружен (`detail` содержит паттерн)
- `401` — отсутствует или недействительный токен
- `503` — нет доступных провайдеров
- `502` — все провайдеры недоступны после retry

---

### Provider Management

#### `GET /providers`
Список всех зарегистрированных провайдеров.

**Response:**
```json
{
  "items": [{
    "name": "mock-fast",
    "url": "http://mock-fast:9000",
    "models": ["*"],
    "weight": 1,
    "timeout_s": 30.0,
    "price_per_token": 0.0,
    "request_limit": 0,
    "priority": 0,
    "healthy": true,
    "latency_ema": 0.062,
    "error_streak": 0,
    "cooldown_until": 0.0
  }],
  "total": 2
}
```

#### `POST /providers` → `201`
Зарегистрировать нового провайдера.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | required | Уникальный идентификатор |
| `url` | string | required | Base URL провайдера |
| `models` | list[str] | `["*"]` | Поддерживаемые модели (`"*"` = любая) |
| `weight` | int | `1` | Вес при взвешенной балансировке |
| `timeout_s` | float | `30.0` | Таймаут запроса в секундах |
| `price_per_token` | float | `0.0` | Цена за токен, USD |
| `request_limit` | int | `0` | RPM лимит (0 = безлимитный) |
| `priority` | int | `0` | Приоритет (выше = предпочтительнее) |

#### `GET /providers/{name}`
Получить данные конкретного провайдера.

#### `DELETE /providers/{name}` → `200`
Удалить провайдера.

---

### Health

#### `GET /health`
Статус шлюза. **Не требует авторизации.**

**Response:**
```json
{
  "status": "ok",
  "uptime_s": 1234.5,
  "providers": {"total": 2, "healthy": 2}
}
```

---

## Agent Registry (port 8010)

#### `GET /healthz`
Статус сервиса.

#### `GET /agents`
Список всех агентов.

#### `GET /agents/search?skill=code&tag=reasoning`
Поиск агентов по навыку и тегу.

#### `POST /agents` → `201`
Зарегистрировать агента.

```json
{
  "agent_card": {
    "name": "Purple Agent",
    "description": "Versatile AI agent",
    "url": "http://purple-agent:8000",
    "version": "1.0.0",
    "skills": [{
      "id": "reasoning",
      "name": "General Reasoning",
      "description": "Answer questions and analyze data",
      "tags": ["reasoning", "qa"],
      "examples": ["Explain neural networks"]
    }]
  }
}
```

#### `GET /agents/{name}`
Получить карточку агента.

#### `DELETE /agents/{name}` → `200`
Удалить агента.

---

## Purple Agent (port 8020)

#### `GET /healthz`
Статус агента.

#### `GET /.well-known/agent-card.json`
A2A Agent Card — описание агента, навыки, capabilities.

#### `POST /tasks/send`
Синхронное выполнение задачи.

**Request:**
```json
{
  "id": "task-123",
  "message": {
    "parts": [{"type": "text", "text": "Explain gradient descent"}]
  }
}
```

**Response:**
```json
{
  "id": "task-123",
  "status": {"state": "completed"},
  "artifacts": [{"parts": [{"type": "text", "text": "Gradient descent is..."}]}],
  "history": [
    {"role": "user", "parts": [{"type": "text", "text": "Explain gradient descent"}]},
    {"role": "agent", "parts": [{"type": "text", "text": "Gradient descent is..."}]}
  ]
}
```

#### `POST /tasks/stream`
Потоковое выполнение задачи (SSE).

#### `GET /tasks/{task_id}`
Получить статус и результат задачи.

---

## Общие коды ошибок

| HTTP | Причина |
|---|---|
| `400` | Prompt injection обнаружен guardrail |
| `401` | Отсутствует или истёк JWT токен |
| `404` | Провайдер/агент не найден |
| `502` | Все LLM провайдеры недоступны |
| `503` | Нет зарегистрированных провайдеров |

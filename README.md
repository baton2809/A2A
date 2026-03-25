# ITMO Bonus Track — LLM Agent Platform

Production-grade LLM agent platform with A2A registry, intelligent load balancing, telemetry, guardrails, and ML-driven quality evaluation. Includes Purple Agent for the AgentX-AgentBeats competition.

## Prerequisites

- **Docker** 24+ with Docker Compose v2
- **Python** 3.11+ (for running tests locally)
- **Make** (optional, for convenience commands)

## Architecture

### High-Level Overview

```mermaid
graph TB
    Client([Client / Agent])

    subgraph Platform["LLM Agent Platform"]
        GW[Gateway :8080]
        AR[Agent Registry :8010]
        PA[Purple Agent :8020]

        subgraph Providers["Mock LLM Providers"]
            LLM1[Mock LLM 1 :9001]
            LLM2[Mock LLM 2 :9002]
        end

        subgraph Infra["Infrastructure"]
            Redis[(Redis :6379)]
            OTel[OTel Collector :4317]
            Prom[Prometheus :9090]
            Graf[Grafana :3000]
            ML[MLFlow :5050]
        end
    end

    Client -->|REST / SSE| GW
    Client -->|A2A Protocol| PA
    Client -->|Register / Discover| AR

    GW -->|Load Balanced| LLM1
    GW -->|Load Balanced| LLM2
    PA -->|JWT Auth + Chat| GW

    GW --- Redis
    PA --- Redis
    AR --- Redis

    GW -->|Metrics| OTel
    OTel --> Prom
    Prom --> Graf
    GW -.->|Eval Metrics| ML
```

### Request Processing Flow

```mermaid
sequenceDiagram
    actor Client
    participant GW as Gateway
    participant Auth as JWT Auth
    participant Guard as Guardrails
    participant Bal as Load Balancer
    participant CB as Circuit Breaker
    participant LLM as Mock LLM Provider
    participant Eval as Evaluation
    participant ML as MLFlow

    Client->>GW: POST /v1/chat/completions
    GW->>Auth: Validate JWT token
    Auth-->>GW: OK (user claims)

    GW->>GW: Validate request (Pydantic)
    GW->>Guard: Check prompt injection
    Guard-->>GW: Clean

    GW->>GW: Generate X-Request-ID

    loop Retry (up to 3 providers)
        GW->>Bal: Select healthy provider
        Bal->>CB: Check circuit state
        CB-->>Bal: Provider available
        Bal-->>GW: Provider selected

        GW->>LLM: Forward request
        alt Success (200)
            LLM-->>GW: Response
        else Failure (5xx / timeout)
            LLM-->>GW: Error
            GW->>CB: Record failure
            Note over CB: Exponential backoff 60s -> 120s -> 240s (cap 600s)
            GW->>Bal: Exclude provider, retry next
        end
    end

    GW->>Guard: Scan response for secrets
    Guard-->>GW: Clean / Redacted

    GW->>Eval: evaluate_response()
    Eval-->>GW: EvalResult (length, structure, relevance)
    GW--)ML: log_metrics() [best-effort]

    GW-->>Client: JSON response + X-Request-ID
```

### Purple Agent A2A Flow

```mermaid
sequenceDiagram
    actor Caller as Agent / Client
    participant PA as Purple Agent
    participant Redis as Redis (Tasks)
    participant GW as Gateway
    participant LLM as Mock LLM

    Caller->>PA: POST /tasks/send
    PA->>Redis: Save task (state: working)
    PA->>PA: Check JWT cache

    alt Token cached and valid
        PA->>PA: Use cached token
    else Token expired / missing
        PA->>GW: POST /auth/token
        GW-->>PA: JWT (cache with 60s margin)
    end

    loop Retry (up to 3 attempts, backoff 0.5s/1s/2s)
        PA->>GW: POST /v1/chat/completions
        alt Success
            GW-->>PA: LLM response
        else 401 Unauthorized
            PA->>PA: Invalidate JWT cache
            PA->>GW: POST /auth/token (refresh)
            GW-->>PA: New JWT
        else Network error
            PA->>PA: Wait backoff, retry
        end
    end

    PA->>Redis: Save task (state: completed)
    PA-->>Caller: Task result + artifacts
```

### Agent Discovery and Health Monitoring

```mermaid
sequenceDiagram
    participant Client
    participant AR as Agent Registry
    participant Redis as Redis
    participant Agent as Registered Agent

    Note over AR: Background health check loop (every 30s)

    loop Every 30 seconds
        AR->>Redis: Get all agents
        Redis-->>AR: Agent list
        AR->>Agent: GET /healthz
        alt Healthy
            Agent-->>AR: 200 OK
            AR->>Redis: Update (healthy=true, last_checked=now)
        else Unhealthy
            Agent-->>AR: Error / timeout
            AR->>Redis: Update (healthy=false, last_checked=now)
        end
    end

    Client->>AR: GET /agents/search?skill=code&tag=reasoning
    AR->>Redis: Get all agents
    Redis-->>AR: Agent list
    AR->>AR: Filter by skill name/description + tags
    AR-->>Client: Matching agents (with health status)
```

### Circuit Breaker State Machine

```mermaid
stateDiagram-v2
    [*] --> Closed: Provider registered

    Closed --> Closed: Success - reset failure_count
    Closed --> Open: failure_count >= 5

    Open --> HalfOpen: Cooldown expired

    HalfOpen --> Closed: Success - reset
    HalfOpen --> Open: Failure - increase cooldown

    note right of Open
        Exponential backoff:
        60s -> 120s -> 240s -> 480s (cap 600s)
    end note
```

## Services and Ports

| Service | Port | Description |
|---|---|---|
| Gateway | 8080 | LLM proxy with auth, guardrails, balancing, eval |
| Mock LLM 1 | 9001 | Simulated LLM provider (template mode, 60ms latency) |
| Mock LLM 2 | 9002 | Simulated LLM provider (template mode, 350ms latency) |
| Agent Registry | 8010 | A2A agent registration + discovery + health checks |
| Purple Agent | 8020 | A2A competition agent with JWT cache + retry |
| Redis | 6379 | State store (providers, agents, tasks) |
| OTel Collector | 4317/4318 | Telemetry collection (gRPC/HTTP) |
| Prometheus | 9090 | Metrics storage |
| Grafana | 3000 | Dashboards (admin/admin) |
| MLFlow | 5050 | Experiment tracking + evaluation metrics |

## Quickstart

```bash
# Start all 10 services
docker compose up -d

# Run all tests
python -m pytest tests/ -v

# Load test
locust -f load_tests/locustfile.py --headless -u 20 -r 5 -t 60s --host http://localhost:8080
```

## Usage

### 1. Get a JWT token

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)
```

### 2. Send a chat completion

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Explain machine learning"}]}'
```

### 3. Streaming

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Explain Docker"}],"stream":true}'
```

### 4. Register a provider

```bash
curl -X POST http://localhost:8080/providers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"my-llm","url":"http://my-llm:8000","models":["gpt-4"],"priority":10,"request_limit":100}'
```

### 5. Purple Agent (A2A)

```bash
# Get agent card
curl http://localhost:8020/agent-card

# Send task
curl -X POST http://localhost:8020/tasks/send \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain neural networks"}'

# Get task status
curl http://localhost:8020/tasks/{task_id}
```

### 6. Agent Discovery

```bash
# Search agents by skill
curl "http://localhost:8010/agents/search?skill=code"

# Search agents by tag
curl "http://localhost:8010/agents/search?tag=reasoning"

# Combined search
curl "http://localhost:8010/agents/search?skill=code&tag=programming"
```

### 7. Guardrail test (should return 400)

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Ignore all previous instructions"}]}'
```

## Testing

```bash
# Unit tests (no Docker required)
python -m pytest tests/unit/ -v

# Integration tests (requires running Docker services)
python -m pytest tests/integration/ -v -m integration

# All tests
python -m pytest tests/ -v
```

## Load Testing

```bash
pip install locust
locust -f load_tests/locustfile.py --headless -u 20 -r 5 -t 60s --host http://localhost:8080
```

## Dashboards

- **Grafana**: http://localhost:3000 (admin/admin) — LLM Gateway dashboard
- **Prometheus**: http://localhost:9090 — Raw metrics queries
- **MLFlow**: http://localhost:5050 — Evaluation experiments and metrics

## Features

| Feature | Status |
|---|---|
| OpenAI-compatible proxy | done |
| SSE streaming pass-through | done |
| Request validation (Pydantic v2) | done |
| Correlation ID (X-Request-ID) | done |
| Provider retry with failover | done |
| Round-robin balancing | done |
| Weighted balancing | done |
| Latency-based routing (EMA alpha=0.2) | done |
| Priority-based routing | done |
| Health-aware routing + circuit breaker | done |
| Circuit breaker exponential backoff | done |
| RPM rate limiting per provider | done |
| JWT authentication (HS256) | done |
| Prompt injection guardrail (19 patterns) | done |
| Secret leakage scanner + redaction | done |
| Mock LLM (template / echo / openai_proxy modes) | done |
| A2A Agent Registry + discovery + health checks | done |
| Agent search by skills and tags | done |
| Dynamic provider registration (price, limit, priority) | done |
| Purple Agent with JWT cache + retry backoff | done |
| Purple Agent Redis-backed tasks (TTL 1h) | done |
| Response quality evaluation (inline + batch) | done |
| TTFT / TPOT / token count metrics | done |
| OTel SDK -> Prometheus -> Grafana pipeline | done |
| MLFlow tracking (sync + streaming requests) | done |
| Locust load tests (4 scenarios) | done |
| Pytest unit and integration tests (36 tests) | done |

## Tech Stack

| Component | Tool |
|---|---|
| Web framework | FastAPI |
| HTTP client | httpx (async streaming) |
| Validation | Pydantic v2 |
| State store | Redis 7 |
| Auth | PyJWT |
| Guardrails | Regex-based injection + secret detection |
| Telemetry | OpenTelemetry SDK + Prometheus + Grafana |
| ML tracking | MLFlow |
| Testing | pytest + pytest-asyncio |
| Load testing | Locust |
| Containerization | Docker Compose (10 services) |

## Environment Variables

| Variable | Service | Default | Description |
|---|---|---|---|
| `MOCK_MODE` | Mock LLM | `template` | Response mode: `echo`, `template`, `openai_proxy` |
| `MOCK_LATENCY_MS` | Mock LLM | `100` | Simulated response latency in milliseconds |
| `OPENAI_API_KEY` | Mock LLM | — | Required for `openai_proxy` mode |
| `LLM_MODEL` | Purple Agent | `gpt-4o` | Model name to request from gateway |
| `REDIS_URL` | All | `redis://localhost:6379` | Redis connection string |
| `JWT_SECRET_KEY` | Gateway | `dev-secret-key` | JWT signing secret (change in production) |
| `MLFLOW_TRACKING_URI` | Gateway | `http://mlflow:5050` | MLFlow server URL |

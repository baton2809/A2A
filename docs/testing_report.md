# Отчёт о тестировании

## Unit тесты (18 тестов, без Docker)

```bash
python3 -m pytest tests/unit/ -v
# 18 passed in 0.21s
```

| Модуль | Тесты | Что проверяется |
|---|---|---|
| `test_providers.py` | 7 | Add/list, remove, EMA обновление (alpha=0.2), circuit breaker (threshold=5), cooldown exclusion |
| `test_routing.py` | 11 | Round-Robin цикличность, Weighted выборка, RoutingEngine: fresh provider, lowest EMA, cooldown skip, fallback |

---

## Integration тесты (15 тестов, требует Docker)

```bash
python3 -m pytest tests/integration/ -v -m integration
# 15 passed in 1.20s
```

| Файл | Тесты | Покрытие |
|---|---|---|
| `test_gateway.py` | 7 | Здоровье, JWT (valid/invalid/missing), completion, injection block, балансировка |
| `test_providers.py` | 2 | Список провайдеров, CRUD регистрация |
| `test_purple_agent.py` | 3 | Health, agent-card, tasks/send |
| `test_registry.py` | 3 | Health, list, CRUD агентов |

---

## Нагрузочные тесты (Locust)

### Конфигурация

```bash
locust -f load_tests/locustfile.py --host http://localhost:8080 \
  --headless -u 20 -r 5 --run-time 40s
```

4 сценария в параллельном запуске (по 5 пользователей каждый):

| Класс | Описание |
|---|---|
| `GatewayUser` | Нормальная нагрузка: sync (6x), stream (3x), health (1x), providers (1x) |
| `ProviderFailureUser` | Отказ провайдера: регистрирует сломанный, отправляет запросы (failover) |
| `PeakLoadUser` | Пиковая нагрузка: без паузы между запросами |
| `InjectionAttackUser` | Атаки injection: проверяет что guardrail блокирует |

### Результаты (20 пользователей, 40 секунд)

| Endpoint | Запросов | Ошибок | Avg (ms) | p50 | p95 | req/s |
|---|---|---|---|---|---|---|
| POST /auth/token | 20 | 0% | 134 | 59 | 320 | 0.5 |
| GET /health | 5 | 0% | 44 | 27 | 87 | 0.1 |
| GET /providers | 8 | 0% | 206 | 260 | 340 | 0.2 |
| POST /completions [sync] | 58 | 0% | 516 | 470 | 880 | 1.5 |
| POST /completions [stream] | 22 | ~5% | 171 | 140 | 360 | 0.6 |
| POST /completions [failover] | 78 | **0%** | 538 | 510 | 870 | 2.0 |
| POST /completions [peak] | 415 | 0% | 453 | 440 | 650 | 10.4 |
| POST /completions [injection] | 94 | **0%** | 119 | 100 | 330 | 2.4 |
| **ИТОГО** | **700+** | **~1%** | 363 | 390 | 640 | **~15** |

### Выводы по нагрузочным тестам

**Throughput:** ~15 req/s на локальной машине при 20 пользователях.
Пиковый сценарий (5 пользователей, 0 wait) даёт **10.4 req/s только от одного класса**.

**Латентность:**
- p50 ≈ 440ms — обусловлено задержкой mock-LLM (60–350ms) + HTTP overhead
- p95 ≈ 650ms — приемлемо для LLM endpoint
- p99 < 1000ms — нет аномально долгих запросов

**Устойчивость при отказе провайдера:**
- Сценарий `ProviderFailureUser` регистрирует недоступный `localhost:19999`
- 78 запросов → **0 ошибок** — gateway автоматически перенаправлял на здоровые mock-fast/mock-slow
- Circuit breaker открывается после 5 ошибок и направляет трафик дальше

**Guardrails под нагрузкой:**
- 94 injection-атаки → **0 пропущено** (после расширения паттернов)
- Среднее время блокировки: 119ms (меньше обычного запроса — reject fast-path)

**Streaming надёжность:**
- ~5% ошибок в streaming связано с race-condition при `0 chunks` (таймаут соединения при быстром завершении потока)
- Реальных разрывов соединений нет — `transfer-encoding: chunked` корректен

---

## Сравнение стратегий балансировки

Измерено в реальных условиях (mock-fast=60ms, mock-slow=350ms):

| Стратегия | Распределение трафика | p50 latency | Поведение при отказе |
|---|---|---|---|
| Round-Robin | 50% / 50% | 205ms | Продолжает слать на упавший |
| Weighted (1:1) | 50% / 50% | 205ms | Продолжает слать на упавший |
| EMA Latency | ~85% fast / ~15% slow | 89ms | Плавно уходит от медленного |
| **Health-Aware (используется)** | **~85% fast / ~15% slow** | **89ms** | **Полный failover, circuit breaker** |

**Вывод:** Health-Aware стратегия даёт на **56% меньшую p50 латентность** (89ms vs 205ms)
по сравнению с Round-Robin при двух провайдерах с разной скоростью.

---

## Запуск нагрузочных тестов

```bash
# Установка
pip install locust

# Интерактивный UI (http://localhost:8089)
locust -f load_tests/locustfile.py --host http://localhost:8080

# Headless — все сценарии:
locust -f load_tests/locustfile.py --host http://localhost:8080 \
  --headless -u 20 -r 5 --run-time 60s --csv load_tests/results/run1

# Только пиковая нагрузка:
locust -f load_tests/locustfile.py --host http://localhost:8080 \
  --headless -u 50 -r 50 --run-time 30s \
  --class-picker   # в UI выбрать PeakLoadUser

# Только тест отказа:
locust -f load_tests/locustfile.py --host http://localhost:8080 \
  --headless -u 10 -r 2 --run-time 60s \
  --class-picker   # выбрать ProviderFailureUser
```

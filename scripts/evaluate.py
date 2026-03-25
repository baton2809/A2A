#!/usr/bin/env python3
"""Скрипт пакетной оценки для LLM-шлюза.

Использование:
    python scripts/evaluate.py [--gateway-url URL] [--prompts-file FILE]

Отправляет тестовые промпты в шлюз, оценивает качество ответов
и записывает агрегированные метрики в MLFlow.
"""
import argparse
import json
import os
import sys
import time

import httpx

# Используем модуль оценки шлюза
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gateway.app.evaluation import evaluate_response

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")

DEFAULT_PROMPTS = [
    "Explain machine learning",
    "Write code for sorting a list",
    "Compare Python and JavaScript",
    "Summarize microservices architecture",
    "How do neural networks work",
    "List best practices for API design",
    "What is containerization",
]


def get_token(base_url: str, username: str = "admin", password: str = "admin") -> str:
    resp = httpx.post(f"{base_url}/auth/token", json={"username": username, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


def send_prompt(base_url: str, token: str, prompt: str) -> tuple[str, float]:
    """Отправляет промпт и возвращает (текст_ответа, задержка_мс)."""
    t0 = time.time()
    resp = httpx.post(
        f"{base_url}/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    latency_ms = (time.time() - t0) * 1000
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return content, latency_ms


def main():
    parser = argparse.ArgumentParser(description="Batch evaluate LLM responses")
    parser.add_argument("--gateway-url", default=GATEWAY_URL)
    parser.add_argument("--prompts-file", help="JSON file with list of prompt strings")
    args = parser.parse_args()

    prompts = DEFAULT_PROMPTS
    if args.prompts_file:
        with open(args.prompts_file) as f:
            prompts = json.load(f)

    print(f"Оцениваем {len(prompts)} промптов -> {args.gateway_url}")
    print("=" * 60)

    token = get_token(args.gateway_url)
    results = []

    for i, prompt in enumerate(prompts, 1):
        try:
            response, latency_ms = send_prompt(args.gateway_url, token, prompt)
            ev = evaluate_response(prompt, response, latency_ms)
            results.append(ev)

            print(f"\n[{i}/{len(prompts)}] {prompt[:55]}...")
            print(f"  Длина       : {ev.response_length} симв.")
            print(f"  Структура   : {ev.has_structure}")
            print(f"  Релевантность: {ev.relevance_score:.3f}")
            print(f"  Задержка    : {ev.latency_ms:.0f} мс")
        except Exception as exc:
            print(f"\n[{i}/{len(prompts)}] ОШИБКА: {exc}")

    if not results:
        print("\nУспешных оценок нет.")
        return

    avg_len = sum(r.response_length for r in results) / len(results)
    avg_lat = sum(r.latency_ms for r in results) / len(results)
    avg_rel = sum(r.relevance_score for r in results) / len(results)
    struct_rate = sum(1 for r in results if r.has_structure) / len(results)

    print("\n" + "=" * 60)
    print("ИТОГОВЫЕ РЕЗУЛЬТАТЫ")
    print(f"  Оценено        : {len(results)}/{len(prompts)}")
    print(f"  Средняя длина  : {avg_len:.0f} симв.")
    print(f"  Средняя задержка: {avg_lat:.0f} мс")
    print(f"  Средняя релев. : {avg_rel:.3f}")
    print(f"  Доля структур. : {struct_rate:.1%}")

    # Логирование в MLFlow
    try:
        import mlflow

        mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5050")
        mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment("llm-platform-eval")

        with mlflow.start_run(run_name="batch-eval"):
            mlflow.log_metrics({
                "avg_response_length": avg_len,
                "avg_latency_ms": avg_lat,
                "avg_relevance_score": avg_rel,
                "structure_rate": struct_rate,
                "num_prompts": float(len(results)),
            })
        print(f"\nМетрики записаны в MLFlow: {mlflow_uri}")
    except Exception as exc:
        print(f"\nЗапись в MLFlow пропущена (некритично): {exc}")


if __name__ == "__main__":
    main()

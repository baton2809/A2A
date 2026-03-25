#!/usr/bin/env python3
"""Batch evaluation script for LLM Gateway.

Usage:
    python scripts/evaluate.py [--gateway-url URL] [--prompts-file FILE]

Sends test prompts to the gateway, evaluates responses quality,
and logs aggregate metrics to MLFlow.
"""
import argparse
import json
import os
import sys
import time

import httpx

# Use our gateway's evaluation module
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
    """Send prompt and return (response_text, latency_ms)."""
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

    print(f"Evaluating {len(prompts)} prompts → {args.gateway_url}")
    print("=" * 60)

    token = get_token(args.gateway_url)
    results = []

    for i, prompt in enumerate(prompts, 1):
        try:
            response, latency_ms = send_prompt(args.gateway_url, token, prompt)
            ev = evaluate_response(prompt, response, latency_ms)
            results.append(ev)

            print(f"\n[{i}/{len(prompts)}] {prompt[:55]}...")
            print(f"  Length    : {ev.response_length} chars")
            print(f"  Structured: {ev.has_structure}")
            print(f"  Relevance : {ev.relevance_score:.3f}")
            print(f"  Latency   : {ev.latency_ms:.0f} ms")
        except Exception as exc:
            print(f"\n[{i}/{len(prompts)}] FAILED: {exc}")

    if not results:
        print("\nNo successful evaluations.")
        return

    avg_len = sum(r.response_length for r in results) / len(results)
    avg_lat = sum(r.latency_ms for r in results) / len(results)
    avg_rel = sum(r.relevance_score for r in results) / len(results)
    struct_rate = sum(1 for r in results if r.has_structure) / len(results)

    print("\n" + "=" * 60)
    print("AGGREGATE RESULTS")
    print(f"  Evaluated      : {len(results)}/{len(prompts)}")
    print(f"  Avg length     : {avg_len:.0f} chars")
    print(f"  Avg latency    : {avg_lat:.0f} ms")
    print(f"  Avg relevance  : {avg_rel:.3f}")
    print(f"  Structure rate : {struct_rate:.1%}")

    # Log to MLFlow
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
        print(f"\nMetrics logged to MLFlow at {mlflow_uri}")
    except Exception as exc:
        print(f"\nMLFlow logging skipped (non-critical): {exc}")


if __name__ == "__main__":
    main()

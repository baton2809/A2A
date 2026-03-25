"""Inline response quality evaluation.

Scores every LLM response on four dimensions and (optionally) ships
the metrics to MLFlow for experiment tracking.
"""
import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class EvalResult:
    response_length: int       # character count
    has_structure: bool        # markdown headers / lists / code blocks present
    latency_ms: float          # end-to-end request latency
    relevance_score: float     # Jaccard similarity between prompt and response
    tokens_in: int = 0         # prompt tokens
    tokens_out: int = 0        # completion tokens
    request_cost_usd: float = 0.0  # tokens_out * price_per_token


def evaluate_response(
    prompt: str,
    response: str,
    latency_ms: float,
    tokens_in: int = 0,
    tokens_out: int = 0,
    price_per_token: float = 0.0,
) -> EvalResult:
    return EvalResult(
        response_length=len(response),
        has_structure=_has_markdown(response),
        latency_ms=latency_ms,
        relevance_score=_jaccard(prompt, response),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        request_cost_usd=tokens_out * price_per_token,
    )


def _has_markdown(text: str) -> bool:
    markers = [r"^#{1,6}\s", r"^[-*]\s", r"^\d+\.\s", r"```"]
    return any(re.search(p, text, re.MULTILINE) for p in markers)


def _jaccard(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def log_to_mlflow(
    eval_result: EvalResult | None,
    provider: str,
    model: str,
    extra: dict | None = None,
) -> None:
    """Best-effort MLFlow logging — never raises.

    eval_result=None допустимо для streaming-запросов,
    когда качество ответа не оценивается — тогда передаётся extra dict с raw-метриками.
    """
    try:
        import os
        import mlflow

        uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5050")
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("llm-gateway-inline")

        with mlflow.start_run(run_name=f"{provider}/{model}", nested=True):
            if eval_result is not None:
                metrics = {
                    "response_length": eval_result.response_length,
                    "has_structure": int(eval_result.has_structure),
                    "latency_ms": eval_result.latency_ms,
                    "relevance_score": eval_result.relevance_score,
                    "tokens_in": eval_result.tokens_in,
                    "tokens_out": eval_result.tokens_out,
                    "request_cost_usd": eval_result.request_cost_usd,
                }
            else:
                metrics = extra or {}
            mlflow.log_metrics(metrics)
            mlflow.log_params({"provider": provider, "model": model})
    except Exception as exc:
        log.debug("MLFlow logging skipped: %s", exc)

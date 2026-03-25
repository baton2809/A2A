"""
OpenTelemetry метрики для LLM Gateway.

ВАЖНО: все инструменты создаются внутри init_telemetry() уже ПОСЛЕ того,
как MeterProvider установлен — иначе get_meter() вернёт no-op провайдер
и данные не попадут в Prometheus.
"""

import logging
from typing import TYPE_CHECKING

import psutil
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

if TYPE_CHECKING:
    pass

from ..config import cfg

log = logging.getLogger(__name__)

_proc = psutil.Process()


def _observe_cpu(_opts):
    yield metrics.Observation(_proc.cpu_percent(interval=None))


def _observe_mem(_opts):
    # RSS в МБ
    yield metrics.Observation(_proc.memory_info().rss / 1024 / 1024)


# Переменные будут заполнены в init_telemetry()
requests_total: metrics.Counter
provider_errors_total: metrics.Counter
response_codes_total: metrics.Counter
tokens_in_total: metrics.Counter
tokens_out_total: metrics.Counter
request_latency: metrics.Histogram
ttft: metrics.Histogram
tpot: metrics.Histogram
active_requests: metrics.UpDownCounter
request_cost_usd: metrics.Counter


def init_telemetry() -> None:
    """
    Настраивает OTel MeterProvider и создаёт все инструменты.
    Должна вызываться один раз при старте приложения — до обработки первого запроса.
    """
    global requests_total, provider_errors_total, response_codes_total
    global tokens_in_total, tokens_out_total
    global request_latency, ttft, tpot, active_requests, request_cost_usd

    resource = Resource.create({"service.name": "llm-gateway", "service.version": "1.0"})

    try:
        exporter = OTLPMetricExporter(endpoint=cfg.otel_endpoint, insecure=True)
        reader = PeriodicExportingMetricReader(exporter, export_interval_millis=10_000)
        provider = MeterProvider(resource=resource, metric_readers=[reader])
        log.info("OTel: экспорт метрик -> %s", cfg.otel_endpoint)
    except Exception as exc:
        log.warning("OTel collector недоступен (%s), метрики без экспорта", exc)
        provider = MeterProvider(resource=resource)

    # Устанавливаем провайдер ДО создания метров и инструментов
    metrics.set_meter_provider(provider)
    _meter = metrics.get_meter("llm-gateway", version="1.0")

    # --- Counters ---
    requests_total = _meter.create_counter(
        "gw_requests_total",
        description="Количество запросов к gateway",
    )
    provider_errors_total = _meter.create_counter(
        "gw_provider_errors_total",
        description="Ошибки при обращении к провайдерам",
    )
    response_codes_total = _meter.create_counter(
        "gw_response_codes_total",
        description="HTTP-коды ответов от провайдеров",
    )
    tokens_in_total = _meter.create_counter(
        "gw_tokens_input_total",
        description="Входящие токены (суммарно)",
    )
    tokens_out_total = _meter.create_counter(
        "gw_tokens_output_total",
        description="Исходящие токены (суммарно)",
    )

    # --- Histograms ---
    request_latency = _meter.create_histogram(
        "gw_request_latency_seconds",
        description="Полная задержка запроса (секунды)",
        unit="s",
    )
    ttft = _meter.create_histogram(
        "gw_ttft_seconds",
        description="Время до первого токена (секунды)",
        unit="s",
    )
    tpot = _meter.create_histogram(
        "gw_tpot_seconds",
        description="Время на один выходной токен (секунды)",
        unit="s",
    )

    # --- UpDownCounter ---
    active_requests = _meter.create_up_down_counter(
        "gw_active_requests",
        description="Активные запросы прямо сейчас",
    )

    # --- Стоимость запросов ---
    request_cost_usd = _meter.create_counter(
        "gw_request_cost_usd_total",
        description="Суммарная стоимость запросов (USD)",
        unit="USD",
    )

    # --- Observable gauges ---
    _meter.create_observable_gauge(
        "gw_process_cpu_percent",
        callbacks=[_observe_cpu],
        description="CPU процесса gateway (%)",
    )
    _meter.create_observable_gauge(
        "gw_process_memory_mb",
        callbacks=[_observe_mem],
        description="Память процесса gateway (МБ)",
    )

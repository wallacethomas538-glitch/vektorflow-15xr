"""VektorFlow AI observability.

OpenTelemetry is the neutral telemetry boundary. When configured, the same
application spans can be exported to Langfuse and/or Arize Phoenix.

Configuration:
  LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL
  PHOENIX_COLLECTOR_ENDPOINT / PHOENIX_API_KEY / PHOENIX_PROJECT_NAME
  VF_OTEL_SERVICE_NAME
  VF_OTEL_SAMPLE_RATIO (default 1.0)

No observability provider is required for the core application to run.
"""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

_INITIALIZED = False
_TRACER = None


def _langfuse_exporter() -> Optional[OTLPSpanExporter]:
    public = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    if not public or not secret:
        return None
    base = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/")
    auth = base64.b64encode(f"{public}:{secret}".encode()).decode()
    return OTLPSpanExporter(
        endpoint=f"{base}/api/public/otel/v1/traces",
        headers={
            "Authorization": f"Basic {auth}",
            "x-langfuse-ingestion-version": "4",
        },
    )


def _phoenix_exporter() -> Optional[OTLPSpanExporter]:
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "").strip().rstrip("/")
    if not endpoint:
        return None
    if not endpoint.endswith("/v1/traces"):
        endpoint = f"{endpoint}/v1/traces"
    headers: Dict[str, str] = {}
    api_key = os.getenv("PHOENIX_API_KEY", "").strip()
    if api_key:
        headers["api_key"] = api_key
    return OTLPSpanExporter(endpoint=endpoint, headers=headers)


def initialize_observability() -> Dict[str, Any]:
    global _INITIALIZED, _TRACER
    if _INITIALIZED:
        return observability_status()

    exporters = []
    providers = []
    if _langfuse_exporter() is not None:
        providers.append("langfuse")
    if _phoenix_exporter() is not None:
        providers.append("phoenix")

    resource = Resource.create({
        "service.name": os.getenv("VF_OTEL_SERVICE_NAME", "vektorflow-15xr"),
        "service.version": os.getenv("VEKTORFLOW_VERSION", "1.1"),
        "deployment.environment": os.getenv("RENDER_ENV", os.getenv("ENVIRONMENT", "unknown")),
    })
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(float(os.getenv("VF_OTEL_SAMPLE_RATIO", "1.0")))),
    )

    langfuse = _langfuse_exporter()
    phoenix = _phoenix_exporter()
    if langfuse:
        provider.add_span_processor(BatchSpanProcessor(langfuse))
        exporters.append("langfuse")
    if phoenix:
        provider.add_span_processor(BatchSpanProcessor(phoenix))
        exporters.append("phoenix")

    if exporters:
        trace.set_tracer_provider(provider)
        _TRACER = trace.get_tracer("vektorflow")
    else:
        _TRACER = trace.get_tracer("vektorflow")

    _INITIALIZED = True
    return observability_status()


def tracer():
    initialize_observability()
    return _TRACER or trace.get_tracer("vektorflow")


def start_span(name: str, attributes: Optional[Dict[str, Any]] = None):
    span = tracer().start_as_current_span(name)
    return _SpanContext(span, attributes or {})


class _SpanContext:
    def __init__(self, context, attributes):
        self._context = context
        self._attributes = attributes

    def __enter__(self):
        self._span = self._context.__enter__()
        for key, value in self._attributes.items():
            if value is not None:
                try:
                    self._span.set_attribute(key, str(value))
                except Exception:
                    pass
        return self._span

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_value is not None:
            try:
                self._span.record_exception(exc_value)
                self._span.set_status(__import__("opentelemetry").trace.Status(
                    __import__("opentelemetry").trace.StatusCode.ERROR,
                    str(exc_value),
                ))
            except Exception:
                pass
        return self._context.__exit__(exc_type, exc_value, traceback)


def observability_status() -> Dict[str, Any]:
    return {
        "status": "configured" if (
            os.getenv("LANGFUSE_SECRET_KEY") and os.getenv("LANGFUSE_PUBLIC_KEY")
        ) or os.getenv("PHOENIX_COLLECTOR_ENDPOINT") else "disabled",
        "langfuse": bool(os.getenv("LANGFUSE_SECRET_KEY") and os.getenv("LANGFUSE_PUBLIC_KEY")),
        "phoenix": bool(os.getenv("PHOENIX_COLLECTOR_ENDPOINT")),
        "service_name": os.getenv("VF_OTEL_SERVICE_NAME", "vektorflow-15xr"),
        "sample_ratio": os.getenv("VF_OTEL_SAMPLE_RATIO", "1.0"),
    }


initialize_observability()

"""
@file backend/app/core/telemetry.py
@description OpenTelemetry tracing, Prometheus metrics and structured logging.
"""

import atexit
import json
import logging
import sys
from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from prometheus_client import make_asgi_app


_telemetry_provider: Optional[TracerProvider] = None
_atexit_registered = False


class JSONLogFormatter(logging.Formatter):
    """
    Structured JSON formatter with OpenTelemetry trace IDs.
    """

    def format(self, record):
        span = trace.get_current_span()
        trace_id = span.get_span_context().trace_id

        trace_id_str = (
            format(trace_id, "032x")
            if trace_id
            else "N/A"
        )

        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id_str,
            "module": record.module,
            "line": record.lineno,
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(
                record.exc_info
            )

        return json.dumps(log_obj)


def shutdown_telemetry():
    """
    Flush and stop OpenTelemetry background exporters.
    """
    global _telemetry_provider

    provider = _telemetry_provider

    if provider is None:
        return

    _telemetry_provider = None

    try:
        provider.shutdown()
    except Exception:
        # Shutdown must never break application/test teardown.
        pass


def setup_telemetry(app: FastAPI):
    """
    Initialize OpenTelemetry, Prometheus metrics and structured logging.
    """
    global _telemetry_provider
    global _atexit_registered

    # Avoid installing multiple providers if the module is imported repeatedly.
    if _telemetry_provider is not None:
        return

    provider = TracerProvider()

    # Use the original stderr stream instead of pytest's temporary capture
    # stream. This prevents the BatchSpanProcessor from writing to a closed
    # capture file after the test session finishes.
    output_stream = sys.__stderr__ or sys.stderr

    exporter = ConsoleSpanExporter(
        out=output_stream
    )

    processor = BatchSpanProcessor(
        exporter
    )

    provider.add_span_processor(
        processor
    )

    trace.set_tracer_provider(
        provider
    )

    _telemetry_provider = provider

    if not _atexit_registered:
        atexit.register(
            shutdown_telemetry
        )
        _atexit_registered = True

    metrics_app = make_asgi_app()

    app.mount(
        "/metrics",
        metrics_app,
    )

    FastAPIInstrumentor.instrument_app(
        app
    )

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        JSONLogFormatter()
    )

    logger.addHandler(
        console_handler
    )

    logger.info(
        "Telemetry and Observability Plane initialized successfully"
    )


def instrument_sqlalchemy(engine):
    """
    Instrument SQLAlchemy with OpenTelemetry.
    """
    from opentelemetry.instrumentation.sqlalchemy import (
        SQLAlchemyInstrumentor,
    )

    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        enable_commenter=True,
        commenter_options={},
    )


def instrument_celery():
    """
    Instrument Celery workers with OpenTelemetry.
    """
    from opentelemetry.instrumentation.celery import (
        CeleryInstrumentor,
    )

    CeleryInstrumentor().instrument()
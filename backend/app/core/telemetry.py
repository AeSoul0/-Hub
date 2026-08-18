"""
@file backend/app/core/telemetry.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import json
import logging
from datetime import datetime

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import make_asgi_app


class JSONLogFormatter(logging.Formatter):
    """
    Phase 4: Semantic Logging.
    Formats logs as structured JSON with Trace IDs for centralized observability.
    """
    def format(self, record):
        span = trace.get_current_span()
        trace_id = span.get_span_context().trace_id
        trace_id_str = format(trace_id, "032x") if trace_id else "N/A"
        
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id_str,
            "module": record.module,
            "line": record.lineno
        }
        
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_obj)

def setup_telemetry(app: FastAPI):
    """
    Phase 4: OpenTelemetry & Metric Exporters.
    Configures Tracing, Metrics, and Prometheus exporters.
    """
    # 1. Tracing
    provider = TracerProvider()
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    
    # 2. Metrics (Prometheus Export)
    # We mount the prometheus client ASGI app at /metrics
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
    
    # 3. Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    # 4. Configure Structured JSON Logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(JSONLogFormatter())
    logger.addHandler(console_handler)
    
    logger.info("Telemetry and Observability Plane initialized successfully")

def instrument_sqlalchemy(engine):
    """Instruments SQLAlchemy engine with OpenTelemetry"""
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        enable_commenter=True,
        commenter_options={}
    )

def instrument_celery():
    """Instruments Celery workers with OpenTelemetry"""
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    CeleryInstrumentor().instrument()

"""
@file backend/app/core/celery_app.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import os

from celery import Celery
from kombu import Queue
from functools import wraps

from app.core.config import settings
from app.core.telemetry import instrument_celery

# Phase 6: Instrument Celery Tracing
instrument_celery()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Phase 13: Specialized Worker Pools (Distributed Scale)
celery_app = Celery(
    "aehub_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.task_queues = (
    Queue('default', routing_key='task.#'),
    Queue('browser_pool', routing_key='browser.#'),
    Queue('cpu_pool', routing_key='cpu.#'),
    Queue('llm_pool', routing_key='llm.#')
)

celery_app.conf.task_routes = {
    'vision.index_folder': {'queue': 'cpu_pool', 'routing_key': 'cpu.vision'},
    'browser.extract': {'queue': 'browser_pool', 'routing_key': 'browser.extract'},
    'workflow.execute_step': {'queue': 'default', 'routing_key': 'task.workflow'}
}

# Reliability Gate: Dead Letter Queue (DLQ) for unrecoverable tasks
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.task_acks_late = True

def route_to_dlq(task, exc, task_id, args, kwargs, einfo):
    """Fallback handler that sends failed tasks to DLQ for manual inspection."""
    import logging
    logging.getLogger("celery.dlq").error(f"Task {task_id} failed and routed to DLQ. Error: {exc}")
    # In a real system, we persist this to the DB.
    
celery_app.conf.task_annotations = {'*': {'on_failure': route_to_dlq}}

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    imports=["app.api.academic"]
)

import functools
from app.core.db import SessionLocal
from app.domain.models.identity import Session as SessionModel
from app.domain.models.audit import AuditLog

def secure_task(name: str):
    """
    Decorator for Celery tasks ensuring they run under a strictly verified Identity Context.
    Emits an Audit Log for background execution.
    """
    def decorator(func):
        @celery_app.task(name=name, bind=True)
        @functools.wraps(func)
        def wrapper(self, session_id: str, *args, **kwargs):
            with SessionLocal() as db:
                session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
                if not session:
                    audit_record = AuditLog(
                        session_id=session_id,
                        principal_id="UNKNOWN",
                        tool_name=f"celery:{name}",
                        success=False,
                        error="Unauthorized: Session not found or expired for background task."
                    )
                    db.add(audit_record)
                    db.commit()
                    raise ValueError("Unauthorized async task execution.")
                
                principal_id = session.user_id
                
                try:
                    result = func(session_id, *args, **kwargs)
                    audit_record = AuditLog(
                        session_id=session_id,
                        principal_id=principal_id,
                        tool_name=f"celery:{name}",
                        success=True,
                        error=None
                    )
                    db.add(audit_record)
                    db.commit()
                    return result
                except Exception as e:
                    audit_record = AuditLog(
                        session_id=session_id,
                        principal_id=principal_id,
                        tool_name=f"celery:{name}",
                        success=False,
                        error=str(e)
                    )
                    db.add(audit_record)
                    db.commit()
                    raise e
        return wrapper
    return decorator

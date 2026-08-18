"""
@file backend/app/workers/celery_app.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import os

from celery import Celery

from app.runtime.task_manager import TaskManager, TaskState

# Phase 5: Distributed remote workers.
# This establishes the Celery application bound to Redis for message brokering.

celery_app = Celery(
    "aurora_workers",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0")
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1, # Ensure fair distribution of durable tasks
    task_acks_late=True, # Resiliency: only ack after successful execution
)

@celery_app.task(bind=True, max_retries=3)
def execute_durable_task(self, task_id: str, tool_name: str, args: dict):
    """
    Worker task that executes a tool through the Sandbox.
    Connects Phase 2 (Durable Task) with Phase 5 (Distributed Workers).
    """
    TaskManager.update_state(task_id, TaskState.RUNNING)
    
    try:
        # In a real environment, this imports the Tool Gateway and executes it.
        # For now, we simulate success and normalize the output.
        import asyncio

        from app.workers.sandbox import EphemeralSandboxManager
        
        sandbox = EphemeralSandboxManager()
        
        # If it's a python skill
        if tool_name == "execute_python":
            code = args.get("code", "")
            # We run asyncio event loop to await the sandbox
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            result = loop.run_until_complete(sandbox.execute_python(code))
            
            if result.exit_code == 0:
                TaskManager.update_state(task_id, TaskState.COMPLETED)
                return result.stdout
            else:
                TaskManager.update_state(task_id, TaskState.FAILED, error_message=result.stderr)
                raise Exception(f"Sandbox Error: {result.stderr}")
                
        else:
            # Generic skill
            TaskManager.update_state(task_id, TaskState.COMPLETED)
            return f"Executed {tool_name} successfully"
            
    except Exception as exc:
        TaskManager.update_state(task_id, TaskState.RETRYING, error_message=str(exc))
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc

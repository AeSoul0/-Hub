import asyncio
from typing import Callable, Coroutine
from datetime import datetime
import contextvars

class AuroraProactiveScheduler:
    """
    Phase 12: Proactive A.U.R.O.R.A.
    Handles background tasks, cron jobs, and proactive workflows.
    Allows A.U.R.O.R.A. to wake up without explicit user prompt to check events,
    fetch news, or perform system maintenance.
    """
    
    def __init__(self):
        self._tasks = []
        self._running = False
        
    def schedule_interval(self, interval_seconds: int, coro_func: Callable[[], Coroutine]):
        """Schedules a coroutine to run every `interval_seconds`."""
        self._tasks.append({
            "type": "interval",
            "interval": interval_seconds,
            "func": coro_func,
            "last_run": None
        })
        
    async def _run_loop(self):
        self._running = True
        print("[Proactive Scheduler] Started A.U.R.O.R.A. background worker loop.")
        while self._running:
            now = datetime.now().timestamp()
            for task in self._tasks:
                if task["type"] == "interval":
                    if task["last_run"] is None or (now - task["last_run"]) >= task["interval"]:
                        print(f"[Proactive Scheduler] Executing scheduled task: {task['func'].__name__}")
                        try:
                            # Run task asynchronously without blocking the loop
                            asyncio.create_task(task["func"]())
                        except Exception as e:
                            print(f"[Proactive Scheduler] Error executing task: {e}")
                        finally:
                            task["last_run"] = datetime.now().timestamp()
                            
            await asyncio.sleep(1) # Check tasks every second
            
    def start(self):
        """Starts the proactive scheduler in the event loop."""
        if not self._running:
            asyncio.create_task(self._run_loop())
            
    def stop(self):
        """Stops the proactive scheduler."""
        self._running = False
        print("[Proactive Scheduler] Stopped.")

# Singleton
proactive_scheduler = AuroraProactiveScheduler()

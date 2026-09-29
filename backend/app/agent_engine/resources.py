"""
@file backend/app/agent_engine/resources.py
@description Optimization & Resource Management Layer (Phase 13).

Dynamically classifies tasks (Light, Standard, Vision, etc.) and allocates
memory budgets, concurrency limits, and worker timeouts. Prevents system exhaustion
by queueing or rejecting tasks that exceed hardware limits.
"""

import psutil
from enum import Enum
from typing import Dict, Any, Optional

class TaskClass(str, Enum):
    LIGHT = "light"
    STANDARD = "standard"
    BROWSER = "browser"
    AUDIO = "audio"
    VISION = "vision"
    HEAVY = "heavy"

class ResourceProfile:
    def __init__(self, task_class: TaskClass, max_ram_mb: int, max_runtime: int, max_parallel: int):
        self.task_class = task_class
        self.max_ram_mb = max_ram_mb
        self.max_runtime = max_runtime
        self.max_parallel = max_parallel

PROFILES = {
    TaskClass.LIGHT: ResourceProfile(TaskClass.LIGHT, max_ram_mb=512, max_runtime=60, max_parallel=8),
    TaskClass.STANDARD: ResourceProfile(TaskClass.STANDARD, max_ram_mb=2048, max_runtime=300, max_parallel=4),
    TaskClass.BROWSER: ResourceProfile(TaskClass.BROWSER, max_ram_mb=4096, max_runtime=600, max_parallel=2),
    TaskClass.VISION: ResourceProfile(TaskClass.VISION, max_ram_mb=8192, max_runtime=900, max_parallel=1),
    TaskClass.HEAVY: ResourceProfile(TaskClass.HEAVY, max_ram_mb=16384, max_runtime=3600, max_parallel=1)
}

class ResourceManager:
    """
    Phase 13 Memory Budget Manager.
    """
    
    @classmethod
    def classify_task(cls, task_description: str) -> TaskClass:
        text = task_description.lower()
        if any(kw in text for kw in ["video", "render", "heavy"]):
            return TaskClass.HEAVY
        if any(kw in text for kw in ["image", "picture", "ocr", "vision"]):
            return TaskClass.VISION
        if any(kw in text for kw in ["scrape", "browser", "navigate"]):
            return TaskClass.BROWSER
        if any(kw in text for kw in ["email", "calendar", "ping"]):
            return TaskClass.LIGHT
        return TaskClass.STANDARD

    @classmethod
    def check_availability(cls, profile: ResourceProfile) -> bool:
        # Check available RAM using psutil
        mem = psutil.virtual_memory()
        available_mb = mem.available / (1024 * 1024)
        
        # If available RAM is less than required, return False (would trigger Queueing)
        if available_mb < profile.max_ram_mb:
            return False
        return True
        
    @classmethod
    def allocate(cls, task_description: str) -> Optional[ResourceProfile]:
        task_class = cls.classify_task(task_description)
        profile = PROFILES.get(task_class, PROFILES[TaskClass.STANDARD])
        
        if not cls.check_availability(profile):
            raise ResourceWarning(f"Insufficient resources for {task_class}. Requires {profile.max_ram_mb}MB RAM.")
            
        return profile

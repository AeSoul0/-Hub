"""
@file backend/app/agent_engine/resources.py
@description Implements resources.py. Core components: TaskClass, ResourceProfile, ResourceManager.

This module manages the internal business logic for TaskClass, ResourceProfile, ResourceManager.
It provides specialized functionality to handle: classify_task, check_availability, allocate.
"""
import psutil
from enum import Enum
from typing import Dict, Any, Optional

class TaskClass(str, Enum):
    """
    Represents the TaskClass entity and its core operations.
    """
    LIGHT = "light"
    STANDARD = "standard"
    BROWSER = "browser"
    AUDIO = "audio"
    VISION = "vision"
    HEAVY = "heavy"

class ResourceProfile:
    """
    Represents the ResourceProfile entity and its core operations.
    """
    def __init__(self, task_class: TaskClass, max_ram_mb: int, max_runtime: int, max_parallel: int):
        """
        Executes __init__ logic.
        """
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
    Represents the ResourceManager entity and its core operations.
    """
    """
    Phase 13 Memory Budget Manager.
    """
    
    @classmethod
    def classify_task(cls, task_description: str) -> TaskClass:
        """
        Executes classify_task logic.
        """
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
        """
        Executes check_availability logic.
        """
        # Check available RAM using psutil
        mem = psutil.virtual_memory()
        available_mb = mem.available / (1024 * 1024)
        
        # If available RAM is less than required, return False (would trigger Queueing)
        if available_mb < profile.max_ram_mb:
            return False
        return True
        
    @classmethod
    def allocate(cls, task_description: str) -> Optional[ResourceProfile]:
        """
        Executes allocate logic.
        """
        task_class = cls.classify_task(task_description)
        profile = PROFILES.get(task_class, PROFILES[TaskClass.STANDARD])
        
        if not cls.check_availability(profile):
            raise ResourceWarning(f"Insufficient resources for {task_class}. Requires {profile.max_ram_mb}MB RAM.")
            
        return profile

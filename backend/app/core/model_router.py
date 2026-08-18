"""
@file backend/app/core/model_router.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from typing import Dict, Any

class ModelRouter:
    """
    M15 Frontier Optimization.
    Dynamically routes LLM queries to the most cost-effective/capable model based on task complexity.
    """
    
    @staticmethod
    def route_query(prompt: str, requires_vision: bool = False, requires_json: bool = False) -> str:
        prompt_length = len(prompt)
        
        if requires_vision:
            return "llama-3.2-90b-vision-preview" # Specialized Vision Model
            
        if requires_json or "workflow" in prompt.lower() or "plan" in prompt.lower():
            return "llama3-70b-8192" # High reasoning model
            
        if prompt_length < 200:
            return "llama3-8b-8192" # Fast, low-latency, cheap model for simple tasks
            
        return "mixtral-8x7b-32768" # Large context window fallback

    @staticmethod
    def calculate_budget_impact(model_name: str, tokens: int) -> float:
        """Calculates estimated cost to ensure Policy Limits are respected."""
        rates = {
            "llama3-8b-8192": 0.0001,
            "llama3-70b-8192": 0.0008,
            "llama-3.2-90b-vision-preview": 0.001,
            "mixtral-8x7b-32768": 0.0005
        }
        return (tokens / 1000) * rates.get(model_name, 0.001)

"""
@file tests/unit/test_memory_models.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from app.core.model_router import ModelRouter

def test_model_router_complexity():
    """M15: Verify simple prompts are routed to fast/cheap models."""
    model = ModelRouter.route_query(prompt="Hello, world!", requires_vision=False)
    assert model == "llama3-8b-8192"

def test_model_router_reasoning():
    """M15: Verify complex planning prompts route to high-parameter models."""
    model = ModelRouter.route_query(prompt="Create a step-by-step workflow for data ingestion.", requires_json=True)
    assert model == "llama3-70b-8192"

def test_model_router_vision():
    """M15: Verify vision-required prompts force vision models."""
    model = ModelRouter.route_query(prompt="Analyze this image", requires_vision=True)
    assert model == "llama-3.2-90b-vision-preview"

def test_model_budget_impact():
    """M15: Verify token cost calculation logic."""
    cost = ModelRouter.calculate_budget_impact("llama3-70b-8192", tokens=1000)
    assert cost == 0.0008
    
    cost_cheap = ModelRouter.calculate_budget_impact("llama3-8b-8192", tokens=1000)
    assert cost_cheap == 0.0001

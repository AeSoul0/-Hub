"""
@file backend/app/core/models.py
@description Framework-agnostic model contracts for A.U.R.O.R.A.

This module contains shared Pydantic contracts used by model routing,
request validation, capability negotiation, usage accounting, and response
normalization. It intentionally has no dependency on LangChain or LangGraph.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==============================================================================
# MODEL PROVIDERS
# ==============================================================================


class ModelProvider(str, Enum):
    """
    Supported logical model providers.
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    LOCAL = "local"


# ==============================================================================
# MODEL CAPABILITIES
# ==============================================================================


class ModelCapabilities(BaseModel):
    """
    Describe the capabilities exposed by a model.
    """

    vision: bool = False
    function_calling: bool = False
    json_mode: bool = False
    streaming: bool = False


# ==============================================================================
# MODEL USAGE
# ==============================================================================


class ModelUsage(BaseModel):
    """
    Normalized token and resource usage for one model invocation.
    """

    prompt_tokens: int = Field(
        default=0,
        ge=0,
    )

    completion_tokens: int = Field(
        default=0,
        ge=0,
    )

    total_tokens: int = Field(
        default=0,
        ge=0,
    )

    estimated_cost: float = Field(
        default=0.0,
        ge=0.0,
    )


# ==============================================================================
# MODEL REQUEST
# ==============================================================================


class ModelRequest(BaseModel):
    """
    Framework-agnostic model invocation request.
    """

    messages: List[Dict[str, Any]] = Field(
        default_factory=list,
    )

    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
    )

    max_tokens: int = Field(
        default=1000,
        gt=0,
    )

    model: Optional[str] = None

    provider: Optional[ModelProvider] = None

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
    )


# ==============================================================================
# MODEL RESPONSE
# ==============================================================================


class ModelResponse(BaseModel):
    """
    Framework-agnostic normalized model response.
    """

    content: str = ""

    usage: ModelUsage = Field(
        default_factory=ModelUsage,
    )

    model: Optional[str] = None

    provider: Optional[ModelProvider] = None

    finish_reason: Optional[str] = None

    tool_calls: List[Dict[str, Any]] = Field(
        default_factory=list,
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
    )


# ==============================================================================
# ROUTING REQUEST
# ==============================================================================


class ModelRoutingRequest(BaseModel):
    """
    Describe model-routing requirements independently from a provider SDK.
    """

    prompt: str

    requires_vision: bool = False
    requires_function_calling: bool = False
    requires_json: bool = False

    max_cost: Optional[float] = Field(
        default=None,
        ge=0.0,
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
    )
"""
@file backend/app/agent_engine/guardrails.py
@description Implements guardrails.py. Core components: GuardrailException, InputGuardrail, OutputGuardrail, ToolGuardrail.

This module manages the internal business logic for GuardrailException, InputGuardrail, OutputGuardrail, ToolGuardrail.
It provides specialized functionality to handle: validate, validate, validate_pre_execution, validate_post_execution.
"""
from typing import Dict, Any, Tuple
import re

class GuardrailException(Exception):
    """
    Represents the GuardrailException entity and its core operations.
    """
    pass

class InputGuardrail:
    """
    Represents the InputGuardrail entity and its core operations.
    """
    @classmethod
    def validate(cls, text: str) -> str:
        """
        Executes validate logic.
        """
        # Prevent obvious prompt injection patterns
        disallowed = [r"ignore all previous instructions", r"system prompt"]
        for pattern in disallowed:
            if re.search(pattern, text, re.IGNORECASE):
                raise GuardrailException(f"Input rejected by guardrail: matched pattern {pattern}")
        return text

class OutputGuardrail:
    """
    Represents the OutputGuardrail entity and its core operations.
    """
    @classmethod
    def validate(cls, text: str) -> str:
        """
        Executes validate logic.
        """
        # Prevent leaking sensitive internal formats or keys
        if "AEHUB_SECRET" in text or "sk-" in text:
            raise GuardrailException("Output rejected by guardrail: potential secret leak")
        return text

class ToolGuardrail:
    """
    Represents the ToolGuardrail entity and its core operations.
    """
    @classmethod
    def validate_pre_execution(cls, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes validate_pre_execution logic.
        """
        # Block dangerous parameters before they hit the policy/gateway
        if tool_name == "shell":
            cmd = args.get("cmd", "")
            if re.search(r"\b(rm -rf|mkfs|dd)\b", cmd):
                raise GuardrailException(f"ToolGuardrail rejected parameter for {tool_name}")
        return args

    @classmethod
    def validate_post_execution(cls, tool_name: str, output: Any) -> Any:
        """
        Executes validate_post_execution logic.
        """
        # Sanitize tool output before returning to LLM
        output_str = str(output)
        if len(output_str) > 10000:
            return output_str[:10000] + "... [TRUNCATED BY GUARDRAIL]"
        return output

"""
@file backend/app/agent_engine/guardrails.py
@description Three-Layer LLM Guardrail Controller.

Implements InputGuardrail (Prompt Injection Defense), ToolGuardrail (Execution Parameter Safety),
and OutputGuardrail (Secret Exfiltration Defense). Provides strict runtime checks 
independent of the Policy Engine (Phase 8).
"""

from typing import Dict, Any, Tuple
import re

class GuardrailException(Exception):
    pass

class InputGuardrail:
    @classmethod
    def validate(cls, text: str) -> str:
        # Prevent obvious prompt injection patterns
        disallowed = [r"ignore all previous instructions", r"system prompt"]
        for pattern in disallowed:
            if re.search(pattern, text, re.IGNORECASE):
                raise GuardrailException(f"Input rejected by guardrail: matched pattern {pattern}")
        return text

class OutputGuardrail:
    @classmethod
    def validate(cls, text: str) -> str:
        # Prevent leaking sensitive internal formats or keys
        if "AEHUB_SECRET" in text or "sk-" in text:
            raise GuardrailException("Output rejected by guardrail: potential secret leak")
        return text

class ToolGuardrail:
    @classmethod
    def validate_pre_execution(cls, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        # Block dangerous parameters before they hit the policy/gateway
        if tool_name == "shell":
            cmd = args.get("cmd", "")
            if re.search(r"\b(rm -rf|mkfs|dd)\b", cmd):
                raise GuardrailException(f"ToolGuardrail rejected parameter for {tool_name}")
        return args

    @classmethod
    def validate_post_execution(cls, tool_name: str, output: Any) -> Any:
        # Sanitize tool output before returning to LLM
        output_str = str(output)
        if len(output_str) > 10000:
            return output_str[:10000] + "... [TRUNCATED BY GUARDRAIL]"
        return output

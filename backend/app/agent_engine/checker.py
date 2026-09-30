"""
@file backend/app/agent_engine/checker.py
@description Independent evaluation and verification engine for A.U.R.O.R.A.

This module implements the isolated Checker stage of the native Agent Engine.
The Checker evaluates the worker result, task constraints, and execution trace
through an independent model provider and returns a deterministic decision.

Security invariant:
    Checker failures must never result in ACCEPT.

Provider failures, malformed JSON, missing fields, invalid decisions, and
invalid issue payloads are converted into a FAIL decision so that the runtime
fails closed rather than accepting an unverified worker result.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.agent_engine.adapters.base import ModelProvider
from app.agent_engine.models import (
    CheckerDecision,
    CheckerDecisionEnum,
)


class AgentChecker:
    """
    Independent evaluation boundary for worker-generated results.
    """

    def __init__(self, model_provider: ModelProvider) -> None:
        """
        Initialize the Checker with an independent model provider.

        Args:
            model_provider: Provider used exclusively for result evaluation.
        """
        if model_provider is None:
            raise ValueError("model_provider is required")

        self.model = model_provider

    async def evaluate(
        self,
        task: Dict[str, Any],
        result: Any,
        trace: Optional[List[Any]] = None,
    ) -> CheckerDecision:
        """
        Evaluate a worker result against task requirements and execution trace.

        The provider must return JSON equivalent to:

            {
                "decision": "ACCEPT" | "RETRY" | "FAIL",
                "issues": [
                    {
                        "code": "MISSING_INFO",
                        "severity": "HIGH"
                    }
                ],
                "retry_instruction": "optional string"
            }

        Any provider or parsing failure is treated as FAIL.
        """
        normalized_trace = trace if trace is not None else []

        prompt = self._build_prompt(
            task=task,
            result=result,
            trace=normalized_trace,
        )

        try:
            response = await self.model.generate(
                {
                    "prompt": prompt,
                    "system": (
                        "You are an independent security and correctness checker. "
                        "Return JSON only. Never approve an output when the "
                        "evaluation itself is uncertain."
                    ),
                }
            )
        except Exception:
            return self._failure(
                code="CHECKER_PROVIDER_ERROR",
                instruction=(
                    "The independent checker could not evaluate the worker result. "
                    "Do not accept the result; retry the checker or fail the run."
                ),
            )

        if not isinstance(response, dict):
            return self._failure(
                code="CHECKER_INVALID_RESPONSE",
                instruction="The checker provider returned an invalid response object.",
            )

        output = response.get("output")
        if not isinstance(output, str) or not output.strip():
            return self._failure(
                code="CHECKER_EMPTY_OUTPUT",
                instruction="The checker provider returned no evaluation payload.",
            )

        payload = self._parse_json(output)
        if payload is None:
            return self._failure(
                code="CHECKER_INVALID_JSON",
                instruction="The checker response was not valid JSON.",
            )

        return self._decision_from_payload(payload)

    @staticmethod
    def _build_prompt(
        task: Dict[str, Any],
        result: Any,
        trace: List[Any],
    ) -> str:
        """
        Build the isolated evaluation prompt.

        The worker is never given control over the evaluation instructions.
        """
        return f"""
You are an independent Checker for a highly secure agentic system.

Evaluate whether the Worker's final result satisfies the original task,
the explicit constraints, and the expected output requirements.

Original task:
{task}

Worker result:
{result}

Execution trace:
{trace}

Return strictly valid JSON and nothing else using this schema:

{{
  "decision": "ACCEPT" | "RETRY" | "FAIL",
  "issues": [
    {{
      "code": "MACHINE_READABLE_CODE",
      "severity": "HIGH" | "MEDIUM" | "LOW"
    }}
  ],
  "retry_instruction": "optional corrective instruction"
}}

Rules:
1. ACCEPT only when the result is sufficiently verified.
2. Use RETRY for recoverable correctness or completeness issues.
3. Use FAIL for security, policy, integrity, or unrecoverable issues.
4. Never invent evidence that is absent from the task, result, or trace.
5. When uncertain, do not return ACCEPT.
""".strip()

    @classmethod
    def _decision_from_payload(cls, payload: Dict[str, Any]) -> CheckerDecision:
        """
        Validate and convert a parsed provider payload into CheckerDecision.
        """
        if not isinstance(payload, dict):
            return cls._failure(
                code="CHECKER_INVALID_PAYLOAD",
                instruction="The checker payload must be a JSON object.",
            )

        raw_decision = payload.get("decision")
        if not isinstance(raw_decision, str):
            return cls._failure(
                code="CHECKER_MISSING_DECISION",
                instruction="The checker response did not contain a valid decision.",
            )

        try:
            decision = CheckerDecisionEnum(raw_decision.upper())
        except ValueError:
            return cls._failure(
                code="CHECKER_UNKNOWN_DECISION",
                instruction="The checker returned an unsupported decision.",
            )

        raw_issues = payload.get("issues", [])
        if not isinstance(raw_issues, list):
            return cls._failure(
                code="CHECKER_INVALID_ISSUES",
                instruction="The checker issues field must be a JSON array.",
            )

        issues = []
        for item in raw_issues:
            if not isinstance(item, dict):
                return cls._failure(
                    code="CHECKER_INVALID_ISSUE",
                    instruction="Each checker issue must be a JSON object.",
                )

            code = item.get("code")
            severity = item.get("severity")

            if not isinstance(code, str) or not code.strip():
                return cls._failure(
                    code="CHECKER_INVALID_ISSUE_CODE",
                    instruction="Each checker issue requires a non-empty code.",
                )

            if not isinstance(severity, str) or not severity.strip():
                return cls._failure(
                    code="CHECKER_INVALID_ISSUE_SEVERITY",
                    instruction="Each checker issue requires a non-empty severity.",
                )

            issues.append(
                {
                    "code": code.strip(),
                    "severity": severity.strip().upper(),
                }
            )

        retry_instruction = payload.get("retry_instruction")
        if retry_instruction is not None and not isinstance(
            retry_instruction, str
        ):
            return cls._failure(
                code="CHECKER_INVALID_RETRY_INSTRUCTION",
                instruction="The retry instruction must be a string when provided.",
            )

        return CheckerDecision(
            status=decision,
            issues=issues,
            retry_instruction=retry_instruction,
        )

    @staticmethod
    def _parse_json(output: str) -> Optional[Dict[str, Any]]:
        """
        Extract the first valid JSON object from provider output.

        This accepts plain JSON and fenced/prose-wrapped JSON while rejecting
        payloads that cannot be decoded into an object.
        """
        decoder = json.JSONDecoder()

        for index, character in enumerate(output):
            if character != "{":
                continue

            try:
                payload, _ = decoder.raw_decode(output[index:])
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict):
                return payload

        return None

    @staticmethod
    def _failure(code: str, instruction: str) -> CheckerDecision:
        """
        Construct a deterministic fail-closed decision.
        """
        return CheckerDecision(
            status=CheckerDecisionEnum.FAIL,
            issues=[
                {
                    "code": code,
                    "severity": "HIGH",
                }
            ],
            retry_instruction=instruction,
        )
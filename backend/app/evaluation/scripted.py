"""
@file backend/app/evaluation/scripted.py
@description Scripted model provider for offline agent evaluation (M7).

Offline evals replace only the model: each case scripts the worker's turns
(tool calls or a final answer) and the Critic's decisions. Everything else
(routing of the call, ToolGateway, guardrails, approvals, budget, Context
Manager, memory) runs for real, so the suite measures the engine and fails
when the engine regresses.

Usage is computed from the real request: input tokens are estimated from
the context the model would receive, so context bloat shows up as cost.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

from app.agent_engine.adapters.base import ModelProvider
from app.agent_engine.adapters.openai_adapter import OpenAIAdapter
from app.agent_engine.context import estimate_tokens
from app.agent_engine.models import ToolProposal
from app.agent_engine.pricing import usage_from_response


class ScriptExhaustedError(RuntimeError):
    pass


class ScriptedModel(ModelProvider):
    """
    Plays back a list of steps. A worker step is {"text": "..."} or
    {"call": name, "args": {...}} or {"calls": [{"call": ..., "args": ...}]};
    a Critic step is {"decision": "ACCEPT" | "RETRY" | "FAIL", ...}.
    """

    def __init__(
        self,
        model_name: str,
        steps: List[Dict[str, Any]],
        substitutions: Dict[str, str] | None = None,
    ) -> None:
        super().__init__(model_name=model_name)
        self.steps = list(steps)
        self.contexts: List[Dict[str, Any]] = []
        self.requests: List[str] = []
        self._substitutions = substitutions or {}
        self._call_number = 0

    def _expand(self, value: Any) -> Any:
        if isinstance(value, str):
            for name, secret in self._substitutions.items():
                value = value.replace("{" + name + "}", secret)
            return value
        if isinstance(value, dict):
            return {key: self._expand(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._expand(item) for item in value]
        return value

    @staticmethod
    def render_request(context: Dict[str, Any]) -> str:
        """
        The request as the model would see it: system prompt, tools, input.
        """
        return json.dumps(
            {
                "instructions": context.get("system_prompt", ""),
                "tools": context.get("tools") or [],
                "input": OpenAIAdapter._build_input(context),
            },
            ensure_ascii=False,
            default=str,
        )

    async def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        request = self.render_request(context)
        self.contexts.append(context)
        self.requests.append(request)

        if not self.steps:
            raise ScriptExhaustedError(
                f"{self.model_name}: the script has no step left."
            )

        step = self._expand(self.steps.pop(0))

        if "decision" in step:
            output = json.dumps(
                {
                    "decision": step["decision"],
                    "issues": step.get("issues", []),
                    "retry_instruction": step.get("retry_instruction"),
                }
            )
            proposals: List[ToolProposal] = []
        elif "text" in step:
            output = str(step["text"])
            proposals = []
        else:
            calls = step.get("calls") or [step]
            proposals = []
            for call in calls:
                self._call_number += 1
                proposals.append(
                    ToolProposal(
                        tool_call_id=f"call_{self._call_number}",
                        tool_name=call["call"],
                        arguments=dict(call.get("args") or {}),
                        run_id=str(context.get("run_id", "")),
                    )
                )
            output = json.dumps([step.get("call") or calls], default=str)

        usage = usage_from_response(
            self.model_name,
            SimpleNamespace(
                input_tokens=estimate_tokens(request),
                output_tokens=estimate_tokens(output),
            ),
        )

        return {
            "output": "" if proposals else output,
            "tool_proposals": proposals,
            "usage": usage.to_dict(),
        }


__all__ = ["ScriptExhaustedError", "ScriptedModel"]

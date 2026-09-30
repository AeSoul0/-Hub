"""
@file backend/app/agent_engine/adapters/langchain_adapter.py
@description Framework-agnostic compatibility adapter for legacy model integrations.

The historical implementation depended directly on LangChain message classes.
The native A.U.R.O.R.A. runtime now communicates through the ModelProvider
interface, so this adapter intentionally accepts a generic async model object.

Expected model contract:

    await model.ainvoke(payload)

The returned payload may be a dictionary or an object exposing:
    - output
    - content
    - tool_calls

No LangChain package is imported or required here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agent_engine.adapters.base import ModelProvider
from app.agent_engine.models import ToolProposal


# ==============================================================================
# NATIVE COMPATIBILITY ADAPTER
# ==============================================================================


class LangchainModelAdapter(ModelProvider):
    """
    Compatibility adapter preserving the historical class name.

    The implementation is intentionally independent from LangChain. Existing
    callers can keep importing LangchainModelAdapter while progressively
    migrating to native ModelProvider implementations.
    """

    def __init__(
        self,
        model: Any,
        tools: Optional[List[Any]] = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the adapter around a generic async model provider.
        """
        if model is None:
            raise ValueError(
                "A model provider instance is required."
            )

        model_name = getattr(
            model,
            "model_name",
            None,
        ) or getattr(
            model,
            "model",
            None,
        ) or "compatibility-model"

        super().__init__(
            model_name=str(model_name),
            **kwargs,
        )

        self.model = model
        self.tools = list(
            tools or []
        )

    # ==========================================================================
    # GENERATION
    # ==========================================================================

    async def generate(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute one model turn through a native async invocation contract.
        """
        task_value = context.get(
            "task",
            "",
        )

        if isinstance(
            task_value,
            dict,
        ):
            task = str(
                task_value.get(
                    "description",
                    "",
                )
            )
        else:
            task = str(
                task_value
            )

        system_prompt = str(
            context.get(
                "system_prompt",
                "You are an intelligent agent.",
            )
        )

        feedback = context.get(
            "feedback"
        )

        observations = []

        for observation in context.get(
            "observations",
            [],
        ):
            if isinstance(
                observation,
                dict,
            ):
                observations.append(
                    {
                        "tool_call_id": observation.get(
                            "tool_call_id"
                        ),
                        "content": str(
                            observation.get(
                                "content",
                                "",
                            )
                        ),
                    }
                )
            else:
                observations.append(
                    {
                        "tool_call_id": getattr(
                            observation,
                            "tool_call_id",
                            None,
                        ),
                        "content": str(
                            getattr(
                                observation,
                                "content",
                                observation,
                            )
                        ),
                    }
                )

        payload: Dict[str, Any] = {
            "system_prompt": system_prompt,
            "task": task,
            "feedback": (
                str(feedback)
                if feedback is not None
                else None
            ),
            "observations": observations,
            "tools": self.tools,
            "run_id": context.get(
                "run_id"
            ),
            "session_id": context.get(
                "session_id"
            ),
            "workspace_id": context.get(
                "workspace_id"
            ),
            "principal_id": context.get(
                "principal_id"
            ),
            "role": context.get(
                "role"
            ),
            "capabilities": context.get(
                "capabilities"
            ),
        }

        ainvoke = getattr(
            self.model,
            "ainvoke",
            None,
        )

        if ainvoke is None:
            raise TypeError(
                "The compatibility model must expose an async 'ainvoke' method."
            )

        response = await ainvoke(
            payload
        )

        output, raw_tool_calls = self._normalize_response(
            response
        )

        run_id = str(
            context.get(
                "run_id",
                "",
            )
        )

        if not run_id:
            raise ValueError(
                "Model execution context is missing run_id."
            )

        proposals = []

        for index, tool_call in enumerate(
            raw_tool_calls
        ):
            normalized = self._normalize_tool_call(
                tool_call,
                index=index,
            )

            if normalized is None:
                continue

            proposals.append(
                ToolProposal(
                    tool_call_id=normalized["tool_call_id"],
                    tool_name=normalized["tool_name"],
                    arguments=normalized["arguments"],
                    run_id=run_id,
                )
            )

        return {
            "output": output,
            "tool_proposals": proposals,
        }

    # ==========================================================================
    # RESPONSE NORMALIZATION
    # ==========================================================================

    @staticmethod
    def _normalize_response(
        response: Any,
    ) -> tuple[Any, List[Any]]:
        """
        Normalize dictionary- or object-based model responses.
        """
        if isinstance(
            response,
            dict,
        ):
            output = response.get(
                "output",
                response.get(
                    "content",
                    "",
                ),
            )

            tool_calls = response.get(
                "tool_calls",
                response.get(
                    "tool_proposals",
                    [],
                ),
            )

            return (
                output,
                list(
                    tool_calls or []
                ),
            )

        output = getattr(
            response,
            "output",
            None,
        )

        if output is None:
            output = getattr(
                response,
                "content",
                "",
            )

        tool_calls = getattr(
            response,
            "tool_calls",
            [],
        )

        return (
            output,
            list(
                tool_calls or []
            ),
        )

    @staticmethod
    def _normalize_tool_call(
        tool_call: Any,
        index: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Normalize one model tool-call representation.
        """
        if isinstance(
            tool_call,
            ToolProposal,
        ):
            return {
                "tool_call_id": tool_call.tool_call_id,
                "tool_name": tool_call.tool_name,
                "arguments": dict(
                    tool_call.arguments
                ),
            }

        if isinstance(
            tool_call,
            dict,
        ):
            tool_call_id = (
                tool_call.get("tool_call_id")
                or tool_call.get("id")
                or tool_call.get("call_id")
            )

            tool_name = (
                tool_call.get("tool_name")
                or tool_call.get("name")
            )

            arguments = tool_call.get(
                "arguments",
                tool_call.get(
                    "args",
                    {},
                ),
            )

        else:
            tool_call_id = (
                getattr(
                    tool_call,
                    "tool_call_id",
                    None,
                )
                or getattr(
                    tool_call,
                    "id",
                    None,
                )
                or getattr(
                    tool_call,
                    "call_id",
                    None,
                )
            )

            tool_name = (
                getattr(
                    tool_call,
                    "tool_name",
                    None,
                )
                or getattr(
                    tool_call,
                    "name",
                    None,
                )
            )

            arguments = getattr(
                tool_call,
                "arguments",
                getattr(
                    tool_call,
                    "args",
                    {},
                ),
            )

        if not tool_name:
            return None

        if not isinstance(
            arguments,
            dict,
        ):
            raise ValueError(
                f"Tool call '{tool_name}' returned non-object arguments."
            )

        return {
            "tool_call_id": str(
                tool_call_id
                or f"tool_call_{index + 1}"
            ),
            "tool_name": str(
                tool_name
            ),
            "arguments": dict(
                arguments
            ),
        }


__all__ = [
    "LangchainModelAdapter",
]
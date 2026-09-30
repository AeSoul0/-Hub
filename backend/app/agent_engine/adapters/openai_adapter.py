"""
@file backend/app/agent_engine/adapters/openai_adapter.py
@description Native OpenAI Responses API adapter for A.U.R.O.R.A.

This adapter translates the framework-agnostic AgentRuntime context into the
official OpenAI Responses API contract and converts model function calls back
into native ToolProposal objects.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from openai import AsyncOpenAI

from app.agent_engine.adapters.base import ModelProvider
from app.agent_engine.models import ToolProposal


# ==============================================================================
# OPENAI ADAPTER
# ==============================================================================


class OpenAIAdapter(ModelProvider):
    """
    ModelProvider implementation backed by the OpenAI Responses API.

    The adapter remains framework-agnostic from the runtime's perspective:
    input and output are normalized dictionaries and native ToolProposal
    instances.
    """

    def __init__(
        self,
        model_name: str = "default",
        **kwargs: Any,
    ) -> None:
        """
        Initialize the adapter without performing network I/O.
        """
        resolved_model = (
            os.getenv(
                "OPENAI_MODEL",
                "gpt-5.5",
            )
            if model_name == "default"
            else model_name
        )

        api_key = kwargs.pop(
            "api_key",
            None,
        ) or os.getenv(
            "OPENAI_API_KEY"
        )

        base_url = kwargs.pop(
            "base_url",
            None,
        ) or os.getenv(
            "OPENAI_BASE_URL"
        )

        timeout = kwargs.pop(
            "timeout",
            60.0,
        )

        super().__init__(
            model_name=resolved_model,
            **kwargs,
        )

        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._client: AsyncOpenAI | None = None

    # ==========================================================================
    # CLIENT LIFECYCLE
    # ==========================================================================

    def _get_client(self) -> AsyncOpenAI:
        """
        Lazily create the OpenAI asynchronous client.
        """
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for OpenAIAdapter."
            )

        if self._client is None:
            client_kwargs: Dict[str, Any] = {
                "api_key": self._api_key,
                "timeout": self._timeout,
            }

            if self._base_url:
                client_kwargs["base_url"] = self._base_url

            self._client = AsyncOpenAI(
                **client_kwargs
            )

        return self._client

    # ==========================================================================
    # INPUT NORMALIZATION
    # ==========================================================================

    @staticmethod
    def _observation_to_input(
        observation: Any,
    ) -> Dict[str, Any]:
        """
        Convert one runtime Observation into a Responses API tool output item.
        """
        tool_call_id = getattr(
            observation,
            "tool_call_id",
            None,
        )

        content = getattr(
            observation,
            "content",
            observation,
        )

        if not tool_call_id:
            return {
                "role": "user",
                "content": (
                    "Tool observation:\n"
                    f"{content}"
                ),
            }

        return {
            "type": "function_call_output",
            "call_id": tool_call_id,
            "output": str(content),
        }

    @classmethod
    def _build_input(
        cls,
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Build the normalized Responses API input sequence.
        """
        task = context.get(
            "task",
            {},
        )

        if isinstance(
            task,
            dict,
        ):
            task_text = str(
                task.get(
                    "description",
                    task,
                )
            )
        else:
            task_text = str(task)

        explicit_prompt = context.get(
            "prompt"
        )

        if explicit_prompt:
            task_text = str(
                explicit_prompt
            )

        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": task_text,
            }
        ]

        feedback = context.get(
            "feedback"
        )

        if feedback:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Checker feedback:\n"
                        f"{feedback}"
                    ),
                }
            )

        for observation in context.get(
            "observations",
            [],
        ):
            messages.append(
                cls._observation_to_input(
                    observation
                )
            )

        return messages

    # ==========================================================================
    # RESPONSE NORMALIZATION
    # ==========================================================================

    @staticmethod
    def _extract_output_text(
        response: Any,
    ) -> str:
        """
        Extract normalized output text from a Responses API response.
        """
        output_text = getattr(
            response,
            "output_text",
            None,
        )

        if output_text is not None:
            return str(
                output_text
            )

        fragments: List[str] = []

        for item in getattr(
            response,
            "output",
            [],
        ):
            item_type = getattr(
                item,
                "type",
                None,
            )

            if item_type != "message":
                continue

            for content in getattr(
                item,
                "content",
                [],
            ):
                text = getattr(
                    content,
                    "text",
                    None,
                )

                if text:
                    fragments.append(
                        str(text)
                    )

        return "\n".join(
            fragments
        )

    @staticmethod
    def _extract_tool_proposals(
        response: Any,
        run_id: str,
    ) -> List[ToolProposal]:
        """
        Convert Responses API function calls into native ToolProposal objects.
        """
        proposals: List[ToolProposal] = []

        for item in getattr(
            response,
            "output",
            [],
        ):
            if getattr(
                item,
                "type",
                None,
            ) != "function_call":
                continue

            tool_name = getattr(
                item,
                "name",
                None,
            )

            call_id = getattr(
                item,
                "call_id",
                None,
            )

            raw_arguments = getattr(
                item,
                "arguments",
                "{}",
            )

            if not tool_name or not call_id:
                raise ValueError(
                    "OpenAI returned an invalid function call."
                )

            if isinstance(
                raw_arguments,
                str,
            ):
                try:
                    arguments = json.loads(
                        raw_arguments
                    )
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON arguments for tool '{tool_name}'."
                    ) from exc
            elif isinstance(
                raw_arguments,
                dict,
            ):
                arguments = raw_arguments
            else:
                raise ValueError(
                    f"Invalid arguments for tool '{tool_name}'."
                )

            if not isinstance(
                arguments,
                dict,
            ):
                raise ValueError(
                    f"Tool '{tool_name}' arguments must be a JSON object."
                )

            proposals.append(
                ToolProposal(
                    tool_call_id=call_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    run_id=run_id,
                )
            )

        return proposals

    # ==========================================================================
    # MODEL EXECUTION
    # ==========================================================================

    async def generate(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute one model turn and normalize the result for AgentRuntime.
        """
        client = self._get_client()

        system_prompt = str(
            context.get(
                "system_prompt",
                "You are a specialized A.U.R.O.R.A. agent.",
            )
        )

        run_id = str(
            context.get(
                "run_id",
                "",
            )
        )

        request: Dict[str, Any] = {
            "model": self.model_name,
            "instructions": system_prompt,
            "input": self._build_input(
                context
            ),
        }

        tools = context.get(
            "tools"
        )

        if tools:
            request["tools"] = tools

        response = await client.responses.create(
            **request
        )

        output = self._extract_output_text(
            response
        )

        tool_proposals = (
            self._extract_tool_proposals(
                response,
                run_id=run_id,
            )
        )

        return {
            "output": output,
            "tool_proposals": tool_proposals,
            "response_id": getattr(
                response,
                "id",
                None,
            ),
        }
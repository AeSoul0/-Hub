"""
@file backend/app/agent_engine/adapters/chat_completions_adapter.py
@description ModelProvider for OpenAI-compatible Chat Completions endpoints.

Used for OpenRouter (cloud, pay-as-you-go and free tiers) and for local
servers such as Ollama or LM Studio (spec 3.5: sensitive roles can run on
local models). The runtime contract is the same as OpenAIAdapter: the input
is rebuilt from the durable context on every turn, so a run can move between
providers mid-way without losing or repeating tool calls.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from app.agent_engine.adapters.base import ModelProvider
from app.agent_engine.adapters.openai_adapter import OpenAIAdapter
from app.agent_engine.pricing import usage_from_response


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LOCAL_BASE_URL = "http://localhost:11434/v1"


class ChatCompletionsAdapter(ModelProvider):
    """
    ModelProvider backed by an OpenAI-compatible Chat Completions API.
    """

    def __init__(
        self,
        model_name: str,
        base_url: str,
        api_key: Optional[str],
        provider: str = "chat",
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name=model_name, **kwargs)

        self.provider = provider
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout
        self._client: AsyncOpenAI | None = None

    @classmethod
    def openrouter(cls, model_name: str, **kwargs: Any) -> "ChatCompletionsAdapter":
        return cls(
            model_name=model_name,
            base_url=os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
            api_key=os.getenv("OPENROUTER_API_KEY"),
            provider="openrouter",
            **kwargs,
        )

    @classmethod
    def local(cls, model_name: str, **kwargs: Any) -> "ChatCompletionsAdapter":
        # Local servers usually ignore the key, but the SDK requires one.
        return cls(
            model_name=model_name,
            base_url=os.getenv("AEHUB_LOCAL_BASE_URL", LOCAL_BASE_URL),
            api_key=os.getenv("AEHUB_LOCAL_API_KEY", "local"),
            provider="local",
            **kwargs,
        )

    def _get_client(self) -> AsyncOpenAI:
        if not self._api_key:
            raise RuntimeError(
                f"An API key is required for the '{self.provider}' provider."
            )

        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )

        return self._client

    # ==========================================================================
    # INPUT CONVERSION
    # ==========================================================================

    @staticmethod
    def _to_messages(
        system_prompt: str,
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Convert the Responses-style input built by OpenAIAdapter into Chat
        Completions messages: a function_call becomes an assistant message
        with tool_calls, its output a tool message.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        for item in items:
            item_type = item.get("type")

            if item_type == "function_call":
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": item["call_id"],
                                "type": "function",
                                "function": {
                                    "name": item["name"],
                                    "arguments": item["arguments"],
                                },
                            }
                        ],
                    }
                )
            elif item_type == "function_call_output":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": item["call_id"],
                        "content": item["output"],
                    }
                )
            else:
                messages.append(
                    {
                        "role": item.get("role", "user"),
                        "content": item.get("content", ""),
                    }
                )

        return messages

    @staticmethod
    def _to_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters")
                    or {"type": "object", "properties": {}},
                },
            }
            for tool in tools
        ]

    # ==========================================================================
    # MODEL EXECUTION
    # ==========================================================================

    async def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        client = self._get_client()

        system_prompt = str(
            context.get(
                "system_prompt",
                "You are a specialized A.U.R.O.R.A. agent.",
            )
        )
        run_id = str(context.get("run_id", ""))

        request: Dict[str, Any] = {
            "model": self.model_name,
            "messages": self._to_messages(
                system_prompt,
                OpenAIAdapter._build_input(context),
            ),
        }

        tools = context.get("tools")
        if tools:
            request["tools"] = self._to_tools(tools)

        response = await client.chat.completions.create(**request)

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ValueError(f"The '{self.provider}' provider returned no choices.")

        message = choices[0].message

        # Reuse the Responses parser: tool calls become function_call items.
        calls = SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    call_id=call.id,
                    name=call.function.name,
                    arguments=call.function.arguments,
                )
                for call in (getattr(message, "tool_calls", None) or [])
            ]
        )

        return {
            "output": getattr(message, "content", None) or "",
            "tool_proposals": OpenAIAdapter._extract_tool_proposals(
                calls,
                run_id=run_id,
            ),
            "response_id": getattr(response, "id", None),
            "usage": usage_from_response(
                self.model_name,
                getattr(response, "usage", None),
            ).to_dict(),
        }


__all__ = [
    "ChatCompletionsAdapter",
    "LOCAL_BASE_URL",
    "OPENROUTER_BASE_URL",
]

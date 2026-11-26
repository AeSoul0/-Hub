"""
@file backend/app/agent_engine/adapters/pydantic_ai_adapter.py
@description The one model adapter of the engine (P1, ADR-032): Pydantic AI
as the layer that talks to the models, A.U.R.O.R.A. as the loop.

`generate` makes exactly one model request (`pydantic_ai.direct.model_request`)
and returns the text, the proposed tool calls as ToolProposal, the usage and
the response id. Pydantic AI runs no tool: the tool definitions only let the
model propose calls, and every proposal goes to the Tool Gateway (policy,
guardrails, approvals, budget, audit).

Providers, each with its native Pydantic AI model:
- openai: OpenAI Responses API;
- openrouter and local (an OpenAI-compatible server on this machine, such
  as Ollama or LM Studio): Chat Completions on their address;
- groq, anthropic, google (Gemini).

The input is rebuilt from the durable context on every turn
(`model_input.build_input`), so a run can change provider mid-way.

While a draft is open for the command (N1, `agent_engine.streaming`), the
request is streamed and its text goes to the draft as it arrives; the result
is the same. A provider that cannot stream is asked again without it.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from app.agent_engine.adapters.base import ModelProvider
from app.agent_engine.model_input import DEFAULT_SYSTEM_PROMPT, build_input, tool_proposals
from app.agent_engine.pricing import usage_from_response
from app.agent_engine.streaming import DraftStream, current_draft
from app.core.runtime_config import config_value

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LOCAL_BASE_URL = "http://localhost:11434/v1"
DEFAULT_TIMEOUT_SECONDS = 60.0

# Provider -> the variable (keyring or environment) holding its key.
PROVIDER_KEYS: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
}

# The local server needs no key, but the OpenAI SDK requires one.
LOCAL_KEY_VARIABLE = "AEHUB_LOCAL_API_KEY"
PROVIDERS = ("openai", "openrouter", "local", "groq", "anthropic", "google")


class PydanticAIAdapter(ModelProvider):
    """
    ModelProvider for every provider, through Pydantic AI.

    `client` is the provider's own SDK client (AsyncOpenAI, AsyncGroq,
    AsyncAnthropic, google-genai Client). It is built on the first request
    from the key, unless one is given, as the tests do.
    """

    def __init__(
        self,
        model_name: str,
        provider: str = "openai",
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: Any = None,
        **kwargs: Any,
    ) -> None:
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider '{provider}': expected one of {', '.join(PROVIDERS)}.")

        super().__init__(model_name=model_name, **kwargs)

        self.provider = provider
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._client = client
        self._model: Any = None
        self._model_client: Any = None

    # ==========================================================================
    # CONSTRUCTION
    # ==========================================================================

    @classmethod
    def for_provider(cls, provider: str, model_name: str, **kwargs: Any) -> "PydanticAIAdapter":
        """
        The adapter of `provider:model_name`, with the key and the address of
        the current configuration.
        """
        if provider == "openai":
            if model_name == "default":
                model_name = config_value("OPENAI_MODEL") or "gpt-5.5"
            kwargs.setdefault("base_url", os.getenv("OPENAI_BASE_URL") or None)
        elif provider == "openrouter":
            kwargs.setdefault("base_url", os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL))
        elif provider == "local":
            kwargs.setdefault("base_url", config_value("AEHUB_LOCAL_BASE_URL") or LOCAL_BASE_URL)
            kwargs.setdefault("api_key", os.getenv(LOCAL_KEY_VARIABLE, "local"))

        if provider in PROVIDER_KEYS:
            kwargs.setdefault("api_key", os.getenv(PROVIDER_KEYS[provider]))

        return cls(model_name=model_name, provider=provider, **kwargs)

    def _require_key(self) -> str:
        if not self._api_key:
            variable = PROVIDER_KEYS.get(self.provider, LOCAL_KEY_VARIABLE)
            raise RuntimeError(f"An API key is required for the '{self.provider}' provider ({variable}).")
        return self._api_key

    def _openai_client(self) -> Any:
        if self._client is not None:
            return self._client

        from openai import AsyncOpenAI

        options: Dict[str, Any] = {"api_key": self._require_key(), "timeout": self._timeout}

        if self._base_url:
            options["base_url"] = self._base_url

        return AsyncOpenAI(**options)

    def _build_model(self) -> Any:
        provider = self.provider

        if provider == "openai":
            from pydantic_ai.models.openai import OpenAIResponsesModel
            from pydantic_ai.providers.openai import OpenAIProvider

            return OpenAIResponsesModel(self.model_name, provider=OpenAIProvider(openai_client=self._openai_client()))

        if provider in ("openrouter", "local"):
            # Plain Chat Completions on the provider's address, as before P1:
            # Pydantic AI's OpenRouterModel refuses names without a vendor
            # prefix, which OpenRouter itself accepts (e.g. "openrouter/auto").
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            return OpenAIChatModel(self.model_name, provider=OpenAIProvider(openai_client=self._openai_client()))

        if provider == "groq":
            from pydantic_ai.models.groq import GroqModel
            from pydantic_ai.providers.groq import GroqProvider

            if self._client is not None:
                return GroqModel(self.model_name, provider=GroqProvider(groq_client=self._client))
            return GroqModel(self.model_name, provider=GroqProvider(api_key=self._require_key(), base_url=self._base_url))

        if provider == "anthropic":
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider

            if self._client is not None:
                return AnthropicModel(self.model_name, provider=AnthropicProvider(anthropic_client=self._client))
            return AnthropicModel(
                self.model_name, provider=AnthropicProvider(api_key=self._require_key(), base_url=self._base_url)
            )

        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        if self._client is not None:
            return GoogleModel(self.model_name, provider=GoogleProvider(client=self._client))
        return GoogleModel(self.model_name, provider=GoogleProvider(api_key=self._require_key(), base_url=self._base_url))

    def _get_model(self) -> Any:
        # Rebuilt when a test (or a key rotation) swaps the client.
        if self._model is None or self._model_client is not self._client:
            self._model = self._build_model()
            self._model_client = self._client
        return self._model

    # ==========================================================================
    # MESSAGES
    # ==========================================================================

    @staticmethod
    def to_messages(system_prompt: str, items: List[Dict[str, Any]]) -> List[Any]:
        """
        The input items as Pydantic AI messages: user text and tool outputs
        in requests, the model's earlier tool calls in responses, in order.
        """
        from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart

        names = {item["call_id"]: item["name"] for item in items if item.get("type") == "function_call"}
        messages: List[Any] = []
        request_parts: List[Any] = []
        response_parts: List[Any] = []

        def flush_request() -> None:
            if request_parts:
                messages.append(ModelRequest(parts=list(request_parts), instructions=system_prompt))
                request_parts.clear()

        def flush_response() -> None:
            if response_parts:
                messages.append(ModelResponse(parts=list(response_parts)))
                response_parts.clear()

        for item in items:
            kind = item.get("type")

            if kind == "function_call":
                flush_request()
                response_parts.append(
                    ToolCallPart(tool_name=item["name"], args=item.get("arguments") or "{}", tool_call_id=item["call_id"])
                )
            elif kind == "function_call_output":
                flush_response()
                request_parts.append(
                    ToolReturnPart(
                        tool_name=names.get(item["call_id"], "tool"),
                        content=item["output"],
                        tool_call_id=item["call_id"],
                    )
                )
            else:
                flush_response()
                request_parts.append(UserPromptPart(content=str(item.get("content", ""))))

        flush_response()
        flush_request()

        if not messages or not hasattr(messages[-1], "instructions"):
            # The last message must be a request; an empty one carries the prompt.
            messages.append(ModelRequest(parts=[], instructions=system_prompt))

        return messages

    @staticmethod
    def to_tools(tools: List[Dict[str, Any]]) -> List[Any]:
        from pydantic_ai.tools import ToolDefinition

        return [
            ToolDefinition(
                name=tool["name"],
                description=tool.get("description") or "",
                parameters_json_schema=tool.get("parameters") or {"type": "object", "properties": {}},
                # As before P1: no strict mode, which some OpenRouter and
                # local models reject; the Tool Gateway validates arguments.
                strict=False,
            )
            for tool in tools
        ]

    # ==========================================================================
    # MODEL EXECUTION
    # ==========================================================================

    async def _streamed(self, draft: DraftStream, arguments: Dict[str, Any]) -> Any:
        """The same request, streamed: its text goes to the draft as it arrives."""
        from pydantic_ai.direct import model_request_stream
        from pydantic_ai.messages import PartDeltaEvent, PartStartEvent, TextPart, TextPartDelta

        async with model_request_stream(**arguments) as stream:
            async for event in stream:
                if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                    await draft.delta(event.part.content)
                elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    await draft.delta(event.delta.content_delta)
            return stream.get()

    async def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        from pydantic_ai.direct import model_request
        from pydantic_ai.messages import TextPart, ToolCallPart
        from pydantic_ai.models import ModelRequestParameters

        system_prompt = str(context.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        run_id = str(context.get("run_id", ""))

        arguments: Dict[str, Any] = {
            "model": self._get_model(),
            "messages": self.to_messages(system_prompt, build_input(context)),
            "model_settings": {"timeout": self._timeout},
            "model_request_parameters": ModelRequestParameters(
                function_tools=self.to_tools(context.get("tools") or [])
            ),
            "instrument": False,
        }

        draft = current_draft()
        response = None
        if draft is not None:
            try:
                response = await self._streamed(draft, arguments)
            except Exception as exc:  # noqa: BLE001 - the draft is optional: the answer comes unstreamed
                logger.info("Streaming from %s failed, asking without it: %s", self.model_name, exc)
                await draft.reset()
        if response is None:
            response = await model_request(**arguments)

        text = "".join(part.content for part in response.parts if isinstance(part, TextPart))
        calls = [
            (part.tool_call_id, part.tool_name, part.args)
            for part in response.parts
            if isinstance(part, ToolCallPart)
        ]

        if draft is not None:
            # A turn that calls tools was not the answer: its words leave the draft.
            if calls:
                await draft.reset()
            else:
                await draft.flush()

        return {
            "output": text,
            "tool_proposals": tool_proposals(calls, run_id=run_id),
            "response_id": response.provider_response_id,
            "usage": usage_from_response(self.model_name, response.usage).to_dict(),
        }


__all__ = [
    "LOCAL_BASE_URL",
    "OPENROUTER_BASE_URL",
    "PROVIDERS",
    "PROVIDER_KEYS",
    "PydanticAIAdapter",
]

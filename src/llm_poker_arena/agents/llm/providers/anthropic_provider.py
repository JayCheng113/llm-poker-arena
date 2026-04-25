"""AnthropicProvider — adapter for Anthropic Claude via the official SDK.

Phase 3a scope: send messages + tools, normalize response into LLMResponse,
translate APIStatusError into transient (5xx, 429) or permanent (4xx).

Out of scope (3b): extended-thinking blocks, capability probe, system prompt
caching headers.
"""
from __future__ import annotations

from typing import Any

from anthropic import APIStatusError, APITimeoutError, AsyncAnthropic, RateLimitError

from llm_poker_arena.agents.llm.provider_base import (
    LLMProvider,
    ProviderPermanentError,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    TokenCounts,
    ToolCall,
)


class AnthropicProvider(LLMProvider):
    def __init__(
        self, *, model: str, api_key: str, max_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = AsyncAnthropic(api_key=api_key)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=temperature,
                messages=messages,
                tools=tools or None,
            )
        except (APITimeoutError, RateLimitError) as e:
            raise ProviderTransientError(str(e)) from e
        except APIStatusError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and status >= 500:
                raise ProviderTransientError(f"{status}: {e}") from e
            if status == 429:
                raise ProviderTransientError(f"429 rate limited: {e}") from e
            raise ProviderPermanentError(f"{status}: {e}") from e

        return self._normalize(resp)

    def provider_name(self) -> str:
        return "anthropic"

    def _normalize(self, resp: Any) -> LLMResponse:  # noqa: ANN401
        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []
        raw_blocks: list[dict[str, Any]] = []
        for block in resp.content:
            block_dump = (
                block.model_dump() if hasattr(block, "model_dump") else dict(block)
            )
            raw_blocks.append(block_dump)
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    name=block.name,
                    args=dict(block.input or {}),
                    tool_use_id=block.id,
                ))
            elif block.type == "text":
                text_parts.append(block.text)

        usage = resp.usage
        tokens = TokenCounts(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_input_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            cache_creation_input_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        )

        stop_reason_raw = resp.stop_reason or "other"
        stop_reason = stop_reason_raw if stop_reason_raw in (
            "end_turn", "tool_use", "max_tokens", "stop_sequence",
        ) else "other"

        return LLMResponse(
            provider="anthropic",
            model=resp.model,
            stop_reason=stop_reason,
            tool_calls=tuple(tool_calls),
            text_content="".join(text_parts),
            tokens=tokens,
            raw_assistant_turn=AssistantTurn(
                provider="anthropic", blocks=tuple(raw_blocks),
            ),
        )


__all__ = ["AnthropicProvider"]

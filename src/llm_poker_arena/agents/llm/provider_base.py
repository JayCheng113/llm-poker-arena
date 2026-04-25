"""LLMProvider ABC (spec §4.4). Phase 3a fully defines the interface; only
`complete()` and `provider_name()` get implemented. The other abstract
methods raise NotImplementedError in 3a and are flesh-filled in 3b.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
)


class ProviderTransientError(Exception):
    """Raised by providers for retryable wire errors (HTTP 5xx, rate limit, timeout).

    LLMAgent's ReAct loop catches this and consumes one api_retry slot.
    """


class ProviderPermanentError(Exception):
    """Raised by providers for non-retryable errors (auth fail, bad request).

    LLMAgent does NOT retry; the hand is censored via api_error.
    """


class LLMProvider(ABC):
    """Wire-level adapter for a specific LLM API (Anthropic, OpenAI, ...)."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        """Send a request to the provider and return a normalized LLMResponse.

        Raises ProviderTransientError on retryable failure;
        ProviderPermanentError on non-retryable.
        """

    @abstractmethod
    def provider_name(self) -> str:
        """Stable provider identifier, e.g. 'anthropic'."""

    def serialize_assistant_turn(self, response: LLMResponse) -> AssistantTurn:
        """spec §4.4 BR2-07: re-serialize provider response as assistant message
        so the next round can include it. Phase 3a default: return the raw
        AssistantTurn untouched (Anthropic thinking-block byte-identical
        preservation lands in 3b).
        """
        return response.raw_assistant_turn

    def extract_reasoning_artifact(self, response: LLMResponse) -> Any:  # noqa: ANN401
        """spec §4.4: provider-specific reasoning extraction. 3a stub."""
        raise NotImplementedError("Phase 3b feature — reasoning artifact extraction")

    async def probe(self) -> Any:  # noqa: ANN401
        """spec §4.4 HR2-03: live capability probe. 3a stub."""
        raise NotImplementedError("Phase 3b feature — capability probe")

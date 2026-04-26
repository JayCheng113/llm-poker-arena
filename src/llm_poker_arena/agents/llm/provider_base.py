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
    ObservedCapability,
    ReasoningArtifact,
    ToolCall,
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
        *,
        system: str | None = None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        """Send a request to the provider and return a normalized LLMResponse.

        `system` is the cached system prompt (Anthropic uses
        messages.create(system=...)). Providers without a separate system
        slot may prepend it to the first user message internally.

        Raises ProviderTransientError on retryable failure;
        ProviderPermanentError on non-retryable.
        """

    @abstractmethod
    def provider_name(self) -> str:
        """Stable provider identifier, e.g. 'anthropic'."""

    @abstractmethod
    def build_assistant_message_for_replay(
        self,
        response: LLMResponse,
    ) -> dict[str, Any]:
        """Reconstruct the assistant turn (in this provider's wire format) so
        it can be appended to `messages` for the next ReAct iteration. For
        Anthropic this is `{"role":"assistant","content":[blocks...]}` with
        thinking blocks preserved byte-identical (BR2-07). For OpenAI Chat:
        `{"role":"assistant","content":text,"tool_calls":[...]}`.
        """

    @abstractmethod
    def build_tool_result_messages(
        self,
        *,
        tool_calls: tuple[ToolCall, ...],
        is_error: bool,
        content: str,
    ) -> list[dict[str, Any]]:
        """Build the message(s) that respond to the prior assistant turn's
        tool_calls. Returned LIST because OpenAI requires one `role: tool`
        message per tool_call, while Anthropic bundles all tool_results into
        a single user message with N content blocks. LLMAgent always uses
        `messages.extend(...)`.

        EVERY tool_call in the prior assistant turn must be answered, otherwise
        Anthropic returns 400; OpenAI similarly drops the conversation if
        tool_call_ids go unanswered.
        """

    @abstractmethod
    def build_user_text_message(self, text: str) -> dict[str, Any]:
        """Plain user message. Used by LLMAgent's no_tool_retry branch where
        the prior assistant turn had NO tool_calls (so we don't need
        tool_result protocol). Anthropic + OpenAI both accept the canonical
        `{"role":"user","content":text}`.
        """

    def serialize_assistant_turn(self, response: LLMResponse) -> AssistantTurn:
        """spec §4.4 BR2-07: re-serialize provider response as assistant message
        so the next round can include it. Phase 3a default: return the raw
        AssistantTurn untouched (Anthropic thinking-block byte-identical
        preservation lands in 3b).
        """
        return response.raw_assistant_turn

    @abstractmethod
    def extract_reasoning_artifact(
        self,
        response: LLMResponse,
    ) -> tuple[ReasoningArtifact, ...]:
        """spec §4.6: extract provider-specific reasoning artifacts (Anthropic
        thinking blocks, DeepSeek `reasoning_content`, OpenAI summary). Return
        empty tuple if the response carries no reasoning artifact. Each
        artifact carries `provider_raw_index` for forensic traceability."""

    @abstractmethod
    async def probe(self) -> ObservedCapability:
        """spec §4.4 HR2-03: minimal cheap probe; called once per session at
        startup. Result is written to meta.json.provider_capabilities. Used
        to surface real provider behavior (vs the stale spec capability table)
        for cross-provider analysis."""

"""Pydantic dataclass schemas for LLM agent decision pipeline (spec §4.1, §4.3)."""
from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from llm_poker_arena.engine.legal_actions import Action


def _frozen() -> ConfigDict:
    return ConfigDict(extra="forbid", frozen=True)


class TokenCounts(BaseModel):
    """Provider-agnostic token usage. Anthropic-specific cache fields are
    plumbed through; OpenAI / others zero them in 3b adapters."""

    model_config = _frozen()

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int

    @classmethod
    def zero(cls) -> TokenCounts:
        return cls(input_tokens=0, output_tokens=0,
                   cache_read_input_tokens=0, cache_creation_input_tokens=0)

    def __add__(self, other: TokenCounts) -> TokenCounts:
        return TokenCounts(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + other.cache_read_input_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens + other.cache_creation_input_tokens,
        )


class ToolCall(BaseModel):
    """A single tool call extracted from a provider response."""

    model_config = _frozen()

    name: str
    args: dict[str, Any]
    tool_use_id: str


class AssistantTurn(BaseModel):
    """spec §4.4 BR2-07: keep provider's content blocks intact for re-send.

    Phase 3a only stores them; thinking-block byte-identical re-send is 3b's job.
    """

    model_config = _frozen()

    provider: str
    blocks: tuple[dict[str, Any], ...]
    role: Literal["assistant"] = "assistant"


class LLMResponse(BaseModel):
    """Wire-level provider response, normalized for ReAct loop consumption."""

    model_config = _frozen()

    provider: str
    model: str
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "stop_sequence", "other"]
    tool_calls: tuple[ToolCall, ...]
    text_content: str
    tokens: TokenCounts
    raw_assistant_turn: AssistantTurn


class IterationRecord(BaseModel):
    """spec §4.3: one per ReAct loop iteration. Written into agent_view_snapshots."""

    model_config = _frozen()

    step: int
    request_messages_digest: str
    provider_response_kind: Literal["tool_use", "text_only", "error", "no_tool"]
    tool_call: ToolCall | None
    text_content: str
    tokens: TokenCounts
    wall_time_ms: int


class ApiErrorInfo(BaseModel):
    model_config = _frozen()

    type: str
    detail: str


class TurnDecisionResult(BaseModel):
    """spec §4.1: complete decision record returned by Agent.decide()."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, arbitrary_types_allowed=True,
    )

    iterations: tuple[IterationRecord, ...]
    final_action: Action | None
    total_tokens: TokenCounts
    wall_time_ms: int

    api_retry_count: int
    illegal_action_retry_count: int
    no_tool_retry_count: int
    tool_usage_error_count: int

    default_action_fallback: bool
    api_error: ApiErrorInfo | None
    turn_timeout_exceeded: bool

    @model_validator(mode="after")
    def _api_error_forbids_action(self) -> Self:
        """spec §4.1 BR2-01: api_error != None ⇒ final_action == None."""
        if self.api_error is not None and self.final_action is not None:
            raise ValueError(
                "final_action must be None when api_error is set "
                "(spec §4.1 BR2-01: censor hand on api_error)"
            )
        return self

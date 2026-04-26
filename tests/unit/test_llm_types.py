"""Tests for LLM agent dataclass schemas (Phase 3a)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from llm_poker_arena.agents.llm.types import (
    ApiErrorInfo,
    AssistantTurn,
    IterationRecord,
    LLMResponse,
    TokenCounts,
    ToolCall,
    TurnDecisionResult,
)
from llm_poker_arena.engine.legal_actions import Action


def test_token_counts_zero_default() -> None:
    z = TokenCounts.zero()
    assert z.input_tokens == 0
    assert z.output_tokens == 0
    assert z.cache_read_input_tokens == 0
    assert z.cache_creation_input_tokens == 0


def test_token_counts_addition() -> None:
    a = TokenCounts(
        input_tokens=10, output_tokens=20, cache_read_input_tokens=5, cache_creation_input_tokens=0
    )
    b = TokenCounts(
        input_tokens=3, output_tokens=4, cache_read_input_tokens=0, cache_creation_input_tokens=2
    )
    s = a + b
    assert s.input_tokens == 13
    assert s.output_tokens == 24
    assert s.cache_read_input_tokens == 5
    assert s.cache_creation_input_tokens == 2


def test_tool_call_round_trip() -> None:
    tc = ToolCall(name="fold", args={}, tool_use_id="toolu_01")
    assert ToolCall.model_validate(tc.model_dump()) == tc


def test_iteration_record_round_trip() -> None:
    ir = IterationRecord(
        step=1,
        request_messages_digest="sha256:abc",
        provider_response_kind="tool_use",
        tool_call=ToolCall(name="fold", args={}, tool_use_id="t1"),
        text_content="reasoning text",
        tokens=TokenCounts.zero(),
        wall_time_ms=42,
    )
    assert IterationRecord.model_validate(ir.model_dump()) == ir


def test_turn_decision_result_minimal_with_action() -> None:
    r = TurnDecisionResult(
        iterations=(),
        final_action=Action(tool_name="fold", args={}),
        total_tokens=TokenCounts.zero(),
        wall_time_ms=10,
        api_retry_count=0,
        illegal_action_retry_count=0,
        no_tool_retry_count=0,
        tool_usage_error_count=0,
        default_action_fallback=False,
        api_error=None,
        turn_timeout_exceeded=False,
    )
    assert r.final_action is not None
    assert r.final_action.tool_name == "fold"


def test_turn_decision_result_api_error_forbids_final_action() -> None:
    """spec §4.1 BR2-01: api_error != None ⇒ final_action == None."""
    with pytest.raises(ValidationError, match="final_action must be None"):
        TurnDecisionResult(
            iterations=(),
            final_action=Action(tool_name="fold", args={}),
            total_tokens=TokenCounts.zero(),
            wall_time_ms=0,
            api_retry_count=1,
            illegal_action_retry_count=0,
            no_tool_retry_count=0,
            tool_usage_error_count=0,
            default_action_fallback=False,
            api_error=ApiErrorInfo(type="ProviderTransient", detail="500"),
            turn_timeout_exceeded=False,
        )


def test_turn_decision_result_both_action_and_error_none_forbidden() -> None:
    """spec §4.1 BR2-01 (reverse direction): api_error is None AND
    final_action is None is an inconsistent state — agent must return
    either an action or an error, never neither."""
    with pytest.raises(ValidationError, match="cannot both be None"):
        TurnDecisionResult(
            iterations=(),
            final_action=None,
            total_tokens=TokenCounts.zero(),
            wall_time_ms=0,
            api_retry_count=0,
            illegal_action_retry_count=0,
            no_tool_retry_count=0,
            tool_usage_error_count=0,
            default_action_fallback=False,
            api_error=None,
            turn_timeout_exceeded=False,
        )


def test_turn_decision_result_is_frozen() -> None:
    r = TurnDecisionResult(
        iterations=(),
        final_action=Action(tool_name="check", args={}),
        total_tokens=TokenCounts.zero(),
        wall_time_ms=0,
        api_retry_count=0,
        illegal_action_retry_count=0,
        no_tool_retry_count=0,
        tool_usage_error_count=0,
        default_action_fallback=False,
        api_error=None,
        turn_timeout_exceeded=False,
    )
    with pytest.raises(ValidationError):
        r.wall_time_ms = 999


def test_assistant_turn_preserves_blocks() -> None:
    """spec §4.4 BR2-07: assistant turn blocks must remain a tuple of opaque dicts."""
    at = AssistantTurn(
        provider="anthropic",
        blocks=({"type": "text", "text": "hi"},),
    )
    assert at.role == "assistant"
    assert at.blocks[0]["type"] == "text"


def test_llm_response_round_trip() -> None:
    resp = LLMResponse(
        provider="anthropic",
        model="claude-haiku-4-5",
        stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t1"),),
        text_content="",
        tokens=TokenCounts(
            input_tokens=100,
            output_tokens=10,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        raw_assistant_turn=AssistantTurn(provider="anthropic", blocks=()),
    )
    assert LLMResponse.model_validate(resp.model_dump()) == resp


def test_turn_decision_result_json_round_trip() -> None:
    """End-to-end: TurnDecisionResult → JSON → back. Action is a stdlib
    dataclass (not a Pydantic BaseModel), so this proves Pydantic v2's
    dataclass-as-field-type serialization holds for the union with None."""
    r = TurnDecisionResult(
        iterations=(
            IterationRecord(
                step=1,
                request_messages_digest="sha256:abc123",
                provider_response_kind="tool_use",
                tool_call=ToolCall(name="raise_to", args={"amount": 300}, tool_use_id="t1"),
                text_content="reasoning",
                tokens=TokenCounts(
                    input_tokens=50,
                    output_tokens=20,
                    cache_read_input_tokens=10,
                    cache_creation_input_tokens=0,
                ),
                wall_time_ms=120,
            ),
        ),
        final_action=Action(tool_name="raise_to", args={"amount": 300}),
        total_tokens=TokenCounts(
            input_tokens=50,
            output_tokens=20,
            cache_read_input_tokens=10,
            cache_creation_input_tokens=0,
        ),
        wall_time_ms=120,
        api_retry_count=0,
        illegal_action_retry_count=0,
        no_tool_retry_count=0,
        tool_usage_error_count=0,
        default_action_fallback=False,
        api_error=None,
        turn_timeout_exceeded=False,
    )
    blob = r.model_dump_json()
    restored = TurnDecisionResult.model_validate_json(blob)
    assert restored == r


def test_turn_decision_result_json_round_trip_with_api_error() -> None:
    """Censor path: api_error set, final_action=None, must round-trip cleanly."""
    r = TurnDecisionResult(
        iterations=(),
        final_action=None,
        total_tokens=TokenCounts.zero(),
        wall_time_ms=42,
        api_retry_count=1,
        illegal_action_retry_count=0,
        no_tool_retry_count=0,
        tool_usage_error_count=0,
        default_action_fallback=False,
        api_error=ApiErrorInfo(type="ProviderTransientError", detail="503"),
        turn_timeout_exceeded=False,
    )
    blob = r.model_dump_json()
    restored = TurnDecisionResult.model_validate_json(blob)
    assert restored == r
    assert restored.final_action is None
    assert restored.api_error is not None


def test_reasoning_artifact_kind_enum_values() -> None:
    from llm_poker_arena.agents.llm.types import ReasoningArtifactKind

    assert ReasoningArtifactKind.RAW.value == "raw"
    assert ReasoningArtifactKind.SUMMARY.value == "summary"
    assert ReasoningArtifactKind.THINKING_BLOCK.value == "thinking_block"
    assert ReasoningArtifactKind.ENCRYPTED.value == "encrypted"
    assert ReasoningArtifactKind.REDACTED.value == "redacted"
    assert ReasoningArtifactKind.UNAVAILABLE.value == "unavailable"


def test_reasoning_artifact_round_trip() -> None:
    from llm_poker_arena.agents.llm.types import (
        ReasoningArtifact,
        ReasoningArtifactKind,
    )

    art = ReasoningArtifact(
        kind=ReasoningArtifactKind.RAW,
        content="Let me think about pot odds...",
        provider_raw_index=2,
    )
    blob = art.model_dump_json()
    art2 = ReasoningArtifact.model_validate_json(blob)
    assert art2 == art
    # Encrypted variant: content is opaque base64-ish string.
    enc = ReasoningArtifact(
        kind=ReasoningArtifactKind.ENCRYPTED,
        content="cipher_payload_base64==",
        provider_raw_index=0,
    )
    assert ReasoningArtifact.model_validate_json(enc.model_dump_json()) == enc
    # Unavailable: content is None, index is None.
    none_art = ReasoningArtifact(
        kind=ReasoningArtifactKind.UNAVAILABLE,
        content=None,
        provider_raw_index=None,
    )
    assert ReasoningArtifact.model_validate_json(none_art.model_dump_json()) == none_art


def test_observed_capability_round_trip() -> None:
    from llm_poker_arena.agents.llm.types import (
        ObservedCapability,
        ReasoningArtifactKind,
    )

    cap = ObservedCapability(
        provider="anthropic",
        probed_at="2026-04-25T10:00:00Z",
        reasoning_kinds=(ReasoningArtifactKind.THINKING_BLOCK, ReasoningArtifactKind.ENCRYPTED),
        seed_accepted=False,
        tool_use_with_thinking_ok=False,
        extra_flags={"system_fingerprint_returned": False},
    )
    blob = cap.model_dump_json()
    cap2 = ObservedCapability.model_validate_json(blob)
    assert cap2 == cap


def test_iteration_record_default_reasoning_artifacts_is_empty_tuple() -> None:
    rec = IterationRecord(
        step=1,
        request_messages_digest="sha256:abcd",
        provider_response_kind="tool_use",
        tool_call=None,
        text_content="thinking",
        tokens=TokenCounts.zero(),
        wall_time_ms=42,
    )
    assert rec.reasoning_artifacts == ()


def test_iteration_record_with_reasoning_artifacts_round_trip() -> None:
    from llm_poker_arena.agents.llm.types import (
        ReasoningArtifact,
        ReasoningArtifactKind,
    )

    arts = (
        ReasoningArtifact(
            kind=ReasoningArtifactKind.THINKING_BLOCK,
            content="step 1 of CoT",
            provider_raw_index=0,
        ),
        ReasoningArtifact(
            kind=ReasoningArtifactKind.ENCRYPTED,
            content="opaque_blob",
            provider_raw_index=1,
        ),
    )
    rec = IterationRecord(
        step=2,
        request_messages_digest="sha256:1234",
        provider_response_kind="tool_use",
        tool_call=None,
        text_content="surface answer",
        tokens=TokenCounts.zero(),
        wall_time_ms=99,
        reasoning_artifacts=arts,
    )
    blob = rec.model_dump_json()
    rec2 = IterationRecord.model_validate_json(blob)
    assert rec2 == rec
    assert len(rec2.reasoning_artifacts) == 2
    assert rec2.reasoning_artifacts[0].kind == ReasoningArtifactKind.THINKING_BLOCK


def test_iteration_record_default_tool_result_is_none() -> None:
    rec = IterationRecord(
        step=1,
        request_messages_digest="sha256:x",
        provider_response_kind="tool_use",
        tool_call=ToolCall(name="fold", args={}, tool_use_id="t1"),
        text_content="r",
        tokens=TokenCounts.zero(),
        wall_time_ms=10,
    )
    assert rec.tool_result is None


def test_iteration_record_with_tool_result_round_trip() -> None:
    rec = IterationRecord(
        step=2,
        request_messages_digest="sha256:y",
        provider_response_kind="tool_use",
        tool_call=ToolCall(name="pot_odds", args={"to_call": 100, "pot": 250}, tool_use_id="tu_a"),
        text_content="checking pot odds",
        tokens=TokenCounts.zero(),
        wall_time_ms=42,
        tool_result={"value": 0.2857142857142857},
    )
    blob = rec.model_dump_json()
    rec2 = IterationRecord.model_validate_json(blob)
    assert rec2 == rec
    assert rec2.tool_result == {"value": 0.2857142857142857}


def test_equity_result_round_trip() -> None:
    from llm_poker_arena.agents.llm.types import EquityResult

    er = EquityResult(
        hero_equity=0.4523,
        ci_low=0.4385,
        ci_high=0.4661,
        n_samples=5000,
        seed=12345,
        backend="eval7",
    )
    blob = er.model_dump_json()
    er2 = EquityResult.model_validate_json(blob)
    assert er2 == er
    assert er2.backend == "eval7"


def test_equity_result_validates_equity_range() -> None:
    """hero_equity must be in [0, 1]."""
    from llm_poker_arena.agents.llm.types import EquityResult

    with pytest.raises(ValidationError):
        EquityResult(
            hero_equity=1.5, ci_low=0.0, ci_high=1.0, n_samples=5000, seed=0, backend="eval7"
        )
    with pytest.raises(ValidationError):
        EquityResult(
            hero_equity=-0.1, ci_low=0.0, ci_high=1.0, n_samples=5000, seed=0, backend="eval7"
        )

"""Unit tests for provider-specific reasoning artifact extraction + byte-identical
thinking-block preservation across replay."""
from __future__ import annotations

from typing import Any

from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    ReasoningArtifactKind,
    TokenCounts,
    ToolCall,
)


def _resp_with_thinking_blocks() -> LLMResponse:
    """Fake Anthropic response carrying extended-thinking blocks. The blocks
    have provider-specific shape (signature, etc.) that MUST round-trip.
    """
    return LLMResponse(
        provider="anthropic", model="claude-opus-4-7",
        stop_reason="tool_use",
        tool_calls=(
            ToolCall(name="fold", args={}, tool_use_id="toolu_x"),
        ),
        text_content="My final answer: fold.",
        tokens=TokenCounts(input_tokens=10, output_tokens=20,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic",
            blocks=(
                {
                    "type": "thinking",
                    "thinking": "Step 1: pot is 150, I have 72o, fold is correct.",
                    "signature": "sig_step1_payload_base64==",
                },
                {
                    "type": "redacted_thinking",
                    "data": "redacted_payload_base64==",
                },
                {
                    "type": "text",
                    "text": "My final answer: fold.",
                },
                {
                    "type": "tool_use",
                    "id": "toolu_x",
                    "name": "fold",
                    "input": {},
                },
            ),
        ),
    )


def test_anthropic_extract_reasoning_artifact_returns_thinking_and_redacted() -> None:
    provider = AnthropicProvider(model="claude-opus-4-7", api_key="sk-test")
    arts = provider.extract_reasoning_artifact(_resp_with_thinking_blocks())
    assert isinstance(arts, tuple)
    assert len(arts) == 2
    a0, a1 = arts
    assert a0.kind == ReasoningArtifactKind.THINKING_BLOCK
    assert a0.content == "Step 1: pot is 150, I have 72o, fold is correct."
    assert a0.provider_raw_index == 0
    assert a1.kind == ReasoningArtifactKind.REDACTED
    # Per spec §4.6, redacted_thinking has no plaintext rationale — content is
    # None. The opaque `data` field stays in raw_assistant_turn.blocks for
    # forensic access (and is preserved byte-identical across replay so the
    # next API call accepts it), but it's NOT exposed as human-readable text.
    assert a1.content is None
    assert a1.provider_raw_index == 1


def test_anthropic_extract_returns_empty_tuple_when_no_thinking_blocks() -> None:
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    plain = LLMResponse(
        provider="anthropic", model="claude-haiku-4-5",
        stop_reason="end_turn", tool_calls=(),
        text_content="ok", tokens=TokenCounts.zero(),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic",
            blocks=({"type": "text", "text": "ok"},),
        ),
    )
    arts = provider.extract_reasoning_artifact(plain)
    assert arts == ()


def test_anthropic_serialize_assistant_turn_preserves_thinking_blocks_byte_identical() -> None:
    """spec §4.4 BR2-07: thinking blocks must round-trip identically when we
    re-send the assistant turn in the next ReAct iteration."""
    provider = AnthropicProvider(model="claude-opus-4-7", api_key="sk-test")
    resp = _resp_with_thinking_blocks()
    msg = provider.build_assistant_message_for_replay(resp)
    # The blocks list inside the constructed message must be IDENTICAL to
    # the raw blocks tuple — not a re-projection that drops fields.
    assert msg["content"] == list(resp.raw_assistant_turn.blocks)
    # In particular, thinking block's `signature` field is preserved (this
    # is what Anthropic uses to validate the thinking block on next request).
    thinking_block = next(b for b in msg["content"] if b["type"] == "thinking")
    assert thinking_block["signature"] == "sig_step1_payload_base64=="
    redacted = next(b for b in msg["content"] if b["type"] == "redacted_thinking")
    assert redacted["data"] == "redacted_payload_base64=="


def test_anthropic_encrypted_thinking_kind_classified_correctly() -> None:
    """Some Anthropic releases use `encrypted_thinking` instead of
    redacted_thinking. Both have opaque content; we map them to the
    appropriate ReasoningArtifactKind per spec §4.6."""
    provider = AnthropicProvider(model="claude-opus-4-7", api_key="sk-test")
    resp = LLMResponse(
        provider="anthropic", model="claude-opus-4-7",
        stop_reason="end_turn", tool_calls=(),
        text_content="", tokens=TokenCounts.zero(),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic",
            blocks=(
                {"type": "encrypted_thinking",
                 "data": "encrypted_blob=="},
            ),
        ),
    )
    arts = provider.extract_reasoning_artifact(resp)
    assert len(arts) == 1
    assert arts[0].kind == ReasoningArtifactKind.ENCRYPTED
    assert arts[0].content == "encrypted_blob=="


def test_anthropic_normalize_preserves_real_thinking_block_signature() -> None:
    """End-to-end: build a real Anthropic-SDK ThinkingBlock, run it through
    `_normalize()`, and verify the normalized AssistantTurn.blocks dict
    preserves the `signature` field that Anthropic uses to validate the
    thinking block on the next request. This catches the case where
    `model_dump()` would drop SDK-specific fields — codex audit NIT-N2."""
    from anthropic.types import (
        TextBlock,
        ThinkingBlock,
        ToolUseBlock,
        Usage,
    )

    class _FakeAnthropicResp:
        model = "claude-opus-4-7"
        stop_reason = "tool_use"
        # Construct real SDK block instances. Pydantic round-trip via
        # model_dump() must preserve `signature` and `thinking` fields.
        content: list[Any] = [
            ThinkingBlock(
                type="thinking",
                thinking="Considering pot odds...",
                signature="real_sdk_sig_payload==",
            ),
            TextBlock(type="text", text="Final answer.", citations=None),
            ToolUseBlock(type="tool_use", id="toolu_real",
                         name="fold", input={}),
        ]
        usage = Usage(input_tokens=10, output_tokens=5)

    provider = AnthropicProvider(model="claude-opus-4-7", api_key="sk-test")
    resp = provider._normalize(_FakeAnthropicResp())  # noqa: SLF001
    # The normalized blocks tuple must contain the thinking block dict
    # WITH the `signature` field intact — otherwise the next API call
    # would fail Anthropic's thinking-block validation.
    thinking_dump = next(
        b for b in resp.raw_assistant_turn.blocks if b.get("type") == "thinking"
    )
    assert thinking_dump["thinking"] == "Considering pot odds..."
    assert thinking_dump["signature"] == "real_sdk_sig_payload=="
    # And extract_reasoning_artifact lifts it correctly.
    arts = provider.extract_reasoning_artifact(resp)
    assert len(arts) == 1
    assert arts[0].kind == ReasoningArtifactKind.THINKING_BLOCK
    assert arts[0].content == "Considering pot odds..."

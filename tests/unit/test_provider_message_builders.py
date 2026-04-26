"""Provider must own the message-format wire details. Test contract per provider."""

from __future__ import annotations

from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    TokenCounts,
    ToolCall,
)


def _resp_with_text_and_tool() -> LLMResponse:
    return LLMResponse(
        provider="anthropic",
        model="claude-haiku-4-5",
        stop_reason="tool_use",
        tool_calls=(ToolCall(name="raise_to", args={"amount": 300}, tool_use_id="toolu_abc"),),
        text_content="Reasoning: I have AKs and good fold equity.",
        tokens=TokenCounts(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic",
            blocks=(
                {"type": "text", "text": "Reasoning: I have AKs and good fold equity."},
                {
                    "type": "tool_use",
                    "id": "toolu_abc",
                    "name": "raise_to",
                    "input": {"amount": 300},
                },
            ),
        ),
    )


def test_anthropic_build_assistant_message_for_replay_uses_raw_blocks() -> None:
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    msg = provider.build_assistant_message_for_replay(_resp_with_text_and_tool())
    assert msg["role"] == "assistant"
    assert isinstance(msg["content"], list)
    assert msg["content"][0]["type"] == "text"
    assert msg["content"][1]["type"] == "tool_use"
    assert msg["content"][1]["id"] == "toolu_abc"


def test_anthropic_build_tool_result_messages_returns_single_user_message() -> None:
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    tcs = (ToolCall(name="raise_to", args={"amount": 300}, tool_use_id="toolu_abc"),)
    msgs = provider.build_tool_result_messages(
        tool_calls=tcs,
        is_error=True,
        content="Illegal: not in legal set",
    )
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert msg["content"][0]["type"] == "tool_result"
    assert msg["content"][0]["tool_use_id"] == "toolu_abc"
    assert msg["content"][0]["is_error"] is True


def test_anthropic_build_tool_result_messages_covers_every_tool_use_id() -> None:
    """If the assistant turn had 2 tool_use blocks, we MUST emit 2 tool_result
    blocks in the SAME user message — Anthropic API requires every prior
    tool_use_id to be answered."""
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    tcs = (
        ToolCall(name="fold", args={}, tool_use_id="toolu_aaa"),
        ToolCall(name="raise_to", args={"amount": 300}, tool_use_id="toolu_bbb"),
    )
    msgs = provider.build_tool_result_messages(
        tool_calls=tcs,
        is_error=True,
        content="Multi-tool calls not allowed; pick one.",
    )
    assert len(msgs) == 1
    blocks = msgs[0]["content"]
    assert {b["tool_use_id"] for b in blocks} == {"toolu_aaa", "toolu_bbb"}


def test_anthropic_build_user_text_message_returns_plain_user() -> None:
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    msg = provider.build_user_text_message("You must call exactly one tool.")
    assert msg == {"role": "user", "content": "You must call exactly one tool."}


def test_mock_provider_implements_same_3_builders() -> None:
    """MockLLMProvider in tests must satisfy the ABC so existing 23 ReAct
    unit tests keep working without touching them."""
    mock = MockLLMProvider(script=MockResponseScript(responses=()))
    # All three methods must exist and return the right shapes (mirrors
    # Anthropic semantics — tests never inspect the inner shape).
    assert callable(mock.build_assistant_message_for_replay)
    assert callable(mock.build_tool_result_messages)
    assert callable(mock.build_user_text_message)
    msg = mock.build_user_text_message("hi")
    assert msg == {"role": "user", "content": "hi"}

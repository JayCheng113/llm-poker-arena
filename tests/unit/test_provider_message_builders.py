"""Provider must own the message-format wire details. Test contract per provider."""

from __future__ import annotations

from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.llm.providers.openai_compatible import (
    OpenAICompatibleProvider,
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


def _resp_with_reasoning_content(provider_name: str) -> LLMResponse:
    """Mimics what an OpenAI-compatible provider's _normalize() emits when
    the upstream response carries `reasoning_content` (DeepSeek thinking
    mode, OpenAI o-series)."""
    return LLMResponse(
        provider=provider_name,
        model="deepseek-v4-flash",
        stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="call_abc"),),
        text_content="folding the weak hand",
        tokens=TokenCounts(
            input_tokens=10, output_tokens=5,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        ),
        raw_assistant_turn=AssistantTurn(
            provider=provider_name,
            blocks=({
                "role": "assistant",
                "content": "folding the weak hand",
                "reasoning_content": "Internal CoT: the pot odds don't justify continuing here.",
                "tool_calls": [{
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "fold", "arguments": "{}"},
                }],
            },),
        ),
    )


def test_deepseek_replay_keeps_reasoning_content() -> None:
    """DeepSeek thinking mode (v4-flash) requires reasoning_content to be
    round-tripped on subsequent multi-turn calls — otherwise: 400
    invalid_request_error. See the apiyi/deepseek docs from April 2026."""
    provider = OpenAICompatibleProvider(
        provider_name_value="deepseek",
        model="deepseek-v4-flash",
        api_key="sk-test",
        base_url="https://api.deepseek.com/v1",
    )
    msg = provider.build_assistant_message_for_replay(
        _resp_with_reasoning_content("deepseek")
    )
    assert "reasoning_content" in msg, (
        "DeepSeek must preserve reasoning_content in replay messages — "
        "stripping it makes thinking-mode multi-turn fail with 400."
    )
    assert "Internal CoT" in msg["reasoning_content"]


def test_replay_normalizes_empty_assistant_content_with_tool_calls() -> None:
    """Kimi (api.moonshot.cn) rejects {role: assistant, content: null,
    tool_calls: [...]} with 400 'message at position N with role assistant
    must not be empty'. OpenAI/DeepSeek accept null content fine. Our
    normalizer replaces null/empty with a single space whenever tool_calls
    are present, keeping all providers happy."""
    response = LLMResponse(
        provider="kimi",
        model="kimi-k2.5",
        stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="call_x"),),
        text_content="",
        tokens=TokenCounts(input_tokens=0, output_tokens=0,
                           cache_read_input_tokens=0, cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(
            provider="kimi",
            blocks=({
                "role": "assistant",
                "content": None,    # the null Kimi rejects
                "tool_calls": [{
                    "id": "call_x", "type": "function",
                    "function": {"name": "fold", "arguments": "{}"},
                }],
            },),
        ),
    )
    provider = OpenAICompatibleProvider(
        provider_name_value="kimi",
        model="kimi-k2.5",
        api_key="sk-test",
        base_url="https://api.moonshot.cn/v1",
    )
    msg = provider.build_assistant_message_for_replay(response)
    assert msg["content"] == " ", (
        "empty assistant content with tool_calls must be normalized to a single "
        "space so Kimi accepts the multi-turn replay."
    )
    assert msg["tool_calls"][0]["function"]["name"] == "fold"


def test_openai_replay_strips_reasoning_content() -> None:
    """For non-DeepSeek OpenAI-compatible providers, reasoning_content is
    informational only — strip it so the wire payload stays minimal."""
    provider = OpenAICompatibleProvider(
        provider_name_value="openai",
        model="gpt-5.4-mini",
        api_key="sk-test",
    )
    msg = provider.build_assistant_message_for_replay(
        _resp_with_reasoning_content("openai")
    )
    assert "reasoning_content" not in msg


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

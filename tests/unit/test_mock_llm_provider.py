"""Tests for MockLLMProvider — preset-driven LLM stub for ReAct loop tests."""

from __future__ import annotations

import pytest

from llm_poker_arena.agents.llm.provider_base import (
    LLMProvider,
    ProviderTransientError,
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


@pytest.mark.asyncio
async def test_mock_provider_returns_scripted_responses_in_order() -> None:
    script = MockResponseScript(
        responses=(
            LLMResponse(
                provider="mock",
                model="m1",
                stop_reason="tool_use",
                tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t1"),),
                text_content="",
                tokens=TokenCounts.zero(),
                raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
            ),
            LLMResponse(
                provider="mock",
                model="m1",
                stop_reason="tool_use",
                tool_calls=(ToolCall(name="check", args={}, tool_use_id="t2"),),
                text_content="",
                tokens=TokenCounts.zero(),
                raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
            ),
        )
    )
    p = MockLLMProvider(script=script)
    r1 = await p.complete(messages=[], tools=[], temperature=0.7, seed=None)
    r2 = await p.complete(messages=[], tools=[], temperature=0.7, seed=None)
    assert r1.tool_calls[0].name == "fold"
    assert r2.tool_calls[0].name == "check"


@pytest.mark.asyncio
async def test_mock_provider_raises_when_script_exhausted() -> None:
    script = MockResponseScript(responses=())
    p = MockLLMProvider(script=script)
    with pytest.raises(RuntimeError, match="exhausted"):
        await p.complete(messages=[], tools=[], temperature=0.7, seed=None)


@pytest.mark.asyncio
async def test_mock_provider_raises_transient_error_when_scripted() -> None:
    script = MockResponseScript(
        responses=(),
        errors_at_step={0: ProviderTransientError("simulated 500")},
    )
    p = MockLLMProvider(script=script)
    with pytest.raises(ProviderTransientError, match="simulated 500"):
        await p.complete(messages=[], tools=[], temperature=0.7, seed=None)


@pytest.mark.asyncio
async def test_mock_provider_provider_name() -> None:
    script = MockResponseScript(responses=())
    p = MockLLMProvider(script=script)
    assert p.provider_name() == "mock"


def test_mock_provider_is_an_llm_provider() -> None:
    """Type check: MockLLMProvider implements LLMProvider ABC."""
    script = MockResponseScript(responses=())
    p = MockLLMProvider(script=script)
    assert isinstance(p, LLMProvider)

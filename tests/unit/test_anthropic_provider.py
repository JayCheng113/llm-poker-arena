"""Tests for AnthropicProvider — Anthropic SDK adapter.

Unit tests monkeypatch `anthropic.AsyncAnthropic` so no network calls happen.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_poker_arena.agents.llm.provider_base import (
    ProviderPermanentError,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)


def _fake_anthropic_response(
    *,
    stop_reason: str = "tool_use",
    content_blocks: list[Any] | None = None,
    input_tokens: int = 100,
    output_tokens: int = 25,
) -> MagicMock:
    """Build a MagicMock that quacks like anthropic.types.Message."""
    msg = MagicMock()
    msg.stop_reason = stop_reason
    msg.model = "claude-haiku-4-5"
    msg.content = content_blocks or []
    msg.usage = MagicMock(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return msg


@pytest.mark.asyncio
async def test_anthropic_provider_normalizes_tool_use_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "fold"
    tool_block.input = {}
    tool_block.id = "toolu_01abc"
    tool_block.model_dump = lambda: {
        "type": "tool_use",
        "name": "fold",
        "input": {},
        "id": "toolu_01abc",
    }
    fake = _fake_anthropic_response(content_blocks=[tool_block])

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake)
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    resp = await p.complete(
        messages=[{"role": "user", "content": "play"}],
        tools=[{"name": "fold", "description": "fold", "input_schema": {"type": "object"}}],
        temperature=0.7,
        seed=None,
    )
    assert resp.provider == "anthropic"
    assert resp.stop_reason == "tool_use"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "fold"
    assert resp.tool_calls[0].tool_use_id == "toolu_01abc"
    assert resp.tokens.input_tokens == 100
    assert resp.tokens.output_tokens == 25


@pytest.mark.asyncio
async def test_anthropic_provider_normalizes_text_only_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I think I should fold here."
    text_block.model_dump = lambda: {"type": "text", "text": "I think I should fold here."}
    fake = _fake_anthropic_response(stop_reason="end_turn", content_blocks=[text_block])

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake)
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    resp = await p.complete(
        messages=[{"role": "user", "content": "play"}],
        tools=[],
        temperature=0.7,
        seed=None,
    )
    assert resp.stop_reason == "end_turn"
    assert resp.tool_calls == ()
    assert "fold" in resp.text_content


@pytest.mark.asyncio
async def test_anthropic_provider_translates_503_to_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anthropic

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(
        side_effect=anthropic.APIStatusError(
            "503 service unavailable",
            response=MagicMock(status_code=503),
            body=None,
        )
    )
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    with pytest.raises(ProviderTransientError):
        await p.complete(messages=[], tools=[], temperature=0.7, seed=None)


@pytest.mark.asyncio
async def test_anthropic_provider_translates_400_to_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anthropic

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(
        side_effect=anthropic.APIStatusError(
            "400 invalid request",
            response=MagicMock(status_code=400),
            body=None,
        )
    )
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    with pytest.raises(ProviderPermanentError):
        await p.complete(messages=[], tools=[], temperature=0.7, seed=None)


def test_anthropic_provider_provider_name() -> None:
    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    assert p.provider_name() == "anthropic"


@pytest.mark.asyncio
async def test_anthropic_provider_threads_system_param_to_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 3d: system kwarg must reach SDK as messages.create(system=...).
    Phase 3a folded system into user message which wastes tokens + breaks
    prompt caching."""
    captured: dict[str, Any] = {}

    async def fake_create(**kw: Any) -> Any:
        captured.update(kw)
        return _fake_anthropic_response(content_blocks=[])

    fake_client = MagicMock()
    fake_client.messages.create = fake_create
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    await p.complete(
        system="You are a poker bot.",
        messages=[{"role": "user", "content": "play"}],
        tools=[],
        temperature=0.7,
        seed=None,
    )
    # System prompt is wrapped as a structured block with cache_control
    # so Anthropic's prompt cache treats it as a stable boundary across
    # turns (every call after the first becomes a cache_read at 10% cost).
    assert captured["system"] == [
        {
            "type": "text",
            "text": "You are a poker bot.",
            "cache_control": {"type": "ephemeral"},
        }
    ]


@pytest.mark.asyncio
async def test_anthropic_provider_omits_system_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """system=None ⇒ no `system` key passed to SDK."""
    captured: dict[str, Any] = {}

    async def fake_create(**kw: Any) -> Any:
        captured.update(kw)
        return _fake_anthropic_response(content_blocks=[])

    fake_client = MagicMock()
    fake_client.messages.create = fake_create
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    await p.complete(
        system=None,
        messages=[{"role": "user", "content": "play"}],
        tools=[],
        temperature=0.7,
        seed=None,
    )
    assert "system" not in captured

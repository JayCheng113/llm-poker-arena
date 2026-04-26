"""Test AnthropicProvider.probe() with a fake SDK response. No network."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.llm.types import (
    ObservedCapability,
    ReasoningArtifactKind,
)


class _FakeUsage:
    input_tokens = 5
    output_tokens = 3
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _FakeBlock:
    def __init__(self, type_: str, text: str = "") -> None:
        self.type = type_
        self.text = text

    def model_dump(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type}
        if self.type == "text":
            d["text"] = self.text
        return d


class _FakeResp:
    model = "claude-haiku-4-5"
    stop_reason = "end_turn"
    content = [_FakeBlock("text", "ok")]
    usage = _FakeUsage()


def test_anthropic_probe_returns_observed_capability_with_seed_false() -> None:
    """Anthropic does not accept the `seed` kwarg; probe records seed_accepted=False
    statically. Reasoning_kinds=(UNAVAILABLE,) because we don't enable extended
    thinking — UNAVAILABLE explicitly signals 'tested, none seen' per spec §4.6."""
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    fake_create = AsyncMock(return_value=_FakeResp())
    provider._client = MagicMock()
    provider._client.messages = MagicMock()
    provider._client.messages.create = fake_create

    cap = asyncio.run(provider.probe())
    assert isinstance(cap, ObservedCapability)
    assert cap.provider == "anthropic"
    assert cap.seed_accepted is False
    assert cap.tool_use_with_thinking_ok is False
    # spec §4.6: probe observed no artifacts → (UNAVAILABLE,) not empty.
    assert cap.reasoning_kinds == (ReasoningArtifactKind.UNAVAILABLE,)
    # extra_flags must record that thinking + tool_use was NOT actually
    # tested (vs "tested and failed"). HR2-03 honest reporting.
    assert cap.extra_flags["tool_use_with_thinking_probed"] is False
    assert cap.extra_flags["extended_thinking_enabled"] is False
    # probed_at is an ISO timestamp; should parse-back without error.
    assert "T" in cap.probed_at
    assert cap.probed_at.endswith("Z")
    # The probe should have called the SDK exactly once with a minimal prompt.
    assert fake_create.await_count == 1
    assert fake_create.await_args is not None
    kwargs = fake_create.await_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs["max_tokens"] <= 32  # cheap probe
    assert "seed" not in kwargs  # we don't pass seed because Anthropic ignores it

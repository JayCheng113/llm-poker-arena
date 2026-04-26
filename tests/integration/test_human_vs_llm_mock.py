"""Full CLI session with HumanCLIAgent + mock LLM agents (Phase 4 Task 6).

Verifies the end-to-end wire: CLI argparse → build_agents (LLM specs) →
Session.run → meta.json + JSONL artifacts. Uses MockLLMProvider so no
real API calls.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from llm_poker_arena.cli.play import run_cli


def test_human_plus_anthropic_mock_session_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1 human (scripted stdin) + 1 mock anthropic + 4 bots; 6 hands; clean."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-mock")

    # Monkeypatch AnthropicProvider to be MockLLMProvider so we don't actually
    # call the API. The factory in build_agents instantiates AnthropicProvider —
    # we replace that class with a stub that returns a MockLLMProvider-backed
    # LLMResponse.
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

    def _fold(uid: str) -> LLMResponse:
        return LLMResponse(
            provider="anthropic", model="claude-haiku-4-5",
            stop_reason="tool_use",
            tool_calls=(ToolCall(name="fold", args={}, tool_use_id=uid),),
            text_content="folding",
            tokens=TokenCounts(input_tokens=50, output_tokens=10,
                               cache_read_input_tokens=0,
                               cache_creation_input_tokens=0),
            raw_assistant_turn=AssistantTurn(provider="anthropic", blocks=()),
        )

    script = MockResponseScript(responses=tuple(
        _fold(f"t{i}") for i in range(200)
    ))

    # Patch AnthropicProvider class within the cli.play module's _PROVIDER_TABLE.
    # The override MUST also have `provider_name() == "anthropic"` so that
    # LLMAgent.provider_id() emits "anthropic:claude-haiku-4-5" (matches
    # what real anthropic flow would produce; persisted to meta.json
    # seat_assignment).
    from llm_poker_arena.cli import play as play_mod

    class _MockAnthropic(MockLLMProvider):
        def __init__(self, *, model: str, api_key: str) -> None:
            super().__init__(script=script)

        def provider_name(self) -> str:
            return "anthropic"

    monkeypatch.setitem(
        play_mod._PROVIDER_TABLE, "anthropic",
        ("ANTHROPIC_API_KEY",
         lambda model, key: _MockAnthropic(model=model, api_key=key)),
    )

    # Cyclic stdin so human always has SOME legal action to pick.
    human_input = io.StringIO("call\ncheck\nfold\nall_in\n" * 100)
    human_output = io.StringIO()

    rc = run_cli(
        num_hands=6, my_seat=3, rng_seed=42,
        output_root=tmp_path,
        human_input=human_input, human_output=human_output,
        llm_specs=[("anthropic", "claude-haiku-4-5", 0)],
    )
    assert rc == 0

    session_dirs = list(tmp_path.glob("session_*"))
    assert len(session_dirs) == 1
    sd = session_dirs[0]
    meta = json.loads((sd / "meta.json").read_text())
    assert meta["total_hands_played"] == 6
    # seat 0 is mock-LLM with "anthropic" provider tag.
    assert meta["seat_assignment"]["0"] == "anthropic:claude-haiku-4-5"
    # seat 3 is human.
    assert meta["seat_assignment"]["3"] == "human:cli_v1"
    # Token aggregation populated for the LLM seat.
    assert meta["total_tokens"]["0"]["input_tokens"] > 0
    # chip P&L conservation.
    assert sum(meta["chip_pnl"].values()) == 0

"""Integration test: 6-hand session with MockLLMProvider-backed LLMAgents.

Asserts:
  - the run completes (no censor)
  - iterations data lands in agent_view_snapshots.jsonl
  - chip_pnl sums to zero (zero-sum game)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
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
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _fold_response(uid: str) -> LLMResponse:
    return LLMResponse(
        provider="mock", model="m", stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id=uid),),
        text_content="folding", tokens=TokenCounts(
            input_tokens=50, output_tokens=10,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        ),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


class _AlwaysFolds(LLMAgent):
    """LLMAgent whose mock provider returns 'fold' on every call."""

    def __init__(self) -> None:
        # 200 responses: way more than 6 hands × 6 seats × max_steps=4 needs.
        responses = tuple(_fold_response(f"t{i}") for i in range(200))
        provider = MockLLMProvider(script=MockResponseScript(responses=responses))
        super().__init__(provider=provider, model="m", temperature=0.7)


def test_six_hand_session_with_mock_llm_agents_completes(tmp_path: Path) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    agents = [_AlwaysFolds() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="llm_mock_test")
    asyncio.run(sess.run())

    # 6 hands written to canonical_private + public_replay.
    private = (tmp_path / "canonical_private.jsonl").read_text().strip().splitlines()
    assert len(private) == 6
    public = (tmp_path / "public_replay.jsonl").read_text().strip().splitlines()
    assert len(public) == 6

    # iterations must be populated for LLMAgent turns.
    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    assert len(snaps) >= 6  # at least one turn per hand
    rec0 = json.loads(snaps[0])
    assert rec0["iterations"], "iterations must be non-empty for LLMAgent turns"
    assert rec0["iterations"][0]["provider_response_kind"] == "tool_use"
    assert rec0["iterations"][0]["tool_call"]["name"] == "fold"
    assert rec0["total_tokens"]["input_tokens"] > 0

    # chip_pnl conservation: zero-sum.
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0

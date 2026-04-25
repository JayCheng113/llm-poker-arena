"""Real Anthropic API smoke test (gated, NOT in CI).

Run only when both env vars are set:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...

Costs ~$0.01-0.05 per run depending on prompt + max_tokens. Uses
claude-haiku-4-5 (cheapest) and 6 hands (validator min) but only seat 3
is the LLM; other seats are RandomAgent.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

pytestmark = pytest.mark.skipif(
    os.getenv("ANTHROPIC_INTEGRATION_TEST") != "1"
    or not os.getenv("ANTHROPIC_API_KEY"),
    reason="needs ANTHROPIC_INTEGRATION_TEST=1 and ANTHROPIC_API_KEY set",
)


def test_real_claude_haiku_plays_one_hand(tmp_path: Path) -> None:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,  # validator demands multiple of 6
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    llm_agent = LLMAgent(
        provider=provider, model="claude-haiku-4-5",
        temperature=0.7, total_turn_timeout_sec=60.0,
    )
    agents = [
        RandomAgent(),  # BTN
        RandomAgent(),  # SB
        RandomAgent(),  # BB
        llm_agent,      # UTG ← Claude
        RandomAgent(),  # HJ
        RandomAgent(),  # CO
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="real_anthropic_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps
                 if json.loads(line)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots found"
    rec = llm_snaps[0]
    assert rec["agent"]["provider"] == "anthropic"
    assert rec["agent"]["model"] == "claude-haiku-4-5"
    assert rec["iterations"], "no iterations recorded — provider plumbing broken"
    assert rec["total_tokens"]["input_tokens"] > 0
    assert rec["total_tokens"]["output_tokens"] > 0

    # Final action must be in the legal set at decision time.
    final = rec["final_action"]
    legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
    assert final["type"] in legal_names, (
        f"LLM picked {final['type']!r} but legal set was {legal_names}"
    )

    # chip_pnl conservation still holds.
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0

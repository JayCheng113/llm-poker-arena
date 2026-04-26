"""Real Anthropic K+1 with HUD tool enabled (gated, NOT in CI).

Run only when:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...

Cost ~$0.05 per run. 6 hands × 1 Claude Haiku 4.5 seat with HUD tool
exposed (insufficient sentinel for all opponents at 6 < 30 hands).

Wire-only assertions (codex IMPORTANT-5 pattern):
  - Session runs to completion
  - All seat-3 final_actions in legal set
  - chip_pnl conserves
  - meta.json provider_capabilities populated
  - Does NOT assert organic HUD tool use (0/22 baseline rate; HUD tool
    likely also unused organically — that's a behavior question for
    Phase 5+ if/when prompt-tuning is on the roadmap)
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


def test_real_claude_haiku_with_hud_enabled(tmp_path: Path) -> None:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=True,  # KEY — HUD tool exposed
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    llm = LLMAgent(provider=provider, model="claude-haiku-4-5",
                   temperature=0.7, total_turn_timeout_sec=60.0)
    agents = [
        RandomAgent(),  # 0 (BTN)
        RandomAgent(),  # 1 (SB)
        RandomAgent(),  # 2 (BB)
        llm,            # 3 (UTG) ← Claude
        RandomAgent(),  # 4 (HJ)
        RandomAgent(),  # 5 (CO)
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="real_anthropic_hud_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps
                 if json.loads(line)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots"

    # 1. Every final_action in legal set.
    for rec in llm_snaps:
        legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
        assert rec["final_action"]["type"] in legal_names

    # 2. chip_pnl conservation.
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0

    # 3. provider_capabilities populated for the LLM seat.
    caps = meta["provider_capabilities"]
    assert "3" in caps
    assert caps["3"]["provider"] == "anthropic"

    # 4. IF Claude actually called HUD tool, validate shape (no organic-use
    # assertion; baseline 0/22).
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc and tc["name"] == "get_opponent_stats":
                tr = it["tool_result"]
                assert tr is not None
                # Either insufficient=True (likely at 6 hands) OR error
                # (e.g. self-seat) OR populated stats (won't happen at <30
                # hands).
                assert "insufficient" in tr or "error" in tr or "vpip" in tr

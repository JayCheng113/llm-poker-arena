"""Real Anthropic K+1 with equity tool, multi-LLM (gated, NOT in CI).

Run only when:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...

Costs ~$0.04-0.08 per run with Claude Haiku 4.5 × 2 seats, 6 hands,
math tools (pot_odds + spr + hand_equity_vs_ranges) enabled.

Assertions are wire-correctness only (mirrors 3c-math gated test
following codex audit IMPORTANT-5):
  - Session runs to completion without crash
  - All seat-1 and seat-3 final_actions are in the legal set
  - meta.json provider_capabilities populated for both LLM seats
  - chip_pnl conserves
  - IF utility iterations appear (any of pot_odds/spr/equity), their
    tool_result has the expected shape

Frequency / behavior assertions belong in DuckDB analysis post-session.
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
    os.getenv("ANTHROPIC_INTEGRATION_TEST") != "1" or not os.getenv("ANTHROPIC_API_KEY"),
    reason="needs ANTHROPIC_INTEGRATION_TEST=1 and ANTHROPIC_API_KEY set",
)


def test_real_claude_haiku_two_llm_seats_with_equity_tool(tmp_path: Path) -> None:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    cfg = SessionConfig(
        num_players=6,
        starting_stack=10_000,
        sb=50,
        bb=100,
        num_hands=6,
        max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30,
        rng_seed=42,
    )
    provider_a = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    provider_b = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    llm_a = LLMAgent(
        provider=provider_a, model="claude-haiku-4-5", temperature=0.7, total_turn_timeout_sec=60.0
    )
    llm_b = LLMAgent(
        provider=provider_b, model="claude-haiku-4-5", temperature=0.7, total_turn_timeout_sec=60.0
    )
    agents = [
        RandomAgent(),  # seat 0 (BTN)
        llm_a,  # SB ← Claude
        RandomAgent(),  # BB
        llm_b,  # UTG ← Claude
        RandomAgent(),  # HJ
        RandomAgent(),  # CO
    ]
    sess = Session(
        config=cfg,
        agents=agents,
        output_dir=tmp_path,
        session_id="real_anthropic_math_equity_smoke",
    )
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_seats = {1, 3}
    llm_snaps = [json.loads(line) for line in snaps if json.loads(line)["seat"] in llm_seats]
    assert llm_snaps, "no LLM seat snapshots"

    # 1. Every final_action must be in the legal set (or default_safe_action).
    for rec in llm_snaps:
        final = rec["final_action"]
        legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
        assert final["type"] in legal_names, (
            f"seat {rec['seat']} final action {final!r} not in legal set {legal_names}"
        )

    # 2. IF any utility iteration appears (pot_odds, spr, OR equity),
    #    validate its shape.
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc and tc["name"] in ("pot_odds", "spr", "hand_equity_vs_ranges"):
                assert it["tool_result"] is not None, (
                    f"utility iteration without tool_result — dispatch broken ({tc['name']})"
                )
                # Each tool has its own result shape; verify minimally.
                if tc["name"] in ("pot_odds", "spr"):
                    has_value = "value" in it["tool_result"]
                    has_error = "error" in it["tool_result"]
                    assert has_value or has_error
                elif tc["name"] == "hand_equity_vs_ranges":
                    tr = it["tool_result"]
                    if "error" not in tr:
                        assert "hero_equity" in tr
                        assert tr["backend"] == "eval7"

    # 3. chip_pnl conservation (no censor / fallback regression on infra).
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0

    # 4. Provider capabilities populated for BOTH LLM seats (3b regression).
    caps = meta["provider_capabilities"]
    assert "1" in caps
    assert caps["1"]["provider"] == "anthropic"
    assert "3" in caps
    assert caps["3"]["provider"] == "anthropic"

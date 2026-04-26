"""Real Anthropic K+1 smoke test (gated, NOT in CI).

Run only when:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...

Costs ~$0.02-0.04 per run with Claude Haiku 4.5, 6 hands, math tools enabled.

Codex audit IMPORTANT-5 fix: this test does NOT require Claude to organically
call ≥1 utility tool. Anthropic API call shape (no tool_choice="any") makes
utility usage purely a model-behavior choice — Claude may rationally skip
utility tools when pot_odds_required is already in the user prompt.

Assertions are wire-correctness only:
  - Session runs to completion without crash
  - All seat-3 final_actions are in the legal set (or default_safe_action
    fallback fired, which is also legal)
  - meta.json provider_capabilities still populated (Phase 3b regression guard)
  - chip_pnl conserves
  - IF utility iterations appear, their tool_result has the expected shape

Frequency / behavior-driven assertions belong in DuckDB analysis post-session,
not in a gated wire test.
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


def test_real_claude_haiku_session_with_math_tools_completes(tmp_path: Path) -> None:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    cfg = SessionConfig(
        num_players=6,
        starting_stack=10_000,
        sb=50,
        bb=100,
        num_hands=6,
        max_utility_calls=5,
        enable_math_tools=True,  # the new flag under test
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30,
        rng_seed=42,
    )
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    llm_agent = LLMAgent(
        provider=provider,
        model="claude-haiku-4-5",
        temperature=0.7,
        total_turn_timeout_sec=60.0,
    )
    agents = [
        RandomAgent(),  # BTN
        RandomAgent(),  # SB
        RandomAgent(),  # BB
        llm_agent,  # UTG ← Claude with math tools
        RandomAgent(),  # HJ
        RandomAgent(),  # CO
    ]
    sess = Session(
        config=cfg, agents=agents, output_dir=tmp_path, session_id="real_anthropic_math_smoke"
    )
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps if json.loads(line)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots"

    # Wire-correctness assertions (codex audit IMPORTANT-5: no behavior
    # frequency requirement; Claude may rationally skip utility tools).

    # 1. Every final_action must be in the legal set (or default_safe_action,
    #    which is always legal). Same as Phase 3a's assertion shape.
    for rec in llm_snaps:
        final = rec["final_action"]
        legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
        assert final["type"] in legal_names, (
            f"final action {final!r} not in legal set {legal_names}"
        )

    # 2. IF any utility iteration appears, validate its shape.
    #    (Don't REQUIRE one to appear — that's behavior, not wiring.)
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc is not None and tc["name"] in ("pot_odds", "spr"):
                assert it["tool_result"] is not None, (
                    "utility iteration without tool_result — dispatch broken"
                )
                # tool_result should have "value" (success) or "error" (bad args).
                has_value = "value" in it["tool_result"]
                has_error = "error" in it["tool_result"]
                assert has_value or has_error, f"unexpected tool_result shape: {it['tool_result']}"

    # 3. chip_pnl conservation (no censor / fallback regression on infra).
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0

    # 4. Provider capabilities populated (Phase 3b regression guard).
    assert meta["provider_capabilities"]["3"]["provider"] == "anthropic"

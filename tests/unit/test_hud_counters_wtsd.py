"""HUD WTSD counter (Phase 3c-hud Task 6).

WTSD = Went-To-Showdown given VPIP.
chances = vpip-true hands; actions = vpip-true AND reached showdown.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import TokenCounts, TurnDecisionResult
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.session.session import Session


def _cfg(num_hands: int = 6) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def test_wtsd_actions_subset_of_chances(tmp_path: Path) -> None:
    """wtsd_actions ≤ wtsd_chances (you can't reach showdown without VPIP)."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="wtsd_subset_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["wtsd_actions"] <= c["wtsd_chances"]


def test_wtsd_chances_equals_vpip_actions(tmp_path: Path) -> None:
    """wtsd_chances and vpip_actions track the same per-hand boolean —
    they should always be equal (Task 6 wires WTSD chance increment off
    the same did_vpip flag)."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="wtsd_eq_vpip_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["wtsd_chances"] == c["vpip_actions"], (
            f"seat {seat}: wtsd_chances={c['wtsd_chances']} != "
            f"vpip_actions={c['vpip_actions']}"
        )


def test_wtsd_zero_when_only_folds(tmp_path: Path) -> None:
    """Fold-only session: no VPIP → no WTSD chances."""
    class FoldOnly(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            action_name = "fold" if "fold" in legal else "check"
            return TurnDecisionResult(
                iterations=(), final_action=Action(tool_name=action_name, args={}),
                total_tokens=TokenCounts.zero(), wall_time_ms=0,
                api_retry_count=0, illegal_action_retry_count=0,
                no_tool_retry_count=0, tool_usage_error_count=0,
                default_action_fallback=False, api_error=None,
                turn_timeout_exceeded=False,
            )

        def provider_id(self) -> str:
            return "test:fold_only"

    cfg = _cfg(num_hands=6)
    agents = [FoldOnly() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="wtsd_zero_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["wtsd_chances"] == 0
        assert c["wtsd_actions"] == 0

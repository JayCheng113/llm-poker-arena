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


def test_wtsd_actions_zero_when_seat_wins_uncalled_preflop_shove(
    tmp_path: Path,
) -> None:
    """Code-reviewer IMPORTANT-1 regression: seat that VPIPs (shoves
    preflop) and wins uncalled should NOT count as WTSD action — there
    was no actual showdown, just everyone else folded.

    Setup: seat 0 always shoves preflop; seats 1-5 always fold. Across 6
    hands of button rotation, seat 0 wins multiple uncalled shoves (VPIP
    True each time, but no contested showdown reached)."""
    class ShovePreflop(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            # Pick raise_to with max amount (effective shove); fall back to
            # call/check/fold if raise not legal (shouldn't happen preflop UTG).
            if "raise_to" in legal:
                spec = next(t for t in view.legal_actions.tools
                            if t.name == "raise_to")
                amt = int(spec.args["amount"]["max"])
                action = Action(tool_name="raise_to", args={"amount": amt})
            elif "all_in" in legal:
                action = Action(tool_name="all_in", args={})
            elif "check" in legal:
                action = Action(tool_name="check", args={})
            else:
                action = Action(tool_name="fold", args={})
            return TurnDecisionResult(
                iterations=(), final_action=action,
                total_tokens=TokenCounts.zero(), wall_time_ms=0,
                api_retry_count=0, illegal_action_retry_count=0,
                no_tool_retry_count=0, tool_usage_error_count=0,
                default_action_fallback=False, api_error=None,
                turn_timeout_exceeded=False,
            )

        def provider_id(self) -> str:
            return "test:shove_preflop"

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
    agents = [ShovePreflop()] + [FoldOnly() for _ in range(5)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="wtsd_uncalled_test")
    asyncio.run(sess.run())

    c = sess._hud_counters[0]
    # Seat 0 VPIPed (shoved) at least once across the 6 hands.
    assert c["vpip_actions"] > 0, (
        f"seat 0 vpip_actions={c['vpip_actions']} — shove agent failed to "
        f"produce any VPIP"
    )
    # WTSD chances should equal vpip_actions per the WTSD-given-VPIP definition.
    assert c["wtsd_chances"] == c["vpip_actions"]
    # KEY: wtsd_actions must be 0 — every hand was won uncalled, so no
    # actual showdown occurred. Pre-fix this would equal vpip_actions.
    assert c["wtsd_actions"] == 0, (
        f"seat 0 wtsd_actions={c['wtsd_actions']} but should be 0 — "
        f"all VPIPed hands won uncalled (no contested showdown). "
        f"showdown_seats with len==1 is NOT a real showdown."
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

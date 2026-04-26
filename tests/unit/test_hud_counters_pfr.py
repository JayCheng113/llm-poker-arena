"""HUD PFR counter logic in Session._run_one_hand (Phase 3c-hud Task 3)."""
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


def test_pfr_counter_within_vpip_bound(tmp_path: Path) -> None:
    """PFR ⊆ VPIP: pfr_actions ≤ vpip_actions ≤ total_hands_played."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="pfr_bounds_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["pfr_actions"] <= c["vpip_actions"], (
            f"seat {seat} pfr_actions={c['pfr_actions']} > "
            f"vpip_actions={c['vpip_actions']} (PFR must be subset of VPIP)"
        )


def test_pfr_zero_when_only_calls_preflop(tmp_path: Path) -> None:
    """A call-only agent (never raises) → pfr_actions=0 for all seats."""
    class CallOnly(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            # Prefer call > check > fold to avoid raise.
            for name in ("call", "check", "fold"):
                if name in legal:
                    action = Action(tool_name=name, args={})
                    break
            else:  # only raises legal — must take one (illegal_action fallback otherwise)
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
            return "test:call_only"

    cfg = _cfg(num_hands=6)
    agents = [CallOnly() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="pfr_zero_test")
    asyncio.run(sess.run())

    for seat in range(6):
        assert sess._hud_counters[seat]["pfr_actions"] == 0, (
            f"seat {seat} pfr_actions != 0 in call-only session"
        )


def test_pfr_increments_when_seat_raises_preflop(tmp_path: Path) -> None:
    """A raise-prefer agent → pfr_actions > 0 for seats that act preflop."""
    class RaisePrefer(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            # Prefer raise > call > check > fold.
            if "raise_to" in legal:
                spec = next(t for t in view.legal_actions.tools
                            if t.name == "raise_to")
                bounds = spec.args["amount"]
                amt = int(bounds["min"])
                action = Action(tool_name="raise_to", args={"amount": amt})
            elif "bet" in legal:
                spec = next(t for t in view.legal_actions.tools if t.name == "bet")
                bounds = spec.args["amount"]
                amt = int(bounds["min"])
                action = Action(tool_name="bet", args={"amount": amt})
            elif "call" in legal:
                action = Action(tool_name="call", args={})
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
            return "test:raise_prefer"

    cfg = _cfg(num_hands=6)
    agents = [RaisePrefer() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="pfr_pos_test")
    asyncio.run(sess.run())

    # At least one seat per hand acts preflop and raises (UTG goes first).
    # Total PFR across all seats >= total_hands_played.
    total_pfr = sum(sess._hud_counters[i]["pfr_actions"] for i in range(6))
    assert total_pfr >= sess._total_hands_played, (
        f"raise-prefer session expected total_pfr >= {sess._total_hands_played}, "
        f"got {total_pfr}"
    )

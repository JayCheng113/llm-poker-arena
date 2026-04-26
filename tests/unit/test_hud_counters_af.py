"""HUD AF (Aggression Factor) counter (Phase 3c-hud Task 5)."""
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


def test_af_counters_non_negative(tmp_path: Path) -> None:
    """RandomAgent session: af_aggressive and af_passive both >= 0."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="af_bounds_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert c["af_aggressive"] >= 0
        assert c["af_passive"] >= 0


def test_af_zero_aggressive_when_only_calls(tmp_path: Path) -> None:
    """Call-only session: af_aggressive=0 (no bet/raise/all_in)."""
    class CallOnly(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            for name in ("call", "check", "fold"):
                if name in legal:
                    action = Action(tool_name=name, args={})
                    break
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
            return "test:call_only"

    cfg = _cfg(num_hands=6)
    agents = [CallOnly() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="af_zero_agg_test")
    asyncio.run(sess.run())

    for seat in range(6):
        assert sess._hud_counters[seat]["af_aggressive"] == 0


def test_af_zero_passive_when_only_raises(tmp_path: Path) -> None:
    """Raise-prefer session never calls — af_passive=0 for all seats."""
    class RaisePrefer(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            if "raise_to" in legal:
                spec = next(t for t in view.legal_actions.tools
                            if t.name == "raise_to")
                amt = int(spec.args["amount"]["min"])
                action = Action(tool_name="raise_to", args={"amount": amt})
            elif "bet" in legal:
                spec = next(t for t in view.legal_actions.tools if t.name == "bet")
                amt = int(spec.args["amount"]["min"])
                action = Action(tool_name="bet", args={"amount": amt})
            elif "check" in legal:
                action = Action(tool_name="check", args={})  # avoid call
            elif "fold" in legal:
                action = Action(tool_name="fold", args={})
            else:
                action = Action(tool_name="call", args={})  # last resort
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
                   session_id="af_zero_pass_test")
    asyncio.run(sess.run())

    # NOTE: this test only verifies af_passive == 0; aggressive may or may
    # not be > 0 depending on hand flow (BB might not get raise option, etc.).
    for seat in range(6):
        assert sess._hud_counters[seat]["af_passive"] == 0, (
            f"seat {seat} af_passive={sess._hud_counters[seat]['af_passive']} "
            f"!= 0 in raise-prefer session"
        )

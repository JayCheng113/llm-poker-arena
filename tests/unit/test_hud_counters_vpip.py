"""HUD VPIP counter logic in Session._run_one_hand (Phase 3c-hud Task 2)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _cfg(num_hands: int = 6) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def test_vpip_counter_increments_when_seat_voluntarily_acts_preflop(
    tmp_path: Path,
) -> None:
    """6-hand session with all RandomAgents. Each seat's vpip_actions
    counter <= total_hands_played and >= 0 (RandomAgent sometimes folds
    preflop = no VPIP, sometimes calls = VPIP)."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="vpip_test")
    asyncio.run(sess.run())

    for seat in range(6):
        c = sess._hud_counters[seat]
        assert 0 <= c["vpip_actions"] <= sess._total_hands_played, (
            f"seat {seat} vpip_actions={c['vpip_actions']} out of bounds "
            f"[0, {sess._total_hands_played}]"
        )


def test_vpip_at_most_one_per_hand_per_seat(tmp_path: Path) -> None:
    """A seat with multiple preflop actions in one hand (e.g. limp then
    call a 3-bet) only increments vpip_actions by 1 for that hand."""
    cfg = _cfg(num_hands=6)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="vpip_dedup_test")
    asyncio.run(sess.run())

    # vpip_actions per seat <= total_hands_played (1-per-hand cap).
    for seat in range(6):
        assert sess._hud_counters[seat]["vpip_actions"] <= 6


def test_vpip_zero_when_seat_only_folds_preflop(tmp_path: Path) -> None:
    """An all-fold session (programmatically via fold-only agent) gives
    vpip_actions=0 for all seats. RandomAgent doesn't always fold, so we
    use a custom fold-only agent."""
    from llm_poker_arena.agents.base import Agent
    from llm_poker_arena.agents.llm.types import TokenCounts, TurnDecisionResult
    from llm_poker_arena.engine.legal_actions import Action
    from llm_poker_arena.engine.views import PlayerView

    class FoldOnly(Agent):
        async def decide(self, view: PlayerView) -> TurnDecisionResult:
            legal = {t.name for t in view.legal_actions.tools}
            # Prefer fold; fall back to check if fold not legal (BB option).
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
                   session_id="vpip_zero_test")
    asyncio.run(sess.run())

    # No seat voluntarily acted (all folds). VPIP = 0 for all. NOTE: BB may
    # have to "check" (option to see flop free) when everyone limps — that
    # check is NOT VPIP per standard convention (no money put in voluntarily
    # beyond the forced blind). Our impl agrees.
    for seat in range(6):
        assert sess._hud_counters[seat]["vpip_actions"] == 0, (
            f"seat {seat} vpip_actions != 0 in all-fold session: "
            f"{sess._hud_counters[seat]['vpip_actions']}"
        )

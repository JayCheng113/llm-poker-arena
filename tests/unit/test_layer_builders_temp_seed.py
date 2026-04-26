"""build_agent_view_snapshot writes temp/seed to AgentDescriptor (Phase 4 Task 1)."""
from __future__ import annotations

from llm_poker_arena.agents.llm.types import TokenCounts
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.storage.layer_builders import build_agent_view_snapshot


def _view() -> PlayerView:
    params = SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=False, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=0.4, effective_stack=10_000,
        seats_public=tuple(
            SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                           position_full="x", stack=10_000,
                           invested_this_hand=0, invested_this_round=0,
                           status="in_hand") for i in range(6)
        ),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=LegalActionSet(tools=(
            ActionToolSpec(name="fold", args={}),
        )),
        opponent_stats={}, hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=params,
    )


def test_build_snapshot_default_temp_seed_none() -> None:
    """No metadata passed → AgentDescriptor.temperature/seed stay None."""
    snap = build_agent_view_snapshot(
        hand_id=1, session_id="s1", seat=3, street=Street.PREFLOP,
        timestamp="2026-04-25T10:00:00.000Z",
        view=_view(), action=Action(tool_name="fold", args={}),
        turn_index=0,
        agent_provider="random", agent_model="uniform",
        agent_version="phase1", default_action_fallback=False,
    )
    assert snap.agent.temperature is None
    assert snap.agent.seed is None


def test_build_snapshot_with_metadata_persists_temp_seed() -> None:
    """metadata kwarg → AgentDescriptor.temperature/seed populated."""
    snap = build_agent_view_snapshot(
        hand_id=1, session_id="s1", seat=3, street=Street.PREFLOP,
        timestamp="2026-04-25T10:00:00.000Z",
        view=_view(), action=Action(tool_name="fold", args={}),
        turn_index=0,
        agent_provider="anthropic", agent_model="claude-haiku-4-5",
        agent_version="phase3d", default_action_fallback=False,
        agent_temperature=0.7, agent_seed=42,
        total_tokens=TokenCounts(input_tokens=100, output_tokens=20,
                                  cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0),
    )
    assert snap.agent.temperature == 0.7
    assert snap.agent.seed == 42

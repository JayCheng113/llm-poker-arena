"""Tests for RandomAgent."""
from __future__ import annotations

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)


def _params() -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=False, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _seats() -> tuple[SeatPublicInfo, ...]:
    return tuple(
        SeatPublicInfo(
            seat=i, label=f"P{i}", position_short="UTG", position_full="Under the Gun",
            stack=10_000, invested_this_hand=0, invested_this_round=0, status="in_hand",
        )
        for i in range(6)
    )


def _view_with(tools: LegalActionSet, turn_seed: int = 1) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=0, my_invested_this_round=0, current_bet_to_match=100,
        seats_public=_seats(), opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=tools, opponent_stats={},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=turn_seed, immutable_session_params=_params(),
    )


def test_random_agent_picks_only_legal_tool_names() -> None:
    tools = LegalActionSet(tools=(
        ActionToolSpec(name="fold", args={}),
        ActionToolSpec(name="call", args={}),
    ))
    agent = RandomAgent()
    for seed in range(100):
        view = _view_with(tools, turn_seed=seed)
        act = agent.decide(view)
        assert act.tool_name in {"fold", "call"}


def test_random_agent_is_deterministic_given_turn_seed() -> None:
    tools = LegalActionSet(tools=(
        ActionToolSpec(name="fold", args={}),
        ActionToolSpec(name="call", args={}),
        ActionToolSpec(name="raise_to", args={"amount": {"min": 200, "max": 1000}}),
    ))
    agent = RandomAgent()
    a = agent.decide(_view_with(tools, turn_seed=777))
    b = agent.decide(_view_with(tools, turn_seed=777))
    assert a == b


def test_random_agent_raise_amount_within_bounds() -> None:
    tools = LegalActionSet(tools=(
        ActionToolSpec(name="fold", args={}),
        ActionToolSpec(name="raise_to", args={"amount": {"min": 200, "max": 1000}}),
    ))
    agent = RandomAgent()
    for seed in range(200):
        act = agent.decide(_view_with(tools, turn_seed=seed))
        if act.tool_name == "raise_to":
            assert 200 <= int(act.args["amount"]) <= 1000


def test_random_agent_provider_id_stable() -> None:
    assert RandomAgent().provider_id().startswith("random")

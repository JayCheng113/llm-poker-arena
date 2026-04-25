"""BR2-03 / PP-04: default_safe_action must never return an illegal action."""
from __future__ import annotations

from llm_poker_arena.engine.legal_actions import default_safe_action
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
            seat=i, label=f"P{i}", position_short="BB", position_full="Big Blind",
            stack=10_000, invested_this_hand=0, invested_this_round=0, status="in_hand",
        )
        for i in range(6)
    )


def _view(*, current_bet_to_match: int, my_invested_this_round: int) -> PlayerView:
    to_call = max(0, current_bet_to_match - my_invested_this_round)
    pot = 150
    pot_odds = to_call / (pot + to_call) if to_call > 0 else None
    return PlayerView(
        my_seat=3,
        my_hole_cards=("As", "Kd"),
        community=(),
        pot=pot,
        sidepots=(),
        my_stack=10_000,
        my_invested_this_hand=my_invested_this_round,
        my_invested_this_round=my_invested_this_round,
        current_bet_to_match=current_bet_to_match,
        to_call=to_call,
        pot_odds_required=pot_odds,
        effective_stack=10_000,
        seats_public=_seats(),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(2, 3, 4, 5, 0, 1),
        seats_yet_to_act_after_me=(4, 5, 0, 1),
        already_acted_this_street=(),
        hand_history=(),
        legal_actions=LegalActionSet(
            tools=(ActionToolSpec(name="check", args={}), ActionToolSpec(name="bet", args={"amount": {"min": 100, "max": 10_000}})),
        ),
        opponent_stats={},
        hand_id=1,
        street=Street.FLOP,
        button_seat=0,
        turn_seed=99,
        immutable_session_params=_params(),
    )


def test_returns_check_when_no_bet_to_call() -> None:
    v = _view(current_bet_to_match=0, my_invested_this_round=0)
    act = default_safe_action(v)
    assert act.tool_name == "check"
    assert act.args == {}


def test_returns_fold_when_facing_a_bet() -> None:
    v = _view(current_bet_to_match=200, my_invested_this_round=0)
    act = default_safe_action(v)
    assert act.tool_name == "fold"
    assert act.args == {}


def test_returns_check_when_matched_this_round() -> None:
    # I've already matched the highest bet — no more to call.
    v = _view(current_bet_to_match=200, my_invested_this_round=200)
    act = default_safe_action(v)
    assert act.tool_name == "check"

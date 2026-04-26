"""Tests for validate_action pure function (Phase 3a)."""

from __future__ import annotations

from llm_poker_arena.engine.legal_actions import (
    Action,
    ValidationResult,
    validate_action,
)
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
        num_players=6,
        sb=50,
        bb=100,
        starting_stack=10_000,
        max_utility_calls=5,
        rationale_required=True,
        enable_math_tools=False,
        enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _seats() -> tuple[SeatPublicInfo, ...]:
    return tuple(
        SeatPublicInfo(
            seat=i,
            label=f"P{i}",
            position_short="UTG",
            position_full="x",
            stack=10_000,
            invested_this_hand=0,
            invested_this_round=0,
            status="in_hand",
        )
        for i in range(6)
    )


def _view(legal: LegalActionSet) -> PlayerView:
    return PlayerView(
        my_seat=3,
        my_hole_cards=("As", "Kd"),
        community=(),
        pot=150,
        sidepots=(),
        my_stack=10_000,
        my_invested_this_hand=0,
        my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100,
        pot_odds_required=0.4,
        effective_stack=10_000,
        seats_public=_seats(),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(),
        hand_history=(),
        legal_actions=legal,
        opponent_stats={},
        hand_id=1,
        street=Street.PREFLOP,
        button_seat=0,
        turn_seed=42,
        immutable_session_params=_params(),
    )


def test_validate_action_accepts_legal_fold() -> None:
    legal = LegalActionSet(
        tools=(
            ActionToolSpec(name="fold", args={}),
            ActionToolSpec(name="call", args={}),
        )
    )
    r = validate_action(_view(legal), Action(tool_name="fold", args={}))
    assert r.is_valid
    assert r.reason is None


def test_validate_action_rejects_unknown_tool() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    r = validate_action(_view(legal), Action(tool_name="raise_to", args={"amount": 200}))
    assert not r.is_valid
    assert r.reason is not None
    assert "raise_to" in r.reason


def test_validate_action_accepts_raise_within_bounds() -> None:
    legal = LegalActionSet(
        tools=(ActionToolSpec(name="raise_to", args={"amount": {"min": 200, "max": 10_000}}),)
    )
    r = validate_action(_view(legal), Action(tool_name="raise_to", args={"amount": 500}))
    assert r.is_valid


def test_validate_action_rejects_raise_below_min() -> None:
    legal = LegalActionSet(
        tools=(ActionToolSpec(name="raise_to", args={"amount": {"min": 200, "max": 10_000}}),)
    )
    r = validate_action(_view(legal), Action(tool_name="raise_to", args={"amount": 150}))
    assert not r.is_valid
    reason = r.reason or ""
    assert "min" in reason.lower() or "200" in reason


def test_validate_action_rejects_raise_above_max() -> None:
    legal = LegalActionSet(
        tools=(ActionToolSpec(name="raise_to", args={"amount": {"min": 200, "max": 10_000}}),)
    )
    r = validate_action(_view(legal), Action(tool_name="raise_to", args={"amount": 12_000}))
    assert not r.is_valid


def test_validate_action_rejects_raise_missing_amount() -> None:
    legal = LegalActionSet(
        tools=(ActionToolSpec(name="raise_to", args={"amount": {"min": 200, "max": 10_000}}),)
    )
    r = validate_action(_view(legal), Action(tool_name="raise_to", args={}))
    assert not r.is_valid
    reason = r.reason or ""
    assert "amount" in reason.lower()


def test_validate_action_accepts_check_no_args() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="check", args={}),))
    r = validate_action(_view(legal), Action(tool_name="check", args={}))
    assert r.is_valid


def test_validation_result_is_a_dataclass() -> None:
    """Defensive: ValidationResult must be importable + constructible."""
    r = ValidationResult(is_valid=True, reason=None)
    assert r.is_valid is True
    assert r.reason is None

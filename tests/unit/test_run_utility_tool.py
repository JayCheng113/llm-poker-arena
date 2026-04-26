"""Tests for run_utility_tool dispatcher (spec §5.4 simplified)."""

from __future__ import annotations

import pytest

from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.tools import ToolDispatchError, run_utility_tool


def _view() -> PlayerView:
    params = SessionParamsView(
        num_players=6,
        sb=50,
        bb=100,
        starting_stack=10_000,
        max_utility_calls=5,
        rationale_required=True,
        enable_math_tools=True,
        enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )
    return PlayerView(
        my_seat=3,
        my_hole_cards=("As", "Kd"),
        community=(),
        pot=250,
        sidepots=(),
        my_stack=9_750,
        my_invested_this_hand=0,
        my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100,
        pot_odds_required=100 / 350,
        effective_stack=9_750,
        seats_public=tuple(
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
        ),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(),
        hand_history=(),
        legal_actions=LegalActionSet(
            tools=(
                ActionToolSpec(name="fold", args={}),
                ActionToolSpec(name="call", args={}),
            )
        ),
        opponent_stats={},
        hand_id=1,
        street=Street.PREFLOP,
        button_seat=0,
        turn_seed=42,
        immutable_session_params=params,
    )


def test_dispatch_pot_odds_zero_arg_returns_value_dict() -> None:
    v = _view()
    result = run_utility_tool(v, "pot_odds", {})
    # Spec §7.4 result shape: {"value": float}
    assert set(result.keys()) == {"value"}
    assert result["value"] == pytest.approx(100 / 350)


def test_dispatch_pot_odds_with_args() -> None:
    v = _view()
    result = run_utility_tool(v, "pot_odds", {"to_call": 600, "pot": 850})
    assert result["value"] == pytest.approx(600 / 1450)


def test_dispatch_spr() -> None:
    v = _view()
    result = run_utility_tool(v, "spr", {})
    assert result["value"] == pytest.approx(9_750 / 250)


def test_dispatch_unknown_tool_raises() -> None:
    v = _view()
    with pytest.raises(ToolDispatchError, match="Unknown utility tool: foo"):
        run_utility_tool(v, "foo", {})


def test_dispatch_propagates_pot_odds_validation_error() -> None:
    """Negative to_call from LLM args must surface as ToolDispatchError —
    LLMAgent will catch it and feed back to the model."""
    v = _view()
    with pytest.raises(ToolDispatchError, match="to_call must be >= 0"):
        run_utility_tool(v, "pot_odds", {"to_call": -50})


def test_dispatch_rejects_extra_args() -> None:
    """Codex audit IMPORTANT-3: input_schema declares additionalProperties=False,
    so extras are REJECTED (not silently dropped). Surfacing the error lets
    the model learn the schema rather than rely on undefined behavior."""
    v = _view()
    with pytest.raises(ToolDispatchError, match="unexpected args"):
        run_utility_tool(v, "pot_odds", {"to_call": 100, "garbage": "x"})


def test_dispatch_rejects_string_arg() -> None:
    """Codex audit IMPORTANT-2: model may pass `{"to_call": "100"}` as string;
    input_schema doesn't enforce, dispatcher must validate before passing
    through (otherwise comparison `"100" < 0` raises uncaught TypeError)."""
    v = _view()
    with pytest.raises(ToolDispatchError, match="must be an integer"):
        run_utility_tool(v, "pot_odds", {"to_call": "100"})


def test_dispatch_rejects_float_arg() -> None:
    v = _view()
    with pytest.raises(ToolDispatchError, match="must be an integer"):
        run_utility_tool(v, "pot_odds", {"pot": 100.5})


def test_dispatch_rejects_bool_arg() -> None:
    """bool is a subclass of int in Python (True == 1, False == 0). Without
    explicit rejection, a confused model could pass `to_call=True` and get
    away with it. Reject bools explicitly."""
    v = _view()
    with pytest.raises(ToolDispatchError, match="must be an integer"):
        run_utility_tool(v, "pot_odds", {"to_call": True})


def test_dispatch_rejects_none_arg() -> None:
    """None passed as a value (not as 'arg absent') is malformed. The
    dispatcher passes args dict to the tool; the tool's signature uses
    `int | None` defaults but only when the KEY is missing. An explicit
    None value with the key present should be rejected."""
    v = _view()
    with pytest.raises(ToolDispatchError, match="must be an integer"):
        run_utility_tool(v, "pot_odds", {"to_call": None})


def test_dispatch_hand_equity_vs_ranges() -> None:
    """run_utility_tool dispatches the new equity tool. Validates the dict
    flows through the normal dispatch path (extras-rejection, type-validation
    DON'T apply to dict-typed args — equity has its own validation in Task 4).

    Uses mostly-disjoint villain ranges so rejection sampling reaches the
    n_samples=5000 target. Heavy-overlap ranges (e.g., 5 villains all on
    QQ+) trip max_attempts before convergence — that's a real edge case
    documented in equity.py but not what this dispatcher test verifies.
    """
    v = _view()
    # Disjoint-by-suit ranges to minimize inter-villain card overlap rejection.
    result = run_utility_tool(
        v,
        "hand_equity_vs_ranges",
        {"range_by_seat": {0: "22+", 1: "A2s+", 2: "K2s+", 4: "Q2s+", 5: "J2s+"}},
    )
    assert "hero_equity" in result
    assert 0.0 <= result["hero_equity"] <= 1.0
    assert result["n_samples"] > 0  # rejection-sampled some valid configurations

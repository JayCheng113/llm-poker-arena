"""hand_equity_vs_ranges full tool integration tests.

Covers spec §5.2.3 strict validation (keys must equal opponent_seats_in_hand),
range parsing via eval7.HandRange (passes through ToolDispatchError on
RangeStringError), combo cap enforcement (codex-style abuse defense), and
EquityResult shape.
"""
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
from llm_poker_arena.tools.equity import hand_equity_vs_ranges
from llm_poker_arena.tools.runner import ToolDispatchError


def _params() -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=True, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _view(*, opponent_seats: tuple[int, ...] = (0, 1, 2, 4, 5),
          community: tuple[str, ...] = ()) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Ks"), community=community,
        pot=250, sidepots=(), my_stack=9_750,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=100 / 350,
        effective_stack=9_750,
        seats_public=tuple(
            SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                           position_full="x", stack=10_000,
                           invested_this_hand=0, invested_this_round=0,
                           status="in_hand") for i in range(6)
        ),
        opponent_seats_in_hand=opponent_seats,
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=LegalActionSet(tools=(
            ActionToolSpec(name="fold", args={}),
        )),
        opponent_stats={}, hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=_params(),
    )


def test_equity_hu_returns_equityresult_dict() -> None:
    """HU degenerate case: dict with single key matching the only villain."""
    v = _view(opponent_seats=(0,))
    result = hand_equity_vs_ranges(v, {0: "QQ+"}, seed=42)
    # Dict with EquityResult dump shape.
    assert set(result.keys()) >= {"hero_equity", "ci_low", "ci_high",
                                   "n_samples", "seed", "backend"}
    assert 0.0 <= result["hero_equity"] <= 1.0
    assert result["ci_low"] <= result["hero_equity"] <= result["ci_high"]
    # n_samples reflects ACTUAL valid samples (typically equals configured
    # 5000 since AsKs vs QQ+ has no card overlap; could be slightly less
    # in pathological setups). Assert == 5000 for this clean HU case.
    assert result["n_samples"] == 5000
    assert result["seed"] == 42
    assert result["backend"] == "eval7"


def test_equity_multi_way_returns_equityresult_dict() -> None:
    """3-way: hero + 2 villains."""
    v = _view(opponent_seats=(0, 4))
    result = hand_equity_vs_ranges(v, {0: "QQ+", 4: "AKs"}, seed=42)
    assert 0.0 <= result["hero_equity"] <= 1.0


def test_equity_missing_seat_raises() -> None:
    """spec §5.2.3: range_by_seat keys MUST equal opponent_seats_in_hand."""
    v = _view(opponent_seats=(0, 1, 4))
    with pytest.raises(ToolDispatchError, match="must equal"):
        hand_equity_vs_ranges(v, {0: "QQ+"}, seed=42)  # missing seats 1, 4


def test_equity_extra_seat_raises() -> None:
    v = _view(opponent_seats=(0,))
    with pytest.raises(ToolDispatchError, match="must equal"):
        # Extra seat 4 not in opponent_seats.
        hand_equity_vs_ranges(v, {0: "QQ+", 4: "AKs"}, seed=42)


def test_equity_combo_cap_500_per_range_raises() -> None:
    """Defense against absurdly broad ranges. spec doesn't mandate this cap;
    plan adds it as a safety rail."""
    v = _view(opponent_seats=(0,))
    # eval7 rejects "100%" syntactically, but very-broad valid ranges still
    # exist. Construct one well over 500.
    huge_range = ("22+, A2s+, K2s+, Q2s+, J2s+, T2s+, 92s+, A2o+, "
                  "K2o+, Q2o+, J2o+, T2o+")
    with pytest.raises(ToolDispatchError, match="combo cap"):
        hand_equity_vs_ranges(v, {0: huge_range}, seed=42)


def test_equity_invalid_range_string_raises_with_eval7_message() -> None:
    """eval7 RangeStringError → ToolDispatchError; original message preserved
    so LLM can self-correct."""
    v = _view(opponent_seats=(0,))
    with pytest.raises(ToolDispatchError, match="parse"):
        hand_equity_vs_ranges(v, {0: "garbage notation here"}, seed=42)


def test_equity_weighted_range_rejected() -> None:
    """Codex audit IMPORTANT-1 fix: eval7 supports weighted syntax like
    '40%(KK)' which our MC silently mishandles (rng.choice ignores weights).
    Plan rejects non-1.0 weights at parse time."""
    v = _view(opponent_seats=(0,))
    with pytest.raises(ToolDispatchError, match="weighted"):
        hand_equity_vs_ranges(v, {0: "40%(KK), AA"}, seed=42)

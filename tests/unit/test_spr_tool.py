"""Tests for spr (stack-to-pot ratio) utility tool.

Spec §5.2.3 defines spr as zero-arg view-derived. Optional-arg superset
mirrors pot_odds: zero-arg falls back to view, args support hypothetical
post-flop SPR reasoning (e.g. 'after I raise to X, what is the SPR on flop').
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
from llm_poker_arena.tools.spr import spr


def _params() -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=True, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _view(*, pot: int = 1_000, my_stack: int = 9_000,
          effective_stack: int = 9_000) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=pot, sidepots=(), my_stack=my_stack,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=0,
        to_call=0, pot_odds_required=None,
        effective_stack=effective_stack,
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
            ActionToolSpec(name="check", args={}),
        )),
        opponent_stats={}, hand_id=1, street=Street.FLOP, button_seat=0,
        turn_seed=42, immutable_session_params=_params(),
    )


def test_spr_zero_arg_uses_view_effective_stack() -> None:
    """Spec §5.2.3 zero-arg: SPR = effective_stack / pot.

    Effective stack (not raw my_stack) is the right denominator because SPR
    measures commitment given the smallest live stack — what's actually at
    risk if hands go to showdown.
    """
    v = _view(pot=1_000, my_stack=9_000, effective_stack=9_000)
    assert spr(v) == 9.0


def test_spr_with_args_overrides_view() -> None:
    """Hypothetical: 'after I raise pot to 3000, what's the new SPR?'"""
    v = _view(pot=1_000, my_stack=9_000, effective_stack=9_000)
    # Hero stacks shrunk to 6000 after putting in 3000; new pot = 4000.
    assert spr(v, stack=6_000, pot=4_000) == 1.5


def test_spr_partial_args_mixes_with_view() -> None:
    v = _view(pot=1_000, my_stack=9_000, effective_stack=9_000)
    # Only override stack; pot stays at view's 1000.
    assert spr(v, stack=4_000) == 4.0
    # Only override pot; stack stays at view's effective_stack=9000.
    assert spr(v, pot=2_000) == 4.5


def test_spr_zero_pot_raises() -> None:
    """SPR with pot=0 is undefined (preflop before blinds posted is the only
    possible case, and that's a degenerate scenario). Raise rather than emit
    inf."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    v = _view(pot=1_000, my_stack=9_000)
    with pytest.raises(ToolDispatchError, match="pot must be > 0"):
        spr(v, pot=0)


def test_spr_negative_stack_raises() -> None:
    from llm_poker_arena.tools.runner import ToolDispatchError
    v = _view(pot=1_000, my_stack=9_000)
    with pytest.raises(ToolDispatchError, match="stack must be >= 0"):
        spr(v, stack=-100)

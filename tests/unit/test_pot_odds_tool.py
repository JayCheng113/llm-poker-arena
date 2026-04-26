"""Tests for pot_odds utility tool.

Spec §5.2.3 defines pot_odds as zero-arg view-derived. Phase 3c-math ships
the optional-arg superset: zero-arg falls back to view, args override for
hypothetical reasoning (e.g. 'if I raise to 600, what is villain's pot_odds').
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
from llm_poker_arena.tools.pot_odds import pot_odds


def _params(enable_math_tools: bool = True) -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=enable_math_tools, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _view(*, pot: int = 250, to_call: int = 100, my_stack: int = 9_750,
          ) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=pot, sidepots=(), my_stack=my_stack,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=to_call,
        to_call=to_call,
        pot_odds_required=to_call / (pot + to_call) if to_call else None,
        effective_stack=my_stack,
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
            ActionToolSpec(name="call", args={}),
        )),
        opponent_stats={}, hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=_params(),
    )


def test_pot_odds_zero_arg_uses_view() -> None:
    """Spec §5.2.3 zero-arg behavior: read to_call + pot from view."""
    v = _view(pot=250, to_call=100)
    # 100 / (250 + 100) = 100 / 350 ≈ 0.2857
    assert pot_odds(v) == pytest.approx(100 / 350)


def test_pot_odds_with_args_overrides_view() -> None:
    """Optional-arg superset: hypothetical reasoning."""
    v = _view(pot=250, to_call=100)
    # If hero is considering raising to 600, villain faces to_call=600 vs
    # pot=250+600=850 (their call would be 600 chips into a 1450 pot).
    assert pot_odds(v, to_call=600, pot=850) == pytest.approx(600 / 1450)


def test_pot_odds_partial_args_mixes_with_view() -> None:
    """Caller can override only one of (to_call, pot) — the other comes from view."""
    v = _view(pot=250, to_call=100)
    # Override to_call only; pot stays at view's 250.
    assert pot_odds(v, to_call=400) == pytest.approx(400 / 650)
    # Override pot only; to_call stays at view's 100.
    assert pot_odds(v, pot=900) == pytest.approx(100 / 1000)


def test_pot_odds_zero_to_call_returns_zero() -> None:
    """When to_call == 0 (we can check), pot_odds is 0 by convention.
    This avoids the divide-by-zero AND matches the user-prompt convention
    where pot_odds_required becomes None in that case.
    """
    v = _view(pot=250, to_call=0)
    assert pot_odds(v) == 0.0


def test_pot_odds_negative_to_call_raises() -> None:
    """Negative to_call is structurally impossible (engine clamps >= 0).
    If the LLM passes a negative arg, that's a user-input bug — raise."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    v = _view(pot=250, to_call=100)
    with pytest.raises(ToolDispatchError, match="to_call must be >= 0"):
        pot_odds(v, to_call=-100)


def test_pot_odds_negative_pot_raises() -> None:
    from llm_poker_arena.tools.runner import ToolDispatchError
    v = _view(pot=250, to_call=100)
    with pytest.raises(ToolDispatchError, match="pot must be >= 0"):
        pot_odds(v, pot=-50)

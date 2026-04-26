"""Unit tests for projections.py helpers (position labeling, status, street)."""

from __future__ import annotations

import pytest

from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.projections import (
    _infer_street,
    _normalize_status,
    _seats_public,
)
from llm_poker_arena.engine.types import Street


def _cfg() -> SessionConfig:
    return SessionConfig(
        num_players=6,
        starting_stack=10_000,
        sb=50,
        bb=100,
        num_hands=60,
        max_utility_calls=5,
        enable_math_tools=False,
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30,
        rng_seed=42,
    )


def _state(button_seat: int) -> CanonicalState:
    ctx = HandContext(
        hand_id=0,
        deck_seed=42_000,
        button_seat=button_seat,
        initial_stacks=(10_000,) * 6,
    )
    return CanonicalState(_cfg(), ctx)


@pytest.mark.parametrize("button_seat", list(range(6)))
def test_seats_public_labels_button_as_BTN(button_seat: int) -> None:
    """The seat at button_seat must be labeled BTN in position_short."""
    s = _state(button_seat=button_seat)
    seats = _seats_public(s)
    assert seats[button_seat].position_short == "BTN"
    assert seats[(button_seat + 1) % 6].position_short == "SB"
    assert seats[(button_seat + 2) % 6].position_short == "BB"
    assert seats[(button_seat + 3) % 6].position_short == "UTG"
    assert seats[(button_seat + 4) % 6].position_short == "HJ"
    assert seats[(button_seat + 5) % 6].position_short == "CO"


def test_normalize_status_on_pokerkit_bool_false_is_folded() -> None:
    """pokerkit emits statuses[i]=False for folded; must normalize to 'folded'."""
    assert _normalize_status(False) == "folded"


def test_normalize_status_on_pokerkit_bool_true_is_in_hand() -> None:
    """pokerkit emits statuses[i]=True for in-hand / all-in; Phase 1 treats as in_hand."""
    assert _normalize_status(True) == "in_hand"


def test_normalize_status_string_fallback() -> None:
    """String-pattern branch still works (Phase 2 compatibility)."""
    assert _normalize_status("folded") == "folded"
    assert _normalize_status("all_in") == "all_in"
    assert _normalize_status("in_hand") == "in_hand"
    assert _normalize_status("UNKNOWN_STATUS") == "in_hand"  # default


def test_infer_street_from_fresh_state_is_preflop() -> None:
    """Fresh state has no community cards → preflop."""
    assert _infer_street(_state(button_seat=0)) == Street.PREFLOP


def test_infer_street_after_flop() -> None:
    """After preflop closes and deal_community(FLOP), helper reports FLOP."""
    from llm_poker_arena.engine.legal_actions import Action
    from llm_poker_arena.engine.transition import apply_action

    s = _state(button_seat=0)
    # button_seat=0: SB=1, BB=2. Preflop action order starts UTG=3, then HJ=4,
    # CO=5, BTN=0, SB=1; BB=2 closes preflop.
    for actor in [3, 4, 5, 0, 1]:
        r = apply_action(s, actor, Action(tool_name="call", args={}))
        assert r.is_valid, f"call from seat {actor} rejected: {r.reason}"
    r = apply_action(s, 2, Action(tool_name="check", args={}))
    assert r.is_valid, f"BB check rejected: {r.reason}"
    s.deal_community(Street.FLOP)
    assert _infer_street(s) == Street.FLOP

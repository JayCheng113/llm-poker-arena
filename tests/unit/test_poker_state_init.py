"""CanonicalState construction + blinds rotation."""
from __future__ import annotations

import pytest

from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine.config import HandContext, SessionConfig


def _cfg() -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def _ctx(button_seat: int) -> HandContext:
    return HandContext(
        hand_id=1, deck_seed=42_001, button_seat=button_seat,
        initial_stacks=(10_000,) * 6,
    )


def test_state_constructs_without_error() -> None:
    s = CanonicalState(_cfg(), _ctx(0))
    assert s.num_players == 6


def test_blinds_rotate_with_button_seat_0() -> None:
    s = CanonicalState(_cfg(), _ctx(0))
    # button=0 → sb at seat 1, bb at seat 2
    assert s.sb_seat == 1
    assert s.bb_seat == 2


def test_blinds_rotate_with_button_seat_3() -> None:
    s = CanonicalState(_cfg(), _ctx(3))
    # button=3 → sb at seat 4, bb at seat 5
    assert s.sb_seat == 4
    assert s.bb_seat == 5


def test_blinds_wrap_around_with_button_seat_5() -> None:
    s = CanonicalState(_cfg(), _ctx(5))
    # button=5 → sb at seat 0, bb at seat 1
    assert s.sb_seat == 0
    assert s.bb_seat == 1


def test_initial_stacks_length_mismatch_rejected() -> None:
    bad_ctx = HandContext(
        hand_id=1, deck_seed=42_001, button_seat=0,
        initial_stacks=(10_000,) * 5,  # only 5 vs num_players=6
    )
    with pytest.raises(ValueError, match="initial_stacks length"):
        CanonicalState(_cfg(), bad_ctx)


def test_button_seat_out_of_range_rejected() -> None:
    # HandContext itself rejects; if we pass num_players=6 with a too-high
    # button we get caught at HandContext construction already.
    with pytest.raises(ValueError, match="button_seat"):
        HandContext(
            hand_id=1, deck_seed=42_001, button_seat=6,
            initial_stacks=(10_000,) * 6,
        )

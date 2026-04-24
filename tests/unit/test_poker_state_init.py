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


# --------------------------- hole card deal ---------------------------

def test_hole_cards_are_dealt_after_construction() -> None:
    s = CanonicalState(_cfg(), _ctx(0))
    hole = s.hole_cards()
    assert set(hole.keys()) == set(range(6))
    assert all(len(pair) == 2 for pair in hole.values())


def test_hole_cards_reproducible_for_same_seed() -> None:
    a = CanonicalState(_cfg(), _ctx(0)).hole_cards()
    b = CanonicalState(_cfg(), _ctx(0)).hole_cards()
    assert a == b


def test_hole_cards_differ_across_button_seats() -> None:
    # Same deck seed, different button -> different SB => different deal order.
    a = CanonicalState(_cfg(), _ctx(0)).hole_cards()
    b = CanonicalState(_cfg(), _ctx(3)).hole_cards()
    # Same deck means the 12 cards used are the same, but their seat assignment shifts.
    cards_a = {c for pair in a.values() for c in pair}
    cards_b = {c for pair in b.values() for c in pair}
    assert cards_a == cards_b
    # Yet the per-seat mapping should differ (except in the unlikely case of a
    # palindrome shift — with a fixed seed 42_001 this holds):
    assert a != b


def test_hole_cards_are_unique_across_seats() -> None:
    hole = CanonicalState(_cfg(), _ctx(0)).hole_cards()
    flat = [c for pair in hole.values() for c in pair]
    assert len(flat) == len(set(flat)) == 12


# --------------------------- community deal ---------------------------

from llm_poker_arena.engine.types import Street  # noqa: E402 — grouped at end intentionally


def _fast_forward_preflop_to_flop(state: CanonicalState) -> None:
    """Close out the current betting street by having every required actor call."""
    # Expose the underlying state for setup purposes only (test-local).
    raw = state._state
    while raw.actor_index is not None:  # FIX: is_actor_required doesn't exist in 0.7.3
        try:
            raw.check_or_call()
        except Exception:  # noqa: BLE001
            break


def test_deal_flop_reveals_three_community_cards() -> None:
    s = CanonicalState(_cfg(), _ctx(0))
    _fast_forward_preflop_to_flop(s)
    s.deal_community(Street.FLOP)
    assert len(s.community()) == 3


def test_deal_turn_adds_fourth_card() -> None:
    s = CanonicalState(_cfg(), _ctx(0))
    _fast_forward_preflop_to_flop(s)
    s.deal_community(Street.FLOP)
    _fast_forward_preflop_to_flop(s)
    s.deal_community(Street.TURN)
    assert len(s.community()) == 4


def test_same_seed_yields_same_community_cards() -> None:
    a = CanonicalState(_cfg(), _ctx(0))
    _fast_forward_preflop_to_flop(a)
    a.deal_community(Street.FLOP)

    b = CanonicalState(_cfg(), _ctx(0))
    _fast_forward_preflop_to_flop(b)
    b.deal_community(Street.FLOP)

    assert a.community() == b.community()

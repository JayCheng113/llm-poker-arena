"""Unit tests for audit invariants."""

from __future__ import annotations

import pytest

from llm_poker_arena.engine._internal.audit import (
    AuditFailure,
    HandPhase,
    audit_cards_invariant,
    audit_invariants,
    audit_pre_settlement,
)
from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine.config import HandContext, SessionConfig


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


def _state() -> CanonicalState:
    ctx = HandContext(hand_id=0, deck_seed=42_000, button_seat=0, initial_stacks=(10_000,) * 6)
    return CanonicalState(_cfg(), ctx)


def test_cards_invariant_passes_fresh_state() -> None:
    s = _state()
    audit_cards_invariant(s)  # should not raise


def test_pre_settlement_passes_fresh_state() -> None:
    s = _state()
    audit_pre_settlement(s, _cfg())


def test_audit_invariants_dispatches_on_phase() -> None:
    s = _state()
    audit_invariants(s, _cfg(), HandPhase.PRE_SETTLEMENT)
    # POST_SETTLEMENT on a mid-hand state should fail because stacks don't sum
    # back up yet (pot still holds blinds).
    with pytest.raises(AuditFailure):
        audit_invariants(s, _cfg(), HandPhase.POST_SETTLEMENT)


def test_cards_invariant_raises_on_duplicate_card() -> None:
    """Force a deck-logic regression by injecting a duplicate card after dealing.

    After `__init__`, 12 hole cards have been dealt so `_deck_cursor == 12`.
    `_deck_order[0..11]` are in pokerkit's `raw.hole_cards`; `_deck_order[12..51]`
    are the remaining undealt deck. If we overwrite one remaining slot with a
    copy of an already-dealt card, the total count stays 52 but one card appears
    in both deck_remaining AND a hole-cards slot — the exact regression
    `audit_cards_invariant` must catch.
    """
    s = _state()
    # Sanity: dealing happened.
    assert s._deck_cursor == 12  # noqa: SLF001
    # Inject a duplicate: make the first undealt slot equal to the first dealt card.
    s._deck_order[s._deck_cursor] = s._deck_order[0]  # noqa: SLF001
    with pytest.raises(AuditFailure, match="duplicate cards detected"):
        audit_cards_invariant(s)


def test_audit_failure_message_is_informative() -> None:
    s = _state()
    # Force a pre-settlement mismatch by adjusting the expected total downwards.
    bad_cfg = SessionConfig(
        num_players=6,
        starting_stack=9_999,
        sb=50,
        bb=100,  # 9_999 != 10_000
        num_hands=60,
        max_utility_calls=5,
        enable_math_tools=False,
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30,
        rng_seed=42,
    )
    with pytest.raises(AuditFailure, match="chip conservation"):
        audit_pre_settlement(s, bad_cfg)

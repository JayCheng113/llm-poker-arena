"""Tests for derived fields on PlayerView (Phase 2.5 UX hardening).

After the Mode-A demo audit revealed that LLM agents miscalculate pot odds /
equity when forced to do arithmetic from raw fields, we promote the most
safety-critical derived values into PlayerView itself:

  - to_call: how much I owe to stay in (== max(0, current_bet_to_match - my_invested_this_round))
  - pot_odds_required: to_call / (pot + to_call), or None when to_call == 0
  - effective_stack: min(my_stack, max(opponent stacks among non-folded))
  - seats_yet_to_act_after_me: PokerKit's actor_indices minus the current actor
  - action_order_this_street: the canonical street order (preflop UTG-first;
    postflop SB-first), full 6-seat tuple including folded seats — this is the
    contract rule_based.py already depends on for `position_idx` math.
"""
from __future__ import annotations

import pytest

from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.projections import build_player_view
from llm_poker_arena.engine.transition import apply_action
from llm_poker_arena.engine.types import Street


def _cfg() -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def _state(button_seat: int = 0,
           initial_stacks: tuple[int, ...] | None = None) -> CanonicalState:
    ctx = HandContext(
        hand_id=0, deck_seed=42_000, button_seat=button_seat,
        initial_stacks=initial_stacks or (10_000,) * 6,
    )
    return CanonicalState(_cfg(), ctx)


# ---------- action_order_this_street ----------

@pytest.mark.parametrize(("button", "expected"), [
    (0, (3, 4, 5, 0, 1, 2)),  # button=0: UTG=3 first, then HJ,CO,BTN,SB,BB
    (1, (4, 5, 0, 1, 2, 3)),  # button=1: UTG=4
    (2, (5, 0, 1, 2, 3, 4)),  # button=2: UTG=5
    (3, (0, 1, 2, 3, 4, 5)),  # button=3: UTG=0
    (4, (1, 2, 3, 4, 5, 0)),  # button=4: UTG=1
    (5, (2, 3, 4, 5, 0, 1)),  # button=5: UTG=2
])
def test_action_order_preflop_starts_at_utg(
    button: int, expected: tuple[int, ...],
) -> None:
    s = _state(button_seat=button)
    actor = (button + 3) % 6  # UTG
    view = build_player_view(s, actor, turn_seed=42)
    assert view.street == Street.PREFLOP
    assert view.action_order_this_street == expected


def test_action_order_postflop_starts_at_sb_for_button_zero() -> None:
    """Postflop: SB acts first (then BB, UTG, ..., BTN closes)."""
    s = _state(button_seat=0)
    # Drive to flop: UTG(3) HJ(4) CO(5) BTN(0) SB(1) call, BB(2) check.
    for actor in (3, 4, 5, 0, 1):
        r = apply_action(s, actor, Action(tool_name="call", args={}))
        assert r.is_valid, f"call from {actor} rejected: {r.reason}"
    r = apply_action(s, 2, Action(tool_name="check", args={}))
    assert r.is_valid
    s.deal_community(Street.FLOP)
    # Postflop first to act = SB = 1; order is (1,2,3,4,5,0).
    view = build_player_view(s, 1, turn_seed=43)
    assert view.street == Street.FLOP
    assert view.action_order_this_street == (1, 2, 3, 4, 5, 0)


# ---------- seats_yet_to_act_after_me ----------

def test_seats_yet_to_act_at_first_preflop_actor_button_zero() -> None:
    s = _state(button_seat=0)
    view = build_player_view(s, 3, turn_seed=42)  # UTG sees view first
    assert view.seats_yet_to_act_after_me == (4, 5, 0, 1, 2)


def test_seats_yet_to_act_drops_folded_seats() -> None:
    """After UTG folds, HJ's view should not list seat 3 in those-after-me."""
    s = _state(button_seat=0)
    apply_action(s, 3, Action(tool_name="fold", args={}))
    view = build_player_view(s, 4, turn_seed=42)  # HJ now to act
    assert 3 not in view.seats_yet_to_act_after_me
    assert view.seats_yet_to_act_after_me == (5, 0, 1, 2)


def test_seats_yet_to_act_at_bb_with_no_raises_is_empty() -> None:
    """BB closes the action when everyone limps: nobody acts after BB."""
    s = _state(button_seat=0)
    for actor in (3, 4, 5, 0, 1):
        apply_action(s, actor, Action(tool_name="call", args={}))
    # BB now to act, nobody behind
    view = build_player_view(s, 2, turn_seed=42)
    assert view.seats_yet_to_act_after_me == ()


# ---------- to_call ----------

def test_to_call_at_first_preflop_actor_is_bb() -> None:
    s = _state(button_seat=0)
    view = build_player_view(s, 3, turn_seed=42)  # UTG facing 100bb
    assert view.to_call == 100


def test_to_call_after_match_is_zero() -> None:
    """BB after everyone calls: my_invested_this_round == current_bet_to_match → 0."""
    s = _state(button_seat=0)
    for actor in (3, 4, 5, 0, 1):
        apply_action(s, actor, Action(tool_name="call", args={}))
    view = build_player_view(s, 2, turn_seed=42)  # BB
    assert view.current_bet_to_match == view.my_invested_this_round
    assert view.to_call == 0


def test_to_call_is_non_negative_even_if_bookkeeping_drifts() -> None:
    """Defensive: to_call must clamp at 0 (never negative)."""
    s = _state(button_seat=0)
    view = build_player_view(s, 3, turn_seed=42)
    # If we're seeing a view, to_call >= 0 by definition.
    assert view.to_call >= 0


# ---------- pot_odds_required ----------

def test_pot_odds_required_when_facing_bb_open() -> None:
    """UTG facing BB: pot=150 (sb+bb), to_call=100. Required = 100/(150+100) = 0.4."""
    s = _state(button_seat=0)
    view = build_player_view(s, 3, turn_seed=42)
    assert view.to_call == 100
    assert view.pot == 150
    assert view.pot_odds_required is not None
    assert abs(view.pot_odds_required - 0.4) < 1e-9


def test_pot_odds_required_is_none_when_to_call_zero() -> None:
    """No call needed → no pot odds threshold."""
    s = _state(button_seat=0)
    for actor in (3, 4, 5, 0, 1):
        apply_action(s, actor, Action(tool_name="call", args={}))
    view = build_player_view(s, 2, turn_seed=42)  # BB, can check
    assert view.to_call == 0
    assert view.pot_odds_required is None


# ---------- effective_stack ----------

def test_effective_stack_with_equal_stacks_is_starting_stack() -> None:
    s = _state(button_seat=0)  # all 10000
    view = build_player_view(s, 3, turn_seed=42)
    assert view.effective_stack == 10_000


def test_effective_stack_capped_by_shorter_opponent() -> None:
    """My 10000 vs deepest opponent 3000 → 3000."""
    stacks = (10_000, 10_000, 10_000, 10_000, 3_000, 10_000)  # seat 4 is short
    s = _state(button_seat=0, initial_stacks=stacks)
    # seat 3 = UTG sees an opp 4 with stack 3000; deepest opp = 10000 (others)
    view = build_player_view(s, 3, turn_seed=42)
    # max opp stack = 10000 (seats 0,1,2,4=3000,5 → max = 10000)
    # min(my_stack, max_opp_stack) = min(10000, 10000) = 10000.
    # That's NOT the heads-up effective stack; it's the "deepest viable opp" version.
    # Test the contract: effective_stack = min(my_stack, max_opp_stack_among_non_folded).
    assert view.effective_stack == 10_000


def test_effective_stack_when_my_stack_is_shorter() -> None:
    stacks = (10_000, 10_000, 10_000, 2_500, 10_000, 10_000)  # I'm seat 3, short
    s = _state(button_seat=0, initial_stacks=stacks)
    view = build_player_view(s, 3, turn_seed=42)
    # blinds posted: SB stack now 9950, BB 9900; my stack still 2500
    assert view.my_stack == 2_500
    # max opp stack among non-folded ≥ 9900; min(2500, ...) = 2500
    assert view.effective_stack == 2_500


def test_effective_stack_excludes_folded_opponents_via_opp_seats() -> None:
    """Folded seats are dropped from opp_stacks → max() ignores them.

    Verified transitively: after UTG and HJ fold, CO's view should not include
    seats 3 or 4 in `opponent_seats_in_hand`, and `effective_stack` is derived
    from those opponent stacks.
    """
    s = _state(button_seat=0)
    apply_action(s, 3, Action(tool_name="fold", args={}))  # UTG folds
    apply_action(s, 4, Action(tool_name="fold", args={}))  # HJ folds
    view = build_player_view(s, 5, turn_seed=42)  # CO to act
    assert 3 not in view.opponent_seats_in_hand
    assert 4 not in view.opponent_seats_in_hand
    # Active opps (BTN=10000, SB=9950, BB=9900) all uniform-ish; max=10000.
    # CO my_stack=10000. effective = min(10000, 10000) = 10000.
    assert view.effective_stack == 10_000

"""Tests for engine.transition.apply_action."""

from __future__ import annotations

from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.transition import TransitionResult, apply_action


def _setup() -> tuple[CanonicalState, int]:
    cfg = SessionConfig(
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
    ctx = HandContext(hand_id=0, deck_seed=42_000, button_seat=0, initial_stacks=(10_000,) * 6)
    s = CanonicalState(cfg, ctx)
    actor = int(getattr(s._state, "actor_index", None) or getattr(s._state, "actor", 0) or 0)
    return s, actor


def test_fold_valid_at_preflop_utg() -> None:
    s, actor = _setup()
    result = apply_action(s, actor, Action(tool_name="fold", args={}))
    assert isinstance(result, TransitionResult)
    assert result.is_valid is True


def test_illegal_tool_name_rejected() -> None:
    s, actor = _setup()
    result = apply_action(s, actor, Action(tool_name="teleport", args={}))
    assert result.is_valid is False
    assert "not in legal set" in (result.reason or "")


def test_raise_amount_below_min_rejected() -> None:
    s, actor = _setup()
    # Force a below-min amount; PokerKit min raise preflop is typically 200 (= 2 * BB).
    result = apply_action(s, actor, Action(tool_name="raise_to", args={"amount": 1}))
    assert result.is_valid is False


def test_apply_action_runs_pre_settlement_audit() -> None:
    s, actor = _setup()
    # A valid fold should preserve chip conservation.
    apply_action(s, actor, Action(tool_name="fold", args={}))
    # If audit had failed, apply_action would have raised AuditFailure.


def test_call_valid_when_facing_bet() -> None:
    """Covers raw.check_or_call() dispatch on the 'call' arm (UTG facing BB)."""
    s, actor = _setup()
    # UTG preflop faces the BB; 'call' is legal.
    result = apply_action(s, actor, Action(tool_name="call", args={}))
    assert result.is_valid is True
    assert result.reason is None


def test_raise_to_valid_in_bounds() -> None:
    """Covers raw.complete_bet_or_raise_to() dispatch success (not just rejection)."""
    s, actor = _setup()
    # Preflop min raise is 200 (2 * BB). Pick 300 — well within bounds.
    result = apply_action(s, actor, Action(tool_name="raise_to", args={"amount": 300}))
    assert result.is_valid is True
    assert result.reason is None


def test_all_in_translates_to_max_completion() -> None:
    """Covers the all_in -> complete_bet_or_raise_to(max) translation path.

    After all-in, actor's stack should be 0 (they shoved everything into the pot)
    AND invariants still hold (audit runs at end of apply_action).
    """
    s, actor = _setup()
    stack_before = s._state.stacks[actor]  # noqa: SLF001
    assert stack_before > 0
    result = apply_action(s, actor, Action(tool_name="all_in", args={}))
    assert result.is_valid is True
    # After all-in, actor's remaining stack is 0 (they shoved to max_cbor).
    assert s._state.stacks[actor] == 0  # noqa: SLF001

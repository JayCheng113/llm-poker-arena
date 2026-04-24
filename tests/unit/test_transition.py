"""Tests for engine.transition.apply_action."""
from __future__ import annotations

from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.transition import TransitionResult, apply_action


def _setup() -> tuple[CanonicalState, int]:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    ctx = HandContext(hand_id=0, deck_seed=42_000, button_seat=0,
                      initial_stacks=(10_000,) * 6)
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

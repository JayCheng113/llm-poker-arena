"""Tests for compute_legal_tool_set dispatched against CanonicalState shapes."""
from __future__ import annotations

from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.legal_actions import compute_legal_tool_set


def _state() -> CanonicalState:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    ctx = HandContext(hand_id=0, deck_seed=42_000, button_seat=0,
                      initial_stacks=(10_000,) * 6)
    return CanonicalState(cfg, ctx)


def test_preflop_utg_has_fold_call_raise_options() -> None:
    s = _state()
    actor = int(getattr(s._state, "actor_index", None) or getattr(s._state, "actor", 0) or 0)
    # Pull the actor from PokerKit; this is the first-to-act preflop.
    legal = compute_legal_tool_set(s, actor)
    names = {t.name for t in legal.tools}
    # UTG faces a BB bet; must be able to fold, call, or raise.
    assert "fold" in names
    assert "call" in names
    assert "raise_to" in names


def test_legal_tool_set_is_never_empty_for_required_actor() -> None:
    s = _state()
    actor = int(getattr(s._state, "actor_index", None) or getattr(s._state, "actor", 0) or 0)
    legal = compute_legal_tool_set(s, actor)
    assert len(legal.tools) > 0

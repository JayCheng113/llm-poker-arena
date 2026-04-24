"""Hypothesis: 52 unique cards are preserved after each hand (including post-showdown)."""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine._internal.audit import audit_cards_invariant
from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine._internal.rebuy import derive_deck_seed, run_single_hand
from llm_poker_arena.engine.config import HandContext, SessionConfig


def _cfg(seed: int) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=seed,
    )


@given(
    rng_seed=st.integers(min_value=0, max_value=10_000),
    button_seat=st.integers(min_value=0, max_value=5),
    hand_id=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=200, deadline=None)
def test_cards_invariant_after_hand(rng_seed: int, button_seat: int, hand_id: int) -> None:
    cfg = _cfg(rng_seed)
    ctx = HandContext(
        hand_id=hand_id, deck_seed=derive_deck_seed(rng_seed, hand_id),
        button_seat=button_seat, initial_stacks=(10_000,) * 6,
    )
    agents = [RandomAgent() for _ in range(6)]
    run_single_hand(cfg, ctx, agents)  # end-of-hand audit runs inside driver.


@given(
    rng_seed=st.integers(min_value=0, max_value=10_000),
    button_seat=st.integers(min_value=0, max_value=5),
    hand_id=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=50, deadline=None)
def test_cards_invariant_mid_hand(rng_seed: int, button_seat: int, hand_id: int) -> None:
    cfg = _cfg(rng_seed)
    ctx = HandContext(
        hand_id=hand_id, deck_seed=derive_deck_seed(rng_seed, hand_id),
        button_seat=button_seat, initial_stacks=(10_000,) * 6,
    )
    state = CanonicalState(cfg, ctx)
    audit_cards_invariant(state)  # fresh post-deal state

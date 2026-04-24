"""PlayerView projection must be pure — no hidden state mutation, repeatable output."""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine._internal.rebuy import derive_deck_seed
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.projections import build_player_view


@given(
    rng_seed=st.integers(min_value=0, max_value=5_000),
    hand_id=st.integers(min_value=0, max_value=100),
    button_seat=st.integers(min_value=0, max_value=5),
    actor=st.integers(min_value=0, max_value=5),
    turn_seed=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=200, deadline=None)
def test_build_player_view_is_pure(
    rng_seed: int, hand_id: int, button_seat: int, actor: int, turn_seed: int
) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=rng_seed,
    )
    ctx = HandContext(
        hand_id=hand_id, deck_seed=derive_deck_seed(rng_seed, hand_id),
        button_seat=button_seat, initial_stacks=(10_000,) * 6,
    )
    state = CanonicalState(cfg, ctx)
    a = build_player_view(state, actor, turn_seed=turn_seed)
    b = build_player_view(state, actor, turn_seed=turn_seed)
    assert a == b

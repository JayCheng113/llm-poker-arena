"""§3.5 auto-rebuy: every hand starts with all seats at starting_stack."""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine._internal.rebuy import derive_deck_seed, run_single_hand
from llm_poker_arena.engine.config import HandContext, SessionConfig


@given(
    rng_seed=st.integers(min_value=0, max_value=5_000),
    hand_id=st.integers(min_value=0, max_value=50),
)
@settings(max_examples=100, deadline=None)
def test_next_hand_starts_fresh(rng_seed: int, hand_id: int) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=rng_seed,
    )
    # Play previous hand to arbitrary final stacks.
    prev_ctx = HandContext(
        hand_id=hand_id, deck_seed=derive_deck_seed(rng_seed, hand_id),
        button_seat=hand_id % 6, initial_stacks=(10_000,) * 6,
    )
    agents = [RandomAgent() for _ in range(6)]
    run_single_hand(cfg, prev_ctx, agents)

    # Construct the NEXT hand with auto-rebuy: initial_stacks reset.
    next_ctx = HandContext(
        hand_id=hand_id + 1,
        deck_seed=derive_deck_seed(rng_seed, hand_id + 1),
        button_seat=(hand_id + 1) % 6,
        initial_stacks=(10_000,) * 6,
    )
    state = CanonicalState(cfg, next_ctx)
    raw = state._state  # noqa: SLF001
    stacks = tuple(int(x) for x in (getattr(raw, "stacks", ()) or ()))
    # After SB/BB auto-post, stacks reflect starting_stack minus blinds at those seats.
    assert stacks[state.sb_seat] == 10_000 - cfg.sb
    assert stacks[state.bb_seat] == 10_000 - cfg.bb
    for i in range(6):
        if i not in (state.sb_seat, state.bb_seat):
            assert stacks[i] == 10_000

"""MVP 5 exit: 50,000 hands with RandomAgent. No crash. Run with `pytest -m slow`."""

from __future__ import annotations

import pytest

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine._internal.rebuy import derive_deck_seed, run_single_hand
from llm_poker_arena.engine.config import HandContext, SessionConfig


@pytest.mark.slow
def test_50k_random_hands_no_audit_failure() -> None:
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
        rng_seed=2026,
    )
    agents = [RandomAgent() for _ in range(6)]
    total = 50_000
    for hand_id in range(total):
        ctx = HandContext(
            hand_id=hand_id,
            deck_seed=derive_deck_seed(cfg.rng_seed, hand_id),
            button_seat=hand_id % 6,
            initial_stacks=(10_000,) * 6,
        )
        result = run_single_hand(cfg, ctx, agents)
        assert sum(result.final_stacks) == cfg.starting_stack * cfg.num_players

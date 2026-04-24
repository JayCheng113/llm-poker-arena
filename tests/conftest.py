"""Shared pytest fixtures for llm-poker-arena tests."""
from __future__ import annotations

from collections.abc import Callable

import pytest

from llm_poker_arena.engine.config import HandContext, SessionConfig


@pytest.fixture
def sample_config() -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )


@pytest.fixture
def hand_context_factory(
    sample_config: SessionConfig,
) -> Callable[..., HandContext]:
    from llm_poker_arena.engine._internal.rebuy import derive_deck_seed

    def _make(hand_id: int, button_seat: int | None = None) -> HandContext:
        btn = button_seat if button_seat is not None else hand_id % sample_config.num_players
        return HandContext(
            hand_id=hand_id,
            deck_seed=derive_deck_seed(sample_config.rng_seed, hand_id),
            button_seat=btn,
            initial_stacks=(sample_config.starting_stack,) * sample_config.num_players,
        )

    return _make

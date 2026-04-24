"""Tests for derive_deck_seed and run_single_hand."""

from __future__ import annotations

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine._internal.rebuy import (
    HandResult,
    derive_deck_seed,
    run_single_hand,
)
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


def test_derive_deck_seed_deterministic() -> None:
    a = derive_deck_seed(42, 7)
    b = derive_deck_seed(42, 7)
    assert a == b


def test_derive_deck_seed_varies_per_hand_id() -> None:
    seeds = {derive_deck_seed(42, h) for h in range(100)}
    assert len(seeds) == 100  # all distinct at true 63-bit entropy


def test_run_single_hand_completes_without_crash() -> None:
    cfg = _cfg()
    ctx = HandContext(
        hand_id=0,
        deck_seed=derive_deck_seed(cfg.rng_seed, 0),
        button_seat=0,
        initial_stacks=(10_000,) * 6,
    )
    agents = [RandomAgent() for _ in range(6)]
    result = run_single_hand(cfg, ctx, agents)
    assert isinstance(result, HandResult)
    assert sum(result.final_stacks) == cfg.starting_stack * cfg.num_players
    assert len(result.action_trace) >= 1, "expected at least one action in the hand"


def test_run_single_hand_reproducible_for_same_context_and_agent_seeds() -> None:
    cfg = _cfg()
    ctx = HandContext(
        hand_id=5,
        deck_seed=derive_deck_seed(cfg.rng_seed, 5),
        button_seat=2,
        initial_stacks=(10_000,) * 6,
    )
    agents_a = [RandomAgent() for _ in range(6)]
    agents_b = [RandomAgent() for _ in range(6)]
    r1 = run_single_hand(cfg, ctx, agents_a)
    r2 = run_single_hand(cfg, ctx, agents_b)
    # Same PlayerView.turn_seed flow → deterministic agent choices → same outcome.
    assert r1.final_stacks == r2.final_stacks
    assert r1.action_trace == r2.action_trace


def test_run_single_hand_rejects_mismatched_agents_length() -> None:
    import pytest

    cfg = _cfg()
    ctx = HandContext(
        hand_id=0,
        deck_seed=derive_deck_seed(cfg.rng_seed, 0),
        button_seat=0,
        initial_stacks=(10_000,) * 6,
    )
    agents = [RandomAgent() for _ in range(3)]  # 3 agents, but config wants 6
    with pytest.raises(ValueError, match="agents length"):
        run_single_hand(cfg, ctx, agents)

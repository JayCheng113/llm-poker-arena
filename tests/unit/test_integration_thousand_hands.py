"""MVP 4 exit criterion: 1,000 hands with RandomAgent, zero crashes, zero audit failures."""
from __future__ import annotations

from collections.abc import Callable

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine._internal.rebuy import run_single_hand
from llm_poker_arena.engine.config import HandContext, SessionConfig


def test_thousand_random_hands_complete(
    sample_config: SessionConfig,
    hand_context_factory: Callable[..., HandContext],
) -> None:
    cfg = sample_config._replace(num_hands=1_002) if hasattr(sample_config, "_replace") else sample_config
    agents = [RandomAgent() for _ in range(6)]
    failures = 0
    total = 1_000
    for hand_id in range(total):
        ctx = hand_context_factory(hand_id)
        result = run_single_hand(cfg, ctx, agents)
        # Auto-rebuy invariant: every hand starts from starting_stack.
        assert sum(result.final_stacks) == cfg.starting_stack * cfg.num_players
        if not result.final_stacks:
            failures += 1
    assert failures == 0

"""Baseline session runners — spec §15.2 B1 (Random) and B2 (RuleBased).

Thin convenience wrappers over `session.session.Session`. Each runner
produces a full Phase-2a session directory under `output_dir` and returns
the path for downstream analysis. The `num_hands` default (120 = 20 × 6)
satisfies the `num_hands % num_players == 0` constraint without being
so small that per-seat VPIP is dominated by noise.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _default_config(num_hands: int, rng_seed: int) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=rng_seed,
    )


def run_random_baseline(
    output_dir: Path, *, num_hands: int = 120, rng_seed: int = 42,
) -> Path:
    """Run a B1 session (6× RandomAgent) into `output_dir` and return it."""
    cfg = _default_config(num_hands=num_hands, rng_seed=rng_seed)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(
        config=cfg, agents=agents, output_dir=output_dir,
        session_id="b1_random",
    )
    asyncio.run(sess.run())
    return output_dir


def run_rule_based_baseline(
    output_dir: Path, *, num_hands: int = 120, rng_seed: int = 42,
) -> Path:
    """Run a B2 session (6× RuleBasedAgent) into `output_dir` and return it."""
    cfg = _default_config(num_hands=num_hands, rng_seed=rng_seed)
    agents = [RuleBasedAgent() for _ in range(6)]
    sess = Session(
        config=cfg, agents=agents, output_dir=output_dir,
        session_id="b2_rule_based",
    )
    asyncio.run(sess.run())
    return output_dir

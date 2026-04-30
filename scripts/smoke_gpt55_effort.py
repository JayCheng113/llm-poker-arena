#!/usr/bin/env python3
"""1-hand smoke for gpt-5.5 with reasoning_effort=medium — verify the
new MODEL_OVERRIDES route through correctly + thinking summary
actually appears in the artifact stream (was nearly empty under the
prior hardcoded effort=low default)."""

# ruff: noqa: E402
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.prompt_profile import (
    load_default_prompt_profile,
    with_overrides,
)
from llm_poker_arena.agents.llm.providers.registry import (
    PROVIDERS,
    make_provider,
    resolved_temperature,
)
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def main() -> None:
    api_key = os.environ.get(PROVIDERS["openai"].env_var)
    if not api_key:
        sys.exit(f"{PROVIDERS['openai'].env_var} not set; source .env first")

    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=True,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
        # Effort=medium will spend more reasoning tokens. 200K cap at
        # gpt-5.5 ($5/$30) ≈ $1.50 absolute ceiling for this 6-hand smoke.
        max_total_tokens=200_000,
    )
    provider = make_provider("openai", "gpt-5.5", api_key)
    # rationale_required=False for gpt-5.x family (existing rule)
    profile = with_overrides(load_default_prompt_profile(), rationale_required=False)
    gpt = LLMAgent(
        provider=provider, model="gpt-5.5",
        temperature=resolved_temperature("openai", 0.7, model="gpt-5.5"),
        prompt_profile=profile,
        total_turn_timeout_sec=200.0,
    )
    agents = [
        RuleBasedAgent(),  # 0
        RuleBasedAgent(),  # 1
        gpt,               # 2 (BB)  ← GPT-5.5 medium effort
        RuleBasedAgent(),  # 3
        RuleBasedAgent(),  # 4
        RuleBasedAgent(),  # 5
    ]

    session_dir = _REPO / "runs" / "smoke-gpt55-medium"
    if session_dir.exists():
        shutil.rmtree(session_dir)

    sess = Session(config=cfg, agents=agents, output_dir=session_dir,
                   session_id="smoke-gpt55-medium")
    asyncio.run(sess.run())
    print(f"\n✓ smoke complete → {session_dir}/meta.json")


if __name__ == "__main__":
    main()

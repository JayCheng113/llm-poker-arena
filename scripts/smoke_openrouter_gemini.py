#!/usr/bin/env python3
"""One-shot 6-hand smoke for gemini-3.1-pro-preview through OpenRouter.

Verifies the new "openrouter" provider config (added to registry.py
2026-04-29) actually returns valid responses for the gemini-3.1-pro-
preview model id. If this works, the full 6-flagship lineup can use
openrouter for the Gemini seat instead of falling back to gemini-2.5-pro
on AI Studio.

Cost ceiling: max_total_tokens=200_000 (~$0.40 even at gemini-3.1-pro
output rates of $12/M).
"""

# ruff: noqa: E402 — sys.path shim must run before src/ imports
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.registry import (
    PROVIDERS,
    make_provider,
    resolved_temperature,
)
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def main() -> None:
    api_key = os.environ.get(PROVIDERS["openrouter"].env_var)
    if not api_key:
        sys.exit(
            f"{PROVIDERS['openrouter'].env_var} not set; sign up at "
            f"https://openrouter.ai and add the key to .env"
        )

    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=True,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
        max_total_tokens=200_000,
    )
    provider = make_provider(
        "openrouter", "google/gemini-3.1-pro-preview", api_key
    )
    gemini = LLMAgent(
        provider=provider, model="google/gemini-3.1-pro-preview",
        temperature=resolved_temperature(
            "openrouter", 0.7, model="google/gemini-3.1-pro-preview"
        ),
        per_iteration_timeout_sec=90.0,
        total_turn_timeout_sec=200.0,
    )
    agents = [
        RuleBasedAgent(),  # 0
        RuleBasedAgent(),  # 1
        RuleBasedAgent(),  # 2
        gemini,            # 3 (UTG) ← Gemini 3.1 Pro Preview via OpenRouter
        RuleBasedAgent(),  # 4
        RuleBasedAgent(),  # 5
    ]

    session_dir = _REPO / "runs" / "smoke-openrouter-gemini"
    if session_dir.exists():
        shutil.rmtree(session_dir)

    sess = Session(config=cfg, agents=agents, output_dir=session_dir,
                   session_id="smoke-openrouter-gemini")
    asyncio.run(sess.run())
    print(f"\n✓ smoke complete → {session_dir}/meta.json")


if __name__ == "__main__":
    main()

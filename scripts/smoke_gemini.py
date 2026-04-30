#!/usr/bin/env python3
"""One-shot 1-hand smoke for gemini-3.1-pro through the existing
OpenAI-compatible shim (https://generativelanguage.googleapis.com/v1beta/openai/).

USAGE.md L312-313 explicitly warns:
  "The `gemini-3.x` family that public docs reference is on Vertex AI,
   not AI Studio's OpenAI-compat endpoint — use `gemini-2.5-*` here."

This smoke verifies that warning empirically. Three possible outcomes:
  1. Works → great, we use gemini-3.1-pro in the flagship lineup
  2. 404 / model_not_found → fall back to gemini-2.5-pro (still flagship,
     $1.25/$10 vs $2/$12, mature/tested path)
  3. Other 4xx (auth/quota/format) → diagnose, may be fixable

Cost ceiling: max_total_tokens=50_000 (~$0.10 even at gemini-3.1-pro
rates).
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
    api_key = os.environ.get(PROVIDERS["gemini"].env_var)
    if not api_key:
        sys.exit(f"{PROVIDERS['gemini'].env_var} not set; source .env first")

    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        # num_hands must be a multiple of num_players (engine constraint
        # for balanced button rotation). 6 is the floor for 6 players.
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=True,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
        # 6 hands × ~5K tokens × gemini-3.1-pro $2/$12 ≈ $0.30 ceiling.
        # 200K cap gives the kill-switch headroom over a 5x verbosity
        # surprise.
        max_total_tokens=200_000,
    )
    # Use the same registry path the real generator uses, so success
    # here means success in the full lineup. Includes the
    # double-extra_body Gemini quirk + 503 retry headroom.
    provider = make_provider("gemini", "gemini-3.1-pro", api_key)
    gemini = LLMAgent(
        provider=provider, model="gemini-3.1-pro",
        temperature=resolved_temperature("gemini", 0.7, model="gemini-3.1-pro"),
        # Gemini sometimes hits 503 spikes; AsyncOpenAI's exponential
        # backoff (sdk_max_retries=5 from registry) needs ~30-60s.
        # Bump per-iteration timeout above the SDK's worst-case backoff.
        per_iteration_timeout_sec=90.0,
        total_turn_timeout_sec=200.0,
    )
    agents = [
        RuleBasedAgent(),  # 0
        RuleBasedAgent(),  # 1
        RuleBasedAgent(),  # 2
        gemini,            # 3 (UTG) ← Gemini 3.1 Pro
        RuleBasedAgent(),  # 4
        RuleBasedAgent(),  # 5
    ]

    session_dir = _REPO / "runs" / "smoke-gemini-3.1-pro"
    if session_dir.exists():
        shutil.rmtree(session_dir)

    sess = Session(config=cfg, agents=agents, output_dir=session_dir,
                   session_id="smoke-gemini-3.1-pro")
    asyncio.run(sess.run())
    print(f"\n✓ smoke-gemini-3.1-pro complete → {session_dir}/meta.json")


if __name__ == "__main__":
    main()

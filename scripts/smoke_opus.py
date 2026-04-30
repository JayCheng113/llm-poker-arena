#!/usr/bin/env python3
"""One-shot 1-hand smoke for claude-opus-4-7 — measures real per-turn
output tokens to bound the flagship-experiment cost projection.

Per the codex review of the flagship-LLM experiment plan: before
spending $50-200 on a 6-flagship 102-hand tournament, replace the
guessed "Opus is 1-3x more verbose than Sonnet" multiplier with one
real measurement. ~$0.05-0.20 spend.

The current AnthropicProvider does NOT pass `thinking={...}` to the
SDK (anthropic_provider.py L13: "Out of scope: extended-thinking"),
so this smoke measures Opus in *standard* mode — the only mode the
codebase can currently produce. If the Opus token count looks sane
here, the codex worst-case ($382 thinking-on bracket) is structurally
unreachable without provider code changes.

Output: runs/smoke-opus/ (canonical) — meta.json has the numbers.
NOT bundled to web/, this is a measurement run.
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
from llm_poker_arena.agents.llm.providers.anthropic_provider import AnthropicProvider
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set; source .env first")

    # 6 hands = one full button rotation, Opus at seat 3 plays each
    # position once. Single-hand mode would only give 1-4 turns of
    # Opus token data (Opus might just fold preflop) — too thin for a
    # per-100-hand cost extrapolation that drives a $50-200 decision.
    # 6 hands at flagship-Sonnet baseline rates was ~$0.04/hand × 6
    # ≈ $0.24; at Opus prices (5x input, 5x output, plus the
    # documented 35% tokenizer bloat), expect ~$0.30-1.20.
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=True,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
        # Hard kill-switch: 100K tokens at Opus prices (~$5 input,
        # $25 output, conservative average) ≈ $1.25-2 absolute ceiling
        # — bumped from earlier 100K only-1-hand scope. If the run
        # hits this, Opus is far more verbose than the prior session
        # data suggested and the full experiment plan needs revisiting.
        max_total_tokens=200_000,
    )
    provider = AnthropicProvider(
        model="claude-opus-4-7",
        api_key=api_key,
        # Opus 4.7 routinely produces longer rationales than Sonnet —
        # bump from the 1024 default so we don't truncate and skew the
        # token measurement low.
        max_tokens=4096,
    )
    opus = LLMAgent(
        provider=provider, model="claude-opus-4-7",
        temperature=0.7,
        total_turn_timeout_sec=180.0,  # Opus is slower than Sonnet
    )
    agents = [
        RuleBasedAgent(),  # 0 (BTN at hand 0, button=0)
        RuleBasedAgent(),  # 1 (SB)
        RuleBasedAgent(),  # 2 (BB)
        opus,              # 3 (UTG) ← Opus 4.7
        RuleBasedAgent(),  # 4 (HJ)
        RuleBasedAgent(),  # 5 (CO)
    ]

    session_dir = _REPO / "runs" / "smoke-opus"
    if session_dir.exists():
        shutil.rmtree(session_dir)

    sess = Session(config=cfg, agents=agents, output_dir=session_dir,
                   session_id="smoke-opus")
    asyncio.run(sess.run())
    print(f"\n✓ smoke-opus complete → {session_dir}/meta.json")


if __name__ == "__main__":
    main()

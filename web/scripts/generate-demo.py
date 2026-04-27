#!/usr/bin/env python3
"""Generate the Phase 1 hardcoded demo session.

Recipe (per Web UI spec §213):
  - Lineup: Claude Haiku 4.5 (seat 3) + 5 RuleBasedAgent (seats 0,1,2,4,5)
  - 6 hands, seed=42, all flags on
  - Cost ~$0.05 at Claude Haiku 4.5 rates

Output: runs/demo-1/ then copy to web/public/data/demo-1/

Usage:
  source <(sed -n '3s/^#//p' ~/.zprofile)  # load ANTHROPIC_API_KEY
  python web/scripts/generate-demo.py
"""
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

# src/ layout package — insert repo root/src on sys.path
# (codex BLOCKER fix: bare _REPO doesn't expose llm_poker_arena/)
_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.anthropic_provider import AnthropicProvider
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set; source your env vars first")

    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=True,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    llm = LLMAgent(provider=provider, model="claude-haiku-4-5",
                   temperature=0.7, total_turn_timeout_sec=60.0)
    agents = [
        RuleBasedAgent(),  # 0 (BTN at hand 0)
        RuleBasedAgent(),  # 1 (SB)
        RuleBasedAgent(),  # 2 (BB)
        llm,               # 3 (UTG) ← Claude
        RuleBasedAgent(),  # 4 (HJ)
        RuleBasedAgent(),  # 5 (CO)
    ]

    output_root = _REPO / "runs"
    session_dir = output_root / "demo-1"
    if session_dir.exists():
        shutil.rmtree(session_dir)

    sess = Session(config=cfg, agents=agents, output_dir=session_dir,
                   session_id="demo-1")
    asyncio.run(sess.run())

    # Copy to web/public/data/demo-1/ (overwrite if exists)
    web_target = _REPO / "web" / "public" / "data" / "demo-1"
    if web_target.exists():
        shutil.rmtree(web_target)
    web_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(session_dir, web_target)

    # Pre-flight 12: auto-rebuild the web manifest.
    bundle_script = _REPO / "web" / "scripts" / "bundle-demos.mjs"
    try:
        subprocess.run(["node", str(bundle_script)], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"warning: manifest rebuild skipped ({e}); "
              f"run `node {bundle_script}` manually.", file=sys.stderr)

    print("Demo session generated:")
    print("  runs/demo-1/ (canonical)")
    print("  web/public/data/demo-1/ (web bundle)")


if __name__ == "__main__":
    main()

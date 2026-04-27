#!/usr/bin/env python3
"""Generate the all-bot baseline demo session (no API cost).

Recipe:
  - Lineup: 6 RuleBasedAgent
  - 60 hands (10 button rotations), seed=7
  - Cost: $0 (no LLM calls)

Output: runs/demo-bots/ then copy to web/public/data/demo-bots/

Usage:
  .venv/bin/python web/scripts/generate-demo-bots.py
"""
import argparse
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force", action="store_true",
        help="overwrite existing runs/demo-bots/ and web/public/data/demo-bots/. "
             "Without this flag the script aborts if either dir exists.",
    )
    args = parser.parse_args()

    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=0,
        enable_math_tools=False,
        enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=7,
    )
    agents = [RuleBasedAgent() for _ in range(6)]

    output_root = _REPO / "runs"
    session_dir = output_root / "demo-bots"
    web_target = _REPO / "web" / "public" / "data" / "demo-bots"
    # Pre-flight 4 (rev): also guard the bot generator (codex P2).
    for d in (session_dir, web_target):
        if d.exists() and not args.force:
            sys.exit(
                f"refusing to overwrite existing {d}\n"
                f"pass --force to delete it."
            )
    if session_dir.exists():
        shutil.rmtree(session_dir)

    sess = Session(config=cfg, agents=agents, output_dir=session_dir,
                   session_id="demo-bots")
    asyncio.run(sess.run())

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

    print("All-bot baseline session generated:")
    print(f"  runs/demo-bots/ (canonical)")
    print(f"  web/public/data/demo-bots/ (web bundle)")


if __name__ == "__main__":
    main()

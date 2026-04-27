#!/usr/bin/env python3
"""Generate the multi-LLM tournament demo session.

Recipe:
  - Lineup: Claude Haiku 4.5 (seat 0) + deepseek-chat (seat 2) +
            gpt-5.4-mini (seat 4) + qwen3.6-plus (seat 5) +
            2 RuleBased (seats 1, 3)
  - Hands: 30 (5 full button rotations) — overridable via --hands
  - Seed: 17
  - max_total_tokens=1_000_000 ($1 budget cap)

Note on DeepSeek model: we use legacy alias 'deepseek-chat' (= v4-flash
non-thinking mode) instead of 'deepseek-v4-flash' directly because the
latter sometimes enters thinking mode and demands `reasoning_content`
roundtrips that our OpenAI-compatible provider doesn't handle. The
'deepseek-chat' alias is deprecated 2026-07-24; until then it's the
clean path. (Tested empirically: v4-flash had hands 0+10 censored due
to thinking-mode protocol violations.)

Output: runs/demo-tournament/ then copy to web/public/data/demo-tournament/

Usage:
  .venv/bin/python web/scripts/generate-demo-tournament.py            # 30 hands
  .venv/bin/python web/scripts/generate-demo-tournament.py --hands 6  # smoke
"""
import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

# Manual .env loader (no python-dotenv dep)
_env_file = _REPO / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.registry import (
    PROVIDERS,
    make_provider,
    resolved_temperature,
)
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

# Per-seat lineup: (provider_tag, model) or None for a RuleBased bot.
# Sourced from registry so URL/env-var changes flow through.
SEAT_LINEUP: tuple[tuple[str, str] | None, ...] = (
    ("anthropic", "claude-haiku-4-5"),  # 0
    None,                                # 1 RuleBased
    ("deepseek", "deepseek-chat"),       # 2
    None,                                # 3 RuleBased
    ("openai", "gpt-5.4-mini"),          # 4
    ("qwen", "qwen3.6-plus"),            # 5
)
REQUIRED_ENV = tuple(
    PROVIDERS[tag].env_var for slot in SEAT_LINEUP if slot is not None
    for tag, _ in [slot]
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hands", type=int, default=30,
                        help="hands to play (must be multiple of 6; default 30)")
    parser.add_argument("--out", default="demo-tournament",
                        help="session id / output dir name")
    parser.add_argument(
        "--force", action="store_true",
        help="overwrite existing runs/<out>/ and web/public/data/<out>/. "
             "Without this flag the script aborts if either dir exists.",
    )
    args = parser.parse_args()

    if args.hands % 6 != 0:
        sys.exit(f"--hands ({args.hands}) must be a multiple of 6 (6 players)")

    for k in REQUIRED_ENV:
        if not os.environ.get(k):
            sys.exit(f"{k} not set; check .env")

    # Pre-flight 4: refuse to clobber existing artifacts unless --force.
    session_dir = _REPO / "runs" / args.out
    web_target = _REPO / "web" / "public" / "data" / args.out
    for dir_to_check in (session_dir, web_target):
        if dir_to_check.exists() and not args.force:
            sys.exit(
                f"refusing to overwrite existing {dir_to_check}\n"
                f"pass --force to delete it, or pick a new --out name."
            )

    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=args.hands, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=True,
        rationale_required=True,
        opponent_stats_min_samples=10,
        rng_seed=17,
        max_total_tokens=1_000_000,  # $1 budget cap
    )

    agents = []
    for slot in SEAT_LINEUP:
        if slot is None:
            agents.append(RuleBasedAgent())
            continue
        provider_tag, model = slot
        api_key = os.environ[PROVIDERS[provider_tag].env_var]
        agents.append(
            LLMAgent(
                provider=make_provider(provider_tag, model, api_key),
                model=model,
                temperature=resolved_temperature(provider_tag, 0.7, model=model),
                total_turn_timeout_sec=60.0,
            )
        )

    if session_dir.exists():
        shutil.rmtree(session_dir)

    sess = Session(config=cfg, agents=agents, output_dir=session_dir,
                   session_id=args.out)
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

    print(f"Tournament session generated:")
    print(f"  runs/{args.out}/")
    print(f"  web/public/data/{args.out}/")


if __name__ == "__main__":
    main()

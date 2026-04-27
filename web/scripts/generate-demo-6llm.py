#!/usr/bin/env python3
"""Generate the 6-LLM showdown — every seat is a different provider.

Recipe:
  - seat 0: Claude Haiku 4.5            (Anthropic)
  - seat 1: deepseek-chat               (DeepSeek, non-thinking alias)
  - seat 2: gpt-5.4-mini                (OpenAI)
  - seat 3: qwen3.6-plus                (Alibaba Qwen via DashScope)
  - seat 4: kimi-k2.5                   (Moonshot Kimi)
  - seat 5: gemini-2.5-flash            (Google AI Studio, OpenAI-compat shim)
  - Hands: 30 (default; --hands 6 for smoke)
  - Seed: 23 (different from demo-tournament=17 to give a fresh deal)
  - max_total_tokens=2_000_000 ($2 budget cap; with 6 LLMs costs grow ~50%
    over the 4-LLM tournament so we lift the ceiling).

All six models are picked from the same "small/fast" tier (Anthropic
Haiku, OpenAI mini, Google Flash, etc.) so the showdown compares
similar-capability models rather than mixing flagship vs. budget.

Usage:
  .venv/bin/python web/scripts/generate-demo-6llm.py            # 30 hands
  .venv/bin/python web/scripts/generate-demo-6llm.py --hands 6  # smoke
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
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

# Six providers, one seat each — sourced from the registry so adding a
# provider there auto-extends the env-key check.
SEAT_LINEUP: tuple[tuple[str, str], ...] = (
    ("anthropic", "claude-haiku-4-5"),       # seat 0
    ("deepseek", "deepseek-chat"),           # seat 1
    ("openai", "gpt-5.4-mini"),              # seat 2
    ("qwen", "qwen3.6-plus"),                # seat 3
    ("kimi", "kimi-k2.5"),                   # seat 4
    ("gemini", "gemini-2.5-flash"),          # seat 5
)
REQUIRED_ENV = tuple(PROVIDERS[tag].env_var for tag, _ in SEAT_LINEUP)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hands", type=int, default=30,
                        help="hands to play (must be multiple of 6; default 30)")
    parser.add_argument("--out", default="demo-6llm",
                        help="session id / output dir name")
    parser.add_argument(
        "--force", action="store_true",
        help="overwrite existing runs/<out>/ and web/public/data/<out>/. "
             "Without this flag the script aborts if either dir exists, "
             "so a $1+ tournament run is not silently nuked.",
    )
    args = parser.parse_args()

    if args.hands % 6 != 0:
        sys.exit(f"--hands ({args.hands}) must be a multiple of 6 (6 players)")

    for k in REQUIRED_ENV:
        if not os.environ.get(k):
            sys.exit(f"{k} not set; check .env")

    # Pre-flight 4: refuse to clobber an existing run unless --force.
    # Why: the prior behaviour was a silent shutil.rmtree before each run,
    # which once cost a 30-hand 6-LLM tournament to a typo'd --out arg.
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
        rng_seed=23,
        max_total_tokens=2_000_000,  # $2 budget cap (6 LLMs)
    )

    # Pre-flight 2 (rev): timeout geometry math.
    #   MAX_API_RETRY=2 ⇒ 3 wait_for(per_iter_timeout) calls
    #   per_iter_timeout = 60s (LLMAgent default)
    #   inter-retry backoff ≈ 0.5–1.0s × 2 sleeps
    # Worst case before total_turn_timeout fires: 3*60 + 2*1 = 182s.
    # 180s (the LLMAgent default) RACES this and would false-positive
    # TotalTurnTimeout exactly when a 3rd retry was about to succeed —
    # codex P0 finding before the 30-hand official tournament.
    # 200s gives ~18s of headroom for OS / network jitter.
    # Kimi keeps a wider envelope because per-call latency p95 is ~45s
    # (observed during smoke), so any retry burns most of one window.
    NORMAL_TIMEOUT = 200.0
    SLOW_TIMEOUT = 260.0
    SLOW_PROVIDERS = {"kimi"}  # observed to need extra headroom

    agents = []
    for provider_tag, model in SEAT_LINEUP:
        api_key = os.environ[PROVIDERS[provider_tag].env_var]
        timeout = SLOW_TIMEOUT if provider_tag in SLOW_PROVIDERS else NORMAL_TIMEOUT
        agents.append(
            LLMAgent(
                provider=make_provider(provider_tag, model, api_key),
                model=model,
                # resolved_temperature pins kimi:kimi-k2.5 to 1.0; every
                # other (provider, model) pair gets the requested 0.7.
                temperature=resolved_temperature(provider_tag, 0.7, model=model),
                total_turn_timeout_sec=timeout,
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

    # Pre-flight 12: auto-rebuild the web manifest so the new session is
    # immediately picked up by the picker without a separate bundle step.
    # No-op (with a warning) if node isn't installed — the artifacts are
    # already on disk and the user can run `node web/scripts/bundle-demos.mjs`
    # later by hand.
    bundle_script = _REPO / "web" / "scripts" / "bundle-demos.mjs"
    try:
        subprocess.run(["node", str(bundle_script)], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"warning: manifest rebuild skipped ({e}); "
              f"run `node {bundle_script}` manually.", file=sys.stderr)

    print(f"6-LLM session generated:")
    print(f"  runs/{args.out}/")
    print(f"  web/public/data/{args.out}/")


if __name__ == "__main__":
    main()

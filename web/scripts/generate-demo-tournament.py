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
from llm_poker_arena.agents.llm.providers.anthropic_provider import AnthropicProvider
from llm_poker_arena.agents.llm.providers.openai_compatible import OpenAICompatibleProvider
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hands", type=int, default=30,
                        help="hands to play (must be multiple of 6; default 30)")
    parser.add_argument("--out", default="demo-tournament",
                        help="session id / output dir name")
    args = parser.parse_args()

    if args.hands % 6 != 0:
        sys.exit(f"--hands ({args.hands}) must be a multiple of 6 (6 players)")

    for k in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "QWEN_API_KEY"):
        if not os.environ.get(k):
            sys.exit(f"{k} not set; check .env")

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

    claude = LLMAgent(
        provider=AnthropicProvider(
            model="claude-haiku-4-5",
            api_key=os.environ["ANTHROPIC_API_KEY"],
        ),
        model="claude-haiku-4-5",
        temperature=0.7, total_turn_timeout_sec=60.0,
    )
    deepseek = LLMAgent(
        provider=OpenAICompatibleProvider(
            provider_name_value="deepseek",
            model="deepseek-chat",
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com/v1",
        ),
        model="deepseek-chat",
        temperature=0.7, total_turn_timeout_sec=60.0,
    )
    gpt = LLMAgent(
        provider=OpenAICompatibleProvider(
            provider_name_value="openai",
            model="gpt-5.4-mini",
            api_key=os.environ["OPENAI_API_KEY"],
        ),
        model="gpt-5.4-mini",
        temperature=0.7, total_turn_timeout_sec=60.0,
    )
    qwen = LLMAgent(
        provider=OpenAICompatibleProvider(
            provider_name_value="qwen",
            model="qwen3.6-plus",
            api_key=os.environ["QWEN_API_KEY"],
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        model="qwen3.6-plus",
        temperature=0.7, total_turn_timeout_sec=60.0,
    )
    agents = [
        claude,           # 0
        RuleBasedAgent(), # 1
        deepseek,         # 2
        RuleBasedAgent(), # 3
        gpt,              # 4
        qwen,             # 5
    ]

    session_dir = _REPO / "runs" / args.out
    if session_dir.exists():
        shutil.rmtree(session_dir)

    sess = Session(config=cfg, agents=agents, output_dir=session_dir,
                   session_id=args.out)
    asyncio.run(sess.run())

    web_target = _REPO / "web" / "public" / "data" / args.out
    if web_target.exists():
        shutil.rmtree(web_target)
    web_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(session_dir, web_target)

    print(f"Tournament session generated:")
    print(f"  runs/{args.out}/")
    print(f"  web/public/data/{args.out}/")


if __name__ == "__main__":
    main()

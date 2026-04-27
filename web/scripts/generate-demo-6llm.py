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
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

REQUIRED_ENV = (
    "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
    "QWEN_API_KEY", "KIMI_API_KEY", "GEMINI_API_KEY",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hands", type=int, default=30,
                        help="hands to play (must be multiple of 6; default 30)")
    parser.add_argument("--out", default="demo-6llm",
                        help="session id / output dir name")
    args = parser.parse_args()

    if args.hands % 6 != 0:
        sys.exit(f"--hands ({args.hands}) must be a multiple of 6 (6 players)")

    for k in REQUIRED_ENV:
        if not os.environ.get(k):
            sys.exit(f"{k} not set; check .env")

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
    kimi = LLMAgent(
        provider=OpenAICompatibleProvider(
            provider_name_value="kimi",
            model="kimi-k2.5",
            api_key=os.environ["KIMI_API_KEY"],
            # User's key is China-region — moonshot.cn (not the .ai
            # international endpoint, which 401s on this key)
            base_url="https://api.moonshot.cn/v1",
        ),
        model="kimi-k2.5",
        # Kimi K2.5 enforces temperature=1.0 (any other value 400s with
        # "invalid temperature: only 1 is allowed for this model").
        # Empirically observed during the first 6-LLM smoke — all 6
        # hands censored on seat 4 until this was fixed.
        temperature=1.0,
        # Kimi is noticeably slower than the other providers (China-region
        # latency + verbose internal reasoning). Default 60s timeout was
        # exceeded on 2/6 smoke hands — bump to 120s.
        total_turn_timeout_sec=120.0,
    )
    gemini = LLMAgent(
        provider=OpenAICompatibleProvider(
            provider_name_value="gemini",
            model="gemini-2.5-flash",
            api_key=os.environ["GEMINI_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
        model="gemini-2.5-flash",
        temperature=0.7, total_turn_timeout_sec=60.0,
    )

    agents = [claude, deepseek, gpt, qwen, kimi, gemini]

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

    print(f"6-LLM session generated:")
    print(f"  runs/{args.out}/")
    print(f"  web/public/data/{args.out}/")


if __name__ == "__main__":
    main()

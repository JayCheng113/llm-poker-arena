#!/usr/bin/env python3
"""Kimi-only debug session — fastest way to iterate on Kimi-specific
provider issues without burning tokens on the other 5 LLM seats.

Lineup: 5 RuleBased + 1 Kimi (seat 4). 6 hands.
"""
import asyncio
import os
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

_env = _REPO / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.openai_compatible import OpenAICompatibleProvider
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def main() -> None:
    if not os.environ.get("KIMI_API_KEY"):
        sys.exit("KIMI_API_KEY not set")

    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=True,
        rationale_required=True,
        opponent_stats_min_samples=10,
        rng_seed=23,
        max_total_tokens=1_000_000,
    )
    kimi = LLMAgent(
        provider=OpenAICompatibleProvider(
            provider_name_value="kimi",
            model="kimi-k2.5",
            api_key=os.environ["KIMI_API_KEY"],
            base_url="https://api.moonshot.cn/v1",
        ),
        model="kimi-k2.5",
        temperature=1.0, total_turn_timeout_sec=60.0,
    )
    agents = [
        RuleBasedAgent(),  # 0
        RuleBasedAgent(),  # 1
        RuleBasedAgent(),  # 2
        RuleBasedAgent(),  # 3
        kimi,              # 4
        RuleBasedAgent(),  # 5
    ]

    out = "kimi-probe"
    sd = _REPO / "runs" / out
    if sd.exists():
        shutil.rmtree(sd)

    sess = Session(config=cfg, agents=agents, output_dir=sd, session_id=out)
    asyncio.run(sess.run())

    # Quick summary
    import json
    m = json.load(open(sd / "meta.json"))
    print(f"\n=== Kimi probe ===")
    print(f"hands={m['total_hands_played']} censored={m['censored_hands_count']}")
    cs = (sd / "censored_hands.jsonl").read_text().splitlines()
    if cs:
        print(f"censored details:")
        for line in cs:
            c = json.loads(line)
            err = str(c.get('api_error', {}).get('detail', ''))
            print(f"  hand {c['hand_id']}: {err[:200]}")
    else:
        print("ALL HANDS CLEAN ✓")
    r = m['retry_summary_per_seat']['4']
    print(f"kimi retry: {r}")


if __name__ == "__main__":
    main()

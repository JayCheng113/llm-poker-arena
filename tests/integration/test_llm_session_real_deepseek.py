"""Real DeepSeek API smoke test (gated, NOT in CI).

Run only when both env vars are set:
  DEEPSEEK_INTEGRATION_TEST=1
  DEEPSEEK_API_KEY=sk-...

Costs ~$0.001-0.005 per run with deepseek-chat, longer with deepseek-reasoner.
6 hands (validator min) but only seat 3 is the LLM; other seats are RandomAgent.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

pytestmark = pytest.mark.skipif(
    os.getenv("DEEPSEEK_INTEGRATION_TEST") != "1"
    or not os.getenv("DEEPSEEK_API_KEY"),
    reason="needs DEEPSEEK_INTEGRATION_TEST=1 and DEEPSEEK_API_KEY set",
)


def test_real_deepseek_chat_plays_six_hands(tmp_path: Path) -> None:
    api_key = os.environ["DEEPSEEK_API_KEY"]
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    provider = OpenAICompatibleProvider(
        provider_name_value="deepseek", model="deepseek-chat",
        api_key=api_key, base_url="https://api.deepseek.com/v1",
    )
    llm_agent = LLMAgent(
        provider=provider, model="deepseek-chat",
        temperature=0.7, total_turn_timeout_sec=60.0,
    )
    agents = [
        RandomAgent(),  # seat 0 (BTN)
        RandomAgent(),  # SB
        RandomAgent(),  # BB
        llm_agent,      # UTG ← DeepSeek
        RandomAgent(),  # HJ
        RandomAgent(),  # CO
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="real_deepseek_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps
                 if json.loads(line)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots found"
    rec = llm_snaps[0]
    assert rec["agent"]["provider"] == "deepseek"
    assert rec["agent"]["model"] == "deepseek-chat"
    assert rec["iterations"], "no iterations recorded — provider plumbing broken"
    # deepseek-chat should NOT emit reasoning_content; artifacts empty.
    assert all(it.get("reasoning_artifacts", []) == []
               for it in rec["iterations"])
    final = rec["final_action"]
    legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
    assert final["type"] in legal_names

    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["provider_capabilities"]["3"]["provider"] == "deepseek"
    assert sum(meta["chip_pnl"].values()) == 0


def test_real_deepseek_probe_returns_observed_capability() -> None:
    api_key = os.environ["DEEPSEEK_API_KEY"]
    provider = OpenAICompatibleProvider(
        provider_name_value="deepseek", model="deepseek-chat",
        api_key=api_key, base_url="https://api.deepseek.com/v1",
    )
    cap = asyncio.run(provider.probe())
    assert cap.provider == "deepseek"
    assert cap.probed_at.endswith("Z")
    # deepseek-chat: seed accepted (DeepSeek docs say so), reasoning_kinds
    # = (UNAVAILABLE,) since V3 doesn't emit reasoning_content (probe
    # explicitly records "tested, none seen" per spec §4.6).
    from llm_poker_arena.agents.llm.types import ReasoningArtifactKind
    assert cap.seed_accepted is True
    assert cap.reasoning_kinds == (ReasoningArtifactKind.UNAVAILABLE,)

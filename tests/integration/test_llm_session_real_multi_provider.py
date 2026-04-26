"""Real multi-provider smoke session: Claude + DeepSeek + Random.

Run only when ALL of:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...
  DEEPSEEK_INTEGRATION_TEST=1
  DEEPSEEK_API_KEY=sk-...

Costs ~$0.02 per run (Claude Haiku ~$0.018, DeepSeek-Chat ~$0.001).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.llm.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

pytestmark = pytest.mark.skipif(
    os.getenv("ANTHROPIC_INTEGRATION_TEST") != "1"
    or os.getenv("DEEPSEEK_INTEGRATION_TEST") != "1"
    or not os.getenv("ANTHROPIC_API_KEY")
    or not os.getenv("DEEPSEEK_API_KEY"),
    reason="needs both INTEGRATION_TEST flags + both API keys",
)


def test_real_multi_provider_six_hand_session(tmp_path: Path) -> None:
    cfg = SessionConfig(
        num_players=6,
        starting_stack=10_000,
        sb=50,
        bb=100,
        num_hands=6,
        max_utility_calls=5,
        enable_math_tools=False,
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30,
        rng_seed=42,
    )
    anth_a = AnthropicProvider(
        model="claude-haiku-4-5",
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )
    anth_b = AnthropicProvider(
        model="claude-haiku-4-5",
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )
    ds = OpenAICompatibleProvider(
        provider_name_value="deepseek",
        model="deepseek-chat",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com/v1",
    )
    agents = [
        RandomAgent(),  # seat 0
        LLMAgent(
            provider=anth_a, model="claude-haiku-4-5", temperature=0.7, total_turn_timeout_sec=60.0
        ),
        RandomAgent(),  # seat 2
        LLMAgent(provider=ds, model="deepseek-chat", temperature=0.7, total_turn_timeout_sec=60.0),
        RandomAgent(),  # seat 4
        LLMAgent(
            provider=anth_b, model="claude-haiku-4-5", temperature=0.7, total_turn_timeout_sec=60.0
        ),
    ]
    sess = Session(
        config=cfg, agents=agents, output_dir=tmp_path, session_id="real_multi_provider_smoke"
    )
    asyncio.run(sess.run())

    meta = json.loads((tmp_path / "meta.json").read_text())
    caps = meta["provider_capabilities"]
    # Two anthropic agents (different provider instances) + one deepseek.
    assert {caps["1"]["provider"], caps["3"]["provider"], caps["5"]["provider"]} == {
        "anthropic",
        "deepseek",
    }
    # Random seats absent.
    for seat_str in ("0", "2", "4"):
        assert seat_str not in caps
    # chip conservation
    assert sum(meta["chip_pnl"].values()) == 0

    # Inspect one snapshot per LLM provider.
    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    by_provider: dict[str, list[Any]] = {}
    for line in snaps:
        rec = json.loads(line)
        prov = rec["agent"]["provider"]
        by_provider.setdefault(prov, []).append(rec)
    assert "anthropic" in by_provider
    assert "deepseek" in by_provider
    # Anthropic snapshots: reasoning_artifacts may be empty (no extended
    # thinking enabled in 3b) OR populated; either is acceptable.
    # DeepSeek-Chat snapshots: reasoning_artifacts MUST be empty (V3 has no CoT).
    for rec in by_provider["deepseek"]:
        for it in rec["iterations"]:
            assert it.get("reasoning_artifacts", []) == [], (
                "deepseek-chat should not emit reasoning artifacts"
            )

"""Mock K+1 session forces HUD tool call; verifies result lands in
agent_view_snapshots.jsonl iterations (Phase 3c-hud Task 9).

Mirror Phase 3c-math/equity mock integration tests.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    TokenCounts,
    ToolCall,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _hud_then_fold(uid_prefix: str, n_responses: int) -> tuple[LLMResponse, ...]:
    """Cycle: get_opponent_stats(seat=0) → fold → get_opponent_stats(seat=1)
    → fold → ..."""
    out: list[LLMResponse] = []
    for i in range(n_responses):
        if i % 2 == 0:
            tc = ToolCall(
                name="get_opponent_stats",
                args={"seat": (i // 2) % 6},  # cycle through seats
                tool_use_id=f"{uid_prefix}_h{i}",
            )
        else:
            tc = ToolCall(name="fold", args={}, tool_use_id=f"{uid_prefix}_f{i}")
        out.append(LLMResponse(
            provider="mock", model="m1", stop_reason="tool_use",
            tool_calls=(tc,), text_content="r",
            tokens=TokenCounts(input_tokens=10, output_tokens=5,
                               cache_read_input_tokens=0,
                               cache_creation_input_tokens=0),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        ))
    return tuple(out)


def test_session_with_hud_tool_call_writes_result_to_snapshot(
    tmp_path: Path,
) -> None:
    """LLM at seat 3 calls get_opponent_stats every other turn; tool result
    (insufficient=True for 6-hand session) lands in iterations."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False,
        enable_hud_tool=True,  # KEY — opens up get_opponent_stats
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    script = MockResponseScript(responses=_hud_then_fold("a", 300))
    provider = MockLLMProvider(script=script)
    llm_agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    agents = [
        RandomAgent(),  # 0
        RandomAgent(),  # 1
        RandomAgent(),  # 2
        llm_agent,      # 3 ← LLM with HUD tool
        RandomAgent(),  # 4
        RandomAgent(),  # 5
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="mock_hud_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps
                 if json.loads(line)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots"

    # Find at least one iteration with tool_call.name == "get_opponent_stats"
    # and tool_result populated.
    hud_iters = []
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc and tc["name"] == "get_opponent_stats":
                hud_iters.append(it)
    assert hud_iters, "no get_opponent_stats iterations recorded"

    # All HUD iterations must have non-None tool_result.
    for it in hud_iters:
        assert it["tool_result"] is not None
        # 6-hand session at min_samples=30 → all opponents insufficient.
        # Result is either {"insufficient": true, ...} OR {"error": "..."}
        # if seat == self (LLM at seat 3, cycling 0/1/2/3/4/5 — seat 3 case
        # returns error).
        tr = it["tool_result"]
        assert "insufficient" in tr or "error" in tr

    # chip_pnl conservation.
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0

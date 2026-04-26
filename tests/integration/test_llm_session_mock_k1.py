"""Integration: 6-hand session with mock LLM agent driving K+1 ReAct loop
including utility tools. Verifies the full pipeline:

  - utility tool calls flow through Session → LLMAgent → ToolRunner
  - IterationRecord with tool_result lands in agent_view_snapshots.jsonl
  - meta.json provider_capabilities still populated correctly
  - chip_pnl conservation holds
  - AgentViewSnapshot.total_utility_calls reflects actual count (codex
    audit IMPORTANT-4 fix)
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


def _utility_then_fold(uid_prefix: str, n_responses: int) -> tuple[LLMResponse, ...]:
    """Cycle: pot_odds → fold → pot_odds → fold → ... so every other turn
    has at least one utility tool call before commit."""
    out: list[LLMResponse] = []
    for i in range(n_responses):
        if i % 2 == 0:
            tc = ToolCall(name="pot_odds", args={}, tool_use_id=f"{uid_prefix}_p{i}")
        else:
            tc = ToolCall(name="fold", args={}, tool_use_id=f"{uid_prefix}_f{i}")
        out.append(
            LLMResponse(
                provider="mock",
                model="m1",
                stop_reason="tool_use",
                tool_calls=(tc,),
                text_content="r",
                tokens=TokenCounts(
                    input_tokens=10,
                    output_tokens=5,
                    cache_read_input_tokens=0,
                    cache_creation_input_tokens=0,
                ),
                raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
            )
        )
    return tuple(out)


def test_six_hand_session_with_k1_utility_tool_calls(tmp_path: Path) -> None:
    cfg = SessionConfig(
        num_players=6,
        starting_stack=10_000,
        sb=50,
        bb=100,
        num_hands=6,
        max_utility_calls=5,
        enable_math_tools=True,  # crucial — turns on utility tool exposure
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30,
        rng_seed=42,
    )
    # Generous response buffer: 6 hands × ~10 turns × cycle of 2 = ~120
    # responses needed for the LLM seat. Use 300 to be safe.
    script = MockResponseScript(responses=_utility_then_fold("a", 300))
    provider = MockLLMProvider(script=script)
    llm_agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    agents = [
        RandomAgent(),  # seat 0 (BTN)
        RandomAgent(),  # SB
        RandomAgent(),  # BB
        llm_agent,  # UTG ← LLM with math tools
        RandomAgent(),  # HJ
        RandomAgent(),  # CO
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="mock_k1_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps if json.loads(line)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots"

    # Across all LLM-seat snapshots, count iterations that called a utility
    # tool. We expect at least one (in fact many — every other LLM turn
    # has the utility-call pattern).
    utility_iters = []
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc is not None and tc["name"] in ("pot_odds", "spr"):
                utility_iters.append(it)
    assert utility_iters, (
        "no utility_tool iterations recorded — K+1 dispatch path "
        "is not wiring through to agent_view_snapshots"
    )
    # Each utility iteration must have a non-None tool_result with "value" key.
    for it in utility_iters:
        assert it["tool_result"] is not None
        assert "value" in it["tool_result"], f"tool_result missing value key: {it['tool_result']}"

    # Codex audit IMPORTANT-4: AgentViewSnapshot.total_utility_calls must
    # reflect actual utility iteration count, not hardcoded 0. For LLM
    # snapshots that contained utility iterations, the field should be
    # >= 1 (spec §7.4).
    snaps_with_utility = [
        rec
        for rec in llm_snaps
        if any(
            it.get("tool_call") and it["tool_call"]["name"] in ("pot_odds", "spr")
            for it in rec["iterations"]
        )
    ]
    assert snaps_with_utility, "no LLM snapshots had utility iterations"
    for snap in snaps_with_utility:
        expected = sum(
            1
            for it in snap["iterations"]
            if it.get("tool_call") and it["tool_call"]["name"] in ("pot_odds", "spr")
        )
        assert snap["total_utility_calls"] == expected, (
            f"total_utility_calls={snap['total_utility_calls']} but "
            f"counted {expected} utility iterations in this snapshot"
        )

    # chip_pnl conservation: zero-sum.
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0


def test_session_with_equity_tool_call_writes_full_result_to_snapshot(
    tmp_path: Path,
) -> None:
    """End-to-end: mock LLM calls hand_equity_vs_ranges; the EquityResult
    dict (hero_equity + CI + n_samples + seed + backend) lands in
    agent_view_snapshots.jsonl iterations[i].tool_result.

    Mock provides ALL 5 villain ranges (preflop UTG always has 5 live
    opponents), so seat 3's first turn each hand is a guaranteed key match.
    """
    cfg = SessionConfig(
        num_players=6,
        starting_stack=10_000,
        sb=50,
        bb=100,
        num_hands=6,
        max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30,
        rng_seed=42,
    )

    def _equity_call(uid: str) -> LLMResponse:
        return LLMResponse(
            provider="mock",
            model="m1",
            stop_reason="tool_use",
            tool_calls=(
                ToolCall(
                    name="hand_equity_vs_ranges",
                    args={"range_by_seat": {0: "22+", 1: "22+", 2: "22+", 4: "22+", 5: "22+"}},
                    tool_use_id=uid,
                ),
            ),
            text_content="checking equity",
            tokens=TokenCounts(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        )

    def _fold(uid: str) -> LLMResponse:
        return LLMResponse(
            provider="mock",
            model="m1",
            stop_reason="tool_use",
            tool_calls=(ToolCall(name="fold", args={}, tool_use_id=uid),),
            text_content="folding",
            tokens=TokenCounts(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        )

    # Cycle: equity → fold → equity → fold ...
    responses: list[LLMResponse] = []
    for i in range(150):
        responses.append(_equity_call(f"eq_{i}"))
        responses.append(_fold(f"f_{i}"))
    script = MockResponseScript(responses=tuple(responses))
    provider = MockLLMProvider(script=script)
    llm_agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    agents = [
        RandomAgent(),  # 0
        RandomAgent(),  # 1
        RandomAgent(),  # 2
        llm_agent,  # 3
        RandomAgent(),  # 4
        RandomAgent(),  # 5
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="mock_k1_equity")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps if json.loads(line)["seat"] == 3]
    assert llm_snaps

    # Codex audit IMPORTANT-2 fix: assert at least one SUCCESSFUL equity
    # iteration with full EquityResult shape. Mock provides all 5 villain
    # ranges (preflop UTG always has 5 live opponents), so seat 3's first
    # turn each hand is a guaranteed match. ≥1 success across 6 hands.
    success_eq_iters = []
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc and tc["name"] == "hand_equity_vs_ranges":
                tr = it.get("tool_result")
                if tr and "hero_equity" in tr:
                    success_eq_iters.append(it)
    assert success_eq_iters, (
        "no successful equity iterations — mock provides all 5 villains as "
        "{0,1,2,4,5} which is the guaranteed preflop UTG live opponent set "
        "for seat 3. If 0 successes, MC dispatch is broken OR opponent "
        "topology unexpected."
    )
    # Each successful equity iteration carries the full EquityResult shape.
    sample = success_eq_iters[0]["tool_result"]
    assert "ci_low" in sample
    assert "ci_high" in sample
    assert "n_samples" in sample
    assert "seed" in sample
    assert sample["backend"] == "eval7"

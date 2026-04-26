"""Session aggregates per-seat retry/token counters into meta.json (Phase 4 Task 2)."""

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


def _fold(uid: str, in_tok: int = 50, out_tok: int = 10) -> LLMResponse:
    return LLMResponse(
        provider="mock",
        model="m",
        stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id=uid),),
        text_content="folding",
        tokens=TokenCounts(
            input_tokens=in_tok,
            output_tokens=out_tok,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


def test_meta_total_tokens_aggregated_per_seat(tmp_path: Path) -> None:
    """Per-seat total_tokens dict reflects accumulated TurnDecisionResult.total_tokens."""
    cfg = SessionConfig(
        num_players=6,
        starting_stack=10_000,
        sb=50,
        bb=100,
        num_hands=6,
        max_utility_calls=5,
        enable_math_tools=False,
        enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30,
        rng_seed=42,
    )
    script = MockResponseScript(responses=tuple(_fold(f"t{i}") for i in range(200)))
    provider = MockLLMProvider(script=script)
    llm_agent = LLMAgent(provider=provider, model="m", temperature=0.7)
    agents = [
        RandomAgent(),  # 0
        llm_agent,  # 1
        RandomAgent(),  # 2
        RandomAgent(),  # 3
        RandomAgent(),  # 4
        RandomAgent(),  # 5
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="meta_agg_test")
    asyncio.run(sess.run())

    meta = json.loads((tmp_path / "meta.json").read_text())
    # Seat 1 (LLM) accumulated tokens. Random seats: not present (no LLM, no tokens).
    tokens = meta["total_tokens"]
    assert "1" in tokens, f"LLM seat 1 missing from total_tokens: {tokens}"
    assert tokens["1"]["input_tokens"] > 0
    assert tokens["1"]["output_tokens"] > 0
    # Random seats have no LLM iterations — they should not appear or have zero entries.
    for s in ("0", "2", "3", "4", "5"):
        if s in tokens:
            assert tokens[s]["input_tokens"] == 0
            assert tokens[s]["output_tokens"] == 0


def test_meta_retry_summary_per_seat_aggregated(tmp_path: Path) -> None:
    """Per-seat retry_summary dict has 6 entries (one per seat) with all
    4 retry counters + default_action_fallback_count + turn_timeout_exceeded_count."""
    cfg = SessionConfig(
        num_players=6,
        starting_stack=10_000,
        sb=50,
        bb=100,
        num_hands=6,
        max_utility_calls=5,
        enable_math_tools=False,
        enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30,
        rng_seed=42,
    )
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="retry_agg_test")
    asyncio.run(sess.run())

    meta = json.loads((tmp_path / "meta.json").read_text())
    rs = meta["retry_summary_per_seat"]
    assert set(rs.keys()) == {"0", "1", "2", "3", "4", "5"}
    for _seat_str, summary in rs.items():
        assert "total_turns" in summary
        assert "api_retry_count" in summary
        assert "illegal_action_retry_count" in summary
        assert "no_tool_retry_count" in summary
        assert "tool_usage_error_count" in summary
        assert "default_action_fallback_count" in summary
        assert "turn_timeout_exceeded_count" in summary
        # Random agents never trip any retries.
        assert summary["api_retry_count"] == 0
        assert summary["illegal_action_retry_count"] == 0


def test_meta_tool_usage_summary_aggregated(tmp_path: Path) -> None:
    """tool_usage_summary tracks utility calls per seat (math/equity tools)."""
    cfg = SessionConfig(
        num_players=6,
        starting_stack=10_000,
        sb=50,
        bb=100,
        num_hands=6,
        max_utility_calls=5,
        enable_math_tools=False,
        enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30,
        rng_seed=42,
    )
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="tool_agg_test")
    asyncio.run(sess.run())

    meta = json.loads((tmp_path / "meta.json").read_text())
    tu = meta["tool_usage_summary"]
    assert set(tu.keys()) == {"0", "1", "2", "3", "4", "5"}
    for _seat_str, summary in tu.items():
        assert "total_utility_calls" in summary
        # Random agents never call utility tools.
        assert summary["total_utility_calls"] == 0

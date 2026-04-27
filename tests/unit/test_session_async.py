"""Tests for Session async migration (Phase 3a Task 6)."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _cfg() -> SessionConfig:
    return SessionConfig(
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


def test_session_run_is_a_coroutine_function() -> None:
    """Session.run must be `async def` after Phase 3a Task 6."""
    assert inspect.iscoroutinefunction(Session.run)


def test_session_run_completes_via_asyncio_run(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RuleBasedAgent() if i % 2 == 0 else RandomAgent() for i in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="async_test")
    asyncio.run(sess.run())
    for fname in (
        "canonical_private.jsonl",
        "public_replay.jsonl",
        "agent_view_snapshots.jsonl",
        "meta.json",
    ):
        assert (tmp_path / fname).exists()
        assert (tmp_path / fname).stat().st_size > 0


def test_session_writes_iterations_field_in_snapshots(tmp_path: Path) -> None:
    """spec §7.4: iterations field must exist in agent_view_snapshots.

    Updated post-Polish 17: RuleBased now records its triggered rule as
    a single synthetic IterationRecord (text_only, no tool_call) so the
    web UI's reasoning panel shows what fired instead of "no LLM
    reasoning". Verify the iteration carries readable rationale text.
    """
    cfg = _cfg()
    agents = [RuleBasedAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="iter_test")
    asyncio.run(sess.run())
    line = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()[0]
    rec = json.loads(line)
    assert "iterations" in rec
    iters = rec["iterations"]
    assert len(iters) == 1, "RuleBased emits exactly one synthetic iteration"
    it = iters[0]
    assert it["provider_response_kind"] == "text_only"
    assert it["tool_call"] is None
    assert it["text_content"], "rationale text must be non-empty"

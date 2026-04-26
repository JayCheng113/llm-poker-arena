"""Tests for full BR2-01 censor record (Phase 3d Task 5)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import (
    ApiErrorInfo,
    TokenCounts,
    TurnDecisionResult,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.engine.legal_actions import default_safe_action
from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.session.session import Session


class _CensoringAgent(Agent):
    """Agent whose first decision returns api_error → forces censor."""

    def __init__(self) -> None:
        self._calls = 0

    async def decide(self, view: PlayerView) -> TurnDecisionResult:
        self._calls += 1
        if self._calls == 1:
            return TurnDecisionResult(
                iterations=(),
                final_action=None,
                total_tokens=TokenCounts.zero(),
                wall_time_ms=10,
                api_retry_count=1,
                illegal_action_retry_count=0,
                no_tool_retry_count=0,
                tool_usage_error_count=0,
                default_action_fallback=False,
                api_error=ApiErrorInfo(
                    type="ProviderTransientError",
                    detail="503 timeout",
                ),
                turn_timeout_exceeded=False,
            )
        return TurnDecisionResult(
            iterations=(),
            final_action=default_safe_action(view),
            total_tokens=TokenCounts.zero(),
            wall_time_ms=0,
            api_retry_count=0,
            illegal_action_retry_count=0,
            no_tool_retry_count=0,
            tool_usage_error_count=0,
            default_action_fallback=True,
            api_error=None,
            turn_timeout_exceeded=False,
        )

    def provider_id(self) -> str:
        return "censor:test"


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


def _agents_with_censor_at_seat3() -> list[Agent]:
    return [
        RandomAgent(),
        RandomAgent(),
        RandomAgent(),
        _CensoringAgent(),
        RandomAgent(),
        RandomAgent(),
    ]


def test_censored_hand_writes_to_censored_hands_jsonl(tmp_path: Path) -> None:
    sess = Session(
        config=_cfg(),
        agents=_agents_with_censor_at_seat3(),
        output_dir=tmp_path,
        session_id="censor_test",
    )
    asyncio.run(sess.run())

    censor_path = tmp_path / "censored_hands.jsonl"
    assert censor_path.exists(), "censored_hands.jsonl must be written"
    lines = censor_path.read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["hand_id"] == 0
    assert rec["seat"] == 3
    assert rec["api_error"]["type"] == "ProviderTransientError"
    assert "503" in rec["api_error"]["detail"]


def test_censored_hand_does_not_emit_partial_canonical_record(
    tmp_path: Path,
) -> None:
    """BR2-01 'censor 整手': hand 0 must NOT appear in canonical_private."""
    sess = Session(
        config=_cfg(),
        agents=_agents_with_censor_at_seat3(),
        output_dir=tmp_path,
        session_id="censor_test_2",
    )
    asyncio.run(sess.run())

    private = (tmp_path / "canonical_private.jsonl").read_text().strip().splitlines()
    private_hand_ids = {json.loads(line)["hand_id"] for line in private}
    assert 0 not in private_hand_ids
    assert {1, 2, 3, 4, 5}.issubset(private_hand_ids)


def test_censored_hand_does_not_emit_partial_public_record(
    tmp_path: Path,
) -> None:
    sess = Session(
        config=_cfg(),
        agents=_agents_with_censor_at_seat3(),
        output_dir=tmp_path,
        session_id="censor_test_3",
    )
    asyncio.run(sess.run())

    public = (tmp_path / "public_replay.jsonl").read_text().strip().splitlines()
    public_hand_ids = {json.loads(line)["hand_id"] for line in public}
    assert 0 not in public_hand_ids


def test_censored_hand_drops_partial_turn_snapshots(tmp_path: Path) -> None:
    sess = Session(
        config=_cfg(),
        agents=_agents_with_censor_at_seat3(),
        output_dir=tmp_path,
        session_id="censor_test_4",
    )
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    snap_hand_ids = {json.loads(line)["hand_id"] for line in snaps}
    assert 0 not in snap_hand_ids

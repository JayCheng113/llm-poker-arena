"""Tests for compute_action_distribution."""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session
from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN


def _run(tmp_path: Path) -> Path:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=24, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=11,
    )
    sess_dir = tmp_path / "b1"
    Session(config=cfg, agents=[RandomAgent() for _ in range(6)],
            output_dir=sess_dir, session_id="b1").run()
    return sess_dir


def test_action_distribution_covers_all_six_seats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.metrics import compute_action_distribution
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        rows = compute_action_distribution(con)
    seats = {r["seat"] for r in rows}
    assert seats == set(range(6))
    # Every (seat, street) block sums to ~1.0 — verify for seat 0 preflop.
    seat0_pre = [r for r in rows if r["seat"] == 0 and r["street"] == "preflop"]
    assert seat0_pre  # at least one preflop action type recorded
    total_rate = sum(r["rate_within_street"] for r in seat0_pre)
    assert abs(total_rate - 1.0) < 1e-9, total_rate


def test_action_distribution_only_reports_known_action_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.metrics import compute_action_distribution
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        rows = compute_action_distribution(con)
    VALID = {"fold", "check", "call", "bet", "raise_to", "all_in"}
    for r in rows:
        assert r["action_type"] in VALID, r

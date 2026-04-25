"""Tests for compute_pfr. PFR ≤ VPIP on every seat."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session
from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN


def _run_b1(tmp_path: Path, num_hands: int = 24) -> Path:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=31,
    )
    sess_dir = tmp_path / "b1"
    sess = Session(config=cfg, agents=[RandomAgent() for _ in range(6)],
                   output_dir=sess_dir, session_id="b1")
    asyncio.run(sess.run())
    return sess_dir


def test_compute_pfr_returns_one_row_per_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.metrics import compute_pfr
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run_b1(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        result = compute_pfr(con)
        # Authoritative denominator from `hands` (Risk 14).
        count_row = con.sql("SELECT COUNT(*) FROM hands").fetchone()
        assert count_row is not None
        expected_n_hands = count_row[0]
    assert len(result) == 6
    assert [r["seat"] for r in result] == [0, 1, 2, 3, 4, 5]
    for row in result:
        assert row["n_hands"] == expected_n_hands, (
            f"seat {row['seat']}: PFR denominator {row['n_hands']} "
            f"!= hands dealt {expected_n_hands} — walk-handling regression"
        )
        assert 0.0 <= row["pfr_rate"] <= 1.0


def test_pfr_is_subset_of_vpip_per_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PFR rate ≤ VPIP rate for every seat — a raise is voluntary."""
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.metrics import compute_pfr, compute_vpip
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run_b1(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        vpip = {r["seat"]: r["vpip_rate"] for r in compute_vpip(con)}
        pfr = {r["seat"]: r["pfr_rate"] for r in compute_pfr(con)}
    for seat in range(6):
        assert pfr[seat] <= vpip[seat] + 1e-9, (
            f"seat {seat}: PFR {pfr[seat]} > VPIP {vpip[seat]}"
        )

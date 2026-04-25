"""Canary: DuckDB can read a real Phase 2a session and access nested JSON fields.

This test exists because `read_json_auto` schema inference on heterogeneous
structs (e.g. `final_action` where `amount` is present on some rows and
absent on others) has historically bitten similar projects. If this test
starts failing, the metric SQL tasks (T4-T6) need to use explicit JSON
extraction instead of dot-access.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session
from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN


def _run_small_session(tmp_path: Path) -> Path:
    """Run a 12-hand heterogeneous session; return the output dir."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=12, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    agents = [RandomAgent(), RuleBasedAgent()] * 3
    sess_dir = tmp_path / "sess_smoke"
    sess = Session(config=cfg, agents=agents, output_dir=sess_dir,
                   session_id="smoke")
    asyncio.run(sess.run())
    return sess_dir


def test_duckdb_can_read_actions_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """actions view opens and exposes columns we rely on in T4-T6."""
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run_small_session(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        # DESCRIBE returns (column_name, column_type, null, key, default, extra)
        # — column NAMES live at row[0], NOT row[1].
        cols = {
            row[0]
            for row in con.sql("DESCRIBE actions").fetchall()
        }
        # Required fields for VPIP/PFR/action_distribution SQL.
        for required in ("seat", "hand_id", "street", "is_forced_blind",
                         "final_action"):
            assert required in cols, f"missing column: {required}"


def test_duckdb_can_access_final_action_type_via_dot_notation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The critical risk: `final_action.type` dot-access on a heterogeneous
    struct column (some rows have `amount`, some don't). If this test fails,
    switch metric SQL to `final_action['type']` subscript syntax.
    """
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run_small_session(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        # Count distinct action types over all snapshots.
        rows = con.sql(
            "SELECT DISTINCT final_action.type FROM actions"
        ).fetchall()
        types = {row[0] for row in rows if row[0] is not None}
        # Must have at least fold / call / raise_to / check — some agent
        # must have hit several. 12 hands × 6 seats guarantees variety.
        assert len(types) >= 2, (
            f"expected ≥2 distinct action types, got {types}; if empty, "
            f"dot-access may be broken — try final_action['type']"
        )
        # Known-valid set from spec §3.3:
        assert types <= {"fold", "check", "call", "bet", "raise_to", "all_in"}

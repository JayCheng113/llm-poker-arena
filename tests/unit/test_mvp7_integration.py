"""MVP 7 exit criterion: B1 + B2 baselines run to completion and all three
metrics + three charts land on disk. Spec §16.1.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_mvp7_b1_random_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.baseline import run_random_baseline
    from llm_poker_arena.analysis.metrics import (
        compute_action_distribution,
        compute_pfr,
        compute_vpip,
    )
    from llm_poker_arena.analysis.plots import (
        plot_action_distribution,
        plot_chip_pnl,
        plot_vpip_pfr_table,
    )
    from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN
    from llm_poker_arena.storage.duckdb_query import open_session

    sess = run_random_baseline(tmp_path / "b1", num_hands=60, rng_seed=99)

    # Metrics.
    with open_session(sess, access_token=PRIVATE_ACCESS_TOKEN) as con:
        vpip = compute_vpip(con)
        pfr = compute_pfr(con)
        ad = compute_action_distribution(con)
        count_row = con.sql("SELECT COUNT(*) FROM hands").fetchone()
        assert count_row is not None
        expected_n = count_row[0]

    assert len(vpip) == 6
    assert len(pfr) == 6
    assert len(ad) > 0
    for seat in range(6):
        seat_vpip = next(r for r in vpip if r["seat"] == seat)
        seat_pfr = next(r for r in pfr if r["seat"] == seat)
        # Denominator uses hands view (Risk 14 — walks don't undercount).
        assert seat_vpip["n_hands"] == expected_n
        assert seat_pfr["n_hands"] == expected_n
        assert seat_pfr["pfr_rate"] <= seat_vpip["vpip_rate"] + 1e-9

    # Plots.
    assert plot_chip_pnl(sess).exists()
    assert plot_vpip_pfr_table(sess).exists()
    assert plot_action_distribution(sess).exists()

    # Chip conservation holds across the session.
    meta = json.loads((sess / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0


def test_mvp7_b2_rule_based_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.baseline import run_rule_based_baseline
    from llm_poker_arena.analysis.metrics import (
        compute_action_distribution,
        compute_pfr,
        compute_vpip,
    )
    from llm_poker_arena.analysis.plots import (
        plot_action_distribution,
        plot_chip_pnl,
        plot_vpip_pfr_table,
    )
    from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN
    from llm_poker_arena.storage.duckdb_query import open_session

    sess = run_rule_based_baseline(tmp_path / "b2", num_hands=60, rng_seed=99)

    with open_session(sess, access_token=PRIVATE_ACCESS_TOKEN) as con:
        vpip = compute_vpip(con)
        pfr = compute_pfr(con)
        ad = compute_action_distribution(con)
    assert len(vpip) == 6
    assert len(pfr) == 6
    assert len(ad) > 0
    # RuleBasedAgent is tight/aggressive — its PFR should be ≤ its VPIP and
    # generally non-zero for hands where premium holdings land preflop.
    for seat in range(6):
        sv = next(r for r in vpip if r["seat"] == seat)
        sp = next(r for r in pfr if r["seat"] == seat)
        assert sp["pfr_rate"] <= sv["vpip_rate"] + 1e-9

    plot_chip_pnl(sess)
    plot_vpip_pfr_table(sess)
    plot_action_distribution(sess)

    meta = json.loads((sess / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0

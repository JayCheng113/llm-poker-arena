"""Tests for chart rendering — files exist, content is non-trivial."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_plot_chip_pnl_writes_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.baseline import run_random_baseline
    from llm_poker_arena.analysis.plots import plot_chip_pnl

    sess = run_random_baseline(tmp_path / "b1", num_hands=6, rng_seed=3)
    out = plot_chip_pnl(sess)
    assert out.exists()
    assert out.suffix == ".png"
    assert out.stat().st_size > 1000  # non-empty PNG


def test_plot_vpip_pfr_table_writes_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.baseline import run_random_baseline
    from llm_poker_arena.analysis.plots import plot_vpip_pfr_table

    sess = run_random_baseline(tmp_path / "b1", num_hands=12, rng_seed=5)
    out = plot_vpip_pfr_table(sess)
    assert out.exists()
    assert out.stat().st_size > 1000


def test_plot_action_distribution_writes_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.baseline import run_random_baseline
    from llm_poker_arena.analysis.plots import plot_action_distribution

    sess = run_random_baseline(tmp_path / "b1", num_hands=12, rng_seed=6)
    out = plot_action_distribution(sess)
    assert out.exists()
    assert out.stat().st_size > 1000

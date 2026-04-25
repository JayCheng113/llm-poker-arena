"""Tests for run_random_baseline + run_rule_based_baseline."""
from __future__ import annotations

import json
from pathlib import Path


def test_run_random_baseline_writes_session_artifacts(tmp_path: Path) -> None:
    from llm_poker_arena.analysis.baseline import run_random_baseline

    out = run_random_baseline(tmp_path / "b1", num_hands=6, rng_seed=7)
    # All Phase-2a artefacts should exist.
    for fname in (
        "canonical_private.jsonl", "public_replay.jsonl",
        "agent_view_snapshots.jsonl", "meta.json", "config.json",
    ):
        assert (out / fname).exists(), fname
    # session_id carries the baseline label.
    meta = json.loads((out / "meta.json").read_text())
    assert meta["session_id"] == "b1_random"


def test_run_rule_based_baseline_writes_session_artifacts(
    tmp_path: Path,
) -> None:
    from llm_poker_arena.analysis.baseline import run_rule_based_baseline

    out = run_rule_based_baseline(tmp_path / "b2", num_hands=6, rng_seed=8)
    meta = json.loads((out / "meta.json").read_text())
    assert meta["session_id"] == "b2_rule_based"
    # All 6 seat_assignment labels share the rule_based provider family.
    for label in meta["seat_assignment"].values():
        assert label.startswith("rule_based")

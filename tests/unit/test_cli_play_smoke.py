"""Smoke test for the poker-play CLI entry point."""
from __future__ import annotations

import io
from pathlib import Path

import pytest


def test_build_agents_places_human_at_requested_seat() -> None:
    from llm_poker_arena.agents.human_cli import HumanCLIAgent
    from llm_poker_arena.agents.random_agent import RandomAgent
    from llm_poker_arena.agents.rule_based import RuleBasedAgent
    from llm_poker_arena.cli.play import build_agents

    agents = build_agents(
        num_players=6,
        my_seat=3,
        human_input=io.StringIO(""),
        human_output=io.StringIO(),
    )
    assert len(agents) == 6
    assert isinstance(agents[3], HumanCLIAgent)
    for i in (0, 1, 2, 4, 5):
        assert isinstance(agents[i], RandomAgent | RuleBasedAgent)


def test_build_agents_rejects_out_of_range_seat() -> None:
    from llm_poker_arena.cli.play import build_agents

    with pytest.raises(ValueError, match="my_seat"):
        build_agents(
            num_players=6,
            my_seat=9,  # out of range
            human_input=io.StringIO(""),
            human_output=io.StringIO(),
        )


def test_run_cli_exits_cleanly_when_human_folds_every_hand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: run a short session where the human always folds.

    `num_hands=2` is rounded UP to 6 by run_cli's guard. Test asserts
    session-level artifacts, not an exact hand count.
    """
    from llm_poker_arena.cli.play import run_cli
    folds = "fold\n" * 50  # generous — 6 hands × up to several prompts each

    rc = run_cli(
        num_hands=2, my_seat=3, rng_seed=42, output_root=tmp_path,
        human_input=io.StringIO(folds),
        human_output=io.StringIO(),
    )
    assert rc == 0
    session_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(session_dirs) == 1
    sess = session_dirs[0]
    for fname in (
        "canonical_private.jsonl", "public_replay.jsonl",
        "agent_view_snapshots.jsonl", "meta.json", "config.json",
    ):
        assert (sess / fname).exists(), fname

    import json
    meta = json.loads((sess / "meta.json").read_text())
    assert meta["seat_assignment"]["3"] == "human:cli_v1"

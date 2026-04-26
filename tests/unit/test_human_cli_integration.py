"""Integration: Session with 1 human seat + 5 bots + scripted cyclic input."""

from __future__ import annotations

import io
import json
from pathlib import Path


def test_human_cli_cyclic_input_session_finishes_cleanly(tmp_path: Path) -> None:
    from llm_poker_arena.cli.play import run_cli

    # Cycle through the 4 most-common action names so at least one is legal
    # for every prompt the human hits. Pure 'call\n' * N would exhaust on
    # a turn where call isn't legal (e.g. agent facing no bet → check/bet
    # offered but not call): HumanCLIAgent reprompts on each illegal input
    # and would EOF before finding a valid action.
    cyclic = "call\ncheck\nfold\nall_in\n" * 50
    input_stream = io.StringIO(cyclic)
    output_stream = io.StringIO()

    rc = run_cli(
        num_hands=6,
        my_seat=3,
        rng_seed=7,
        output_root=tmp_path,
        human_input=input_stream,
        human_output=output_stream,
    )
    assert rc == 0

    session_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(session_dirs) == 1
    sess = session_dirs[0]

    # Canonical private has 6 lines (one per hand).
    lines = (sess / "canonical_private.jsonl").read_text().splitlines()
    assert len(lines) == 6

    # agent_view_snapshots includes rows where seat=3 and agent.provider='human'.
    human_turns = 0
    for line in (sess / "agent_view_snapshots.jsonl").read_text().splitlines():
        snap = json.loads(line)
        if snap["seat"] == 3 and snap["agent"]["provider"] == "human":
            human_turns += 1
    assert human_turns >= 6, f"expected >= 6 human turns, got {human_turns}"

    # Chip conservation across the whole session.
    meta = json.loads((sess / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0


def test_human_cli_session_meta_marks_human_seat(tmp_path: Path) -> None:
    """meta.json.seat_assignment labels the human seat with 'human:cli_v1'."""
    from llm_poker_arena.cli.play import run_cli

    cyclic = "call\ncheck\nfold\nall_in\n" * 50
    rc = run_cli(
        num_hands=6,
        my_seat=2,
        rng_seed=3,
        output_root=tmp_path,
        human_input=io.StringIO(cyclic),
        human_output=io.StringIO(),
    )
    assert rc == 0
    session_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    sess = session_dirs[0]
    meta = json.loads((sess / "meta.json").read_text())
    assert meta["seat_assignment"]["2"] == "human:cli_v1"
    # Other seats are bot-tagged (random:* or rule_based:*).
    for seat_str, label in meta["seat_assignment"].items():
        if int(seat_str) == 2:
            continue
        assert label.startswith(("random:", "rule_based:"))

"""Real Anthropic + scripted human via CLI (gated, NOT in CI).

Run only when:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...

Verifies the human-vs-LLM CLI path end-to-end on the real Anthropic API.
Cost ~$0.01 (6 hands, 1 Claude Haiku 4.5 seat).

Wire-only assertions (mirror Phase 3 gated patterns):
  - run_cli returns 0
  - meta.json.seat_assignment / total_tokens populated
  - chip_pnl conserves
  - all final_actions in legal set (per snapshot)
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest

from llm_poker_arena.cli.play import run_cli

pytestmark = pytest.mark.skipif(
    os.getenv("ANTHROPIC_INTEGRATION_TEST") != "1"
    or not os.getenv("ANTHROPIC_API_KEY"),
    reason="needs ANTHROPIC_INTEGRATION_TEST=1 and ANTHROPIC_API_KEY set",
)


def test_human_plus_real_claude_session_completes(tmp_path: Path) -> None:
    """Scripted stdin so test runs unattended (no real human at keyboard)."""
    # Cyclic stdin: alternating call/check/fold/all_in covers every legal set.
    human_input = io.StringIO("call\ncheck\nfold\nall_in\n" * 100)
    human_output = io.StringIO()

    rc = run_cli(
        num_hands=6, my_seat=3, rng_seed=42,
        output_root=tmp_path,
        human_input=human_input, human_output=human_output,
        llm_specs=[("anthropic", "claude-haiku-4-5", 0)],
    )
    assert rc == 0

    session_dirs = list(tmp_path.glob("session_*"))
    assert len(session_dirs) == 1
    sd = session_dirs[0]

    # meta.json basics.
    meta = json.loads((sd / "meta.json").read_text())
    assert meta["total_hands_played"] == 6
    assert meta["seat_assignment"]["0"] == "anthropic:claude-haiku-4-5"
    assert meta["seat_assignment"]["3"] == "human:cli_v1"
    assert meta["total_tokens"]["0"]["input_tokens"] > 0
    assert sum(meta["chip_pnl"].values()) == 0

    # Every snapshot's final_action is in its legal set.
    snaps = (sd / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    for line in snaps:
        rec = json.loads(line)
        legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
        assert rec["final_action"]["type"] in legal_names, (
            f"seat {rec['seat']} {rec['turn_id']} final {rec['final_action']!r} "
            f"not in legal {legal_names}"
        )

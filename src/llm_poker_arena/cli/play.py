"""`poker-play` CLI: interactive terminal game with HumanCLIAgent.

Not a spec §16.1 MVP task — dogfooding deliverable. Builds a mixed
lineup (1 human seat + 5 bots), runs a Phase-2a `Session`, prints a
session-level summary from `meta.json`.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.human_cli import HumanCLIAgent
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def build_agents(
    *,
    num_players: int,
    my_seat: int,
    human_input: TextIO | None = None,
    human_output: TextIO | None = None,
) -> list[Agent]:
    """Construct `num_players` agents: HumanCLIAgent at `my_seat`, bots elsewhere.

    Bots alternate `RandomAgent` / `RuleBasedAgent` by seat parity.
    """
    if not 0 <= my_seat < num_players:
        raise ValueError(
            f"my_seat must be in [0, {num_players}), got {my_seat}"
        )
    agents: list[Agent] = []
    for i in range(num_players):
        if i == my_seat:
            agents.append(
                HumanCLIAgent(input_stream=human_input, output_stream=human_output)
            )
        elif i % 2 == 0:
            agents.append(RandomAgent())
        else:
            agents.append(RuleBasedAgent())
    return agents


def _session_dir_name(rng_seed: int) -> str:
    # Microseconds included so repeated runs within the same second don't
    # collide on the same directory (BatchedJsonlWriter opens "a" mode and
    # would otherwise append to stale artifacts).
    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S-%f")
    return f"session_{ts}_seed{rng_seed}"


def _print_session_summary(
    session_dir: Path, my_seat: int, output_stream: TextIO,
) -> None:
    """Emit a terse session-level summary after the Session finishes."""
    meta = json.loads((session_dir / "meta.json").read_text())
    chip_pnl = meta["chip_pnl"]
    my_pnl = int(chip_pnl[str(my_seat)])
    output_stream.write("\n" + "=" * 60 + "\n")
    output_stream.write(
        f"Session complete — {meta['total_hands_played']} hands "
        f"in {meta['session_wall_time_sec']}s\n"
    )
    output_stream.write(f"Your seat ({my_seat}) net P&L: {my_pnl:+d} chips\n")
    output_stream.write("All seats:\n")
    for seat in sorted(chip_pnl, key=int):
        marker = " ← YOU" if int(seat) == my_seat else ""
        output_stream.write(
            f"  seat {seat}: {int(chip_pnl[seat]):+d}{marker}\n"
        )
    output_stream.write(f"Session artifacts at: {session_dir}\n")
    output_stream.flush()


def run_cli(
    *,
    num_hands: int,
    my_seat: int,
    rng_seed: int,
    output_root: Path,
    human_input: TextIO | None = None,
    human_output: TextIO | None = None,
) -> int:
    """Programmatic entry point; returns shell-style return code."""
    out_stream = human_output if human_output is not None else sys.stdout
    if num_hands % 6 != 0:
        # SessionConfig requires num_hands % num_players == 0; round UP to 6x.
        num_hands = ((num_hands + 5) // 6) * 6
        out_stream.write(
            f"[poker-play] num_hands rounded up to {num_hands} "
            f"(must be multiple of num_players=6)\n"
        )

    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=rng_seed,
    )
    agents = build_agents(
        num_players=6, my_seat=my_seat,
        human_input=human_input, human_output=human_output,
    )

    session_dir = output_root / _session_dir_name(rng_seed=rng_seed)
    if session_dir.exists():
        out_stream.write(
            f"[poker-play] session directory {session_dir} already exists; "
            f"aborting to avoid appending to stale artifacts\n"
        )
        return 1
    Session(
        config=cfg, agents=agents, output_dir=session_dir,
        session_id=session_dir.name,
    ).run()

    _print_session_summary(session_dir, my_seat=my_seat, output_stream=out_stream)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="poker-play",
        description="Play poker against RandomAgent + RuleBasedAgent in the terminal.",
    )
    parser.add_argument("--num-hands", type=int, default=6)
    parser.add_argument("--my-seat", type=int, default=3)
    parser.add_argument("--rng-seed", type=int, default=42)
    parser.add_argument(
        "--output-root", type=Path, default=Path("runs").resolve(),
        help="Where to write session artefacts (default: ./runs/).",
    )
    args = parser.parse_args(argv)

    args.output_root.mkdir(parents=True, exist_ok=True)
    return run_cli(
        num_hands=args.num_hands,
        my_seat=args.my_seat,
        rng_seed=args.rng_seed,
        output_root=args.output_root,
    )


if __name__ == "__main__":
    sys.exit(main())

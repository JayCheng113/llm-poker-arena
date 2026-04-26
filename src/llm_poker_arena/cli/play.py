"""`poker-play` CLI: interactive terminal game with HumanCLIAgent.

Phase 4 extends Phase 1's bot-only build with --llm-seat / --llm-provider /
--llm-model triplets so the lineup can mix Anthropic / OpenAI / DeepSeek
LLM agents alongside the human seat. API keys come from env vars only
(ANTHROPIC_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY); fail-fast if a
required key is missing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.human_cli import HumanCLIAgent
from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.llm.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

# Provider tag → (env_var_name, factory(model, api_key) -> Provider).
_PROVIDER_TABLE: dict[str, tuple[str, Any]] = {
    "anthropic": (
        "ANTHROPIC_API_KEY",
        lambda model, key: AnthropicProvider(model=model, api_key=key),
    ),
    "openai": (
        "OPENAI_API_KEY",
        lambda model, key: OpenAICompatibleProvider(
            provider_name_value="openai",
            model=model,
            api_key=key,
        ),
    ),
    "deepseek": (
        "DEEPSEEK_API_KEY",
        lambda model, key: OpenAICompatibleProvider(
            provider_name_value="deepseek",
            model=model,
            api_key=key,
            base_url="https://api.deepseek.com/v1",
        ),
    ),
}


def build_agents(
    *,
    num_players: int,
    my_seat: int,
    human_input: TextIO | None = None,
    human_output: TextIO | None = None,
    llm_specs: list[tuple[str, str, int]] | None = None,
) -> list[Agent]:
    """Construct `num_players` agents: HumanCLIAgent at `my_seat`, LLMAgents at
    seats listed in `llm_specs`, bots elsewhere.

    `llm_specs` is a list of (provider, model, seat) triples. Each `provider`
    must be one of "anthropic" / "openai" / "deepseek". The corresponding
    env var (ANTHROPIC_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY) MUST be
    set or build_agents raises ValueError.

    Bots fill remaining seats: alternate `RandomAgent` / `RuleBasedAgent`
    by seat parity.
    """
    if not 0 <= my_seat < num_players:
        raise ValueError(f"my_seat must be in [0, {num_players}), got {my_seat}")
    llm_specs = llm_specs or []
    llm_seats: dict[int, tuple[str, str]] = {}
    for provider_tag, model, seat in llm_specs:
        if not 0 <= seat < num_players:
            raise ValueError(f"--llm-seat {seat} out of range [0, {num_players})")
        if seat == my_seat:
            raise ValueError(
                f"--llm-seat {seat} cannot equal --my-seat {my_seat} "
                f"(human seat is reserved for HumanCLIAgent)"
            )
        if seat in llm_seats:
            raise ValueError(f"duplicate --llm-seat {seat}; pass each seat at most once")
        if provider_tag not in _PROVIDER_TABLE:
            raise ValueError(
                f"unknown --llm-provider {provider_tag!r}; supported: {sorted(_PROVIDER_TABLE)}"
            )
        env_name, _factory = _PROVIDER_TABLE[provider_tag]
        if not os.environ.get(env_name):
            raise ValueError(f"--llm-provider {provider_tag} requires {env_name} env var to be set")
        llm_seats[seat] = (provider_tag, model)

    agents: list[Agent] = []
    for i in range(num_players):
        if i == my_seat:
            agents.append(HumanCLIAgent(input_stream=human_input, output_stream=human_output))
        elif i in llm_seats:
            provider_tag, model = llm_seats[i]
            env_name, factory = _PROVIDER_TABLE[provider_tag]
            api_key = os.environ[env_name]
            provider = factory(model, api_key)
            agents.append(
                LLMAgent(
                    provider=provider,
                    model=model,
                    temperature=0.7,
                )
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
    session_dir: Path,
    my_seat: int,
    output_stream: TextIO,
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
        output_stream.write(f"  seat {seat}: {int(chip_pnl[seat]):+d}{marker}\n")
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
    llm_specs: list[tuple[str, str, int]] | None = None,
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

    # Phase 4: enable_math_tools auto-True if any LLM seat is configured.
    has_llm = bool(llm_specs)
    cfg = SessionConfig(
        num_players=6,
        starting_stack=10_000,
        sb=50,
        bb=100,
        num_hands=num_hands,
        max_utility_calls=5,
        enable_math_tools=has_llm,
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30,
        rng_seed=rng_seed,
    )
    agents = build_agents(
        num_players=6,
        my_seat=my_seat,
        human_input=human_input,
        human_output=human_output,
        llm_specs=llm_specs,
    )

    session_dir = output_root / _session_dir_name(rng_seed=rng_seed)
    if session_dir.exists():
        out_stream.write(
            f"[poker-play] session directory {session_dir} already exists; "
            f"aborting to avoid appending to stale artifacts\n"
        )
        return 1
    sess = Session(
        config=cfg,
        agents=agents,
        output_dir=session_dir,
        session_id=session_dir.name,
    )
    asyncio.run(sess.run())

    _print_session_summary(session_dir, my_seat=my_seat, output_stream=out_stream)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="poker-play",
        description=(
            "Play poker against bots and/or LLM agents in the terminal. "
            "Use --llm-seat/--llm-provider/--llm-model in tandem (repeatable) "
            "to mix LLM opponents into the lineup."
        ),
    )
    parser.add_argument("--num-hands", type=int, default=6)
    parser.add_argument("--my-seat", type=int, default=3)
    parser.add_argument("--rng-seed", type=int, default=42)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runs").resolve(),
        help="Where to write session artefacts (default: ./runs/).",
    )
    parser.add_argument(
        "--llm-seat",
        type=int,
        action="append",
        default=[],
        help="Seat to assign an LLM agent. Repeat for multiple LLMs.",
    )
    parser.add_argument(
        "--llm-provider",
        action="append",
        default=[],
        choices=["anthropic", "openai", "deepseek"],
        help="Provider for the corresponding --llm-seat (must repeat in tandem).",
    )
    parser.add_argument(
        "--llm-model",
        action="append",
        default=[],
        help="Model name for the corresponding --llm-seat (e.g. claude-haiku-4-5, deepseek-chat).",
    )
    args = parser.parse_args(argv)

    if not (len(args.llm_seat) == len(args.llm_provider) == len(args.llm_model)):
        parser.error(
            "--llm-seat, --llm-provider, --llm-model must be repeated the "
            f"same number of times (got {len(args.llm_seat)} / "
            f"{len(args.llm_provider)} / {len(args.llm_model)})"
        )

    llm_specs = list(zip(args.llm_provider, args.llm_model, args.llm_seat, strict=True))

    args.output_root.mkdir(parents=True, exist_ok=True)
    return run_cli(
        num_hands=args.num_hands,
        my_seat=args.my_seat,
        rng_seed=args.rng_seed,
        output_root=args.output_root,
        llm_specs=llm_specs,
    )


if __name__ == "__main__":
    sys.exit(main())

# llm-poker-arena Phase 2c (Interactive Human CLI — dogfood) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user play poker against `RandomAgent` + `RuleBasedAgent` via a terminal CLI, using only the existing Phase-1–2b public API. Purely a dogfooding deliverable — NOT a spec §16.1 MVP — intended to surface `PlayerView` UX gaps before Phase 3 async Agent widening and to provide a taste-test tool for the user.

**Architecture:** A new `HumanCLIAgent(Agent)` implementing the sync Phase-1 `Agent` ABC with overridable I/O hooks (for deterministic testing). A thin `cli/play.py` console entry point that constructs a mixed `[HumanCLIAgent, *bots]` lineup, runs a `Session`, and prints a per-hand summary. No engine / storage / session orchestrator modifications — this is pure consumer-side extension.

**Tech Stack:** Existing (Python 3.11+, pokerkit, Pydantic 2, pytest). Adds a console_script entry point `poker-play` via `[project.scripts]` in `pyproject.toml`. No new runtime deps.

---

## Pre-flight: Context, Scope, Phase 3 Obsolescence

### Why this exists

The user has asked whether humans can plug into the engine. Answer: **yes, via the sync `Agent` ABC**, but nothing was reserved FOR humans. This plan closes the gap with the smallest-possible deliverable:
1. Validates the Agent ABC contract from a human user's perspective (dogfooding)
2. Surfaces `PlayerView` UX issues that RandomAgent/RuleBasedAgent can't expose (they don't "read" the view; humans do)
3. Gives the user a tangible way to interact with the engine before Phase 3's multi-week LLM integration work

### Scope discipline

**In scope:**
- `HumanCLIAgent` class with input()/print() I/O injected via constructor (so tests can drive it with `io.StringIO`)
- `cli/play.py` console entry point with `--num-hands`, `--my-seat`, `--rng-seed` flags
- Unit test: simulated input streams through `HumanCLIAgent.decide()` → expected Action
- Integration test: 1 hand with scripted human responses → Session succeeds, all 3 JSONL layers + meta.json land

**Out of scope:**
- Async `decide()` (Phase 3)
- Per-turn timeout (`total_turn_timeout` per BR2-06 is an LLM/API concern)
- Pause / resume Session state
- Web UI (Phase 6 MVP 12)
- Multi-human play
- Any change to `engine/` / `storage/` / `session/` — this is pure consumer-side extension

### Phase 3 obsolescence (deliberate)

When Phase 3 widens `Agent` to `async def decide(view, tool_runner) -> TurnDecisionResult`, this `HumanCLIAgent` will need to be rewritten:
- `decide()` becomes async — can await stdin asynchronously (`asyncio.to_thread` wraps `input()`)
- Return type becomes `TurnDecisionResult` (not bare `Action`) — human provides `reasoning_stated` free-text, retry counters are all 0, `api_error=None`
- Still no ReAct iterations for humans

Phase 3 plan MUST include "update HumanCLIAgent to async interface" as one of its tasks. Until then, this sync implementation is THE interface humans use.

### Phase 2a/2b contracts respected (zero engine/storage touches)

- `Agent` ABC unchanged (`agents/base.py`)
- `Session.run()` unchanged — takes `Sequence[Agent]`, calls `.decide()` inline
- `AgentViewSnapshot.agent` populated from `provider_id()` via `_split_provider_id` — `"human:cli_v1"` → `("human", "cli_v1")` works
- `meta.json.seat_assignment` gets `{3: "human:cli_v1", 0: "random:uniform", ...}` — no schema change needed
- Blocking on `input()` is fine in sync Session — other seats' `decide()` are instant (RandomAgent microseconds, RuleBased also instant), no throughput concern
- Reproducibility: human seat breaks byte-level reproducibility of the session — acceptable per spec §11.1's layered promise (engine layer deterministic given same seeds; decision layer best-effort)

### Risks (short list)

1. **`input()` buffering in tests.** Tests must use `io.StringIO` / pytest `monkeypatch.setattr("builtins.input", ...)` rather than subprocess stdin to stay deterministic.
2. **Prompt line re-parsing for bet amounts.** User types `"raise_to 300"` or `raise_to\n300\n` — pick one style, stick to it. Plan uses "one action per prompt, amount on follow-up prompt if bet/raise_to".
3. **Entry point install.** `[project.scripts]` requires `pip install -e .` after pyproject change; document in T2.
4. **Readline/pytest segfault** (Phase 1 known): tests use `.venv/bin/pytest` via activate; no `uv run pytest`.
5. **Invalid-action retry loop.** If user types `fold` when fold isn't legal, or `"raise_to 50"` below min, CLI must reprompt — not crash. Test covers this.

---

## File Structure

```
src/llm_poker_arena/
├── agents/
│   ├── human_cli.py                 # NEW — HumanCLIAgent
│   └── (existing: base.py, random_agent.py, rule_based.py)
├── cli/                             # NEW subpackage
│   ├── __init__.py                  # NEW (empty docstring)
│   └── play.py                      # NEW — poker-play entry point

pyproject.toml                       # modify — add [project.scripts].poker-play

tests/
├── unit/
│   ├── test_human_cli_agent.py      # NEW
│   └── test_human_cli_integration.py# NEW
```

Total new src files: 3. Total new test files: 2. One pyproject.toml modification.

---

## Task 1: `HumanCLIAgent` + unit tests

**Files:**
- Create: `src/llm_poker_arena/agents/human_cli.py`
- Create: `tests/unit/test_human_cli_agent.py`

`HumanCLIAgent` reads action choices from an injectable input stream and writes prompts to an injectable output stream. Production default: `input` + `print`. Testing default: `io.StringIO` for both.

- [ ] **Step 1: Write failing tests**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_human_cli_agent.py`:

```python
"""Tests for HumanCLIAgent (sync Agent ABC implementation for terminal play)."""
from __future__ import annotations

import io

import pytest

from llm_poker_arena.agents.human_cli import HumanCLIAgent
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)


def _params() -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=False, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _seats() -> tuple[SeatPublicInfo, ...]:
    return tuple(
        SeatPublicInfo(
            seat=i, label=f"Player_{i}",
            position_short="UTG", position_full="Under the Gun",
            stack=10_000, invested_this_hand=0, invested_this_round=0,
            status="in_hand",
        )
        for i in range(6)
    )


def _view(*, legal_names: tuple[str, ...], raise_min_max: tuple[int, int] = (200, 10_000)) -> PlayerView:
    tools = []
    for name in legal_names:
        if name in ("bet", "raise_to"):
            tools.append(ActionToolSpec(
                name=name,
                args={"amount": {"min": raise_min_max[0], "max": raise_min_max[1]}},
            ))
        else:
            tools.append(ActionToolSpec(name=name, args={}))
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        seats_public=_seats(), opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=LegalActionSet(tools=tuple(tools)),
        opponent_stats={},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=1, immutable_session_params=_params(),
    )


def test_fold_is_accepted_verbatim() -> None:
    """User types 'fold' → Action(tool_name='fold', args={})."""
    stdin = io.StringIO("fold\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("fold", "call", "raise_to"))
    act = agent.decide(view)
    assert act == Action(tool_name="fold", args={})


def test_check_is_accepted_verbatim() -> None:
    stdin = io.StringIO("check\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("check", "bet"))
    act = agent.decide(view)
    assert act.tool_name == "check"


def test_raise_to_prompts_for_amount_on_separate_line() -> None:
    """User types 'raise_to' then '300' on the next prompt."""
    stdin = io.StringIO("raise_to\n300\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("fold", "call", "raise_to"), raise_min_max=(200, 10_000))
    act = agent.decide(view)
    assert act.tool_name == "raise_to"
    assert act.args == {"amount": 300}


def test_bet_prompts_for_amount_on_separate_line() -> None:
    stdin = io.StringIO("bet\n500\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("check", "bet"), raise_min_max=(100, 10_000))
    act = agent.decide(view)
    assert act.tool_name == "bet"
    assert act.args == {"amount": 500}


def test_illegal_tool_name_reprompts() -> None:
    """User types 'teleport' → agent complains; then types valid action."""
    stdin = io.StringIO("teleport\nfold\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("fold", "call"))
    act = agent.decide(view)
    assert act.tool_name == "fold"
    # Output includes an error for the first attempt.
    assert "not in legal" in stdout.getvalue().lower()


def test_raise_below_min_reprompts() -> None:
    """User types 'raise_to' then '50' (below min=200) → reprompt for amount."""
    stdin = io.StringIO("raise_to\n50\n400\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(
        legal_names=("fold", "call", "raise_to"),
        raise_min_max=(200, 10_000),
    )
    act = agent.decide(view)
    assert act == Action(tool_name="raise_to", args={"amount": 400})
    assert "out of" in stdout.getvalue().lower() or "below min" in stdout.getvalue().lower()


def test_amount_not_an_integer_reprompts() -> None:
    stdin = io.StringIO("raise_to\nabc\n400\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(
        legal_names=("fold", "call", "raise_to"),
        raise_min_max=(200, 10_000),
    )
    act = agent.decide(view)
    assert act.args == {"amount": 400}


def test_eof_mid_prompt_raises() -> None:
    """Unexpected stdin EOF during a prompt raises EOFError (clean propagation)."""
    stdin = io.StringIO("")  # no input
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("fold", "call"))
    with pytest.raises(EOFError):
        agent.decide(view)


def test_provider_id_is_stable_and_namespaced() -> None:
    """provider_id must split into ('human', 'cli_v1') per Session convention."""
    agent = HumanCLIAgent()
    pid = agent.provider_id()
    assert pid == "human:cli_v1"
    parts = pid.split(":", 1)
    assert parts[0] == "human"
    assert parts[1] == "cli_v1"


def test_view_renders_hole_community_stack_to_output() -> None:
    """Every decide() call prints enough info for the human to act."""
    stdin = io.StringIO("fold\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("fold", "call"))
    agent.decide(view)
    text = stdout.getvalue()
    # Hole cards, pot, to_call, and legal tools must all be visible.
    assert "As" in text and "Kd" in text
    assert "150" in text  # pot
    assert "fold" in text and "call" in text  # legal actions
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_human_cli_agent.py -v
```
Expected: `ModuleNotFoundError: No module named 'llm_poker_arena.agents.human_cli'`.

- [ ] **Step 3: Implement `human_cli.py`**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/agents/human_cli.py`:

```python
"""HumanCLIAgent: sync Agent that reads actions from a terminal.

Dogfood implementation for pre-Phase-3 play. When Phase 3 widens the
`Agent` ABC to `async def decide(view, tool_runner) -> TurnDecisionResult`,
this class will be rewritten to match.

I/O is injectable (via `input_stream` + `output_stream` constructor args)
so unit tests can drive it deterministically. Production default is
`sys.stdin` / `sys.stdout`.
"""
from __future__ import annotations

import sys
from typing import TextIO

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.views import PlayerView


_VALID_ACTION_NAMES: frozenset[str] = frozenset(
    {"fold", "check", "call", "bet", "raise_to", "all_in"}
)


class HumanCLIAgent(Agent):
    """Sync human agent reading from a text stream. See module docstring."""

    def __init__(
        self,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
    ) -> None:
        self._in: TextIO = input_stream if input_stream is not None else sys.stdin
        self._out: TextIO = output_stream if output_stream is not None else sys.stdout

    def provider_id(self) -> str:
        return "human:cli_v1"

    # ----- Agent ABC -------------------------------------------------

    def decide(self, view: PlayerView) -> Action:
        self._render_view(view)
        legal = {t.name for t in view.legal_actions.tools}
        while True:
            tool_name = self._prompt("Choose action: ").strip()
            if tool_name not in _VALID_ACTION_NAMES:
                self._emit(f"'{tool_name}' is not a known action. Valid: {sorted(_VALID_ACTION_NAMES)}\n")
                continue
            if tool_name not in legal:
                self._emit(f"'{tool_name}' is not in legal set this turn: {sorted(legal)}\n")
                continue
            if tool_name in ("bet", "raise_to"):
                spec = next(t for t in view.legal_actions.tools if t.name == tool_name)
                bounds = spec.args.get("amount") if isinstance(spec.args, dict) else None
                if not isinstance(bounds, dict):
                    self._emit(f"'{tool_name}' missing amount bounds (engine bug?)\n")
                    continue
                amount = self._prompt_amount(int(bounds["min"]), int(bounds["max"]))
                return Action(tool_name=tool_name, args={"amount": amount})
            return Action(tool_name=tool_name, args={})

    # ----- internals -------------------------------------------------

    def _prompt_amount(self, min_amt: int, max_amt: int) -> int:
        while True:
            raw = self._prompt(f"Amount (int in [{min_amt}, {max_amt}]): ").strip()
            try:
                amt = int(raw)
            except ValueError:
                self._emit(f"'{raw}' is not an integer\n")
                continue
            if not (min_amt <= amt <= max_amt):
                self._emit(f"{amt} is out of bounds [{min_amt}, {max_amt}]\n")
                continue
            return amt

    def _render_view(self, view: PlayerView) -> None:
        hid = view.hand_id
        my_seat = view.my_seat
        my_info = view.seats_public[my_seat]
        to_call = view.current_bet_to_match - view.my_invested_this_round

        self._emit("\n" + "=" * 60 + "\n")
        self._emit(
            f"Hand {hid}  |  your seat: {my_seat} ({my_info.position_short})  |  street: {view.street.value}\n"
        )
        self._emit(
            f"Button: seat {view.button_seat}  |  pot: {view.pot}  |  your stack: {view.my_stack}  |  to_call: {to_call}\n"
        )
        if view.community:
            self._emit(f"Community: {' '.join(view.community)}\n")
        self._emit(f"Your hole cards: {' '.join(view.my_hole_cards)}\n")
        self._emit("Other seats:\n")
        for s in view.seats_public:
            if s.seat == my_seat:
                continue
            self._emit(
                f"  seat {s.seat} ({s.label}, {s.position_short}): {s.stack} chips, {s.status}\n"
            )
        self._emit("Legal actions this turn:\n")
        for t in view.legal_actions.tools:
            if t.name in ("bet", "raise_to"):
                bounds = t.args.get("amount") if isinstance(t.args, dict) else None
                if isinstance(bounds, dict):
                    self._emit(f"  {t.name}  (amount in [{bounds['min']}, {bounds['max']}])\n")
                else:
                    self._emit(f"  {t.name}\n")
            else:
                self._emit(f"  {t.name}\n")
        self._emit("-" * 60 + "\n")

    def _prompt(self, prompt: str) -> str:
        self._emit(prompt)
        line = self._in.readline()
        if line == "":  # EOF
            raise EOFError("HumanCLIAgent: input stream closed during prompt")
        return line.rstrip("\n")

    def _emit(self, text: str) -> None:
        self._out.write(text)
        self._out.flush()
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_human_cli_agent.py -v
```
Expected: 10 passed.

- [ ] **Step 5: Lint + type**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/agents/human_cli.py tests/unit/test_human_cli_agent.py && git commit -m "feat(agents): HumanCLIAgent — sync terminal-based Agent with injectable I/O (pre-Phase-3 dogfood)"
```

---

## Task 2: `cli/play.py` + console_script entry point

**Files:**
- Create: `src/llm_poker_arena/cli/__init__.py`
- Create: `src/llm_poker_arena/cli/play.py`
- Modify: `pyproject.toml` (add `[project.scripts]`)
- Create: `tests/unit/test_cli_play_smoke.py`

The CLI takes `--num-hands` (default 6), `--my-seat` (default 3), `--rng-seed` (default 42). Builds a 6-seat agent list with `HumanCLIAgent` at `my_seat` and an alternating mix of Random / RuleBased at the other 5 seats. Runs a `Session` into a tmp-timestamped dir under `runs/`, prints a per-hand summary.

- [ ] **Step 1: Write failing test**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_cli_play_smoke.py`:

```python
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
    """End-to-end: run 2 hands, human always folds, session lands all artifacts."""
    from llm_poker_arena.cli.play import run_cli
    # Every prompt gets "fold" — CLI's legal filter will validate. Preflop
    # UTG/HJ/CO/BTN all have fold in legal. Human seat 3 is UTG for button=0.
    folds = "fold\n" * 20  # enough for multiple actions across 2 hands

    rc = run_cli(
        num_hands=2, my_seat=3, rng_seed=42, output_root=tmp_path,
        human_input=io.StringIO(folds),
        human_output=io.StringIO(),
    )
    assert rc == 0
    # Find the session dir — run_cli creates runs/session_<...>/ under output_root.
    session_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(session_dirs) == 1
    sess = session_dirs[0]
    for fname in (
        "canonical_private.jsonl", "public_replay.jsonl",
        "agent_view_snapshots.jsonl", "meta.json", "config.json",
    ):
        assert (sess / fname).exists(), fname

    # meta.json has the human seat_assignment entry.
    import json
    meta = json.loads((sess / "meta.json").read_text())
    assert meta["seat_assignment"]["3"] == "human:cli_v1"
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_cli_play_smoke.py -v
```
Expected: ModuleNotFoundError on `llm_poker_arena.cli.play`.

- [ ] **Step 3: Create cli subpackage + play.py**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/cli/__init__.py`:

```python
"""Command-line entry points.

Phase 2c: interactive terminal play (`poker-play`). Pre-Phase-3 dogfood.
Phase 3 will add async entry points for LLM-driven sessions.
"""
```

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/cli/play.py`:

```python
"""`poker-play` CLI: interactive terminal game with HumanCLIAgent.

Not a spec §16.1 MVP task — dogfooding deliverable. Builds a mixed
lineup (1 human seat + 5 bots), runs a Phase-2a `Session`, prints a
per-hand summary from `meta.json` / `canonical_private.jsonl`.
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
    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
    return f"session_{ts}_seed{rng_seed}"


def _print_hand_summary(
    session_dir: Path, my_seat: int, output_stream: TextIO,
) -> None:
    """Emit a terse per-hand summary after the Session finishes."""
    meta = json.loads((session_dir / "meta.json").read_text())
    chip_pnl = meta["chip_pnl"]
    my_pnl = int(chip_pnl[str(my_seat)])
    output_stream.write("\n" + "=" * 60 + "\n")
    output_stream.write(
        f"Session complete — {meta['total_hands_played']} hands in {meta['session_wall_time_sec']}s\n"
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
) -> int:
    """Programmatic entry point; returns shell-style return code."""
    out_stream = human_output if human_output is not None else sys.stdout
    if num_hands % 6 != 0:
        # SessionConfig requires num_hands % num_players == 0; round UP to 6x.
        num_hands = ((num_hands + 5) // 6) * 6
        out_stream.write(
            f"[poker-play] num_hands rounded up to {num_hands} (must be multiple of num_players=6)\n"
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
    Session(
        config=cfg, agents=agents, output_dir=session_dir,
        session_id=session_dir.name,
    ).run()

    _print_hand_summary(session_dir, my_seat=my_seat, output_stream=out_stream)
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
```

- [ ] **Step 4: Register console_script**

Edit `/Users/zcheng256/llm-poker-arena/pyproject.toml`. Add after the `[project.optional-dependencies]` block:

```toml
[project.scripts]
poker-play = "llm_poker_arena.cli.play:main"
```

- [ ] **Step 5: Reinstall editable + verify entry point**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pip install -e . --quiet && which poker-play
```
Expected: prints a path inside `.venv/bin/poker-play`.

- [ ] **Step 6: Run tests**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_cli_play_smoke.py -v
```
Expected: 3 passed.

- [ ] **Step 7: Lint + type**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy
```
Expected: clean.

- [ ] **Step 8: Commit**

```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/cli/__init__.py src/llm_poker_arena/cli/play.py pyproject.toml tests/unit/test_cli_play_smoke.py && git commit -m "feat(cli): poker-play console entry point (HumanCLIAgent + mixed bots)"
```

---

## Task 3: Integration test — scripted human plays 1 full hand to showdown

**Files:**
- Create: `tests/unit/test_human_cli_integration.py`

Run a single-hand session with a scripted input sequence that reaches showdown (human calls every decision). Assert the hand settles correctly, chip conservation holds, and agent_view_snapshots for the human seat are correctly tagged.

- [ ] **Step 1: Write failing test**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_human_cli_integration.py`:

```python
"""Integration: Session with 1 human seat + 5 bots + scripted 'call everything' input."""
from __future__ import annotations

import io
import json
from pathlib import Path


def test_human_cli_call_only_session_finishes_cleanly(tmp_path: Path) -> None:
    from llm_poker_arena.cli.play import run_cli

    # Feed enough 'call' / 'check' responses for the human to get through
    # up to ~30 decisions (6 hands × ~5 turns per hand max). Any of these
    # actions must be in legal set when it's the human's turn; we mix both
    # to cover the "no bet to call" case (check) and "facing bet" case (call).
    actions = ("call\n" + "check\n") * 50
    input_stream = io.StringIO(actions)
    output_stream = io.StringIO()

    rc = run_cli(
        num_hands=6, my_seat=3, rng_seed=7,
        output_root=tmp_path,
        human_input=input_stream, human_output=output_stream,
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
    assert human_turns >= 6, f"expected ≥ 6 human turns, got {human_turns}"

    # Chip conservation across the whole session.
    meta = json.loads((sess / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0


def test_human_cli_session_meta_marks_human_seat(tmp_path: Path) -> None:
    """meta.json.seat_assignment labels the human seat with 'human:cli_v1'."""
    from llm_poker_arena.cli.play import run_cli

    rc = run_cli(
        num_hands=6, my_seat=2, rng_seed=3,
        output_root=tmp_path,
        human_input=io.StringIO("call\n" * 50),
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
```

- [ ] **Step 2: Run — expect pass (Tasks 1+2 land the needed code)**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_human_cli_integration.py -v
```
Expected: 2 passed.

- [ ] **Step 3: Full suite + lint + type**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest -m 'not slow' -q && ruff check . && mypy
```
Expected: 195 + 10 + 3 + 2 = 210 passing. Clean. (Actual baseline may differ by ±1 per Phase-2b numbering; the delta +15 from Phase 2c is the fixed addition.)

- [ ] **Step 4: Commit**

```bash
cd /Users/zcheng256/llm-poker-arena && git add tests/unit/test_human_cli_integration.py && git commit -m "test(cli): HumanCLIAgent full-session integration — human seat labelled + chip conservation holds"
```

---

## Self-Review

**1. Spec coverage.**
- `Agent` ABC consumer-side extension — does NOT touch spec-mandated contracts; no spec change needed.
- spec §15.2 B10-human-in-the-loop: still backlog in spec text; this plan is an early partial for dev dogfooding, not a spec bump.
- spec §11.1 reproducibility: human seat breaks decision-layer byte-reproducibility (engine layer still deterministic). Plan acknowledges in Pre-flight.

**2. Placeholder scan.** Grep'd plan: no TODO / TBD / FIXME. Every task has full code.

**3. Type consistency.**
- `HumanCLIAgent(input_stream: TextIO | None = None, output_stream: TextIO | None = None)` — constructor signature consistent across Task 1 tests, Task 2 `build_agents`, Task 3 integration test.
- `build_agents(num_players, my_seat, human_input, human_output) -> list[Agent]` — kwargs-only via `*,` separator.
- `run_cli(num_hands, my_seat, rng_seed, output_root, human_input=None, human_output=None) -> int` — returns shell rc.
- `provider_id()` returns `"human:cli_v1"`. Split via `:` → `("human", "cli_v1")`. Matches `_split_provider_id` in Session.

**4. Phase-1/2a/2b invariants respected.**
- No engine / storage / session touches.
- No destructive git; no `Co-Authored-By`; no warning suppression.
- Pydantic tuple fields untouched (no new DTOs).
- `apply_action(state, actor, action)` — no `config` kwarg; we don't call it directly anyway, Session does.
- `state.actor_index is not None` — Session's job; we just supply an Agent.

**5. Phase-3 obsolescence explicit.** Pre-flight names the rewrite contract. Phase-3 plan writer is required (by memory note) to include "migrate HumanCLIAgent to async" as a task.

**6. No broken-world assertions.**
- `pyproject.toml` `[project.scripts]` addition tested in Task 2 Step 5 (checks `which poker-play`).
- `run_cli`'s `num_hands % 6` rounding-up is tested implicitly (Tasks 2/3 use num_hands=6 which divides cleanly); not strictly tested when rounding fires, but the branch is reachable only for user-input non-multiples-of-6.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-04-24-llm-poker-arena-phase-2c-human-cli.md`. Two execution options:

**1. Subagent-Driven (recommended for safety)** — dispatch a fresh subagent per task, no formal Codex round (scope is ~200 lines of production code; dogfood deliverable, not on MVP critical path).

**2. Inline Execution** — execute in this session via `superpowers:executing-plans`.

For this scale of work (3 tasks, ~400 lines total including tests), inline execution is reasonable. The key risks — `input()` stream handling in tests, `[project.scripts]` install mechanics, `build_agents` seat ordering — are all covered by unit tests.

**Which approach?**

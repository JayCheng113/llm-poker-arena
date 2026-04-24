# llm-poker-arena Phase 2a (MVP 6 Storage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 3-layer JSONL observability stack (canonical_private / public_replay / agent_view_snapshots) + Session orchestrator + RuleBased (B2) agent, so that 1000 mock-agent hands produce durable disk artifacts with zero private-info leakage in the public layer and ≤ 10 entries lost on crash.

**Architecture:** Event-emitting Session replaces Phase-1 `run_single_hand`. Each hand drives the audited engine loop (unchanged from Phase 1) and fans out structured events to three BatchedJsonlWriters. Access is split by trust boundary: a `PublicLogReader` requires only `public_replay.jsonl` (shippable as open dataset); a `PrivateLogReader` needs all three files plus an access-token check. Schemas are Pydantic-frozen with tuple sequence fields (deep immutability), and every DTO round-trips through `model_dump_json()` so the writer serializes by-contract, not by-accident. A minimal `RuleBasedAgent` implements spec §15.2 B2 so that the 1000-hand integration exercises a heterogeneous `[Random, RuleBased]` lineup rather than a pure-random degenerate case.

**Tech Stack:** Python 3.12 / pokerkit 0.7.3 / Pydantic 2 / pytest 9 / hypothesis 6 / ruff / mypy --strict. No new runtime deps (no DuckDB yet — that is Phase 2b; no PHH exporter yet — deferred to Phase 2b or later). Standard library: `atexit`, `signal`, `json`, `pathlib`, `datetime`.

---

## Pre-flight: Context, Pitfalls, Baseline

### Phase 1 baseline you MUST read before starting

- Spec v2.1.1: `docs/superpowers/specs/2026-04-23-llm-poker-arena-design-v2.md` — read §2.2 P2 (trust boundary), §3.6 (hand lifecycle), §7.1-§7.6 (JSONL schemas + access control + meta.json), §8.1 (BatchedJsonlWriter), §15.2 (B2 RuleBased baseline definition). Ignore §4-§6 and §8.2-§8.3 — those are Phase 3 / Phase 2b.
- PokerKit 0.7.3 API reference: `docs/superpowers/notes/pokerkit-0.7.3-api.md` — this is the empirically-verified API doc; spec + prior plans may have stale snippets.
- Current HEAD `21570ed` on `main`; Phase 1 locked public engine API at `src/llm_poker_arena/engine/__init__.py` (27 symbols).

### Known-painful pitfalls from Phase 1 — DO NOT repeat

1. **Pydantic frozen ≠ deep immutability.** Every sequence field on boundary DTOs MUST be `tuple[X, ...]` not `list[X]`. Lists passed to tuple fields fail Pydantic validation with a confusing message. See `src/llm_poker_arena/engine/views.py:1-20` for the documented convention. This plan's schemas follow the same rule.
2. **`state.is_actor_required` does NOT exist in pokerkit 0.7.3.** Use `state.actor_index is not None` as the predicate. Phase 1's rebuy driver discovered this — do not rewrite that bug.
3. **`apply_action(state, actor, action)` has NO `config` kwarg.** T12 dropped it; audit runs unconditionally via `state._config` internally. Any plan snippet you might have seen elsewhere with `apply_action(..., config=cfg)` is stale.
4. **`repr(card) == 'As'`, `str(card) == 'ACE OF SPADES (As)'`.** When reading pokerkit `Card` objects, use `repr(...)` for the 2-char compact form. The engine's `engine/_internal/deck.py::card_to_str` helper already does this — prefer calling it.
5. **`state.pots` is a generator AND empty during in-flight betting.** Use `state.total_pot_amount` as the canonical pot accessor.
6. **Never `warnings.catch_warnings()` / `simplefilter("ignore")` without empirical proof.** Phase 1 had a wrapper that was masking a real regression detector; the feedback memory `feedback_verify_noise_before_suppressing` explains why.
7. **Commit messages do NOT carry `Co-Authored-By` trailers.** Copy the plan-mandated message verbatim.
8. **`.venv/bin/python -c "import readline"` segfaults on this workstation.** Use `source .venv/bin/activate && pytest` or `.venv/bin/pytest` to run tests. A known workaround on memory file.
9. **`num_hands % num_players == 0` is already enforced by `SessionConfig` validator** (`engine/config.py:38-42`). Don't re-implement.
10. **Auto-rebuy is driven by `HandContext.initial_stacks`** — session orchestrator must always construct each hand's context with `initial_stacks = (config.starting_stack,) * config.num_players`, never persisting stack deltas across hands. Spec §3.5 / B-05.

### Pre-existing state to inherit (do NOT modify)

- Engine public API at `src/llm_poker_arena/engine/__init__.py` is **locked**. Phase 2 imports from there, does not add to it.
- `engine/_internal/rebuy.py::run_single_hand` stays intact. Phase 2's Session **does not** call it — Session re-implements the multi-hand loop with event emission. `run_single_hand` remains as the MVP 4 integration test driver and is exercised by `tests/unit/test_integration_thousand_hands.py` (Phase 1 T17). Leave it alone.
- `agents/base.py::Agent` ABC is **synchronous** (`decide(view) -> Action` + `provider_id() -> str`). Phase 2a uses this unchanged. Phase 3 widens it to async with `TurnDecisionResult`; do not pre-empt that here.
- `agents/random_agent.py::RandomAgent` is the existing Phase-1 agent. Reuse for Phase 2 integration tests.

### Branch/worktree decision

Phase 1 worked cleanly on `main` without worktrees (this is user-observed preference). Phase 2a continues on `main` with the same discipline: never destructive git, every task = one commit with plan-verbatim message, no `--no-verify`.

If you prefer a feature branch (`feature/phase-2a`), create it before Task 1 but note that rebasing across 11 commits has its own risk; main-line commit has been working.

---

## File Structure

```
src/llm_poker_arena/
├── storage/                          # NEW subpackage
│   ├── __init__.py                   # (empty docstring; no public re-exports yet)
│   ├── jsonl_writer.py               # BatchedJsonlWriter with SIGTERM + atexit drain
│   ├── schemas.py                    # Pydantic frozen DTOs for 3 layers + public event union
│   ├── layer_builders.py             # CanonicalState + turn info → layer records
│   ├── access_control.py             # PublicLogReader / PrivateLogReader
│   └── meta.py                       # SessionMeta builder (meta.json shape)
├── session/                          # NEW subpackage
│   ├── __init__.py                   # (empty docstring)
│   └── session.py                    # Session orchestrator (replaces run_single_hand)
├── agents/
│   ├── base.py                       # (existing, unchanged)
│   ├── random_agent.py               # (existing, unchanged)
│   └── rule_based.py                 # NEW: B2 TAG bot
└── engine/                           # UNCHANGED (do not modify public API)

tests/
├── unit/
│   ├── test_jsonl_writer.py          # NEW
│   ├── test_storage_schemas.py       # NEW
│   ├── test_layer_builders.py        # NEW
│   ├── test_access_control.py        # NEW
│   ├── test_meta.py                  # NEW
│   ├── test_rule_based_agent.py      # NEW
│   ├── test_session_orchestrator.py  # NEW (3-hand smoke)
│   ├── test_mvp6_integration.py      # NEW (1000-hand full stack)
│   └── test_batch_flush_durability.py# NEW (SIGTERM / subprocess)
└── property/
    └── test_public_replay_no_leak.py # NEW (hypothesis)

Total NEW src files: 9 production .py + 1 extra `rule_based.py` = 10 under src/
Total NEW test files: 9
```

---

## Task 1: Scaffold `storage/` + `session/` subpackages

**Files:**
- Create: `src/llm_poker_arena/storage/__init__.py`
- Create: `src/llm_poker_arena/session/__init__.py`
- Create: `tests/unit/test_phase2a_scaffolding.py`

- [ ] **Step 1: Write failing smoke test for the new subpackages**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_phase2a_scaffolding.py`:

```python
"""Smoke: Phase 2a subpackages exist and are importable."""
from __future__ import annotations


def test_storage_subpackage_importable() -> None:
    import llm_poker_arena.storage as storage
    assert storage.__doc__ is not None


def test_session_subpackage_importable() -> None:
    import llm_poker_arena.session as session
    assert session.__doc__ is not None
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_phase2a_scaffolding.py -v
```
Expected: `ModuleNotFoundError: No module named 'llm_poker_arena.storage'`.

- [ ] **Step 3: Create the two `__init__.py` files**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/storage/__init__.py`:

```python
"""3-layer JSONL observability stack (canonical_private / public_replay / agent_view_snapshots).

Phase 2a (MVP 6): writer, schemas, layer builders, access control, meta.json.
Phase 2b will add DuckDB query layer + PHH exporter on top.
"""
```

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/session/__init__.py`:

```python
"""Session orchestrator (multi-hand loop + audit + event emission).

Replaces Phase-1 `engine._internal.rebuy.run_single_hand` for end-to-end runs.
Phase 2a: mock-agent sessions. Phase 3 will widen to async ReAct + censored
hand handling per spec §3.6 / BR2-01.
"""
```

- [ ] **Step 4: Run tests; expect pass**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_phase2a_scaffolding.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Full suite + lint**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest && ruff check . && mypy
```
Expected: 112 + 2 = 114 passing, ruff clean, mypy clean.

- [ ] **Step 6: Commit**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/storage/__init__.py src/llm_poker_arena/session/__init__.py tests/unit/test_phase2a_scaffolding.py && git commit -m "chore(scaffolding): storage + session subpackage skeletons for Phase 2a"
```

---

## Task 2: `BatchedJsonlWriter` (`storage/jsonl_writer.py`)

**Files:**
- Create: `src/llm_poker_arena/storage/jsonl_writer.py`
- Create: `tests/unit/test_jsonl_writer.py`

Per spec §8.1: buffered writer with `BATCH_SIZE=10` flush-at-count, `FLUSH_INTERVAL_MS=200` flush-at-time, atexit drain, SIGTERM drain. Every call to `write(dict)` either buffers or flushes; buffer is bounded, so crash at any point loses ≤ `BATCH_SIZE` entries.

- [ ] **Step 1: Write failing tests**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_jsonl_writer.py`:

```python
"""Tests for BatchedJsonlWriter (durability + batch semantics)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_poker_arena.storage.jsonl_writer import BatchedJsonlWriter


def _lines(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def test_writes_buffer_flushes_at_batch_size(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    w = BatchedJsonlWriter(p)
    # BATCH_SIZE=10 so first 9 don't flush.
    for i in range(9):
        w.write({"i": i})
    assert _lines(p) == []  # still buffered
    w.write({"i": 9})  # 10th write triggers flush
    assert len(_lines(p)) == 10
    w.close()


def test_close_drains_remaining(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    w = BatchedJsonlWriter(p)
    for i in range(3):
        w.write({"i": i})
    assert _lines(p) == []
    w.close()
    assert len(_lines(p)) == 3


def test_time_based_flush(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """After FLUSH_INTERVAL_MS elapses since last flush, next write triggers a drain."""
    p = tmp_path / "out.jsonl"
    w = BatchedJsonlWriter(p)

    # Advance monotonic clock by > FLUSH_INTERVAL_MS between writes.
    clock = [0]
    monkeypatch.setattr(
        "llm_poker_arena.storage.jsonl_writer.time.monotonic_ns",
        lambda: clock[0],
    )
    w.write({"i": 0})
    clock[0] += (BatchedJsonlWriter.FLUSH_INTERVAL_MS + 50) * 1_000_000
    w.write({"i": 1})
    # First write buffered; second write after interval triggers flush of both.
    assert len(_lines(p)) == 2
    w.close()


def test_json_serialization_is_deterministic(tmp_path: Path) -> None:
    """Dict keys must serialize in sorted order for diff-friendliness."""
    p = tmp_path / "out.jsonl"
    w = BatchedJsonlWriter(p)
    # Intentionally unsorted-key dicts.
    w.write({"b": 2, "a": 1, "c": 3})
    w.close()
    text = p.read_text().strip()
    # json.dumps with sort_keys=True → '{"a": 1, "b": 2, "c": 3}'
    assert text == '{"a": 1, "b": 2, "c": 3}'


def test_append_mode_preserves_prior_content(tmp_path: Path) -> None:
    """Reopening a writer on the same path appends; prior lines survive."""
    p = tmp_path / "out.jsonl"
    w1 = BatchedJsonlWriter(p)
    w1.write({"i": 0})
    w1.close()
    w2 = BatchedJsonlWriter(p)
    w2.write({"i": 1})
    w2.close()
    assert _lines(p) == [{"i": 0}, {"i": 1}]


def test_write_after_close_raises(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    w = BatchedJsonlWriter(p)
    w.close()
    with pytest.raises(RuntimeError, match="closed"):
        w.write({"i": 0})
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_jsonl_writer.py -v
```
Expected: `ModuleNotFoundError: No module named 'llm_poker_arena.storage.jsonl_writer'`.

- [ ] **Step 3: Implement `jsonl_writer.py`**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/storage/jsonl_writer.py`:

```python
"""Buffered JSONL writer with periodic/size-based fsync + crash-safe drain.

Spec §8.1 / H-10. Guarantees:
  - Flush every `BATCH_SIZE` records OR `FLUSH_INTERVAL_MS` since last flush.
  - Drain + fsync on atexit and SIGTERM.
  - Crash at arbitrary point loses at most `BATCH_SIZE` buffered records.

Each record serializes as one line via `json.dumps(..., sort_keys=True)` for
deterministic output (diff-friendly under same input).
"""
from __future__ import annotations

import atexit
import json
import os
import signal
import time
from pathlib import Path
from typing import Any


class BatchedJsonlWriter:
    """Buffered append-only JSONL writer."""

    BATCH_SIZE: int = 10
    FLUSH_INTERVAL_MS: int = 200

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._buffer: list[str] = []
        self._f = self._path.open("a", encoding="utf-8")
        self._last_flush_ns: int = time.monotonic_ns()
        self._closed: bool = False
        atexit.register(self._drain_silent)
        # SIGTERM: drain then re-raise default behavior. We do not replace the
        # handler globally because multiple writers may register; each writes
        # independently and then the default terminator runs.
        prev = signal.getsignal(signal.SIGTERM)
        def _on_sigterm(signum: int, frame: Any) -> None:  # noqa: ANN401
            self._drain_silent()
            if callable(prev):
                prev(signum, frame)
        signal.signal(signal.SIGTERM, _on_sigterm)

    def write(self, record: dict[str, Any]) -> None:
        """Append one record. Flushes if batch-size or time-interval triggered."""
        if self._closed:
            raise RuntimeError("BatchedJsonlWriter is closed")
        self._buffer.append(json.dumps(record, sort_keys=True))
        if len(self._buffer) >= self.BATCH_SIZE:
            self._flush()
            return
        # time-based flush
        if (time.monotonic_ns() - self._last_flush_ns) >= self.FLUSH_INTERVAL_MS * 1_000_000:
            self._flush()

    def flush(self) -> None:
        """Force-drain the buffer to disk (hand-end checkpoint)."""
        self._flush()

    def close(self) -> None:
        if self._closed:
            return
        self._drain_silent()
        self._f.close()
        self._closed = True

    # ----- internals -----

    def _flush(self) -> None:
        if not self._buffer:
            return
        self._f.write("\n".join(self._buffer) + "\n")
        self._f.flush()
        os.fsync(self._f.fileno())
        self._buffer.clear()
        self._last_flush_ns = time.monotonic_ns()

    def _drain_silent(self) -> None:
        """atexit-safe: never raise."""
        try:
            self._flush()
        except Exception:  # noqa: BLE001 — atexit path, must not propagate
            pass
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_jsonl_writer.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Lint + type**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy
```
Expected: clean. If ruff flags `ANN401` on the SIGTERM frame parameter, keep the `# noqa: ANN401` — signal-handler signatures require `Any` for the frame object.

- [ ] **Step 6: Commit**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/storage/jsonl_writer.py tests/unit/test_jsonl_writer.py && git commit -m "feat(storage): BatchedJsonlWriter with size/time flush + atexit/SIGTERM drain"
```

---

## Task 3: Pydantic schemas for the 3 layers (`storage/schemas.py`)

**Files:**
- Create: `src/llm_poker_arena/storage/schemas.py`
- Create: `tests/unit/test_storage_schemas.py`

Per spec §7.2 (canonical_private), §7.3 (public_replay events), §7.4 (agent_view_snapshots). All frozen, all sequence fields are tuples. Phase 2a populates the ReAct-specific fields of `AgentViewSnapshot` with safe defaults (mock agents do not iterate); schema is forward-compatible with Phase 3.

- [ ] **Step 1: Write failing tests**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_storage_schemas.py`:

```python
"""Tests for Phase 2a Pydantic storage schemas (round-trip + frozen + tuple fields)."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from llm_poker_arena.storage.schemas import (
    ActionRecordPrivate,
    AgentDescriptor,
    AgentViewSnapshot,
    CanonicalPrivateHandRecord,
    HandResultPrivate,
    PublicReplayEvent,
    WinnerInfo,
)


def _winner_info() -> WinnerInfo:
    return WinnerInfo(seat=2, winnings=2450, best_hand_desc="Set of 7s")


def _hand_result() -> HandResultPrivate:
    return HandResultPrivate(
        showdown=True,
        winners=(_winner_info(),),
        side_pots=(),
        final_invested={"1": 1200, "2": 1200},
        net_pnl={"1": -1200, "2": 1250},
    )


def _action_record() -> ActionRecordPrivate:
    return ActionRecordPrivate(
        seat=3, street="flop", action_type="raise_to",
        amount=725, is_forced_blind=False, turn_index=12,
    )


def _canonical_hand() -> CanonicalPrivateHandRecord:
    return CanonicalPrivateHandRecord(
        hand_id=127,
        started_at="2026-04-23T18:12:33.123Z",
        ended_at="2026-04-23T18:13:05.456Z",
        button_seat=4, sb_seat=5, bb_seat=0,
        deck_seed=42_127,
        starting_stacks={"1": 10_000, "2": 10_000},
        hole_cards={"1": ("Ah", "Kh"), "2": ("7s", "7c")},
        community=("7c", "2d", "5s", "9h", "Ah"),
        actions=(_action_record(),),
        result=_hand_result(),
    )


def _agent_descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        provider="random", model="uniform", version="phase1",
        temperature=None, seed=None,
    )


def _snapshot() -> AgentViewSnapshot:
    return AgentViewSnapshot(
        hand_id=127, turn_id="127-flop-3", session_id="session_abc",
        seat=3, street="flop", timestamp="2026-04-23T18:12:55.789Z",
        view_at_turn_start={"my_seat": 3, "my_hole_cards": ["Ah", "Kh"]},
        iterations=(),
        final_action={"type": "raise_to", "amount": 725},
        is_forced_blind=False,
        total_utility_calls=0,
        api_retry_count=0, illegal_action_retry_count=0,
        no_tool_retry_count=0, tool_usage_error_count=0,
        default_action_fallback=False,
        api_error=None,
        turn_timeout_exceeded=False,
        total_tokens={},
        wall_time_ms=0,
        agent=_agent_descriptor(),
    )


def test_canonical_hand_frozen_forbids_extra() -> None:
    h = _canonical_hand()
    with pytest.raises(ValidationError):
        CanonicalPrivateHandRecord(**{**h.model_dump(), "unexpected_field": 1})


def test_canonical_hand_sequence_fields_are_tuples() -> None:
    h = _canonical_hand()
    # Pydantic serializes tuple fields; tuples are immutable so constructing
    # from a list must still yield a tuple in the model.
    h2 = CanonicalPrivateHandRecord(**h.model_dump())
    assert isinstance(h2.community, tuple)
    assert isinstance(h2.actions, tuple)
    assert isinstance(h2.result.winners, tuple)


def test_canonical_hand_round_trip() -> None:
    h = _canonical_hand()
    blob = h.model_dump_json()
    back = CanonicalPrivateHandRecord.model_validate_json(blob)
    assert back == h


def test_agent_view_snapshot_frozen_and_round_trip() -> None:
    s = _snapshot()
    # frozen: attribute reassignment denied
    with pytest.raises(ValidationError):
        s.seat = 5  # type: ignore[misc]
    back = AgentViewSnapshot.model_validate_json(s.model_dump_json())
    assert back == s


def test_public_replay_event_union_roundtrip() -> None:
    # hand_started
    e1 = PublicReplayEvent.model_validate(
        {"type": "hand_started", "hand_id": 1, "button_seat": 4,
         "blinds": {"sb": 50, "bb": 100}}
    )
    assert e1.type == "hand_started"
    # action
    e2 = PublicReplayEvent.model_validate(
        {"type": "action", "hand_id": 1, "seat": 3, "street": "preflop",
         "action": {"type": "raise_to", "amount": 300}}
    )
    assert e2.type == "action"
    # showdown with per-seat revealed cards (tuple of 2-char strings)
    e3 = PublicReplayEvent.model_validate(
        {"type": "showdown", "hand_id": 1,
         "revealed": {"1": ("Ah", "Kh"), "3": ("2d", "2h")}}
    )
    assert e3.type == "showdown"
    # round-trip
    for e in (e1, e2, e3):
        assert PublicReplayEvent.model_validate_json(e.model_dump_json()) == e


def test_public_replay_event_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        PublicReplayEvent.model_validate({"type": "unknown_event", "hand_id": 1})


def test_agent_descriptor_supports_all_phase1_provider_values() -> None:
    # Phase 2a: only random + rule_based. Phase 3 adds anthropic/openai/google.
    for provider in ("random", "rule_based"):
        AgentDescriptor(provider=provider, model="x", version="phase1",
                        temperature=None, seed=None)


def test_canonical_hand_blinds_sum_sanity() -> None:
    """starting_stacks map must have num_players entries."""
    h = _canonical_hand()
    # Schema does not enforce player count (that is Session's job). Confirm
    # the schema accepts arbitrary-length maps.
    assert len(h.starting_stacks) == 2
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_storage_schemas.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `schemas.py`**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/storage/schemas.py`:

```python
"""Frozen Pydantic DTOs for Phase 2a three-layer JSONL observability stack.

- `CanonicalPrivateHandRecord` — one line per hand in canonical_private.jsonl.
- `PublicReplayEvent` — tagged union; one line per event in public_replay.jsonl.
- `AgentViewSnapshot` — one line per turn per agent in agent_view_snapshots.jsonl.

All models are `frozen=True`, `extra="forbid"`. Every sequence field is
declared as `tuple[X, ...]` because Pydantic 2's `frozen=True` is shallow —
a list field would still allow `record.actions.append(...)` and silently
corrupt the serialized history. Tuples close that hole structurally.

Phase 2a populates the ReAct-specific fields of `AgentViewSnapshot` with
degenerate defaults (mock agents do not iterate, never hit api_error, never
time out). The schema is forward-compatible with Phase 3 which fills the
`iterations` tuple and the four retry counters properly.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag


def _frozen() -> ConfigDict:
    return ConfigDict(extra="forbid", frozen=True)


# ----------------------------------------------------------- agent descriptor

class AgentDescriptor(BaseModel):
    """Minimal per-snapshot agent identity (phase-1 mock agents: random/rule_based)."""

    model_config = _frozen()

    provider: str
    model: str
    version: str
    temperature: float | None = None
    seed: int | None = None


# ----------------------------------------------------------- canonical_private

class WinnerInfo(BaseModel):
    model_config = _frozen()

    seat: int
    winnings: int
    best_hand_desc: str


class SidePotSummary(BaseModel):
    model_config = _frozen()

    amount: int
    eligible_seats: tuple[int, ...]


class HandResultPrivate(BaseModel):
    model_config = _frozen()

    showdown: bool
    winners: tuple[WinnerInfo, ...]
    side_pots: tuple[SidePotSummary, ...]
    final_invested: dict[str, int]
    net_pnl: dict[str, int]


ActionType = Literal["fold", "check", "call", "bet", "raise_to", "all_in"]


class ActionRecordPrivate(BaseModel):
    """Per-action record inside canonical_private.jsonl's `actions` tuple."""

    model_config = _frozen()

    seat: int
    street: Literal["preflop", "flop", "turn", "river"]
    action_type: ActionType
    amount: int | None = None
    is_forced_blind: bool = False
    turn_index: int


class CanonicalPrivateHandRecord(BaseModel):
    """One line per hand in canonical_private.jsonl."""

    model_config = _frozen()

    hand_id: int
    started_at: str
    ended_at: str
    button_seat: int
    sb_seat: int
    bb_seat: int
    deck_seed: int
    starting_stacks: dict[str, int]
    hole_cards: dict[str, tuple[str, str]]
    community: tuple[str, ...] = Field(default_factory=tuple, max_length=5)
    actions: tuple[ActionRecordPrivate, ...]
    result: HandResultPrivate


# ----------------------------------------------------------- public_replay

class PublicHandStarted(BaseModel):
    model_config = _frozen()
    type: Literal["hand_started"] = "hand_started"
    hand_id: int
    button_seat: int
    blinds: dict[str, int]  # {"sb": 50, "bb": 100}


class PublicHoleDealt(BaseModel):
    model_config = _frozen()
    type: Literal["hole_dealt"] = "hole_dealt"
    hand_id: int


class PublicAction(BaseModel):
    model_config = _frozen()
    type: Literal["action"] = "action"
    hand_id: int
    seat: int
    street: Literal["preflop", "flop", "turn", "river"]
    action: dict[str, Any]  # {"type": "raise_to", "amount": 300}


class PublicFlop(BaseModel):
    model_config = _frozen()
    type: Literal["flop"] = "flop"
    hand_id: int
    community: tuple[str, str, str]


class PublicTurn(BaseModel):
    model_config = _frozen()
    type: Literal["turn"] = "turn"
    hand_id: int
    card: str


class PublicRiver(BaseModel):
    model_config = _frozen()
    type: Literal["river"] = "river"
    hand_id: int
    card: str


class PublicShowdown(BaseModel):
    model_config = _frozen()
    type: Literal["showdown"] = "showdown"
    hand_id: int
    # Only seats that reached showdown reveal holes; folded/mucked not present.
    revealed: dict[str, tuple[str, str]]


class PublicHandEnded(BaseModel):
    model_config = _frozen()
    type: Literal["hand_ended"] = "hand_ended"
    hand_id: int
    winnings: dict[str, int]  # per-seat chip delta this hand


def _public_event_discriminator(v: Any) -> str:  # noqa: ANN401
    if isinstance(v, dict):
        return str(v.get("type"))
    return getattr(v, "type", "")


PublicReplayEventInner = Annotated[
    (
        Annotated[PublicHandStarted, Tag("hand_started")]
        | Annotated[PublicHoleDealt, Tag("hole_dealt")]
        | Annotated[PublicAction, Tag("action")]
        | Annotated[PublicFlop, Tag("flop")]
        | Annotated[PublicTurn, Tag("turn")]
        | Annotated[PublicRiver, Tag("river")]
        | Annotated[PublicShowdown, Tag("showdown")]
        | Annotated[PublicHandEnded, Tag("hand_ended")]
    ),
    Discriminator(_public_event_discriminator),
]


class PublicReplayEvent(BaseModel):
    """Tagged union wrapper so callers can `PublicReplayEvent.model_validate(d).inner`."""

    model_config = _frozen()

    inner: PublicReplayEventInner = Field(discriminator="type")

    @classmethod
    def model_validate(cls, obj: Any) -> "PublicReplayEvent":  # noqa: ANN401
        if isinstance(obj, cls):
            return obj
        return cls(inner=obj)  # type: ignore[arg-type]

    def model_dump_json(self, **kwargs: Any) -> str:  # noqa: ANN401
        import json as _json
        return _json.dumps(self.inner.model_dump(), sort_keys=True)

    @property
    def type(self) -> str:
        return self.inner.type

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PublicReplayEvent):
            return NotImplemented
        return self.inner == other.inner

    def __hash__(self) -> int:
        return hash(self.inner)


# ----------------------------------------------------------- agent_view_snapshots

class AgentViewSnapshot(BaseModel):
    """One line per turn per agent in agent_view_snapshots.jsonl.

    Phase 2a: mock agents produce degenerate `iterations=()` + zero retry
    counters; schema is forward-compatible with Phase 3 ReAct.
    """

    model_config = _frozen()

    hand_id: int
    turn_id: str
    session_id: str
    seat: int
    street: Literal["preflop", "flop", "turn", "river"]
    timestamp: str

    view_at_turn_start: dict[str, Any]  # PlayerView.model_dump() raw
    iterations: tuple[dict[str, Any], ...] = ()

    final_action: dict[str, Any]
    is_forced_blind: bool = False
    total_utility_calls: int = 0

    api_retry_count: int = 0
    illegal_action_retry_count: int = 0
    no_tool_retry_count: int = 0
    tool_usage_error_count: int = 0

    default_action_fallback: bool = False
    api_error: str | None = None
    turn_timeout_exceeded: bool = False

    total_tokens: dict[str, int] = Field(default_factory=dict)
    wall_time_ms: int = 0
    agent: AgentDescriptor
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_storage_schemas.py -v
```
Expected: 8 passed. If `PublicReplayEvent.model_validate` dispatch on the discriminator misbehaves (Pydantic 2 discriminator syntax has moved across versions), simplify by wrapping `PublicReplayEvent` around a `RootModel[Union[...]]` instead — same API.

- [ ] **Step 5: Lint + type**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy
```
Expected: clean.

- [ ] **Step 6: Commit**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/storage/schemas.py tests/unit/test_storage_schemas.py && git commit -m "feat(storage): Pydantic schemas for canonical_private / public_replay / agent_view_snapshots"
```

---

## Task 4: Layer builders (`storage/layer_builders.py`)

**Files:**
- Create: `src/llm_poker_arena/storage/layer_builders.py`
- Create: `tests/unit/test_layer_builders.py`

Builders are pure functions from `(CanonicalState, turn context)` to layer records. Session wires them to writers. Each builder is deterministic and side-effect-free.

Per spec §7.3: showdown only reveals seats that reached showdown; folded-mucked hole cards stay private. That selection logic lives here.

- [ ] **Step 1: Write failing tests**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_layer_builders.py`:

```python
"""Tests for layer builders (canonical_private / public_replay / agent_view_snapshots)."""
from __future__ import annotations

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.projections import build_player_view
from llm_poker_arena.engine.transition import apply_action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.storage.layer_builders import (
    build_agent_view_snapshot,
    build_canonical_private_hand,
    build_public_action_event,
    build_public_hand_ended_event,
    build_public_hand_started_event,
    build_public_showdown_event,
    build_public_street_reveal_event,
)


def _cfg() -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def _state(button: int = 0) -> CanonicalState:
    cfg = _cfg()
    ctx = HandContext(
        hand_id=0, deck_seed=42_000, button_seat=button,
        initial_stacks=(10_000,) * 6,
    )
    return CanonicalState(cfg, ctx)


def test_public_hand_started_carries_button_and_blinds() -> None:
    cfg = _cfg()
    s = _state(button=0)
    e = build_public_hand_started_event(hand_id=0, state=s, sb=cfg.sb, bb=cfg.bb)
    assert e["type"] == "hand_started"
    assert e["hand_id"] == 0
    assert e["button_seat"] == 0
    assert e["blinds"] == {"sb": 50, "bb": 100}


def test_public_action_event_records_seat_street_action() -> None:
    e = build_public_action_event(
        hand_id=0, seat=3, street=Street.PREFLOP,
        action=Action(tool_name="raise_to", args={"amount": 300}),
    )
    assert e == {
        "type": "action", "hand_id": 0, "seat": 3,
        "street": "preflop",
        "action": {"type": "raise_to", "amount": 300},
    }


def test_public_street_reveal_flop_contains_3_cards() -> None:
    s = _state(button=0)
    # Drive to flop: UTG(3) HJ(4) CO(5) BTN(0) SB(1) call, BB(2) check.
    for actor in (3, 4, 5, 0, 1):
        r = apply_action(s, actor, Action(tool_name="call", args={}))
        assert r.is_valid
    r = apply_action(s, 2, Action(tool_name="check", args={}))
    assert r.is_valid
    s.deal_community(Street.FLOP)
    e = build_public_street_reveal_event(hand_id=0, state=s, street=Street.FLOP)
    assert e["type"] == "flop"
    assert len(e["community"]) == 3


def test_public_showdown_event_only_reveals_showdown_seats() -> None:
    # All-in preflop scenario would showdown all seats; here we just check
    # that the builder accepts a `showdown_seats` set and uses it to filter.
    s = _state(button=0)
    all_holes = s.hole_cards()  # dict[int, tuple[str, str]]
    revealed = build_public_showdown_event(
        hand_id=0, state=s, showdown_seats={1, 3, 5}
    )
    assert revealed["type"] == "showdown"
    # Only the 3 revealed seats appear in the map.
    assert set(revealed["revealed"].keys()) == {"1", "3", "5"}
    # Folded (2, 4, 0) seats NOT present.
    for absent in ("0", "2", "4"):
        assert absent not in revealed["revealed"]
    # And the revealed cards match.
    for seat in (1, 3, 5):
        assert tuple(revealed["revealed"][str(seat)]) == all_holes[seat]


def test_public_hand_ended_event_has_per_seat_winnings() -> None:
    e = build_public_hand_ended_event(
        hand_id=0, winnings={1: -50, 2: 150, 3: -100, 4: 0, 5: 0, 0: 0},
    )
    assert e["type"] == "hand_ended"
    assert e["winnings"] == {"1": -50, "2": 150, "3": -100, "4": 0, "5": 0, "0": 0}


def test_canonical_private_hand_has_full_hole_cards_and_actions() -> None:
    s = _state(button=0)
    # Collect actions as we drive to showdown.
    actions: list[dict] = []
    for turn_idx, actor in enumerate((3, 4, 5, 0, 1)):
        r = apply_action(s, actor, Action(tool_name="call", args={}))
        assert r.is_valid
        actions.append({"seat": actor, "street": "preflop",
                        "action_type": "call", "amount": None,
                        "is_forced_blind": False, "turn_index": turn_idx})
    r = apply_action(s, 2, Action(tool_name="check", args={}))
    assert r.is_valid
    actions.append({"seat": 2, "street": "preflop", "action_type": "check",
                    "amount": None, "is_forced_blind": False, "turn_index": 5})

    rec = build_canonical_private_hand(
        hand_id=0, state=s, started_at="2026-04-24T00:00:00Z",
        ended_at="2026-04-24T00:00:05Z",
        actions=tuple(actions),
    )
    assert rec["hand_id"] == 0
    assert rec["button_seat"] == 0
    # All 6 hole cards present regardless of showdown status.
    assert set(rec["hole_cards"].keys()) == {"0", "1", "2", "3", "4", "5"}
    assert len(rec["actions"]) == 6


def test_agent_view_snapshot_records_mock_agent_action() -> None:
    s = _state(button=0)
    actor = 3  # UTG on button=0
    view = build_player_view(s, actor, turn_seed=42)
    snap = build_agent_view_snapshot(
        hand_id=0, session_id="sess_test", seat=actor,
        street=Street.PREFLOP, timestamp="2026-04-24T00:00:00Z",
        view=view,
        action=Action(tool_name="fold", args={}),
        turn_index=0,
        agent_provider="random", agent_model="uniform", agent_version="phase1",
        default_action_fallback=False,
    )
    assert snap["hand_id"] == 0
    assert snap["seat"] == 3
    assert snap["turn_id"] == "0-preflop-0"
    assert snap["final_action"] == {"type": "fold"}
    # Mock agent has zero iterations.
    assert snap["iterations"] == []
    assert snap["agent"]["provider"] == "random"


def test_public_hand_started_serializes_symmetric_to_schema() -> None:
    from llm_poker_arena.storage.schemas import PublicReplayEvent
    cfg = _cfg()
    s = _state(button=3)
    e = build_public_hand_started_event(hand_id=9, state=s, sb=cfg.sb, bb=cfg.bb)
    # Must round-trip through the schema's discriminated union.
    wrapped = PublicReplayEvent.model_validate(e)
    assert wrapped.type == "hand_started"
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_layer_builders.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `layer_builders.py`**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/storage/layer_builders.py`:

```python
"""Pure builders from CanonicalState + turn metadata to layer dict records.

Builders return `dict[str, Any]` ready for JSONL writing. Downstream writer
serializes with `json.dumps(..., sort_keys=True)` (deterministic output).

The schemas in `storage.schemas` are authoritative on what fields exist; the
test `test_public_hand_started_serializes_symmetric_to_schema` enforces that
this builder's dict dialect matches the Pydantic union.
"""
from __future__ import annotations

from typing import Any

from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import PlayerView


def build_public_hand_started_event(
    *, hand_id: int, state: Any, sb: int, bb: int,  # noqa: ANN401 — CanonicalState
) -> dict[str, Any]:
    return {
        "type": "hand_started",
        "hand_id": hand_id,
        "button_seat": state.button_seat,
        "blinds": {"sb": sb, "bb": bb},
    }


def build_public_hole_dealt_event(*, hand_id: int) -> dict[str, Any]:
    return {"type": "hole_dealt", "hand_id": hand_id}


def build_public_action_event(
    *, hand_id: int, seat: int, street: Street, action: Action,
) -> dict[str, Any]:
    body: dict[str, Any] = {"type": action.tool_name}
    if action.tool_name in ("bet", "raise_to"):
        amt = action.args.get("amount") if isinstance(action.args, dict) else None
        if amt is not None:
            body["amount"] = int(amt)
    return {
        "type": "action", "hand_id": hand_id,
        "seat": seat, "street": street.value,
        "action": body,
    }


def build_public_street_reveal_event(
    *, hand_id: int, state: Any, street: Street,  # noqa: ANN401
) -> dict[str, Any]:
    community = state.community()  # list[str]
    if street == Street.FLOP:
        return {"type": "flop", "hand_id": hand_id, "community": list(community[:3])}
    if street == Street.TURN:
        return {"type": "turn", "hand_id": hand_id, "card": community[3]}
    if street == Street.RIVER:
        return {"type": "river", "hand_id": hand_id, "card": community[4]}
    raise ValueError(f"street {street!r} is not a board-reveal street")


def build_public_showdown_event(
    *, hand_id: int, state: Any, showdown_seats: set[int],  # noqa: ANN401
) -> dict[str, Any]:
    holes = state.hole_cards()  # dict[int, tuple[str, str]]
    revealed = {
        str(seat): list(holes[seat]) for seat in sorted(showdown_seats) if seat in holes
    }
    return {"type": "showdown", "hand_id": hand_id, "revealed": revealed}


def build_public_hand_ended_event(
    *, hand_id: int, winnings: dict[int, int],
) -> dict[str, Any]:
    return {
        "type": "hand_ended", "hand_id": hand_id,
        "winnings": {str(seat): int(amt) for seat, amt in winnings.items()},
    }


def build_canonical_private_hand(
    *, hand_id: int, state: Any,  # noqa: ANN401
    started_at: str, ended_at: str,
    actions: tuple[dict[str, Any], ...],
    winners: tuple[dict[str, Any], ...] = (),
    side_pots: tuple[dict[str, Any], ...] = (),
    final_invested: dict[int, int] | None = None,
    net_pnl: dict[int, int] | None = None,
    showdown: bool = False,
) -> dict[str, Any]:
    holes = state.hole_cards()  # dict[int, tuple[str, str]]
    stacks_initial = dict(enumerate(state._ctx.initial_stacks))  # noqa: SLF001
    return {
        "hand_id": hand_id,
        "started_at": started_at, "ended_at": ended_at,
        "button_seat": state.button_seat,
        "sb_seat": state.sb_seat, "bb_seat": state.bb_seat,
        "deck_seed": state._ctx.deck_seed,  # noqa: SLF001
        "starting_stacks": {str(s): int(v) for s, v in stacks_initial.items()},
        "hole_cards": {str(s): list(cards) for s, cards in holes.items()},
        "community": list(state.community()),
        "actions": list(actions),
        "result": {
            "showdown": showdown,
            "winners": list(winners),
            "side_pots": list(side_pots),
            "final_invested": {str(k): int(v) for k, v in (final_invested or {}).items()},
            "net_pnl": {str(k): int(v) for k, v in (net_pnl or {}).items()},
        },
    }


def build_agent_view_snapshot(
    *, hand_id: int, session_id: str, seat: int, street: Street,
    timestamp: str, view: PlayerView, action: Action, turn_index: int,
    agent_provider: str, agent_model: str, agent_version: str,
    default_action_fallback: bool,
) -> dict[str, Any]:
    final_action: dict[str, Any] = {"type": action.tool_name}
    if action.tool_name in ("bet", "raise_to"):
        amt = action.args.get("amount") if isinstance(action.args, dict) else None
        if amt is not None:
            final_action["amount"] = int(amt)
    return {
        "hand_id": hand_id,
        "turn_id": f"{hand_id}-{street.value}-{turn_index}",
        "session_id": session_id,
        "seat": seat,
        "street": street.value,
        "timestamp": timestamp,
        "view_at_turn_start": view.model_dump(mode="json"),
        "iterations": [],
        "final_action": final_action,
        "is_forced_blind": False,  # Phase-1 blinds are automation-posted; agent never chooses blind-post
        "total_utility_calls": 0,
        "api_retry_count": 0,
        "illegal_action_retry_count": 0,
        "no_tool_retry_count": 0,
        "tool_usage_error_count": 0,
        "default_action_fallback": default_action_fallback,
        "api_error": None,
        "turn_timeout_exceeded": False,
        "total_tokens": {},
        "wall_time_ms": 0,
        "agent": {
            "provider": agent_provider,
            "model": agent_model,
            "version": agent_version,
            "temperature": None,
            "seed": None,
        },
    }
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_layer_builders.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Lint + type**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy
```
Expected: clean.

- [ ] **Step 6: Commit**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/storage/layer_builders.py tests/unit/test_layer_builders.py && git commit -m "feat(storage): layer_builders build canonical_private/public/snapshot dicts from CanonicalState"
```

---

## Task 5: Access control readers (`storage/access_control.py`)

**Files:**
- Create: `src/llm_poker_arena/storage/access_control.py`
- Create: `tests/unit/test_access_control.py`

Per spec §7.5 / HR2-06: `PublicLogReader` requires only `public_replay.jsonl` to exist (so the reader works on a session that was published as a public dataset with private files stripped). `PrivateLogReader` requires all 3 files AND an access_token whitelist check.

Phase 2a uses a stub `require_private_access(token) → None` that accepts a single fixed sentinel for now; real token management is Phase 3+. The important thing in Phase 2a is that `PublicLogReader` and `PrivateLogReader` are structurally separate — `PublicLogReader` does NOT inherit from `PrivateLogReader` or require private files to exist.

- [ ] **Step 1: Write failing tests**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_access_control.py`:

```python
"""Tests for PublicLogReader and PrivateLogReader (trust boundary enforcement)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_poker_arena.storage.access_control import (
    PRIVATE_ACCESS_TOKEN,
    PrivateLogReader,
    PublicLogReader,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in records) + "\n")


def test_public_reader_works_without_private_files(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "public_replay.jsonl",
                 [{"type": "hand_started", "hand_id": 0},
                  {"type": "hand_ended", "hand_id": 0}])
    r = PublicLogReader(tmp_path)
    events = list(r.iter_events())
    assert len(events) == 2
    assert events[0]["type"] == "hand_started"


def test_public_reader_raises_when_public_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="public_replay.jsonl"):
        PublicLogReader(tmp_path)


def test_private_reader_requires_all_three_files(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "public_replay.jsonl", [{"type": "hand_started", "hand_id": 0}])
    with pytest.raises(FileNotFoundError, match="canonical_private.jsonl"):
        PrivateLogReader(tmp_path, access_token=PRIVATE_ACCESS_TOKEN)


def test_private_reader_rejects_wrong_token(tmp_path: Path) -> None:
    for name in ("canonical_private.jsonl", "public_replay.jsonl", "agent_view_snapshots.jsonl"):
        _write_jsonl(tmp_path / name, [{"ok": True}])
    with pytest.raises(PermissionError, match="access_token"):
        PrivateLogReader(tmp_path, access_token="wrong")


def test_private_reader_iterates_all_three_layers(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "canonical_private.jsonl", [{"hand_id": 0}])
    _write_jsonl(tmp_path / "public_replay.jsonl", [{"type": "hand_started", "hand_id": 0}])
    _write_jsonl(tmp_path / "agent_view_snapshots.jsonl", [{"hand_id": 0, "seat": 1}])
    r = PrivateLogReader(tmp_path, access_token=PRIVATE_ACCESS_TOKEN)
    assert list(r.iter_private_hands()) == [{"hand_id": 0}]
    assert list(r.iter_snapshots()) == [{"hand_id": 0, "seat": 1}]
    # public sub-reader still works
    pub = r.public_reader()
    assert list(pub.iter_events()) == [{"hand_id": 0, "type": "hand_started"}]
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_access_control.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `access_control.py`**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/storage/access_control.py`:

```python
"""Access-bounded JSONL readers (spec §7.5 / HR2-06).

PublicLogReader: only needs public_replay.jsonl. Can be used on a session
directory where private files were stripped before publishing.

PrivateLogReader: needs all three layers + a valid access_token. Does NOT
inherit from PublicLogReader — would otherwise force private files to exist
for public-only workflows.

Phase 2a stub: `require_private_access` accepts a single sentinel token.
Phase 3+ will wire real credential management.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

PRIVATE_ACCESS_TOKEN: str = "dev-local-private-v1"


def require_private_access(token: str) -> None:
    if token != PRIVATE_ACCESS_TOKEN:
        raise PermissionError(
            "PrivateLogReader requires a valid access_token "
            "(Phase 2a: use PRIVATE_ACCESS_TOKEN sentinel from storage.access_control)"
        )


class PublicLogReader:
    """Read public_replay.jsonl only. No private-file dependency."""

    def __init__(self, session_dir: Path) -> None:
        self._session_dir = Path(session_dir)
        self._public_path = self._session_dir / "public_replay.jsonl"
        if not self._public_path.exists():
            raise FileNotFoundError(
                f"Public replay not found at {self._public_path}. "
                f"PublicLogReader only needs public_replay.jsonl; private files are not required."
            )

    def iter_events(self) -> Iterator[dict[str, Any]]:
        with self._public_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)


class PrivateLogReader:
    """Read all three layers. Requires access_token whitelist check."""

    def __init__(self, session_dir: Path, access_token: str) -> None:
        require_private_access(access_token)
        self._session_dir = Path(session_dir)
        self._private_path = self._session_dir / "canonical_private.jsonl"
        self._public_path = self._session_dir / "public_replay.jsonl"
        self._snapshots_path = self._session_dir / "agent_view_snapshots.jsonl"
        for p in (self._private_path, self._public_path, self._snapshots_path):
            if not p.exists():
                raise FileNotFoundError(f"Required session file missing: {p}")

    def iter_private_hands(self) -> Iterator[dict[str, Any]]:
        with self._private_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def iter_snapshots(self) -> Iterator[dict[str, Any]]:
        with self._snapshots_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def public_reader(self) -> PublicLogReader:
        return PublicLogReader(self._session_dir)
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_access_control.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Lint + type**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy
```
Expected: clean.

- [ ] **Step 6: Commit**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/storage/access_control.py tests/unit/test_access_control.py && git commit -m "feat(storage): PublicLogReader + PrivateLogReader (§7.5 trust boundary enforcement)"
```

---

## Task 6: meta.json builder (`storage/meta.py`)

**Files:**
- Create: `src/llm_poker_arena/storage/meta.py`
- Create: `tests/unit/test_meta.py`

Per spec §7.6. Phase 2a populates only the fields that make sense for mock agents:
- `session_id`, `version=2`, `schema_version="v2.0"`
- `started_at`, `ended_at`, `total_hands_played`, `planned_hands`
- `git_commit` (from `subprocess git rev-parse HEAD`; best-effort)
- `prompt_profile_version="default-v2"`
- `seat_assignment` (provider labels keyed by seat number as string)
- `initial_button_seat`
- `chip_pnl` (cumulative per-seat over session)

Phase 3 fields (retry counters, token totals, provider_capabilities, estimated_cost_breakdown) stay as zeros / empty dicts. Forward-compatible schema.

- [ ] **Step 1: Write failing tests**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_meta.py`:

```python
"""Tests for SessionMeta builder."""
from __future__ import annotations

from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.storage.meta import build_session_meta


def _cfg() -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def test_meta_carries_session_timing_and_hand_counts() -> None:
    m = build_session_meta(
        session_id="session_test_001",
        config=_cfg(),
        started_at="2026-04-24T00:00:00Z",
        ended_at="2026-04-24T00:01:30Z",
        total_hands_played=60,
        seat_assignment={1: "Random_A", 2: "Random_B",
                         3: "RuleBased_A", 4: "RuleBased_B",
                         5: "Random_C", 0: "RuleBased_C"},
        initial_button_seat=0,
        chip_pnl={0: 150, 1: -200, 2: 75, 3: -50, 4: 100, 5: -75},
    )
    assert m["session_id"] == "session_test_001"
    assert m["version"] == 2
    assert m["schema_version"] == "v2.0"
    assert m["total_hands_played"] == 60
    assert m["planned_hands"] == 60
    assert m["initial_button_seat"] == 0
    assert m["chip_pnl"] == {"0": 150, "1": -200, "2": 75, "3": -50, "4": 100, "5": -75}


def test_meta_phase2a_retry_fields_are_zeros_or_empty() -> None:
    m = build_session_meta(
        session_id="sess_x", config=_cfg(),
        started_at="2026-04-24T00:00:00Z", ended_at="2026-04-24T00:00:01Z",
        total_hands_played=1, seat_assignment={}, initial_button_seat=0,
        chip_pnl={},
    )
    # Phase-3 fields degenerate in Phase 2a.
    assert m["censored_hands_count"] == 0
    assert m["censored_hand_ids"] == []
    assert m["total_tokens"] == {}
    assert m["retry_summary_per_seat"] == {}
    assert m["tool_usage_summary"] == {}
    assert m["estimated_cost_breakdown"] == {}


def test_meta_includes_git_commit_or_empty_string() -> None:
    m = build_session_meta(
        session_id="sess_x", config=_cfg(),
        started_at="t0", ended_at="t1",
        total_hands_played=1, seat_assignment={}, initial_button_seat=0,
        chip_pnl={},
    )
    # git_commit should be a string (possibly empty if git unavailable).
    assert isinstance(m["git_commit"], str)
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_meta.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `meta.py`**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/storage/meta.py`:

```python
"""Session-level meta.json builder (spec §7.6).

Phase 2a: populates session timing, chip P&L, git commit, seat assignment.
Phase 3 fills retry counters, provider_capabilities, estimated_cost_breakdown.
Schema is forward-compatible — Phase 2a omits nothing; unpopulated fields
degenerate to zeros / empty dicts for clean analyst consumption.
"""
from __future__ import annotations

import subprocess
from typing import Any

from llm_poker_arena.engine.config import SessionConfig


def _git_commit() -> str:
    """Best-effort HEAD SHA; returns '' if git unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=2,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def build_session_meta(
    *,
    session_id: str,
    config: SessionConfig,
    started_at: str,
    ended_at: str,
    total_hands_played: int,
    seat_assignment: dict[int, str],
    initial_button_seat: int,
    chip_pnl: dict[int, int],
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "version": 2,
        "schema_version": "v2.0",
        "started_at": started_at,
        "ended_at": ended_at,
        "total_hands_played": total_hands_played,
        "planned_hands": config.num_hands,
        "git_commit": _git_commit(),
        "prompt_profile_version": "default-v2",
        "provider_capabilities": {},
        "chip_pnl": {str(s): int(v) for s, v in chip_pnl.items()},
        "retry_summary_per_seat": {},
        "tool_usage_summary": {},
        "censored_hands_count": 0,
        "censored_hand_ids": [],
        "total_tokens": {},
        "estimated_cost_breakdown": {},
        "session_wall_time_sec": 0,  # Session can populate if desired
        "seat_assignment": {str(s): label for s, label in seat_assignment.items()},
        "initial_button_seat": initial_button_seat,
        "seat_permutation_id": "phase2a_default",
    }
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_meta.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Lint + type**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy
```
Expected: clean.

- [ ] **Step 6: Commit**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/storage/meta.py tests/unit/test_meta.py && git commit -m "feat(storage): SessionMeta builder (§7.6) with Phase-3-forward-compatible degenerate fields"
```

---

## Task 7: `RuleBasedAgent` (B2 baseline) (`agents/rule_based.py`)

**Files:**
- Create: `src/llm_poker_arena/agents/rule_based.py`
- Create: `tests/unit/test_rule_based_agent.py`

Per spec §15.2: "simple tight/aggressive bot". Spec doesn't define exact rules; this plan commits to a transparent, documented TAG ruleset. Phase 2a goal is NOT competitive play — it is a heterogeneous-agent lineup for the integration test + later baseline experiments.

**Phase 2a ruleset (simple TAG):**
- Preflop:
  - Premium (AA, KK, QQ, AKs, AKo): raise_to bb × 3 from any position; face a raise → re-raise (raise_to `current_bet_to_match` × 3)
  - Strong (JJ, TT, 99, AQ, AJs, KQs): raise_to bb × 3 from middle+late (button-relative idx ≥ 2 "CO"); call a raise; fold to a re-raise
  - Medium (88-22, AJo, KJs, QJs, JTs): call a single raise; fold to a re-raise; from button, raise
  - Else: fold unless BB with checkable BB option
- Postflop (flop/turn/river):
  - If `my_hole_cards` contains a pair with either card matching a board card (top/middle pair): bet `pot / 2` if `to_call == 0`, else `raise_to current_bet_to_match + pot / 2`; fold to a re-raise if `to_call > pot`
  - No pair but flush-draw or OESD (detected by rank/suit neighbor heuristics): check/call up to `pot / 4`
  - Otherwise: check if possible, else fold

This is a functional skill floor, not GTO. Testing focuses on correctness of rule dispatch, not quality of play.

- [ ] **Step 1: Write failing tests**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_rule_based_agent.py`:

```python
"""Tests for RuleBasedAgent (B2 baseline) — rule dispatch, not play quality."""
from __future__ import annotations

from llm_poker_arena.agents.rule_based import RuleBasedAgent
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


def _seats(position_of_actor: str = "UTG") -> tuple[SeatPublicInfo, ...]:
    return tuple(
        SeatPublicInfo(
            seat=i, label=f"P{i}",
            position_short=position_of_actor if i == 3 else "BB",
            position_full="pos",
            stack=10_000, invested_this_hand=0, invested_this_round=0, status="in_hand",
        )
        for i in range(6)
    )


def _view(
    *,
    hole: tuple[str, str],
    street: Street = Street.PREFLOP,
    current_bet_to_match: int = 100,
    my_invested_this_round: int = 0,
    legal_names: tuple[str, ...] = ("fold", "call", "raise_to"),
    raise_min_max: tuple[int, int] = (200, 10_000),
    community: tuple[str, ...] = (),
    position: str = "UTG",
) -> PlayerView:
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
        my_seat=3, my_hole_cards=hole, community=community,
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=my_invested_this_round,
        my_invested_this_round=my_invested_this_round,
        current_bet_to_match=current_bet_to_match,
        seats_public=_seats(position), opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=LegalActionSet(tools=tuple(tools)),
        opponent_stats={},
        hand_id=1, street=street, button_seat=0,
        turn_seed=1, immutable_session_params=_params(),
    )


def test_premium_preflop_raises_from_utg() -> None:
    agent = RuleBasedAgent()
    v = _view(hole=("As", "Ad"))  # AA
    act = agent.decide(v)
    assert act.tool_name == "raise_to"
    # bb × 3 = 300 target
    assert act.args["amount"] == 300


def test_junk_preflop_folds_from_utg() -> None:
    agent = RuleBasedAgent()
    v = _view(hole=("7c", "2d"))  # 72o junk
    act = agent.decide(v)
    assert act.tool_name == "fold"


def test_medium_hand_folds_to_3bet_from_utg() -> None:
    agent = RuleBasedAgent()
    v = _view(
        hole=("8h", "8d"),  # 88 medium
        current_bet_to_match=900,  # a 3bet-sized raise faced
        legal_names=("fold", "call", "raise_to"),
        raise_min_max=(1800, 10_000),
    )
    act = agent.decide(v)
    assert act.tool_name == "fold"


def test_medium_hand_calls_single_raise_from_utg() -> None:
    agent = RuleBasedAgent()
    v = _view(
        hole=("9h", "9d"),
        current_bet_to_match=300,  # standard 3bb raise
        legal_names=("fold", "call", "raise_to"),
        raise_min_max=(600, 10_000),
    )
    act = agent.decide(v)
    assert act.tool_name == "call"


def test_postflop_top_pair_bets_when_checkable() -> None:
    agent = RuleBasedAgent()
    v = _view(
        hole=("As", "Kd"),  # AKo
        street=Street.FLOP,
        current_bet_to_match=0,  # checked to me
        my_invested_this_round=0,
        legal_names=("check", "bet"),
        community=("Ah", "8c", "2d"),  # top pair aces
        raise_min_max=(100, 10_000),
    )
    act = agent.decide(v)
    assert act.tool_name == "bet"
    # bet pot/2 = 75
    assert act.args["amount"] == 75


def test_postflop_missed_folds_when_facing_bet() -> None:
    agent = RuleBasedAgent()
    v = _view(
        hole=("5s", "6d"),  # complete miss
        street=Street.FLOP,
        current_bet_to_match=200,
        my_invested_this_round=0,
        legal_names=("fold", "call", "raise_to"),
        community=("Ah", "Kc", "Qd"),
        raise_min_max=(400, 10_000),
    )
    act = agent.decide(v)
    assert act.tool_name == "fold"


def test_postflop_missed_checks_when_checkable() -> None:
    agent = RuleBasedAgent()
    v = _view(
        hole=("5s", "6d"),
        street=Street.FLOP,
        current_bet_to_match=0,
        my_invested_this_round=0,
        legal_names=("check", "bet"),
        community=("Ah", "Kc", "Qd"),
        raise_min_max=(100, 10_000),
    )
    act = agent.decide(v)
    assert act.tool_name == "check"


def test_returned_action_is_always_in_legal_set() -> None:
    agent = RuleBasedAgent()
    import random
    rng = random.Random(42)
    ranks = "23456789TJQKA"
    suits = "cdhs"
    for _ in range(200):
        c1 = rng.choice(ranks) + rng.choice(suits)
        c2 = rng.choice(ranks) + rng.choice(suits)
        if c1 == c2:
            continue
        v = _view(hole=(c1, c2))
        act = agent.decide(v)
        names = {t.name for t in v.legal_actions.tools}
        assert act.tool_name in names, (c1, c2, act.tool_name, names)


def test_provider_id_starts_with_rule_based() -> None:
    assert RuleBasedAgent().provider_id().startswith("rule_based")
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_rule_based_agent.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `rule_based.py`**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/agents/rule_based.py`:

```python
"""RuleBasedAgent: simple tight/aggressive skill-floor baseline (spec §15.2 B2).

Not intended to play well; intended to be a reproducible, transparent rule
dispatcher that an integration test can exercise alongside RandomAgent to
produce a heterogeneous lineup. No randomness — decisions are a pure function
of `view`.

Ruleset (documented inline below):
  Preflop:
    PREMIUM → raise_to bb*3; face a raise → re-raise to current_bet_to_match*3.
    STRONG  → raise_to bb*3 from mid/late position; call a single raise; fold to 3bet.
    MEDIUM  → call a single raise; fold to 3bet. From button, raise.
    Otherwise fold.
  Postflop (flop/turn/river):
    Top/middle pair → bet pot/2 if checkable, else raise_to current_bet_to_match + pot/2.
    No pair          → check if possible, else fold.
"""
from __future__ import annotations

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import LegalActionSet, PlayerView


_PREMIUM_PAIRS = {"AA", "KK", "QQ"}
_PREMIUM_BROADWAY = {"AKs", "AKo"}
_STRONG_PAIRS = {"JJ", "TT", "99"}
_STRONG_BROADWAY = {"AQs", "AQo", "AJs", "KQs"}
_MEDIUM_PAIRS = {f"{r}{r}" for r in ("2", "3", "4", "5", "6", "7", "8")}
_MEDIUM_BROADWAY = {"AJo", "KJs", "QJs", "JTs"}


def _hand_key(hole: tuple[str, str]) -> str:
    """Normalize 2 cards to ranked notation: 'AKs' (suited) / 'AKo' (offsuit) / 'AA' (pair)."""
    r1, s1 = hole[0][0], hole[0][1]
    r2, s2 = hole[1][0], hole[1][1]
    order = "23456789TJQKA"
    hi, lo = (r1, r2) if order.index(r1) >= order.index(r2) else (r2, r1)
    if hi == lo:
        return hi + lo
    suited = "s" if s1 == s2 else "o"
    return f"{hi}{lo}{suited}"


def _classify_preflop(hole: tuple[str, str]) -> str:
    k = _hand_key(hole)
    if k in _PREMIUM_PAIRS or k in _PREMIUM_BROADWAY:
        return "PREMIUM"
    if k in _STRONG_PAIRS or k in _STRONG_BROADWAY:
        return "STRONG"
    if k in _MEDIUM_PAIRS or k in _MEDIUM_BROADWAY:
        return "MEDIUM"
    return "JUNK"


def _has_top_or_middle_pair(hole: tuple[str, str], community: tuple[str, ...]) -> bool:
    if not community:
        return False
    board_ranks = [c[0] for c in community]
    hole_ranks = [c[0] for c in hole]
    return any(r in board_ranks for r in hole_ranks)


def _my_position_index(view: PlayerView) -> int:
    """Button-relative action order. 0=earliest (UTG), 5=latest (BB) for 6max."""
    return view.action_order_this_street.index(view.my_seat) if view.my_seat in view.action_order_this_street else 0


def _find_tool_amount_bounds(legal: LegalActionSet, name: str) -> tuple[int, int]:
    spec = next(t for t in legal.tools if t.name == name)
    bounds = spec.args["amount"]
    return int(bounds["min"]), int(bounds["max"])


def _clamp(amount: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, amount))


class RuleBasedAgent(Agent):
    """B2 baseline: tight/aggressive rule dispatcher. Deterministic in `view`."""

    def decide(self, view: PlayerView) -> Action:
        legal = {t.name for t in view.legal_actions.tools}
        bb = view.immutable_session_params.bb
        to_call = view.current_bet_to_match - view.my_invested_this_round
        is_preflop = view.street == Street.PREFLOP

        if is_preflop:
            return self._preflop(view, legal, bb, to_call)
        return self._postflop(view, legal, to_call)

    def provider_id(self) -> str:
        return "rule_based:tag_v1"

    # --------------------------------------------------- preflop

    def _preflop(
        self, view: PlayerView, legal: set[str], bb: int, to_call: int,
    ) -> Action:
        cls = _classify_preflop(view.my_hole_cards)
        position_idx = _my_position_index(view)
        facing_raise = to_call > bb  # more than BB to call → someone raised
        facing_3bet = to_call > bb * 3  # raise × 3 → 3-bet range

        if cls == "PREMIUM":
            if facing_3bet and "raise_to" in legal:
                mn, mx = _find_tool_amount_bounds(view.legal_actions, "raise_to")
                amt = _clamp(view.current_bet_to_match * 3, mn, mx)
                return Action(tool_name="raise_to", args={"amount": amt})
            if "raise_to" in legal:
                mn, mx = _find_tool_amount_bounds(view.legal_actions, "raise_to")
                return Action(tool_name="raise_to", args={"amount": _clamp(bb * 3, mn, mx)})
            if "call" in legal:
                return Action(tool_name="call", args={})
            return self._safe_check_or_fold(legal)

        if cls == "STRONG":
            if facing_3bet:
                return self._safe_fold_or_check(legal)
            if facing_raise and "call" in legal:
                return Action(tool_name="call", args={})
            if position_idx >= 2 and "raise_to" in legal:  # CO / BTN / SB / BB
                mn, mx = _find_tool_amount_bounds(view.legal_actions, "raise_to")
                return Action(tool_name="raise_to", args={"amount": _clamp(bb * 3, mn, mx)})
            if "call" in legal:
                return Action(tool_name="call", args={})
            return self._safe_check_or_fold(legal)

        if cls == "MEDIUM":
            if facing_3bet:
                return self._safe_fold_or_check(legal)
            if facing_raise and "call" in legal:
                return Action(tool_name="call", args={})
            if position_idx >= 3 and "raise_to" in legal:  # BTN / SB / BB
                mn, mx = _find_tool_amount_bounds(view.legal_actions, "raise_to")
                return Action(tool_name="raise_to", args={"amount": _clamp(bb * 3, mn, mx)})
            if "check" in legal:
                return Action(tool_name="check", args={})
            if "call" in legal and to_call <= bb:
                return Action(tool_name="call", args={})
            return self._safe_check_or_fold(legal)

        # JUNK
        if "check" in legal:
            return Action(tool_name="check", args={})
        if "fold" in legal:
            return Action(tool_name="fold", args={})
        if "call" in legal:
            return Action(tool_name="call", args={})
        # very last resort (all_in etc.): fold-equivalent
        return Action(tool_name="fold", args={})

    # --------------------------------------------------- postflop

    def _postflop(self, view: PlayerView, legal: set[str], to_call: int) -> Action:
        has_pair = _has_top_or_middle_pair(view.my_hole_cards, view.community)
        pot_half = max(1, view.pot // 2)

        if has_pair:
            if to_call <= 0 and "bet" in legal:
                mn, mx = _find_tool_amount_bounds(view.legal_actions, "bet")
                return Action(tool_name="bet", args={"amount": _clamp(pot_half, mn, mx)})
            if to_call > 0 and to_call > view.pot and "fold" in legal:
                return Action(tool_name="fold", args={})
            if "call" in legal:
                return Action(tool_name="call", args={})
            return self._safe_check_or_fold(legal)

        # No pair
        if to_call <= 0 and "check" in legal:
            return Action(tool_name="check", args={})
        return self._safe_fold_or_check(legal)

    # --------------------------------------------------- fallbacks

    @staticmethod
    def _safe_check_or_fold(legal: set[str]) -> Action:
        if "check" in legal:
            return Action(tool_name="check", args={})
        if "fold" in legal:
            return Action(tool_name="fold", args={})
        if "call" in legal:
            return Action(tool_name="call", args={})
        return Action(tool_name="fold", args={})

    @staticmethod
    def _safe_fold_or_check(legal: set[str]) -> Action:
        if "fold" in legal:
            return Action(tool_name="fold", args={})
        if "check" in legal:
            return Action(tool_name="check", args={})
        if "call" in legal:
            return Action(tool_name="call", args={})
        return Action(tool_name="fold", args={})
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_rule_based_agent.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Lint + type**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy
```
Expected: clean.

- [ ] **Step 6: Commit**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/agents/rule_based.py tests/unit/test_rule_based_agent.py && git commit -m "feat(agents): RuleBasedAgent (B2 TAG baseline per spec §15.2) with 9 rule-dispatch unit tests"
```

---

## Task 8: `Session` orchestrator (`session/session.py`)

**Files:**
- Create: `src/llm_poker_arena/session/session.py`
- Create: `tests/unit/test_session_orchestrator.py`

`Session.run()` iterates `config.num_hands` hands. Per hand:
1. Build `HandContext` with `button_seat = hand_id % num_players`, `initial_stacks = (config.starting_stack,) * num_players` (auto-rebuy), `deck_seed = derive_deck_seed(config.rng_seed, hand_id)`.
2. Construct `CanonicalState` — this auto-runs `audit_cards_invariant` (Phase-1 I-1).
3. Write `hand_started` + `hole_dealt` events to public_replay.
4. Drive the action loop (based on Phase-1 `run_single_hand` pattern): `while state.actor_index is not None` → agent.decide → apply_action → write public action + agent_view_snapshot → between-street advance. On street advance, write `flop`/`turn`/`river` event.
5. When hand ends: determine showdown seats (seats whose `state._state.statuses[i] is True`), write `showdown` (if applicable) + `hand_ended` events; run `audit_invariants(POST_SETTLEMENT)`.
6. Build + flush `canonical_private` record; flush all 3 writers for hand-end durability.
7. Accumulate `chip_pnl[seat] += state._state.payoffs[seat]`.

On exit: write `meta.json`, close all writers (drains buffers).

Phase 2a deliberately keeps this synchronous (matches Phase-1 Agent ABC). Phase 3 re-does it async.

- [ ] **Step 1: Write failing test (3-hand smoke)**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_session_orchestrator.py`:

```python
"""Tests for Session orchestrator (3-hand smoke + artifact structural checks)."""
from __future__ import annotations

import json
from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _cfg() -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6,  # smoke: 1 button rotation
        max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def test_session_writes_three_jsonl_files(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RandomAgent(), RuleBasedAgent()] * 3
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_test")
    sess.run()
    # All 3 layer files exist and are non-empty.
    for fname in ("canonical_private.jsonl", "public_replay.jsonl",
                  "agent_view_snapshots.jsonl", "meta.json"):
        p = tmp_path / fname
        assert p.exists(), fname
        assert p.stat().st_size > 0, fname


def test_session_canonical_private_has_num_hands_lines(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_c")
    sess.run()
    lines = (tmp_path / "canonical_private.jsonl").read_text().strip().splitlines()
    assert len(lines) == cfg.num_hands


def test_session_public_replay_first_event_is_hand_started(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_p")
    sess.run()
    lines = (tmp_path / "public_replay.jsonl").read_text().strip().splitlines()
    first = json.loads(lines[0])
    assert first["type"] == "hand_started"


def test_session_agent_view_snapshot_is_at_least_one_per_hand(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_a")
    sess.run()
    lines = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    # Each hand has ≥ 1 action turn (minimum: 1 fold settles pre-action? No —
    # with blinds posted, BB can check at minimum, so ≥ 1 turn always).
    assert len(lines) >= cfg.num_hands


def test_session_meta_json_carries_total_hands_and_chip_pnl(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_m")
    sess.run()
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["session_id"] == "sess_m"
    assert meta["total_hands_played"] == cfg.num_hands
    # chip_pnl sums to 0 (zero-sum game)
    assert sum(meta["chip_pnl"].values()) == 0


def test_session_rejects_agents_list_length_mismatch(tmp_path: Path) -> None:
    import pytest
    cfg = _cfg()
    with pytest.raises(ValueError, match="agents"):
        Session(config=cfg, agents=[RandomAgent()] * 3,  # only 3 agents for 6 seats
                output_dir=tmp_path, session_id="sess_bad")
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_session_orchestrator.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `session.py`**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/session/session.py`:

```python
"""Session orchestrator: multi-hand loop with audit + 3-layer event emission.

Replaces Phase-1 `engine._internal.rebuy.run_single_hand` for end-to-end runs.
Phase 2a: synchronous; each agent's `decide(view)` is called inline. Every
hand commits a full canonical_private record, a stream of public_replay
events, and per-turn agent_view_snapshots via BatchedJsonlWriter (H-10).

Phase 3 responsibilities not in Phase 2a:
  - Async ReAct loop with 4 retry counters
  - `mark_hand_censored` for api_error / total_turn_timeout
  - Seat permutation (this Phase uses simple button_seat = hand_id % n)
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.engine._internal.audit import HandPhase, audit_invariants
from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine._internal.rebuy import derive_deck_seed
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.legal_actions import Action, default_safe_action
from llm_poker_arena.engine.projections import build_player_view
from llm_poker_arena.engine.transition import apply_action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.storage.jsonl_writer import BatchedJsonlWriter
from llm_poker_arena.storage.layer_builders import (
    build_agent_view_snapshot,
    build_canonical_private_hand,
    build_public_action_event,
    build_public_hand_ended_event,
    build_public_hand_started_event,
    build_public_hole_dealt_event,
    build_public_showdown_event,
    build_public_street_reveal_event,
)
from llm_poker_arena.storage.meta import build_session_meta


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _derive_turn_seed(deck_seed: int, actor: int, turn_counter: int) -> int:
    payload = f"{deck_seed}:{actor}:{turn_counter}".encode()
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big") & (
        (1 << 63) - 1
    )


class Session:
    """Phase 2a synchronous session driver."""

    def __init__(
        self, *, config: SessionConfig, agents: Sequence[Agent],
        output_dir: Path, session_id: str,
    ) -> None:
        if len(agents) != config.num_players:
            raise ValueError(
                f"agents length ({len(agents)}) != config.num_players ({config.num_players})"
            )
        self._config = config
        self._agents = list(agents)
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._session_id = session_id

        self._private_writer = BatchedJsonlWriter(self._output_dir / "canonical_private.jsonl")
        self._public_writer = BatchedJsonlWriter(self._output_dir / "public_replay.jsonl")
        self._snapshot_writer = BatchedJsonlWriter(self._output_dir / "agent_view_snapshots.jsonl")

        self._chip_pnl: dict[int, int] = {i: 0 for i in range(config.num_players)}
        self._total_hands_played = 0

    def run(self) -> None:
        started_at = _now_iso()
        initial_button_seat = 0
        try:
            for hand_id in range(self._config.num_hands):
                self._run_one_hand(hand_id)
                self._total_hands_played += 1
        finally:
            ended_at = _now_iso()
            meta = build_session_meta(
                session_id=self._session_id, config=self._config,
                started_at=started_at, ended_at=ended_at,
                total_hands_played=self._total_hands_played,
                seat_assignment={i: self._agents[i].provider_id()
                                 for i in range(self._config.num_players)},
                initial_button_seat=initial_button_seat,
                chip_pnl=self._chip_pnl,
            )
            (self._output_dir / "meta.json").write_text(
                __import__("json").dumps(meta, sort_keys=True, indent=2)
            )
            for w in (self._private_writer, self._public_writer, self._snapshot_writer):
                w.close()

    # ------------------------------------------------- per-hand

    def _run_one_hand(self, hand_id: int) -> None:
        cfg = self._config
        ctx = HandContext(
            hand_id=hand_id,
            deck_seed=derive_deck_seed(cfg.rng_seed, hand_id),
            button_seat=hand_id % cfg.num_players,
            initial_stacks=(cfg.starting_stack,) * cfg.num_players,
        )
        state = CanonicalState(cfg, ctx)
        audit_invariants(state, cfg, HandPhase.PRE_SETTLEMENT)

        started_at = _now_iso()
        self._public_writer.write(
            build_public_hand_started_event(hand_id=hand_id, state=state, sb=cfg.sb, bb=cfg.bb)
        )
        self._public_writer.write(build_public_hole_dealt_event(hand_id=hand_id))

        actions: list[dict[str, Any]] = []
        turn_counter = 0
        prev_board_len = 0

        while state._state.actor_index is not None:  # noqa: SLF001
            actor = int(state._state.actor_index)  # noqa: SLF001
            turn_seed = _derive_turn_seed(ctx.deck_seed, actor, turn_counter)
            view = build_player_view(state, actor, turn_seed=turn_seed)
            street = view.street
            chosen = self._agents[actor].decide(view)
            fallback = False
            result = apply_action(state, actor, chosen)
            if not result.is_valid:
                fallback = True
                chosen = default_safe_action(view)
                result2 = apply_action(state, actor, chosen)
                if not result2.is_valid:
                    raise RuntimeError(
                        f"default_safe_action also rejected by pokerkit at seat {actor}: "
                        f"reason={result2.reason}"
                    )

            self._public_writer.write(
                build_public_action_event(
                    hand_id=hand_id, seat=actor, street=street, action=chosen,
                )
            )
            self._snapshot_writer.write(
                build_agent_view_snapshot(
                    hand_id=hand_id, session_id=self._session_id, seat=actor,
                    street=street, timestamp=_now_iso(), view=view,
                    action=chosen, turn_index=turn_counter,
                    agent_provider=self._agents[actor].provider_id().split(":", 1)[0],
                    agent_model=self._agents[actor].provider_id().split(":", 1)[-1],
                    agent_version="phase2a",
                    default_action_fallback=fallback,
                )
            )
            actions.append({
                "seat": actor, "street": street.value,
                "action_type": chosen.tool_name,
                "amount": chosen.args.get("amount")
                          if isinstance(chosen.args, dict) else None,
                "is_forced_blind": False, "turn_index": turn_counter,
            })
            turn_counter += 1

            prev_board_len = self._maybe_advance_between_streets(
                state, hand_id, prev_board_len,
            )

        # Hand is over. Emit showdown (if anyone saw it) + hand_ended.
        statuses = list(state._state.statuses)  # noqa: SLF001
        showdown_seats = {i for i, alive in enumerate(statuses) if bool(alive)}
        showdown = len(showdown_seats) > 1
        if showdown:
            self._public_writer.write(
                build_public_showdown_event(
                    hand_id=hand_id, state=state, showdown_seats=showdown_seats,
                )
            )

        payoffs = list(state._state.payoffs)  # noqa: SLF001
        winnings = {i: int(payoffs[i]) for i in range(cfg.num_players)}
        self._public_writer.write(
            build_public_hand_ended_event(hand_id=hand_id, winnings=winnings)
        )

        audit_invariants(state, cfg, HandPhase.POST_SETTLEMENT)

        # Canonical private hand record.
        ended_at = _now_iso()
        final_invested = {i: cfg.starting_stack - int(state._state.stacks[i]) - max(0, int(payoffs[i]))  # noqa: SLF001
                          for i in range(cfg.num_players)}
        self._private_writer.write(
            build_canonical_private_hand(
                hand_id=hand_id, state=state,
                started_at=started_at, ended_at=ended_at,
                actions=tuple(actions),
                winners=tuple({"seat": i, "winnings": int(payoffs[i]), "best_hand_desc": ""}
                              for i in range(cfg.num_players) if int(payoffs[i]) > 0),
                side_pots=(),
                final_invested=final_invested,
                net_pnl=winnings,
                showdown=showdown,
            )
        )

        # Hand-end durability checkpoint (H-10).
        for w in (self._public_writer, self._snapshot_writer, self._private_writer):
            w.flush()

        # Session-level chip_pnl accumulator (spec meta.chip_pnl).
        for seat, delta in winnings.items():
            self._chip_pnl[seat] += delta

    # ------------------------------------------------- between-street advance

    def _maybe_advance_between_streets(
        self, state: CanonicalState, hand_id: int, prev_board_len: int,
    ) -> int:
        """Emit street_reveal events if burn+deal happened since last check.

        Mirrors rebuy.py::_maybe_advance_between_streets logic but returns the
        new board length so the caller tracks whether a reveal has been
        emitted for this hand.
        """
        raw = state._state  # noqa: SLF001
        for _ in range(32):
            if raw.actor_index is not None:
                break
            if raw.can_show_or_muck_hole_cards():
                raw.show_or_muck_hole_cards()
                continue
            if raw.can_burn_card():
                board_len = sum(len(slot) for slot in (raw.board_cards or []))
                # Decide next street based on current board length.
                if board_len == 0:
                    state.deal_community(Street.FLOP)
                    self._public_writer.write(
                        build_public_street_reveal_event(
                            hand_id=hand_id, state=state, street=Street.FLOP,
                        )
                    )
                elif board_len == 3:
                    state.deal_community(Street.TURN)
                    self._public_writer.write(
                        build_public_street_reveal_event(
                            hand_id=hand_id, state=state, street=Street.TURN,
                        )
                    )
                elif board_len == 4:
                    state.deal_community(Street.RIVER)
                    self._public_writer.write(
                        build_public_street_reveal_event(
                            hand_id=hand_id, state=state, street=Street.RIVER,
                        )
                    )
                else:
                    raise RuntimeError(
                        f"unexpected board length {board_len} requesting burn"
                    )
                continue
            break
        return sum(len(slot) for slot in (raw.board_cards or []))
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_session_orchestrator.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Full suite + lint + type**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest && ruff check . && mypy
```
Expected: all green.

- [ ] **Step 6: Commit**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/session/session.py tests/unit/test_session_orchestrator.py && git commit -m "feat(session): Session orchestrator (multi-hand loop + 3-layer writers + audit + meta.json)"
```

---

## Task 9: Property test — `public_replay` zero-leak (`tests/property/test_public_replay_no_leak.py`)

**Files:**
- Create: `tests/property/test_public_replay_no_leak.py`

Spec invariant P2 (§2.2): `public_replay.jsonl` must NEVER contain hole cards of a seat that did not reach showdown (folded / mucked). Hypothesis-drive random sessions and compare per-hand.

- [ ] **Step 1: Write failing test**

Create `/Users/zcheng256/llm-poker-arena/tests/property/test_public_replay_no_leak.py`:

```python
"""Property P2: public_replay.jsonl never leaks hole cards of non-showdown seats."""
from __future__ import annotations

import json
from pathlib import Path

from hypothesis import given, settings, strategies as st

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


@given(
    rng_seed=st.integers(min_value=0, max_value=5_000),
    num_hands=st.sampled_from([6, 12, 18]),
)
@settings(max_examples=30, deadline=None)
def test_public_replay_has_no_non_showdown_hole_leak(
    rng_seed: int, num_hands: int, tmp_path_factory: object,
) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=rng_seed,
    )
    # tmp_path_factory is pytest's session-scoped factory; mktemp gives a
    # fresh dir per hypothesis example.
    out_dir = tmp_path_factory.mktemp("sess_leakcheck")  # type: ignore[attr-defined]
    agents = [RandomAgent() for _ in range(6)]
    Session(config=cfg, agents=agents, output_dir=Path(out_dir),
            session_id="leaktest").run()

    # For each hand in canonical_private, compare its hole_cards against the
    # cards revealed (or absent) in public_replay.
    private = [json.loads(line) for line in
               (Path(out_dir) / "canonical_private.jsonl").read_text().splitlines() if line.strip()]
    public = [json.loads(line) for line in
              (Path(out_dir) / "public_replay.jsonl").read_text().splitlines() if line.strip()]
    public_by_hand: dict[int, list[dict]] = {}
    for ev in public:
        public_by_hand.setdefault(ev["hand_id"], []).append(ev)

    for hand in private:
        hid = hand["hand_id"]
        holes = hand["hole_cards"]  # dict[str, list[str, str]]
        # Find showdown event (may be absent if hand ended by fold-to-one).
        showdown_evs = [e for e in public_by_hand[hid] if e["type"] == "showdown"]
        revealed_seats: set[str] = set()
        if showdown_evs:
            revealed_seats = set(showdown_evs[0]["revealed"].keys())

        public_blob = "\n".join(
            json.dumps(e, sort_keys=True) for e in public_by_hand[hid]
        )
        for seat_str, cards in holes.items():
            if seat_str in revealed_seats:
                continue  # showdown reveal allowed
            for card in cards:
                assert card not in public_blob, (
                    f"seat {seat_str} (non-showdown) card {card!r} leaked "
                    f"into public_replay for hand {hid}"
                )
```

- [ ] **Step 2: Run, expect pass (writer is already correct; this is a regression guard)**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/property/test_public_replay_no_leak.py -v
```
Expected: 1 passed (hypothesis runs 30 examples). If it fails, the writer/builder code has a real leak — diagnose immediately, do NOT patch the test.

- [ ] **Step 3: Commit**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && git add tests/property/test_public_replay_no_leak.py && git commit -m "test(property): public_replay P2 invariant — no non-showdown hole-card leak"
```

---

## Task 10: Durability test — crash ≤ BATCH_SIZE (`tests/unit/test_batch_flush_durability.py`)

**Files:**
- Create: `tests/unit/test_batch_flush_durability.py`

Spec §8.1: crash at arbitrary point loses ≤ `BATCH_SIZE` entries. Test by fork-and-kill: parent forks a child that writes N records then SIGKILLs itself; parent verifies the resulting file contains `N - k` lines for `k ≤ BATCH_SIZE`.

- [ ] **Step 1: Write failing test**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_batch_flush_durability.py`:

```python
"""Durability: BatchedJsonlWriter loses ≤ BATCH_SIZE entries on SIGKILL."""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from llm_poker_arena.storage.jsonl_writer import BatchedJsonlWriter


@pytest.mark.skipif(sys.platform == "win32", reason="fork-based test; Unix only")
def test_sigkill_loses_at_most_batch_size_entries(tmp_path: Path) -> None:
    out = tmp_path / "durability.jsonl"
    total = 50  # write 50 entries then SIGKILL self
    pid = os.fork()
    if pid == 0:
        # Child
        w = BatchedJsonlWriter(out)
        for i in range(total):
            w.write({"i": i})
            # Don't flush — rely on BATCH_SIZE + FLUSH_INTERVAL_MS only.
            if i == total - 1:
                # Kill before close() can drain.
                os.kill(os.getpid(), signal.SIGKILL)
        os._exit(0)
    else:
        # Parent
        (_, status) = os.waitpid(pid, 0)
        assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL

    # Verify file contents.
    time.sleep(0.05)  # fsyncs settle
    lines = out.read_text().splitlines() if out.exists() else []
    written = len(lines)
    lost = total - written
    assert 0 <= lost <= BatchedJsonlWriter.BATCH_SIZE, (
        f"expected ≤ {BatchedJsonlWriter.BATCH_SIZE} lost, got lost={lost}, "
        f"written={written}"
    )
    # Any written line must be valid JSON.
    for line in lines:
        json.loads(line)


def test_sigterm_drains_buffer(tmp_path: Path) -> None:
    """SIGTERM (not SIGKILL) must drain the buffer — writer has a handler."""
    out = tmp_path / "sigterm.jsonl"
    pid = os.fork()
    if pid == 0:
        # Child
        w = BatchedJsonlWriter(out)
        for i in range(3):
            w.write({"i": i})
        # 3 entries < BATCH_SIZE, so none are flushed yet. Signal ourselves.
        os.kill(os.getpid(), signal.SIGTERM)
        # If the handler ran, the buffer is drained; let process terminate.
        os._exit(0)
    else:
        os.waitpid(pid, 0)

    lines = out.read_text().splitlines() if out.exists() else []
    # All 3 buffered entries should be present (SIGTERM drains).
    assert len(lines) == 3
```

- [ ] **Step 2: Run**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_batch_flush_durability.py -v
```
Expected: 2 passed on macOS / Linux. Windows is skipped.

If the SIGTERM test fails with 0 lines written, the signal handler in `BatchedJsonlWriter.__init__` is not running before `_exit`. Root cause diagnosis is the fix — do NOT patch the test.

- [ ] **Step 3: Commit**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && git add tests/unit/test_batch_flush_durability.py && git commit -m "test(storage): BatchedJsonlWriter durability under SIGKILL and SIGTERM"
```

---

## Task 11: 1000-hand MVP 6 integration (`tests/unit/test_mvp6_integration.py`)

**Files:**
- Create: `tests/unit/test_mvp6_integration.py`

Spec MVP 6 exit criterion: "mock decisions 下跑 1,000 手；public_replay 无 private 信息泄漏；crash at arbitrary point 最多丢最后 10 条". This test satisfies the 1000-hand + no-leak component; Task 10 already covers crash durability.

- [ ] **Step 1: Write test**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_mvp6_integration.py`:

```python
"""MVP 6 exit criterion: 1,000 mock-agent hands → 3-layer JSONL + meta + zero leak."""
from __future__ import annotations

import json
from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session
from llm_poker_arena.storage.access_control import (
    PRIVATE_ACCESS_TOKEN,
    PrivateLogReader,
    PublicLogReader,
)


def test_mvp6_thousand_hands_heterogeneous_lineup(tmp_path: Path) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=1_002,  # multiple of 6 closest to 1000
        max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=2026,
    )
    # Heterogeneous lineup: 3 Random + 3 RuleBased.
    agents = [RandomAgent(), RuleBasedAgent()] * 3
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="mvp6")
    sess.run()

    # Three layer files + meta exist.
    for fname in ("canonical_private.jsonl", "public_replay.jsonl",
                  "agent_view_snapshots.jsonl", "meta.json"):
        assert (tmp_path / fname).exists()

    # 1002 hand records.
    private_lines = (tmp_path / "canonical_private.jsonl").read_text().splitlines()
    assert len(private_lines) == 1_002

    # Round-trip readers work.
    pub = PublicLogReader(tmp_path)
    pub_events = list(pub.iter_events())
    assert len(pub_events) > 1_002  # at minimum 1 event per hand + hand_started/ended

    priv = PrivateLogReader(tmp_path, access_token=PRIVATE_ACCESS_TOKEN)
    hands = list(priv.iter_private_hands())
    assert len(hands) == 1_002
    snapshots = list(priv.iter_snapshots())
    assert len(snapshots) >= 1_002

    # Chip conservation sanity (zero-sum across all hands).
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0
```

- [ ] **Step 2: Run**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && time pytest tests/unit/test_mvp6_integration.py -v
```
Expected: 1 passed. At ~300 hands/sec from T17 baseline, 1002 hands ≈ 3-5 sec wall clock; add some writer overhead, expect under 30 sec total.

If runtime blows up to minutes, the writer's batch-flush discipline is leaking (buffer growing unbounded or flushing per-write). Diagnose in the writer, not the test.

- [ ] **Step 3: Full suite**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest && ruff check . && mypy
```
Expected: all Phase 1 tests (112) + Phase 2a additions (≈ 6+8+5+3+9+6+1+2+1 = 41) = 153 passing.

- [ ] **Step 4: Commit**

Run:
```bash
cd /Users/zcheng256/llm-poker-arena && git add tests/unit/test_mvp6_integration.py && git commit -m "test: MVP 6 exit criterion — 1000-hand heterogeneous lineup with 3-layer JSONL + readers"
```

---

## Self-Review

After completing Tasks 1-11:

**Spec coverage** (re-skim each relevant spec section):
- §7.1 directory structure → Task 8 (Session lays out session_dir with all 3 files + meta.json). Missing: `prompts/` and `crash.json` dirs; both are Phase 3+ (prompts for LLM providers, crash.json for uncaught exception snapshot). Acceptable gap.
- §7.2 canonical_private schema → Task 3 `CanonicalPrivateHandRecord`. ✓
- §7.3 public_replay events → Task 3 `PublicReplayEvent` union + Task 4 builders. ✓
- §7.4 agent_view_snapshots → Task 3 + Task 4. Phase 2a degenerate (iterations empty) — forward-compat ✓
- §7.5 access control → Task 5. ✓
- §7.6 meta.json → Task 6. Phase 2a degenerate fields acceptable ✓
- §7.7 PHH exporter → **deferred to Phase 2b/Phase 5**. Plan explicitly documents this decision. ✓
- §8.1 BatchedJsonlWriter → Task 2. ✓
- §8.2 / §8.3 DuckDB + VPIP SQL → Phase 2b. Out of Phase 2a scope.
- §15.2 B2 RuleBased → Task 7. ✓
- §2.2 P2 public no-leak → Task 9. ✓
- MVP 6 exit criterion → Task 11 (1000 hands) + Task 10 (durability). ✓

**Placeholder scan**: search the document for "TODO", "TBD", "implement later". None present. The only "deferred" references point to Phase 2b / Phase 3 with explicit rationale.

**Type consistency check**:
- `CanonicalState._state`, `CanonicalState._config`, `CanonicalState._ctx`, `CanonicalState.hole_cards()` → used consistently in Tasks 4, 8. Phase-1 shapes respected.
- `Action(tool_name: str, args: dict)` → consistent everywhere; `args["amount"]` is `int` when present.
- `Session.__init__(config, agents, output_dir, session_id)` → kwargs-only, matches Task 8 test signatures.
- Writer method surface: `write(dict)` / `flush()` / `close()`. Session uses exactly these in Task 8.
- Agent `provider_id()` returns `"random:uniform"` or `"rule_based:tag_v1"`. Session splits on `:` at most once; builders use the split parts for snapshot.

**Pre-existing Phase-1 contracts respected**:
- `SessionConfig.num_hands % num_players == 0` — MVP 6 integration uses 1002 (÷ 6 = 167). ✓
- `HandContext.initial_stacks = (starting_stack,) * num_players` — Session enforces this in `_run_one_hand`. ✓ (auto-rebuy per spec §3.5)
- `apply_action(state, actor, action)` — no `config` kwarg. ✓
- `state.actor_index is not None` — used as loop predicate. ✓
- Tuples for frozen-Pydantic sequence fields — enforced via schemas.py. ✓
- Commit messages — 11 plan-verbatim messages. No `Co-Authored-By`.

**Open risk**: Task 8's `Session._maybe_advance_between_streets` duplicates logic from `engine._internal.rebuy._maybe_advance_between_streets`. If pokerkit 0.7.3 ever diverges, two sites need updating. Accepted for Phase 2a (Phase 3's orchestrator will subsume both). Noted in memory post-completion.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-24-llm-poker-arena-phase-2a.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. Best given Phase 1 showed pokerkit-version quirks surface one-by-one (Tasks 2 / 7 / 8 carry the most of that risk).

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

**Which approach?**

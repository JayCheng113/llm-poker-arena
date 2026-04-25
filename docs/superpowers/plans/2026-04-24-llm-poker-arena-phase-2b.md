# llm-poker-arena Phase 2b (MVP 7 DuckDB Analysis) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a DuckDB-backed analysis layer over the Phase-2a JSONL stack so B1-Random + B2-RuleBased baselines can run to completion, produce per-seat VPIP/PFR/action-distribution metrics, and emit chart outputs — satisfying spec v2.1.1 §16.1 MVP 7 exit criterion.

**Architecture:** Add `storage/duckdb_query.py` (safe path whitelist + `open_session` connection factory per spec §8.2) and a new `analysis/` subpackage that (a) exposes compiled SQL for VPIP/PFR/action_distribution as plain string constants, (b) drives baseline sessions via helpers that wrap Phase-2a `Session`, and (c) renders matplotlib charts into `session_dir/plots/`. No changes to Phase 2a files — the analysis layer reads the existing three JSONL files strictly via public readers + DuckDB views.

**Tech Stack:** Python 3.11+, DuckDB 1.x (new), matplotlib 3.8+ (new), plus existing pokerkit 0.7.3 / Pydantic 2 / pytest / hypothesis / ruff / mypy --strict. No pyyaml yet (config.yaml rename still deferred).

---

## Pre-flight: Context, Phase 2a Realities, Risks

Skip nothing in this section — Phase 1 and Phase 2a both had plan code that didn't survive contact with as-built reality. The 13 risk notes below are lessons from Codex audits on prior phases.

### What Phase 2a actually shipped (the JSONL schemas you'll query)

- **`canonical_private.jsonl`** — one line per hand. Each line is `CanonicalPrivateHandRecord.model_dump(mode="json")`:
  - `hand_id`, `started_at`, `ended_at`, `button_seat`, `sb_seat`, `bb_seat`, `deck_seed`
  - `starting_stacks: dict[str, int]` — keys are `"0".."5"` (stringified seat indices)
  - `hole_cards: dict[str, tuple[str, str]]` — full hands (all 6 seats)
  - `community: tuple[str, ...]` max length 5
  - `actions: tuple[ActionRecordPrivate, ...]` — agent actions ONLY (blind posts excluded; see Risk 7)
  - `result: {showdown, winners, side_pots, final_invested, net_pnl}`
  - **`result.final_invested` is always `{}`** in Phase 2a (deferred)
- **`public_replay.jsonl`** — one line per hand. Each line is `PublicHandRecord.model_dump(mode="json")`:
  - `{ "hand_id": int, "street_events": [event, event, ...] }`
  - Event types: `hand_started`, `hole_dealt`, `action`, `flop`, `turn`, `river`, `showdown`, `hand_ended`
  - Use for replay/UI; NOT queried in Phase 2b analysis (metrics come from agent_view_snapshots)
- **`agent_view_snapshots.jsonl`** — one line per agent turn (≈30 rows/hand × num_hands). Each line is `AgentViewSnapshot.model_dump(mode="json")`:
  - `hand_id: int`, `turn_id: str`, `session_id: str`, `seat: int`
  - `street: "preflop" | "flop" | "turn" | "river"`
  - `timestamp: str`
  - `view_at_turn_start: dict` — full PlayerView dump (don't parse; opaque to analysis)
  - `iterations: []` (empty in Phase 2a mock agents)
  - `final_action: {"type": str, "amount"?: int}` — the key VPIP/PFR field; `amount` present only for `bet`/`raise_to` (sometimes `all_in`)
  - `is_forced_blind: false` ALWAYS (mock agents don't post blinds; engine automation handles it)
  - `default_action_fallback`, `api_error=null`, `turn_timeout_exceeded=false`, `api_retry_count=0`, etc.
  - `agent: {provider, model, version, temperature=null, seed=null}`
- **`meta.json`** — session-level aggregate; has `session_id`, `chip_pnl: dict[str, int]`, `total_hands_played`, `session_wall_time_sec`, `seat_assignment`, etc. Read for chart titles + P&L histograms.
- **`config.json`** — the SessionConfig snapshot (`rng_seed`, `num_hands`, `sb/bb`, etc.). Read for reproducibility annotations in plots.

### Pitfall register (15 risks — the plan addresses each)

1. **DuckDB struct inference on heterogeneous `final_action`.** Rows alternate between `{"type":"fold"}` and `{"type":"raise_to","amount":300}`. `read_json_auto` samples rows to infer a struct schema; if sampling misses the `amount` field, later rows with `amount` might fail to parse or come in as NULL. **Mitigation**: Task 3 is a canary smoke test that reads a real Phase 2a session BEFORE any metric SQL lands. Use `read_json_auto(..., sample_size=-1)` (full scan) to guarantee schema unification.

2. **`is_forced_blind` is always `false` in Phase 2a.** Spec §8.3's VPIP SQL filter `WHERE is_forced_blind = false` is trivially always true for mock-agent data — which is semantically CORRECT because blinds are posted by PokerKit automation, not by agents, so blind posts never produce an agent_view_snapshot row. Document this in the SQL comment; don't "simplify" by removing the filter (Phase 3 LLM agents might theoretically emit blind-post records, and the filter stays load-bearing).

3. **Spec view naming is confusing for our shape.** Spec §8.2 names views `public_events` (=public_replay.jsonl) / `hands` (=canonical_private.jsonl) / `actions` (=agent_view_snapshots.jsonl). In Phase 2a shape, `public_events` rows are HAND records (not events) and `actions` rows are SNAPSHOTS (not actions). Keep spec names for continuity with §8.3 SQL; add a comment block in `open_session` explaining the misnomer.

4. **Spec's `is_private_access_ok(access_token)` vs Phase 2a's `require_private_access(token)`.** Spec §8.2 uses a bool-returning predicate; Phase 2a's `access_control.py` exports a raising function. Use the Phase 2a convention (`require_private_access`) — adapt the spec's `if access_token and is_private_access_ok(...)` to `if access_token: require_private_access(access_token); ...`.

5. **`RUNS_ROOT = Path("runs").resolve()` is cwd-dependent.** Works when tests run from project root. Test code must monkeypatch `RUNS_ROOT` to `tmp_path` so test sessions can live under a trusted root. The baseline runner (Task 7) should accept an explicit `output_dir: Path` and ensure tests monkeypatch before calling.

6. **`RUNS_ROOT` whitelist rejects `tmp_path` by default.** If a test writes a session to `tmp_path/session_001/` but `RUNS_ROOT = /Users/.../llm-poker-arena/runs`, `safe_json_source` will reject. Every test that uses `open_session` must monkeypatch `llm_poker_arena.storage.duckdb_query.RUNS_ROOT` to the test's tmp root FIRST.

7. **Blind posts NOT in `canonical_private.actions`.** Phase 2a `Session` only records agent turns; PokerKit's `BlindOrStraddlePosting` operation is not synthesized into an `ActionRecordPrivate`. Any analysis that counts "actions per hand" from `hands` view will under-count by 2 (SB + BB). Phase 2b metrics all read from `actions` view (=agent_view_snapshots) where this is not an issue.

8. **`final_invested` is `{}`.** Phase 2a deferred per-seat cumulative contribution tracking. Any metric that needs "chips voluntarily put in" should reconstruct from snapshot `final_action.amount` SUM, not read `hands.result.final_invested` (which is empty).

9. **DuckDB dot-access syntax.** `final_action.type` in DuckDB SQL accesses a struct field via dot notation. For JSON data this works when the field's schema is inferred as STRUCT. Alternative: `final_action['type']::VARCHAR` (subscript + cast). Use dot notation per spec §8.3, with fallback to subscript if the canary test fails.

10. **Plan drift recurrence.** Phase 1 had `config=cfg` stale kwarg in multiple plan task bodies, Phase 2a had `PublicReplayEvent` wrapper that broke round-trip. Phase 2b MUST validate each SQL snippet against the as-built schema (Task 3 canary does this empirically).

11. **matplotlib test backend.** Tests that import matplotlib in a headless CI or pytest-xdist worker will try to open a GUI backend and hang. Always set `matplotlib.use("Agg")` BEFORE `import matplotlib.pyplot as plt` in plot modules.

12. **DuckDB in-memory connections are per-call.** `duckdb.connect(":memory:")` creates a fresh connection each call — views don't persist across calls. The analysis pipeline must either hold a single connection for the whole analysis OR re-open-and-re-create-views per metric. Task 2's `open_session` returns a connection that callers MUST close (use `with` context manager or explicit `.close()`).

13. **`readline` segfault environment workaround.** Already documented in Phase 1 memory. `source .venv/bin/activate && pytest` works; `uv run pytest` segfaults. No Phase-2b-specific action needed.

14. **Not every (seat, hand) pair produces an `AgentViewSnapshot`.** Empirically verified (Codex review of this plan, DuckDB 1.5.2, 24-hand session rng_seed=42): seat 4 had snapshots on 23/24 hands. When all other seats fold pre-flop and the BB wins by walk, the BB never enters the `while state.actor_index is not None` loop — no snapshot is written for that (seat=BB, hand). Implication: `COUNT(DISTINCT hand_id) FROM actions GROUP BY seat` UNDERCOUNTS the per-seat participating-hand count and inflates VPIP/PFR rates proportionally. The fix used in T4/T5: derive `n_hands` from the `hands` view (which has one row per hand regardless of action count). Tests MUST cover this edge case — see T4/T5 regression fixtures.

15. **DuckDB views over `read_json_auto` re-scan the file on every query.** Empirically confirmed (Codex review). Acceptable for MVP-7-sized sessions (≤ 2000 hands); for multi-session analyses or repeated metrics/charts, materialise to a temporary TABLE via `CREATE TABLE actions AS SELECT * FROM read_json_auto(...)`. Phase 2b does not materialise — plan's tests all open a fresh connection per test so view re-scan cost is bounded.

### What Phase 2b does NOT do (scope discipline)

Per spec §16.1, MVP 7 exit criterion is:
> B1-Random 和 B2-RuleBased 可完整跑 + 出图；`is_forced_blind=false` 路径正常执行

Phase 2b **does NOT**:
- Implement ReAct / LLM agent / tool system (MVP 8-9 = Phase 3)
- Add provider adapters / API calls (Phase 4)
- Reimplement `run_single_hand` again (Phase 2a's `Session` is the final Phase-1-and-earlier orchestrator shape until Phase 3 rewrites it async)
- PHH exporter (§7.7; deferred beyond Phase 2b per spec §16.1's MVP 7 exit criterion)
- Seat permutation logic (§15.4 Phase 4+)
- `config.yaml` rename (still `config.json` until pyyaml lands)
- Cross-session analysis / 5-baseline matrix statistics (that's Phase 5 once we have real LLM runs)

### Branch / worktree

Phase 1 and Phase 2a both ran cleanly on `main`. Continue the same pattern — no worktree needed. If a Phase-2b task fails destructively (unlikely; this is mostly pure additions), we have reflog + 51 commits of reversible history.

---

## File Structure

Files that will exist at Phase 2b completion:

```
src/llm_poker_arena/
├── storage/                                 # existing Phase 2a
│   └── duckdb_query.py                      # NEW — safe_json_source + open_session
├── analysis/                                # NEW subpackage
│   ├── __init__.py                          # NEW — empty docstring
│   ├── sql.py                               # NEW — VPIP/PFR/action_distribution SQL strings
│   ├── metrics.py                           # NEW — compute_vpip / compute_pfr / compute_action_distribution helpers
│   ├── baseline.py                          # NEW — run_random_baseline / run_rule_based_baseline helpers
│   └── plots.py                             # NEW — plot_chip_pnl / plot_action_distribution / plot_vpip_pfr_table
└── (other existing packages unchanged)

tests/
├── unit/
│   ├── test_safe_json_source.py             # NEW (spec §8.2 4 tests)
│   ├── test_duckdb_smoke.py                 # NEW (canary against real Phase 2a output)
│   ├── test_metrics_vpip.py                 # NEW
│   ├── test_metrics_pfr.py                  # NEW
│   ├── test_metrics_action_distribution.py  # NEW
│   ├── test_analysis_baseline.py            # NEW
│   ├── test_analysis_plots.py               # NEW
│   └── test_mvp7_integration.py             # NEW (B1 + B2 end-to-end + plots)

pyproject.toml                               # modify — add duckdb + matplotlib deps
```

Total new src files: 6. Total new test files: 8.

Do NOT touch existing Phase-1 or Phase-2a production files.

---

## Task 1: Add DuckDB + matplotlib to project dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Run the current full suite baseline once so post-change diffs are measurable**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest -m 'not slow' -q 2>&1 | tail -3
```
Expected: `170 passed, 1 deselected`.

- [ ] **Step 2: Modify `pyproject.toml` dependencies list**

Apply this exact change to the `[project].dependencies` list — add two lines:

```toml
dependencies = [
    "pokerkit>=0.7,<0.8",
    "pydantic>=2.0",
    "duckdb>=1.0,<2.0",
    "matplotlib>=3.8,<4.0",
]
```

Leave the `[project.optional-dependencies].dev` block unchanged (pytest/hypothesis/ruff/mypy already pinned there).

- [ ] **Step 3: Install new deps into the existing venv**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pip install duckdb matplotlib
```
Expected: both install. `pip list | grep -E 'duckdb|matplotlib'` shows versions.

- [ ] **Step 4: Verify imports work**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && python -c "import duckdb, matplotlib; print(duckdb.__version__, matplotlib.__version__)"
```
Expected: prints two version strings.

- [ ] **Step 5: Re-run full suite to confirm no regression**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest -m 'not slow' -q && ruff check . && mypy
```
Expected: 170 passed, ruff clean, mypy clean.

- [ ] **Step 6: Commit**

```bash
cd /Users/zcheng256/llm-poker-arena && git add pyproject.toml && git commit -m "chore(deps): add duckdb + matplotlib for Phase 2b analysis layer"
```

---

## Task 2: `safe_json_source` + `open_session` (`storage/duckdb_query.py`)

**Files:**
- Create: `src/llm_poker_arena/storage/duckdb_query.py`
- Create: `tests/unit/test_safe_json_source.py`

Per spec §8.2. The `safe_json_source(path)` helper takes a filesystem path, verifies it lives under the trusted `RUNS_ROOT`, and returns a DuckDB SQL string literal with proper single-quote escaping. `open_session(session_dir, access_token=None)` spins up an in-memory DuckDB connection with 1-3 views per access level.

### Risk callouts for this task

- **Risk 4** — adapt spec's `is_private_access_ok(...)` call to Phase 2a's `require_private_access(...)` (raises instead of returning bool). The Phase 2a `access_control.PRIVATE_ACCESS_TOKEN` is the sentinel.
- **Risk 5/6** — `RUNS_ROOT` is module-global; tests MUST monkeypatch before calling `safe_json_source` with a `tmp_path`-built path.
- **Risk 12** — `open_session` returns `duckdb.DuckDBPyConnection`; caller is responsible for `con.close()` (or `with`). Add a docstring note.

- [ ] **Step 1: Write failing tests**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_safe_json_source.py`:

```python
"""Tests for safe_json_source (spec §8.2 path whitelist + SQL literal escaping)."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_accepts_paths_under_runs_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.storage.duckdb_query import safe_json_source

    session_dir = tmp_path / "session_2026-04-24_a8f3b2"
    session_dir.mkdir()
    p = session_dir / "public_replay.jsonl"
    p.touch()
    result = safe_json_source(p)
    assert str(p.resolve()) in result
    assert result.startswith("'") and result.endswith("'")


def test_rejects_paths_outside_runs_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", runs_root.resolve()
    )
    from llm_poker_arena.storage.duckdb_query import safe_json_source

    outside = tmp_path / "elsewhere" / "evil.jsonl"
    outside.parent.mkdir(parents=True)
    outside.touch()
    with pytest.raises(ValueError, match="not under trusted runs root"):
        safe_json_source(outside)


def test_rejects_path_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", runs_root.resolve()
    )
    from llm_poker_arena.storage.duckdb_query import safe_json_source

    # Path with `..` that resolves outside runs_root.
    traversal = runs_root / ".." / "etc" / "passwd"
    with pytest.raises(ValueError, match="not under trusted runs root"):
        safe_json_source(traversal)


def test_escapes_single_quotes_in_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.storage.duckdb_query import safe_json_source

    weird = tmp_path / "session_o'malley" / "public.jsonl"
    weird.parent.mkdir()
    weird.touch()
    result = safe_json_source(weird)
    assert "''" in result  # single quote doubled
    assert result.startswith("'") and result.endswith("'")


def test_open_session_public_only_without_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """public_events view exists; hands + actions do NOT (no access token)."""
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.storage.duckdb_query import open_session

    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    (session_dir / "public_replay.jsonl").write_text(
        '{"hand_id":0,"street_events":[]}\n'
    )
    con = open_session(session_dir)
    try:
        views = {
            row[0]
            for row in con.sql(
                "SELECT view_name FROM duckdb_views() WHERE NOT internal"
            ).fetchall()
        }
        assert "public_events" in views
        assert "hands" not in views
        assert "actions" not in views
    finally:
        con.close()


def test_open_session_with_token_exposes_all_three_views(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN
    from llm_poker_arena.storage.duckdb_query import open_session

    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    (session_dir / "public_replay.jsonl").write_text(
        '{"hand_id":0,"street_events":[]}\n'
    )
    (session_dir / "canonical_private.jsonl").write_text(
        '{"hand_id":0}\n'
    )
    (session_dir / "agent_view_snapshots.jsonl").write_text(
        '{"hand_id":0,"seat":0}\n'
    )
    con = open_session(session_dir, access_token=PRIVATE_ACCESS_TOKEN)
    try:
        views = {
            row[0]
            for row in con.sql(
                "SELECT view_name FROM duckdb_views() WHERE NOT internal"
            ).fetchall()
        }
        assert {"public_events", "hands", "actions"}.issubset(views)
    finally:
        con.close()


def test_open_session_with_bad_token_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.storage.duckdb_query import open_session

    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    (session_dir / "public_replay.jsonl").write_text(
        '{"hand_id":0,"street_events":[]}\n'
    )
    with pytest.raises(PermissionError, match="access_token"):
        open_session(session_dir, access_token="wrong-token")
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_safe_json_source.py -v
```
Expected: `ModuleNotFoundError: No module named 'llm_poker_arena.storage.duckdb_query'`.

- [ ] **Step 3: Implement `duckdb_query.py`**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/storage/duckdb_query.py`:

```python
"""DuckDB query-side helpers (spec §8.2 / H-11 / PP-07).

`safe_json_source(path)` renders a filesystem path as a DuckDB SQL string
literal, enforcing two independent defences:

    1. Whitelist: `path.resolve()` must be a descendant of `RUNS_ROOT`
       (the trusted session-outputs root). Path traversal via `..` is
       blocked because `resolve()` normalises before the prefix check.
    2. Escape: DuckDB string literals use single quotes; internal single
       quotes are escaped by doubling (`'` → `''`).

Both defences matter because DuckDB's `read_json_auto(...)` is a table
function whose path argument CANNOT be bound as a parameterised `?`
placeholder — we must embed the path as a SQL literal, and unvalidated
input would be an injection vector.

`open_session(session_dir, access_token=None)` creates an in-memory
DuckDB connection and registers 1-3 views depending on access level:

- Always: `public_events` (public_replay.jsonl)
- With valid token: additionally `hands` (canonical_private.jsonl) and
  `actions` (agent_view_snapshots.jsonl)

View name note: spec §8.2 names are preserved for continuity with §8.3
SQL — but in the Phase-2a JSONL shape, `public_events` rows are HAND
records (one per line, with a `street_events` array inside) and `actions`
rows are SNAPSHOTS (one per agent turn). Neither view name matches its
payload at a glance; keep them anyway to match spec.

Callers own the returned connection's lifecycle: use a `with` block or
call `con.close()` when done.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from llm_poker_arena.storage.access_control import require_private_access

RUNS_ROOT: Path = Path("runs").resolve()


def safe_json_source(path: Path) -> str:
    """Return a DuckDB SQL string literal for `path`, gated by RUNS_ROOT.

    Raises `ValueError` if the resolved path is not under `RUNS_ROOT`.
    """
    abs_path = path.resolve()
    try:
        abs_path.relative_to(RUNS_ROOT)
    except ValueError as e:
        raise ValueError(
            f"Path {abs_path} not under trusted runs root {RUNS_ROOT}"
        ) from e
    escaped = str(abs_path).replace("'", "''")
    return f"'{escaped}'"


def open_session(
    session_dir: Path, access_token: str | None = None,
) -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB connection over a session_dir's JSONL files.

    Args:
        session_dir: directory containing public_replay.jsonl (required)
            and canonical_private.jsonl + agent_view_snapshots.jsonl (required
            for private-access queries).
        access_token: if provided, must match the Phase-2a sentinel
            (`access_control.PRIVATE_ACCESS_TOKEN`) — else `PermissionError`.

    Returns: a `duckdb.DuckDBPyConnection` with views registered. Caller owns
    `.close()` — use `with` or explicit close.

    Uses `read_json_auto(..., sample_size=-1)` to force full-scan schema
    inference. A partial sample could miss rare struct variants (e.g.
    `final_action` with an `amount` key present on only some rows — Risk 1).
    """
    con = duckdb.connect(":memory:")

    public_src = safe_json_source(session_dir / "public_replay.jsonl")
    con.sql(
        f"CREATE VIEW public_events AS "
        f"SELECT * FROM read_json_auto({public_src}, sample_size=-1);"
    )

    if access_token is not None:
        require_private_access(access_token)
        private_src = safe_json_source(session_dir / "canonical_private.jsonl")
        snapshots_src = safe_json_source(session_dir / "agent_view_snapshots.jsonl")
        con.sql(
            f"CREATE VIEW hands AS "
            f"SELECT * FROM read_json_auto({private_src}, sample_size=-1);"
        )
        con.sql(
            f"CREATE VIEW actions AS "
            f"SELECT * FROM read_json_auto({snapshots_src}, sample_size=-1);"
        )

    return con
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_safe_json_source.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Lint + type**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy
```
Expected: clean. If mypy complains about `duckdb.DuckDBPyConnection` missing stubs, add `duckdb.*` to the existing `[[tool.mypy.overrides]]` block in pyproject.toml (similar to the existing `pokerkit.*` override).

- [ ] **Step 6: Commit**

```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/storage/duckdb_query.py tests/unit/test_safe_json_source.py && git commit -m "feat(storage): DuckDB query layer — safe_json_source + open_session (spec §8.2)"
```

If mypy required a pyproject edit, include it: `git add pyproject.toml ...`.

---

## Task 3: DuckDB canary smoke on a real Phase 2a session

**Files:**
- Create: `tests/unit/test_duckdb_smoke.py`

**Why this task exists**: Risk 1 and Risk 10. Before any metric SQL assumes DuckDB can access `final_action.type` on heterogeneous rows, we need an empirical proof against a real session's output. If DuckDB can't unify the schema, the downstream VPIP/PFR tasks need a different projection strategy (e.g. JSON functions) and we want to know NOW, not during Task 4.

- [ ] **Step 1: Write failing test**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_duckdb_smoke.py`:

```python
"""Canary: DuckDB can read a real Phase 2a session and access nested JSON fields.

This test exists because `read_json_auto` schema inference on heterogeneous
structs (e.g. `final_action` where `amount` is present on some rows and
absent on others) has historically bitten similar projects. If this test
starts failing, the metric SQL tasks (T4-T6) need to use explicit JSON
extraction instead of dot-access.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session
from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN


def _run_small_session(tmp_path: Path) -> Path:
    """Run a 12-hand heterogeneous session; return the output dir."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=12, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    agents = [RandomAgent(), RuleBasedAgent()] * 3
    sess_dir = tmp_path / "sess_smoke"
    Session(config=cfg, agents=agents, output_dir=sess_dir,
            session_id="smoke").run()
    return sess_dir


def test_duckdb_can_read_actions_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """actions view opens and exposes columns we rely on in T4-T6."""
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run_small_session(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        # DESCRIBE returns (column_name, column_type, null, key, default, extra)
        # — column NAMES live at row[0], NOT row[1].
        cols = {
            row[0]
            for row in con.sql("DESCRIBE actions").fetchall()
        }
        # Required fields for VPIP/PFR/action_distribution SQL.
        for required in ("seat", "hand_id", "street", "is_forced_blind",
                         "final_action"):
            assert required in cols, f"missing column: {required}"


def test_duckdb_can_access_final_action_type_via_dot_notation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The critical risk: `final_action.type` dot-access on a heterogeneous
    struct column (some rows have `amount`, some don't). If this test fails,
    switch metric SQL to `final_action['type']` subscript syntax.
    """
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run_small_session(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        # Count distinct action types over all snapshots.
        rows = con.sql(
            "SELECT DISTINCT final_action.type FROM actions"
        ).fetchall()
        types = {row[0] for row in rows if row[0] is not None}
        # Must have at least fold / call / raise_to / check — some agent
        # must have hit several. 12 hands × 6 seats guarantees variety.
        assert len(types) >= 2, (
            f"expected ≥2 distinct action types, got {types}; if empty, "
            f"dot-access may be broken — try final_action['type']"
        )
        # Known-valid set from spec §3.3:
        assert types <= {"fold", "check", "call", "bet", "raise_to", "all_in"}
```

- [ ] **Step 2: Run — expect pass (this is a canary; a failure flags a real schema-inference issue, not a missing implementation)**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_duckdb_smoke.py -v
```
Expected: 2 passed. If `test_duckdb_can_access_final_action_type_via_dot_notation` fails, STOP — investigate DuckDB's actual inferred schema via `con.sql("DESCRIBE actions").show()` and decide whether subscript syntax or explicit typecast is needed. Do NOT proceed to T4 until this canary passes.

- [ ] **Step 3: Lint + type**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy
```
Expected: clean.

- [ ] **Step 4: Commit**

```bash
cd /Users/zcheng256/llm-poker-arena && git add tests/unit/test_duckdb_smoke.py && git commit -m "test(storage): DuckDB canary — read real Phase 2a session via dot-access on final_action"
```

---

## Task 4: VPIP SQL + `analysis/metrics.py` scaffolding

**Files:**
- Create: `src/llm_poker_arena/analysis/__init__.py`
- Create: `src/llm_poker_arena/analysis/sql.py`
- Create: `src/llm_poker_arena/analysis/metrics.py`
- Create: `tests/unit/test_metrics_vpip.py`

Spec §8.3 VPIP SQL (verbatim, only reformatted for consistency). Wrapper function `compute_vpip(con) -> list[dict]` returns per-seat rows `{seat, n_hands, vpip_rate}`.

### Risk callouts for this task

- **Risk 2** — `is_forced_blind = false` is trivially true in Phase 2a but the filter must stay (Phase 3 might populate it).
- **Risk 9** — dot notation on `final_action.type` was verified in Task 3's canary. If Task 3 passed, this task inherits that confidence.

- [ ] **Step 1: Write failing test**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_metrics_vpip.py`:

```python
"""Tests for compute_vpip (spec §8.3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session
from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN


def _run_b1(tmp_path: Path, num_hands: int = 12) -> Path:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=17,
    )
    sess_dir = tmp_path / "b1"
    Session(config=cfg, agents=[RandomAgent() for _ in range(6)],
            output_dir=sess_dir, session_id="b1").run()
    return sess_dir


def test_compute_vpip_returns_one_row_per_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.metrics import compute_vpip
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run_b1(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        result = compute_vpip(con)
        # Derive the authoritative hand count from `hands` view (NOT from
        # actions — see Risk 14: walks cause missing snapshots, so an
        # actions-derived count would be systematically low and inflate VPIP).
        expected_n_hands = con.sql("SELECT COUNT(*) FROM hands").fetchone()[0]
    # 6 seats, ordered by seat asc.
    assert len(result) == 6
    assert [r["seat"] for r in result] == [0, 1, 2, 3, 4, 5]
    for row in result:
        # n_hands MUST equal the actual hands dealt (every seat in 6-max cash
        # with auto-rebuy is dealt into every hand per spec §3.5).
        assert row["n_hands"] == expected_n_hands, (
            f"seat {row['seat']}: VPIP denominator {row['n_hands']} "
            f"!= hands dealt {expected_n_hands} — walk-handling regression"
        )
        # vpip_rate is in [0, 1].
        assert 0.0 <= row["vpip_rate"] <= 1.0


def test_compute_vpip_counts_voluntary_actions_not_folds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A seat that folds every preflop has vpip_rate == 0.

    RandomAgent is uniform — some seats will have 0 hands and some won't.
    This test only asserts the measured rate is consistent with the SQL
    definition by sampling one seat and verifying manually against the
    snapshots.
    """
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.metrics import compute_vpip
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run_b1(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        result = {r["seat"]: r for r in compute_vpip(con)}
        # Re-derive: for seat 0, count preflop hands with a voluntary action.
        seat0_voluntary_hands = {
            row[0]
            for row in con.sql(
                "SELECT DISTINCT hand_id FROM actions "
                "WHERE seat = 0 AND street = 'preflop' "
                "AND is_forced_blind = false "
                "AND final_action.type IN ('call', 'raise_to', 'bet', 'all_in')"
            ).fetchall()
        }
        expected = len(seat0_voluntary_hands) / result[0]["n_hands"]
        assert abs(result[0]["vpip_rate"] - expected) < 1e-9


def test_compute_vpip_denominator_uses_hands_not_actions_on_walks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression (Risk 14): a seat that had walks (BB wins without acting)
    still gets VPIP denominator = total hands dealt, NOT the snapshot count.

    Synthesises a minimal 3-hand session where seat 5 is missing from hand
    2's agent_view_snapshots (simulating a walk). Asserts VPIP's
    `n_hands` for seat 5 is 3 (all hands dealt), not 2 (snapshots only).
    """
    import json

    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.metrics import compute_vpip
    from llm_poker_arena.storage.duckdb_query import open_session

    sess = tmp_path / "synth"
    sess.mkdir()

    # canonical_private.jsonl — 3 hands, all 6 seats dealt every hand.
    hands_data = [
        {
            "hand_id": i, "started_at": "t0", "ended_at": "t1",
            "button_seat": 0, "sb_seat": 1, "bb_seat": 2, "deck_seed": i,
            "starting_stacks": {str(s): 10000 for s in range(6)},
            "hole_cards": {str(s): ["As", "Kd"] for s in range(6)},
            "community": [], "actions": [],
            "result": {
                "showdown": False, "winners": [], "side_pots": [],
                "final_invested": {},
                "net_pnl": {str(s): 0 for s in range(6)},
            },
        }
        for i in range(3)
    ]
    (sess / "canonical_private.jsonl").write_text(
        "\n".join(json.dumps(h) for h in hands_data) + "\n"
    )

    # agent_view_snapshots.jsonl — seat 5 is MISSING from hand 2 (walk).
    snaps = []
    for hand_id in range(3):
        seats_here = range(6) if hand_id != 2 else range(5)
        for seat in seats_here:
            snaps.append({
                "hand_id": hand_id, "turn_id": f"{hand_id}-preflop-{seat}",
                "session_id": "synth", "seat": seat, "street": "preflop",
                "timestamp": "t0", "view_at_turn_start": {},
                "iterations": [],
                "final_action": {"type": "fold"},
                "is_forced_blind": False, "total_utility_calls": 0,
                "api_retry_count": 0, "illegal_action_retry_count": 0,
                "no_tool_retry_count": 0, "tool_usage_error_count": 0,
                "default_action_fallback": False,
                "api_error": None, "turn_timeout_exceeded": False,
                "total_tokens": {}, "wall_time_ms": 0,
                "agent": {
                    "provider": "synth", "model": "x", "version": "1",
                    "temperature": None, "seed": None,
                },
            })
    (sess / "agent_view_snapshots.jsonl").write_text(
        "\n".join(json.dumps(s) for s in snaps) + "\n"
    )

    # public_replay.jsonl — minimal stub (required by open_session).
    (sess / "public_replay.jsonl").write_text(
        '{"hand_id": 0, "street_events": []}\n'
    )

    with open_session(sess, access_token=PRIVATE_ACCESS_TOKEN) as con:
        result = compute_vpip(con)

    # Seat 5 has 2 snapshots (hands 0 and 1) but was dealt in 3 hands.
    # The bugged denominator would report n_hands=2; correct is 3.
    seat5 = next(r for r in result if r["seat"] == 5)
    assert seat5["n_hands"] == 3, (
        f"seat 5 denominator {seat5['n_hands']} != 3 (walk-handling bug). "
        f"full result: {result}"
    )
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_metrics_vpip.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement analysis subpackage**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/analysis/__init__.py`:

```python
"""Phase 2b analysis layer — DuckDB-backed metric queries + plots.

Phase 2b scope: spec §16.1 MVP 7. Consumes Phase 2a JSONL outputs via
`storage.duckdb_query.open_session`; produces VPIP/PFR/action distribution
tables and matplotlib charts.

Phase 3+ will add cross-session aggregation over the 5-baseline matrix.
"""
```

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/analysis/sql.py`:

```python
"""SQL strings for Phase 2b metrics (spec §8.3 + §15.3).

Keep the SQL as plain string constants so it can be diffed in PR review
and copy-pasted into `duckdb` REPL for ad-hoc debugging. Do NOT templatise
with f-strings — if a query ever needs a parameter, use DuckDB's bind
mechanism via `con.execute(sql, params)`.

All queries target the three views registered by
`storage.duckdb_query.open_session` with a valid access_token:
- `actions` = agent_view_snapshots.jsonl (NOT the hand-level action tuple)
- `hands` = canonical_private.jsonl
- `public_events` = public_replay.jsonl (one row per hand)

Risk 2 note: `is_forced_blind = false` is trivially true on Phase-2a
mock-agent data (blinds are posted by PokerKit automation, not agents,
so no agent_view_snapshot exists for blind posts). The filter remains
load-bearing for Phase 3+ if/when agent-driven blind posts are recorded.
"""


VPIP_SQL: str = """
-- VPIP: per-seat fraction of hands where player voluntarily put money in
-- pot preflop. "Voluntary" excludes forced blind posts.
--
-- Denominator note (Risk 14): n_hands = COUNT(*) FROM hands, NOT
-- COUNT(DISTINCT hand_id) FROM actions. In 6-max cash with auto-rebuy
-- every seat is dealt into every hand (§3.5), but an agent_view_snapshot
-- is only written when the seat is the actor. A BB who wins by walk (all
-- others folded pre-action) has ZERO snapshots for that hand, so an
-- actions-based denominator would undercount and inflate VPIP.
--
-- Seat list is derived from `actions` (seats that took at least one
-- action across the session). A seat with ZERO snapshots entire session
-- would be missing from output — vanishingly unlikely for ≥10 hands of
-- random play; tests assert `len(result) == num_players` to catch it.

WITH all_seats AS (
    SELECT DISTINCT seat FROM actions
),
total_hands_dealt AS (
    SELECT COUNT(*) AS n_hands FROM hands
),
voluntary_preflop AS (
    SELECT DISTINCT seat, hand_id
    FROM actions
    WHERE street = 'preflop'
      AND is_forced_blind = false
      AND final_action.type IN ('call', 'raise_to', 'bet', 'all_in')
)
SELECT
    s.seat,
    t.n_hands,
    COUNT(v.hand_id) * 1.0 / t.n_hands AS vpip_rate
FROM all_seats s
CROSS JOIN total_hands_dealt t
LEFT JOIN voluntary_preflop v ON s.seat = v.seat
GROUP BY s.seat, t.n_hands
ORDER BY s.seat;
"""
```

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/analysis/metrics.py`:

```python
"""Per-metric helpers over the Phase 2a JSONL outputs via DuckDB.

Each helper takes a live `duckdb.DuckDBPyConnection` (opened by
`storage.duckdb_query.open_session`) and returns a list of plain dicts
(seat-indexed). Callers own the connection lifecycle.
"""
from __future__ import annotations

from typing import Any

import duckdb

from llm_poker_arena.analysis.sql import VPIP_SQL


def compute_vpip(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Return per-seat VPIP rate.

    Each row: `{"seat": int, "n_hands": int, "vpip_rate": float}`.
    `vpip_rate` is in [0, 1]. `n_hands` is the player's participating-hand
    count (= total hands for all seats since every seat is dealt into
    every hand in 6-max cash games).
    """
    rows = con.sql(VPIP_SQL).fetchall()
    return [
        {"seat": int(r[0]), "n_hands": int(r[1]), "vpip_rate": float(r[2])}
        for r in rows
    ]
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_metrics_vpip.py -v
```
Expected: 3 passed (including the walk-denominator regression).

- [ ] **Step 5: Lint + type**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
cd /Users/zcheng256/llm-poker-arena && git add src/llm_poker_arena/analysis/__init__.py src/llm_poker_arena/analysis/sql.py src/llm_poker_arena/analysis/metrics.py tests/unit/test_metrics_vpip.py && git commit -m "feat(analysis): compute_vpip + spec §8.3 SQL via DuckDB views"
```

---

## Task 5: PFR SQL + `compute_pfr`

**Files:**
- Modify: `src/llm_poker_arena/analysis/sql.py` (append `PFR_SQL`)
- Modify: `src/llm_poker_arena/analysis/metrics.py` (add `compute_pfr`)
- Create: `tests/unit/test_metrics_pfr.py`

PFR = per-seat fraction of hands where player raised preflop (bet/raise_to). `PFR ≤ VPIP` for every seat — a raise is a subset of voluntary actions. Structural mirror of VPIP SQL.

- [ ] **Step 1: Write failing test**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_metrics_pfr.py`:

```python
"""Tests for compute_pfr. PFR ≤ VPIP on every seat."""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session
from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN


def _run_b1(tmp_path: Path, num_hands: int = 24) -> Path:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=31,
    )
    sess_dir = tmp_path / "b1"
    Session(config=cfg, agents=[RandomAgent() for _ in range(6)],
            output_dir=sess_dir, session_id="b1").run()
    return sess_dir


def test_compute_pfr_returns_one_row_per_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.metrics import compute_pfr
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run_b1(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        result = compute_pfr(con)
        # Authoritative denominator from `hands` (Risk 14).
        expected_n_hands = con.sql("SELECT COUNT(*) FROM hands").fetchone()[0]
    assert len(result) == 6
    assert [r["seat"] for r in result] == [0, 1, 2, 3, 4, 5]
    for row in result:
        assert row["n_hands"] == expected_n_hands, (
            f"seat {row['seat']}: PFR denominator {row['n_hands']} "
            f"!= hands dealt {expected_n_hands} — walk-handling regression"
        )
        assert 0.0 <= row["pfr_rate"] <= 1.0


def test_pfr_is_subset_of_vpip_per_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PFR rate ≤ VPIP rate for every seat — a raise is voluntary."""
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.metrics import compute_pfr, compute_vpip
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run_b1(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        vpip = {r["seat"]: r["vpip_rate"] for r in compute_vpip(con)}
        pfr = {r["seat"]: r["pfr_rate"] for r in compute_pfr(con)}
    for seat in range(6):
        assert pfr[seat] <= vpip[seat] + 1e-9, (
            f"seat {seat}: PFR {pfr[seat]} > VPIP {vpip[seat]}"
        )
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_metrics_pfr.py -v
```
Expected: `ImportError: cannot import name 'compute_pfr' from 'llm_poker_arena.analysis.metrics'`.

- [ ] **Step 3: Append `PFR_SQL` to `analysis/sql.py`**

Add below `VPIP_SQL`:

```python


PFR_SQL: str = """
-- PFR: per-seat fraction of hands where player voluntarily raised preflop.
-- PFR ⊆ VPIP (raising is a subset of voluntary action).
-- Denominator semantics: identical to VPIP — hand count from `hands` view,
-- NOT from `actions` (Risk 14; see VPIP_SQL comment).

WITH all_seats AS (
    SELECT DISTINCT seat FROM actions
),
total_hands_dealt AS (
    SELECT COUNT(*) AS n_hands FROM hands
),
preflop_raises AS (
    SELECT DISTINCT seat, hand_id
    FROM actions
    WHERE street = 'preflop'
      AND is_forced_blind = false
      AND final_action.type IN ('raise_to', 'bet')
)
SELECT
    s.seat,
    t.n_hands,
    COUNT(p.hand_id) * 1.0 / t.n_hands AS pfr_rate
FROM all_seats s
CROSS JOIN total_hands_dealt t
LEFT JOIN preflop_raises p ON s.seat = p.seat
GROUP BY s.seat, t.n_hands
ORDER BY s.seat;
"""
```

- [ ] **Step 4: Add `compute_pfr` to `analysis/metrics.py`**

Update the import block and add the function:

```python
from llm_poker_arena.analysis.sql import PFR_SQL, VPIP_SQL


def compute_pfr(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Return per-seat PFR rate (preflop raise frequency, voluntary only)."""
    rows = con.sql(PFR_SQL).fetchall()
    return [
        {"seat": int(r[0]), "n_hands": int(r[1]), "pfr_rate": float(r[2])}
        for r in rows
    ]
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_metrics_pfr.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Lint + type, commit**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy && git add src/llm_poker_arena/analysis/sql.py src/llm_poker_arena/analysis/metrics.py tests/unit/test_metrics_pfr.py && git commit -m "feat(analysis): compute_pfr + PFR SQL mirroring VPIP pattern"
```

---

## Task 6: Action distribution SQL + `compute_action_distribution`

**Files:**
- Modify: `src/llm_poker_arena/analysis/sql.py` (append `ACTION_DISTRIBUTION_SQL`)
- Modify: `src/llm_poker_arena/analysis/metrics.py` (add `compute_action_distribution`)
- Create: `tests/unit/test_metrics_action_distribution.py`

Per spec §15.3 item 2: per-(seat, street) action frequencies for fold/call/raise_to/check/bet/all_in. Output rows `{seat, street, action_type, count, rate_within_street}`.

- [ ] **Step 1: Write failing test**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_metrics_action_distribution.py`:

```python
"""Tests for compute_action_distribution."""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session
from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN


def _run(tmp_path: Path) -> Path:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=24, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=11,
    )
    sess_dir = tmp_path / "b1"
    Session(config=cfg, agents=[RandomAgent() for _ in range(6)],
            output_dir=sess_dir, session_id="b1").run()
    return sess_dir


def test_action_distribution_covers_all_six_seats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.metrics import compute_action_distribution
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        rows = compute_action_distribution(con)
    seats = {r["seat"] for r in rows}
    assert seats == set(range(6))
    # Every (seat, street) block sums to ~1.0 — verify for seat 0 preflop.
    seat0_pre = [r for r in rows if r["seat"] == 0 and r["street"] == "preflop"]
    assert seat0_pre  # at least one preflop action type recorded
    total_rate = sum(r["rate_within_street"] for r in seat0_pre)
    assert abs(total_rate - 1.0) < 1e-9, total_rate


def test_action_distribution_only_reports_known_action_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve()
    )
    from llm_poker_arena.analysis.metrics import compute_action_distribution
    from llm_poker_arena.storage.duckdb_query import open_session

    sess_dir = _run(tmp_path)
    with open_session(sess_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        rows = compute_action_distribution(con)
    VALID = {"fold", "check", "call", "bet", "raise_to", "all_in"}
    for r in rows:
        assert r["action_type"] in VALID, r
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_metrics_action_distribution.py -v
```
Expected: `ImportError: cannot import name 'compute_action_distribution'`.

- [ ] **Step 3: Append `ACTION_DISTRIBUTION_SQL` to `analysis/sql.py`**

```python


ACTION_DISTRIBUTION_SQL: str = """
-- Per-(seat, street) action-type frequency. `rate_within_street` is the
-- within-(seat, street) normalised probability — useful for comparing
-- preflop vs flop aggression without stack-depth noise.

WITH per_row AS (
    SELECT
        seat,
        street,
        final_action.type AS action_type
    FROM actions
    WHERE is_forced_blind = false
),
per_cell AS (
    SELECT seat, street, action_type, COUNT(*) AS cnt
    FROM per_row
    GROUP BY seat, street, action_type
),
per_street_totals AS (
    SELECT seat, street, COUNT(*) AS street_total
    FROM per_row
    GROUP BY seat, street
)
SELECT
    c.seat,
    c.street,
    c.action_type,
    c.cnt AS count,
    c.cnt * 1.0 / t.street_total AS rate_within_street
FROM per_cell c
JOIN per_street_totals t
  ON c.seat = t.seat AND c.street = t.street
ORDER BY c.seat, c.street, c.action_type;
"""
```

- [ ] **Step 4: Add `compute_action_distribution` to `analysis/metrics.py`**

Update imports and add:

```python
from llm_poker_arena.analysis.sql import ACTION_DISTRIBUTION_SQL, PFR_SQL, VPIP_SQL


def compute_action_distribution(
    con: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    """Return per-(seat, street, action_type) frequencies.

    Each row: `{seat, street, action_type, count, rate_within_street}`.
    Multiple rows per (seat, street) — one per action_type observed.
    """
    rows = con.sql(ACTION_DISTRIBUTION_SQL).fetchall()
    return [
        {
            "seat": int(r[0]),
            "street": str(r[1]),
            "action_type": str(r[2]),
            "count": int(r[3]),
            "rate_within_street": float(r[4]),
        }
        for r in rows
    ]
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_metrics_action_distribution.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Lint + type, commit**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy && git add src/llm_poker_arena/analysis/sql.py src/llm_poker_arena/analysis/metrics.py tests/unit/test_metrics_action_distribution.py && git commit -m "feat(analysis): compute_action_distribution — per-(seat, street) action-type frequencies"
```

---

## Task 7: Baseline runner (`analysis/baseline.py`)

**Files:**
- Create: `src/llm_poker_arena/analysis/baseline.py`
- Create: `tests/unit/test_analysis_baseline.py`

Thin helpers wrapping Phase-2a `Session` with B1 (6× Random) and B2 (6× RuleBased) lineups. Callers pass `output_dir` (tests use `tmp_path` under a monkeypatched RUNS_ROOT).

- [ ] **Step 1: Write failing test**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_analysis_baseline.py`:

```python
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
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_analysis_baseline.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `analysis/baseline.py`**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/analysis/baseline.py`:

```python
"""Baseline session runners — spec §15.2 B1 (Random) and B2 (RuleBased).

Thin convenience wrappers over `session.session.Session`. Each runner
produces a full Phase-2a session directory under `output_dir` and returns
the path for downstream analysis. The `num_hands` default (120 = 20 × 6)
satisfies the `num_hands % num_players == 0` constraint without being
so small that per-seat VPIP is dominated by noise.
"""
from __future__ import annotations

from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _default_config(num_hands: int, rng_seed: int) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=rng_seed,
    )


def run_random_baseline(
    output_dir: Path, *, num_hands: int = 120, rng_seed: int = 42,
) -> Path:
    """Run a B1 session (6× RandomAgent) into `output_dir` and return it."""
    cfg = _default_config(num_hands=num_hands, rng_seed=rng_seed)
    agents = [RandomAgent() for _ in range(6)]
    Session(
        config=cfg, agents=agents, output_dir=output_dir,
        session_id="b1_random",
    ).run()
    return output_dir


def run_rule_based_baseline(
    output_dir: Path, *, num_hands: int = 120, rng_seed: int = 42,
) -> Path:
    """Run a B2 session (6× RuleBasedAgent) into `output_dir` and return it."""
    cfg = _default_config(num_hands=num_hands, rng_seed=rng_seed)
    agents = [RuleBasedAgent() for _ in range(6)]
    Session(
        config=cfg, agents=agents, output_dir=output_dir,
        session_id="b2_rule_based",
    ).run()
    return output_dir
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_analysis_baseline.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Lint + type, commit**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy && git add src/llm_poker_arena/analysis/baseline.py tests/unit/test_analysis_baseline.py && git commit -m "feat(analysis): B1/B2 baseline runners wrapping Phase 2a Session"
```

---

## Task 8: Chart rendering (`analysis/plots.py`)

**Files:**
- Create: `src/llm_poker_arena/analysis/plots.py`
- Create: `tests/unit/test_analysis_plots.py`

Three plots per spec §15.3:
- `plot_chip_pnl(session_dir)` — per-seat chip P&L bar chart from `meta.json.chip_pnl`
- `plot_vpip_pfr_table(session_dir)` — per-seat VPIP / PFR side-by-side bar
- `plot_action_distribution(session_dir)` — per-(seat, street) stacked bar

All saved to `session_dir/plots/<name>.png`. Force `matplotlib.use("Agg")` before importing pyplot (Risk 11).

- [ ] **Step 1: Write failing test**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_analysis_plots.py`:

```python
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
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_analysis_plots.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `analysis/plots.py`**

Create `/Users/zcheng256/llm-poker-arena/src/llm_poker_arena/analysis/plots.py`:

```python
"""matplotlib chart rendering over Phase-2a session outputs + DuckDB metrics.

All functions save a PNG to `session_dir/plots/<name>.png` and return the
Path. Phase 2a session_id is pulled from meta.json for subtitle annotations.

Risk 11: `matplotlib.use("Agg")` MUST run before `pyplot` is imported so
tests never try to open a GUI backend.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  — Agg backend must be set first

from llm_poker_arena.analysis.metrics import (
    compute_action_distribution,
    compute_pfr,
    compute_vpip,
)
from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN
from llm_poker_arena.storage.duckdb_query import open_session


def _meta(session_dir: Path) -> dict[str, object]:
    return json.loads((session_dir / "meta.json").read_text())


def _plots_dir(session_dir: Path) -> Path:
    d = session_dir / "plots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def plot_chip_pnl(session_dir: Path) -> Path:
    """Per-seat net P&L bar chart, sorted by seat."""
    meta = _meta(session_dir)
    chip_pnl = meta["chip_pnl"]
    assert isinstance(chip_pnl, dict)
    seats = sorted(int(k) for k in chip_pnl)
    values = [int(chip_pnl[str(s)]) for s in seats]

    fig, ax = plt.subplots(figsize=(7, 4))
    colors = ["steelblue" if v >= 0 else "indianred" for v in values]
    ax.bar([str(s) for s in seats], values, color=colors)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("seat")
    ax.set_ylabel("net chips (end of session)")
    ax.set_title(f"Chip P&L — {meta.get('session_id', '?')}")
    fig.tight_layout()

    out = _plots_dir(session_dir) / "chip_pnl.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def plot_vpip_pfr_table(session_dir: Path) -> Path:
    """Side-by-side bar chart of per-seat VPIP + PFR."""
    meta = _meta(session_dir)
    with open_session(session_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        vpip = {r["seat"]: r["vpip_rate"] for r in compute_vpip(con)}
        pfr = {r["seat"]: r["pfr_rate"] for r in compute_pfr(con)}

    seats = sorted(vpip)
    vpip_vals = [vpip[s] for s in seats]
    pfr_vals = [pfr[s] for s in seats]

    fig, ax = plt.subplots(figsize=(7, 4))
    import numpy as np

    x = np.arange(len(seats))
    width = 0.35
    ax.bar(x - width / 2, vpip_vals, width, label="VPIP", color="steelblue")
    ax.bar(x + width / 2, pfr_vals, width, label="PFR", color="darkorange")
    ax.set_xticks(x)
    ax.set_xticklabels([str(s) for s in seats])
    ax.set_xlabel("seat")
    ax.set_ylabel("rate")
    ax.set_ylim(0, 1)
    ax.legend()
    ax.set_title(f"VPIP / PFR — {meta.get('session_id', '?')}")
    fig.tight_layout()

    out = _plots_dir(session_dir) / "vpip_pfr.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def plot_action_distribution(session_dir: Path) -> Path:
    """Per-(seat, street) action-type stacked bar chart."""
    meta = _meta(session_dir)
    with open_session(session_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        rows = compute_action_distribution(con)

    # Aggregate to (seat, street) → {action_type: rate}.
    agg: dict[tuple[int, str], dict[str, float]] = {}
    for r in rows:
        key = (int(r["seat"]), str(r["street"]))
        agg.setdefault(key, {})[str(r["action_type"])] = float(r["rate_within_street"])

    streets = ["preflop", "flop", "turn", "river"]
    seats = sorted({k[0] for k in agg})
    action_types = ("fold", "check", "call", "bet", "raise_to", "all_in")
    color_map = {
        "fold": "#999999", "check": "#a6cee3", "call": "#1f78b4",
        "bet": "#b2df8a", "raise_to": "#e31a1c", "all_in": "#ff7f00",
    }

    fig, axes = plt.subplots(
        1, len(streets), figsize=(14, 4), sharey=True,
    )
    for ax, street in zip(axes, streets, strict=True):
        bottoms = [0.0] * len(seats)
        for at in action_types:
            rates = [agg.get((s, street), {}).get(at, 0.0) for s in seats]
            ax.bar(
                [str(s) for s in seats], rates,
                bottom=bottoms, label=at, color=color_map[at],
            )
            bottoms = [b + r for b, r in zip(bottoms, rates, strict=True)]
        ax.set_title(street)
        ax.set_ylim(0, 1.01)
        ax.set_xlabel("seat")
    axes[0].set_ylabel("action rate within street")
    axes[-1].legend(loc="upper right", fontsize=7)
    fig.suptitle(f"Action Distribution — {meta.get('session_id', '?')}")
    fig.tight_layout()

    out = _plots_dir(session_dir) / "action_distribution.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest tests/unit/test_analysis_plots.py -v
```
Expected: 3 passed. If any test fails due to matplotlib backend issues (display server, missing Agg), verify `matplotlib.use("Agg")` is called BEFORE any `pyplot` import in `plots.py`.

- [ ] **Step 5: Lint + type, commit**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && ruff check . && mypy && git add src/llm_poker_arena/analysis/plots.py tests/unit/test_analysis_plots.py && git commit -m "feat(analysis): matplotlib-backed chip_pnl + vpip_pfr + action_distribution charts"
```

If `ruff` flags `numpy` as undeclared, add `numpy` to `pyproject.toml` deps (matplotlib depends on it transitively but explicit is better) and amend in the SAME commit. If `mypy` flags numpy missing stubs, add a `[[tool.mypy.overrides]]` for `numpy.*` with `ignore_missing_imports = true`.

---

## Task 9: MVP 7 integration test — B1 + B2 end-to-end

**Files:**
- Create: `tests/unit/test_mvp7_integration.py`

Run B1 and B2 baselines (60 hands each — multiple of 6 for button rotation balance; small enough that the MVP 7 integration test stays under 10s wall-clock; large enough that walks naturally occur and exercise the Risk-14 denominator path), compute all three metrics on both, generate all three plots for both, and assert exit-criterion invariants: DuckDB queries return non-empty, `is_forced_blind=false` path works, chip_pnl is zero-sum.

- [ ] **Step 1: Write test**

Create `/Users/zcheng256/llm-poker-arena/tests/unit/test_mvp7_integration.py`:

```python
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
        compute_action_distribution, compute_pfr, compute_vpip,
    )
    from llm_poker_arena.analysis.plots import (
        plot_action_distribution, plot_chip_pnl, plot_vpip_pfr_table,
    )
    from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN
    from llm_poker_arena.storage.duckdb_query import open_session

    sess = run_random_baseline(tmp_path / "b1", num_hands=60, rng_seed=99)

    # Metrics.
    with open_session(sess, access_token=PRIVATE_ACCESS_TOKEN) as con:
        vpip = compute_vpip(con)
        pfr = compute_pfr(con)
        ad = compute_action_distribution(con)
        expected_n = con.sql("SELECT COUNT(*) FROM hands").fetchone()[0]

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
        compute_action_distribution, compute_pfr, compute_vpip,
    )
    from llm_poker_arena.analysis.plots import (
        plot_action_distribution, plot_chip_pnl, plot_vpip_pfr_table,
    )
    from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN
    from llm_poker_arena.storage.duckdb_query import open_session

    sess = run_rule_based_baseline(tmp_path / "b2", num_hands=60, rng_seed=99)

    with open_session(sess, access_token=PRIVATE_ACCESS_TOKEN) as con:
        vpip = compute_vpip(con)
        pfr = compute_pfr(con)
        ad = compute_action_distribution(con)
    assert len(vpip) == 6 and len(pfr) == 6 and len(ad) > 0
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
```

- [ ] **Step 2: Run**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && time pytest tests/unit/test_mvp7_integration.py -v
```
Expected: 2 passed in < 10s wall-clock. (60 hands × 2 baselines × ~3ms/hand engine time + DuckDB + matplotlib overhead.)

- [ ] **Step 3: Full suite regression**

```bash
cd /Users/zcheng256/llm-poker-arena && source .venv/bin/activate && pytest -m 'not slow' -q && ruff check . && mypy
```
Expected: 170 Phase-2a baseline + (7 T2 + 2 T3 + 3 T4 + 2 T5 + 2 T6 + 2 T7 + 3 T8 + 2 T9) = 170 + 23 = 193 passing. Ruff + mypy clean. (Codex-audit amendment: T4 added a synthetic denominator-regression test to guard Risk 14.)

- [ ] **Step 4: Commit**

```bash
cd /Users/zcheng256/llm-poker-arena && git add tests/unit/test_mvp7_integration.py && git commit -m "test: MVP 7 exit criterion — B1/B2 end-to-end with metrics + charts"
```

---

## Self-Review

Ran after writing, before execution.

**1. Spec coverage.**
- §8.2 `safe_json_source` + `open_session` → Task 2 ✓
- §8.3 VPIP SQL → Task 4 (SQL is spec-verbatim) ✓
- §15.3 item 1 (Chip P&L histogram) → Task 8 `plot_chip_pnl` ✓ (bar chart rather than histogram; spec's "histogram + CI" is cross-session aggregation, not Phase 2b's per-session view — mark as Phase 4+ deferral)
- §15.3 item 2 (Action distribution by street) → Task 8 `plot_action_distribution` ✓
- §15.3 item 3 (VPIP/PFR/AF/3bet%/WTSD%) → Tasks 4-5 cover VPIP + PFR; AF/3bet/WTSD deferred (spec §8.3 only gave verbatim SQL for VPIP, noting "其他衍生指标…具体 SQL 在 analysis/derived_metrics.sql 中给出" which is undefined — defer to Phase 4+ with a note here)
- §15.3 items 4-9 → all Phase 3+ (utility-calls, retry-rate, reasoning-artifact, seat-bias, PHH round-trip, censored-hands breakdown) — none needed for MVP 7 exit.
- §16.1 MVP 7 exit criterion "B1-Random 和 B2-RuleBased 可完整跑 + 出图" → Task 9 ✓

Deferred-but-in-spec items explicitly noted: AF / 3bet% / WTSD% SQL, cross-session P&L histogram with CI, PHH exporter. All acceptable gaps against MVP 7.

**2. Placeholder scan.** Grep'd for "TODO", "TBD", "FIXME", "fill in". None found in this plan body (the self-review section itself mentions "TODO" as a red flag pattern but doesn't use it).

**3. Type consistency.**
- `compute_vpip`, `compute_pfr`, `compute_action_distribution` all return `list[dict[str, Any]]` with stable row shapes — tests use the same keys throughout.
- `run_random_baseline`, `run_rule_based_baseline` both `(output_dir: Path, *, num_hands: int = 120, rng_seed: int = 42) -> Path`.
- `plot_*(session_dir: Path) -> Path`. Always returns the generated file.
- `safe_json_source(path: Path) -> str`; `open_session(session_dir: Path, access_token: str | None = None) -> duckdb.DuckDBPyConnection`.
- Across tasks, `SessionConfig` is always constructed with all 11 fields (mirrors Phase 2a tests — no missing `opponent_stats_min_samples` etc.).

**4. Phase-1 + Phase-2a invariants respected.**
- No destructive git (just additions).
- No `Co-Authored-By`.
- No `warnings.catch_warnings`.
- No reaching into `engine._internal` from analysis layer (analysis consumes storage + session public APIs only).
- pytest invocation uses venv-activate pattern (no `uv run pytest`).

**5. Pitfall register cross-check.** Each of the 15 risks in the Pre-flight is actively mitigated by at least one task:
- R1 (struct inference) → Task 2 (sample_size=-1) + Task 3 (canary); **empirically verified by Codex review: DuckDB 1.5.2 unifies `STRUCT(type VARCHAR, amount BIGINT)` with NULL amount for fold/call rows when `sample_size=-1`**
- R2 (is_forced_blind always false) → Task 4-6 SQL comments
- R3 (view naming) → Task 2 docstring
- R4 (access_token convention) → Task 2 impl
- R5 + R6 (RUNS_ROOT monkeypatch) → all test steps
- R7 (blind posts missing from hands.actions) → metrics read from `actions` view (= snapshots) not `hands`
- R8 (final_invested empty) → not used
- R9 (dot-access) → Task 3 canary; **empirically verified: works in SELECT, WHERE, and GROUP BY**
- R10 (plan drift) → Task 3 canary runs against real as-built output
- R11 (matplotlib Agg) → Task 8 `matplotlib.use("Agg")` before pyplot
- R12 (con lifecycle) → all tests use `with open_session(...) as con:`; **empirically verified: DuckDB 1.5.2 supports context manager**
- R13 (readline) → pytest invocation pattern documented
- R14 (walks produce no snapshot → denominator undercounts) → Task 4+5 SQL derives `n_hands` from `hands` view, NOT `actions`; Task 4 adds explicit synthetic regression test
- R15 (view re-scan cost) → acceptable for MVP-7-sized sessions; Task 2 docstring notes the option to materialize

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-24-llm-poker-arena-phase-2b.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. Phase 2a's pattern (small-tasks bundled — T1 scaffolding, T5+T6 helpers, T9+T10+T11 tests) mapped cleanly.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

**Which approach?**

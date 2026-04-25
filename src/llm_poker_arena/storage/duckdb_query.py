"""DuckDB query-side helpers (spec §8.2 / H-11 / PP-07).

`safe_json_source(path)` renders a filesystem path as a DuckDB SQL string
literal, enforcing two independent defences:

    1. Whitelist: `path.resolve()` must be a descendant of `RUNS_ROOT`
       (the trusted session-outputs root). Path traversal via `..` is
       blocked because `resolve()` normalises before the prefix check.
    2. Escape: DuckDB string literals use single quotes; internal single
       quotes are escaped by doubling (`'` -> `''`).

Both defences matter because DuckDB's `read_json_auto(...)` is a table
function whose path argument CANNOT be bound as a parameterised `?`
placeholder -- we must embed the path as a SQL literal, and unvalidated
input would be an injection vector.

`open_session(session_dir, access_token=None)` creates an in-memory
DuckDB connection and registers 1-3 views depending on access level:

- Always: `public_events` (public_replay.jsonl)
- With valid token: additionally `hands` (canonical_private.jsonl) and
  `actions` (agent_view_snapshots.jsonl)

View name note: spec §8.2 names are preserved for continuity with §8.3
SQL -- but in the Phase-2a JSONL shape, `public_events` rows are HAND
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
            (`access_control.PRIVATE_ACCESS_TOKEN`) -- else `PermissionError`.

    Returns: a `duckdb.DuckDBPyConnection` with views registered. Caller owns
    `.close()` -- use `with` or explicit close.

    Uses `read_json_auto(..., sample_size=-1)` to force full-scan schema
    inference. A partial sample could miss rare struct variants (e.g.
    `final_action` with an `amount` key present on only some rows -- Risk 1).
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

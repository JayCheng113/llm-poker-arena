"""Per-metric helpers over the Phase 2a JSONL outputs via DuckDB.

Each helper takes a live `duckdb.DuckDBPyConnection` (opened by
`storage.duckdb_query.open_session`) and returns a list of plain dicts
(seat-indexed). Callers own the connection lifecycle.

`compute_vpip` and `compute_pfr` accept an explicit `num_players` parameter
so the seat list is generated from `range(0, num_players)` — NOT derived
from `SELECT DISTINCT seat FROM actions`. A seat that had zero snapshots
across the entire session (possible on very small or pathological runs
where the player gets walks / folds-before-act every hand) would otherwise
be silently dropped. Phase-2b Codex audit Part B.2.
"""

from __future__ import annotations

from typing import Any

import duckdb

from llm_poker_arena.analysis.sql import (
    ACTION_DISTRIBUTION_SQL,
    PFR_SQL_TEMPLATE,
    VPIP_SQL_TEMPLATE,
)


def _validate_num_players(num_players: int) -> None:
    """Bounds-check `num_players`. Keeps the f-string SQL interpolation safe.

    `SessionConfig` enforces `2 <= num_players <= 10`; we mirror that here so
    the int formatted into the SQL template is always a small safe integer.
    """
    if not isinstance(num_players, int):
        raise TypeError(f"num_players must be int, got {type(num_players).__name__}")
    if not 2 <= num_players <= 10:
        raise ValueError(f"num_players must be in [2, 10], got {num_players}")


def compute_vpip(
    con: duckdb.DuckDBPyConnection,
    *,
    num_players: int = 6,
) -> list[dict[str, Any]]:
    """Return per-seat VPIP rate for a 6-max (default) or n-max session.

    Each row: `{"seat": int, "n_hands": int, "vpip_rate": float}`. Output is
    always `num_players` rows — seats with zero actions across the session
    still appear (with `vpip_rate=0.0`), unlike a naive seat-from-actions
    derivation which would silently drop them.
    """
    _validate_num_players(num_players)
    sql = VPIP_SQL_TEMPLATE.format(num_players=num_players)
    rows = con.sql(sql).fetchall()
    return [{"seat": int(r[0]), "n_hands": int(r[1]), "vpip_rate": float(r[2])} for r in rows]


def compute_pfr(
    con: duckdb.DuckDBPyConnection,
    *,
    num_players: int = 6,
) -> list[dict[str, Any]]:
    """Return per-seat PFR rate (preflop raise frequency, voluntary only).

    Shape and seat-list semantics mirror `compute_vpip`. PFR ≤ VPIP for
    every seat (raises are a subset of voluntary actions).
    """
    _validate_num_players(num_players)
    sql = PFR_SQL_TEMPLATE.format(num_players=num_players)
    rows = con.sql(sql).fetchall()
    return [{"seat": int(r[0]), "n_hands": int(r[1]), "pfr_rate": float(r[2])} for r in rows]


def compute_action_distribution(
    con: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    """Return per-(seat, street, action_type) frequencies.

    Each row: `{seat, street, action_type, count, rate_within_street}`.
    Multiple rows per (seat, street) — one per action_type observed.

    Sparse by design: if a (seat, street) cell has zero actions, it simply
    has no rows in the output. `plots.plot_action_distribution` fills
    missing cells with zeros at chart time. This is acceptable for Phase 2b;
    if Phase 3 analyses need a dense-over-(seat, street, type) output,
    add a `num_players` parameter here too.
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

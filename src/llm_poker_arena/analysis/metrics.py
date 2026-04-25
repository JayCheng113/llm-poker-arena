"""Per-metric helpers over the Phase 2a JSONL outputs via DuckDB.

Each helper takes a live `duckdb.DuckDBPyConnection` (opened by
`storage.duckdb_query.open_session`) and returns a list of plain dicts
(seat-indexed). Callers own the connection lifecycle.
"""
from __future__ import annotations

from typing import Any

import duckdb

from llm_poker_arena.analysis.sql import ACTION_DISTRIBUTION_SQL, PFR_SQL, VPIP_SQL


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


def compute_pfr(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Return per-seat PFR rate (preflop raise frequency, voluntary only)."""
    rows = con.sql(PFR_SQL).fetchall()
    return [
        {"seat": int(r[0]), "n_hands": int(r[1]), "pfr_rate": float(r[2])}
        for r in rows
    ]


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

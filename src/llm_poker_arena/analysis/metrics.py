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

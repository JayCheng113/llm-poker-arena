"""Phase 2b analysis layer — DuckDB-backed metric queries + plots.

Phase 2b scope: spec §16.1 MVP 7. Consumes Phase 2a JSONL outputs via
`storage.duckdb_query.open_session`; produces VPIP/PFR/action distribution
tables and matplotlib charts.

Phase 3+ will add cross-session aggregation over the 5-baseline matrix.
"""

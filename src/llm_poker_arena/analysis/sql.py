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

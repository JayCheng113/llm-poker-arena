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
        count_row = con.sql("SELECT COUNT(*) FROM hands").fetchone()
        assert count_row is not None
        expected_n_hands = count_row[0]
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

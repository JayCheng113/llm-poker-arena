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
        session_wall_time_sec=90,
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
        chip_pnl={}, session_wall_time_sec=0,
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
        chip_pnl={}, session_wall_time_sec=0,
    )
    # git_commit should be a string (possibly empty if git unavailable).
    assert isinstance(m["git_commit"], str)


def test_meta_session_wall_time_sec_is_passed_through() -> None:
    m = build_session_meta(
        session_id="sess_x", config=_cfg(),
        started_at="t0", ended_at="t1",
        total_hands_played=1, seat_assignment={}, initial_button_seat=0,
        chip_pnl={}, session_wall_time_sec=134,
    )
    assert m["session_wall_time_sec"] == 134

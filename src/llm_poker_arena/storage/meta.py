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
    session_wall_time_sec: int,
    provider_capabilities: dict[str, dict[str, Any]] | None = None,
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
        "provider_capabilities": (provider_capabilities or {}),
        "chip_pnl": {str(s): int(v) for s, v in chip_pnl.items()},
        "retry_summary_per_seat": {},
        "tool_usage_summary": {},
        "censored_hands_count": 0,
        "censored_hand_ids": [],
        "total_tokens": {},
        "estimated_cost_breakdown": {},
        "session_wall_time_sec": int(session_wall_time_sec),
        "seat_assignment": {str(s): label for s, label in seat_assignment.items()},
        "initial_button_seat": initial_button_seat,
        "seat_permutation_id": "phase2a_default",
    }

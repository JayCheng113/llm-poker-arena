"""Session-level meta.json builder (spec §7.6).

Phase 2a: populates session timing, chip P&L, git commit, seat assignment.
Phase 3 fills retry counters, provider_capabilities, estimated_cost_breakdown.
Schema is forward-compatible — Phase 2a omits nothing; unpopulated fields
degenerate to zeros / empty dicts for clean analyst consumption.
"""

from __future__ import annotations

import statistics
import subprocess
from typing import Any

from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.storage.pricing import estimate_cost_usd


def _git_commit() -> str:
    """Best-effort HEAD SHA; returns '' if git unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _latency_summary(
    samples_per_seat: dict[int, list[int]] | None,
) -> dict[str, dict[str, int]]:
    """Reduce per-iteration wall_time_ms samples into p50/p95/max per seat.

    Empty sample list → all zeros (so downstream consumers don't crash).
    """
    if not samples_per_seat:
        return {}
    out: dict[str, dict[str, int]] = {}
    for seat, samples in samples_per_seat.items():
        if not samples:
            out[str(seat)] = {"p50_ms": 0, "p95_ms": 0, "max_ms": 0, "count": 0}
            continue
        sorted_s = sorted(samples)
        # statistics.quantiles uses inclusive interpolation; for tiny
        # samples we fall back to manual indexing.
        if len(sorted_s) >= 4:
            quartiles = statistics.quantiles(sorted_s, n=20)
            p50 = int(statistics.median(sorted_s))
            p95 = int(quartiles[18])  # 95th percentile in 20-quantile split
        else:
            p50 = int(statistics.median(sorted_s))
            p95 = int(sorted_s[-1])
        out[str(seat)] = {
            "p50_ms": p50,
            "p95_ms": p95,
            "max_ms": int(sorted_s[-1]),
            "count": len(samples),
        }
    return out


def _agent_args_summary(
    agents: list[Any] | None,
) -> dict[str, dict[str, Any]]:
    """Snapshot per-seat agent config (model, temperature, timeouts) so the
    run is reproducible. Reads attributes that LLMAgent + RuleBased both
    expose; falls back to None for non-LLM agents."""
    if not agents:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for seat, agent in enumerate(agents):
        out[str(seat)] = {
            "provider_id": getattr(agent, "provider_id", lambda: "unknown")(),
            "model": getattr(agent, "_model", None),
            "temperature": getattr(agent, "_temperature", None),
            "per_iteration_timeout_sec": getattr(agent, "_per_iter_timeout", None),
            "total_turn_timeout_sec": getattr(agent, "_total_turn_timeout", None),
            "version": getattr(agent, "_version", None),
        }
    return out


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
    retry_summary_per_seat: dict[int, dict[str, int]] | None = None,
    tool_usage_summary: dict[int, dict[str, int]] | None = None,
    total_tokens_per_seat: dict[int, dict[str, int]] | None = None,
    hud_per_seat: dict[int, dict[str, int]] | None = None,
    hud_hands_counted: int = 0,
    censored_hand_ids: list[int] | None = None,
    latency_samples_per_seat: dict[int, list[int]] | None = None,
    agents: list[Any] | None = None,
    stop_reason: str = "completed",
) -> dict[str, Any]:
    censored_ids = list(censored_hand_ids or [])
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
        "retry_summary_per_seat": ({str(s): v for s, v in (retry_summary_per_seat or {}).items()}),
        "tool_usage_summary": ({str(s): v for s, v in (tool_usage_summary or {}).items()}),
        # Phase 3c-hud follow-up: persist raw counters + denominator so the
        # web UI can derive VPIP/PFR/3-bet/AF/WTSD ratios without re-running
        # the engine. hud_hands_counted is the denominator for VPIP/PFR
        # (clean-completion hands only — does NOT include censored hands).
        "hud_per_seat": ({str(s): v for s, v in (hud_per_seat or {}).items()}),
        "hud_hands_counted": int(hud_hands_counted),
        # Pre-flight 1: real censored ids (used to be hardcoded 0 / [] —
        # invisible to post-hoc analysis when something failed).
        "censored_hands_count": len(censored_ids),
        "censored_hand_ids": censored_ids,
        "total_tokens": ({str(s): v for s, v in (total_tokens_per_seat or {}).items()}),
        # Pre-flight 6: USD breakdown using the bundled pricing table.
        # Empty dict if pricing unknown for the agent. Always carries
        # price_table_version so analysts know which prices applied.
        "estimated_cost_breakdown": estimate_cost_usd(
            seat_assignment=seat_assignment,
            total_tokens_per_seat=total_tokens_per_seat or {},
        ),
        # Pre-flight 7: per-seat latency summary derived from per-iteration
        # wall_time_ms samples (already in agent_view_snapshots — this is
        # the session-level convenience reduction).
        "latency_per_seat_ms": _latency_summary(latency_samples_per_seat),
        # Pre-flight 8: agent config snapshot so a re-run can match exactly.
        "agent_config_per_seat": _agent_args_summary(agents),
        # SessionConfig knobs that aren't yet captured elsewhere.
        "session_config": {
            "rng_seed": config.rng_seed,
            "max_total_tokens": config.max_total_tokens,
            "max_utility_calls": config.max_utility_calls,
            "enable_math_tools": config.enable_math_tools,
            "enable_hud_tool": config.enable_hud_tool,
            "rationale_required": config.rationale_required,
            "opponent_stats_min_samples": config.opponent_stats_min_samples,
            "starting_stack": config.starting_stack,
            "sb": config.sb,
            "bb": config.bb,
        },
        "session_wall_time_sec": int(session_wall_time_sec),
        "stop_reason": stop_reason,
        "seat_assignment": {str(s): label for s, label in seat_assignment.items()},
        "initial_button_seat": initial_button_seat,
        "seat_permutation_id": "phase2a_default",
    }

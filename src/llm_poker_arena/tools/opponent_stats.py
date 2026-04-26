"""get_opponent_stats utility tool (spec §5.2 / Phase 3c-hud).

Thin accessor over PlayerView.opponent_stats — counter computation lives
in Session._build_opponent_stats. Tool validates seat ∈ [0, num_players),
seat ≠ my_seat, returns OpponentStatsOrInsufficient as dict.

Raises ToolDispatchError on invalid input (matches pot_odds/spr/equity
convention; LLMAgent K+1 loop catches and surfaces error to LLM).
"""
from __future__ import annotations

from typing import Any

from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.tools.runner import ToolDispatchError


def get_opponent_stats(
    view: PlayerView,
    seat: int,
    detail_level: str = "summary",
) -> dict[str, Any]:
    """Return opponent's HUD stats for the given seat.

    Args:
        view: current PlayerView (carries pre-computed opponent_stats dict).
        seat: opponent seat to query. Must be in [0, num_players) and != my_seat.
        detail_level: only "summary" supported in Phase 3c-hud. "detailed"
            reserved for Phase 5+.

    Returns:
        OpponentStatsOrInsufficient as dict (vpip/pfr/three_bet/af/wtsd
        floats, or insufficient=True sentinel).

    Raises:
        ToolDispatchError on invalid input (detail_level, seat range, self-seat).
    """
    if detail_level != "summary":
        raise ToolDispatchError(
            f"detail_level must be 'summary' (got {detail_level!r}); "
            "Phase 3c-hud ships summary only"
        )
    n_players = view.immutable_session_params.num_players
    if isinstance(seat, bool) or not isinstance(seat, int):
        raise ToolDispatchError(
            f"seat must be an integer; got {type(seat).__name__}={seat!r}"
        )
    if not 0 <= seat < n_players:
        raise ToolDispatchError(f"seat {seat!r} not in [0, {n_players})")
    if seat == view.my_seat:
        raise ToolDispatchError(
            f"cannot query own seat ({seat}); use PlayerView fields directly "
            "for self-stats"
        )
    stats = view.opponent_stats.get(seat)
    if stats is None:
        # Should not happen in normal Session flow — Session populates all
        # other seats. Defensive return for edge cases (folded seat post-hand).
        return {"insufficient": True}
    return stats.model_dump(mode="json")

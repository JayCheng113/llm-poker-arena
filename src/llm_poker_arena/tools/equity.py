"""hand_equity_vs_ranges multi-way Monte Carlo equity tool (spec §5.2.3).

Phase 3c-equity skeleton — implementations land in Tasks 2 and 4.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from llm_poker_arena.engine.views import PlayerView


def hand_equity_vs_ranges(
    view: PlayerView,
    range_by_seat: dict[int, str],
    *,
    n_samples: int = 5000,
    seed: int | None = None,
) -> dict[str, Any]:
    """Compute hero equity vs villain ranges via multi-way Monte Carlo.

    spec §5.2.3 main API. range_by_seat keys MUST equal
    view.opponent_seats_in_hand (Task 4 enforces). Returns EquityResult
    dump (dict).
    """
    raise NotImplementedError(
        "Phase 3c-equity Tasks 2-4 implement multi-way MC + tool wrapping."
    )


__all__ = ["hand_equity_vs_ranges"]

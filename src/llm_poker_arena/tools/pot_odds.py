"""pot_odds utility tool (spec §5.2.3 + Phase 3c-math optional-arg superset).

Zero-arg call: read to_call + pot from PlayerView (matches spec §5.2.3).
Args call: use provided values for hypothetical bet-sizing reasoning.

Convention: when to_call == 0 (check is legal), return 0.0 instead of
NaN/error — matches the user-prompt convention that pot_odds_required is
None when to_call == 0.
"""

from __future__ import annotations

from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.tools.runner import ToolDispatchError


def pot_odds(
    view: PlayerView,
    *,
    to_call: int | None = None,
    pot: int | None = None,
) -> float:
    """Return pot odds = to_call / (pot + to_call), or 0.0 if to_call == 0.

    Both args are optional; missing args fall back to view fields.
    Raises ToolDispatchError on negative inputs.
    """
    effective_to_call = view.to_call if to_call is None else to_call
    effective_pot = view.pot if pot is None else pot

    if effective_to_call < 0:
        raise ToolDispatchError(f"to_call must be >= 0, got {effective_to_call}")
    if effective_pot < 0:
        raise ToolDispatchError(f"pot must be >= 0, got {effective_pot}")

    if effective_to_call == 0:
        return 0.0
    return effective_to_call / (effective_pot + effective_to_call)

"""spr (stack-to-pot ratio) utility tool.

Spec §5.2.3 defines spr as zero-arg view-derived (uses effective_stack / pot,
NOT my_stack / pot — effective_stack is the correct commitment measure).

Optional-arg superset mirrors pot_odds: hypothetical post-flop SPR after a
planned bet/raise.
"""

from __future__ import annotations

from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.tools.runner import ToolDispatchError


def spr(
    view: PlayerView,
    *,
    stack: int | None = None,
    pot: int | None = None,
) -> float:
    """Return stack-to-pot ratio = stack / pot.

    Default stack = view.effective_stack (not my_stack — effective is what's
    actually at risk in a showdown).
    Default pot = view.pot.
    Raises ToolDispatchError on pot <= 0 or negative stack.
    """
    effective_stack = view.effective_stack if stack is None else stack
    effective_pot = view.pot if pot is None else pot

    if effective_stack < 0:
        raise ToolDispatchError(f"stack must be >= 0, got {effective_stack}")
    if effective_pot <= 0:
        raise ToolDispatchError(f"pot must be > 0, got {effective_pot}")

    return effective_stack / effective_pot

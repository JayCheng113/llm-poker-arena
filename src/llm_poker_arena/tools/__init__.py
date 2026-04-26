"""Utility tool subpackage (spec §5.2-§5.4).

Phase 3c-math ships the math-tools subset:
  - `pot_odds(view, *, to_call=None, pot=None) -> float`
  - `spr(view, *, stack=None, pot=None) -> float`

Phase 3c-equity will add `hand_equity_vs_ranges` and a `ToolRunner` class
(stateful, holds `EquityBackend`); for 3c-math the dispatcher is a stateless
function `run_utility_tool(view, name, args)` because no per-turn state needs
carrying.
"""
from llm_poker_arena.tools.runner import (
    ToolDispatchError,
    run_utility_tool,
    utility_tool_specs,
)

__all__ = [
    "ToolDispatchError",
    "run_utility_tool",
    "utility_tool_specs",
]

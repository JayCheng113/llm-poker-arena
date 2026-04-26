"""Stateless utility-tool dispatcher (spec §5.4 simplification for 3c-math).

`run_utility_tool(view, name, args)` returns the tool's result as a dict (e.g.
`{"value": 0.297}` for pot_odds/spr) on success. On unknown tool name or
malformed args, raises `ToolDispatchError`; LLMAgent's K+1 loop catches that,
encodes it as an error tool_result message, increments tool_usage_error_count
(analytics counter, NOT a retry budget), and continues until max_utility_calls
or commit (spec §4.2 + §4.1 BR2-05 reading).
"""
from __future__ import annotations

from typing import Any

from llm_poker_arena.engine.views import PlayerView


class ToolDispatchError(Exception):
    """Raised by `run_utility_tool` on unknown name or malformed args.

    LLMAgent treats this as a soft error: emit `{"error": str(e)}` as the
    tool_result, increment tool_usage_error_count, continue the loop.
    """


def run_utility_tool(
    view: PlayerView, name: str, args: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch to the registered utility tool. 3c-math skeleton — Tasks 2-4
    fill in pot_odds/spr branches.
    """
    raise NotImplementedError(
        "Phase 3c-math Tasks 2-4 implement pot_odds and spr; this skeleton "
        "is wired up in Task 1 only to establish the import surface."
    )


def utility_tool_specs(view: PlayerView) -> list[dict[str, Any]]:
    """Return the Anthropic-shape tool spec list for utility tools that are
    enabled on this view's session params. 3c-math skeleton — Task 5 fills in.

    `view.immutable_session_params.enable_math_tools` gates pot_odds + spr.
    """
    raise NotImplementedError(
        "Phase 3c-math Task 5 implements utility_tool_specs."
    )

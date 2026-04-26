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


# Allowed kwargs per tool. Used for both extra-key rejection and the
# whitelist filter when dispatching to the per-tool function.
_ALLOWED_ARGS: dict[str, frozenset[str]] = {
    "pot_odds": frozenset({"to_call", "pot"}),
    "spr": frozenset({"stack", "pot"}),
}


def _validate_int_arg(name: str, value: Any) -> None:
    """Codex audit IMPORTANT-2 fix: input_schema declares integer type, but
    Anthropic SDK does NOT enforce — model can pass strings, floats, or bools.
    Validate at the tool boundary and surface as ToolDispatchError so LLMAgent
    feeds the error back to the model.

    Note: bool is a subclass of int in Python (True == 1, False == 0), so a
    plain isinstance(value, int) accepts bools. We reject bools explicitly —
    a model passing `to_call=True` is almost certainly confused.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolDispatchError(
            f"{name} must be an integer; got {type(value).__name__}={value!r}"
        )


def run_utility_tool(
    view: PlayerView, name: str, args: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch to the registered utility tool. Returns `{"value": float}` for
    pot_odds/spr; richer dicts for future tools. Raises `ToolDispatchError`
    on unknown tool name, extra args, or args type/value validation failure.

    Codex audit IMPORTANT-3 fix: extra args are REJECTED (not silently
    dropped). The tool spec input_schema declares `additionalProperties: False`
    — silently dropping would let the model rely on undefined behavior.
    """
    from llm_poker_arena.tools.pot_odds import pot_odds
    from llm_poker_arena.tools.spr import spr

    if name not in _ALLOWED_ARGS:
        raise ToolDispatchError(f"Unknown utility tool: {name}")

    allowed = _ALLOWED_ARGS[name]
    extra = set(args) - allowed
    if extra:
        raise ToolDispatchError(
            f"{name} received unexpected args {sorted(extra)}; "
            f"allowed: {sorted(allowed)}"
        )
    for k, v in args.items():
        _validate_int_arg(f"{name}.{k}", v)

    if name == "pot_odds":
        return {"value": pot_odds(view, **args)}
    return {"value": spr(view, **args)}


def utility_tool_specs(view: PlayerView) -> list[dict[str, Any]]:
    """Return the Anthropic-shape tool spec list for utility tools enabled on
    this view's session params. Empty list when `enable_math_tools=False`.

    spec §5.3 build_tool_specs reads view.immutable_session_params.enable_math_tools.
    Phase 3c-math ships pot_odds + spr only; 3c-equity adds hand_equity_vs_ranges.
    """
    if not view.immutable_session_params.enable_math_tools:
        return []
    return [
        {
            "name": "pot_odds",
            "description": (
                "Compute pot odds = to_call / (pot + to_call). Optional args "
                "let you compute hypothetical scenarios (e.g. 'if I raise to "
                "X, what pot odds does villain face'). Zero-arg call uses the "
                "current to_call and pot from your turn state."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "to_call": {
                        "type": "integer",
                        "description": "Optional override for the to_call amount; defaults to current.",
                        "minimum": 0,
                    },
                    "pot": {
                        "type": "integer",
                        "description": "Optional override for the pot size; defaults to current.",
                        "minimum": 0,
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        },
        {
            "name": "spr",
            "description": (
                "Compute stack-to-pot ratio = stack / pot. Default stack is "
                "your effective_stack (the smallest live stack at risk for "
                "showdown). Optional args support post-flop SPR planning "
                "(e.g. 'after I raise to X, new SPR on flop is Y')."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "stack": {
                        "type": "integer",
                        "description": "Optional override for the stack; defaults to effective_stack.",
                        "minimum": 0,
                    },
                    "pot": {
                        "type": "integer",
                        "description": "Optional override for the pot size; defaults to current.",
                        "minimum": 1,
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    ]

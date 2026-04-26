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
    "hand_equity_vs_ranges": frozenset({"range_by_seat"}),
    "get_opponent_stats": frozenset({"seat", "detail_level"}),
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
        raise ToolDispatchError(f"{name} must be an integer; got {type(value).__name__}={value!r}")


def run_utility_tool(
    view: PlayerView,
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch to the registered utility tool. Returns `{"value": float}` for
    pot_odds/spr; richer dicts (EquityResult.model_dump()) for equity tools.
    Raises `ToolDispatchError` on unknown tool name, extra args, or args
    type/value validation failure.

    Codex audit IMPORTANT-3 fix: extra args are REJECTED (not silently
    dropped). The tool spec input_schema declares `additionalProperties: False`
    — silently dropping would let the model rely on undefined behavior.

    NB: hand_equity_vs_ranges takes a dict-typed `range_by_seat` arg; the
    int-only validation below applies to pot_odds/spr (which take int args).
    Equity validates its own dict shape internally (Task 4).
    """
    from llm_poker_arena.tools.equity import hand_equity_vs_ranges
    from llm_poker_arena.tools.pot_odds import pot_odds
    from llm_poker_arena.tools.spr import spr

    if name not in _ALLOWED_ARGS:
        raise ToolDispatchError(f"Unknown utility tool: {name}")

    allowed = _ALLOWED_ARGS[name]
    extra = set(args) - allowed
    if extra:
        raise ToolDispatchError(
            f"{name} received unexpected args {sorted(extra)}; allowed: {sorted(allowed)}"
        )

    if name == "pot_odds":
        for k, v in args.items():
            _validate_int_arg(f"{name}.{k}", v)
        return {"value": pot_odds(view, **args)}
    if name == "spr":
        for k, v in args.items():
            _validate_int_arg(f"{name}.{k}", v)
        return {"value": spr(view, **args)}
    if name == "hand_equity_vs_ranges":
        range_by_seat = args.get("range_by_seat")
        if not isinstance(range_by_seat, dict):
            raise ToolDispatchError(
                f"hand_equity_vs_ranges.range_by_seat must be a dict; "
                f"got {type(range_by_seat).__name__}"
            )
        # Coerce JSON-decoded string keys to int (Anthropic tool args may arrive
        # with string keys from JSON, but spec §5.2.3 expects seat: int).
        coerced: dict[int, str] = {}
        for k, val in range_by_seat.items():
            try:
                seat_int = int(k)
            except (ValueError, TypeError) as e:
                raise ToolDispatchError(
                    f"hand_equity_vs_ranges.range_by_seat key {k!r} must be a "
                    f"seat integer (or string-encoded integer)"
                ) from e
            if not isinstance(val, str):
                raise ToolDispatchError(
                    f"hand_equity_vs_ranges.range_by_seat[{seat_int}] must be a "
                    f"string range; got {type(val).__name__}"
                )
            coerced[seat_int] = val
        return hand_equity_vs_ranges(view, coerced)
    # name == "get_opponent_stats" (Phase 3c-hud)
    if not view.immutable_session_params.enable_hud_tool:
        raise ToolDispatchError(
            "get_opponent_stats not enabled (enable_hud_tool=False)"
        )
    # codex audit BLOCKER B3 fix: explicit required-arg validation.
    # _ALLOWED_ARGS only checks for EXTRA args; missing "seat" would otherwise
    # raise an uncaught TypeError from get_opponent_stats(view, **args) since
    # LLMAgent only catches ToolDispatchError.
    if "seat" not in args:
        raise ToolDispatchError(
            "get_opponent_stats requires 'seat' arg"
        )
    from llm_poker_arena.tools.opponent_stats import get_opponent_stats
    return get_opponent_stats(view, **args)


def utility_tool_specs(view: PlayerView) -> list[dict[str, Any]]:
    """Return Anthropic-shape tool spec list for utility tools enabled on
    this view's session params. Empty list when both math and hud are off.

    spec §5.3 build_tool_specs reads view.immutable_session_params for
    enable_math_tools and enable_hud_tool independently. Phase 3c-math
    ships pot_odds + spr; 3c-equity adds hand_equity_vs_ranges (all gated
    on enable_math_tools); 3c-hud adds get_opponent_stats (gated on
    enable_hud_tool, independent of math).
    """
    params = view.immutable_session_params
    specs: list[dict[str, Any]] = []
    if not params.enable_math_tools and not params.enable_hud_tool:
        return specs
    if not params.enable_math_tools:
        # Skip math specs; jump to HUD-only branch.
        if params.enable_hud_tool:
            specs.append(_HUD_TOOL_SPEC)
        return specs
    specs = [
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
        {
            "name": "hand_equity_vs_ranges",
            "description": (
                "Estimate your equity (probability of winning at showdown) "
                "against villains' hand ranges via Monte Carlo. Pass a "
                "range_by_seat dict mapping each opponent seat number "
                "(must equal opponent_seats_in_hand) to an eval7-compatible "
                "range string (e.g. 'QQ+, AKs, AKo'). Returns hero_equity, "
                "ci_low, ci_high, n_samples, seed, backend. Use this for "
                "decisions where pot_odds alone is insufficient — e.g. "
                "calling a multi-way 3-bet, choosing between calling and "
                "shoving on a draw, or evaluating equity vs a polarized 3-bet."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "range_by_seat": {
                        "type": "object",
                        "description": (
                            "Dict mapping seat int to eval7 HandRange string. "
                            "Keys MUST equal opponent_seats_in_hand."
                        ),
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["range_by_seat"],
                "additionalProperties": False,
            },
        },
    ]
    if params.enable_hud_tool:
        specs.append(_HUD_TOOL_SPEC)
    return specs


_HUD_TOOL_SPEC: dict[str, Any] = {
    "name": "get_opponent_stats",
    "description": (
        "Get opponent's HUD stats (VPIP, PFR, 3-bet%, AF, WTSD) "
        "for a specific seat. Returns insufficient=True sentinel "
        "when fewer than opponent_stats_min_samples hands have "
        "accumulated (default 30). Use to model opponent's playing "
        "style for range estimation and bluff/value frequency tuning."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "seat": {
                "type": "integer",
                "description": "Opponent seat ID. Must be in "
                               "[0, num_players) and != your own seat.",
                "minimum": 0,
            },
            "detail_level": {
                "type": "string",
                "enum": ["summary"],
                "description": "Only 'summary' supported in v1.",
                "default": "summary",
            },
        },
        "required": ["seat"],
        "additionalProperties": False,
    },
}

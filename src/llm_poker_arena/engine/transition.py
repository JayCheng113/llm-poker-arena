"""State transition entry point (the only way action proposals mutate CanonicalState).

Flow:
  1. Look up legal tool set for `actor`.
  2. If `action.tool_name` is absent -> return TransitionResult(invalid, reason).
  3. If `bet`/`raise_to` amount is out of declared [min, max] -> return invalid.
  4. Dispatch to PokerKit (.fold(), .check_or_call(), .complete_bet_or_raise_to(amount),
     or `all_in` translated to max completion bet/raise).
  5. Run pre-settlement audit unconditionally (spec P7 / BR2-03): every state
     mutation is followed by card-conservation + chip-conservation checks using
     the SessionConfig attached to the CanonicalState (`state._config`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from llm_poker_arena.engine._internal.audit import HandPhase, audit_invariants
from llm_poker_arena.engine.legal_actions import Action, compute_legal_tool_set

if TYPE_CHECKING:
    from llm_poker_arena.engine._internal.poker_state import CanonicalState


@dataclass(frozen=True, slots=True)
class TransitionResult:
    is_valid: bool
    reason: str | None = None


def apply_action(
    state: CanonicalState, actor: int, action: Action
) -> TransitionResult:
    """Validate `action` against the legal set, dispatch to PokerKit, then audit.

    Returns `TransitionResult(is_valid=False, reason=...)` without mutating
    state if the action is rejected at any stage:
      - tool name not in the legal set;
      - bet/raise_to amount missing, non-int, or out of declared bounds;
      - PokerKit itself rejects the dispatched call.

    On successful dispatch, runs `audit_invariants(state, state._config,
    HandPhase.PRE_SETTLEMENT)`. If that raises AuditFailure, the exception
    propagates (callers are expected to dump crash artifacts and abort the
    hand; corrupted state must not continue).
    """
    legal = compute_legal_tool_set(state, actor)
    legal_names = [t.name for t in legal.tools]

    if action.tool_name not in legal_names:
        return TransitionResult(
            False, f"Action '{action.tool_name}' not in legal set {legal_names}"
        )

    if action.tool_name in ("bet", "raise_to"):
        amt = action.args.get("amount") if isinstance(action.args, dict) else None
        if not isinstance(amt, int):
            return TransitionResult(False, f"{action.tool_name} requires integer 'amount'")
        spec = next(t for t in legal.tools if t.name == action.tool_name)
        amt_bounds = spec.args.get("amount") if isinstance(spec.args, dict) else None
        if not isinstance(amt_bounds, dict):
            return TransitionResult(False, f"{action.tool_name} missing amount bounds")
        mn, mx = int(amt_bounds["min"]), int(amt_bounds["max"])
        if not (mn <= amt <= mx):
            return TransitionResult(
                False, f"{action.tool_name} amount {amt} out of [{mn}, {mx}]"
            )

    raw = state._state  # noqa: SLF001

    # Dispatch to PokerKit. Method names reflect pokerkit>=0.7,<0.8.
    try:
        if action.tool_name == "fold":
            raw.fold()
        elif action.tool_name in ("check", "call"):
            # PokerKit picks check vs call automatically from checking_or_calling_amount.
            raw.check_or_call()
        elif action.tool_name in ("bet", "raise_to"):
            # Amount is the target total bet, not an increment.
            raw.complete_bet_or_raise_to(int(action.args["amount"]))
        elif action.tool_name == "all_in":
            # Translate to max-raise / max-bet; fall back to call-for-less when
            # max completion amount is 0 (actor's stack < call amount, so the
            # only legal action is to shove chips into a call).
            max_amt = int(
                getattr(raw, "max_completion_betting_or_raising_to_amount", 0) or 0
            )
            if max_amt > 0:
                raw.complete_bet_or_raise_to(max_amt)
            else:
                raw.check_or_call()  # forced call-for-less scenario
        else:
            return TransitionResult(False, f"Unhandled action tool '{action.tool_name}'")
    except Exception as e:  # noqa: BLE001 — PokerKit-specific exceptions vary
        return TransitionResult(False, f"PokerKit rejected {action.tool_name}: {e}")

    audit_invariants(state, state._config, HandPhase.PRE_SETTLEMENT)  # noqa: SLF001
    return TransitionResult(True, None)

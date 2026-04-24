"""Legal action computation + safe-action fallback.

compute_legal_tool_set delegates legality decisions (including min-raise
reopening) entirely to PokerKit, per spec §3.3 / BR2-04.

default_safe_action is the fallback for illegal-retry-exhausted or no-tool
paths (§3.3 / BR2-03). It **never** returns an illegal action: `check` if the
actor faces no bet, else `fold`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from llm_poker_arena.engine.views import ActionToolSpec, LegalActionSet, PlayerView

if TYPE_CHECKING:
    from llm_poker_arena.engine._internal.poker_state import CanonicalState


@dataclass(frozen=True, slots=True)
class Action:
    """A concrete action proposal.

    `args` carries tool-specific params (e.g. `{"amount": 300}` for bet/raise_to).
    Note: frozen=True prevents attribute reassignment but `args` dict is
    structurally mutable — do not mutate after construction. Actions are
    short-lived (built → apply → discarded within one turn) so this does not
    cross a persistence boundary, but treat them as immutable by convention.
    """

    tool_name: str
    args: dict[str, Any]


def default_safe_action(view: PlayerView) -> Action:
    """BR2-03 / PP-04 always-legal fallback.

    Returns `check` if `current_bet_to_match - my_invested_this_round <= 0`,
    else `fold`. This guarantee is conditional on the caller's PlayerView
    being faithful to the canonical state: if the view's bet fields disagree
    with pokerkit's `state.bets`, `check` may fire against an open bet and
    PokerKit will reject it with ValueError. The T13 projection layer is
    responsible for keeping those fields consistent with
    `_to_call_amount(raw, my_seat)`.
    """
    to_call = view.current_bet_to_match - view.my_invested_this_round
    if to_call <= 0:
        return Action(tool_name="check", args={})
    return Action(tool_name="fold", args={})


def compute_legal_tool_set(state: CanonicalState, actor: int) -> LegalActionSet:
    """Build the LegalActionSet for `actor` by querying PokerKit capability predicates.

    `all_in` dispatch contract (T12 `apply_action` must honor):
      - If PokerKit accepts `complete_bet_or_raise_to(max_cbor)`, dispatch that.
      - If actor faces a bet larger than their stack, dispatch `check_or_call()`
        (call-for-less; shoves the remaining stack into the pot).
      - If actor has chips but no raise is legal (stack < min_bet pre-bet, or
        all-in-to-call already exceeds pot), dispatch `check_or_call()`.
    The contract is written down here so that widening the set in this file
    requires updating the dispatch in `engine/transition.py` in the same commit.
    """
    raw = state._state  # noqa: SLF001

    tools: list[ActionToolSpec] = []

    can_fold = bool(getattr(raw, "can_fold", lambda: False)())
    can_check_or_call = bool(getattr(raw, "can_check_or_call", lambda: False)())
    can_bet_or_raise = bool(getattr(raw, "can_complete_bet_or_raise_to", lambda: False)())

    # Determine to_call from PokerKit. Try a few common accessors.
    to_call = _to_call_amount(raw, actor)

    if can_fold and to_call > 0:
        tools.append(ActionToolSpec(name="fold", args={}))

    if can_check_or_call:
        if to_call <= 0:
            tools.append(ActionToolSpec(name="check", args={}))
        else:
            tools.append(ActionToolSpec(name="call", args={}))

    if can_bet_or_raise:
        min_amt = int(
            getattr(raw, "min_completion_betting_or_raising_to_amount", 0) or 0
        )
        max_amt = int(
            getattr(raw, "max_completion_betting_or_raising_to_amount", 0) or 0
        )
        if max_amt > 0 and min_amt <= max_amt:
            if to_call <= 0:
                tools.append(
                    ActionToolSpec(
                        name="bet",
                        args={"amount": {"min": min_amt, "max": max_amt}},
                    )
                )
            else:
                tools.append(
                    ActionToolSpec(
                        name="raise_to",
                        args={"amount": {"min": min_amt, "max": max_amt}},
                    )
                )

    # all_in as a convenience tool (available whenever the actor has chips + some
    # action is legal). The engine translates it into bet/raise_to(max) at apply time.
    stacks = getattr(raw, "stacks", ()) or ()
    if 0 <= actor < len(stacks) and int(stacks[actor]) > 0 and (can_check_or_call or can_bet_or_raise):
        tools.append(ActionToolSpec(name="all_in", args={}))

    return LegalActionSet(tools=tuple(tools))


def _to_call_amount(raw: Any, actor: int) -> int:
    """Compute chips needed for `actor` to call the current highest bet this round."""
    bets = list(getattr(raw, "bets", ()) or [])
    if not bets:
        return 0
    my_bet = int(bets[actor]) if 0 <= actor < len(bets) else 0
    max_bet = max(int(b) for b in bets) if bets else 0
    return max(0, max_bet - my_bet)

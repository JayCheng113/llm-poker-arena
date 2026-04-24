"""Seed derivation + single-hand driver for Phase-1 integration tests.

Phase 2 will replace `run_single_hand` with a richer Session orchestrator that
emits events, writes JSONL logs, and handles API errors -> hand censoring. Here
we just need enough to exercise the engine end-to-end under RandomAgent.

Audit coverage (spec P7 / BR2-03):
  - `audit_cards_invariant(state)` fires at CanonicalState construction.
  - `audit_invariants(..., PRE_SETTLEMENT)` fires once here at the start, and
    then is re-invoked inside `apply_action` after every successful action.
  - `audit_invariants(..., POST_SETTLEMENT)` fires once here after the last
    action when no actor is required and no future streets remain. AuditFailure
    propagates (never wrap in try/except): chip-conservation violations are
    hard bugs, not soft agent mistakes.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from llm_poker_arena.engine._internal.audit import (
    HandPhase,
    audit_cards_invariant,
    audit_invariants,
)
from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine.legal_actions import default_safe_action
from llm_poker_arena.engine.projections import build_player_view
from llm_poker_arena.engine.transition import apply_action
from llm_poker_arena.engine.types import Street

if TYPE_CHECKING:
    from llm_poker_arena.agents.base import Agent
    from llm_poker_arena.engine.config import HandContext, SessionConfig


@dataclass(frozen=True, slots=True)
class HandResult:
    hand_id: int
    final_stacks: tuple[int, ...]
    action_trace: tuple[tuple[int, str, int | None], ...]  # (seat, tool_name, amount)
    ended_at_street: Street


def derive_deck_seed(rng_seed: int, hand_id: int) -> int:
    """Deterministic, well-mixed per-hand seed.

    Using BLAKE2b of a canonical byte payload keeps avalanche good even when
    rng_seed varies by 1. The result is truncated to 63 bits so downstream
    `random.Random` accepts it cleanly.
    """
    payload = f"{rng_seed}:{hand_id}".encode()
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big") & ((1 << 63) - 1)


def run_single_hand(
    config: SessionConfig,
    ctx: HandContext,
    agents: Sequence[Agent],
) -> HandResult:
    """Drive one hand end-to-end: deal -> action loop -> street transitions -> settle.

    `agents` is typed `Sequence[Agent]` (not `list[Agent]`) so callers can pass
    a concrete subtype list like `list[RandomAgent]` without triggering mypy's
    list-invariance rule. We only index into it, never mutate it.

    Does NOT handle API errors (Phase 3 replaces this). RandomAgent cannot raise
    in well-formed conditions (its min>max and empty-tool guards are at
    `random_agent.py:17-19, 24-26`), so we deliberately let any surprising
    exception propagate — silent fallbacks would mask real bugs.
    """
    state = CanonicalState(config, ctx)
    audit_cards_invariant(state)
    audit_invariants(state, config, HandPhase.PRE_SETTLEMENT)

    trace: list[tuple[int, str, int | None]] = []
    ended_street = Street.PREFLOP
    turn_counter = 0

    while _actor_required(state):
        actor = _current_actor(state)
        turn_seed = _derive_turn_seed(ctx.deck_seed, actor, turn_counter)
        view = build_player_view(state, actor, turn_seed=turn_seed)
        action = agents[actor].decide(view)

        result = apply_action(state, actor, action)
        if not result.is_valid:
            # Agent produced an illegal action (e.g. RandomAgent picked
            # raise_to bounds that PokerKit rejected for a stack-edge reason
            # the legal-set helper didn't catch); fall back to the always-safe
            # action and keep going.
            safe = default_safe_action(view)
            apply_action(state, actor, safe)
            amt = safe.args.get("amount") if isinstance(safe.args, dict) else None
            trace.append((actor, safe.tool_name, amt))
        else:
            amt = action.args.get("amount") if isinstance(action.args, dict) else None
            trace.append((actor, action.tool_name, amt))

        turn_counter += 1
        _maybe_advance_between_streets(state)
        ended_street = _current_street(state)

    audit_invariants(state, config, HandPhase.POST_SETTLEMENT)

    raw = state._state  # noqa: SLF001
    final_stacks = tuple(int(x) for x in (getattr(raw, "stacks", ()) or ()))
    return HandResult(
        hand_id=ctx.hand_id,
        final_stacks=final_stacks,
        action_trace=tuple(trace),
        ended_at_street=ended_street,
    )


def _actor_required(state: CanonicalState) -> bool:
    """True iff PokerKit wants a seat to act right now.

    Per pokerkit 0.7.3 (notes §D line 177): `state.is_actor_required` does not
    exist. The canonical predicate is `state.actor_index is not None`.
    """
    return state._state.actor_index is not None  # noqa: SLF001


def _current_actor(state: CanonicalState) -> int:
    """Seat index of the actor PokerKit is waiting on.

    Caller must have checked `_actor_required(state)` first; raises if not.
    """
    idx = state._state.actor_index  # noqa: SLF001
    if idx is None:
        raise RuntimeError(
            "no actor required; caller should have checked _actor_required first"
        )
    return int(idx)


def _current_street(state: CanonicalState) -> Street:
    n = len(state.community())
    if n == 0:
        return Street.PREFLOP
    if n == 3:
        return Street.FLOP
    if n == 4:
        return Street.TURN
    return Street.RIVER


def _maybe_advance_between_streets(state: CanonicalState) -> None:
    """Advance PokerKit's internal machinery when no seat needs to act.

    Between the end of a betting round and the start of the next, PokerKit
    may need to:
      - resolve a forced all-in showdown (`can_show_or_muck_hole_cards`), or
      - burn + deal the next street (`can_burn_card` → feed burn + board
        via CanonicalState's deterministic deck).

    We excluded `HOLE_CARDS_SHOWING_OR_MUCKING`, `CARD_BURNING`, and
    `BOARD_DEALING` automations (see `_AUTOMATIONS` in `poker_state.py`), so
    this function explicitly drives those transitions. Loops until PokerKit
    either requires an actor again or the hand is over.

    The loop's termination is guaranteed by PokerKit: each successful
    show/muck or burn+deal advances internal state; when no further
    auto-transition is possible the predicates all return False. A defensive
    iteration cap prevents infinite looping if our predicate assumptions are
    ever wrong.
    """
    raw = state._state  # noqa: SLF001
    # Max plausible transitions per call: 6 shows/mucks + 3 burn+deals = 9,
    # with generous headroom the cap is 32. If we ever hit it, something is
    # wrong with pokerkit's predicate contract and we want to surface it.
    for _ in range(32):
        if _actor_required(state):
            return
        if raw.can_show_or_muck_hole_cards():
            # Default (status_or_hole_cards=None) = PokerKit picks best-for-actor
            # show-or-muck. We have no strategic concern here since hands settle
            # on winning-low criteria once all cards are revealed.
            raw.show_or_muck_hole_cards()
            continue
        if raw.can_burn_card():
            board_len = sum(len(slot) for slot in (raw.board_cards or []))
            if board_len == 0:
                state.deal_community(Street.FLOP)
            elif board_len == 3:
                state.deal_community(Street.TURN)
            elif board_len == 4:
                state.deal_community(Street.RIVER)
            else:
                # Defensive: board in unexpected shape; surface loudly.
                raise RuntimeError(
                    f"unexpected board_len={board_len} with can_burn=True"
                )
            continue
        # No pending transition and no actor required: hand is resolved.
        return
    raise RuntimeError("exceeded between-street advance iteration cap (32)")


def _derive_turn_seed(deck_seed: int, actor: int, turn_counter: int) -> int:
    """Deterministic per-turn RandomAgent seed.

    Same BLAKE2b shape as `derive_deck_seed` so two runs with the same
    (deck_seed, actor, turn_counter) produce identical RandomAgent picks —
    this is what the reproducibility test leans on.
    """
    payload = f"{deck_seed}:{actor}:{turn_counter}".encode()
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big") & (
        (1 << 63) - 1
    )

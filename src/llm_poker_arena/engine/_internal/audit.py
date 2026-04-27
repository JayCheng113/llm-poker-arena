"""Engine audit helpers (§2.2 P7 / BR2-03).

Three kinds of invariants:
  - Card conservation: always (52 unique cards across deck/burn/hole/board/muck).
  - Pre-settlement chip conservation: stacks + total_pot_amount == starting_total.
    (`total_pot_amount` already includes in-flight `bets`; do NOT add them again.)
  - Post-settlement chip conservation: sum(stacks) == starting_total, pot == 0,
    bets == 0.

Fail fast with AuditFailure carrying a descriptive message; the Session
orchestrator is expected to dump crash artifacts before re-raising.
"""

from __future__ import annotations

from enum import Enum
from itertools import combinations
from typing import TYPE_CHECKING

from llm_poker_arena.engine._internal.deck import card_to_str, full_52_card_str_set

if TYPE_CHECKING:
    from pokerkit import Card

    from llm_poker_arena.engine._internal.poker_state import CanonicalState
    from llm_poker_arena.engine.config import SessionConfig


class HandPhase(str, Enum):  # noqa: UP042  # match Street enum style in types.py
    PRE_SETTLEMENT = "pre_settlement"
    POST_SETTLEMENT = "post_settlement"


class AuditFailure(AssertionError):
    """Raised when any engine invariant fails."""


def audit_cards_invariant(state: CanonicalState) -> None:
    raw = state._state  # noqa: SLF001 — internal module allowed
    deck_remaining = list(state._deck_order[state._deck_cursor :])  # noqa: SLF001
    burn_cards = list(getattr(raw, "burn_cards", []) or [])
    # board_cards is list[list[Card]] (outer=slot, inner=runout). Flatten.
    board_nested = getattr(raw, "board_cards", None) or []
    community: list[Card] = []
    for slot in board_nested:
        if slot:
            community.extend(slot)
    hole_all: list[Card] = []
    for seat_cards in getattr(raw, "hole_cards", []) or []:
        if not seat_cards:
            continue
        hole_all.extend(seat_cards)
    mucked = list(getattr(raw, "mucked_cards", []) or [])

    all_cards = deck_remaining + burn_cards + community + hole_all + mucked
    if len(all_cards) != 52:
        raise AuditFailure(
            f"card conservation: expected 52 total, got {len(all_cards)} "
            f"(deck={len(deck_remaining)}, burn={len(burn_cards)}, "
            f"board={len(community)}, hole={len(hole_all)}, muck={len(mucked)})"
        )
    as_strs = [card_to_str(c) for c in all_cards]
    if len(set(as_strs)) != 52:
        dupes = {s for s in as_strs if as_strs.count(s) > 1}
        raise AuditFailure(f"card conservation: duplicate cards detected: {sorted(dupes)}")
    if frozenset(as_strs) != full_52_card_str_set():
        missing = full_52_card_str_set() - frozenset(as_strs)
        raise AuditFailure(f"card conservation: missing cards: {sorted(missing)}")

    # Hole-card pairwise disjointness.
    hole_pairs = [set(cards) for cards in (getattr(raw, "hole_cards", []) or []) if cards]
    for i, j in combinations(range(len(hole_pairs)), 2):
        if hole_pairs[i] & hole_pairs[j]:
            raise AuditFailure(f"card conservation: hole cards overlap between seats {i} and {j}")


def audit_pre_settlement(state: CanonicalState, config: SessionConfig) -> None:
    raw = state._state  # noqa: SLF001
    starting_total = config.starting_stack * config.num_players
    total_stacks = sum(getattr(raw, "stacks", ()) or ())
    # total_pot_amount == collected pots + in-flight bets (PokerKit 0.7.3
    # convention). Adding `sum(bets)` again would double-count in-flight chips.
    total_pot = int(getattr(raw, "total_pot_amount", 0) or 0)
    conserved = total_stacks + total_pot
    if conserved != starting_total:
        in_flight = sum(getattr(raw, "bets", ()) or ())
        collected = total_pot - in_flight
        raise AuditFailure(
            f"pre-settlement chip conservation: {conserved} "
            f"(stacks={total_stacks} + total_pot={total_pot} "
            f"[collected={collected} + in_flight={in_flight}]) "
            f"!= starting_total {starting_total}"
        )


def audit_post_settlement(state: CanonicalState, config: SessionConfig) -> None:
    raw = state._state  # noqa: SLF001
    starting_total = config.starting_stack * config.num_players
    total_stacks = sum(getattr(raw, "stacks", ()) or ())
    if total_stacks != starting_total:
        raise AuditFailure(
            f"post-settlement chip conservation: stacks sum {total_stacks} "
            f"!= starting_total {starting_total}"
        )
    pot = int(getattr(raw, "total_pot_amount", 0) or 0)
    if pot != 0:
        raise AuditFailure(f"post-settlement pot should be 0, got {pot}")
    bets = sum(getattr(raw, "bets", ()) or ())
    if bets != 0:
        raise AuditFailure(f"post-settlement bets should be 0, got {bets}")


def audit_invariants(state: CanonicalState, config: SessionConfig, phase: HandPhase) -> None:
    audit_cards_invariant(state)
    if phase == HandPhase.POST_SETTLEMENT:
        audit_post_settlement(state, config)
    else:
        audit_pre_settlement(state, config)

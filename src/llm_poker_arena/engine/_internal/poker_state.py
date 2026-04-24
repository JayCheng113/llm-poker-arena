"""CanonicalState: the single canonical game state wrapper.

Phase-1 scope: construction + blinds rotation + hole/board deterministic deal
(Tasks 7-9). Action application and audit plumb in Tasks 11-13.

Invariants (from spec §3.1 / PP-01 / PP-02):
  - CARD_BURNING / HOLE_DEALING / BOARD_DEALING PokerKit automations are
    DISABLED so all card movement flows through our seeded deck.
  - Blinds tuple rotates: SB at (button_seat + 1) % num_players, BB at
    (button_seat + 2) % num_players.
  - Starts fresh per hand; no state persists across hands in this object.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pokerkit import Automation, NoLimitTexasHoldem

from llm_poker_arena.engine._internal.deck import build_deterministic_deck
from llm_poker_arena.engine.config import HandContext, SessionConfig

if TYPE_CHECKING:
    from pokerkit import Card, State


_AUTOMATIONS: tuple[Automation, ...] = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    # CARD_BURNING, HOLE_DEALING, BOARD_DEALING intentionally OFF.
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
    Automation.RUNOUT_COUNT_SELECTION,
)


class CanonicalState:
    """Wraps pokerkit.State with deterministic deck + rotated blinds."""

    def __init__(self, config: SessionConfig, hand_context: HandContext) -> None:
        if len(hand_context.initial_stacks) != config.num_players:
            raise ValueError(
                f"initial_stacks length ({len(hand_context.initial_stacks)}) != "
                f"num_players ({config.num_players})"
            )

        self._config: SessionConfig = config
        self._ctx: HandContext = hand_context
        self._deck_order: list[Card] = build_deterministic_deck(hand_context.deck_seed)
        self._deck_cursor: int = 0

        self._sb_seat: int = (hand_context.button_seat + 1) % config.num_players
        self._bb_seat: int = (hand_context.button_seat + 2) % config.num_players

        blinds: list[int] = [0] * config.num_players
        blinds[self._sb_seat] = config.sb
        blinds[self._bb_seat] = config.bb

        self._state: State = NoLimitTexasHoldem.create_state(
            automations=_AUTOMATIONS,
            ante_trimming_status=True,
            raw_antes=(0,) * config.num_players,
            raw_blinds_or_straddles=tuple(blinds),
            min_bet=config.bb,
            raw_starting_stacks=hand_context.initial_stacks,
            player_count=config.num_players,
        )

    # ---------- read-only accessors ----------
    @property
    def num_players(self) -> int:
        return self._config.num_players

    @property
    def button_seat(self) -> int:
        return self._ctx.button_seat

    @property
    def sb_seat(self) -> int:
        return self._sb_seat

    @property
    def bb_seat(self) -> int:
        return self._bb_seat

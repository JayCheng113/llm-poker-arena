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

from llm_poker_arena.engine._internal.deck import build_deterministic_deck, card_to_str
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.types import Street

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

        # PP-01/§3.1: manual deterministic deal because HOLE_DEALING automation is OFF.
        self._deal_hole_cards_deterministic()

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

    # ---------- card movement (deterministic) ----------
    def _next_card(self) -> Card:
        card = self._deck_order[self._deck_cursor]
        self._deck_cursor += 1
        return card

    def _deal_hole_cards_deterministic(self) -> None:
        n = self._config.num_players
        for _round in range(2):
            for offset in range(n):
                seat = (self._sb_seat + offset) % n
                # PokerKit's hole_dealee_index always starts at 0; pass player_index
                # explicitly so cards rotate from SB clockwise per spec §3.1.
                self._state.deal_hole((self._next_card(),), player_index=seat)

    def hole_cards(self) -> dict[int, tuple[str, str]]:
        """Return current hole cards as {seat: (card0_str, card1_str)} in deal order."""
        out: dict[int, tuple[str, str]] = {}
        for seat, cards in enumerate(self._state.hole_cards):
            if cards is None or len(cards) == 0:
                continue
            assert len(cards) == 2, f"seat {seat} has {len(cards)} hole cards"
            out[seat] = (card_to_str(cards[0]), card_to_str(cards[1]))
        return out

    def deal_community(self, street: Street) -> None:
        """Burn one card, then deal the appropriate number of community cards.

        PP-01: CARD_BURNING / BOARD_DEALING automations are OFF; all card
        movement flows through the seeded deck. PokerKit's UserWarning for
        "not recommended" cards fires only on genuine duplicates — we
        intentionally do NOT suppress it so deck-logic regressions surface.
        """
        count = {Street.FLOP: 3, Street.TURN: 1, Street.RIVER: 1}[street]
        self._state.burn_card(self._next_card())
        cards = tuple(self._next_card() for _ in range(count))
        self._state.deal_board(cards)

    def community(self) -> list[str]:
        """Current community cards as 2-char string tokens (flat, ordered)."""
        return [card_to_str(c) for c in self._state.get_board_cards(0)]

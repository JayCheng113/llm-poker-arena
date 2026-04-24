"""Project-wide public type aliases and enums used by DTOs and outer layers.

Cards in public surfaces are 2-character strings: rank ∈ "23456789TJQKA",
suit ∈ "cdhs". Examples: "As", "Td", "2c".

PokerKit's own Card type is confined to `engine/_internal/`; do not import it
outside that package.
"""
from __future__ import annotations

from enum import Enum
from typing import TypeAlias

SeatId: TypeAlias = int
Chips: TypeAlias = int
CardStr: TypeAlias = str  # exactly 2 chars, rank + suit


class Street(str, Enum):  # noqa: UP042  # keep str+Enum on py311; StrEnum is py311+ but plan requires str,Enum form
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"


RANKS: tuple[str, ...] = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")
SUITS: tuple[str, ...] = ("c", "d", "h", "s")


def is_valid_card_str(s: str) -> bool:
    """True iff s is exactly a valid 2-char card representation."""
    return len(s) == 2 and s[0] in RANKS and s[1] in SUITS

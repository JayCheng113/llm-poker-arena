"""Deterministic 52-card deck generator used by CanonicalState.

Produces a stable permutation of the 52 standard cards given a single integer
seed. We rely only on Python's stdlib `random.Random` to keep behavior
reproducible across Python minor versions; do not swap for `secrets` or
NumPy RNG without updating reproducibility guarantees (§11.1).

PokerKit's `Card` class is confined to this `_internal/` package; outer code
should consume only the 2-char string form via `card_to_str`.
"""

from __future__ import annotations

import random
from functools import lru_cache

from pokerkit import Card

from llm_poker_arena.engine.types import RANKS, SUITS, CardStr


def build_deterministic_deck(deck_seed: int) -> list[Card]:
    """Return a shuffled 52-card deck deterministically seeded by `deck_seed`."""
    base = _all_52_cards()
    rng = random.Random(deck_seed)
    shuffled = list(base)
    rng.shuffle(shuffled)
    return shuffled


def card_to_str(card: Card) -> CardStr:
    """Canonical 2-char rank+suit token (e.g. 'As', 'Td', '2c').

    PokerKit 0.7.3: `repr(card)` is the compact 2-char form
    ('As'); `str(card)` is the verbose form ('ACE OF SPADES (As)').
    """
    s = repr(card)
    if len(s) != 2 or s[0] not in RANKS or s[1] not in SUITS:
        raise RuntimeError(f"Unexpected Card repr form from pokerkit: {s!r}")
    return s


@lru_cache(maxsize=1)
def full_52_card_str_set() -> frozenset[CardStr]:
    return frozenset(f"{r}{s}" for r in RANKS for s in SUITS)


@lru_cache(maxsize=1)
def _all_52_cards() -> tuple[Card, ...]:
    cards: list[Card] = []
    for r in RANKS:
        for s in SUITS:
            cards.append(_make_card(f"{r}{s}"))
    return tuple(cards)


def _make_card(token: str) -> Card:
    """Construct a single PokerKit `Card` from our 2-char token.

    PokerKit 0.7.3: `Card.parse(text)` returns a generator of Cards.
    """
    return next(Card.parse(token))

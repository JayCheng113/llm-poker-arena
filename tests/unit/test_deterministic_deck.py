"""Tests for the deterministic deck used by CanonicalState."""
from __future__ import annotations

from llm_poker_arena.engine._internal.deck import (
    build_deterministic_deck,
    card_to_str,
    full_52_card_str_set,
)


def test_deck_is_length_52() -> None:
    deck = build_deterministic_deck(42)
    assert len(deck) == 52


def test_deck_contains_all_52_cards_no_dup() -> None:
    deck = build_deterministic_deck(42)
    strs = {card_to_str(c) for c in deck}
    assert strs == full_52_card_str_set()


def test_same_seed_same_order() -> None:
    a = [card_to_str(c) for c in build_deterministic_deck(42)]
    b = [card_to_str(c) for c in build_deterministic_deck(42)]
    assert a == b


def test_different_seeds_different_order() -> None:
    a = [card_to_str(c) for c in build_deterministic_deck(42)]
    b = [card_to_str(c) for c in build_deterministic_deck(43)]
    assert a != b


def test_card_to_str_format_is_two_chars() -> None:
    deck = build_deterministic_deck(0)
    for c in deck:
        s = card_to_str(c)
        assert len(s) == 2
        assert s[0] in "23456789TJQKA"
        assert s[1] in "cdhs"

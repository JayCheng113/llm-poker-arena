"""Unit tests for engine.types aliases and enums."""
from __future__ import annotations

from llm_poker_arena.engine.types import Street


def test_street_enum_order_preflop_to_river() -> None:
    ordered = [Street.PREFLOP, Street.FLOP, Street.TURN, Street.RIVER]
    assert [s.value for s in ordered] == ["preflop", "flop", "turn", "river"]


def test_street_from_string_round_trip() -> None:
    for name in ("preflop", "flop", "turn", "river"):
        assert Street(name).value == name


def test_street_rejects_unknown_name() -> None:
    import pytest

    with pytest.raises(ValueError, match="not a valid Street"):
        Street("showdown")


def test_is_valid_card_str_accepts_canonical() -> None:
    from llm_poker_arena.engine.types import is_valid_card_str

    assert is_valid_card_str("As")
    assert is_valid_card_str("Td")
    assert is_valid_card_str("2c")


def test_is_valid_card_str_rejects_bad() -> None:
    from llm_poker_arena.engine.types import is_valid_card_str

    for bad in ["", "A", "AAA", "Ax", "1s", "AS", "as", "ah kh"]:
        assert not is_valid_card_str(bad), f"should reject {bad!r}"

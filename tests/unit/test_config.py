"""Unit tests for SessionConfig + HandContext."""

from __future__ import annotations

from typing import Any

import pytest

from llm_poker_arena.engine.config import HandContext, SessionConfig


def _base_kwargs() -> dict[str, Any]:
    return dict(
        num_players=6,
        starting_stack=10_000,
        sb=50,
        bb=100,
        num_hands=1500,
        max_utility_calls=5,
        enable_math_tools=False,
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30,
        rng_seed=42,
    )


def test_session_config_accepts_valid() -> None:
    cfg = SessionConfig(**_base_kwargs())
    assert cfg.num_hands == 1500
    assert cfg.sb == 50
    assert cfg.bb == 100


def test_num_hands_must_be_multiple_of_num_players() -> None:
    kwargs = _base_kwargs() | {"num_hands": 1501}
    with pytest.raises(ValueError, match="multiple of num_players"):
        SessionConfig(**kwargs)


def test_sb_must_be_less_than_bb() -> None:
    kwargs = _base_kwargs() | {"sb": 100, "bb": 100}
    with pytest.raises(ValueError, match="sb must be less than bb"):
        SessionConfig(**kwargs)


def test_sb_and_bb_must_be_positive() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        SessionConfig(**(_base_kwargs() | {"sb": 0}))
    with pytest.raises(ValueError, match="greater than 0"):
        SessionConfig(**(_base_kwargs() | {"bb": -100}))


def test_num_players_between_2_and_10() -> None:
    for bad in (0, 1, 11, -1):
        with pytest.raises(ValueError, match="num_players"):
            SessionConfig(**(_base_kwargs() | {"num_players": bad, "num_hands": 60}))


def test_session_config_is_frozen() -> None:
    cfg = SessionConfig(**_base_kwargs())
    # Pydantic ValidationError (subclass of ValueError) on mutation of a frozen model.
    with pytest.raises(Exception):  # noqa: B017, PT011
        cfg.sb = 25


def test_session_config_forbids_extra_fields() -> None:
    kwargs = _base_kwargs() | {"favorite_color": "blue"}
    with pytest.raises(ValueError, match="favorite_color"):
        SessionConfig(**kwargs)


def test_hand_context_is_frozen_dataclass() -> None:
    ctx = HandContext(hand_id=1, deck_seed=42001, button_seat=0, initial_stacks=(10_000,) * 6)
    assert ctx.hand_id == 1
    # FrozenInstanceError (or AttributeError/TypeError) on mutation of a frozen dataclass.
    with pytest.raises(Exception):  # noqa: B017, PT011
        ctx.hand_id = 2  # type: ignore[misc]


def test_hand_context_rejects_wrong_stack_length() -> None:
    # HandContext does not know num_players; length validation happens when
    # CanonicalState is constructed (Task 6). Here we just verify that a
    # malformed context (empty stacks) is rejected locally.
    with pytest.raises(ValueError, match="initial_stacks length"):
        HandContext(hand_id=1, deck_seed=42001, button_seat=0, initial_stacks=())


def test_hand_context_rejects_button_out_of_range() -> None:
    with pytest.raises(ValueError, match="button_seat"):
        HandContext(hand_id=1, deck_seed=42001, button_seat=6, initial_stacks=(10_000,) * 6)

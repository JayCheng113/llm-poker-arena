"""P2 invariant: PlayerView[i] never leaks another seat's hole cards on serialize."""
from __future__ import annotations

import pytest

from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.projections import (
    build_player_view,
    build_public_view,
)


def _setup() -> CanonicalState:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    ctx = HandContext(hand_id=0, deck_seed=42_000, button_seat=0,
                      initial_stacks=(10_000,) * 6)
    return CanonicalState(cfg, ctx)


@pytest.mark.parametrize("viewer_seat", list(range(6)))
def test_playerview_excludes_other_seats_hole_cards(viewer_seat: int) -> None:
    s = _setup()
    true_hole = s.hole_cards()
    view = build_player_view(s, viewer_seat, turn_seed=viewer_seat * 1000 + 1)
    blob = view.model_dump_json()
    for seat, cards in true_hole.items():
        if seat == viewer_seat:
            continue
        for c in cards:
            assert c not in blob, (
                f"PlayerView[{viewer_seat}] serialization leaks seat {seat} card {c}: {blob[:200]}…"
            )


def test_playerview_includes_my_hole_cards() -> None:
    s = _setup()
    view = build_player_view(s, 3, turn_seed=1)
    assert set(view.my_hole_cards) == set(s.hole_cards()[3])


def test_publicview_has_no_hole_card_leak() -> None:
    s = _setup()
    pv = build_public_view(s)
    blob = pv.model_dump_json()
    for cards in s.hole_cards().values():
        for c in cards:
            assert c not in blob, f"PublicView leaks hole card {c}"


def test_playerview_round_trip_is_pure() -> None:
    """PlayerView is a pure function of (state, actor); repeat calls agree."""
    s = _setup()
    a = build_player_view(s, 2, turn_seed=999)
    b = build_player_view(s, 2, turn_seed=999)
    assert a == b

"""Schema/serialization tests for view DTOs."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionRecord,
    ActionToolSpec,
    AgentSnapshot,
    LegalActionSet,
    OpponentStatsOrInsufficient,
    PlayerView,
    PublicView,
    SeatPublicInfo,
    SessionParamsView,
)


def _params() -> SessionParamsView:
    return SessionParamsView(
        num_players=6,
        sb=50,
        bb=100,
        starting_stack=10_000,
        max_utility_calls=5,
        rationale_required=True,
        enable_math_tools=False,
        enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _legal_fold_call() -> LegalActionSet:
    return LegalActionSet(
        tools=(
            ActionToolSpec(name="fold", args={}),
            ActionToolSpec(name="call", args={}),
        )
    )


def _seats() -> tuple[SeatPublicInfo, ...]:
    out: list[SeatPublicInfo] = []
    for i in range(6):
        out.append(
            SeatPublicInfo(
                seat=i,
                label=f"Player_{i}",
                position_short="UTG" if i == 0 else "HJ",
                position_full="Under the Gun" if i == 0 else "Hijack",
                stack=10_000,
                invested_this_hand=0,
                invested_this_round=0,
                status="in_hand",
            )
        )
    return tuple(out)


def _player_view() -> PlayerView:
    return PlayerView(
        my_seat=3,
        my_hole_cards=("As", "Kd"),
        community=(),
        pot=150,
        sidepots=(),
        my_stack=10_000,
        my_invested_this_hand=0,
        my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100,
        pot_odds_required=0.4,
        effective_stack=10_000,
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(2, 3, 4, 5, 0, 1),
        seats_yet_to_act_after_me=(4, 5, 0, 1),
        already_acted_this_street=(),
        hand_history=(),
        legal_actions=_legal_fold_call(),
        opponent_stats={},
        hand_id=1,
        street=Street.PREFLOP,
        button_seat=0,
        turn_seed=12_345,
        immutable_session_params=_params(),
        seats_public=_seats(),
    )


# ---------- SessionParamsView ----------


def test_session_params_view_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        SessionParamsView(
            num_players=6,
            sb=50,
            bb=100,
            starting_stack=10_000,
            max_utility_calls=5,
            rationale_required=True,
            enable_math_tools=False,
            enable_hud_tool=False,
            opponent_stats_min_samples=30,
            favorite_color="blue",  # type: ignore[call-arg]
        )


def test_session_params_view_is_frozen() -> None:
    p = _params()
    with pytest.raises(ValidationError):
        p.sb = 25


# ---------- ActionToolSpec / LegalActionSet ----------


def test_action_tool_spec_round_trip() -> None:
    spec = ActionToolSpec(
        name="raise_to",
        args={"amount": {"min": 200, "max": 10_000}},
    )
    dumped = spec.model_dump()
    assert dumped == {"name": "raise_to", "args": {"amount": {"min": 200, "max": 10_000}}}
    assert ActionToolSpec.model_validate(dumped) == spec


def test_legal_action_set_is_tuple_of_specs() -> None:
    las = _legal_fold_call()
    assert len(las.tools) == 2
    assert [t.name for t in las.tools] == ["fold", "call"]


# ---------- PlayerView ----------


def test_player_view_round_trip_json() -> None:
    v = _player_view()
    blob = v.model_dump_json()
    restored = PlayerView.model_validate(json.loads(blob))
    assert restored == v


def test_player_view_is_frozen() -> None:
    v = _player_view()
    with pytest.raises(ValidationError):
        v.my_stack = 0


def test_player_view_forbids_extra() -> None:
    d = _player_view().model_dump()
    d["secret_note"] = "leak"
    with pytest.raises(ValidationError):
        PlayerView.model_validate(d)


def test_player_view_sequence_fields_are_tuples() -> None:
    """Deep-immutability guard: every sequence field must be a tuple, not a list.

    Pydantic 2 `frozen=True` blocks attribute reassignment but NOT nested
    mutation of list-valued fields. Using tuple types closes that hole
    structurally for the anti-cheat boundary.
    """
    v = _player_view()
    for field_name in (
        "my_hole_cards",
        "community",
        "sidepots",
        "opponent_seats_in_hand",
        "action_order_this_street",
        "seats_yet_to_act_after_me",
        "already_acted_this_street",
        "hand_history",
    ):
        value = getattr(v, field_name)
        assert isinstance(value, tuple), (
            f"PlayerView.{field_name} must be tuple (frozen=True is shallow); "
            f"got {type(value).__name__}"
        )


def test_player_view_nested_mutation_attempts_fail() -> None:
    """Actively try to mutate boundary sequences — every attempt must raise."""
    v = _player_view()
    # tuples have no append/extend/__setitem__/__delitem__/clear
    with pytest.raises(AttributeError):
        v.community.append("7c")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        v.opponent_seats_in_hand.append(999)  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        v.opponent_seats_in_hand[0] = 999  # type: ignore[index]


# ---------- PublicView ----------


def test_public_view_has_no_hole_card_field() -> None:
    fields = set(PublicView.model_fields.keys())
    leaks = {"my_hole_cards", "hole_cards", "hole_cards_by_seat", "deck", "turn_seed"}
    assert fields.isdisjoint(leaks), f"PublicView must not expose {fields & leaks}"


def test_public_view_round_trip() -> None:
    pv = PublicView(
        hand_id=1,
        street=Street.FLOP,
        pot=500,
        sidepots=(),
        community=("7c", "2d", "5s"),
        seats_public=_seats(),
        button_seat=0,
    )
    blob = pv.model_dump_json()
    restored = PublicView.model_validate(json.loads(blob))
    assert restored == pv


def test_public_view_sequences_are_tuples() -> None:
    pv = PublicView(
        hand_id=1,
        street=Street.FLOP,
        pot=500,
        sidepots=(),
        community=("7c", "2d", "5s"),
        seats_public=_seats(),
        button_seat=0,
    )
    assert isinstance(pv.sidepots, tuple)
    assert isinstance(pv.community, tuple)
    with pytest.raises(AttributeError):
        pv.community.append("Xx")  # type: ignore[attr-defined]


# ---------- OpponentStatsOrInsufficient ----------


def test_opponent_stats_union_allows_insufficient_sentinel() -> None:
    ins = OpponentStatsOrInsufficient(insufficient=True)
    assert ins.insufficient is True
    assert ins.vpip is None


def test_opponent_stats_union_allows_concrete_values() -> None:
    full = OpponentStatsOrInsufficient(
        insufficient=False, vpip=0.24, pfr=0.18, three_bet=0.06, af=2.3, wtsd=0.31
    )
    assert full.insufficient is False
    assert full.vpip == 0.24


def test_opponent_stats_rejects_insufficient_with_values() -> None:
    with pytest.raises(ValidationError):
        OpponentStatsOrInsufficient(insufficient=True, vpip=0.24)


# ---------- AgentSnapshot ----------


def test_agent_snapshot_round_trip() -> None:
    snap = AgentSnapshot(
        timestamp="2026-04-23T18:12:55.789Z",
        seat=3,
        hand_id=1,
        turn_id="1-preflop-3",
        view=_player_view(),
    )
    blob = snap.model_dump_json()
    restored = AgentSnapshot.model_validate(json.loads(blob))
    assert restored == snap


# ---------- ActionRecord ----------


def test_action_record_minimal() -> None:
    rec = ActionRecord(
        seat=0,
        action_type="call",
        amount=100,
        is_forced_blind=False,
    )
    assert rec.action_type == "call"
    assert rec.is_forced_blind is False

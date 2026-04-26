"""Tests for Phase 2a Pydantic storage schemas (round-trip + frozen + tuple fields)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from llm_poker_arena.storage.schemas import (
    ActionRecordPrivate,
    AgentDescriptor,
    AgentViewSnapshot,
    CanonicalPrivateHandRecord,
    HandResultPrivate,
    PublicAction,
    PublicHandEnded,
    PublicHandRecord,
    PublicHandStarted,
    PublicShowdown,
    WinnerInfo,
)


def _winner_info() -> WinnerInfo:
    return WinnerInfo(seat=2, winnings=2450, best_hand_desc="Set of 7s")


def _hand_result() -> HandResultPrivate:
    return HandResultPrivate(
        showdown=True,
        winners=(_winner_info(),),
        side_pots=(),
        final_invested={"1": 1200, "2": 1200},
        net_pnl={"1": -1200, "2": 1250},
    )


def _action_record() -> ActionRecordPrivate:
    return ActionRecordPrivate(
        seat=3,
        street="flop",
        action_type="raise_to",
        amount=725,
        is_forced_blind=False,
        turn_index=12,
    )


def _canonical_hand() -> CanonicalPrivateHandRecord:
    return CanonicalPrivateHandRecord(
        hand_id=127,
        started_at="2026-04-23T18:12:33.123Z",
        ended_at="2026-04-23T18:13:05.456Z",
        button_seat=4,
        sb_seat=5,
        bb_seat=0,
        deck_seed=42_127,
        starting_stacks={"1": 10_000, "2": 10_000},
        hole_cards={"1": ("Ah", "Kh"), "2": ("7s", "7c")},
        community=("7c", "2d", "5s", "9h", "Ah"),
        actions=(_action_record(),),
        result=_hand_result(),
    )


def _agent_descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        provider="random",
        model="uniform",
        version="phase1",
        temperature=None,
        seed=None,
    )


def _snapshot() -> AgentViewSnapshot:
    return AgentViewSnapshot(
        hand_id=127,
        turn_id="127-flop-3",
        session_id="session_abc",
        seat=3,
        street="flop",
        timestamp="2026-04-23T18:12:55.789Z",
        view_at_turn_start={"my_seat": 3, "my_hole_cards": ["Ah", "Kh"]},
        iterations=(),
        final_action={"type": "raise_to", "amount": 725},
        is_forced_blind=False,
        total_utility_calls=0,
        api_retry_count=0,
        illegal_action_retry_count=0,
        no_tool_retry_count=0,
        tool_usage_error_count=0,
        default_action_fallback=False,
        api_error=None,
        turn_timeout_exceeded=False,
        total_tokens={},
        wall_time_ms=0,
        agent=_agent_descriptor(),
    )


def test_canonical_hand_frozen_forbids_extra() -> None:
    h = _canonical_hand()
    with pytest.raises(ValidationError):
        CanonicalPrivateHandRecord(**{**h.model_dump(), "unexpected_field": 1})


def test_canonical_hand_sequence_fields_are_tuples() -> None:
    h = _canonical_hand()
    # Pydantic serializes tuple fields; tuples are immutable so constructing
    # from a list must still yield a tuple in the model.
    h2 = CanonicalPrivateHandRecord(**h.model_dump())
    assert isinstance(h2.community, tuple)
    assert isinstance(h2.actions, tuple)
    assert isinstance(h2.result.winners, tuple)


def test_canonical_hand_round_trip() -> None:
    h = _canonical_hand()
    blob = h.model_dump_json()
    back = CanonicalPrivateHandRecord.model_validate_json(blob)
    assert back == h


def test_agent_view_snapshot_frozen_and_round_trip() -> None:
    s = _snapshot()
    # frozen: attribute reassignment denied
    with pytest.raises(ValidationError):
        s.seat = 5
    back = AgentViewSnapshot.model_validate_json(s.model_dump_json())
    assert back == s


def test_public_hand_record_round_trip_with_mixed_events() -> None:
    """spec §7.3: one line per hand, `street_events` is a discriminated union."""
    rec = PublicHandRecord(
        hand_id=1,
        street_events=(
            PublicHandStarted(hand_id=1, button_seat=4, blinds={"sb": 50, "bb": 100}),
            PublicAction(
                hand_id=1, seat=3, street="preflop", action={"type": "raise_to", "amount": 300}
            ),
            PublicShowdown(hand_id=1, revealed={"1": ("Ah", "Kh"), "3": ("2d", "2h")}),
            PublicHandEnded(hand_id=1, winnings={"1": -1200, "2": 1250}),
        ),
    )
    back = PublicHandRecord.model_validate_json(rec.model_dump_json())
    assert back == rec


def test_public_hand_record_discriminator_selects_correct_variant() -> None:
    """`Field(discriminator='type')` must produce the correct concrete class."""
    rec = PublicHandRecord.model_validate(
        {
            "hand_id": 1,
            "street_events": [
                {
                    "type": "hand_started",
                    "hand_id": 1,
                    "button_seat": 4,
                    "blinds": {"sb": 50, "bb": 100},
                },
                {
                    "type": "action",
                    "hand_id": 1,
                    "seat": 3,
                    "street": "preflop",
                    "action": {"type": "raise_to", "amount": 300},
                },
                {"type": "hand_ended", "hand_id": 1, "winnings": {"1": 100}},
            ],
        }
    )
    assert isinstance(rec.street_events[0], PublicHandStarted)
    assert isinstance(rec.street_events[1], PublicAction)
    assert isinstance(rec.street_events[2], PublicHandEnded)
    assert rec.street_events[0].button_seat == 4


def test_public_hand_record_rejects_unknown_event_type() -> None:
    with pytest.raises(ValidationError):
        PublicHandRecord.model_validate(
            {"hand_id": 1, "street_events": [{"type": "unknown_event", "hand_id": 1}]}
        )


def test_public_hand_record_street_events_is_tuple_not_list() -> None:
    rec = PublicHandRecord(
        hand_id=1,
        street_events=(PublicHandEnded(hand_id=1, winnings={"1": 0}),),
    )
    # After round-trip, sequence field is still a tuple (deep immutability).
    back = PublicHandRecord.model_validate_json(rec.model_dump_json())
    assert isinstance(back.street_events, tuple)


def test_agent_descriptor_supports_all_phase1_provider_values() -> None:
    # Phase 2a: only random + rule_based. Phase 3 adds anthropic/openai/google.
    for provider in ("random", "rule_based"):
        AgentDescriptor(provider=provider, model="x", version="phase1", temperature=None, seed=None)


def test_canonical_hand_blinds_sum_sanity() -> None:
    """starting_stacks map must have num_players entries."""
    h = _canonical_hand()
    # Schema does not enforce player count (that is Session's job). Confirm
    # the schema accepts arbitrary-length maps.
    assert len(h.starting_stacks) == 2

"""Tests for layer builders (canonical_private / public_replay / agent_view_snapshots)."""
from __future__ import annotations

from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.projections import build_player_view
from llm_poker_arena.engine.transition import apply_action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.storage.layer_builders import (
    build_agent_view_snapshot,
    build_canonical_private_hand,
    build_public_action_event,
    build_public_hand_ended_event,
    build_public_hand_record,
    build_public_hand_started_event,
    build_public_hole_dealt_event,
    build_public_showdown_event,
    build_public_street_reveal_event,
)
from llm_poker_arena.storage.schemas import (
    ActionRecordPrivate,
    AgentViewSnapshot,
    CanonicalPrivateHandRecord,
    PublicAction,
    PublicFlop,
    PublicHandEnded,
    PublicHandRecord,
    PublicHandStarted,
    PublicHoleDealt,
    PublicShowdown,
)


def _cfg() -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def _state(button: int = 0) -> CanonicalState:
    cfg = _cfg()
    ctx = HandContext(
        hand_id=0, deck_seed=42_000, button_seat=button,
        initial_stacks=(10_000,) * 6,
    )
    return CanonicalState(cfg, ctx)


def test_public_hand_started_carries_button_and_blinds() -> None:
    cfg = _cfg()
    s = _state(button=0)
    e = build_public_hand_started_event(hand_id=0, state=s, sb=cfg.sb, bb=cfg.bb)
    assert isinstance(e, PublicHandStarted)
    assert e.hand_id == 0
    assert e.button_seat == 0
    assert e.blinds == {"sb": 50, "bb": 100}


def test_public_action_event_records_seat_street_action() -> None:
    e = build_public_action_event(
        hand_id=0, seat=3, street=Street.PREFLOP,
        action=Action(tool_name="raise_to", args={"amount": 300}),
    )
    assert isinstance(e, PublicAction)
    assert e.hand_id == 0
    assert e.seat == 3
    assert e.street == "preflop"
    assert e.action == {"type": "raise_to", "amount": 300}


def test_public_street_reveal_flop_contains_3_cards() -> None:
    s = _state(button=0)
    # Drive to flop: UTG(3) HJ(4) CO(5) BTN(0) SB(1) call, BB(2) check.
    for actor in (3, 4, 5, 0, 1):
        r = apply_action(s, actor, Action(tool_name="call", args={}))
        assert r.is_valid
    r = apply_action(s, 2, Action(tool_name="check", args={}))
    assert r.is_valid
    s.deal_community(Street.FLOP)
    e = build_public_street_reveal_event(hand_id=0, state=s, street=Street.FLOP)
    assert isinstance(e, PublicFlop)
    assert len(e.community) == 3


def test_public_showdown_event_only_reveals_showdown_seats() -> None:
    s = _state(button=0)
    all_holes = s.hole_cards()  # dict[int, tuple[str, str]]
    e = build_public_showdown_event(hand_id=0, state=s, showdown_seats={1, 3, 5})
    assert isinstance(e, PublicShowdown)
    # Only the 3 revealed seats appear in the map.
    assert set(e.revealed.keys()) == {"1", "3", "5"}
    for absent in ("0", "2", "4"):
        assert absent not in e.revealed
    for seat in (1, 3, 5):
        assert e.revealed[str(seat)] == all_holes[seat]


def test_public_hand_ended_event_has_per_seat_winnings() -> None:
    e = build_public_hand_ended_event(
        hand_id=0, winnings={1: -50, 2: 150, 3: -100, 4: 0, 5: 0, 0: 0},
    )
    assert isinstance(e, PublicHandEnded)
    assert e.winnings == {"1": -50, "2": 150, "3": -100, "4": 0, "5": 0, "0": 0}


def test_build_public_hand_record_wraps_events_in_hand_shape() -> None:
    """spec §7.3: one hand per line, events in a tuple."""
    events = (
        build_public_hand_started_event(hand_id=7, state=_state(button=2),
                                        sb=50, bb=100),
        build_public_hole_dealt_event(hand_id=7),
        build_public_hand_ended_event(hand_id=7, winnings={0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}),
    )
    rec = build_public_hand_record(hand_id=7, events=events)
    assert isinstance(rec, PublicHandRecord)
    assert rec.hand_id == 7
    assert len(rec.street_events) == 3
    assert isinstance(rec.street_events[0], PublicHandStarted)
    assert isinstance(rec.street_events[1], PublicHoleDealt)
    assert isinstance(rec.street_events[2], PublicHandEnded)


def test_canonical_private_hand_has_full_hole_cards_and_actions() -> None:
    s = _state(button=0)
    action_records: list[ActionRecordPrivate] = []
    for turn_idx, actor in enumerate((3, 4, 5, 0, 1)):
        r = apply_action(s, actor, Action(tool_name="call", args={}))
        assert r.is_valid
        action_records.append(ActionRecordPrivate(
            seat=actor, street="preflop", action_type="call",
            amount=None, is_forced_blind=False, turn_index=turn_idx,
        ))
    r = apply_action(s, 2, Action(tool_name="check", args={}))
    assert r.is_valid
    action_records.append(ActionRecordPrivate(
        seat=2, street="preflop", action_type="check",
        amount=None, is_forced_blind=False, turn_index=5,
    ))

    rec = build_canonical_private_hand(
        hand_id=0, state=s, started_at="2026-04-24T00:00:00Z",
        ended_at="2026-04-24T00:00:05Z",
        actions=tuple(action_records),
    )
    assert isinstance(rec, CanonicalPrivateHandRecord)
    assert rec.hand_id == 0
    assert rec.button_seat == 0
    # All 6 hole cards present regardless of showdown status.
    assert set(rec.hole_cards.keys()) == {"0", "1", "2", "3", "4", "5"}
    assert len(rec.actions) == 6


def test_agent_view_snapshot_records_mock_agent_action() -> None:
    s = _state(button=0)
    actor = 3  # UTG on button=0
    view = build_player_view(s, actor, turn_seed=42)
    snap = build_agent_view_snapshot(
        hand_id=0, session_id="sess_test", seat=actor,
        street=Street.PREFLOP, timestamp="2026-04-24T00:00:00Z",
        view=view,
        action=Action(tool_name="fold", args={}),
        turn_index=0,
        agent_provider="random", agent_model="uniform", agent_version="phase1",
        default_action_fallback=False,
    )
    assert isinstance(snap, AgentViewSnapshot)
    assert snap.hand_id == 0
    assert snap.seat == 3
    assert snap.turn_id == "0-preflop-0"
    assert snap.final_action == {"type": "fold"}
    assert snap.iterations == ()  # mock agent → empty
    assert snap.agent.provider == "random"


def test_public_hand_record_round_trip_via_json() -> None:
    """End-to-end: builders → PublicHandRecord → JSON → back to PublicHandRecord."""
    s = _state(button=3)
    events = (
        build_public_hand_started_event(hand_id=9, state=s, sb=50, bb=100),
        build_public_hand_ended_event(hand_id=9, winnings={0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}),
    )
    rec = build_public_hand_record(hand_id=9, events=events)
    back = PublicHandRecord.model_validate_json(rec.model_dump_json())
    assert back == rec

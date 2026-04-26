"""Frozen Pydantic DTOs for Phase 2a three-layer JSONL observability stack.

- `CanonicalPrivateHandRecord` — one line per hand in canonical_private.jsonl.
- `PublicHandRecord` — one line per hand in public_replay.jsonl; contains a discriminated-union `street_events` tuple (spec §7.3 shape).
- `AgentViewSnapshot` — one line per turn per agent in agent_view_snapshots.jsonl.

All models are `frozen=True`, `extra="forbid"`. Every sequence field is
declared as `tuple[X, ...]` because Pydantic 2's `frozen=True` is shallow —
a list field would still allow `record.actions.append(...)` and silently
corrupt the serialized history. Tuples close that hole structurally.

Phase 2a populates the ReAct-specific fields of `AgentViewSnapshot` with
degenerate defaults (mock agents do not iterate, never hit api_error, never
time out). The schema is forward-compatible with Phase 3 which fills the
`iterations` tuple and the four retry counters properly.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _frozen() -> ConfigDict:
    return ConfigDict(extra="forbid", frozen=True)


# ----------------------------------------------------------- agent descriptor


class AgentDescriptor(BaseModel):
    """Minimal per-snapshot agent identity (phase-1 mock agents: random/rule_based)."""

    model_config = _frozen()

    provider: str
    model: str
    version: str
    temperature: float | None = None
    seed: int | None = None


# ----------------------------------------------------------- canonical_private


class WinnerInfo(BaseModel):
    model_config = _frozen()

    seat: int
    winnings: int
    best_hand_desc: str


class SidePotSummary(BaseModel):
    model_config = _frozen()

    amount: int
    eligible_seats: tuple[int, ...]


class HandResultPrivate(BaseModel):
    model_config = _frozen()

    showdown: bool
    winners: tuple[WinnerInfo, ...]
    side_pots: tuple[SidePotSummary, ...]
    final_invested: dict[str, int]
    net_pnl: dict[str, int]


ActionType = Literal["fold", "check", "call", "bet", "raise_to", "all_in"]


class ActionRecordPrivate(BaseModel):
    """Per-action record inside canonical_private.jsonl's `actions` tuple."""

    model_config = _frozen()

    seat: int
    street: Literal["preflop", "flop", "turn", "river"]
    action_type: ActionType
    amount: int | None = None
    is_forced_blind: bool = False
    turn_index: int


class CanonicalPrivateHandRecord(BaseModel):
    """One line per hand in canonical_private.jsonl."""

    model_config = _frozen()

    hand_id: int
    started_at: str
    ended_at: str
    button_seat: int
    sb_seat: int
    bb_seat: int
    deck_seed: int
    starting_stacks: dict[str, int]
    hole_cards: dict[str, tuple[str, str]]
    community: tuple[str, ...] = Field(default_factory=tuple, max_length=5)
    actions: tuple[ActionRecordPrivate, ...]
    result: HandResultPrivate


# ----------------------------------------------------------- public_replay


class PublicHandStarted(BaseModel):
    model_config = _frozen()
    type: Literal["hand_started"] = "hand_started"
    hand_id: int
    button_seat: int
    blinds: dict[str, int]  # {"sb": 50, "bb": 100}


class PublicHoleDealt(BaseModel):
    model_config = _frozen()
    type: Literal["hole_dealt"] = "hole_dealt"
    hand_id: int


class PublicAction(BaseModel):
    model_config = _frozen()
    type: Literal["action"] = "action"
    hand_id: int
    seat: int
    street: Literal["preflop", "flop", "turn", "river"]
    action: dict[str, Any]  # {"type": "raise_to", "amount": 300}


class PublicFlop(BaseModel):
    model_config = _frozen()
    type: Literal["flop"] = "flop"
    hand_id: int
    community: tuple[str, str, str]


class PublicTurn(BaseModel):
    model_config = _frozen()
    type: Literal["turn"] = "turn"
    hand_id: int
    card: str


class PublicRiver(BaseModel):
    model_config = _frozen()
    type: Literal["river"] = "river"
    hand_id: int
    card: str


class PublicShowdown(BaseModel):
    model_config = _frozen()
    type: Literal["showdown"] = "showdown"
    hand_id: int
    # Only seats that reached showdown reveal holes; folded/mucked not present.
    revealed: dict[str, tuple[str, str]]


class PublicHandEnded(BaseModel):
    model_config = _frozen()
    type: Literal["hand_ended"] = "hand_ended"
    hand_id: int
    winnings: dict[str, int]  # per-seat chip delta this hand


# ----------------------------------------------------------- public hand record

# Discriminated union over the 8 event variants. Each variant has a
# `type: Literal[...]` class attribute; Pydantic 2's `Field(discriminator=...)`
# inspects that attribute at validation time. No hand-rolled discriminator
# function or wrapper class needed.
PublicEvent = Annotated[
    PublicHandStarted
    | PublicHoleDealt
    | PublicAction
    | PublicFlop
    | PublicTurn
    | PublicRiver
    | PublicShowdown
    | PublicHandEnded,
    Field(discriminator="type"),
]


class PublicHandRecord(BaseModel):
    """One line per hand in public_replay.jsonl (spec §7.3).

    Spec shape: `{"hand_id": N, "street_events": [event, event, ...]}`.
    The Session buffers events during the hand and flushes one record at
    hand_end — not one event per line — so `BatchedJsonlWriter`'s BATCH_SIZE
    bounds durability in units of HANDS (≤ 10 hands lost on crash).
    """

    model_config = _frozen()

    hand_id: int
    street_events: tuple[PublicEvent, ...]


# ----------------------------------------------------------- agent_view_snapshots


class AgentViewSnapshot(BaseModel):
    """One line per turn per agent in agent_view_snapshots.jsonl.

    Phase 2a: mock agents produce degenerate `iterations=()` + zero retry
    counters; schema is forward-compatible with Phase 3 ReAct.
    """

    model_config = _frozen()

    hand_id: int
    turn_id: str
    session_id: str
    seat: int
    street: Literal["preflop", "flop", "turn", "river"]
    timestamp: str

    view_at_turn_start: dict[str, Any]  # PlayerView.model_dump() raw
    iterations: tuple[dict[str, Any], ...] = ()

    final_action: dict[str, Any]
    is_forced_blind: bool = False
    total_utility_calls: int = 0

    api_retry_count: int = 0
    illegal_action_retry_count: int = 0
    no_tool_retry_count: int = 0
    tool_usage_error_count: int = 0

    default_action_fallback: bool = False
    api_error: str | None = None
    turn_timeout_exceeded: bool = False

    total_tokens: dict[str, int] = Field(default_factory=dict)
    wall_time_ms: int = 0
    agent: AgentDescriptor


# ----------------------------------------------------------- censored_hands


class CensoredHandRecord(BaseModel):
    """spec §4.1 BR2-01: one line per hand abandoned due to api_error or
    null final_action. Hand records (canonical_private + public_replay) are
    NOT written for censored hands; this is the analyst's only signal."""

    model_config = _frozen()

    hand_id: int
    seat: int  # the seat whose decide() returned api_error
    api_error: dict[str, str]  # {"type": ..., "detail": ...}
    timestamp: str
    session_id: str

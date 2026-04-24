"""Read-only Pydantic DTOs that cross the engine/agent trust boundary.

Every model in this file:
  - is frozen (immutable after construction);
  - forbids extra fields (explicit whitelist);
  - carries only data derivable from a PokerKit canonical state projection.

Callers see these DTOs (or serialized dicts); they never see CanonicalState.
"""
from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from llm_poker_arena.engine.types import CardStr, Chips, SeatId, Street


def _frozen() -> ConfigDict:
    return ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------- session

class SessionParamsView(BaseModel):
    """Read-only subset of SessionConfig that agents + tools may see."""

    model_config = _frozen()

    num_players: int
    sb: Chips
    bb: Chips
    starting_stack: Chips
    max_utility_calls: int
    rationale_required: bool
    enable_math_tools: bool
    enable_hud_tool: bool
    opponent_stats_min_samples: int


# --------------------------------------------------------------------- tools

class ActionToolSpec(BaseModel):
    """Legal action tool descriptor for a specific turn."""

    model_config = _frozen()

    name: Literal["fold", "check", "call", "bet", "raise_to", "all_in"]
    args: dict[str, Any]


class LegalActionSet(BaseModel):
    model_config = _frozen()

    tools: tuple[ActionToolSpec, ...]


# --------------------------------------------------------------------- seats

SeatStatus = Literal["in_hand", "folded", "all_in"]


class SeatPublicInfo(BaseModel):
    model_config = _frozen()

    seat: SeatId
    label: str
    position_short: str
    position_full: str
    stack: Chips
    invested_this_hand: Chips
    invested_this_round: Chips
    status: SeatStatus


# --------------------------------------------------------------------- history

class ActionRecord(BaseModel):
    """Canonical description of a committed action (post-apply)."""

    model_config = _frozen()

    seat: SeatId
    action_type: Literal["fold", "check", "call", "bet", "raise_to", "all_in"]
    amount: Chips | None = None
    is_forced_blind: bool = False


class StreetHistory(BaseModel):
    model_config = _frozen()

    street: Street
    board: tuple[CardStr, ...]
    pot_at_street_start: Chips
    actions: tuple[ActionRecord, ...]


class SidePotInfo(BaseModel):
    model_config = _frozen()

    amount: Chips
    eligible_seats: tuple[SeatId, ...]


# --------------------------------------------------------------------- stats

class OpponentStatsOrInsufficient(BaseModel):
    """Either an 'insufficient sample' sentinel or a full stats bundle.

    Represented as one model (not a Union) so the JSON shape is uniform across
    DuckDB queries. When insufficient=True all numeric fields must be None.
    """

    model_config = _frozen()

    insufficient: bool
    vpip: float | None = None
    pfr: float | None = None
    three_bet: float | None = None
    af: float | None = None
    wtsd: float | None = None

    @model_validator(mode="after")
    def _check_sentinel(self) -> Self:
        numeric = (self.vpip, self.pfr, self.three_bet, self.af, self.wtsd)
        if self.insufficient and any(v is not None for v in numeric):
            raise ValueError("insufficient=True forbids numeric stat fields")
        if not self.insufficient and any(v is None for v in numeric):
            raise ValueError("insufficient=False requires all numeric stat fields")
        return self


# --------------------------------------------------------------------- PlayerView

class PlayerView(BaseModel):
    """What seat `my_seat` is allowed to see.

    Never contains other seats' hole cards. Never contains the deck. Never
    contains the turn_seed of any seat but this one (and only where caller
    holds this view).
    """

    model_config = _frozen()

    my_seat: SeatId
    my_hole_cards: list[CardStr] = Field(min_length=2, max_length=2)
    community: list[CardStr] = Field(default_factory=list, max_length=5)
    pot: Chips
    sidepots: list[SidePotInfo]
    my_stack: Chips
    my_invested_this_hand: Chips
    my_invested_this_round: Chips
    current_bet_to_match: Chips
    seats_public: tuple[SeatPublicInfo, ...]
    opponent_seats_in_hand: list[SeatId]
    action_order_this_street: list[SeatId]
    already_acted_this_street: list[ActionRecord]
    hand_history: list[StreetHistory]
    legal_actions: LegalActionSet
    opponent_stats: dict[SeatId, OpponentStatsOrInsufficient]
    hand_id: int
    street: Street
    button_seat: SeatId
    turn_seed: int
    immutable_session_params: SessionParamsView


# --------------------------------------------------------------------- PublicView

class PublicView(BaseModel):
    """No hidden information; safe for spectator UI and open-dataset publish.

    Notably **absent**: my_hole_cards, hole_cards_by_seat, deck, turn_seed.
    """

    model_config = _frozen()

    hand_id: int
    street: Street
    pot: Chips
    sidepots: list[SidePotInfo]
    community: list[CardStr]
    seats_public: tuple[SeatPublicInfo, ...]
    button_seat: SeatId


# --------------------------------------------------------------------- AgentSnapshot

class AgentSnapshot(BaseModel):
    """Envelope written to agent_view_snapshots.jsonl (one per turn per seat)."""

    model_config = _frozen()

    timestamp: str
    seat: SeatId
    hand_id: int
    turn_id: str
    view: PlayerView

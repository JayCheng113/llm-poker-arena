"""Pure builders from CanonicalState + turn metadata to typed Pydantic records.

Each builder returns a concrete Pydantic model from `storage.schemas`. The
Session calls `model.model_dump(mode="json")` at write time. This way schema
validation fires at build time (close to where the data is shaped) and the
writer is schema-agnostic.

Spec §7.3 shape: `public_replay.jsonl` is ONE HAND PER LINE, with all events
for that hand in `street_events`. Per-event builders (`build_public_*_event`)
produce atomic events; `build_public_hand_record` wraps a tuple of events
into the top-level `PublicHandRecord` that Session flushes at hand_end.

Phase 2a note on blind-post records: spec §7.2 hand-example shows blind
posts in `actions`, but PokerKit's BLIND_OR_STRADDLE_POSTING automation
handles them without agent involvement, so the Session does not currently
emit ActionRecordPrivate for them. Phase 2b can synthesize blind-post
records from `state.operations` if VPIP/PFR SQL needs them; meanwhile
VPIP-relevant filtering uses `is_forced_blind` on agent snapshots, which is
always `False` (mock agents never post blinds).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from llm_poker_arena.agents.llm.types import IterationRecord, TokenCounts
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.storage.schemas import (
    ActionRecordPrivate,
    AgentDescriptor,
    AgentViewSnapshot,
    CanonicalPrivateHandRecord,
    CensoredHandRecord,
    HandResultPrivate,
    PublicAction,
    PublicEvent,
    PublicFlop,
    PublicHandEnded,
    PublicHandRecord,
    PublicHandStarted,
    PublicHoleDealt,
    PublicRiver,
    PublicShowdown,
    PublicTurn,
    SidePotSummary,
    WinnerInfo,
)


def build_public_hand_started_event(
    *, hand_id: int, state: Any, sb: int, bb: int,  # noqa: ANN401 — CanonicalState
) -> PublicHandStarted:
    return PublicHandStarted(
        hand_id=hand_id,
        button_seat=state.button_seat,
        blinds={"sb": sb, "bb": bb},
    )


def build_public_hole_dealt_event(*, hand_id: int) -> PublicHoleDealt:
    return PublicHoleDealt(hand_id=hand_id)


def build_public_action_event(
    *, hand_id: int, seat: int, street: Street, action: Action,
) -> PublicAction:
    body: dict[str, Any] = {"type": action.tool_name}
    if action.tool_name in ("bet", "raise_to"):
        amt = action.args.get("amount") if isinstance(action.args, dict) else None
        if amt is not None:
            body["amount"] = int(amt)
    return PublicAction(
        hand_id=hand_id,
        seat=seat,
        street=cast(Any, street.value),  # Literal["preflop", ...] — enum value is the literal
        action=body,
    )


def build_public_street_reveal_event(
    *, hand_id: int, state: Any, street: Street,  # noqa: ANN401
) -> PublicFlop | PublicTurn | PublicRiver:
    community = state.community()  # list[str]
    if street == Street.FLOP:
        cards = tuple(community[:3])
        return PublicFlop(hand_id=hand_id, community=cast(Any, cards))
    if street == Street.TURN:
        return PublicTurn(hand_id=hand_id, card=community[3])
    if street == Street.RIVER:
        return PublicRiver(hand_id=hand_id, card=community[4])
    raise ValueError(f"street {street!r} is not a board-reveal street")


def build_public_showdown_event(
    *, hand_id: int,
    showdown_seats: set[int],
    hole_cards: dict[int, tuple[str, str]],
) -> PublicShowdown:
    """Reveal hole cards for seats that reached showdown.

    Caller MUST pass `hole_cards` captured BEFORE `HAND_KILLING` automation
    mucks the loser's cards — typically a snapshot taken right after
    `CanonicalState` construction. Reading `state.hole_cards()` at hand-end
    would only see the winner (mucked losers have empty cards) and
    systematically under-reveal the showdown per spec §7.3.
    """
    revealed = {
        str(seat): hole_cards[seat]
        for seat in sorted(showdown_seats) if seat in hole_cards
    }
    return PublicShowdown(hand_id=hand_id, revealed=revealed)


def build_public_hand_ended_event(
    *, hand_id: int, winnings: dict[int, int],
) -> PublicHandEnded:
    return PublicHandEnded(
        hand_id=hand_id,
        winnings={str(seat): int(amt) for seat, amt in winnings.items()},
    )


def build_public_hand_record(
    *, hand_id: int, events: tuple[PublicEvent, ...],
) -> PublicHandRecord:
    """Wrap a tuple of atomic public events into the spec-§7.3 hand-per-line shape."""
    return PublicHandRecord(hand_id=hand_id, street_events=events)


def build_canonical_private_hand(
    *, hand_id: int, state: Any,  # noqa: ANN401
    started_at: str, ended_at: str,
    actions: tuple[ActionRecordPrivate, ...],
    hole_cards: dict[int, tuple[str, str]],
    winners: tuple[WinnerInfo, ...] = (),
    side_pots: tuple[SidePotSummary, ...] = (),
    final_invested: dict[int, int] | None = None,
    net_pnl: dict[int, int] | None = None,
    showdown: bool = False,
) -> CanonicalPrivateHandRecord:
    """Build the canonical_private.jsonl hand record.

    Phase 2a: `final_invested` defaults to `{}` — proper tracking deferred
    to Phase 2b (needs per-action contribution accumulation from
    `state.operations`). MVP 6 exit criterion does not depend on this field.

    `hole_cards` MUST be a pre-settlement snapshot (typically captured right
    after `CanonicalState` construction). PokerKit's `HAND_KILLING`
    automation moves folded/losing seats' cards to `mucked_cards`
    immediately; reading `state.hole_cards()` at hand-end would miss them
    and violate spec §7.2 ("all hole cards").
    """
    stacks_initial = dict(enumerate(state._ctx.initial_stacks))  # noqa: SLF001
    return CanonicalPrivateHandRecord(
        hand_id=hand_id,
        started_at=started_at, ended_at=ended_at,
        button_seat=state.button_seat,
        sb_seat=state.sb_seat, bb_seat=state.bb_seat,
        deck_seed=state._ctx.deck_seed,  # noqa: SLF001
        starting_stacks={str(s): int(v) for s, v in stacks_initial.items()},
        hole_cards={str(s): cards for s, cards in hole_cards.items()},
        community=tuple(state.community()),
        actions=actions,
        result=HandResultPrivate(
            showdown=showdown,
            winners=winners,
            side_pots=side_pots,
            final_invested={str(k): int(v) for k, v in (final_invested or {}).items()},
            net_pnl={str(k): int(v) for k, v in (net_pnl or {}).items()},
        ),
    )


def build_agent_view_snapshot(
    *, hand_id: int, session_id: str, seat: int, street: Street,
    timestamp: str, view: PlayerView, action: Action, turn_index: int,
    agent_provider: str, agent_model: str, agent_version: str,
    default_action_fallback: bool,
    iterations: tuple[IterationRecord, ...] = (),
    total_tokens: TokenCounts | Mapping[str, int] | None = None,
    wall_time_ms: int = 0,
    api_retry_count: int = 0,
    illegal_action_retry_count: int = 0,
    no_tool_retry_count: int = 0,
    tool_usage_error_count: int = 0,
) -> AgentViewSnapshot:
    final_action: dict[str, Any] = {"type": action.tool_name}
    if action.tool_name in ("bet", "raise_to"):
        amt = action.args.get("amount") if isinstance(action.args, dict) else None
        if amt is not None:
            final_action["amount"] = int(amt)

    iter_dump: tuple[dict[str, Any], ...] = tuple(
        cast("Any", ir).model_dump(mode="json") for ir in iterations
    )
    total_tokens_dict: dict[str, int]
    if total_tokens is None:
        total_tokens_dict = {}
    elif isinstance(total_tokens, TokenCounts):
        total_tokens_dict = cast("dict[str, int]",
                                 total_tokens.model_dump(mode="json"))
    else:
        total_tokens_dict = dict(total_tokens)

    return AgentViewSnapshot(
        hand_id=hand_id,
        turn_id=f"{hand_id}-{street.value}-{turn_index}",
        session_id=session_id,
        seat=seat,
        street=cast(Any, street.value),
        timestamp=timestamp,
        view_at_turn_start=view.model_dump(mode="json"),
        iterations=iter_dump,
        final_action=final_action,
        is_forced_blind=False,
        total_utility_calls=0,
        api_retry_count=api_retry_count,
        illegal_action_retry_count=illegal_action_retry_count,
        no_tool_retry_count=no_tool_retry_count,
        tool_usage_error_count=tool_usage_error_count,
        default_action_fallback=default_action_fallback,
        api_error=None,
        turn_timeout_exceeded=False,
        total_tokens=total_tokens_dict,
        wall_time_ms=wall_time_ms,
        agent=AgentDescriptor(
            provider=agent_provider,
            model=agent_model,
            version=agent_version,
            temperature=None,
            seed=None,
        ),
    )


def build_censored_hand_record(
    *, hand_id: int, seat: int, session_id: str,
    api_error: object,
    timestamp: str,
) -> CensoredHandRecord:
    """spec §4.1 BR2-01: build the censored_hands.jsonl record for a hand
    abandoned due to api_error or null final_action."""
    err_dict: dict[str, str]
    if api_error is None:
        err_dict = {
            "type": "NullFinalAction",
            "detail": "agent returned final_action=None without api_error",
        }
    elif hasattr(api_error, "model_dump"):
        err_dict = {
            "type": str(getattr(api_error, "type", "Unknown")),
            "detail": str(getattr(api_error, "detail", "")),
        }
    else:
        err_dict = {"type": "Unknown", "detail": str(api_error)}
    return CensoredHandRecord(
        hand_id=hand_id, seat=seat, session_id=session_id,
        api_error=err_dict, timestamp=timestamp,
    )

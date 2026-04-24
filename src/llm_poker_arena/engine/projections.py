"""Pure projections from CanonicalState into read-only view DTOs.

`build_player_view` scopes a CanonicalState to one seat's trust surface:
the returned `PlayerView` includes only the viewer's own hole cards, and
carries the viewer's turn_seed — nobody else's. This is the P2 invariant
enforced by `tests/unit/test_playerview_isolation.py`.

`build_public_view` produces a sanitized `PublicView` suitable for spectator
publish: no hole cards from any seat, no deck state, no per-seat turn_seed.

Both functions are pure: repeated calls with the same inputs produce equal
DTOs. Phase-1 stub fields (action_order_this_street, already_acted_this_street,
hand_history, my_invested_this_hand) are placeholders until street history
plumbing lands in a later task (Phase 2 / MVP 6-7).

All sequence fields are built as tuples to match `views.py`'s
deep-immutability convention.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from llm_poker_arena.engine.legal_actions import compute_legal_tool_set
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    PlayerView,
    PublicView,
    SeatPublicInfo,
    SeatStatus,
    SessionParamsView,
)

if TYPE_CHECKING:
    from llm_poker_arena.engine._internal.poker_state import CanonicalState


_POSITIONS_6MAX: tuple[tuple[str, str], ...] = (
    ("UTG", "Under the Gun"),
    ("HJ", "Hijack"),
    ("CO", "Cutoff"),
    ("BTN", "Button"),
    ("SB", "Small Blind"),
    ("BB", "Big Blind"),
)


def _session_params_view(state: CanonicalState) -> SessionParamsView:
    cfg = state._config  # noqa: SLF001
    return SessionParamsView(
        num_players=cfg.num_players,
        sb=cfg.sb,
        bb=cfg.bb,
        starting_stack=cfg.starting_stack,
        max_utility_calls=cfg.max_utility_calls,
        rationale_required=cfg.rationale_required,
        enable_math_tools=cfg.enable_math_tools,
        enable_hud_tool=cfg.enable_hud_tool,
        opponent_stats_min_samples=cfg.opponent_stats_min_samples,
    )


def _normalize_status(raw_status: object) -> SeatStatus:
    s = str(raw_status).lower()
    if "fold" in s:
        return "folded"
    if "all" in s:
        return "all_in"
    return "in_hand"


def _seats_public(state: CanonicalState) -> tuple[SeatPublicInfo, ...]:
    raw = state._state  # noqa: SLF001
    stacks = list(getattr(raw, "stacks", ()) or ())
    bets = list(getattr(raw, "bets", ()) or [0] * state.num_players)
    statuses = list(getattr(raw, "statuses", ()) or [])
    n = state.num_players
    out: list[SeatPublicInfo] = []
    for i in range(n):
        position_idx = (i - state.button_seat - 1) % n  # BTN-relative
        short, full = _POSITIONS_6MAX[position_idx] if n == 6 else (f"P{i}", f"Position {i}")
        status = _normalize_status(statuses[i] if i < len(statuses) else "in_hand")
        out.append(
            SeatPublicInfo(
                seat=i,
                label=f"Player_{i}",
                position_short=short,
                position_full=full,
                stack=int(stacks[i]) if i < len(stacks) else 0,
                invested_this_hand=0,  # Task 14+ will plumb real values
                invested_this_round=int(bets[i]) if i < len(bets) else 0,
                status=status,
            )
        )
    return tuple(out)


def _infer_street(state: CanonicalState) -> Street:
    board = state.community()
    n = len(board)
    if n == 0:
        return Street.PREFLOP
    if n == 3:
        return Street.FLOP
    if n == 4:
        return Street.TURN
    return Street.RIVER


def build_player_view(
    state: CanonicalState, actor: int, *, turn_seed: int
) -> PlayerView:
    """Project CanonicalState into a seat-scoped PlayerView DTO.

    P2 invariant: the returned DTO carries only `actor`'s hole cards and
    `actor`'s turn_seed; it never contains other seats' hole cards or other
    seats' turn_seed. Pure function of (state, actor, turn_seed).
    """
    raw = state._state  # noqa: SLF001
    my_hole = state.hole_cards().get(actor)
    if my_hole is None:
        raise ValueError(f"seat {actor} has no hole cards")

    seats = _seats_public(state)
    bets = list(getattr(raw, "bets", ()) or [0] * state.num_players)
    my_invested_round = int(bets[actor]) if actor < len(bets) else 0
    max_bet = max((int(b) for b in bets), default=0)

    opp_in_hand: list[int] = []
    for i, seat_info in enumerate(seats):
        if i != actor and seat_info.status != "folded":
            opp_in_hand.append(i)

    stacks = list(getattr(raw, "stacks", ()) or [0] * state.num_players)
    my_stack = int(stacks[actor]) if actor < len(stacks) else 0

    return PlayerView(
        my_seat=actor,
        my_hole_cards=my_hole,
        community=tuple(state.community()),
        pot=int(getattr(raw, "total_pot_amount", 0) or 0),
        sidepots=(),
        my_stack=my_stack,
        my_invested_this_hand=my_invested_round,  # Phase 2: refine when street history lands
        my_invested_this_round=my_invested_round,
        current_bet_to_match=max_bet,
        seats_public=seats,
        opponent_seats_in_hand=tuple(opp_in_hand),
        action_order_this_street=tuple(range(state.num_players)),  # placeholder
        already_acted_this_street=(),
        hand_history=(),
        legal_actions=compute_legal_tool_set(state, actor),
        opponent_stats={},
        hand_id=state._ctx.hand_id,  # noqa: SLF001
        street=_infer_street(state),
        button_seat=state.button_seat,
        turn_seed=turn_seed,
        immutable_session_params=_session_params_view(state),
    )


def build_public_view(state: CanonicalState) -> PublicView:
    """Project CanonicalState into a sanitized PublicView.

    No hole cards, no deck, no per-seat turn_seed: safe to publish.
    """
    raw = state._state  # noqa: SLF001
    return PublicView(
        hand_id=state._ctx.hand_id,  # noqa: SLF001
        street=_infer_street(state),
        pot=int(getattr(raw, "total_pot_amount", 0) or 0),
        sidepots=(),
        community=tuple(state.community()),
        seats_public=_seats_public(state),
        button_seat=state.button_seat,
    )

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
    OpponentStatsOrInsufficient,
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
    """Normalize pokerkit's per-seat status into our SeatStatus Literal.

    pokerkit 0.7.3: `raw.statuses[i]` is `bool` — False means folded.
    `all_in` detection additionally requires `stack == 0` with status True; that
    refinement is plumbed into `_seats_public` via a helper parameter in Phase 2
    (see TODO tag in `_seats_public`). Phase 1 treats all-in as in_hand.
    """
    if raw_status is False:
        return "folded"
    if isinstance(raw_status, str):
        s = raw_status.lower()
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
        position_idx = (i - state.button_seat + 3) % n  # button -> BTN (index 3 in _POSITIONS_6MAX)
        short, full = _POSITIONS_6MAX[position_idx] if n == 6 else (f"P{i}", f"Position {i}")
        status = _normalize_status(statuses[i] if i < len(statuses) else "in_hand")
        out.append(
            SeatPublicInfo(
                seat=i,
                label=f"Player_{i}",
                position_short=short,
                position_full=full,
                stack=int(stacks[i]) if i < len(stacks) else 0,
                invested_this_hand=0,  # TODO(phase2): plumb cumulative across streets; Phase 1 has no street history
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
    state: CanonicalState,
    actor: int,
    *,
    turn_seed: int,
    opponent_stats: dict[int, OpponentStatsOrInsufficient] | None = None,
) -> PlayerView:
    """Project CanonicalState into a seat-scoped PlayerView DTO.

    P2 invariant: the returned DTO carries only `actor`'s hole cards and
    `actor`'s turn_seed; it never contains other seats' hole cards or other
    seats' turn_seed. Pure function of (state, actor, turn_seed,
    opponent_stats).

    Phase 3c-hud: optional opponent_stats kwarg (default None → {}) carries
    pre-computed per-opponent HUD stats. Session computes via
    _build_opponent_stats(actor) and passes per turn.
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

    pot_total = int(getattr(raw, "total_pot_amount", 0) or 0)
    street = _infer_street(state)
    to_call = max(0, max_bet - my_invested_round)
    pot_odds_required: float | None = to_call / (pot_total + to_call) if to_call > 0 else None
    # Effective stack: capped by deepest non-folded opponent. With no opps left
    # the heads-up notion degenerates to my own stack.
    opp_stacks = [seats[i].stack for i in opp_in_hand]
    effective_stack = min(my_stack, max(opp_stacks)) if opp_stacks else my_stack

    return PlayerView(
        my_seat=actor,
        my_hole_cards=my_hole,
        community=tuple(state.community()),
        pot=pot_total,
        sidepots=(),  # TODO(phase2): derive side pots from state.pots after BET_COLLECTION
        my_stack=my_stack,
        my_invested_this_hand=my_invested_round,  # TODO(phase2): plumb cumulative across streets; currently equals this_round
        my_invested_this_round=my_invested_round,
        current_bet_to_match=max_bet,
        to_call=to_call,
        pot_odds_required=pot_odds_required,
        effective_stack=effective_stack,
        seats_public=seats,
        opponent_seats_in_hand=tuple(opp_in_hand),
        action_order_this_street=_canonical_street_action_order(
            button=state.button_seat,
            n=state.num_players,
            street=street,
        ),
        seats_yet_to_act_after_me=_seats_yet_to_act_after_me(state, actor),
        already_acted_this_street=(),  # TODO(phase2): thread street-history plumbing
        hand_history=(),  # TODO(phase2): thread street-history plumbing
        legal_actions=compute_legal_tool_set(state, actor),
        opponent_stats=opponent_stats or {},
        hand_id=state._ctx.hand_id,  # noqa: SLF001
        street=street,
        button_seat=state.button_seat,
        turn_seed=turn_seed,
        immutable_session_params=_session_params_view(state),
    )


def _canonical_street_action_order(
    *,
    button: int,
    n: int,
    street: Street,
) -> tuple[int, ...]:
    """The canonical seat-order for a street, full N seats including folded.

    Preflop: UTG (= button+3) acts first, then HJ, CO, BTN, SB, BB.
    Postflop: SB (= button+1) acts first; BTN (= button) closes.

    This is the *theoretical* street order, not the live action queue: it
    includes every seat at the table in their natural turn so that callers
    relying on `view.action_order_this_street.index(my_seat)` get a stable
    position index. For live "who's still to act" use
    `seats_yet_to_act_after_me` (PokerKit-derived).
    """
    start = (button + 3) % n if street == Street.PREFLOP else (button + 1) % n
    return tuple((start + i) % n for i in range(n))


def _seats_yet_to_act_after_me(state: CanonicalState, actor: int) -> tuple[int, ...]:
    """Seats remaining in PokerKit's actor queue *after* dropping me.

    PokerKit's `state.actor_indices` is a deque whose head is the current
    actor. The tail enumerates the seats that will act next on this street
    after the current actor; PokerKit handles fold / all-in / re-queueing
    after a raise, so reading the deque is more robust than recomputing it
    from scratch.
    """
    raw = state._state  # noqa: SLF001
    queue = getattr(raw, "actor_indices", None)
    if queue is None:
        return ()
    seq = tuple(int(i) for i in queue)
    if not seq or seq[0] != actor:
        return seq
    return seq[1:]


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

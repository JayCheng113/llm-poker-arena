"""Session orchestrator: multi-hand loop with audit + 3-layer event emission.

Replaces Phase-1 `engine._internal.rebuy.run_single_hand` for end-to-end runs.
Phase 3a: async; each agent's `await decide(view) -> TurnDecisionResult` is
called inline. Per hand:

  - One `CanonicalPrivateHandRecord` line (canonical_private.jsonl)
  - One `PublicHandRecord` line (public_replay.jsonl; spec §7.3 hand-per-line
    shape; events are collected into a list during the hand then wrapped)
  - N `AgentViewSnapshot` lines, one per agent turn (agent_view_snapshots.jsonl)

Forward-compatibility: `AgentViewSnapshot` schema carries all Phase-3 fields
(retry counters, api_error, turn_timeout_exceeded) but populates them with
degenerate defaults for mock agents — no field added in Phase 3 that isn't
writable today.

Phase 3 responsibilities out of scope here:
  - Async ReAct loop with 4 retry counters
  - `mark_hand_censored` for api_error / total_turn_timeout (spec BR2-01)
  - Seat permutation (Phase 2a uses `button_seat = hand_id % n`)
"""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.engine._internal.audit import HandPhase, audit_invariants
from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine._internal.rebuy import derive_deck_seed
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.projections import build_player_view
from llm_poker_arena.engine.transition import apply_action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.storage.jsonl_writer import BatchedJsonlWriter
from llm_poker_arena.storage.layer_builders import (
    build_agent_view_snapshot,
    build_canonical_private_hand,
    build_censored_hand_record,
    build_public_action_event,
    build_public_hand_ended_event,
    build_public_hand_record,
    build_public_hand_started_event,
    build_public_hole_dealt_event,
    build_public_showdown_event,
    build_public_street_reveal_event,
)
from llm_poker_arena.storage.meta import build_session_meta
from llm_poker_arena.storage.schemas import (
    ActionRecordPrivate,
    PublicEvent,
    WinnerInfo,
)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _derive_turn_seed(deck_seed: int, actor: int, turn_counter: int) -> int:
    payload = f"{deck_seed}:{actor}:{turn_counter}".encode()
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big") & (
        (1 << 63) - 1
    )


def _split_provider_id(pid: str) -> tuple[str, str]:
    """'random:uniform' -> ('random', 'uniform'); 'random' -> ('random', 'random')."""
    parts = pid.split(":", 1)
    provider = parts[0]
    model = parts[1] if len(parts) > 1 else parts[0]
    return provider, model


class Session:
    """Phase 2a synchronous session driver."""

    def __init__(
        self, *, config: SessionConfig, agents: Sequence[Agent],
        output_dir: Path, session_id: str,
    ) -> None:
        if len(agents) != config.num_players:
            raise ValueError(
                f"agents length ({len(agents)}) != config.num_players ({config.num_players})"
            )
        self._config = config
        self._agents = list(agents)
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._session_id = session_id

        # spec §7.1: snapshot the SessionConfig at session start so analysts
        # can reproduce the exact run. Phase 2a uses config.json (no new dep);
        # Phase 2b renames to config.yaml when pyyaml is added.
        (self._output_dir / "config.json").write_text(
            config.model_dump_json(indent=2)
        )

        self._private_writer = BatchedJsonlWriter(self._output_dir / "canonical_private.jsonl")
        self._public_writer = BatchedJsonlWriter(self._output_dir / "public_replay.jsonl")
        self._snapshot_writer = BatchedJsonlWriter(self._output_dir / "agent_view_snapshots.jsonl")
        self._censor_writer = BatchedJsonlWriter(self._output_dir / "censored_hands.jsonl")

        self._chip_pnl: dict[int, int] = {i: 0 for i in range(config.num_players)}
        self._total_hands_played = 0

    async def run(self) -> None:
        started_at_iso = _now_iso()
        started_at_monotonic = time.monotonic()
        initial_button_seat = 0
        try:
            for hand_id in range(self._config.num_hands):
                await self._run_one_hand(hand_id)
                self._total_hands_played += 1
        finally:
            ended_at_iso = _now_iso()
            wall_time_sec = max(0, int(time.monotonic() - started_at_monotonic))
            meta = build_session_meta(
                session_id=self._session_id, config=self._config,
                started_at=started_at_iso, ended_at=ended_at_iso,
                total_hands_played=self._total_hands_played,
                seat_assignment={i: self._agents[i].provider_id()
                                 for i in range(self._config.num_players)},
                initial_button_seat=initial_button_seat,
                chip_pnl=self._chip_pnl,
                session_wall_time_sec=wall_time_sec,
            )
            (self._output_dir / "meta.json").write_text(
                json.dumps(meta, sort_keys=True, indent=2)
            )
            for w in (self._private_writer, self._public_writer,
                      self._snapshot_writer, self._censor_writer):
                w.close()

    # ------------------------------------------------- per-hand

    async def _run_one_hand(self, hand_id: int) -> None:
        cfg = self._config
        ctx = HandContext(
            hand_id=hand_id,
            deck_seed=derive_deck_seed(cfg.rng_seed, hand_id),
            button_seat=hand_id % cfg.num_players,
            initial_stacks=(cfg.starting_stack,) * cfg.num_players,
        )
        state = CanonicalState(cfg, ctx)
        audit_invariants(state, cfg, HandPhase.PRE_SETTLEMENT)

        # Snapshot ALL 6 seats' hole cards BEFORE any fold happens. PokerKit's
        # HAND_KILLING automation moves folded/losing seats' cards to
        # `mucked_cards` immediately on fold, so reading `state.hole_cards()`
        # at hand-end only sees the winner. We need the complete snapshot for
        # spec §7.2 canonical_private ("all hole cards") and §7.3 public
        # showdown (reveal every seat that reached showdown, not just winner).
        initial_hole_cards = state.hole_cards()

        started_at = _now_iso()
        # Per spec §7.3: one public_replay line per hand. Collect events
        # into a local buffer and flush via PublicHandRecord at hand-end.
        events: list[PublicEvent] = []
        events.append(build_public_hand_started_event(
            hand_id=hand_id, state=state, sb=cfg.sb, bb=cfg.bb,
        ))
        events.append(build_public_hole_dealt_event(hand_id=hand_id))

        action_records: list[ActionRecordPrivate] = []
        # Phase 3d: stage per-turn snapshots so a mid-hand censor (or a
        # RuntimeError) discards them atomically rather than leaving partial
        # state in agent_view_snapshots.jsonl. spec §4.1 BR2-01 "censor 整手".
        staged_snapshots: list[dict[str, Any]] = []
        turn_counter = 0

        while state._state.actor_index is not None:  # noqa: SLF001
            actor = int(state._state.actor_index)  # noqa: SLF001
            turn_seed = _derive_turn_seed(ctx.deck_seed, actor, turn_counter)
            view = build_player_view(state, actor, turn_seed=turn_seed)
            street = view.street
            decision = await self._agents[actor].decide(view)
            if decision.api_error is not None or decision.final_action is None:
                # spec §4.1 BR2-01: censor full hand. Discard staged
                # per-hand artifacts (staged_snapshots is a local var, dropped
                # on return) and emit one censor record.
                censor_rec = build_censored_hand_record(
                    hand_id=hand_id, seat=actor,
                    session_id=self._session_id,
                    api_error=decision.api_error,
                    timestamp=_now_iso(),
                )
                self._censor_writer.write(censor_rec.model_dump(mode="json"))
                return
            chosen = decision.final_action
            fallback = decision.default_action_fallback
            result = apply_action(state, actor, chosen)
            if not result.is_valid:
                raise RuntimeError(
                    f"agent at seat {actor} returned action {chosen!r} that "
                    f"pokerkit rejected: {result.reason}. This is an agent "
                    f"contract violation."
                )

            events.append(build_public_action_event(
                hand_id=hand_id, seat=actor, street=street, action=chosen,
            ))

            provider, model = _split_provider_id(self._agents[actor].provider_id())
            snapshot = build_agent_view_snapshot(
                hand_id=hand_id, session_id=self._session_id, seat=actor,
                street=street, timestamp=_now_iso(), view=view,
                action=chosen, turn_index=turn_counter,
                agent_provider=provider, agent_model=model,
                agent_version="phase3a",
                default_action_fallback=fallback,
                iterations=decision.iterations,
                total_tokens=decision.total_tokens,
                wall_time_ms=decision.wall_time_ms,
                api_retry_count=decision.api_retry_count,
                illegal_action_retry_count=decision.illegal_action_retry_count,
                no_tool_retry_count=decision.no_tool_retry_count,
                tool_usage_error_count=decision.tool_usage_error_count,
            )
            staged_snapshots.append(snapshot.model_dump(mode="json"))

            action_records.append(ActionRecordPrivate(
                seat=actor,
                street=cast(Any, street.value),
                action_type=cast(Any, chosen.tool_name),
                amount=(
                    int(chosen.args["amount"])
                    if isinstance(chosen.args, dict) and "amount" in chosen.args
                    else None
                ),
                is_forced_blind=False,
                turn_index=turn_counter,
            ))
            turn_counter += 1

            self._maybe_advance_between_streets(state, hand_id, events)

        # Hand completed cleanly (no censor). Commit staged per-turn
        # snapshots now (spec §4.1 BR2-01: only flush after we know the
        # hand wasn't censored).
        for snap in staged_snapshots:
            self._snapshot_writer.write(snap)

        # Hand is over. Emit showdown (if anyone saw it) + hand_ended.
        statuses = list(state._state.statuses)  # noqa: SLF001
        showdown_seats = {i for i, alive in enumerate(statuses) if bool(alive)}
        showdown = len(showdown_seats) > 1
        if showdown:
            events.append(build_public_showdown_event(
                hand_id=hand_id,
                showdown_seats=showdown_seats,
                hole_cards=initial_hole_cards,
            ))

        payoffs = list(state._state.payoffs)  # noqa: SLF001
        winnings = {i: int(payoffs[i]) for i in range(cfg.num_players)}
        events.append(build_public_hand_ended_event(
            hand_id=hand_id, winnings=winnings,
        ))

        audit_invariants(state, cfg, HandPhase.POST_SETTLEMENT)

        # Flush public_replay: ONE line per hand (spec §7.3 shape).
        public_record = build_public_hand_record(
            hand_id=hand_id, events=tuple(events),
        )
        self._public_writer.write(public_record.model_dump(mode="json"))

        # Canonical private hand record.
        # Phase 2a: final_invested left empty -- proper tracking (per-seat
        # cumulative contribution including blinds) requires walking
        # `state.operations` or tracking bets inline. Deferred to Phase 2b;
        # MVP 6 exit criterion does not depend on this field.
        ended_at = _now_iso()
        private_record = build_canonical_private_hand(
            hand_id=hand_id, state=state,
            started_at=started_at, ended_at=ended_at,
            actions=tuple(action_records),
            hole_cards=initial_hole_cards,
            winners=tuple(
                WinnerInfo(seat=i, winnings=int(payoffs[i]), best_hand_desc="")
                for i in range(cfg.num_players) if int(payoffs[i]) > 0
            ),
            side_pots=(),
            final_invested={},
            net_pnl=winnings,
            showdown=showdown,
        )
        self._private_writer.write(private_record.model_dump(mode="json"))

        # Hand-end durability checkpoint (spec §8.1: flush at hand_ended).
        for w in (self._public_writer, self._snapshot_writer, self._private_writer):
            w.flush()

        # Session-level chip_pnl accumulator (spec meta.chip_pnl).
        for seat, delta in winnings.items():
            self._chip_pnl[seat] += delta

    # ------------------------------------------------- between-street advance

    def _maybe_advance_between_streets(
        self, state: CanonicalState, hand_id: int, events: list[PublicEvent],
    ) -> None:
        """Drain pokerkit's show_or_muck + burn+deal queue between streets.

        Appends public street-reveal events directly into the `events` buffer
        (spec §7.3 one-hand-per-line shape). Mirrors the Phase-1 pattern in
        `engine/_internal/rebuy.py::_maybe_advance_between_streets`.

        Raises `RuntimeError` if the iteration cap is reached without the
        state machine converging -- matches Phase-1 discipline. Silent return
        on cap exhaustion would hide infinite-loop bugs in pokerkit's
        between-streets logic.
        """
        raw = state._state  # noqa: SLF001
        for _ in range(32):
            if raw.actor_index is not None:
                return
            if raw.can_show_or_muck_hole_cards():
                raw.show_or_muck_hole_cards()
                continue
            if raw.can_burn_card():
                board_len = sum(len(slot) for slot in (raw.board_cards or []))
                if board_len == 0:
                    state.deal_community(Street.FLOP)
                    events.append(build_public_street_reveal_event(
                        hand_id=hand_id, state=state, street=Street.FLOP,
                    ))
                elif board_len == 3:
                    state.deal_community(Street.TURN)
                    events.append(build_public_street_reveal_event(
                        hand_id=hand_id, state=state, street=Street.TURN,
                    ))
                elif board_len == 4:
                    state.deal_community(Street.RIVER)
                    events.append(build_public_street_reveal_event(
                        hand_id=hand_id, state=state, street=Street.RIVER,
                    ))
                else:
                    raise RuntimeError(
                        f"unexpected board length {board_len} requesting burn"
                    )
                continue
            # Neither actor-required nor pending show/burn -- hand has
            # reached a stable terminal state. Return to outer loop.
            return
        raise RuntimeError(
            "_maybe_advance_between_streets exceeded 32 iterations; pokerkit "
            "between-streets state machine is not converging (hand_id="
            f"{hand_id})"
        )


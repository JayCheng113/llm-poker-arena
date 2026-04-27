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
from llm_poker_arena.agents.llm.types import ObservedCapability
from llm_poker_arena.engine._internal.audit import HandPhase, audit_invariants
from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine._internal.rebuy import derive_deck_seed
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.projections import build_player_view
from llm_poker_arena.engine.transition import apply_action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import OpponentStatsOrInsufficient
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
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big") & ((1 << 63) - 1)


def _split_provider_id(pid: str) -> tuple[str, str]:
    """'random:uniform' -> ('random', 'uniform'); 'random' -> ('random', 'random')."""
    parts = pid.split(":", 1)
    provider = parts[0]
    model = parts[1] if len(parts) > 1 else parts[0]
    return provider, model


def _capability_to_meta_json(cap: ObservedCapability) -> dict[str, Any]:
    """Map in-process ObservedCapability (§4.4 names) to spec §7.6
    persisted JSON schema names. Keeps the Pydantic type clean while
    honoring the meta.json contract analysts depend on.
    """
    return {
        "provider": cap.provider,
        "probed_at": cap.probed_at,
        "reasoning_kinds_observed": [k.value for k in cap.reasoning_kinds],
        "seed_supported": cap.seed_accepted,
        "tool_use_with_thinking_ok": cap.tool_use_with_thinking_ok,
        "extra_flags": dict(cap.extra_flags),
    }


class Session:
    """Phase 2a synchronous session driver."""

    def __init__(
        self,
        *,
        config: SessionConfig,
        agents: Sequence[Agent],
        output_dir: Path,
        session_id: str,
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
        (self._output_dir / "config.json").write_text(config.model_dump_json(indent=2))

        self._private_writer = BatchedJsonlWriter(self._output_dir / "canonical_private.jsonl")
        self._public_writer = BatchedJsonlWriter(self._output_dir / "public_replay.jsonl")
        self._snapshot_writer = BatchedJsonlWriter(self._output_dir / "agent_view_snapshots.jsonl")
        self._censor_writer = BatchedJsonlWriter(self._output_dir / "censored_hands.jsonl")

        self._chip_pnl: dict[int, int] = {i: 0 for i in range(config.num_players)}
        self._total_hands_played = 0

        # Phase 4 Task 2: per-seat aggregation for meta.json. Initialized as
        # empty dicts (one entry per seat appears as turns accumulate).
        n = config.num_players
        self._retry_summary_per_seat: dict[int, dict[str, int]] = {
            i: {
                "total_turns": 0,
                "api_retry_count": 0,
                "illegal_action_retry_count": 0,
                "no_tool_retry_count": 0,
                "tool_usage_error_count": 0,
                "default_action_fallback_count": 0,
                "turn_timeout_exceeded_count": 0,
            }
            for i in range(n)
        }
        self._tool_usage_summary: dict[int, dict[str, int]] = {
            i: {"total_utility_calls": 0} for i in range(n)
        }
        self._total_tokens_per_seat: dict[int, dict[str, int]] = {
            i: {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            }
            for i in range(n)
        }

        # Phase 3c-hud: per-seat HUD stat counters. Initialized to all zeros.
        # 8 counters per seat — see plan §"Phase 3c-hud Scope Decisions"
        # for stat semantics. Updated incrementally in _run_one_hand
        # (per-action for AF; per-hand boolean flush at hand end for the rest).
        self._hud_counters: dict[int, dict[str, int]] = {
            i: {
                "vpip_actions": 0,
                "pfr_actions": 0,
                "three_bet_chances": 0,
                "three_bet_actions": 0,
                "af_aggressive": 0,
                "af_passive": 0,
                "wtsd_chances": 0,
                "wtsd_actions": 0,
            }
            for i in range(n)
        }
        # codex audit IMPORTANT-5 fix: HUD-specific completed-hand counter.
        # Distinct from self._total_hands_played which counts ALL hands
        # including censored ones (returned-early in _run_one_hand on
        # api_error). HUD counters only flush on clean hand completion, so
        # using _total_hands_played as the VPIP/PFR denominator would
        # depress rates by the censor count.
        self._hud_hands_counted: int = 0

    async def run(self) -> None:
        started_at_iso = _now_iso()
        started_at_monotonic = time.monotonic()
        initial_button_seat = 0
        # Initialize capabilities BEFORE the try so that even probe failure
        # reaches the finally cleanup (writers close, partial meta.json
        # still written). spec §4.4 HR2-03: probe each unique LLMProvider
        # once; non-LLM agents (Random, RuleBased, HumanCLI) skip probe.
        provider_capabilities: dict[str, dict[str, Any]] = {}
        # Phase 4 Task 3: track stop reason for meta.json. Defaults to
        # "completed" when the session finishes all configured hands; updated
        # to a sentinel string if cost cap aborts.
        stop_reason = "completed"
        try:
            provider_capabilities = await self._probe_providers()
            for hand_id in range(self._config.num_hands):
                await self._run_one_hand(hand_id)
                self._total_hands_played += 1
                # Cost cap check at hand boundary (clean abort, complete artifacts).
                if self._config.max_total_tokens is not None:
                    total_tokens = sum(
                        seat["input_tokens"] + seat["output_tokens"]
                        for seat in self._total_tokens_per_seat.values()
                    )
                    if total_tokens > self._config.max_total_tokens:
                        stop_reason = "max_total_tokens_exceeded"
                        break
        finally:
            ended_at_iso = _now_iso()
            wall_time_sec = max(0, int(time.monotonic() - started_at_monotonic))
            meta = build_session_meta(
                session_id=self._session_id,
                config=self._config,
                started_at=started_at_iso,
                ended_at=ended_at_iso,
                total_hands_played=self._total_hands_played,
                seat_assignment={
                    i: self._agents[i].provider_id() for i in range(self._config.num_players)
                },
                initial_button_seat=initial_button_seat,
                chip_pnl=self._chip_pnl,
                session_wall_time_sec=wall_time_sec,
                provider_capabilities=provider_capabilities,
                retry_summary_per_seat=self._retry_summary_per_seat,
                tool_usage_summary=self._tool_usage_summary,
                total_tokens_per_seat=self._total_tokens_per_seat,
                hud_per_seat=self._hud_counters,
                hud_hands_counted=self._hud_hands_counted,
                stop_reason=stop_reason,
            )
            (self._output_dir / "meta.json").write_text(json.dumps(meta, sort_keys=True, indent=2))
            for w in (
                self._private_writer,
                self._public_writer,
                self._snapshot_writer,
                self._censor_writer,
            ):
                w.close()

    async def _probe_providers(self) -> dict[str, dict[str, Any]]:
        """For each LLMAgent in the seat list, call provider.probe() once
        and store the §7.6-named JSON dict under the seat's string key.
        Probes per provider instance are deduped (id-based) so two agents
        sharing one provider only probe once and reuse the result.

        The internal Pydantic `ObservedCapability` type uses §4.4 names
        (reasoning_kinds, seed_accepted); we map to §7.6 persisted-schema
        names (reasoning_kinds_observed, seed_supported) at this boundary
        so analysts reading meta.json get the schema spec promises.
        """
        from llm_poker_arena.agents.llm.llm_agent import LLMAgent

        results: dict[str, dict[str, Any]] = {}
        cache: dict[int, dict[str, Any]] = {}
        for seat, agent in enumerate(self._agents):
            if not isinstance(agent, LLMAgent):
                continue
            provider = agent._provider  # noqa: SLF001
            pid = id(provider)
            if pid not in cache:
                cap: ObservedCapability = await provider.probe()
                cache[pid] = _capability_to_meta_json(cap)
            results[str(seat)] = cache[pid]
        return results

    def _build_opponent_stats(
        self, actor: int,
    ) -> dict[int, OpponentStatsOrInsufficient]:
        """Phase 3c-hud: build per-opponent OpponentStatsOrInsufficient dict
        from cumulative HUD counters. Self-seat excluded.

        Uses _hud_hands_counted (codex audit IMPORTANT-5) — counts only
        cleanly-completed hands. Censored hands (api_error → early return
        in _run_one_hand) don't depress VPIP/PFR rates or count toward
        min-sample gating.

        Returns insufficient=True for ALL opponents when _hud_hands_counted
        < opponent_stats_min_samples. Past that threshold, returns
        insufficient=True ONLY for individual opponents whose specific stat
        denominator is 0 (rare edge case — opponent who played 30+ hands
        but never had a 3-bet opportunity, or never called).

        Conservative all-or-nothing per-opponent policy avoids the
        OpponentStatsOrInsufficient validator's "non-insufficient → all
        numeric required" constraint. Documented limitation: an opponent
        past 30 hands with no 3-bet chance / no calls / no VPIP loses
        all 5 stats. Future Phase 5+ may relax the validator to per-stat
        None handling.
        """
        # OpponentStatsOrInsufficient imported at module top (codex re-audit
        # BLOCKER N3 fix — annotation must resolve under mypy --strict).
        n_played = self._hud_hands_counted
        min_samples = self._config.opponent_stats_min_samples
        out: dict[int, OpponentStatsOrInsufficient] = {}
        for seat in range(self._config.num_players):
            if seat == actor:
                continue  # exclude self
            if n_played < min_samples:
                out[seat] = OpponentStatsOrInsufficient(insufficient=True)
                continue
            c = self._hud_counters[seat]
            three_bet_den = c["three_bet_chances"]
            af_den = c["af_passive"]
            wtsd_den = c["wtsd_chances"]
            if three_bet_den == 0 or af_den == 0 or wtsd_den == 0:
                out[seat] = OpponentStatsOrInsufficient(insufficient=True)
                continue
            out[seat] = OpponentStatsOrInsufficient(
                insufficient=False,
                vpip=c["vpip_actions"] / n_played,
                pfr=c["pfr_actions"] / n_played,
                three_bet=c["three_bet_actions"] / three_bet_den,
                af=c["af_aggressive"] / af_den,
                wtsd=c["wtsd_actions"] / wtsd_den,
            )
        return out

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
        events.append(
            build_public_hand_started_event(
                hand_id=hand_id,
                state=state,
                sb=cfg.sb,
                bb=cfg.bb,
            )
        )
        events.append(build_public_hole_dealt_event(hand_id=hand_id))

        action_records: list[ActionRecordPrivate] = []
        # Phase 3d: stage per-turn snapshots so a mid-hand censor (or a
        # RuntimeError) discards them atomically rather than leaving partial
        # state in agent_view_snapshots.jsonl. spec §4.1 BR2-01 "censor 整手".
        staged_snapshots: list[dict[str, Any]] = []
        turn_counter = 0

        # Phase 3c-hud: per-hand booleans for VPIP/PFR/3-bet/WTSD; flushed
        # to _hud_counters at hand end. Per-action stats (AF) are updated
        # immediately in the loop below.
        n_seats = self._config.num_players
        hand_state: dict[int, dict[str, bool]] = {
            i: {
                "did_vpip": False,
                "did_pfr": False,
                "had_3bet_chance": False,
                "did_3bet": False,
                "preflop_raised": False,
            }
            for i in range(n_seats)
        }

        while state._state.actor_index is not None:  # noqa: SLF001
            actor = int(state._state.actor_index)  # noqa: SLF001
            turn_seed = _derive_turn_seed(ctx.deck_seed, actor, turn_counter)
            opp_stats = self._build_opponent_stats(actor)
            view = build_player_view(
                state, actor, turn_seed=turn_seed,
                opponent_stats=opp_stats,
            )
            street = view.street
            decision = await self._agents[actor].decide(view)
            # Phase 4 Task 2: per-seat retry/token aggregation for meta.json.
            rs = self._retry_summary_per_seat[actor]
            rs["total_turns"] += 1
            rs["api_retry_count"] += decision.api_retry_count
            rs["illegal_action_retry_count"] += decision.illegal_action_retry_count
            rs["no_tool_retry_count"] += decision.no_tool_retry_count
            rs["tool_usage_error_count"] += decision.tool_usage_error_count
            if decision.default_action_fallback:
                rs["default_action_fallback_count"] += 1
            if decision.turn_timeout_exceeded:
                rs["turn_timeout_exceeded_count"] += 1

            tu = self._tool_usage_summary[actor]
            for ir in decision.iterations:
                if ir.tool_result is not None:
                    tu["total_utility_calls"] += 1

            tt = self._total_tokens_per_seat[actor]
            tt["input_tokens"] += decision.total_tokens.input_tokens
            tt["output_tokens"] += decision.total_tokens.output_tokens
            tt["cache_read_input_tokens"] += decision.total_tokens.cache_read_input_tokens
            tt["cache_creation_input_tokens"] += decision.total_tokens.cache_creation_input_tokens

            if decision.api_error is not None or decision.final_action is None:
                # spec §4.1 BR2-01: censor full hand. Discard staged
                # per-hand artifacts (staged_snapshots is a local var, dropped
                # on return) and emit one censor record.
                censor_rec = build_censored_hand_record(
                    hand_id=hand_id,
                    seat=actor,
                    session_id=self._session_id,
                    api_error=decision.api_error,
                    timestamp=_now_iso(),
                )
                self._censor_writer.write(censor_rec.model_dump(mode="json"))
                return
            chosen = decision.final_action
            fallback = decision.default_action_fallback

            # Phase 3c-hud: VPIP — voluntary preflop action (call/raise/bet/all_in).
            # All `chosen` actions are voluntary by construction (forced blinds
            # are posted by PokerKit automation, never via agent.decide).
            if street == Street.PREFLOP and chosen.tool_name in (
                "call", "raise_to", "bet", "all_in",
            ):
                hand_state[actor]["did_vpip"] = True

            # Phase 3c-hud: PFR — voluntary preflop raise (raise_to/bet/all_in).
            # Standard tracker convention treats all_in as a raise even when
            # it equals current_bet_to_match (rare in 6-max deep stack).
            if street == Street.PREFLOP and chosen.tool_name in (
                "raise_to", "bet", "all_in",
            ):
                hand_state[actor]["did_pfr"] = True

            # Phase 3c-hud: 3-bet — the SECOND voluntary preflop raise
            # (codex audit BLOCKER B2 fix). Anything beyond is 4-bet+, NOT 3-bet.
            #
            # Chance: this seat acts preflop with EXACTLY ONE prior voluntary
            # aggressive action (from another seat) on the table AND this seat
            # has not yet raised preflop this hand.
            # Action: chance + this seat raises in that turn.
            if street == Street.PREFLOP:
                preflop_raise_count = sum(
                    1 for ar in action_records
                    if ar.street == "preflop"
                    and ar.action_type in ("raise_to", "bet", "all_in")
                )
                if (
                    preflop_raise_count == 1
                    and not hand_state[actor]["preflop_raised"]
                ):
                    hand_state[actor]["had_3bet_chance"] = True
                    if chosen.tool_name in ("raise_to", "bet", "all_in"):
                        hand_state[actor]["did_3bet"] = True
                # Track this seat's own preflop raises for self-exclusion.
                if chosen.tool_name in ("raise_to", "bet", "all_in"):
                    hand_state[actor]["preflop_raised"] = True

            # Phase 3c-hud: AF — individual action ratio across all streets.
            # aggressive = bet + raise_to + all_in
            # passive = call
            # fold + check not in formula (Task 5).
            if chosen.tool_name in ("bet", "raise_to", "all_in"):
                self._hud_counters[actor]["af_aggressive"] += 1
            elif chosen.tool_name == "call":
                self._hud_counters[actor]["af_passive"] += 1

            result = apply_action(state, actor, chosen)
            if not result.is_valid:
                raise RuntimeError(
                    f"agent at seat {actor} returned action {chosen!r} that "
                    f"pokerkit rejected: {result.reason}. This is an agent "
                    f"contract violation."
                )

            events.append(
                build_public_action_event(
                    hand_id=hand_id,
                    seat=actor,
                    street=street,
                    action=chosen,
                )
            )

            provider, model = _split_provider_id(self._agents[actor].provider_id())
            agent_md = self._agents[actor].metadata() or {}
            snapshot = build_agent_view_snapshot(
                hand_id=hand_id,
                session_id=self._session_id,
                seat=actor,
                street=street,
                timestamp=_now_iso(),
                view=view,
                action=chosen,
                turn_index=turn_counter,
                agent_provider=provider,
                agent_model=model,
                agent_version="phase3a",
                default_action_fallback=fallback,
                iterations=decision.iterations,
                total_tokens=decision.total_tokens,
                wall_time_ms=decision.wall_time_ms,
                api_retry_count=decision.api_retry_count,
                illegal_action_retry_count=decision.illegal_action_retry_count,
                no_tool_retry_count=decision.no_tool_retry_count,
                tool_usage_error_count=decision.tool_usage_error_count,
                agent_temperature=agent_md.get("temperature"),
                agent_seed=agent_md.get("seed"),
            )
            staged_snapshots.append(snapshot.model_dump(mode="json"))

            action_records.append(
                ActionRecordPrivate(
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
                )
            )
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

        # Phase 3c-hud: flush per-hand booleans to cumulative counters.
        # codex audit IMPORTANT-5: also bump HUD-only completed-hand counter.
        # This block ONLY runs on clean hand completion (censored hands return
        # early earlier in the method), so _hud_hands_counted reflects the
        # true denominator for VPIP/PFR rates and min-sample gating.
        self._hud_hands_counted += 1
        # Real showdown requires len(showdown_seats) > 1 (matches the
        # `showdown` flag computed two lines below). A solo survivor of
        # uncalled action did not actually show down — code-reviewer
        # IMPORTANT-1.
        had_real_showdown = len(showdown_seats) > 1
        for seat in range(n_seats):
            if hand_state[seat]["did_vpip"]:
                self._hud_counters[seat]["vpip_actions"] += 1
                # WTSD chance granted to all VPIP hands (matches our
                # plan §26 denominator convention).
                self._hud_counters[seat]["wtsd_chances"] += 1
                if had_real_showdown and seat in showdown_seats:
                    self._hud_counters[seat]["wtsd_actions"] += 1
            if hand_state[seat]["did_pfr"]:
                self._hud_counters[seat]["pfr_actions"] += 1
            if hand_state[seat]["had_3bet_chance"]:
                self._hud_counters[seat]["three_bet_chances"] += 1
            if hand_state[seat]["did_3bet"]:
                self._hud_counters[seat]["three_bet_actions"] += 1
        showdown = len(showdown_seats) > 1
        if showdown:
            events.append(
                build_public_showdown_event(
                    hand_id=hand_id,
                    showdown_seats=showdown_seats,
                    hole_cards=initial_hole_cards,
                )
            )

        payoffs = list(state._state.payoffs)  # noqa: SLF001
        winnings = {i: int(payoffs[i]) for i in range(cfg.num_players)}
        events.append(
            build_public_hand_ended_event(
                hand_id=hand_id,
                winnings=winnings,
            )
        )

        audit_invariants(state, cfg, HandPhase.POST_SETTLEMENT)

        # Flush public_replay: ONE line per hand (spec §7.3 shape).
        public_record = build_public_hand_record(
            hand_id=hand_id,
            events=tuple(events),
        )
        self._public_writer.write(public_record.model_dump(mode="json"))

        # Canonical private hand record.
        # Phase 2a: final_invested left empty -- proper tracking (per-seat
        # cumulative contribution including blinds) requires walking
        # `state.operations` or tracking bets inline. Deferred to Phase 2b;
        # MVP 6 exit criterion does not depend on this field.
        ended_at = _now_iso()
        private_record = build_canonical_private_hand(
            hand_id=hand_id,
            state=state,
            started_at=started_at,
            ended_at=ended_at,
            actions=tuple(action_records),
            hole_cards=initial_hole_cards,
            winners=tuple(
                WinnerInfo(seat=i, winnings=int(payoffs[i]), best_hand_desc="")
                for i in range(cfg.num_players)
                if int(payoffs[i]) > 0
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
        self,
        state: CanonicalState,
        hand_id: int,
        events: list[PublicEvent],
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
                    events.append(
                        build_public_street_reveal_event(
                            hand_id=hand_id,
                            state=state,
                            street=Street.FLOP,
                        )
                    )
                elif board_len == 3:
                    state.deal_community(Street.TURN)
                    events.append(
                        build_public_street_reveal_event(
                            hand_id=hand_id,
                            state=state,
                            street=Street.TURN,
                        )
                    )
                elif board_len == 4:
                    state.deal_community(Street.RIVER)
                    events.append(
                        build_public_street_reveal_event(
                            hand_id=hand_id,
                            state=state,
                            street=Street.RIVER,
                        )
                    )
                else:
                    raise RuntimeError(f"unexpected board length {board_len} requesting burn")
                continue
            # Neither actor-required nor pending show/burn -- hand has
            # reached a stable terminal state. Return to outer loop.
            return
        raise RuntimeError(
            "_maybe_advance_between_streets exceeded 32 iterations; pokerkit "
            "between-streets state machine is not converging (hand_id="
            f"{hand_id})"
        )

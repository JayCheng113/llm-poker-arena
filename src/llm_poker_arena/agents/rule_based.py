"""RuleBasedAgent: simple tight/aggressive skill-floor baseline (spec §15.2 B2).

Not intended to play well; intended to be a reproducible, transparent rule
dispatcher that an integration test can exercise alongside RandomAgent to
produce a heterogeneous lineup. No randomness — decisions are a pure function
of `view`.

Ruleset (documented inline below):
  Preflop:
    PREMIUM → raise_to bb*3; face a raise → re-raise to current_bet_to_match*3.
    STRONG  → raise_to bb*3 from mid/late position; call a single raise; fold to 3bet.
    MEDIUM  → call a single raise; fold to 3bet. From button, raise.
    Otherwise fold.
  Postflop (flop/turn/river):
    Top/middle pair → bet pot/2 if checkable (clamped to legal min); call if
                      facing a modest bet (to_call <= pot); fold if facing an
                      overbet (to_call > pot).
    No pair          → check if possible, else fold.

Simple TAG floor: this agent does not raise postflop. Raising is a deliberate
Phase-3+ enhancement. The Phase 2a goal is a deterministic, heterogeneous
lineup partner for the RandomAgent-driven integration test, not a competitive
opponent.
"""

from __future__ import annotations

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import TokenCounts, TurnDecisionResult
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import LegalActionSet, PlayerView

_PREMIUM_PAIRS = {"AA", "KK", "QQ"}
_PREMIUM_BROADWAY = {"AKs", "AKo"}
_STRONG_PAIRS = {"JJ", "TT", "99"}
_STRONG_BROADWAY = {"AQs", "AQo", "AJs", "KQs"}
_MEDIUM_PAIRS = {f"{r}{r}" for r in ("2", "3", "4", "5", "6", "7", "8")}
_MEDIUM_BROADWAY = {"AJo", "KJs", "QJs", "JTs"}


def _hand_key(hole: tuple[str, str]) -> str:
    """Normalize 2 cards to ranked notation: 'AKs' (suited) / 'AKo' (offsuit) / 'AA' (pair)."""
    r1, s1 = hole[0][0], hole[0][1]
    r2, s2 = hole[1][0], hole[1][1]
    order = "23456789TJQKA"
    hi, lo = (r1, r2) if order.index(r1) >= order.index(r2) else (r2, r1)
    if hi == lo:
        return hi + lo
    suited = "s" if s1 == s2 else "o"
    return f"{hi}{lo}{suited}"


def _classify_preflop(hole: tuple[str, str]) -> str:
    k = _hand_key(hole)
    if k in _PREMIUM_PAIRS or k in _PREMIUM_BROADWAY:
        return "PREMIUM"
    if k in _STRONG_PAIRS or k in _STRONG_BROADWAY:
        return "STRONG"
    if k in _MEDIUM_PAIRS or k in _MEDIUM_BROADWAY:
        return "MEDIUM"
    return "JUNK"


def _has_top_or_middle_pair(hole: tuple[str, str], community: tuple[str, ...]) -> bool:
    if not community:
        return False
    board_ranks = [c[0] for c in community]
    hole_ranks = [c[0] for c in hole]
    return any(r in board_ranks for r in hole_ranks)


def _my_position_index(view: PlayerView) -> int:
    """Button-relative action order. 0=earliest (UTG), 5=latest (BB) for 6max."""
    return (
        view.action_order_this_street.index(view.my_seat)
        if view.my_seat in view.action_order_this_street
        else 0
    )


def _find_tool_amount_bounds(legal: LegalActionSet, name: str) -> tuple[int, int]:
    spec = next(t for t in legal.tools if t.name == name)
    bounds = spec.args["amount"]
    return int(bounds["min"]), int(bounds["max"])


def _clamp(amount: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, amount))


class RuleBasedAgent(Agent):
    """B2 baseline: tight/aggressive rule dispatcher. Deterministic in `view`."""

    async def decide(self, view: PlayerView) -> TurnDecisionResult:
        action = self._pick_action(view)
        return TurnDecisionResult(
            iterations=(),
            final_action=action,
            total_tokens=TokenCounts.zero(),
            wall_time_ms=0,
            api_retry_count=0,
            illegal_action_retry_count=0,
            no_tool_retry_count=0,
            tool_usage_error_count=0,
            default_action_fallback=False,
            api_error=None,
            turn_timeout_exceeded=False,
        )

    def _pick_action(self, view: PlayerView) -> Action:
        legal: set[str] = {str(t.name) for t in view.legal_actions.tools}
        bb = view.immutable_session_params.bb
        to_call = view.current_bet_to_match - view.my_invested_this_round
        is_preflop = view.street == Street.PREFLOP

        if is_preflop:
            return self._preflop(view, legal, bb, to_call)
        return self._postflop(view, legal, to_call)

    def provider_id(self) -> str:
        return "rule_based:tag_v1"

    # --------------------------------------------------- preflop

    def _preflop(
        self,
        view: PlayerView,
        legal: set[str],
        bb: int,
        to_call: int,
    ) -> Action:
        cls = _classify_preflop(view.my_hole_cards)
        position_idx = _my_position_index(view)
        facing_raise = to_call > bb  # more than BB to call → someone raised
        facing_3bet = to_call > bb * 3  # raise × 3 → 3-bet range

        if cls == "PREMIUM":
            if facing_3bet and "raise_to" in legal:
                mn, mx = _find_tool_amount_bounds(view.legal_actions, "raise_to")
                amt = _clamp(view.current_bet_to_match * 3, mn, mx)
                return Action(tool_name="raise_to", args={"amount": amt})
            if "raise_to" in legal:
                mn, mx = _find_tool_amount_bounds(view.legal_actions, "raise_to")
                return Action(tool_name="raise_to", args={"amount": _clamp(bb * 3, mn, mx)})
            if "call" in legal:
                return Action(tool_name="call", args={})
            return self._safe_check_or_fold(legal)

        if cls == "STRONG":
            if facing_3bet:
                return self._safe_fold_or_check(legal)
            if facing_raise and "call" in legal:
                return Action(tool_name="call", args={})
            if position_idx >= 2 and "raise_to" in legal:  # CO / BTN / SB / BB
                mn, mx = _find_tool_amount_bounds(view.legal_actions, "raise_to")
                return Action(tool_name="raise_to", args={"amount": _clamp(bb * 3, mn, mx)})
            if "call" in legal:
                return Action(tool_name="call", args={})
            return self._safe_check_or_fold(legal)

        if cls == "MEDIUM":
            if facing_3bet:
                return self._safe_fold_or_check(legal)
            if facing_raise and "call" in legal:
                return Action(tool_name="call", args={})
            if position_idx >= 3 and "raise_to" in legal:  # BTN / SB / BB
                mn, mx = _find_tool_amount_bounds(view.legal_actions, "raise_to")
                return Action(tool_name="raise_to", args={"amount": _clamp(bb * 3, mn, mx)})
            if "check" in legal:
                return Action(tool_name="check", args={})
            if "call" in legal and to_call <= bb:
                return Action(tool_name="call", args={})
            return self._safe_check_or_fold(legal)

        # JUNK
        if "check" in legal:
            return Action(tool_name="check", args={})
        if "fold" in legal:
            return Action(tool_name="fold", args={})
        if "call" in legal:
            return Action(tool_name="call", args={})
        # Phase-2a-audit: preserve always-legal invariant when only all_in
        # remains in the set (pokerkit 0.7.3 doesn't emit this today, but the
        # prior `return fold` would have been illegal if it ever did).
        if "all_in" in legal:
            return Action(tool_name="all_in", args={})
        return Action(tool_name="fold", args={})

    # --------------------------------------------------- postflop

    def _postflop(self, view: PlayerView, legal: set[str], to_call: int) -> Action:
        has_pair = _has_top_or_middle_pair(view.my_hole_cards, view.community)
        pot_half = max(1, view.pot // 2)

        if has_pair:
            if to_call <= 0 and "bet" in legal:
                mn, mx = _find_tool_amount_bounds(view.legal_actions, "bet")
                return Action(tool_name="bet", args={"amount": _clamp(pot_half, mn, mx)})
            if to_call > 0 and to_call > view.pot and "fold" in legal:
                return Action(tool_name="fold", args={})
            if "call" in legal:
                return Action(tool_name="call", args={})
            return self._safe_check_or_fold(legal)

        # No pair
        if to_call <= 0 and "check" in legal:
            return Action(tool_name="check", args={})
        return self._safe_fold_or_check(legal)

    # --------------------------------------------------- fallbacks

    @staticmethod
    def _safe_check_or_fold(legal: set[str]) -> Action:
        if "check" in legal:
            return Action(tool_name="check", args={})
        if "fold" in legal:
            return Action(tool_name="fold", args={})
        if "call" in legal:
            return Action(tool_name="call", args={})
        # Phase-2a-audit: pokerkit 0.7.3 never emits {"all_in"}-only legal sets
        # today (see `compute_legal_tool_set`), but if it did the prior fallback
        # would have returned an illegal `fold`. Cover the case explicitly.
        if "all_in" in legal:
            return Action(tool_name="all_in", args={})
        return Action(tool_name="fold", args={})

    @staticmethod
    def _safe_fold_or_check(legal: set[str]) -> Action:
        if "fold" in legal:
            return Action(tool_name="fold", args={})
        if "check" in legal:
            return Action(tool_name="check", args={})
        if "call" in legal:
            return Action(tool_name="call", args={})
        if "all_in" in legal:
            return Action(tool_name="all_in", args={})
        return Action(tool_name="fold", args={})

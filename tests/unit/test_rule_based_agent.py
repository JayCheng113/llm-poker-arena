"""Tests for RuleBasedAgent (B2 baseline) — rule dispatch, not play quality."""
from __future__ import annotations

import asyncio
from typing import Literal, cast

from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)


def _act(agent: RuleBasedAgent, view: PlayerView) -> Action:
    """Phase 3a helper: call async decide() and unwrap to Action."""
    result = asyncio.run(agent.decide(view))
    assert result.final_action is not None
    return result.final_action

_ToolName = Literal["fold", "check", "call", "bet", "raise_to", "all_in"]


def _params() -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=False, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _seats(position_of_actor: str = "UTG") -> tuple[SeatPublicInfo, ...]:
    return tuple(
        SeatPublicInfo(
            seat=i, label=f"P{i}",
            position_short=position_of_actor if i == 3 else "BB",
            position_full="pos",
            stack=10_000, invested_this_hand=0, invested_this_round=0, status="in_hand",
        )
        for i in range(6)
    )


def _view(
    *,
    hole: tuple[str, str],
    street: Street = Street.PREFLOP,
    current_bet_to_match: int = 100,
    my_invested_this_round: int = 0,
    legal_names: tuple[str, ...] = ("fold", "call", "raise_to"),
    raise_min_max: tuple[int, int] = (200, 10_000),
    community: tuple[str, ...] = (),
    position: str = "UTG",
) -> PlayerView:
    tools = []
    for name in legal_names:
        tn = cast(_ToolName, name)
        if name in ("bet", "raise_to"):
            tools.append(ActionToolSpec(
                name=tn,
                args={"amount": {"min": raise_min_max[0], "max": raise_min_max[1]}},
            ))
        else:
            tools.append(ActionToolSpec(name=tn, args={}))
    to_call = max(0, current_bet_to_match - my_invested_this_round)
    pot_at_call = 150
    pot_odds = to_call / (pot_at_call + to_call) if to_call > 0 else None
    return PlayerView(
        my_seat=3, my_hole_cards=hole, community=community,
        pot=pot_at_call, sidepots=(), my_stack=10_000,
        my_invested_this_hand=my_invested_this_round,
        my_invested_this_round=my_invested_this_round,
        current_bet_to_match=current_bet_to_match,
        to_call=to_call, pot_odds_required=pot_odds, effective_stack=10_000,
        seats_public=_seats(position), opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=LegalActionSet(tools=tuple(tools)),
        opponent_stats={},
        hand_id=1, street=street, button_seat=0,
        turn_seed=1, immutable_session_params=_params(),
    )


def test_premium_preflop_raises_from_utg() -> None:
    agent = RuleBasedAgent()
    v = _view(hole=("As", "Ad"))  # AA
    act = _act(agent, v)
    assert act.tool_name == "raise_to"
    # bb × 3 = 300 target
    assert act.args["amount"] == 300


def test_junk_preflop_folds_from_utg() -> None:
    agent = RuleBasedAgent()
    v = _view(hole=("7c", "2d"))  # 72o junk
    act = _act(agent, v)
    assert act.tool_name == "fold"


def test_medium_hand_folds_to_3bet_from_utg() -> None:
    agent = RuleBasedAgent()
    v = _view(
        hole=("8h", "8d"),  # 88 medium
        current_bet_to_match=900,  # a 3bet-sized raise faced
        legal_names=("fold", "call", "raise_to"),
        raise_min_max=(1800, 10_000),
    )
    act = _act(agent, v)
    assert act.tool_name == "fold"


def test_medium_hand_calls_single_raise_from_utg() -> None:
    agent = RuleBasedAgent()
    v = _view(
        hole=("9h", "9d"),
        current_bet_to_match=300,  # standard 3bb raise
        legal_names=("fold", "call", "raise_to"),
        raise_min_max=(600, 10_000),
    )
    act = _act(agent, v)
    assert act.tool_name == "call"


def test_postflop_top_pair_bets_when_checkable_clamped_to_min() -> None:
    """Top pair + checkable spot: agent bets pot/2, clamped to legal min.

    pot=150, pot/2=75, but bet_min=bb=100 per NLHE — pot/2 is BELOW min, so
    the agent clamps up to 100. Exercises the `_clamp(target, min, max)` path.
    """
    agent = RuleBasedAgent()
    v = _view(
        hole=("As", "Kd"),  # AKo
        street=Street.FLOP,
        current_bet_to_match=0,  # checked to me
        my_invested_this_round=0,
        legal_names=("check", "bet"),
        community=("Ah", "8c", "2d"),  # top pair aces
        raise_min_max=(100, 10_000),
    )
    act = _act(agent, v)
    assert act.tool_name == "bet"
    # pot/2 = 75 but min = 100 → clamp up to 100
    assert act.args["amount"] == 100


def test_postflop_missed_folds_when_facing_bet() -> None:
    agent = RuleBasedAgent()
    v = _view(
        hole=("5s", "6d"),  # complete miss
        street=Street.FLOP,
        current_bet_to_match=200,
        my_invested_this_round=0,
        legal_names=("fold", "call", "raise_to"),
        community=("Ah", "Kc", "Qd"),
        raise_min_max=(400, 10_000),
    )
    act = _act(agent, v)
    assert act.tool_name == "fold"


def test_postflop_missed_checks_when_checkable() -> None:
    agent = RuleBasedAgent()
    v = _view(
        hole=("5s", "6d"),
        street=Street.FLOP,
        current_bet_to_match=0,
        my_invested_this_round=0,
        legal_names=("check", "bet"),
        community=("Ah", "Kc", "Qd"),
        raise_min_max=(100, 10_000),
    )
    act = _act(agent, v)
    assert act.tool_name == "check"


def test_returned_action_is_always_in_legal_set() -> None:
    agent = RuleBasedAgent()
    import random
    rng = random.Random(42)
    ranks = "23456789TJQKA"
    suits = "cdhs"
    for _ in range(200):
        c1 = rng.choice(ranks) + rng.choice(suits)
        c2 = rng.choice(ranks) + rng.choice(suits)
        if c1 == c2:
            continue
        v = _view(hole=(c1, c2))
        act = _act(agent, v)
        names = {t.name for t in v.legal_actions.tools}
        assert act.tool_name in names, (c1, c2, act.tool_name, names)


def test_provider_id_starts_with_rule_based() -> None:
    assert RuleBasedAgent().provider_id().startswith("rule_based")


def test_rule_based_falls_back_to_all_in_when_only_all_in_legal() -> None:
    """Phase-2a-audit: when legal set is {all_in} only, the agent must return
    an action in the legal set. Prior fallback would have returned an illegal
    `fold`. pokerkit 0.7.3 doesn't emit this legal shape today, but the
    always-legal invariant should hold regardless.
    """
    agent = RuleBasedAgent()

    # Junk preflop view: JUNK branch previously fell through to an illegal fold.
    junk_v = _view(
        hole=("7c", "2d"),
        legal_names=("all_in",),
    )
    act = _act(agent, junk_v)
    assert act.tool_name == "all_in"

    # Postflop missed-hand view: hits `_safe_fold_or_check` fallback.
    flop_v = _view(
        hole=("5s", "6d"),
        street=Street.FLOP,
        community=("Ah", "Kc", "Qd"),
        current_bet_to_match=10_000,
        my_invested_this_round=0,
        legal_names=("all_in",),
    )
    act = _act(agent, flop_v)
    assert act.tool_name == "all_in"

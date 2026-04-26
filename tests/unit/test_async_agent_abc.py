"""Tests for the Phase 3a async Agent ABC migration."""

from __future__ import annotations

import asyncio
import inspect

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import TurnDecisionResult
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)


def _params() -> SessionParamsView:
    return SessionParamsView(
        num_players=6,
        sb=50,
        bb=100,
        starting_stack=10_000,
        max_utility_calls=5,
        rationale_required=True,
        enable_math_tools=False,
        enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _seats() -> tuple[SeatPublicInfo, ...]:
    return tuple(
        SeatPublicInfo(
            seat=i,
            label=f"P{i}",
            position_short="UTG",
            position_full="x",
            stack=10_000,
            invested_this_hand=0,
            invested_this_round=0,
            status="in_hand",
        )
        for i in range(6)
    )


def _view(legal: LegalActionSet) -> PlayerView:
    return PlayerView(
        my_seat=3,
        my_hole_cards=("As", "Kd"),
        community=(),
        pot=150,
        sidepots=(),
        my_stack=10_000,
        my_invested_this_hand=0,
        my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100,
        pot_odds_required=0.4,
        effective_stack=10_000,
        seats_public=_seats(),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(),
        hand_history=(),
        legal_actions=legal,
        opponent_stats={},
        hand_id=1,
        street=Street.PREFLOP,
        button_seat=0,
        turn_seed=42,
        immutable_session_params=_params(),
    )


def test_agent_decide_is_async() -> None:
    """spec §4.1: Agent.decide must be a coroutine function."""
    assert inspect.iscoroutinefunction(Agent.decide)


def test_random_agent_decide_returns_turn_decision_result() -> None:
    legal = LegalActionSet(
        tools=(
            ActionToolSpec(name="fold", args={}),
            ActionToolSpec(name="call", args={}),
        )
    )
    agent = RandomAgent()
    result: TurnDecisionResult = asyncio.run(agent.decide(_view(legal)))
    assert isinstance(result, TurnDecisionResult)
    assert result.final_action is not None
    assert result.final_action.tool_name in {"fold", "call"}
    assert result.iterations == ()
    assert result.api_error is None
    assert result.default_action_fallback is False


def test_rule_based_agent_returns_turn_decision_result() -> None:
    """RuleBasedAgent picks AA for premium → raise_to."""
    from llm_poker_arena.engine.views import (
        ActionToolSpec as Spec,
    )
    from llm_poker_arena.engine.views import (
        LegalActionSet as L,
    )

    legal = L(
        tools=(
            Spec(name="fold", args={}),
            Spec(name="call", args={}),
            Spec(name="raise_to", args={"amount": {"min": 200, "max": 10_000}}),
        )
    )
    view = PlayerView(
        my_seat=3,
        my_hole_cards=("As", "Ad"),  # AA — PREMIUM
        community=(),
        pot=150,
        sidepots=(),
        my_stack=10_000,
        my_invested_this_hand=0,
        my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100,
        pot_odds_required=0.4,
        effective_stack=10_000,
        seats_public=_seats(),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(),
        hand_history=(),
        legal_actions=legal,
        opponent_stats={},
        hand_id=1,
        street=Street.PREFLOP,
        button_seat=0,
        turn_seed=42,
        immutable_session_params=_params(),
    )
    agent = RuleBasedAgent()
    result = asyncio.run(agent.decide(view))
    assert isinstance(result, TurnDecisionResult)
    assert result.final_action is not None
    assert result.final_action.tool_name == "raise_to"


def test_human_cli_agent_keeps_input_io_contract() -> None:
    """HumanCLIAgent must still accept input/output streams in __init__."""
    import io

    from llm_poker_arena.agents.human_cli import HumanCLIAgent

    a = HumanCLIAgent(input_stream=io.StringIO("fold\n"), output_stream=io.StringIO())
    assert a.provider_id() == "human:cli_v1"

"""Tests for LLMAgent's K=0 ReAct loop (Phase 3a)."""
from __future__ import annotations

import asyncio

import pytest

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.provider_base import (
    ProviderPermanentError,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    TokenCounts,
    ToolCall,
)
from llm_poker_arena.engine.legal_actions import Action
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
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=False, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _seats() -> tuple[SeatPublicInfo, ...]:
    return tuple(
        SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                       position_full="x", stack=10_000,
                       invested_this_hand=0, invested_this_round=0,
                       status="in_hand")
        for i in range(6)
    )


def _view(legal: LegalActionSet) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=0.4, effective_stack=10_000,
        seats_public=_seats(), opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=legal, opponent_stats={},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=_params(),
    )


def _resp(*tool_calls: ToolCall, stop_reason: str = "tool_use",
          text: str = "") -> LLMResponse:
    return LLMResponse(
        provider="mock", model="m1",
        stop_reason=stop_reason,  # type: ignore[arg-type]
        tool_calls=tuple(tool_calls), text_content=text,
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


def test_happy_path_first_response_is_legal_action() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="fold", args={}, tool_use_id="t1")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="fold", args={})
    assert result.iterations and len(result.iterations) == 1
    assert result.api_retry_count == 0
    assert result.illegal_action_retry_count == 0
    assert result.no_tool_retry_count == 0
    assert result.default_action_fallback is False
    assert result.api_error is None
    assert result.total_tokens.input_tokens == 10


def test_illegal_action_retried_once_then_recovers() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="raise_to", args={"amount": 500},
                       tool_use_id="t1")),  # illegal: not in legal set
        _resp(ToolCall(name="fold", args={}, tool_use_id="t2")),  # legal recovery
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"
    assert result.illegal_action_retry_count == 1
    assert result.default_action_fallback is False


def test_illegal_action_exhausts_retry_then_fallback() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="raise_to", args={"amount": 500}, tool_use_id="t1")),
        _resp(ToolCall(name="raise_to", args={"amount": 500}, tool_use_id="t2")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.illegal_action_retry_count == 1  # consumed budget
    assert result.default_action_fallback is True
    assert result.final_action is not None
    # Default-safe fallback: with to_call > 0 and check not legal, fold.
    assert result.final_action.tool_name == "fold"


def test_no_tool_response_retried_once_then_recovers() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        _resp(stop_reason="end_turn", text="thinking..."),  # no tool call
        _resp(ToolCall(name="fold", args={}, tool_use_id="t2")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.no_tool_retry_count == 1
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"


def test_no_tool_exhausted_falls_back_to_default_safe() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    script = MockResponseScript(responses=(
        _resp(stop_reason="end_turn", text="..."),
        _resp(stop_reason="end_turn", text="still thinking..."),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.no_tool_retry_count == 1
    assert result.default_action_fallback is True


def test_transient_error_retried_once_then_recovers() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(
        responses=(_resp(ToolCall(name="fold", args={}, tool_use_id="t1")),),
        errors_at_step={0: ProviderTransientError("simulated 503")},
    )
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.api_retry_count == 1
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"


def test_transient_error_exhausted_returns_api_error() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(
        responses=(),
        errors_at_step={
            0: ProviderTransientError("503-1"),
            1: ProviderTransientError("503-2"),
        },
    )
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.api_retry_count == 1
    assert result.api_error is not None
    assert result.api_error.type == "ProviderTransientError"
    assert result.final_action is None


def test_permanent_error_immediately_returns_api_error_no_retry() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(
        responses=(),
        errors_at_step={0: ProviderPermanentError("400 bad request")},
    )
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.api_retry_count == 0
    assert result.api_error is not None
    assert result.api_error.type == "ProviderPermanentError"
    assert result.final_action is None


def test_total_turn_timeout_returns_api_error() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))

    class SlowMock(MockLLMProvider):
        async def complete(self, **_kw):  # type: ignore[override]
            await asyncio.sleep(2.0)
            raise RuntimeError("unreachable")

    provider = SlowMock(script=MockResponseScript(responses=()))
    agent = LLMAgent(
        provider=provider, model="m1", temperature=0.7,
        total_turn_timeout_sec=0.1,
    )
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.turn_timeout_exceeded is True
    assert result.api_error is not None
    assert result.api_error.type == "TotalTurnTimeout"
    assert result.final_action is None


def test_multi_tool_call_response_increments_tool_usage_error_count() -> None:
    """Multi tool_use blocks per response is misuse → counted + retry."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    multi_tool_response = LLMResponse(
        provider="mock", model="m1", stop_reason="tool_use",
        tool_calls=(
            ToolCall(name="fold", args={}, tool_use_id="t1a"),
            ToolCall(name="call", args={}, tool_use_id="t1b"),
        ),
        text_content="", tokens=TokenCounts(input_tokens=10, output_tokens=5,
                                             cache_read_input_tokens=0,
                                             cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )
    single_recovery = _resp(ToolCall(name="fold", args={}, tool_use_id="t2"))
    script = MockResponseScript(responses=(multi_tool_response, single_recovery))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.tool_usage_error_count == 1
    assert result.illegal_action_retry_count == 1  # consumed 1 retry slot
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"
    assert result.default_action_fallback is False


def test_action_tool_specs_fails_fast_on_missing_bounds() -> None:
    """No silent default bounds. raise_to without amount range → ValueError."""
    from llm_poker_arena.agents.llm.llm_agent import _action_tool_specs
    bad_legal = LegalActionSet(tools=(
        ActionToolSpec(name="raise_to", args={}),
    ))
    view = _view(bad_legal)
    with pytest.raises(ValueError, match="missing amount bounds"):
        _action_tool_specs(view)

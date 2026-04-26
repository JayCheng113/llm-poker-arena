"""K+1 ReAct loop tests (Phase 3c-math).

Phase 3a/3b LLMAgent runs K=0 (one action step + retries). Phase 3c-math
widens to K+1: up to `max_utility_calls` utility-tool calls before the
forced action commit. These tests use MockLLMProvider to drive
deterministic [utility, utility, action] sequences and assert the
IterationRecord chain populates tool_result correctly.
"""
from __future__ import annotations

import asyncio
from typing import Any

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
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


def _params(*, max_utility_calls: int = 5) -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=max_utility_calls, rationale_required=True,
        enable_math_tools=True, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _view(legal: LegalActionSet,
          params: SessionParamsView | None = None) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=250, sidepots=(), my_stack=9_750,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=100 / 350,
        effective_stack=9_750,
        seats_public=tuple(
            SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                           position_full="x", stack=10_000,
                           invested_this_hand=0, invested_this_round=0,
                           status="in_hand") for i in range(6)
        ),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=legal, opponent_stats={},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=params or _params(),
    )


def _resp(*tool_calls: ToolCall, text: str = "rationale") -> LLMResponse:
    return LLMResponse(
        provider="mock", model="m1", stop_reason="tool_use",
        tool_calls=tuple(tool_calls), text_content=text,
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


def test_k1_happy_utility_then_action() -> None:
    """LLM calls pot_odds, then commits fold. IterationRecord chain has
    2 entries: first with tool_call.name='pot_odds' + tool_result, second
    with tool_call.name='fold' + tool_result=None."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="pot_odds", args={}, tool_use_id="tu1")),
        _resp(ToolCall(name="fold", args={}, tool_use_id="tu2")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="fold", args={})
    assert len(result.iterations) == 2
    util_iter, action_iter = result.iterations
    assert util_iter.tool_call is not None
    assert util_iter.tool_call.name == "pot_odds"
    assert util_iter.tool_result == {"value": 100 / 350}
    assert action_iter.tool_call is not None
    assert action_iter.tool_call.name == "fold"
    assert action_iter.tool_result is None
    assert result.tool_usage_error_count == 0


def test_k1_two_utility_then_action() -> None:
    """LLM chains pot_odds → spr → action_call."""
    legal = LegalActionSet(tools=(
        ActionToolSpec(name="fold", args={}),
        ActionToolSpec(name="call", args={}),
    ))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="pot_odds", args={"to_call": 600, "pot": 850},
                       tool_use_id="tu1")),
        _resp(ToolCall(name="spr", args={}, tool_use_id="tu2")),
        _resp(ToolCall(name="call", args={}, tool_use_id="tu3")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="call", args={})
    assert len(result.iterations) == 3
    pot_iter, spr_iter, action_iter = result.iterations
    assert pot_iter.tool_result == {"value": 600 / 1450}
    assert spr_iter.tool_result == {"value": 9_750 / 250}
    assert action_iter.tool_result is None


def test_k1_utility_with_bad_args_increments_error_count() -> None:
    """ToolDispatchError → tool_usage_error_count += 1; loop continues; LLM
    sees error tool_result and recovers on next iteration. Spec §4.2 lines
    1019-1021. Does NOT consume any retry budget (Q4 brainstorming decision)."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        # Bad args first.
        _resp(ToolCall(name="pot_odds", args={"to_call": -50},
                       tool_use_id="tu_bad")),
        # Then commit.
        _resp(ToolCall(name="fold", args={}, tool_use_id="tu2")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="fold", args={})
    assert result.tool_usage_error_count == 1
    # Retry budgets all stay at 0 — utility errors don't consume them.
    assert result.api_retry_count == 0
    assert result.illegal_action_retry_count == 0
    assert result.no_tool_retry_count == 0
    assert len(result.iterations) == 2
    bad_iter = result.iterations[0]
    assert bad_iter.tool_result is not None
    assert "error" in bad_iter.tool_result


def test_k1_unknown_tool_name_consumes_illegal_retry() -> None:
    """LLM hallucinates a tool name not in either action_tools OR
    utility_names → falls through both branches to the illegal-action path
    per spec §4.2 line 1027 (codex audit IMPORTANT-1 fix). Consumes
    illegal_action_retry budget, NOT tool_usage_error_count."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="hallucinated_equity", args={"villain": "AKs"},
                       tool_use_id="tu_h")),
        _resp(ToolCall(name="fold", args={}, tool_use_id="tu2")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="fold", args={})
    # Unknown tool name is treated as illegal action (spec §4.2 line 1027),
    # NOT a utility-tool error. tool_usage_error_count stays at 0.
    assert result.illegal_action_retry_count == 1
    assert result.tool_usage_error_count == 0


def test_k1_mixed_utility_and_action_in_one_response_is_misuse() -> None:
    """Codex audit NIT-2: when the response has BOTH a utility tool_call AND
    an action tool_call (multi-tool-call response), the existing multi-tool-
    call branch in _decide_inner fires BEFORE the utility-dispatch branch
    (the dispatch branch only inspects response.tool_calls[0] AFTER the
    multi-call check). The whole response is rejected as protocol misuse;
    no action is accepted from it; tool_usage_error_count increments and
    tool_usage_retry budget is consumed."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        # Bad multi-call: pot_odds + fold in one response.
        _resp(
            ToolCall(name="pot_odds", args={}, tool_use_id="tu_p"),
            ToolCall(name="fold", args={}, tool_use_id="tu_f"),
        ),
        # Recovery response with single tool_call.
        _resp(ToolCall(name="fold", args={}, tool_use_id="tu_recover")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="fold", args={})
    # The mixed response was rejected as misuse → tool_usage_error_count=1,
    # tool_usage_retry consumed=1 (Phase 3d's separate retry slot).
    assert result.tool_usage_error_count == 1


def test_k1_max_utility_calls_exhaustion_falls_back() -> None:
    """LLM keeps calling utility tools past max_utility_calls → fallback."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    # max_utility_calls=2; LLM tries pot_odds 3 times.
    params = _params(max_utility_calls=2)
    responses = tuple(
        _resp(ToolCall(name="pot_odds", args={}, tool_use_id=f"tu{i}"))
        for i in range(10)
    )
    script = MockResponseScript(responses=responses)
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal, params=params)))
    # After 2 utility calls, LLM still calls pot_odds → no_tool_retry budget
    # catches it (final-step pressure in Task 8 will short-circuit this; for
    # Task 7 the loop just exhausts MAX_STEPS and falls back).
    assert result.default_action_fallback is True
    # At least 2 utility iterations happened.
    util_count = sum(
        1 for it in result.iterations
        if it.tool_call is not None and it.tool_call.name == "pot_odds"
    )
    assert util_count >= 2

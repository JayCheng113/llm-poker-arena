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
          text: str = "rationale: tactical decision") -> LLMResponse:
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
    assert len(result.iterations) == 1
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
        async def complete(self, **_kw: object) -> LLMResponse:  # type: ignore[override]
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
    # Phase 3d: tool_usage_retry is independent from illegal_retry (spec
    # §4.1 BR2-05). Multi-tool retry consumes the new tool_usage_retry slot,
    # leaving illegal_retry untouched.
    assert result.illegal_action_retry_count == 0
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"
    assert result.default_action_fallback is False


def test_api_error_detail_is_redacted_when_provider_msg_contains_key() -> None:
    """Codex B9: provider exceptions may carry API key fragments. The
    persisted ApiErrorInfo.detail MUST be redacted before reaching the
    AgentViewSnapshot."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    fake_key = "sk-ant-api03-fake-leaked-key-aaaaaa"
    err = ProviderPermanentError(f"401 unauthorized: bad key {fake_key}")
    script = MockResponseScript(
        responses=(),
        errors_at_step={0: err},
    )
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.api_error is not None
    assert fake_key not in result.api_error.detail
    assert "<REDACTED_API_KEY>" in result.api_error.detail


def test_action_tool_specs_fails_fast_on_missing_bounds() -> None:
    """No silent default bounds. raise_to without amount range → ValueError."""
    from llm_poker_arena.agents.llm.llm_agent import _action_tool_specs
    bad_legal = LegalActionSet(tools=(
        ActionToolSpec(name="raise_to", args={}),
    ))
    view = _view(bad_legal)
    with pytest.raises(ValueError, match="missing amount bounds"):
        _action_tool_specs(view)


def test_tool_usage_error_does_not_consume_illegal_retry_budget() -> None:
    """spec §4.1 BR2-05: tool_usage_error_count and illegal_retry have
    independent budgets. After a multi-tool-call (consumes tool_usage slot),
    a subsequent illegal-action attempt must STILL have its own retry slot."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    multi_tool_response = LLMResponse(
        provider="mock", model="m1", stop_reason="tool_use",
        tool_calls=(
            ToolCall(name="fold", args={}, tool_use_id="t1a"),
            ToolCall(name="call", args={}, tool_use_id="t1b"),
        ),
        text_content="reasoning here",
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )
    illegal_response = _resp(
        ToolCall(name="raise_to", args={"amount": 500},
                 tool_use_id="t2"),
    )
    legal_recovery = _resp(
        ToolCall(name="fold", args={}, tool_use_id="t3"),
    )
    script = MockResponseScript(responses=(
        multi_tool_response, illegal_response, legal_recovery,
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.tool_usage_error_count == 1
    assert result.illegal_action_retry_count == 1
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"
    assert result.default_action_fallback is False


def test_rationale_required_strict_mode_retries_on_empty_text() -> None:
    """When rationale_required=True (default), an LLM response with tool_use
    but no text content triggers a 'rationale missing' retry (consumes the
    no_tool_retry slot — text-only emit is the same family of error)."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    no_text_response = LLMResponse(
        provider="mock", model="m1", stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t1"),),
        text_content="",
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )
    recovery = LLMResponse(
        provider="mock", model="m1", stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t2"),),
        text_content="I am folding because 9-5o is weak.",
        tokens=TokenCounts(input_tokens=10, output_tokens=10,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )
    script = MockResponseScript(responses=(no_text_response, recovery))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.no_tool_retry_count == 1
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"


def test_rationale_required_false_accepts_empty_text() -> None:
    """When the profile has rationale_required=False, an empty-text response
    with a legal tool call is accepted directly (no retry)."""
    import tempfile
    from pathlib import Path

    from llm_poker_arena.agents.llm.prompt_profile import PromptProfile

    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
        f.write(
            'name = "no-rat"\nlanguage = "en"\npersona = ""\n'
            'reasoning_prompt = "light"\nrationale_required = false\n'
            'stats_min_samples = 30\ncard_format = "Ah Kh"\n'
            'player_label_format = "Player_{seat}"\n'
            'position_label_format = "{short} ({full})"\n'
            '[templates]\nsystem = "system.j2"\nuser = "user.j2"\n'
        )
        toml_path = Path(f.name)
    profile = PromptProfile.from_toml(toml_path)
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        LLMResponse(
            provider="mock", model="m1", stop_reason="tool_use",
            tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t1"),),
            text_content="",
            tokens=TokenCounts(input_tokens=10, output_tokens=5,
                               cache_read_input_tokens=0,
                               cache_creation_input_tokens=0),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        ),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7,
                     prompt_profile=profile)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.no_tool_retry_count == 0
    assert result.final_action is not None


def test_llm_agent_renders_my_position_short_in_user_prompt() -> None:
    """Regression for Phase 3a smoke finding: Claude was inferring the
    wrong position from raw seat indices. The Jinja-rendered user prompt
    must spell out my_position_short directly."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    captured: list[list[dict[str, object]]] = []
    captured_systems: list[str | None] = []

    class Capturing(MockLLMProvider):
        async def complete(self, **kw: Any) -> LLMResponse:  # type: ignore[override]
            captured.append(list(kw["messages"]))
            captured_systems.append(kw.get("system"))
            return await super().complete(**kw)

    script = MockResponseScript(responses=(
        _resp(ToolCall(name="fold", args={}, tool_use_id="t1")),
    ))
    provider = Capturing(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action is not None

    # System prompt must be passed via system= (not folded into user message).
    sys_text = captured_systems[0]
    assert sys_text is not None
    assert "No-Limit Texas Hold'em 6-max" in sys_text
    assert "First write reasoning" in sys_text  # rationale_required default

    # User message must contain the rendered template fields.
    first = captured[0][0]
    assert first["role"] == "user"
    user_text = first["content"]
    assert isinstance(user_text, str)
    assert "my_position_short:" in user_text
    # _seats() makes everyone "UTG" so position_short for seat 3 is "UTG"
    assert "UTG" in user_text
    assert "to_call: 100" in user_text
    assert "pot_odds_required: 0.4" in user_text


def test_multi_tool_retry_replies_to_all_tool_use_ids_not_just_first() -> None:
    """Regression for codex B2: when the model returns N>1 tool_use blocks,
    Anthropic protocol requires the next user message to include a
    tool_result block for EVERY one of those tool_use_ids. Replying to
    only the first would produce a 400 on the retry request.

    We assert this by intercepting messages at the second provider call:
    after the multi-tool retry, every original tool_use_id must appear in
    the tool_result blocks.
    """
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))

    captured_messages: list[list[dict[str, object]]] = []

    multi_tool_response = LLMResponse(
        provider="mock", model="m1", stop_reason="tool_use",
        tool_calls=(
            ToolCall(name="fold", args={}, tool_use_id="tu_first"),
            ToolCall(name="call", args={}, tool_use_id="tu_second"),
            ToolCall(name="fold", args={}, tool_use_id="tu_third"),
        ),
        text_content="multi", tokens=TokenCounts(input_tokens=10, output_tokens=5,
                                                  cache_read_input_tokens=0,
                                                  cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )
    single_recovery = _resp(ToolCall(name="fold", args={}, tool_use_id="tu_recovery"))
    script = MockResponseScript(responses=(multi_tool_response, single_recovery))

    class CapturingMock(MockLLMProvider):
        async def complete(self, **kw):  # type: ignore[override, no-untyped-def]
            captured_messages.append(list(kw["messages"]))
            return await super().complete(**kw)

    provider = CapturingMock(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))

    # Sanity: 2 calls (original + retry); recovery succeeded
    assert len(captured_messages) == 2
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"

    # The retry's `messages` list must end with: assistant turn, then a user
    # turn whose content blocks include tool_result for ALL 3 tool_use_ids.
    retry_messages = captured_messages[1]
    last_user = retry_messages[-1]
    assert last_user["role"] == "user"
    content = last_user["content"]
    assert isinstance(content, list), (
        f"retry user content must be structured (list of blocks); got {content!r}"
    )
    tool_result_ids = {
        block["tool_use_id"] for block in content
        if isinstance(block, dict) and block.get("type") == "tool_result"
    }
    assert tool_result_ids == {"tu_first", "tu_second", "tu_third"}, (
        f"every tool_use_id from the prior assistant turn must have a "
        f"tool_result; got tool_result_ids={tool_result_ids}"
    )

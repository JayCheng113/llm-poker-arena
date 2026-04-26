"""Tests for HumanCLIAgent (Phase 3a async Agent ABC, sync I/O underneath)."""

from __future__ import annotations

import asyncio
import io
from typing import Literal

import pytest

from llm_poker_arena.agents.human_cli import HumanCLIAgent
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)


def _act(agent: HumanCLIAgent, view: PlayerView) -> Action:
    """Phase 3a helper: call async decide() and unwrap to Action."""
    result = asyncio.run(agent.decide(view))
    assert result.final_action is not None
    return result.final_action


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
            label=f"Player_{i}",
            position_short="UTG",
            position_full="Under the Gun",
            stack=10_000,
            invested_this_hand=0,
            invested_this_round=0,
            status="in_hand",
        )
        for i in range(6)
    )


_ToolName = Literal["fold", "check", "call", "bet", "raise_to", "all_in"]


def _view(
    *,
    legal_names: tuple[_ToolName, ...],
    raise_min_max: tuple[int, int] = (200, 10_000),
) -> PlayerView:
    tools: list[ActionToolSpec] = []
    for name in legal_names:
        if name in ("bet", "raise_to"):
            tools.append(
                ActionToolSpec(
                    name=name,
                    args={"amount": {"min": raise_min_max[0], "max": raise_min_max[1]}},
                )
            )
        else:
            tools.append(ActionToolSpec(name=name, args={}))
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
        legal_actions=LegalActionSet(tools=tuple(tools)),
        opponent_stats={},
        hand_id=1,
        street=Street.PREFLOP,
        button_seat=0,
        turn_seed=1,
        immutable_session_params=_params(),
    )


def test_fold_is_accepted_verbatim() -> None:
    """User types 'fold' → Action(tool_name='fold', args={})."""
    stdin = io.StringIO("fold\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("fold", "call", "raise_to"))
    act = _act(agent, view)
    assert act == Action(tool_name="fold", args={})


def test_check_is_accepted_verbatim() -> None:
    stdin = io.StringIO("check\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("check", "bet"))
    act = _act(agent, view)
    assert act.tool_name == "check"


def test_raise_to_prompts_for_amount_on_separate_line() -> None:
    """User types 'raise_to' then '300' on the next prompt."""
    stdin = io.StringIO("raise_to\n300\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("fold", "call", "raise_to"), raise_min_max=(200, 10_000))
    act = _act(agent, view)
    assert act.tool_name == "raise_to"
    assert act.args == {"amount": 300}


def test_bet_prompts_for_amount_on_separate_line() -> None:
    stdin = io.StringIO("bet\n500\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("check", "bet"), raise_min_max=(100, 10_000))
    act = _act(agent, view)
    assert act.tool_name == "bet"
    assert act.args == {"amount": 500}


def test_unknown_action_name_reprompts() -> None:
    """User types 'teleport' (not a valid action name) → agent complains; then types valid action."""
    stdin = io.StringIO("teleport\nfold\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("fold", "call"))
    act = _act(agent, view)
    assert act.tool_name == "fold"
    assert "not a known action" in stdout.getvalue().lower()


def test_known_action_outside_legal_set_reprompts() -> None:
    """User types 'bet' (known action) but legal set only has fold/call → reprompt."""
    stdin = io.StringIO("bet\nfold\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("fold", "call"))
    act = _act(agent, view)
    assert act.tool_name == "fold"
    assert "not in legal set" in stdout.getvalue().lower()


def test_raise_below_min_reprompts() -> None:
    """User types 'raise_to' then '50' (below min=200) → reprompt for amount."""
    stdin = io.StringIO("raise_to\n50\n400\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(
        legal_names=("fold", "call", "raise_to"),
        raise_min_max=(200, 10_000),
    )
    act = _act(agent, view)
    assert act == Action(tool_name="raise_to", args={"amount": 400})
    assert "out of" in stdout.getvalue().lower() or "below min" in stdout.getvalue().lower()


def test_amount_not_an_integer_reprompts() -> None:
    stdin = io.StringIO("raise_to\nabc\n400\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(
        legal_names=("fold", "call", "raise_to"),
        raise_min_max=(200, 10_000),
    )
    act = _act(agent, view)
    assert act.args == {"amount": 400}


def test_eof_mid_prompt_raises() -> None:
    """Unexpected stdin EOF during a prompt raises EOFError (clean propagation)."""
    stdin = io.StringIO("")  # no input
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("fold", "call"))
    with pytest.raises(EOFError):
        asyncio.run(agent.decide(view))


def test_provider_id_is_stable_and_namespaced() -> None:
    """provider_id must split into ('human', 'cli_v1') per Session convention."""
    agent = HumanCLIAgent()
    pid = agent.provider_id()
    assert pid == "human:cli_v1"
    parts = pid.split(":", 1)
    assert parts[0] == "human"
    assert parts[1] == "cli_v1"


def test_view_renders_hole_community_stack_to_output() -> None:
    """Every decide() call prints enough info for the human to act."""
    stdin = io.StringIO("fold\n")
    stdout = io.StringIO()
    agent = HumanCLIAgent(input_stream=stdin, output_stream=stdout)
    view = _view(legal_names=("fold", "call"))
    asyncio.run(agent.decide(view))
    text = stdout.getvalue()
    assert "As" in text
    assert "Kd" in text
    assert "150" in text
    assert "fold" in text
    assert "call" in text

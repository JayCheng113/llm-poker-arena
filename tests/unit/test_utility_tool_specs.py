"""Tests for utility_tool_specs — gated by SessionConfig.enable_math_tools."""
from __future__ import annotations

from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.tools import utility_tool_specs


def _view(*, enable_math_tools: bool) -> PlayerView:
    params = SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=enable_math_tools, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )
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
        legal_actions=LegalActionSet(tools=(
            ActionToolSpec(name="fold", args={}),
        )),
        opponent_stats={}, hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=params,
    )


def test_specs_empty_when_math_tools_disabled() -> None:
    v = _view(enable_math_tools=False)
    assert utility_tool_specs(v) == []


def test_specs_contains_pot_odds_and_spr_when_enabled() -> None:
    v = _view(enable_math_tools=True)
    specs = utility_tool_specs(v)
    names = {s["name"] for s in specs}
    # Phase 3c-equity adds hand_equity_vs_ranges; the dedicated assertion
    # is in test_specs_includes_hand_equity_vs_ranges_when_enabled.
    assert names == {"pot_odds", "spr", "hand_equity_vs_ranges"}


def test_pot_odds_spec_schema_shape() -> None:
    """Anthropic tool spec format. input_schema must declare optional
    integer args (LLM may call zero-arg or with one/both args)."""
    v = _view(enable_math_tools=True)
    specs = utility_tool_specs(v)
    pot_spec = next(s for s in specs if s["name"] == "pot_odds")
    assert "description" in pot_spec
    schema = pot_spec["input_schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    # Optional args: required is empty list.
    assert schema.get("required", []) == []
    # to_call + pot are integer-typed.
    props = schema["properties"]
    assert props["to_call"]["type"] == "integer"
    assert props["pot"]["type"] == "integer"


def test_spr_spec_schema_shape() -> None:
    v = _view(enable_math_tools=True)
    specs = utility_tool_specs(v)
    spr_spec = next(s for s in specs if s["name"] == "spr")
    schema = spr_spec["input_schema"]
    assert schema["type"] == "object"
    assert schema.get("required", []) == []
    props = schema["properties"]
    assert props["stack"]["type"] == "integer"
    assert props["pot"]["type"] == "integer"


def test_specs_includes_hand_equity_vs_ranges_when_enabled() -> None:
    """Phase 3c-equity adds hand_equity_vs_ranges to utility_tool_specs."""
    v = _view(enable_math_tools=True)
    specs = utility_tool_specs(v)
    names = {s["name"] for s in specs}
    assert "hand_equity_vs_ranges" in names
    equity_spec = next(s for s in specs if s["name"] == "hand_equity_vs_ranges")
    schema = equity_spec["input_schema"]
    assert schema["type"] == "object"
    # spec §5.2.3 + Q4 minimal API: only range_by_seat is exposed.
    assert "range_by_seat" in schema["properties"]
    assert schema["required"] == ["range_by_seat"]
    # range_by_seat is a dict mapping seat (additionalProperties string).
    rbs = schema["properties"]["range_by_seat"]
    assert rbs["type"] == "object"
    assert rbs["additionalProperties"]["type"] == "string"

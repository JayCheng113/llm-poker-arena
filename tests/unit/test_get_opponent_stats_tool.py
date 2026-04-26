"""get_opponent_stats tool (Phase 3c-hud Task 8)."""
from __future__ import annotations

import pytest

from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    OpponentStatsOrInsufficient,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.tools import run_utility_tool
from llm_poker_arena.tools.opponent_stats import get_opponent_stats


def _view(
    enable_hud_tool: bool = True,
    opponent_stats: dict[int, OpponentStatsOrInsufficient] | None = None,
) -> PlayerView:
    params = SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=False, enable_hud_tool=enable_hud_tool,
        opponent_stats_min_samples=30,
    )
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=0.4, effective_stack=10_000,
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
        opponent_stats=opponent_stats or {},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=params,
    )


def test_get_opponent_stats_returns_view_data() -> None:
    """Tool returns OpponentStatsOrInsufficient.model_dump for queried seat."""
    stats = {
        0: OpponentStatsOrInsufficient(
            insufficient=False, vpip=0.32, pfr=0.18,
            three_bet=0.05, af=2.1, wtsd=0.28,
        ),
    }
    view = _view(opponent_stats=stats)
    result = get_opponent_stats(view, seat=0)
    assert result["insufficient"] is False
    assert result["vpip"] == 0.32
    assert result["wtsd"] == 0.28


def test_get_opponent_stats_self_seat_raises() -> None:
    """Tool rejects seat == my_seat (no peeking at own stats via opponent
    interface — use direct view fields for self). Convention: raise
    ToolDispatchError, not return error dict."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    view = _view()
    with pytest.raises(ToolDispatchError, match="own|self"):
        get_opponent_stats(view, seat=3)  # my_seat=3


def test_get_opponent_stats_out_of_range_seat_raises() -> None:
    """seat must be in [0, num_players). seat=99 → ToolDispatchError."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    view = _view()
    with pytest.raises(ToolDispatchError, match="seat"):
        get_opponent_stats(view, seat=99)


def test_dispatcher_blocks_hud_tool_when_disabled() -> None:
    """When enable_hud_tool=False, run_utility_tool('get_opponent_stats')
    raises ToolDispatchError (gate enforced before dispatch)."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    view = _view(enable_hud_tool=False)
    with pytest.raises(ToolDispatchError, match="not enabled|disabled|enable_hud"):
        run_utility_tool(view, "get_opponent_stats", {"seat": 0})


def test_dispatcher_missing_seat_arg_raises_tool_dispatch_error() -> None:
    """codex audit BLOCKER B3: missing 'seat' arg must raise
    ToolDispatchError (not uncaught TypeError) — LLMAgent only catches
    ToolDispatchError, an uncaught TypeError would crash the turn."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    view = _view(enable_hud_tool=True)
    with pytest.raises(ToolDispatchError, match="requires 'seat'|seat"):
        run_utility_tool(view, "get_opponent_stats", {})


def test_utility_tool_specs_hud_independent_of_math() -> None:
    """codex audit IMPORTANT-9: utility_tool_specs must include HUD spec
    when enable_hud_tool=True even if enable_math_tools=False (independent
    gates). Currently covered by manually editing _view's flags."""
    from llm_poker_arena.tools.runner import utility_tool_specs

    # Math off, HUD on → only HUD spec.
    view_hud_only = _view(enable_hud_tool=True)
    # _view default enable_math_tools=False; HUD spec should appear.
    specs = utility_tool_specs(view_hud_only)
    names = [s["name"] for s in specs]
    assert "get_opponent_stats" in names
    # Math tools NOT included.
    assert "pot_odds" not in names
    assert "spr" not in names
    assert "hand_equity_vs_ranges" not in names


def test_utility_tool_specs_both_math_and_hud_enabled() -> None:
    """When both enable_math_tools=True AND enable_hud_tool=True, all 4
    utility specs appear."""
    from llm_poker_arena.tools.runner import utility_tool_specs

    # Use a custom view with both flags on.
    params = SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=True, enable_hud_tool=True,
        opponent_stats_min_samples=30,
    )
    view = PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=0.4, effective_stack=10_000,
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
    specs = utility_tool_specs(view)
    names = [s["name"] for s in specs]
    assert set(names) == {"pot_odds", "spr", "hand_equity_vs_ranges", "get_opponent_stats"}


def test_system_prompt_includes_hud_block_when_enabled() -> None:
    """codex audit IMPORTANT-9: system.j2 advertises HUD tool when
    enable_hud_tool=True."""
    from llm_poker_arena.agents.llm.prompt_profile import (
        load_default_prompt_profile,
    )
    profile = load_default_prompt_profile()
    text = profile.render_system(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        enable_math_tools=False, enable_hud_tool=True,
        opponent_stats_min_samples=30, max_utility_calls=5,
    )
    assert "get_opponent_stats" in text
    assert "30" in text  # opponent_stats_min_samples shown


def test_system_prompt_omits_hud_block_when_disabled() -> None:
    """When enable_hud_tool=False, HUD section absent from system prompt."""
    from llm_poker_arena.agents.llm.prompt_profile import (
        load_default_prompt_profile,
    )
    profile = load_default_prompt_profile()
    text = profile.render_system(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        enable_math_tools=False, enable_hud_tool=False,
        opponent_stats_min_samples=30, max_utility_calls=5,
    )
    assert "get_opponent_stats" not in text


def test_user_prompt_includes_opponent_stats_block_when_populated() -> None:
    """codex audit BLOCKER B1: user.j2 renders opponent_stats when passed."""
    from llm_poker_arena.agents.llm.prompt_profile import (
        load_default_prompt_profile,
    )
    profile = load_default_prompt_profile()
    stats = {
        0: OpponentStatsOrInsufficient(
            insufficient=False, vpip=0.32, pfr=0.18,
            three_bet=0.05, af=2.1, wtsd=0.28,
        ),
        1: OpponentStatsOrInsufficient(insufficient=True),
    }
    seats_public = [
        SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                       position_full="x", stack=10_000,
                       invested_this_hand=0, invested_this_round=0,
                       status="in_hand") for i in range(6)
    ]
    text = profile.render_user(
        hand_id=1, street="preflop", my_seat=3,
        my_position_short="UTG", my_position_full="x",
        my_hole_cards=("As", "Kd"), community=(),
        pot=150, my_stack=10_000, to_call=100,
        pot_odds_required=0.4, effective_stack=10_000,
        button_seat=0, opponent_seats_in_hand=(0, 1, 2, 4, 5),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        seats_public=seats_public,
        opponent_stats=stats,
    )
    assert "OPPONENT STATS" in text
    assert "VPIP=0.32" in text
    assert "insufficient samples" in text  # for seat 1


def test_user_prompt_omits_opponent_stats_block_when_empty() -> None:
    """When opponent_stats={} or None, user prompt has no OPPONENT STATS section."""
    from llm_poker_arena.agents.llm.prompt_profile import (
        load_default_prompt_profile,
    )
    profile = load_default_prompt_profile()
    seats_public = [
        SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                       position_full="x", stack=10_000,
                       invested_this_hand=0, invested_this_round=0,
                       status="in_hand") for i in range(6)
    ]
    text = profile.render_user(
        hand_id=1, street="preflop", my_seat=3,
        my_position_short="UTG", my_position_full="x",
        my_hole_cards=("As", "Kd"), community=(),
        pot=150, my_stack=10_000, to_call=100,
        pot_odds_required=0.4, effective_stack=10_000,
        button_seat=0, opponent_seats_in_hand=(0, 1, 2, 4, 5),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        seats_public=seats_public,
        opponent_stats={},
    )
    assert "OPPONENT STATS" not in text

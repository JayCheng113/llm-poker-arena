"""Tests for PromptProfile (Phase 3d Task 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from llm_poker_arena.agents.llm.prompt_profile import (
    PromptProfile,
    load_default_prompt_profile,
)


def test_default_profile_loads_and_has_expected_fields() -> None:
    p = load_default_prompt_profile()
    assert p.name == "default-v2"
    assert p.language == "en"
    assert p.rationale_required is True
    assert p.stats_min_samples == 30


def test_render_system_prompt_substitutes_session_params() -> None:
    p = load_default_prompt_profile()
    text = p.render_system(
        num_players=6,
        sb=50,
        bb=100,
        starting_stack=10_000,
    )
    assert "100 BB" in text
    assert "50/100" in text
    assert "First write reasoning" in text


def test_render_system_prompt_omits_rationale_when_disabled(
    tmp_path: Path,
) -> None:
    """Custom profile with rationale_required=False uses the else branch."""
    custom_toml = tmp_path / "no_rationale.toml"
    custom_toml.write_text(
        'name = "no-rat"\n'
        'language = "en"\n'
        'persona = ""\n'
        'reasoning_prompt = "light"\n'
        "rationale_required = false\n"
        "stats_min_samples = 30\n"
        'card_format = "Ah Kh"\n'
        'player_label_format = "Player_{seat}"\n'
        'position_label_format = "{short} ({full})"\n'
        "[templates]\n"
        'system = "system.j2"\n'
        'user = "user.j2"\n'
    )
    p = PromptProfile.from_toml(custom_toml)
    text = p.render_system(
        num_players=6,
        sb=50,
        bb=100,
        starting_stack=10_000,
    )
    assert "First write reasoning" not in text
    assert "may optionally write brief reasoning" in text


def test_render_user_prompt_includes_my_position_short() -> None:
    """Phase 3a smoke test showed Claude inferring wrong positions; the
    prompt must now spell out my_position_short directly."""
    p = load_default_prompt_profile()
    text = p.render_user(
        hand_id=0,
        street="preflop",
        my_seat=3,
        my_position_short="UTG",
        my_position_full="Under the Gun",
        my_hole_cards=("9c", "5h"),
        community=(),
        pot=150,
        my_stack=10_000,
        to_call=100,
        pot_odds_required=0.4,
        effective_stack=10_000,
        button_seat=0,
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        seats_public=(),
    )
    assert "my_position_short: UTG" in text
    assert "my_position_full: Under the Gun" in text
    assert "to_call: 100" in text
    assert "pot_odds_required: 0.4" in text
    assert "effective_stack: 10000" in text
    assert "9c 5h" in text
    assert "(none)" in text


def test_render_user_prompt_includes_seats_table() -> None:
    from llm_poker_arena.engine.views import SeatPublicInfo

    seats = tuple(
        SeatPublicInfo(
            seat=i,
            label=f"P{i}",
            position_short=("BTN", "SB", "BB", "UTG", "HJ", "CO")[i],
            position_full="x",
            stack=10_000 - (50 if i == 1 else 100 if i == 2 else 0),
            invested_this_hand=0,
            invested_this_round=(50 if i == 1 else 100 if i == 2 else 0),
            status="in_hand",
        )
        for i in range(6)
    )
    p = load_default_prompt_profile()
    text = p.render_user(
        hand_id=0,
        street="preflop",
        my_seat=3,
        my_position_short="UTG",
        my_position_full="Under the Gun",
        my_hole_cards=("As", "Kd"),
        community=(),
        pot=150,
        my_stack=10_000,
        to_call=100,
        pot_odds_required=0.4,
        effective_stack=10_000,
        button_seat=0,
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        seats_public=seats,
    )
    assert "← me" in text
    assert "(BTN)" in text
    assert "stack=9950" in text


def test_render_user_prompt_respects_rationale_required(tmp_path: Path) -> None:
    """The user.j2 "explain your reasoning, then call exactly one tool"
    line is the per-turn equivalent of the system.j2 reasoning block,
    and must track the same per-profile flag — otherwise GPT-5 reasoning
    models that we explicitly switch to rationale_required=False still
    receive an explicit "explain your reasoning" instruction every turn,
    which both wastes their tokens and re-triggers OpenAI's
    invalid_prompt moderation. Regression test for the second 30-hand
    re-run censoring hand 2 / seat 2 (codex 2026-04-27 follow-up)."""
    user_kwargs: dict[str, Any] = dict(  # noqa: C408
        hand_id=0, street="preflop", my_seat=3, my_position_short="UTG",
        my_position_full="Under the Gun", my_hole_cards=("As", "Kd"),
        community=(), pot=150, my_stack=10_000, to_call=100,
        pot_odds_required=0.4, effective_stack=10_000, button_seat=0,
        opponent_seats_in_hand=(0,), seats_yet_to_act_after_me=(),
        seats_public=(),
    )

    # Default (rationale_required=True): the explain instruction is shown.
    default_profile = load_default_prompt_profile()
    default_text = default_profile.render_user(**user_kwargs)
    assert "Briefly explain your reasoning" in default_text

    # Custom toml flips the flag — the per-turn instruction collapses.
    custom_toml = tmp_path / "no_rat.toml"
    custom_toml.write_text(
        'name = "no-rat"\nlanguage = "en"\npersona = ""\n'
        'reasoning_prompt = "light"\nrationale_required = false\n'
        'stats_min_samples = 30\ncard_format = "Ah Kh"\n'
        'player_label_format = "Player_{seat}"\n'
        'position_label_format = "{short} ({full})"\n'
        '[templates]\nsystem = "system.j2"\nuser = "user.j2"\n'
    )
    no_rat_profile = PromptProfile.from_toml(custom_toml)
    no_rat_text = no_rat_profile.render_user(**user_kwargs)
    assert "Briefly explain your reasoning" not in no_rat_text
    assert "Call exactly one tool" in no_rat_text

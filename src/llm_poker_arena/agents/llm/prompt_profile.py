"""PromptProfile: TOML-defined Jinja prompt config for LLMAgent (spec §6.3)."""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DEFAULT_TOML = _PROMPTS_DIR / "default-v2.toml"


@dataclass(frozen=True)
class PromptProfile:
    """Spec §6.3 PromptProfile. Holds config + renders system/user prompts."""

    name: str
    language: str
    persona: str
    reasoning_prompt: str
    rationale_required: bool
    stats_min_samples: int
    card_format: str
    player_label_format: str
    position_label_format: str
    system_template: str
    user_template: str
    _env: Environment

    @classmethod
    def from_toml(cls, path: Path) -> PromptProfile:
        with path.open("rb") as f:
            data = tomllib.load(f)
        templates = data.get("templates", {})
        env = Environment(
            loader=FileSystemLoader(str(_PROMPTS_DIR)),
            undefined=StrictUndefined,
            trim_blocks=False,
            lstrip_blocks=False,
        )
        return cls(
            name=str(data["name"]),
            language=str(data["language"]),
            persona=str(data.get("persona", "")),
            reasoning_prompt=str(data["reasoning_prompt"]),
            rationale_required=bool(data["rationale_required"]),
            stats_min_samples=int(data["stats_min_samples"]),
            card_format=str(data["card_format"]),
            player_label_format=str(data["player_label_format"]),
            position_label_format=str(data["position_label_format"]),
            system_template=str(templates.get("system", "system.j2")),
            user_template=str(templates.get("user", "user.j2")),
            _env=env,
        )

    def render_system(
        self,
        *,
        num_players: int,
        sb: int,
        bb: int,
        starting_stack: int,
        enable_math_tools: bool = False,
        enable_hud_tool: bool = False,
        opponent_stats_min_samples: int = 30,
        max_utility_calls: int = 5,
    ) -> str:
        tpl = self._env.get_template(self.system_template)
        return tpl.render(
            num_players=num_players,
            sb=sb,
            bb=bb,
            starting_stack=starting_stack,
            rationale_required=self.rationale_required,
            language=self.language,
            enable_math_tools=enable_math_tools,
            enable_hud_tool=enable_hud_tool,
            opponent_stats_min_samples=opponent_stats_min_samples,
            max_utility_calls=max_utility_calls,
        )

    def render_user(
        self,
        *,
        hand_id: int,
        street: str,
        my_seat: int,
        my_position_short: str,
        my_position_full: str,
        my_hole_cards: tuple[str, str],
        community: Iterable[str],
        pot: int,
        my_stack: int,
        to_call: int,
        pot_odds_required: float | None,
        effective_stack: int,
        button_seat: int,
        opponent_seats_in_hand: Iterable[int],
        seats_yet_to_act_after_me: Iterable[int],
        seats_public: Iterable[Any],
        opponent_stats: dict[int, Any] | None = None,
    ) -> str:
        tpl = self._env.get_template(self.user_template)
        return tpl.render(
            hand_id=hand_id,
            street=street,
            my_seat=my_seat,
            my_position_short=my_position_short,
            my_position_full=my_position_full,
            my_hole_cards=tuple(my_hole_cards),
            community=tuple(community),
            pot=pot,
            my_stack=my_stack,
            to_call=to_call,
            pot_odds_required=pot_odds_required,
            effective_stack=effective_stack,
            button_seat=button_seat,
            opponent_seats_in_hand=tuple(opponent_seats_in_hand),
            seats_yet_to_act_after_me=tuple(seats_yet_to_act_after_me),
            seats_public=tuple(seats_public),
            opponent_stats=opponent_stats or {},
        )


@lru_cache(maxsize=1)
def load_default_prompt_profile() -> PromptProfile:
    """Cached so multiple LLMAgent instances share one parse + Jinja env."""
    return PromptProfile.from_toml(_DEFAULT_TOML)


def with_overrides(base: PromptProfile, **overrides: Any) -> PromptProfile:
    """Build a new PromptProfile from `base` with one or more fields
    overridden — used by per-seat configuration like "gpt-5 reasoning
    models reject explicit chain-of-thought, set rationale_required=False
    for that seat only."

    Wraps `dataclasses.replace` so callers don't have to import the
    field name twice; the Jinja env (a non-replaceable shared resource)
    is preserved automatically since `replace` only swaps the named
    fields. Returns a new immutable instance — caller must reassign."""
    return replace(base, **overrides)


__all__ = ["PromptProfile", "load_default_prompt_profile", "with_overrides"]

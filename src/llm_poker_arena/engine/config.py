"""SessionConfig and HandContext.

SessionConfig is the top-level validated configuration for a single simulation
session (Pydantic BaseModel, frozen, extra=forbid).

HandContext is a small immutable descriptor built by the session orchestrator
for each hand and consumed by CanonicalState.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SessionConfig(BaseModel):
    """Top-level session configuration. Immutable after construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    num_players: int = Field(ge=2, le=10)
    starting_stack: int = Field(gt=0)
    sb: int = Field(gt=0)
    bb: int = Field(gt=0)
    num_hands: int = Field(gt=0)
    max_utility_calls: int = Field(ge=0)
    enable_math_tools: bool
    enable_hud_tool: bool
    rationale_required: bool
    opponent_stats_min_samples: int = Field(ge=1)
    rng_seed: int

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        if self.sb >= self.bb:
            raise ValueError(f"sb must be less than bb (got sb={self.sb}, bb={self.bb})")
        if self.num_hands % self.num_players != 0:
            raise ValueError(
                f"num_hands ({self.num_hands}) must be a multiple of num_players "
                f"({self.num_players}) for balanced button rotation"
            )
        if self.starting_stack < self.bb:
            raise ValueError(
                f"starting_stack ({self.starting_stack}) must be at least bb ({self.bb})"
            )
        return self


@dataclass(frozen=True, slots=True)
class HandContext:
    """Per-hand immutable descriptor consumed by CanonicalState."""

    hand_id: int
    deck_seed: int
    button_seat: int
    initial_stacks: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.hand_id < 0:
            raise ValueError(f"hand_id must be non-negative (got {self.hand_id})")
        if not self.initial_stacks:
            raise ValueError("initial_stacks length must be >= 1")
        n = len(self.initial_stacks)
        if n < 2:
            raise ValueError(f"initial_stacks length must be >= 2 (got {n})")
        if not (0 <= self.button_seat < n):
            raise ValueError(
                f"button_seat ({self.button_seat}) must be in [0, {n})"
            )

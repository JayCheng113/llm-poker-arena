"""Minimal Phase-1 Agent interface.

This is intentionally narrower than the full spec §4.1 interface:
  - Synchronous only (no async, no ToolRunner).
  - Returns a bare Action (no iterations / reasoning / retry counters).

Phase 3 will widen to `async decide(view, tool_runner) -> TurnDecisionResult`.
The RandomAgent below implements this narrow shape to keep Phase-1 engine
tests self-contained.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.views import PlayerView


class Agent(ABC):
    @abstractmethod
    def decide(self, view: PlayerView) -> Action:
        """Return a concrete Action proposal for this turn."""

    @abstractmethod
    def provider_id(self) -> str:
        """Stable identifier, e.g. 'random:seed42' or 'anthropic:claude-opus-4-7'."""

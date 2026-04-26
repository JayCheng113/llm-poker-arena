"""Async Agent ABC (spec §4.1, Phase 3a)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from llm_poker_arena.agents.llm.types import TurnDecisionResult
from llm_poker_arena.engine.views import PlayerView


class Agent(ABC):
    """Phase 3 contract: every agent returns a complete decision record.

    Sync-by-nature agents (RandomAgent / RuleBasedAgent / HumanCLIAgent)
    implement `decide` as `async def` and return a TurnDecisionResult with
    a single final_action and empty iterations / zero retries. LLMAgent
    populates iterations + retry counters during ReAct.
    """

    @abstractmethod
    async def decide(self, view: PlayerView) -> TurnDecisionResult:
        """Return a TurnDecisionResult for the given view. May not raise."""

    @abstractmethod
    def provider_id(self) -> str: ...

    def metadata(self) -> dict[str, Any] | None:
        """Optional per-agent metadata for snapshot persistence (spec §7.4).

        LLM-backed agents return a dict like
        `{"temperature": 0.7, "seed": 42}`. Non-LLM agents (Random,
        RuleBased, HumanCLI) return None — their AgentDescriptor.temperature
        and .seed stay None in the snapshot.

        This is intentionally a regular method (not @abstractmethod) so
        existing agents inherit the None default without modification.
        """
        return None

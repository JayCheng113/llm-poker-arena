"""Agent.metadata() ABC + LLMAgent override (Phase 4 Task 1)."""

from __future__ import annotations

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent


def test_random_agent_metadata_returns_none() -> None:
    """Non-LLM agents have no temp/seed; metadata() defaults to None."""
    assert RandomAgent().metadata() is None


def test_rule_based_agent_metadata_returns_none() -> None:
    assert RuleBasedAgent().metadata() is None


def test_llm_agent_metadata_returns_temperature_and_seed() -> None:
    """LLMAgent surfaces its temperature + seed for spec §7.4 persistence."""
    provider = MockLLMProvider(script=MockResponseScript(responses=()))
    agent = LLMAgent(
        provider=provider,
        model="m1",
        temperature=0.7,
        seed=42,
    )
    md = agent.metadata()
    assert md == {"temperature": 0.7, "seed": 42}


def test_llm_agent_metadata_handles_none_seed() -> None:
    """seed=None is valid (Anthropic doesn't accept seed); metadata reflects."""
    provider = MockLLMProvider(script=MockResponseScript(responses=()))
    agent = LLMAgent(provider=provider, model="m1", temperature=0.5, seed=None)
    md = agent.metadata()
    assert md == {"temperature": 0.5, "seed": None}

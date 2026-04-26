"""poker-play CLI accepts --llm-seat / --llm-provider / --llm-model triplets (Phase 4 Task 4)."""
from __future__ import annotations

import io

import pytest

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.cli.play import build_agents


def test_build_agents_with_one_llm_seat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Single LLM agent at seat 0 (anthropic), bots elsewhere."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    inp = io.StringIO()
    out = io.StringIO()
    agents = build_agents(
        num_players=6, my_seat=3,
        human_input=inp, human_output=out,
        llm_specs=[("anthropic", "claude-haiku-4-5", 0)],
    )
    assert isinstance(agents[0], LLMAgent)
    # seat 3 is HumanCLI (always); other seats are bots or LLMs.
    from llm_poker_arena.agents.human_cli import HumanCLIAgent
    assert isinstance(agents[3], HumanCLIAgent)


def test_build_agents_with_two_llm_seats(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two LLM agents (Anthropic seat 0 + DeepSeek seat 1), human at seat 3."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    agents = build_agents(
        num_players=6, my_seat=3,
        human_input=io.StringIO(), human_output=io.StringIO(),
        llm_specs=[
            ("anthropic", "claude-haiku-4-5", 0),
            ("deepseek", "deepseek-chat", 1),
        ],
    )
    assert isinstance(agents[0], LLMAgent)
    assert isinstance(agents[1], LLMAgent)
    # seat 0's provider is anthropic; seat 1's is deepseek.
    assert agents[0].provider_id().startswith("anthropic:")
    assert agents[1].provider_id().startswith("deepseek:")


def test_build_agents_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing ANTHROPIC_API_KEY when an anthropic LLM seat is requested → fail-fast."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_agents(
            num_players=6, my_seat=3,
            human_input=io.StringIO(), human_output=io.StringIO(),
            llm_specs=[("anthropic", "claude-haiku-4-5", 0)],
        )


def test_build_agents_llm_seat_collides_with_human_seat_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM-seat must not equal human seat."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with pytest.raises(ValueError, match="cannot equal"):
        build_agents(
            num_players=6, my_seat=3,
            human_input=io.StringIO(), human_output=io.StringIO(),
            llm_specs=[("anthropic", "claude-haiku-4-5", 3)],  # seat 3 is human!
        )

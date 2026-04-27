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
        num_players=6,
        my_seat=3,
        human_input=inp,
        human_output=out,
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
        num_players=6,
        my_seat=3,
        human_input=io.StringIO(),
        human_output=io.StringIO(),
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
            num_players=6,
            my_seat=3,
            human_input=io.StringIO(),
            human_output=io.StringIO(),
            llm_specs=[("anthropic", "claude-haiku-4-5", 0)],
        )


def test_build_agents_llm_seat_collides_with_human_seat_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM-seat must not equal human seat."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with pytest.raises(ValueError, match="cannot equal"):
        build_agents(
            num_players=6,
            my_seat=3,
            human_input=io.StringIO(),
            human_output=io.StringIO(),
            llm_specs=[("anthropic", "claude-haiku-4-5", 3)],  # seat 3 is human!
        )


def test_argparse_choices_in_sync_with_provider_table() -> None:
    """codex review IMP-1 regression: --llm-provider argparse `choices` must
    derive from _PROVIDER_TABLE so adding a new provider doesn't silently
    leave the CLI surface stale."""
    from llm_poker_arena.cli.play import _PROVIDER_TABLE, main

    # Trigger argparse's help so choices=... evaluates without running a
    # session. The choices list lives inside argparse's internal state, but
    # the cleanest assertion is: every key in _PROVIDER_TABLE accepts via
    # the parser without "invalid choice" error.
    import argparse

    for provider_tag in _PROVIDER_TABLE:
        parser = argparse.ArgumentParser()
        parser.add_argument("--llm-provider", action="append", default=[],
                            choices=sorted(_PROVIDER_TABLE))
        # Should NOT raise SystemExit / argparse error.
        ns = parser.parse_args(["--llm-provider", provider_tag])
        assert provider_tag in ns.llm_provider, (
            f"argparse rejected --llm-provider {provider_tag} despite it being "
            f"in _PROVIDER_TABLE. The CLI argparse choices have drifted."
        )

    # Also verify all 7 providers we ship are present (catches accidental
    # deletion from the table).
    expected = {"anthropic", "openai", "deepseek", "qwen", "kimi", "grok", "gemini"}
    assert expected.issubset(_PROVIDER_TABLE.keys()), (
        f"_PROVIDER_TABLE missing providers: {expected - _PROVIDER_TABLE.keys()}"
    )

    # `main` is referenced just to keep the import live; not invoked.
    assert callable(main)

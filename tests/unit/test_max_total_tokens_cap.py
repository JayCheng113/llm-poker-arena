"""SessionConfig.max_total_tokens cost cap (Phase 4 Task 3)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    TokenCounts,
    ToolCall,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _bigfold(uid: str, in_tok: int = 10_000, out_tok: int = 0) -> LLMResponse:
    """A 'fold' response that consumes a lot of tokens (for cap-test setup)."""
    return LLMResponse(
        provider="mock", model="m", stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id=uid),),
        text_content="big folding",
        tokens=TokenCounts(input_tokens=in_tok, output_tokens=out_tok,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


def test_default_max_total_tokens_is_none() -> None:
    """Backward-compat: no cap by default."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    assert cfg.max_total_tokens is None


def test_cap_none_runs_full_session(tmp_path: Path) -> None:
    """max_total_tokens=None preserves Phase 3 behavior (no abort)."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
        max_total_tokens=None,
    )
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="no_cap")
    asyncio.run(sess.run())
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["total_hands_played"] == 6
    assert meta.get("stop_reason") in (None, "completed")


def test_cap_aborts_after_hand_when_exceeded(tmp_path: Path) -> None:
    """Set a low cap so the LLM seat blows it within first hand. Session
    aborts cleanly at hand boundary; meta.json shows stop_reason."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=12, max_utility_calls=5,  # 12 hands; cap will trip earlier
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
        max_total_tokens=5_000,  # very small; first LLM turn exceeds
    )
    script = MockResponseScript(responses=tuple(
        _bigfold(f"t{i}") for i in range(200)
    ))
    provider = MockLLMProvider(script=script)
    llm = LLMAgent(provider=provider, model="m", temperature=0.7)
    agents = [
        RandomAgent(), llm, RandomAgent(), RandomAgent(),
        RandomAgent(), RandomAgent(),
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="cap_trip")
    asyncio.run(sess.run())
    meta = json.loads((tmp_path / "meta.json").read_text())
    # Aborted before all 12 hands.
    assert meta["total_hands_played"] < 12
    assert meta["stop_reason"] == "max_total_tokens_exceeded"


def test_cap_above_session_total_does_not_abort(tmp_path: Path) -> None:
    """Cap higher than session's actual usage → completes normally."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
        max_total_tokens=10_000_000,  # huge — won't trip
    )
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="cap_unreached")
    asyncio.run(sess.run())
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["total_hands_played"] == 6
    assert meta.get("stop_reason") in (None, "completed")

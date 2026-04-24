"""Tests for Session orchestrator (3-hand smoke + artifact structural checks)."""
from __future__ import annotations

import json
from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _cfg() -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6,  # smoke: 1 button rotation
        max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def test_session_writes_three_jsonl_files(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RandomAgent(), RuleBasedAgent()] * 3
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_test")
    sess.run()
    # All 3 layer files exist and are non-empty.
    for fname in ("canonical_private.jsonl", "public_replay.jsonl",
                  "agent_view_snapshots.jsonl", "meta.json"):
        p = tmp_path / fname
        assert p.exists(), fname
        assert p.stat().st_size > 0, fname


def test_session_canonical_private_has_num_hands_lines(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_c")
    sess.run()
    lines = (tmp_path / "canonical_private.jsonl").read_text().strip().splitlines()
    assert len(lines) == cfg.num_hands


def test_session_public_replay_is_one_hand_per_line(tmp_path: Path) -> None:
    """spec §7.3: `public_replay.jsonl` has one line per hand, events in array."""
    cfg = _cfg()
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_p")
    sess.run()
    lines = (tmp_path / "public_replay.jsonl").read_text().strip().splitlines()
    assert len(lines) == cfg.num_hands
    first_hand = json.loads(lines[0])
    assert "hand_id" in first_hand
    assert "street_events" in first_hand
    assert first_hand["street_events"][0]["type"] == "hand_started"
    assert first_hand["street_events"][-1]["type"] == "hand_ended"


def test_session_writes_config_json_on_init(tmp_path: Path) -> None:
    """spec §7.1 dir structure includes config snapshot."""
    cfg = _cfg()
    agents = [RandomAgent() for _ in range(6)]
    # Don't even call .run() — config.json should be written in __init__.
    _ = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_cfg")
    p = tmp_path / "config.json"
    assert p.exists()
    written = json.loads(p.read_text())
    assert written["num_players"] == 6
    assert written["rng_seed"] == 42


def test_session_agent_view_snapshot_is_at_least_one_per_hand(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_a")
    sess.run()
    lines = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    # Each hand has >= 1 action turn (minimum: 1 fold settles pre-action? No --
    # with blinds posted, BB can check at minimum, so >= 1 turn always).
    assert len(lines) >= cfg.num_hands


def test_session_meta_json_carries_total_hands_and_chip_pnl(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_m")
    sess.run()
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["session_id"] == "sess_m"
    assert meta["total_hands_played"] == cfg.num_hands
    # chip_pnl sums to 0 (zero-sum game)
    assert sum(meta["chip_pnl"].values()) == 0
    # session_wall_time_sec is populated (non-negative int)
    assert isinstance(meta["session_wall_time_sec"], int)
    assert meta["session_wall_time_sec"] >= 0


def test_session_rejects_agents_list_length_mismatch(tmp_path: Path) -> None:
    import pytest
    cfg = _cfg()
    with pytest.raises(ValueError, match="agents"):
        Session(config=cfg, agents=[RandomAgent()] * 3,  # only 3 agents for 6 seats
                output_dir=tmp_path, session_id="sess_bad")

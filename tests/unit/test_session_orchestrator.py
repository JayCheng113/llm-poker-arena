"""Tests for Session orchestrator (3-hand smoke + artifact structural checks)."""
from __future__ import annotations

import asyncio
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
    asyncio.run(sess.run())
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
    asyncio.run(sess.run())
    lines = (tmp_path / "canonical_private.jsonl").read_text().strip().splitlines()
    assert len(lines) == cfg.num_hands


def test_session_public_replay_is_one_hand_per_line(tmp_path: Path) -> None:
    """spec §7.3: `public_replay.jsonl` has one line per hand, events in array."""
    cfg = _cfg()
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_p")
    asyncio.run(sess.run())
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
    asyncio.run(sess.run())
    lines = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    # Each hand has >= 1 action turn (minimum: 1 fold settles pre-action? No --
    # with blinds posted, BB can check at minimum, so >= 1 turn always).
    assert len(lines) >= cfg.num_hands


def test_session_meta_json_carries_total_hands_and_chip_pnl(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_m")
    asyncio.run(sess.run())
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


def test_session_canonical_private_preserves_hole_cards_of_folded_seats(
    tmp_path: Path,
) -> None:
    """Regression: canonical_private must record all 6 seats' hole cards
    per spec §7.2, even for seats that folded (and had their cards mucked
    by PokerKit's HAND_KILLING automation).

    Prior to the pre-settlement-snapshot fix, `build_canonical_private_hand`
    re-read `state.hole_cards()` at hand-end, which only returned the
    winner. Any fold-heavy hand produced a `hole_cards` map with < 6 keys.
    """
    cfg = _cfg()  # 6 hands, rng_seed=42 — produces natural folds
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(
        config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_holes",
    )
    asyncio.run(sess.run())

    lines = (tmp_path / "canonical_private.jsonl").read_text().strip().splitlines()
    assert len(lines) == cfg.num_hands
    for line in lines:
        rec = json.loads(line)
        holes = rec["hole_cards"]
        assert set(holes.keys()) == {"0", "1", "2", "3", "4", "5"}, (
            f"hand {rec['hand_id']}: expected all 6 seats' hole_cards, "
            f"got keys {sorted(holes.keys())}"
        )
        # Each seat's hole is exactly 2 card strings.
        for seat_str, cards in holes.items():
            assert len(cards) == 2, (seat_str, cards)


def test_session_public_showdown_event_reveals_all_participants_not_just_winner(
    tmp_path: Path,
) -> None:
    """Regression: public_replay showdown event must include every seat
    that reached showdown, not just the winner.

    Prior to the fix, `build_public_showdown_event` re-read
    `state.hole_cards()` and missed losers whose cards were mucked by
    HAND_KILLING. Verify by finding a hand with a showdown event and
    asserting its `revealed` has ≥ 2 seats when the hand reached showdown
    (showdown_seats size ≥ 2).
    """
    # Use more hands so at least one naturally reaches showdown.
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=12, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=99,
    )
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(
        config=cfg, agents=agents, output_dir=tmp_path, session_id="sess_showdown",
    )
    asyncio.run(sess.run())

    hands_with_showdown: list[dict[str, object]] = []
    for line in (tmp_path / "public_replay.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        hand = json.loads(line)
        for ev in hand["street_events"]:
            if ev["type"] == "showdown":
                hands_with_showdown.append(ev)
                break

    # At least one hand in 12 with random-aggressive play should reach
    # showdown. If this ever fails, the test seed needs adjustment —
    # but the invariant we care about is the assertion below, not zero-
    # showdowns.
    assert hands_with_showdown, (
        "no hand reached showdown in 12-hand seed=99 session; "
        "try a different seed or more hands"
    )
    for ev in hands_with_showdown:
        revealed = ev["revealed"]
        assert isinstance(revealed, dict)
        assert len(revealed) >= 2, (
            f"showdown hand {ev['hand_id']}: only {len(revealed)} seats "
            f"revealed, expected >= 2 (winner + at least one loser); "
            f"got {revealed}"
        )

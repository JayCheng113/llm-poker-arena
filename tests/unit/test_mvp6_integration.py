"""MVP 6 exit criterion: 1,000 mock-agent hands → 3-layer JSONL + meta + zero leak."""
from __future__ import annotations

import json
from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session
from llm_poker_arena.storage.access_control import (
    PRIVATE_ACCESS_TOKEN,
    PrivateLogReader,
    PublicLogReader,
)


def test_mvp6_thousand_hands_heterogeneous_lineup(tmp_path: Path) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=1_002,  # multiple of 6 closest to 1000
        max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=2026,
    )
    # Heterogeneous lineup: 3 Random + 3 RuleBased.
    agents = [RandomAgent(), RuleBasedAgent()] * 3
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path, session_id="mvp6")
    sess.run()

    # Three layer files + meta + config.json exist.
    for fname in ("canonical_private.jsonl", "public_replay.jsonl",
                  "agent_view_snapshots.jsonl", "meta.json", "config.json"):
        assert (tmp_path / fname).exists(), fname

    # 1002 hand records in both canonical_private AND public_replay
    # (spec §7.3: public_replay is ONE LINE PER HAND, not per event).
    private_lines = (tmp_path / "canonical_private.jsonl").read_text().splitlines()
    assert len(private_lines) == 1_002
    public_lines = (tmp_path / "public_replay.jsonl").read_text().splitlines()
    assert len(public_lines) == 1_002

    # Round-trip readers work.
    pub = PublicLogReader(tmp_path)
    pub_hands = list(pub.iter_events())  # each entry = one hand record
    assert len(pub_hands) == 1_002
    # Spot-check first few: each hand has street_events bookended by
    # hand_started ... hand_ended.
    for rec in pub_hands[:5]:
        assert "street_events" in rec
        event_types = [e["type"] for e in rec["street_events"]]
        assert event_types[0] == "hand_started"
        assert event_types[-1] == "hand_ended"

    priv = PrivateLogReader(tmp_path, access_token=PRIVATE_ACCESS_TOKEN)
    hands = list(priv.iter_private_hands())
    assert len(hands) == 1_002
    snapshots = list(priv.iter_snapshots())
    assert len(snapshots) >= 1_002  # ≥ 1 agent turn per hand

    # Chip conservation sanity (zero-sum across all hands).
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0
    assert meta["total_hands_played"] == 1_002

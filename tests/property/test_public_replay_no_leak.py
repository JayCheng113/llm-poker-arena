"""Property P2: public_replay.jsonl never leaks hole cards of non-showdown seats."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


@given(
    rng_seed=st.integers(min_value=0, max_value=5_000),
    num_hands=st.sampled_from([6, 12, 18]),
)
@settings(max_examples=30, deadline=None)
def test_public_replay_has_no_non_showdown_hole_leak(
    rng_seed: int, num_hands: int, tmp_path_factory: object,
) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=rng_seed,
    )
    # tmp_path_factory is pytest's session-scoped factory; mktemp gives a
    # fresh dir per hypothesis example.
    out_dir = tmp_path_factory.mktemp("sess_leakcheck")  # type: ignore[attr-defined]
    agents = [RandomAgent() for _ in range(6)]
    Session(config=cfg, agents=agents, output_dir=Path(out_dir),
            session_id="leaktest").run()

    # For each hand in canonical_private, compare its hole_cards against the
    # cards revealed (or absent) in public_replay. Both files are one hand
    # per line (spec §7.2 / §7.3 shape).
    private = [json.loads(line) for line in
               (Path(out_dir) / "canonical_private.jsonl").read_text().splitlines() if line.strip()]
    public_by_hand: dict[int, dict[str, Any]] = {
        rec["hand_id"]: rec
        for rec in (json.loads(line) for line in
                    (Path(out_dir) / "public_replay.jsonl").read_text().splitlines() if line.strip())
    }

    for hand in private:
        hid = hand["hand_id"]
        holes = hand["hole_cards"]  # dict[str, list[str, str]]
        public_rec = public_by_hand[hid]
        street_events = public_rec["street_events"]

        # Find showdown event (may be absent if hand ended by fold-to-one).
        showdown_evs = [e for e in street_events if e["type"] == "showdown"]
        revealed_seats: set[str] = set()
        if showdown_evs:
            revealed_seats = set(showdown_evs[0]["revealed"].keys())

        # Serialize the whole hand record to one string and substring-search.
        public_blob = json.dumps(public_rec, sort_keys=True)
        for seat_str, cards in holes.items():
            if seat_str in revealed_seats:
                continue  # showdown reveal allowed
            for card in cards:
                assert card not in public_blob, (
                    f"seat {seat_str} (non-showdown) card {card!r} leaked "
                    f"into public_replay for hand {hid}"
                )

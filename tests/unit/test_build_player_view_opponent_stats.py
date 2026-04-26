"""build_player_view threads opponent_stats from Session counters
(Phase 3c-hud Task 7)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine._internal.rebuy import derive_deck_seed
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.projections import build_player_view
from llm_poker_arena.engine.views import OpponentStatsOrInsufficient
from llm_poker_arena.session.session import Session


def _cfg(num_hands: int = 6, min_samples: int = 30) -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=num_hands, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=min_samples, rng_seed=42,
    )


def test_build_view_default_opponent_stats_is_empty() -> None:
    """When no opponent_stats kwarg passed, opponent_stats stays {} (back-compat)."""
    cfg = _cfg()
    ctx = HandContext(
        hand_id=0, deck_seed=derive_deck_seed(42, 0),
        button_seat=0, initial_stacks=(10_000,) * 6,
    )
    state = CanonicalState(cfg, ctx)
    view = build_player_view(state, actor=3, turn_seed=42)
    assert view.opponent_stats == {}


def test_build_view_with_opponent_stats_kwarg_populates() -> None:
    """Pass explicit opponent_stats dict → view.opponent_stats reflects it."""
    cfg = _cfg()
    ctx = HandContext(
        hand_id=0, deck_seed=derive_deck_seed(42, 0),
        button_seat=0, initial_stacks=(10_000,) * 6,
    )
    state = CanonicalState(cfg, ctx)
    stats = {
        0: OpponentStatsOrInsufficient(insufficient=True),
        1: OpponentStatsOrInsufficient(insufficient=True),
    }
    view = build_player_view(state, actor=3, turn_seed=42, opponent_stats=stats)
    assert view.opponent_stats == stats


def test_session_below_min_samples_returns_insufficient(tmp_path: Path) -> None:
    """6-hand session with default min_samples=30 → all opponents
    insufficient because total_hands_played (6) < 30."""
    cfg = _cfg(num_hands=6, min_samples=30)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="insufficient_test")
    asyncio.run(sess.run())

    # Call _build_opponent_stats(actor=3) directly post-session.
    stats = sess._build_opponent_stats(actor=3)
    # Self-seat (3) NOT in dict.
    assert 3 not in stats
    # Other 5 seats all insufficient.
    assert set(stats.keys()) == {0, 1, 2, 4, 5}
    for seat, s in stats.items():
        assert s.insufficient, f"seat {seat} should be insufficient at 6 < 30 hands"


def test_build_opponent_stats_deterministic_above_min_samples(tmp_path: Path) -> None:
    """codex audit IMPORTANT-7 fix: directly seed Session._hud_counters and
    _hud_hands_counted instead of running 30 RandomAgent hands (which is
    fragile with the all-or-nothing sentinel)."""
    cfg = _cfg(num_hands=6, min_samples=30)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="seeded_test")
    # Seed the session as if 30 clean hands have completed.
    sess._hud_hands_counted = 30
    for seat in range(6):
        sess._hud_counters[seat] = {
            "vpip_actions": 12,           # 40% VPIP
            "pfr_actions": 6,             # 20% PFR
            "three_bet_chances": 5,
            "three_bet_actions": 1,       # 20% 3-bet
            "af_aggressive": 18,
            "af_passive": 9,              # AF = 2.0
            "wtsd_chances": 12,           # = vpip_actions per WTSD def
            "wtsd_actions": 4,            # 33% WTSD
        }
    stats = sess._build_opponent_stats(actor=3)
    assert set(stats.keys()) == {0, 1, 2, 4, 5}
    for seat, s in stats.items():
        assert not s.insufficient, f"seat {seat} unexpectedly insufficient"
        assert s.vpip == 12 / 30
        assert s.pfr == 6 / 30
        assert s.three_bet == 1 / 5
        assert s.af == 18 / 9
        assert s.wtsd == 4 / 12


def test_build_opponent_stats_3bet_den_zero_falls_back_to_insufficient(
    tmp_path: Path,
) -> None:
    """codex audit IMPORTANT-6: opponent past min_samples but with
    three_bet_chances=0 falls back to insufficient=True (all-or-nothing
    sentinel — documented v1 limitation)."""
    cfg = _cfg(num_hands=6, min_samples=30)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="3bet_den_zero_test")
    sess._hud_hands_counted = 30
    sess._hud_counters[0] = {
        "vpip_actions": 12, "pfr_actions": 6,
        "three_bet_chances": 0,           # ← zero denominator
        "three_bet_actions": 0,
        "af_aggressive": 18, "af_passive": 9,
        "wtsd_chances": 12, "wtsd_actions": 4,
    }
    stats = sess._build_opponent_stats(actor=3)
    assert stats[0].insufficient is True


def test_build_opponent_stats_af_passive_zero_falls_back_to_insufficient(
    tmp_path: Path,
) -> None:
    """codex audit IMPORTANT-6: opponent past min_samples but with
    af_passive=0 (never called) falls back to insufficient=True."""
    cfg = _cfg(num_hands=6, min_samples=30)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="af_passive_zero_test")
    sess._hud_hands_counted = 30
    sess._hud_counters[0] = {
        "vpip_actions": 12, "pfr_actions": 12,
        "three_bet_chances": 5, "three_bet_actions": 3,
        "af_aggressive": 30,
        "af_passive": 0,                  # ← zero denominator
        "wtsd_chances": 12, "wtsd_actions": 4,
    }
    stats = sess._build_opponent_stats(actor=3)
    assert stats[0].insufficient is True


def test_build_opponent_stats_uses_hud_hands_counted_not_total(
    tmp_path: Path,
) -> None:
    """codex audit IMPORTANT-5: denominator must be _hud_hands_counted
    (clean-completion count), not _total_hands_played (which counts
    censored hands too). Simulate divergent counters."""
    cfg = _cfg(num_hands=6, min_samples=30)
    agents = [RandomAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="hud_hands_counter_test")
    # Simulate: 50 total hands attempted, 5 were censored, 45 cleanly
    # completed and contributed HUD counters. 45 >= min_samples=30 → not
    # insufficient.
    sess._total_hands_played = 50
    sess._hud_hands_counted = 45
    for seat in range(6):
        sess._hud_counters[seat] = {
            "vpip_actions": 18, "pfr_actions": 9,
            "three_bet_chances": 7, "three_bet_actions": 2,
            "af_aggressive": 27, "af_passive": 14,
            "wtsd_chances": 18, "wtsd_actions": 6,
        }
    stats = sess._build_opponent_stats(actor=3)
    for seat in (0, 1, 2, 4, 5):
        s = stats[seat]
        assert not s.insufficient, (
            f"seat {seat} should be sufficient (45 clean hands ≥ 30)"
        )
        assert s.vpip is not None
        # Rate should use 45 not 50.
        assert abs(s.vpip - 18 / 45) < 1e-9

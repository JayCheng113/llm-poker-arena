"""Multi-way MC equity invariants. The algorithm runs rejection sampling:
  - Sample one combo INDEPENDENTLY from each villain's range
  - Reject the WHOLE attempt if any card overlap (codex BLOCKER B1 fix)
  - Sample remaining board cards
  - Evaluate hero + each villain; multi-way tie share = 1/N (codex
    BLOCKER B2 fix)

Tests verify:
  1. Equity is in [0, 1]
  2. Same seed → identical equity (determinism for spec §11.1)
  3. Different seeds → different equity (sanity that MC is actually random)
  4. HU degenerate case matches eval7's native HU MC within MC noise
  5. Seat order invariant (BLOCKER B1 regression)
  6. 3-way all-tie hero share = 1/3 (BLOCKER B2 regression)
  7. Empty villain pool (max_attempts trips) → graceful (0.0, 0.0, 0)
"""
from __future__ import annotations

import eval7
import pytest

from llm_poker_arena.tools.equity import _multi_way_equity_mc
from llm_poker_arena.tools.equity_backend import Eval7Backend


def _cards(*names: str) -> tuple[eval7.Card, ...]:
    return tuple(eval7.Card(n) for n in names)


def test_multi_way_mc_equity_in_unit_interval() -> None:
    """AKs vs QQ+ HU preflop. Equity should be a valid probability."""
    hero = _cards("As", "Ks")
    board: tuple[eval7.Card, ...] = ()
    villain_pools = [tuple(eval7.HandRange("QQ+").hands)]
    backend = Eval7Backend()
    eq, var, valid = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                            n_samples=1000, seed=42)
    assert 0.0 <= eq <= 1.0
    assert var >= 0.0  # variance non-negative
    assert valid == 1000  # rejection sampling converges to target


def test_multi_way_mc_deterministic_with_seed() -> None:
    """Same (hero, board, ranges, seed) → identical result. spec §11.1."""
    hero = _cards("As", "Ks")
    board: tuple[eval7.Card, ...] = ()
    villain_pools = [tuple(eval7.HandRange("QQ+, AKs").hands)]
    backend = Eval7Backend()
    eq_a, _, _ = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                       n_samples=2000, seed=42)
    eq_b, _, _ = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                       n_samples=2000, seed=42)
    assert eq_a == eq_b


def test_multi_way_mc_different_seeds_differ() -> None:
    """Sanity: MC is actually using the seed (not constant)."""
    hero = _cards("As", "Ks")
    board: tuple[eval7.Card, ...] = ()
    villain_pools = [tuple(eval7.HandRange("QQ+").hands)]
    backend = Eval7Backend()
    eq_a, _, _ = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                       n_samples=500, seed=1)
    eq_b, _, _ = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                       n_samples=500, seed=2)
    # MC noise at N=500 ≈ 2.2% SE; two seeds should differ noticeably.
    assert abs(eq_a - eq_b) > 0.001


def test_multi_way_mc_hu_matches_eval7_native_within_mc_noise() -> None:
    """Our HU code path (1 villain in dict) should match eval7's native HU
    MC equity within statistical noise. 95% CI at N=10000 ≈ ±1%."""
    hero_eval7 = list(_cards("As", "Ks"))
    villain_range = eval7.HandRange("QQ+")
    eval7_eq = eval7.py_hand_vs_range_monte_carlo(
        hero_eval7, villain_range, [], 10000,
    )

    hero = tuple(hero_eval7)
    board: tuple[eval7.Card, ...] = ()
    villain_pools = [tuple(villain_range.hands)]
    backend = Eval7Backend()
    our_eq, _, _ = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                         n_samples=10000, seed=42)
    # Two independent MC samples of same true equity; difference < ±2%
    # (loose bound — the eval7 native MC has its own seed we can't control).
    assert abs(our_eq - eval7_eq) < 0.02


def test_multi_way_mc_seat_order_invariant() -> None:
    """Codex audit BLOCKER B1 regression: rejection sampling MUST be order-
    independent. Swapping seats for the same multiset of ranges must yield
    statistically equivalent equity (within MC noise). Old sequential algorithm
    leaked ~2.2pp bias on this test.
    """
    hero = _cards("As", "Ks")
    board: tuple[eval7.Card, ...] = ()
    pool_qq = tuple(eval7.HandRange("QQ+").hands)
    pool_aks = tuple(eval7.HandRange("AKs, AKo").hands)
    backend = Eval7Backend()

    # Same ranges, different seat order:
    #   - order A: villain1=QQ+, villain2=AKs/o
    #   - order B: villain1=AKs/o, villain2=QQ+
    eq_a, _, _ = _multi_way_equity_mc(hero, board, [pool_qq, pool_aks], backend,
                                       n_samples=10000, seed=42)
    eq_b, _, _ = _multi_way_equity_mc(hero, board, [pool_aks, pool_qq], backend,
                                       n_samples=10000, seed=42)
    # SE at N=10000 ≈ 0.005 → 95% CI ≈ ±0.01. Two independent seeds give
    # different MC noise; assert difference < 0.015 (loose 3-SE bound).
    # Old sequential algorithm gave ~0.022 difference (codex repro).
    assert abs(eq_a - eq_b) < 0.015, (
        f"order-dependent bias detected: eq_a={eq_a:.4f}, eq_b={eq_b:.4f} "
        f"(diff={abs(eq_a-eq_b):.4f}). rejection sampling should be invariant "
        f"to seat ordering."
    )


def test_multi_way_mc_three_way_tie_assigns_one_third_share() -> None:
    """Codex audit BLOCKER B2 regression: in N-way ties, hero's share is
    1/N, NOT 0.5 (which is HU-only). Test sets up a guaranteed all-tie
    scenario: 3 players all hold the same straight (board provides A high
    straight to all because hero+villains have low cards that don't beat
    the straight).

    Constructed scenario: board = AhKhQhJhTh (royal flush ON board). Every
    player ties on the royal — hero share should be 1/3 with 2 villains.
    """
    backend = Eval7Backend()
    hero = _cards("2c", "2d")  # irrelevant — board is royal
    board = _cards("Ah", "Kh", "Qh", "Jh", "Th")
    # Villains hold any non-overlapping low cards.
    pool_v1 = (((eval7.Card("3c"), eval7.Card("3d")), 1.0),)
    pool_v2 = (((eval7.Card("4c"), eval7.Card("4d")), 1.0),)
    eq, _, valid = _multi_way_equity_mc(
        hero, board, [pool_v1, pool_v2], backend,
        n_samples=200, seed=42,
    )
    assert valid > 0
    # All 3 players use the royal on board → 3-way tie every iteration.
    # Hero's share = 1/3.
    assert eq == pytest.approx(1.0 / 3.0, abs=0.01)


def test_multi_way_mc_skips_iterations_when_villain_pool_empty() -> None:
    """If hero blocks the entire villain pool (e.g., hero=AsKs blocks all of
    villain "AsKs" range), MC iterations skip and equity converges to 0
    (no successful sample). NOT a crash."""
    hero = _cards("As", "Ks")
    board: tuple[eval7.Card, ...] = ()
    # Villain range with ONLY AsKs combo, which hero blocks.
    villain_pools = [tuple(eval7.HandRange("AsKs").hands)]
    backend = Eval7Backend()
    eq, _, valid = _multi_way_equity_mc(hero, board, villain_pools, backend,
                                         n_samples=100, seed=42)
    # No villain combo survivable → max_attempts trips without producing
    # any valid sample → returns (0.0, 0.0, 0). Caller (hand_equity_vs_ranges)
    # surfaces as ToolDispatchError; here we just verify the algo returns
    # gracefully without crashing or returning garbage.
    assert eq == 0.0
    assert valid == 0  # rejection-sampled to exhaustion, all rejected

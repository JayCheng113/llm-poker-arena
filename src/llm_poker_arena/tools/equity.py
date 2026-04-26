"""hand_equity_vs_ranges multi-way Monte Carlo equity tool (spec §5.2.3).

Phase 3c-equity: implementation. eval7 ships only HU MC primitives
(`py_hand_vs_range_monte_carlo`); we hand-roll the N-way MC algorithm
on top of eval7.evaluate() + HandRange.hands. ~50 LOC including
rejection-sampling correctness machinery.

Algorithm (REJECTION SAMPLING — codex audit BLOCKER B1 fix):
  1. Sample one combo INDEPENDENTLY from each villain's range (no
     conditioning on previously-sampled villains).
  2. Reject the WHOLE attempt if any card overlap occurs (hero ↔ villain,
     board ↔ villain, or villain ↔ villain).
  3. Sample remaining board cards from the unused deck.
  4. Evaluate hero + each villain. Multi-way tie accounting (codex audit
     BLOCKER B2 fix): hero's share = 1 / N if N players tie for best
     hand (HU=0.5 is just N=2 special case); 0 if hero doesn't tie for
     best. Equity = sum(shares) / valid_samples.
  5. Continue until `valid_samples == n_samples` OR `attempts >= max_attempts`
     (10× n_samples cap on pathological setups).

Why rejection (not sequential conditioning): sequential filtering biases
toward villain combos that don't block later villains. Codex demonstrated
empirically that swapping seat order changes equity by ~2.2pp under the
old algorithm. Rejection sampling draws from the true joint distribution.

Determinism: caller passes `seed`; we use `random.Random(seed)` for all
sampling. Same (hero, board, ranges, seed) → identical equity result
(spec §11.1).

CI calculation (multi-way correctness): each sample contributes a share
∈ {0, 1/N, 2/N, ...}, NOT a Bernoulli outcome. We track sum_x2 to compute
sample variance directly. For HU + no ties, this reduces to the standard
Bernoulli p(1-p)/n formula.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

import eval7

if TYPE_CHECKING:
    from llm_poker_arena.engine.views import PlayerView
    from llm_poker_arena.tools.equity_backend import EquityBackend

# Type alias for a villain combo as returned by eval7.HandRange.hands:
# (combo, weight) where combo = (Card, Card). Phase 3c-equity rejects
# non-1.0 weights at parse time (codex audit IMPORTANT-1) — see
# hand_equity_vs_ranges below.
_RangeCombo = tuple[tuple[eval7.Card, eval7.Card], float]


def _multi_way_equity_mc(
    hero: tuple[eval7.Card, ...],
    board: tuple[eval7.Card, ...],
    villain_pools: list[tuple[_RangeCombo, ...]],
    backend: EquityBackend,
    *,
    n_samples: int,
    seed: int,
) -> tuple[float, float, int]:
    """Run N-way MC via rejection sampling; return (equity, share_variance,
    valid_samples).

    equity = sum_of_hero_shares / valid_samples (each share in {0, 1/N, ...,
    1} where N = #players tying for best hand).

    share_variance is the SAMPLE variance of hero shares — used by caller
    to compute CI correctly for multi-way ties (Bernoulli p(1-p) is wrong
    when ties yield fractional shares).

    valid_samples is the count of iterations that produced a valid card
    configuration. Rejection sampling continues until valid_samples ==
    n_samples, capped at max_attempts = 10*n_samples to bound pathological
    cases. If max_attempts trips with valid_samples == 0, returns
    (0.0, 0.0, 0) — caller raises ToolDispatchError.
    """
    rng = random.Random(seed)
    full_deck: list[eval7.Card] = []
    for r in eval7.ranks:
        for s in eval7.suits:
            full_deck.append(eval7.Card(r + s))

    hero_list = list(hero)
    board_list = list(board)
    hero_board_set: set[eval7.Card] = set(hero_list) | set(board_list)
    n_board_to_deal = 5 - len(board_list)

    valid_samples = 0
    share_sum = 0.0
    share_sq_sum = 0.0
    max_attempts = max(n_samples * 10, 100)
    attempts = 0

    while valid_samples < n_samples and attempts < max_attempts:
        attempts += 1
        # 1. Sample INDEPENDENTLY from each villain pool (codex BLOCKER B1).
        sampled_villains = [
            rng.choice(pool)[0]  # (combo, weight) → combo
            for pool in villain_pools
        ]
        # 2. Reject the WHOLE attempt on any overlap.
        all_villain_cards = [c for v in sampled_villains for c in v]
        if len(set(all_villain_cards)) != len(all_villain_cards):
            continue  # villain ↔ villain overlap
        if any(c in hero_board_set for c in all_villain_cards):
            continue  # hero/board ↔ villain overlap
        # 3. Sample remaining board cards.
        used = hero_board_set | set(all_villain_cards)
        remaining_deck = [c for c in full_deck if c not in used]
        if len(remaining_deck) < n_board_to_deal:
            continue  # shouldn't happen but safe
        extra_board = rng.sample(remaining_deck, n_board_to_deal)
        full_board = board_list + extra_board
        # 4. Evaluate; multi-way tie accounting (codex BLOCKER B2).
        hero_score = backend.evaluate(tuple(hero_list + full_board))
        villain_scores = [
            backend.evaluate(tuple(list(v) + full_board))
            for v in sampled_villains
        ]
        all_scores = [hero_score] + villain_scores
        best = max(all_scores)
        if hero_score == best:
            n_at_best = sum(1 for s in all_scores if s == best)
            share = 1.0 / n_at_best
        else:
            share = 0.0
        share_sum += share
        share_sq_sum += share * share
        valid_samples += 1

    if valid_samples == 0:
        return 0.0, 0.0, 0
    mean = share_sum / valid_samples
    # Sample variance: E[X²] - E[X]². For binary {0,1} shares (no ties),
    # this reduces to mean*(1-mean) — matches Bernoulli.
    variance = max(0.0, (share_sq_sum / valid_samples) - mean * mean)
    return mean, variance, valid_samples


def hand_equity_vs_ranges(
    view: PlayerView,
    range_by_seat: dict[int, str],
    *,
    n_samples: int = 5000,
    seed: int | None = None,
) -> dict[str, Any]:
    """Compute hero equity vs villain ranges via multi-way Monte Carlo.

    spec §5.2.3 main API. Task 4 implements full validation + EquityResult
    return shape; this stub raises pending wiring.
    """
    raise NotImplementedError(
        "Phase 3c-equity Task 4 implements hand_equity_vs_ranges wrapping."
    )


__all__ = ["hand_equity_vs_ranges"]

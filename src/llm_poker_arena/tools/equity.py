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
        villain_scores = [backend.evaluate(tuple(list(v) + full_board)) for v in sampled_villains]
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


# Combo cap per villain range — defense against absurdly broad ranges
# (e.g., LLM passes "all reasonable hands" → MC samples become noise).
# spec doesn't mandate this; plan adds as safety rail. eval7 syntactically
# rejects "100%" but very broad valid ranges (~80-1000+ combos) can still
# happen. 500 is a generous-but-not-unbounded threshold.
_MAX_COMBOS_PER_RANGE = 500


def hand_equity_vs_ranges(
    view: PlayerView,
    range_by_seat: dict[int, str],
    *,
    n_samples: int = 5000,
    seed: int | None = None,
) -> dict[str, Any]:
    """Compute hero equity vs villain ranges via multi-way Monte Carlo.

    spec §5.2.3 main API. Returns EquityResult.model_dump() — a dict ready
    for IterationRecord.tool_result.

    Validation (raises ToolDispatchError):
      - range_by_seat.keys() must equal view.opponent_seats_in_hand
      - each range string must parse via eval7.HandRange
      - each parsed range must have 0 < combos <= 500 (combo cap)
      - all combos must have weight=1.0 (codex IMPORTANT-1: weighted
        ranges silently mishandled by uniform rng.choice — reject early)

    Determinism: caller passes seed; defaults to view.turn_seed if None.
    """
    import math

    from llm_poker_arena.agents.llm.types import EquityResult
    from llm_poker_arena.tools.equity_backend import Eval7Backend
    from llm_poker_arena.tools.runner import ToolDispatchError

    # 1. Strict key validation (spec §5.2.3).
    expected = set(view.opponent_seats_in_hand)
    provided = set(range_by_seat.keys())
    if provided != expected:
        missing = expected - provided
        extra = provided - expected
        raise ToolDispatchError(
            f"range_by_seat keys {sorted(provided)} must equal live opponent "
            f"seats {sorted(expected)}. Missing: {sorted(missing)}, "
            f"extra: {sorted(extra)}."
        )

    # 2. Parse ranges via eval7. Wrap RangeStringError as ToolDispatchError.
    villain_pools: list[tuple[_RangeCombo, ...]] = []
    for seat, range_str in sorted(range_by_seat.items()):
        try:
            parsed = eval7.HandRange(range_str)
        except eval7.rangestring.RangeStringError as e:
            raise ToolDispatchError(
                f"failed to parse range for seat {seat}: {range_str!r} — "
                f"{e!s}. Use eval7 HandRange syntax (e.g. 'QQ+, AKs+, AKo')."
            ) from e
        # 3. Combo cap.
        n_combos = len(parsed.hands)
        if n_combos == 0:
            raise ToolDispatchError(f"range for seat {seat} parses to 0 combos: {range_str!r}")
        if n_combos > _MAX_COMBOS_PER_RANGE:
            raise ToolDispatchError(
                f"range for seat {seat} parses to {n_combos} combos "
                f"(combo cap = {_MAX_COMBOS_PER_RANGE}); narrow the range."
            )
        # 3b. Codex audit IMPORTANT-1 fix: eval7 supports weighted syntax
        # like "40%(KK)" returning combos with non-1.0 weights. The MC
        # algorithm uses rng.choice() (uniform), which silently drops
        # weight info. For 3c-equity MVP, REJECT non-1.0 weights instead
        # of silently mishandling. system.j2 doesn't advertise weighted
        # syntax; if Claude tries it, error feedback teaches not to.
        for _combo, weight in parsed.hands:
            if weight != 1.0:
                raise ToolDispatchError(
                    f"range for seat {seat} contains weighted combo "
                    f"(weight={weight}); weighted ranges (e.g. '40%(KK)') "
                    f"are not supported in this version. Use unweighted "
                    f"syntax like 'QQ+, AKs'."
                )
        villain_pools.append(tuple(parsed.hands))

    # 4. Convert hero + community to eval7.Card.
    hero = tuple(eval7.Card(c) for c in view.my_hole_cards)
    board = tuple(eval7.Card(c) for c in view.community)

    # 5. Determine seed (spec §11.1: deterministic from view.turn_seed).
    effective_seed = seed if seed is not None else view.turn_seed

    # 6. Multi-way MC (rejection sampling — codex BLOCKER B1; multi-way
    # tie accounting — codex BLOCKER B2).
    backend = Eval7Backend()
    equity, share_variance, valid_samples = _multi_way_equity_mc(
        hero,
        board,
        villain_pools,
        backend,
        n_samples=n_samples,
        seed=effective_seed,
    )

    # 7. Edge case: max_attempts cap tripped without producing a single
    # valid sample (hero blocks the entire villain pool, etc). Surface as
    # ToolDispatchError so LLM gets actionable feedback.
    if valid_samples == 0:
        raise ToolDispatchError(
            "MC produced 0 valid samples — hero or board cards block "
            "every combo in at least one villain range. Adjust the range."
        )

    # 8. 95% CI from sample variance (multi-way correctness — codex NIT-1).
    # SE_of_mean = sqrt(sample_variance / n). For HU + no ties, this
    # reduces to sqrt(p(1-p)/n) — matches Bernoulli. For multi-way ties,
    # uses the actual fractional-share variance.
    se = math.sqrt(share_variance / valid_samples) if valid_samples > 0 else 0.0
    ci_half = 1.96 * se
    ci_low = max(0.0, equity - ci_half)
    ci_high = min(1.0, equity + ci_half)

    # 9. Build EquityResult (Pydantic validates equity ∈ [0, 1]).
    # With rejection sampling, valid_samples == n_samples (configured)
    # in non-pathological cases — n_samples field semantic preserved
    # (codex NIT-1 resolution: rejection-to-target).
    return EquityResult(
        hero_equity=equity,
        ci_low=ci_low,
        ci_high=ci_high,
        n_samples=valid_samples,
        seed=effective_seed,
        backend="eval7",
    ).model_dump(mode="json")


__all__ = ["hand_equity_vs_ranges"]

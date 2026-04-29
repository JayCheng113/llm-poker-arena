#!/usr/bin/env python3
"""Compare seat-5 P&L between two pilot arms (RuleBased vs ExploitBot).

Usage:
    python scripts/analyze_pilot.py \
        --rb-run  runs/demo-6llm-pilot-rb \
        --exp-run runs/demo-6llm-pilot-exp \
        --seat 5 \
        --bootstrap 10000

Reads `canonical_private.jsonl` from each arm, extracts the seat's
per-hand `result.net_pnl`, computes (Exploit - RuleBased) hand-paired
deltas, and reports mean + percentile-bootstrap 95 % CI.

Also walks `agent_view_snapshots.jsonl` of the exploit arm and tallies
`EXPLOIT-` rule fires by rule id (the prefix before the first colon in
the bot's rationale text).

Why "approximate pairing": both arms share `--seed`, so the deck shuffle
and button rotation are identical hand-by-hand. But LLM outputs are
non-deterministic at temperature 0.7, and the seat-5 agent itself
differs between arms — so the action tree diverges as soon as anyone
acts non-identically. The pairing is best-thought-of as "matched
hand-id with the same starting conditions", not "matched action-by-
action playthrough".
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path


def load_pnl(run_dir: Path, seat: int) -> dict[int, int]:
    """hand_id -> seat's net_pnl chip delta for that hand."""
    out: dict[int, int] = {}
    canon = run_dir / "canonical_private.jsonl"
    if not canon.exists():
        sys.exit(f"missing {canon}")
    for line in canon.open():
        d = json.loads(line)
        net = d["result"]["net_pnl"]
        out[d["hand_id"]] = int(net.get(str(seat), 0))
    return out


def count_exploit_fires(run_dir: Path, seat: int) -> tuple[int, dict[str, int], int]:
    """Returns (total_seat_turns, fires_by_rule_tag, hand_count_with_fire)."""
    snap = run_dir / "agent_view_snapshots.jsonl"
    if not snap.exists():
        return (0, {}, 0)
    fires: dict[str, int] = {}
    total = 0
    hands_with_fire: set[int] = set()
    for line in snap.open():
        d = json.loads(line)
        if d.get("seat") != seat:
            continue
        total += 1
        # exploit rationale always starts with "EXPLOIT-<rule>:" and
        # falls through to vanilla RuleBased text otherwise.
        try:
            txt = d["iterations"][0]["text_content"]
        except (KeyError, IndexError):
            continue
        if "EXPLOIT-" in txt:
            tag = txt.split(":", 1)[0].strip()
            fires[tag] = fires.get(tag, 0) + 1
            hands_with_fire.add(d["hand_id"])
    return (total, fires, len(hands_with_fire))


def bootstrap_ci(
    diffs: list[float], n_boot: int, alpha: float, rng: random.Random
) -> tuple[float, float, float]:
    """Returns (mean, lower_pct, upper_pct) with `1-alpha` coverage."""
    if not diffs:
        return (0.0, 0.0, 0.0)
    n = len(diffs)
    means: list[float] = []
    for _ in range(n_boot):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int(n_boot * (alpha / 2))
    hi_idx = int(n_boot * (1 - alpha / 2)) - 1
    return (statistics.mean(diffs), means[lo_idx], means[hi_idx])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rb-run", type=Path, required=True,
                   help="runs/<id> directory of the RuleBased baseline arm")
    p.add_argument("--exp-run", type=Path, required=True,
                   help="runs/<id> directory of the ExploitBot arm")
    p.add_argument("--seat", type=int, default=5,
                   help="seat being compared (the replaced one); default 5")
    p.add_argument("--bootstrap", type=int, default=10_000,
                   help="bootstrap resamples for CI; default 10k")
    p.add_argument("--alpha", type=float, default=0.05,
                   help="CI level: 0.05 → 95 %% CI; default 0.05")
    p.add_argument("--seed", type=int, default=0,
                   help="bootstrap RNG seed (for reproducible CI); default 0")
    args = p.parse_args()

    rng = random.Random(args.seed)

    rb = load_pnl(args.rb_run, args.seat)
    exp = load_pnl(args.exp_run, args.seat)

    common = sorted(set(rb) & set(exp))
    if not common:
        sys.exit("no overlapping hand_ids between the two arms — check inputs")
    if set(rb) != set(exp):
        only_rb = sorted(set(rb) - set(exp))
        only_exp = sorted(set(exp) - set(rb))
        print(f"warning: hand_id mismatch (only_rb={only_rb}, only_exp={only_exp}) "
              f"— restricting to {len(common)} matched hands.", file=sys.stderr)

    diffs = [exp[h] - rb[h] for h in common]
    rb_total = sum(rb[h] for h in common)
    exp_total = sum(exp[h] for h in common)
    mean_diff, lo, hi = bootstrap_ci(diffs, args.bootstrap, args.alpha, rng)

    rb_w = sum(1 for h in common if rb[h] > 0)
    exp_w = sum(1 for h in common if exp[h] > 0)
    paired_exp_better = sum(1 for d in diffs if d > 0)
    paired_rb_better = sum(1 for d in diffs if d < 0)
    paired_tied = sum(1 for d in diffs if d == 0)

    total_exp_turns, fires, hands_with_fire = count_exploit_fires(
        args.exp_run, args.seat
    )

    print(f"=== Seat-{args.seat} P&L pilot comparison ===")
    print(f"  hands matched:      {len(common)}  (rb={len(rb)} / exp={len(exp)})")
    print(f"  RuleBased   total:  {rb_total:+,d} chips  ({rb_w} winning hands)")
    print(f"  Exploit     total:  {exp_total:+,d} chips  ({exp_w} winning hands)")
    print()
    print("  per-hand diff (Exploit − RuleBased):")
    print(f"    mean:   {mean_diff:+.1f} chips/hand")
    pct = (1 - args.alpha) * 100
    print(f"    {pct:.0f}% CI: [{lo:+.1f}, {hi:+.1f}]  ({args.bootstrap} bootstrap)")
    if lo > 0:
        print("    ✓ exploit > rule_based (CI strictly above 0)")
    elif hi < 0:
        print("    ✗ exploit < rule_based (CI strictly below 0)")
    else:
        print(f"    ~ CI straddles 0 → no significant lift at α={args.alpha}")
    print()
    print(f"  paired hand wins: exp={paired_exp_better} / rb={paired_rb_better} / tied={paired_tied}")
    print()
    print("=== Exploit rule fires (in exp arm) ===")
    print(f"  total seat-{args.seat} turns: {total_exp_turns}")
    print(f"  hands with at least one fire: {hands_with_fire}")
    if not fires:
        print("  (no EXPLOIT- rule fired — exploit arm reduced to RuleBased baseline)")
    else:
        for tag in sorted(fires):
            print(f"    {tag}: {fires[tag]}")


if __name__ == "__main__":
    main()

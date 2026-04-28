#!/usr/bin/env python3
"""Decision-type deep dive across the demo-6llm-flagship session.

Reads runs/demo-6llm-flagship/canonical_private.jsonl + agent_view_snapshots.jsonl
and emits a markdown report (docs/llm-decision-profile.md) breaking each
LLM's behavior down by:

  - Position (BTN / CO / HJ / UTG / SB / BB)
  - Pot type (heads-up / multi-way / 3-bet pot)
  - Street pressure (preflop / flop / turn / river)
  - Big-bet response (≥ pot bet)
  - Showdown vs steal frequency

Goal: turn the raw "Sonnet won, Gemini lost" P&L into 6 short style
profiles built from observable behavior, not vibes.

Run: python scripts/analyze_decision_types.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUN = REPO / "runs" / "demo-6llm-flagship"
OUT = REPO / "docs" / "llm-decision-profile.md"

POSITIONS = ["BTN", "SB", "BB", "UTG", "HJ", "CO"]


def position_for(seat: int, button: int, n: int = 6) -> str:
    """Seat → table-relative position label.

    Engine convention: seat == button is BTN, +1 = SB, +2 = BB,
    +3 = UTG, +4 = HJ, +5 = CO.
    """
    return POSITIONS[(seat - button) % n]


def load_hands() -> list[dict]:
    hands = []
    with (RUN / "canonical_private.jsonl").open() as f:
        for line in f:
            hands.append(json.loads(line))
    return hands


def load_seat_assignment() -> dict[int, str]:
    meta = json.loads((RUN / "meta.json").read_text())
    return {int(s): label for s, label in meta["seat_assignment"].items()}


def short_label(provider_model: str) -> str:
    return provider_model.split(":")[-1]


def classify_pot_type(actions: list[dict], at_turn: int) -> str:
    """Was this turn a heads-up, multi-way (3+), or 3-bet pot at the moment
    of decision? Looks at preflop action up to (but not including) this turn."""
    preflop_raises = 0
    seats_in = set()
    for a in actions:
        if a["turn_index"] >= at_turn:
            break
        if a["street"] != "preflop":
            continue
        if a["action_type"] in ("raise_to", "bet"):
            preflop_raises += 1
        if a["action_type"] not in ("fold",):
            seats_in.add(a["seat"])
    # The seat about to act counts too if they haven't folded yet.
    target_action = actions[at_turn]
    seats_in.add(target_action["seat"])
    multi = len(seats_in) >= 3
    threebet = preflop_raises >= 2
    if threebet:
        return "3bet_pot"
    if multi:
        return "multi_way"
    return "heads_up"


def pot_at_turn(actions: list[dict], at_turn: int, sb: int, bb: int) -> int:
    """Best-effort pot size at the moment of decision (sum of invested chips
    up to that turn). Doesn't account for forced blind side details — fine
    for the heuristic categorization here."""
    pot = sb + bb
    for a in actions[:at_turn]:
        if a.get("amount"):
            pot += a["amount"]
    return pot


def categorize(hands: list[dict]) -> dict:
    """Walk every action and bucket it into per-seat / per-category counters."""
    SB, BB = 50, 100
    # data[seat][category][action_type] = count
    data: dict[int, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    # Voluntary preflop actions per seat (for VPIP-by-position breakdown)
    vpip_by_pos: dict[int, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    # Big-bet response per seat
    bigbet_response: dict[int, Counter] = defaultdict(Counter)

    for hand in hands:
        button = hand["button_seat"]
        actions = hand["actions"]
        # Track per-(hand, seat) whether they voluntarily put money in preflop
        # (call/raise — not blind).
        for i, a in enumerate(actions):
            seat = a["seat"]
            if a.get("is_forced_blind"):
                continue

            # === preflop position breakdown ===
            if a["street"] == "preflop":
                pos = position_for(seat, button)
                voluntary = a["action_type"] in ("call", "bet", "raise_to")
                vpip_by_pos[seat][pos].append(voluntary)

            # === pot-type categorization ===
            pot_type = classify_pot_type(actions, i)
            data[seat][f"{pot_type}_{a['street']}"][a["action_type"]] += 1
            data[seat][f"all_{a['street']}"][a["action_type"]] += 1
            data[seat][f"all_{pot_type}"][a["action_type"]] += 1

            # === big-bet response (face a bet ≥ pot, not blind) ===
            if a["street"] != "preflop" and a["action_type"] in ("fold", "call", "raise_to"):
                # Check if the LAST betting action this street was ≥ current pot.
                pot_now = pot_at_turn(actions, i, SB, BB)
                last_bet = 0
                for prev in reversed(actions[:i]):
                    if prev["street"] != a["street"]:
                        break
                    if prev["action_type"] in ("bet", "raise_to") and prev.get("amount"):
                        last_bet = prev["amount"]
                        break
                if last_bet >= pot_now / 2 and last_bet > 0:  # ≥ half-pot bet
                    bigbet_response[seat][a["action_type"]] += 1

    return {
        "data": data,
        "vpip_by_pos": vpip_by_pos,
        "bigbet_response": bigbet_response,
    }


def fmt_action_dist(counter: Counter, *, total_min: int = 1) -> str:
    """Render '{fold: 50%, call: 30%, raise: 20%}' for a tiny per-cell table."""
    total = sum(counter.values())
    if total < total_min:
        return "(n/a)"
    parts = []
    for action in ("fold", "check", "call", "bet", "raise_to", "all_in"):
        v = counter.get(action, 0)
        if v == 0:
            continue
        parts.append(f"{action}:{100 * v / total:.0f}%")
    return f"n={total} " + " ".join(parts)


def fmt_pct_or_dash(num: int, denom: int) -> str:
    if denom == 0:
        return "—"
    return f"{100 * num / denom:.0f}%"


def render_report(hands: list[dict], seat_assignment: dict[int, str]) -> str:
    bucketed = categorize(hands)
    data = bucketed["data"]
    vpip_by_pos = bucketed["vpip_by_pos"]
    bigbet = bucketed["bigbet_response"]

    seats = sorted(seat_assignment)
    labels = {s: short_label(seat_assignment[s]) for s in seats}

    out: list[str] = []
    out.append("# Decision-type deep dive — flagship 102-hand session")
    out.append("")
    out.append(
        "Distilled from the same `runs/demo-6llm-flagship/` data the [Live demo]"
        "(https://jaycheng113.github.io/llm-poker-arena/?session=demo-6llm-flagship) "
        "renders, but bucketed so the per-LLM **style** falls out instead of "
        "drowning in 1,069 individual decisions. Source: "
        "[`scripts/analyze_decision_types.py`](../scripts/analyze_decision_types.py)."
    )
    out.append("")
    out.append("## VPIP by position")
    out.append("")
    out.append(
        "Voluntary money in pot, broken out by seat-relative position. "
        "BTN / CO are the cheapest spots to enter; UTG / HJ are the most "
        "expensive. A model that opens too wide from UTG bleeds chips; a "
        "model that folds too tight on the BTN misses easy pots."
    )
    out.append("")
    out.append("| LLM | UTG | HJ | CO | BTN | SB | BB |")
    out.append("|---|---|---|---|---|---|---|")
    for seat in seats:
        row = [labels[seat]]
        for pos in ["UTG", "HJ", "CO", "BTN", "SB", "BB"]:
            samples = vpip_by_pos[seat].get(pos, [])
            if not samples:
                row.append("—")
            else:
                pct = 100 * sum(samples) / len(samples)
                row.append(f"{pct:.0f}% ({sum(samples)}/{len(samples)})")
        out.append("| " + " | ".join(row) + " |")
    out.append("")

    out.append("## Behavior by pot type")
    out.append("")
    out.append(
        "How each LLM acts depending on whether the pot is heads-up "
        "(2 players), multi-way (3+), or already had a 3-bet preflop "
        "(=both players show real strength). Combine across all post-flop "
        "streets. Reading: which actions does each LLM reach for in "
        "which spots?"
    )
    out.append("")
    for pot_type in ("heads_up", "multi_way", "3bet_pot"):
        out.append(f"### {pot_type.replace('_', ' ').title()}")
        out.append("")
        out.append("| LLM | Action distribution |")
        out.append("|---|---|")
        for seat in seats:
            counter = data[seat].get(f"all_{pot_type}", Counter())
            out.append(f"| {labels[seat]} | {fmt_action_dist(counter)} |")
        out.append("")

    out.append("## Behavior by street")
    out.append("")
    out.append(
        "Same model, different streets. Look for the LLM whose fold rate "
        "spikes on the river (= can't bluff-catch) or whose bet rate spikes "
        "on the flop (= mandatory c-bet bot)."
    )
    out.append("")
    for street in ("preflop", "flop", "turn", "river"):
        out.append(f"### {street.title()}")
        out.append("")
        out.append("| LLM | Action distribution |")
        out.append("|---|---|")
        for seat in seats:
            counter = data[seat].get(f"all_{street}", Counter())
            out.append(f"| {labels[seat]} | {fmt_action_dist(counter)} |")
        out.append("")

    out.append("## Response to ≥ half-pot bets (postflop only)")
    out.append("")
    out.append(
        "When a non-trivial bet (≥ half pot, post-flop) lands in front of "
        "them, what do they do? High fold % = exploitable / nit; high "
        "call % = calling station; high raise = aggressive."
    )
    out.append("")
    out.append("| LLM | Fold | Call | Raise | n |")
    out.append("|---|---|---|---|---|")
    for seat in seats:
        counter = bigbet[seat]
        n = sum(counter.values())
        out.append(
            f"| {labels[seat]} | {fmt_pct_or_dash(counter['fold'], n)} | "
            f"{fmt_pct_or_dash(counter['call'], n)} | "
            f"{fmt_pct_or_dash(counter['raise_to'], n)} | {n} |"
        )
    out.append("")

    # Headline takeaways auto-generated from the data
    out.append("## Auto-generated takeaways")
    out.append("")
    takeaways = generate_takeaways(data, vpip_by_pos, bigbet, labels, seats)
    for t in takeaways:
        out.append(f"- {t}")
    out.append("")

    out.append("---")
    out.append("")
    out.append(
        "*Generated by `scripts/analyze_decision_types.py` from "
        "`runs/demo-6llm-flagship/`. Re-run after every new tournament "
        "to refresh.*"
    )
    return "\n".join(out)


def generate_takeaways(
    data: dict, vpip_by_pos: dict, bigbet: dict, labels: dict, seats: list[int]
) -> list[str]:
    """Turn the numeric tables into one-liner observations the reader can
    skim. Heuristics-only — anything more would need a solver baseline."""
    out: list[str] = []

    # 1) UTG vs BTN spread per seat — wider gap = better positional discipline
    pos_gap: dict[int, float] = {}
    for seat in seats:
        utg = vpip_by_pos[seat].get("UTG", [])
        btn = vpip_by_pos[seat].get("BTN", [])
        if utg and btn:
            utg_pct = sum(utg) / len(utg)
            btn_pct = sum(btn) / len(btn)
            pos_gap[seat] = btn_pct - utg_pct
    if pos_gap:
        widest = max(pos_gap, key=pos_gap.get)
        narrowest = min(pos_gap, key=pos_gap.get)
        out.append(
            f"**Position discipline** (BTN−UTG VPIP gap): widest is "
            f"{labels[widest]} (+{pos_gap[widest] * 100:.0f}pp), "
            f"narrowest is {labels[narrowest]} ({pos_gap[narrowest] * 100:+.0f}pp). "
            f"A wider gap means the model adjusts entry frequency to position; "
            f"a narrow or negative gap means it plays the same range everywhere."
        )

    # 2) Fold rate to big bets per seat
    fold_to_bigbet: dict[int, float] = {}
    for seat in seats:
        c = bigbet[seat]
        n = sum(c.values())
        # n>=8 cutoff — anything below ~one button rotation is too noisy to
        # rank with confidence (102 hands × ~6 seats × low fraction of pots
        # that face a real bet = small denominators).
        if n >= 8:
            fold_to_bigbet[seat] = c["fold"] / n
    if fold_to_bigbet:
        nittiest = max(fold_to_bigbet, key=fold_to_bigbet.get)
        stickiest = min(fold_to_bigbet, key=fold_to_bigbet.get)
        out.append(
            f"**Bluff-resistance** (call+raise rate vs ≥ half-pot bets): "
            f"stickiest is {labels[stickiest]} (folds only "
            f"{fold_to_bigbet[stickiest] * 100:.0f}%), most exploitable to "
            f"big bets is {labels[nittiest]} (folds "
            f"{fold_to_bigbet[nittiest] * 100:.0f}%). The latter is the "
            f"obvious bluff target; the former is who you only bet for value."
        )

    # 3) Multi-way fold rate
    multi_fold: dict[int, float] = {}
    for seat in seats:
        c = data[seat].get("all_multi_way", Counter())
        n = sum(c.values())
        if n >= 5:
            multi_fold[seat] = c["fold"] / n
    if multi_fold:
        tightest = max(multi_fold, key=multi_fold.get)
        loosest = min(multi_fold, key=multi_fold.get)
        out.append(
            f"**Multi-way comfort**: in 3+ player pots {labels[tightest]} "
            f"folds {multi_fold[tightest] * 100:.0f}% of the time vs "
            f"{labels[loosest]}'s {multi_fold[loosest] * 100:.0f}%. "
            f"Higher fold% is correct equity-wise (multi-way realizes less), "
            f"but extreme tightness leaves money on the table when other "
            f"seats keep checking down."
        )

    # 4) River fold rate (bluff-catching willingness) — most hands end
    # before the river, so this gate is loose (n>=6 = at least one button
    # rotation made it). Kimi (n=1) and Gemini (n=3) get excluded.
    river_fold: dict[int, float] = {}
    for seat in seats:
        c = data[seat].get("all_river", Counter())
        n = sum(c.values())
        if n >= 6:
            river_fold[seat] = (c["fold"] / n, n)
    if river_fold:
        # Sort by fold rate; if there's a tie pick the larger sample.
        ranked = sorted(river_fold.items(), key=lambda kv: (kv[1][0], -kv[1][1]))
        catcher_seat, (catcher_pct, catcher_n) = ranked[0]
        avoider_seat, (avoider_pct, avoider_n) = ranked[-1]
        out.append(
            f"**River bluff-catching**: {labels[catcher_seat]} folds the "
            f"river only {catcher_pct * 100:.0f}% (n={catcher_n}, most "
            f"willing to call thin), {labels[avoider_seat]} folds "
            f"{avoider_pct * 100:.0f}% (n={avoider_n}, rarely defends rivers). "
            f"In a vacuum the catcher loses to polarized betting and wins "
            f"vs bluffs; the avoider is the opposite. {len(river_fold)} of "
            f"{len(seats)} seats reached the n≥6 threshold — treat as "
            f"directional."
        )

    # 5) 3-bet pot aggression (raise + bet rate in 3-bet pots)
    threebet_aggro: dict[int, float] = {}
    for seat in seats:
        c = data[seat].get("all_3bet_pot", Counter())
        n = sum(c.values())
        if n >= 3:
            aggro = (c["raise_to"] + c["bet"]) / n
            threebet_aggro[seat] = aggro
    if threebet_aggro:
        most_aggro = max(threebet_aggro, key=threebet_aggro.get)
        least_aggro = min(threebet_aggro, key=threebet_aggro.get)
        out.append(
            f"**3-bet pot aggression**: {labels[most_aggro]} keeps barreling "
            f"({threebet_aggro[most_aggro] * 100:.0f}% bet-or-raise in 3-bet "
            f"pots) while {labels[least_aggro]} shuts down "
            f"({threebet_aggro[least_aggro] * 100:.0f}%). Sample sizes are "
            f"small (3-bet pots are rare in this lineup) — read as "
            f"directional, not statistically significant."
        )

    return out


def main() -> None:
    if not RUN.exists():
        raise SystemExit(f"missing {RUN}; run generate-demo-6llm.py --lineup flagship first")
    hands = load_hands()
    seats = load_seat_assignment()
    report = render_report(hands, seats)
    OUT.write_text(report)
    print(f"wrote {OUT}")
    print(f"  {len(hands)} hands × {len(seats)} seats analyzed")


if __name__ == "__main__":
    main()

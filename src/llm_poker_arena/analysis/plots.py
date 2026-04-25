"""matplotlib chart rendering over Phase-2a session outputs + DuckDB metrics.

All functions save a PNG to `session_dir/plots/<name>.png` and return the
Path. Phase 2a session_id is pulled from meta.json for subtitle annotations.

Risk 11: `matplotlib.use("Agg")` MUST run before `pyplot` is imported so
tests never try to open a GUI backend.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  — Agg backend must be set first

from llm_poker_arena.analysis.metrics import (
    compute_action_distribution,
    compute_pfr,
    compute_vpip,
)
from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN
from llm_poker_arena.storage.duckdb_query import open_session


def _meta(session_dir: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads((session_dir / "meta.json").read_text())
    return data


def _plots_dir(session_dir: Path) -> Path:
    d = session_dir / "plots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def plot_chip_pnl(session_dir: Path) -> Path:
    """Per-seat net P&L bar chart, sorted by seat."""
    meta = _meta(session_dir)
    chip_pnl = meta["chip_pnl"]
    assert isinstance(chip_pnl, dict)
    seats = sorted(int(k) for k in chip_pnl)
    values = [int(chip_pnl[str(s)]) for s in seats]

    fig, ax = plt.subplots(figsize=(7, 4))
    colors = ["steelblue" if v >= 0 else "indianred" for v in values]
    ax.bar([str(s) for s in seats], values, color=colors)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("seat")
    ax.set_ylabel("net chips (end of session)")
    ax.set_title(f"Chip P&L — {meta.get('session_id', '?')}")
    fig.tight_layout()

    out = _plots_dir(session_dir) / "chip_pnl.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def plot_vpip_pfr_table(session_dir: Path) -> Path:
    """Side-by-side bar chart of per-seat VPIP + PFR."""
    meta = _meta(session_dir)
    with open_session(session_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        vpip = {r["seat"]: r["vpip_rate"] for r in compute_vpip(con)}
        pfr = {r["seat"]: r["pfr_rate"] for r in compute_pfr(con)}

    seats = sorted(vpip)
    vpip_vals = [vpip[s] for s in seats]
    pfr_vals = [pfr[s] for s in seats]

    fig, ax = plt.subplots(figsize=(7, 4))
    import numpy as np

    x = np.arange(len(seats))
    width = 0.35
    ax.bar(x - width / 2, vpip_vals, width, label="VPIP", color="steelblue")
    ax.bar(x + width / 2, pfr_vals, width, label="PFR", color="darkorange")
    ax.set_xticks(x)
    ax.set_xticklabels([str(s) for s in seats])
    ax.set_xlabel("seat")
    ax.set_ylabel("rate")
    ax.set_ylim(0, 1)
    ax.legend()
    ax.set_title(f"VPIP / PFR — {meta.get('session_id', '?')}")
    fig.tight_layout()

    out = _plots_dir(session_dir) / "vpip_pfr.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def plot_action_distribution(session_dir: Path) -> Path:
    """Per-(seat, street) action-type stacked bar chart."""
    meta = _meta(session_dir)
    with open_session(session_dir, access_token=PRIVATE_ACCESS_TOKEN) as con:
        rows = compute_action_distribution(con)

    # Aggregate to (seat, street) → {action_type: rate}.
    agg: dict[tuple[int, str], dict[str, float]] = {}
    for r in rows:
        key = (int(r["seat"]), str(r["street"]))
        agg.setdefault(key, {})[str(r["action_type"])] = float(r["rate_within_street"])

    streets = ["preflop", "flop", "turn", "river"]
    seats = sorted({k[0] for k in agg})
    action_types = ("fold", "check", "call", "bet", "raise_to", "all_in")
    color_map = {
        "fold": "#999999", "check": "#a6cee3", "call": "#1f78b4",
        "bet": "#b2df8a", "raise_to": "#e31a1c", "all_in": "#ff7f00",
    }

    fig, axes = plt.subplots(
        1, len(streets), figsize=(14, 4), sharey=True,
    )
    for ax, street in zip(axes, streets, strict=True):
        bottoms = [0.0] * len(seats)
        for at in action_types:
            rates = [agg.get((s, street), {}).get(at, 0.0) for s in seats]
            ax.bar(
                [str(s) for s in seats], rates,
                bottom=bottoms, label=at, color=color_map[at],
            )
            bottoms = [b + r for b, r in zip(bottoms, rates, strict=True)]
        ax.set_title(street)
        ax.set_ylim(0, 1.01)
        ax.set_xlabel("seat")
    axes[0].set_ylabel("action rate within street")
    axes[-1].legend(loc="upper right", fontsize=7)
    fig.suptitle(f"Action Distribution — {meta.get('session_id', '?')}")
    fig.tight_layout()

    out = _plots_dir(session_dir) / "action_distribution.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out

"""Eval7Backend basic correctness — relative hand ordering.

eval7.evaluate returns higher integers for stronger hands. We assert the
ordering of well-known holdem hand ranks rather than specific values
(eval7's exact ranking constants are an implementation detail).
"""

from __future__ import annotations

import eval7

from llm_poker_arena.tools.equity_backend import Eval7Backend


def _cards(*names: str) -> tuple[eval7.Card, ...]:
    return tuple(eval7.Card(n) for n in names)


def test_eval7_backend_evaluate_higher_for_stronger_hand() -> None:
    backend = Eval7Backend()
    # AAA full vs straight on same board.
    aces_full = backend.evaluate(_cards("Ah", "Ad", "As", "Ac", "Kh", "Kd", "2c"))
    straight = backend.evaluate(_cards("Th", "Jh", "Qh", "Kh", "Ad", "5c", "2c"))
    assert aces_full > straight


def test_eval7_backend_evaluate_pair_beats_high_card() -> None:
    backend = Eval7Backend()
    pair = backend.evaluate(_cards("As", "Ad", "Kh", "Qc", "Jd", "9s", "7c"))
    high = backend.evaluate(_cards("As", "Kc", "Qd", "Jh", "9s", "7c", "3d"))
    assert pair > high


def test_eval7_backend_evaluate_returns_int() -> None:
    backend = Eval7Backend()
    rank = backend.evaluate(_cards("As", "Ks", "Qs", "Js", "Ts", "2c", "3d"))
    assert isinstance(rank, int)

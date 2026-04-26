"""EquityBackend ABC + Eval7Backend impl (spec §5.2.2 minimal subset).

Spec defines an EquityBackend interface meant to be backend-agnostic at
the Card boundary. Phase 3c-equity ships ONE backend (eval7) and accepts
the spec deviation: EquityBackend.evaluate is typed against eval7.Card
directly, NOT abstracted to CardStr. Justification: card-string-to-eval7-Card
conversion inside the 5000-iteration MC loop costs measurable overhead
(~210K conversions per equity call). Future TreysBackend would force
introducing a backend-internal Card adapter — refactor when actually needed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import eval7


class EquityBackend(ABC):
    """spec §5.2.2: pluggable hand evaluator + (someday) range parser."""

    @abstractmethod
    def evaluate(self, cards: tuple[eval7.Card, ...]) -> int:
        """Return the hand rank (higher = stronger) for a 5-7 card hand.
        Backend-defined integer scale; only relative ordering matters."""


class Eval7Backend(EquityBackend):
    """Concrete backend wrapping eval7's C-extension hand evaluator."""

    def evaluate(self, cards: tuple[eval7.Card, ...]) -> int:
        import eval7
        return int(eval7.evaluate(list(cards)))


__all__ = ["EquityBackend", "Eval7Backend"]

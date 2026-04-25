"""HumanCLIAgent: sync Agent that reads actions from a terminal.

Dogfood implementation for pre-Phase-3 play. When Phase 3 widens the
`Agent` ABC to `async def decide(view, tool_runner) -> TurnDecisionResult`,
this class will be rewritten to match.

I/O is injectable (via `input_stream` + `output_stream` constructor args)
so unit tests can drive it deterministically. Production default is
`sys.stdin` / `sys.stdout`.
"""
from __future__ import annotations

import sys
from typing import TextIO

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import TokenCounts, TurnDecisionResult
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.views import PlayerView

_VALID_ACTION_NAMES: frozenset[str] = frozenset(
    {"fold", "check", "call", "bet", "raise_to", "all_in"}
)


class HumanCLIAgent(Agent):
    """Sync human agent reading from a text stream. See module docstring."""

    def __init__(
        self,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
    ) -> None:
        self._in: TextIO = input_stream if input_stream is not None else sys.stdin
        self._out: TextIO = output_stream if output_stream is not None else sys.stdout

    def provider_id(self) -> str:
        return "human:cli_v1"

    # ----- Agent ABC -------------------------------------------------

    async def decide(self, view: PlayerView) -> TurnDecisionResult:
        action = self._pick_action(view)
        return TurnDecisionResult(
            iterations=(),
            final_action=action,
            total_tokens=TokenCounts.zero(),
            wall_time_ms=0,
            api_retry_count=0, illegal_action_retry_count=0,
            no_tool_retry_count=0, tool_usage_error_count=0,
            default_action_fallback=False,
            api_error=None, turn_timeout_exceeded=False,
        )

    def _pick_action(self, view: PlayerView) -> Action:
        self._render_view(view)
        legal = {t.name for t in view.legal_actions.tools}
        while True:
            tool_name = self._prompt("Choose action: ").strip()
            if tool_name not in _VALID_ACTION_NAMES:
                self._emit(
                    f"'{tool_name}' is not a known action. "
                    f"Valid: {sorted(_VALID_ACTION_NAMES)}\n"
                )
                continue
            if tool_name not in legal:
                self._emit(
                    f"'{tool_name}' is not in legal set this turn: "
                    f"{sorted(legal)}\n"
                )
                continue
            if tool_name in ("bet", "raise_to"):
                spec = next(t for t in view.legal_actions.tools if t.name == tool_name)
                bounds = spec.args.get("amount") if isinstance(spec.args, dict) else None
                if not isinstance(bounds, dict):
                    self._emit(f"'{tool_name}' missing amount bounds (engine bug?)\n")
                    continue
                amount = self._prompt_amount(int(bounds["min"]), int(bounds["max"]))
                return Action(tool_name=tool_name, args={"amount": amount})
            return Action(tool_name=tool_name, args={})

    # ----- internals -------------------------------------------------

    def _prompt_amount(self, min_amt: int, max_amt: int) -> int:
        while True:
            raw = self._prompt(
                f"Amount (int in [{min_amt}, {max_amt}]): "
            ).strip()
            try:
                amt = int(raw)
            except ValueError:
                self._emit(f"'{raw}' is not an integer\n")
                continue
            if not (min_amt <= amt <= max_amt):
                self._emit(f"{amt} is out of bounds [{min_amt}, {max_amt}]\n")
                continue
            return amt

    def _render_view(self, view: PlayerView) -> None:
        hid = view.hand_id
        my_seat = view.my_seat
        my_info = view.seats_public[my_seat]
        to_call = view.current_bet_to_match - view.my_invested_this_round

        self._emit("\n" + "=" * 60 + "\n")
        self._emit(
            f"Hand {hid}  |  your seat: {my_seat} ({my_info.position_short})  "
            f"|  street: {view.street.value}\n"
        )
        self._emit(
            f"Button: seat {view.button_seat}  |  pot: {view.pot}  "
            f"|  your stack: {view.my_stack}  |  to_call: {to_call}\n"
        )
        if view.community:
            self._emit(f"Community: {' '.join(view.community)}\n")
        self._emit(f"Your hole cards: {' '.join(view.my_hole_cards)}\n")
        self._emit("Other seats:\n")
        for s in view.seats_public:
            if s.seat == my_seat:
                continue
            self._emit(
                f"  seat {s.seat} ({s.label}, {s.position_short}): "
                f"{s.stack} chips, {s.status}\n"
            )
        self._emit("Legal actions this turn:\n")
        for t in view.legal_actions.tools:
            if t.name in ("bet", "raise_to"):
                bounds = t.args.get("amount") if isinstance(t.args, dict) else None
                if isinstance(bounds, dict):
                    self._emit(
                        f"  {t.name}  (amount in [{bounds['min']}, {bounds['max']}])\n"
                    )
                else:
                    self._emit(f"  {t.name}\n")
            else:
                self._emit(f"  {t.name}\n")
        self._emit("-" * 60 + "\n")

    def _prompt(self, prompt: str) -> str:
        self._emit(prompt)
        line = self._in.readline()
        if line == "":  # EOF
            raise EOFError("HumanCLIAgent: input stream closed during prompt")
        return line.rstrip("\n")

    def _emit(self, text: str) -> None:
        self._out.write(text)
        self._out.flush()

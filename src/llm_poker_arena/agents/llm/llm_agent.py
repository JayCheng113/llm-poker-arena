"""LLMAgent: K=0 simplified Bounded ReAct (spec §4.2 Phase 3a).

Phase 3a constraints:
  - max_utility_calls=0 → loop is "one action step, with retry".
  - tools sent to the provider include ONLY action tools (no utility tools).
  - retry budgets:
      api_retry_count ≤ 1 (transient → backoff → retry once)
      illegal_action_retry_count ≤ 1 (illegal → message + retry once)
      no_tool_retry_count ≤ 1 (text-only → message + retry once)
  - on transient exhaustion: api_error set, final_action=None.
  - on illegal/no_tool exhaustion: default_safe_action fallback, api_error=None.
  - on permanent provider error: api_error set, no retry.
  - per-iteration timeout + total-turn timeout via asyncio.wait_for.

Out of scope (3c+): utility tools, range parser, equity backend, HUD stats.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from typing import Any

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.provider_base import (
    LLMProvider,
    ProviderPermanentError,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.types import (
    ApiErrorInfo,
    IterationRecord,
    LLMResponse,
    TokenCounts,
    TurnDecisionResult,
)
from llm_poker_arena.engine.legal_actions import (
    Action,
    default_safe_action,
    validate_action,
)
from llm_poker_arena.engine.views import PlayerView

_SYSTEM_PROMPT = """You are a player in a No-Limit Texas Hold'em 6-max cash game simulation.

YOUR ROLE
- See only your hole cards.
- Maximize chip EV over many hands.

HOW TO ACT
- Each turn you receive game state and a list of legal action tools.
- Briefly state your reasoning, then call exactly one action tool.
- Tools not in the list are not legal this turn.
- Bet/raise amounts must be in the integer range advertised by the tool.

Respond in English."""


class LLMAgent(Agent):
    def __init__(
        self,
        *,
        provider: LLMProvider,
        model: str,
        temperature: float = 0.7,
        seed: int | None = None,
        per_iteration_timeout_sec: float = 60.0,
        total_turn_timeout_sec: float = 180.0,
        version: str = "phase3a",
    ) -> None:
        self._provider = provider
        self._model = model
        self._temperature = temperature
        self._seed = seed
        self._per_iter_timeout = per_iteration_timeout_sec
        self._total_turn_timeout = total_turn_timeout_sec
        self._version = version

    def provider_id(self) -> str:
        return f"{self._provider.provider_name()}:{self._model}"

    async def decide(self, view: PlayerView) -> TurnDecisionResult:
        try:
            return await asyncio.wait_for(
                self._decide_inner(view),
                timeout=self._total_turn_timeout,
            )
        except TimeoutError:
            return TurnDecisionResult(
                iterations=(),
                final_action=None,
                total_tokens=TokenCounts.zero(),
                wall_time_ms=int(self._total_turn_timeout * 1000),
                api_retry_count=0, illegal_action_retry_count=0,
                no_tool_retry_count=0, tool_usage_error_count=0,
                default_action_fallback=False,
                api_error=ApiErrorInfo(
                    type="TotalTurnTimeout",
                    detail=f"exceeded {self._total_turn_timeout}s",
                ),
                turn_timeout_exceeded=True,
            )

    async def _decide_inner(self, view: PlayerView) -> TurnDecisionResult:
        MAX_API_RETRY = 1
        MAX_ILLEGAL_RETRY = 1
        MAX_NO_TOOL_RETRY = 1
        MAX_STEPS = 4

        api_retry = 0
        illegal_retry = 0
        no_tool_retry = 0
        tool_usage_error_count = 0

        iterations: list[IterationRecord] = []
        messages: list[dict[str, Any]] = self._build_initial_messages(view)
        action_tools = _action_tool_specs(view)
        turn_start = time.monotonic()
        total_tokens = TokenCounts.zero()

        for step in range(MAX_STEPS):
            digest = _digest_messages(messages)
            iter_start = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    self._provider.complete(
                        messages=messages, tools=action_tools,
                        temperature=self._temperature, seed=self._seed,
                    ),
                    timeout=self._per_iter_timeout,
                )
            except (TimeoutError, ProviderTransientError) as e:
                err_type = (
                    "ProviderTransientError"
                    if isinstance(e, ProviderTransientError)
                    else "PerIterationTimeout"
                )
                iter_record = IterationRecord(
                    step=step + 1,
                    request_messages_digest=digest,
                    provider_response_kind="error",
                    tool_call=None,
                    text_content=str(e),
                    tokens=TokenCounts.zero(),
                    wall_time_ms=int((time.monotonic() - iter_start) * 1000),
                )
                iterations.append(iter_record)
                if api_retry < MAX_API_RETRY:
                    api_retry += 1
                    await asyncio.sleep(0.5 + random.random() * 0.5)
                    continue
                return self._fail_with_api_error(
                    iterations, total_tokens, turn_start,
                    api_retry, illegal_retry, no_tool_retry,
                    err_type=err_type, detail=str(e),
                    tool_usage_error_count=tool_usage_error_count,
                )
            except ProviderPermanentError as e:
                iter_record = IterationRecord(
                    step=step + 1,
                    request_messages_digest=digest,
                    provider_response_kind="error",
                    tool_call=None,
                    text_content=str(e),
                    tokens=TokenCounts.zero(),
                    wall_time_ms=int((time.monotonic() - iter_start) * 1000),
                )
                iterations.append(iter_record)
                return self._fail_with_api_error(
                    iterations, total_tokens, turn_start,
                    api_retry, illegal_retry, no_tool_retry,
                    err_type="ProviderPermanentError", detail=str(e),
                    tool_usage_error_count=tool_usage_error_count,
                )

            iter_ms = int((time.monotonic() - iter_start) * 1000)
            total_tokens = total_tokens + response.tokens

            if not response.tool_calls:
                iter_record = IterationRecord(
                    step=step + 1,
                    request_messages_digest=digest,
                    provider_response_kind="no_tool",
                    tool_call=None,
                    text_content=response.text_content,
                    tokens=response.tokens,
                    wall_time_ms=iter_ms,
                )
                iterations.append(iter_record)
                if no_tool_retry < MAX_NO_TOOL_RETRY:
                    no_tool_retry += 1
                    messages.append(_assistant_message(response))
                    messages.append(_user_text(
                        "You must call exactly one action tool. Try again."
                    ))
                    continue
                return self._fallback_default_safe(
                    view, iterations, total_tokens, turn_start,
                    api_retry, illegal_retry, no_tool_retry,
                    tool_usage_error_count=tool_usage_error_count,
                )

            # Multi-tool-call response is misuse: count + retry via illegal slot.
            if len(response.tool_calls) > 1:
                tool_usage_error_count += 1
                first_tc = response.tool_calls[0]
                iter_record = IterationRecord(
                    step=step + 1,
                    request_messages_digest=digest,
                    provider_response_kind="tool_use",
                    tool_call=first_tc,
                    text_content=response.text_content,
                    tokens=response.tokens,
                    wall_time_ms=iter_ms,
                )
                iterations.append(iter_record)
                if illegal_retry < MAX_ILLEGAL_RETRY:
                    illegal_retry += 1
                    messages.append(_assistant_message(response))
                    messages.append(_tool_result_user(
                        tool_use_id=first_tc.tool_use_id,
                        is_error=True,
                        content=(
                            f"Multiple tool calls in one response are not "
                            f"allowed. Got {len(response.tool_calls)} calls; "
                            f"call exactly one action tool."
                        ),
                    ))
                    continue
                return self._fallback_default_safe(
                    view, iterations, total_tokens, turn_start,
                    api_retry, illegal_retry, no_tool_retry,
                    tool_usage_error_count=tool_usage_error_count,
                )

            tc = response.tool_calls[0]
            candidate = Action(tool_name=tc.name, args=dict(tc.args or {}))
            v = validate_action(view, candidate)
            iter_record = IterationRecord(
                step=step + 1,
                request_messages_digest=digest,
                provider_response_kind="tool_use",
                tool_call=tc,
                text_content=response.text_content,
                tokens=response.tokens,
                wall_time_ms=iter_ms,
            )
            iterations.append(iter_record)
            if v.is_valid:
                return TurnDecisionResult(
                    iterations=tuple(iterations),
                    final_action=candidate,
                    total_tokens=total_tokens,
                    wall_time_ms=int((time.monotonic() - turn_start) * 1000),
                    api_retry_count=api_retry,
                    illegal_action_retry_count=illegal_retry,
                    no_tool_retry_count=no_tool_retry,
                    tool_usage_error_count=tool_usage_error_count,
                    default_action_fallback=False,
                    api_error=None,
                    turn_timeout_exceeded=False,
                )

            if illegal_retry < MAX_ILLEGAL_RETRY:
                illegal_retry += 1
                messages.append(_assistant_message(response))
                messages.append(_tool_result_user(
                    tool_use_id=tc.tool_use_id,
                    is_error=True,
                    content=(
                        f"Illegal action: {v.reason}. Legal action tools: "
                        f"{[t.name for t in view.legal_actions.tools]}. "
                        f"Call exactly one of those next."
                    ),
                ))
                continue

            return self._fallback_default_safe(
                view, iterations, total_tokens, turn_start,
                api_retry, illegal_retry, no_tool_retry,
                tool_usage_error_count=tool_usage_error_count,
            )

        return self._fallback_default_safe(
            view, iterations, total_tokens, turn_start,
            api_retry, illegal_retry, no_tool_retry,
            tool_usage_error_count=tool_usage_error_count,
        )

    def _build_initial_messages(self, view: PlayerView) -> list[dict[str, Any]]:
        return [{"role": "user", "content": _user_prompt_for(view)}]

    def _fail_with_api_error(
        self,
        iterations: list[IterationRecord],
        total_tokens: TokenCounts,
        turn_start: float,
        api_retry: int, illegal_retry: int, no_tool_retry: int,
        *, err_type: str, detail: str,
        tool_usage_error_count: int = 0,
    ) -> TurnDecisionResult:
        return TurnDecisionResult(
            iterations=tuple(iterations),
            final_action=None,
            total_tokens=total_tokens,
            wall_time_ms=int((time.monotonic() - turn_start) * 1000),
            api_retry_count=api_retry,
            illegal_action_retry_count=illegal_retry,
            no_tool_retry_count=no_tool_retry,
            tool_usage_error_count=tool_usage_error_count,
            default_action_fallback=False,
            api_error=ApiErrorInfo(type=err_type, detail=detail),
            turn_timeout_exceeded=False,
        )

    def _fallback_default_safe(
        self,
        view: PlayerView,
        iterations: list[IterationRecord],
        total_tokens: TokenCounts,
        turn_start: float,
        api_retry: int, illegal_retry: int, no_tool_retry: int,
        *, tool_usage_error_count: int = 0,
    ) -> TurnDecisionResult:
        return TurnDecisionResult(
            iterations=tuple(iterations),
            final_action=default_safe_action(view),
            total_tokens=total_tokens,
            wall_time_ms=int((time.monotonic() - turn_start) * 1000),
            api_retry_count=api_retry,
            illegal_action_retry_count=illegal_retry,
            no_tool_retry_count=no_tool_retry,
            tool_usage_error_count=tool_usage_error_count,
            default_action_fallback=True,
            api_error=None,
            turn_timeout_exceeded=False,
        )


# ---------- helpers ----------

def _digest_messages(messages: list[dict[str, Any]]) -> str:
    """Stable hash for IterationRecord traceability."""
    blob = json.dumps(messages, sort_keys=True, default=str).encode()
    return f"sha256:{hashlib.sha256(blob).hexdigest()[:16]}"


def _action_tool_specs(view: PlayerView) -> list[dict[str, Any]]:
    """Convert PlayerView's LegalActionSet into Anthropic tool-call schema."""
    out: list[dict[str, Any]] = []
    for spec in view.legal_actions.tools:
        if spec.name in ("bet", "raise_to"):
            bounds = spec.args.get("amount") if isinstance(spec.args, dict) else None
            if (not isinstance(bounds, dict)
                    or "min" not in bounds or "max" not in bounds):
                raise ValueError(
                    f"legal action spec for {spec.name!r} missing amount "
                    f"bounds: spec.args={spec.args!r}. This is an engine bug "
                    f"in compute_legal_tool_set; do not paper over with "
                    f"default bounds."
                )
            mn, mx = int(bounds["min"]), int(bounds["max"])
            schema: dict[str, Any] = {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "integer", "minimum": mn, "maximum": mx,
                    },
                },
                "required": ["amount"],
                "additionalProperties": False,
            }
            description = (
                f"{spec.name.replace('_', ' ').capitalize()}: "
                f"amount in [{mn}, {mx}]"
            )
        else:
            schema = {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            }
            description = spec.name.capitalize()
        out.append({
            "name": spec.name,
            "description": description,
            "input_schema": schema,
        })
    return out


def _user_prompt_for(view: PlayerView) -> str:
    """Phase 3a hardcoded prompt; 3d swaps in Jinja templates per spec §6."""
    return (
        f"{_SYSTEM_PROMPT}\n\n"
        f"=== STATE ===\n"
        f"hand_id: {view.hand_id}\n"
        f"street: {view.street.value}\n"
        f"my_seat: {view.my_seat}\n"
        f"my_hole_cards: {' '.join(view.my_hole_cards)}\n"
        f"community: {' '.join(view.community) or '(none)'}\n"
        f"pot: {view.pot}\n"
        f"my_stack: {view.my_stack}\n"
        f"to_call: {view.to_call}\n"
        f"pot_odds_required: {view.pot_odds_required}\n"
        f"effective_stack: {view.effective_stack}\n"
        f"button_seat: {view.button_seat}\n"
        f"opponents_in_hand: {list(view.opponent_seats_in_hand)}\n"
        f"seats_yet_to_act_after_me: {list(view.seats_yet_to_act_after_me)}\n"
        f"\nLegal action tools available below. "
        f"Briefly explain your reasoning, then call exactly one tool."
    )


def _assistant_message(response: LLMResponse) -> dict[str, Any]:
    """Re-serialize provider response as Anthropic-shape assistant message."""
    blocks = list(response.raw_assistant_turn.blocks)
    if not blocks:
        # No raw blocks captured (e.g. MockLLMProvider) — synthesize from
        # text + tool_calls so the message is well-formed.
        synth: list[dict[str, Any]] = []
        if response.text_content:
            synth.append({"type": "text", "text": response.text_content})
        for tc in response.tool_calls:
            synth.append({
                "type": "tool_use",
                "id": tc.tool_use_id,
                "name": tc.name,
                "input": tc.args,
            })
        if not synth:
            synth.append({"type": "text", "text": ""})
        blocks = synth
    return {"role": "assistant", "content": blocks}


def _user_text(text: str) -> dict[str, Any]:
    """Plain text user message — only safe when previous assistant turn had
    NO tool_use block. Anthropic API rejects plain-text after tool_use; use
    _tool_result_user instead in that case."""
    return {"role": "user", "content": text}


def _tool_result_user(
    *, tool_use_id: str, is_error: bool, content: str,
) -> dict[str, Any]:
    """Anthropic-compliant tool_result block, MUST follow any assistant turn
    that contained a tool_use block (matching by tool_use_id)."""
    return {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "is_error": is_error,
            "content": content,
        }],
    }


__all__ = ["LLMAgent"]

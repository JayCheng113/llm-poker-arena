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
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.provider_base import (
    LLMProvider,
    ProviderPermanentError,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.redaction import redact_secret
from llm_poker_arena.tools import run_utility_tool as _default_tool_runner

if TYPE_CHECKING:
    from llm_poker_arena.agents.llm.prompt_profile import PromptProfile
from llm_poker_arena.agents.llm.types import (
    ApiErrorInfo,
    IterationRecord,
    ReasoningArtifact,
    ReasoningArtifactKind,
    TokenCounts,
    TurnDecisionResult,
)
from llm_poker_arena.engine.legal_actions import (
    Action,
    default_safe_action,
    validate_action,
)
from llm_poker_arena.engine.views import PlayerView


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
        version: str = "phase3d",
        prompt_profile: PromptProfile | None = None,
        tool_runner: Callable[[Any, str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._temperature = temperature
        self._seed = seed
        self._per_iter_timeout = per_iteration_timeout_sec
        self._total_turn_timeout = total_turn_timeout_sec
        self._version = version
        if prompt_profile is None:
            from llm_poker_arena.agents.llm.prompt_profile import (
                load_default_prompt_profile,
            )

            prompt_profile = load_default_prompt_profile()
        self._prompt_profile = prompt_profile
        self._tool_runner = tool_runner if tool_runner is not None else _default_tool_runner

    def provider_id(self) -> str:
        return f"{self._provider.provider_name()}:{self._model}"

    def metadata(self) -> dict[str, Any] | None:
        """spec §7.4: surface temperature + seed for snapshot persistence."""
        return {"temperature": self._temperature, "seed": self._seed}

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
                api_retry_count=0,
                illegal_action_retry_count=0,
                no_tool_retry_count=0,
                tool_usage_error_count=0,
                default_action_fallback=False,
                api_error=ApiErrorInfo(
                    type="TotalTurnTimeout",
                    detail=f"exceeded {self._total_turn_timeout}s",
                ),
                turn_timeout_exceeded=True,
            )

    async def _decide_inner(self, view: PlayerView) -> TurnDecisionResult:
        from llm_poker_arena.tools import ToolDispatchError, utility_tool_specs

        MAX_API_RETRY = 1
        MAX_ILLEGAL_RETRY = 1
        MAX_NO_TOOL_RETRY = 1
        MAX_TOOL_USAGE_RETRY = 1  # spec §4.1 BR2-05: independent budget
        # spec §4.2 K+1 ReAct: bound = max_utility_calls + 4 retry slots + 1
        # commit slot. Default max_utility_calls=5 → MAX_STEPS=10. When
        # enable_math_tools=False, utility_specs is empty and utility_count
        # stays 0 → behavior identical to Phase 3a/3b K=0.
        max_utility_calls = view.immutable_session_params.max_utility_calls
        MAX_STEPS = max_utility_calls + 5

        api_retry = 0
        illegal_retry = 0
        no_tool_retry = 0
        tool_usage_retry = 0  # phase 3d: separate from tool_usage_error_count
        tool_usage_error_count = 0
        utility_count = 0  # successful + failed utility attempts (spec §4.2 line 1017)

        iterations: list[IterationRecord] = []
        system_text, messages = self._build_initial_state(view)
        action_tools = _action_tool_specs(view)
        utility_specs = utility_tool_specs(view)
        all_tools = action_tools + utility_specs
        # Codex audit IMPORTANT-1: only dispatch as utility when name matches a
        # CURRENTLY-REGISTERED utility tool. Empty when enable_math_tools=False.
        utility_names = {s["name"] for s in utility_specs}
        turn_start = time.monotonic()
        total_tokens = TokenCounts.zero()

        for step in range(MAX_STEPS):
            digest = _digest_messages(messages)
            iter_start = time.monotonic()
            # spec §4.2 is_final_step: pass action-only tools when utility
            # budget is exhausted OR this is the last allowed step. This
            # denies the model the option to call more utilities — forces
            # commit pressure.
            is_final_step = utility_count >= max_utility_calls or step == MAX_STEPS - 1
            tools_this_step = action_tools if is_final_step else all_tools
            try:
                response = await asyncio.wait_for(
                    self._provider.complete(
                        system=system_text,
                        messages=messages,
                        tools=tools_this_step,
                        temperature=self._temperature,
                        seed=self._seed,
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
                    text_content=redact_secret(str(e)),
                    tokens=TokenCounts.zero(),
                    wall_time_ms=int((time.monotonic() - iter_start) * 1000),
                )
                iterations.append(iter_record)
                if api_retry < MAX_API_RETRY:
                    api_retry += 1
                    await asyncio.sleep(0.5 + random.random() * 0.5)
                    continue
                return self._fail_with_api_error(
                    iterations,
                    total_tokens,
                    turn_start,
                    api_retry,
                    illegal_retry,
                    no_tool_retry,
                    err_type=err_type,
                    detail=str(e),
                    tool_usage_error_count=tool_usage_error_count,
                )
            except ProviderPermanentError as e:
                iter_record = IterationRecord(
                    step=step + 1,
                    request_messages_digest=digest,
                    provider_response_kind="error",
                    tool_call=None,
                    text_content=redact_secret(str(e)),
                    tokens=TokenCounts.zero(),
                    wall_time_ms=int((time.monotonic() - iter_start) * 1000),
                )
                iterations.append(iter_record)
                return self._fail_with_api_error(
                    iterations,
                    total_tokens,
                    turn_start,
                    api_retry,
                    illegal_retry,
                    no_tool_retry,
                    err_type="ProviderPermanentError",
                    detail=str(e),
                    tool_usage_error_count=tool_usage_error_count,
                )

            iter_ms = int((time.monotonic() - iter_start) * 1000)
            total_tokens = total_tokens + response.tokens
            artifacts = self._provider.extract_reasoning_artifact(response)

            if not response.tool_calls:
                iter_record = IterationRecord(
                    step=step + 1,
                    request_messages_digest=digest,
                    provider_response_kind="no_tool",
                    tool_call=None,
                    text_content=redact_secret(response.text_content),
                    tokens=response.tokens,
                    wall_time_ms=iter_ms,
                    reasoning_artifacts=artifacts,
                )
                iterations.append(iter_record)
                if no_tool_retry < MAX_NO_TOOL_RETRY:
                    no_tool_retry += 1
                    messages.append(self._provider.build_assistant_message_for_replay(response))
                    messages.append(
                        self._provider.build_user_text_message(
                            "You must call exactly one action tool. Try again."
                        )
                    )
                    continue
                return self._fallback_default_safe(
                    view,
                    iterations,
                    total_tokens,
                    turn_start,
                    api_retry,
                    illegal_retry,
                    no_tool_retry,
                    tool_usage_error_count=tool_usage_error_count,
                )

            # Multi-tool-call response is misuse: count + retry on dedicated
            # tool_usage_retry slot (spec §4.1 BR2-05: 4 independent budgets).
            if len(response.tool_calls) > 1:
                tool_usage_error_count += 1
                first_tc = response.tool_calls[0]
                iter_record = IterationRecord(
                    step=step + 1,
                    request_messages_digest=digest,
                    provider_response_kind="tool_use",
                    tool_call=first_tc,
                    text_content=redact_secret(response.text_content),
                    tokens=response.tokens,
                    wall_time_ms=iter_ms,
                    reasoning_artifacts=artifacts,
                )
                iterations.append(iter_record)
                if tool_usage_retry < MAX_TOOL_USAGE_RETRY:
                    tool_usage_retry += 1
                    messages.append(self._provider.build_assistant_message_for_replay(response))
                    # Provider-specific tool_result protocol (Anthropic: 1
                    # user message with N tool_result blocks; OpenAI: N
                    # role:tool messages). build_tool_result_messages hides
                    # the difference; LLMAgent always extends.
                    err_content = (
                        f"Multiple tool calls in one response are not "
                        f"allowed. Got {len(response.tool_calls)} calls; "
                        f"call exactly one action tool."
                    )
                    messages.extend(
                        self._provider.build_tool_result_messages(
                            tool_calls=response.tool_calls,
                            is_error=True,
                            content=err_content,
                        )
                    )
                    continue
                return self._fallback_default_safe(
                    view,
                    iterations,
                    total_tokens,
                    turn_start,
                    api_retry,
                    illegal_retry,
                    no_tool_retry,
                    tool_usage_error_count=tool_usage_error_count,
                )

            tc_first = response.tool_calls[0]

            # Phase 3c-math: utility-tool dispatch branch. Fires BEFORE the
            # rationale_required check — utility tool calls themselves are a
            # form of structured reasoning, so they're exempt from the
            # text-rationale requirement (see plan §"Spec Inconsistencies" #3).
            # Only matches names registered in utility_names — unknown names
            # (model hallucinated) fall through to the action-tool branch and
            # consume illegal_action_retry per spec §4.2 line 1027.
            if tc_first.name in utility_names:
                if is_final_step:
                    # Spec §4.2 lines 994-1015: LLM defied the action-only
                    # tool list (we passed action_tools only). Treat as
                    # no_tool: didn't follow protocol. Consume no_tool_retry
                    # budget; on exhaustion fall back to default_safe_action.
                    iter_record = IterationRecord(
                        step=step + 1,
                        request_messages_digest=digest,
                        provider_response_kind="no_tool",
                        tool_call=tc_first,
                        text_content=redact_secret(response.text_content),
                        tokens=response.tokens,
                        wall_time_ms=iter_ms,
                        reasoning_artifacts=artifacts,
                    )
                    iterations.append(iter_record)
                    if no_tool_retry < MAX_NO_TOOL_RETRY:
                        no_tool_retry += 1
                        messages.append(self._provider.build_assistant_message_for_replay(response))
                        messages.extend(
                            self._provider.build_tool_result_messages(
                                tool_calls=(tc_first,),
                                is_error=True,
                                content=(
                                    "You have exhausted your utility-tool budget. "
                                    "Call exactly one action tool now."
                                ),
                            )
                        )
                        continue
                    return self._fallback_default_safe(
                        view,
                        iterations,
                        total_tokens,
                        turn_start,
                        api_retry,
                        illegal_retry,
                        no_tool_retry,
                        tool_usage_error_count=tool_usage_error_count,
                    )

                try:
                    tool_result = self._tool_runner(
                        view,
                        tc_first.name,
                        dict(tc_first.args or {}),
                    )
                except ToolDispatchError as e:
                    tool_result = {"error": str(e)}
                    tool_usage_error_count += 1

                iter_record = IterationRecord(
                    step=step + 1,
                    request_messages_digest=digest,
                    provider_response_kind="tool_use",
                    tool_call=tc_first,
                    text_content=redact_secret(response.text_content),
                    tokens=response.tokens,
                    wall_time_ms=iter_ms,
                    reasoning_artifacts=artifacts,
                    tool_result=tool_result,
                )
                iterations.append(iter_record)
                # spec §4.2 line 1017: utility_count increments on ATTEMPT,
                # not just success. Otherwise a buggy/malicious LLM emitting
                # bad args 5x would never hit the budget cap and would chew
                # through MAX_STEPS instead.
                utility_count += 1

                # Feed tool result back to the model and continue the loop.
                messages.append(self._provider.build_assistant_message_for_replay(response))
                messages.extend(
                    self._provider.build_tool_result_messages(
                        tool_calls=(tc_first,),
                        is_error="error" in tool_result,
                        content=json.dumps(tool_result),
                    )
                )
                continue

            # Phase 3d: rationale_required strict mode (spec §4.5).
            # When the profile demands reasoning, an empty text_content with
            # a tool_use block is treated as "no rationale" — same family of
            # error as no_tool, consume the no_tool_retry budget.
            # Phase 3b (codex BLOCKER fix): reasoning artifacts can also
            # carry the rationale (e.g. DeepSeek-R1's reasoning_content,
            # Anthropic thinking blocks); accept those too. But ENCRYPTED /
            # REDACTED artifacts are opaque and MUST NOT count.
            if (
                self._prompt_profile.rationale_required
                and not response.text_content.strip()
                and not _has_text_rationale_artifact(artifacts)
            ):
                tc = response.tool_calls[0]
                iter_record = IterationRecord(
                    step=step + 1,
                    request_messages_digest=digest,
                    provider_response_kind="no_tool",
                    tool_call=tc,
                    text_content="",
                    tokens=response.tokens,
                    wall_time_ms=iter_ms,
                    reasoning_artifacts=artifacts,
                )
                iterations.append(iter_record)
                if no_tool_retry < MAX_NO_TOOL_RETRY:
                    no_tool_retry += 1
                    messages.append(self._provider.build_assistant_message_for_replay(response))
                    messages.extend(
                        self._provider.build_tool_result_messages(
                            tool_calls=(tc,),
                            is_error=True,
                            content=(
                                "Reasoning required: write 1-3 short paragraphs "
                                "of reasoning before calling the tool. Try again."
                            ),
                        )
                    )
                    continue
                return self._fallback_default_safe(
                    view,
                    iterations,
                    total_tokens,
                    turn_start,
                    api_retry,
                    illegal_retry,
                    no_tool_retry,
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
                text_content=redact_secret(response.text_content),
                tokens=response.tokens,
                wall_time_ms=iter_ms,
                reasoning_artifacts=artifacts,
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
                messages.append(self._provider.build_assistant_message_for_replay(response))
                messages.extend(
                    self._provider.build_tool_result_messages(
                        tool_calls=(tc,),
                        is_error=True,
                        content=(
                            f"Illegal action: {v.reason}. Legal action tools: "
                            f"{[t.name for t in view.legal_actions.tools]}. "
                            f"Call exactly one of those next."
                        ),
                    )
                )
                continue

            return self._fallback_default_safe(
                view,
                iterations,
                total_tokens,
                turn_start,
                api_retry,
                illegal_retry,
                no_tool_retry,
                tool_usage_error_count=tool_usage_error_count,
            )

        return self._fallback_default_safe(
            view,
            iterations,
            total_tokens,
            turn_start,
            api_retry,
            illegal_retry,
            no_tool_retry,
            tool_usage_error_count=tool_usage_error_count,
        )

    def _build_initial_state(
        self,
        view: PlayerView,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Returns (system_prompt, initial_messages). The system prompt is
        passed via LLMProvider.complete(system=...) so Anthropic prompt
        caching can take effect."""
        params = view.immutable_session_params
        system_text = self._prompt_profile.render_system(
            num_players=params.num_players,
            sb=params.sb,
            bb=params.bb,
            starting_stack=params.starting_stack,
            enable_math_tools=params.enable_math_tools,
            max_utility_calls=params.max_utility_calls,
        )
        my_seat_info = view.seats_public[view.my_seat]
        user_text = self._prompt_profile.render_user(
            hand_id=view.hand_id,
            street=view.street.value,
            my_seat=view.my_seat,
            my_position_short=my_seat_info.position_short,
            my_position_full=my_seat_info.position_full,
            my_hole_cards=view.my_hole_cards,
            community=view.community,
            pot=view.pot,
            my_stack=view.my_stack,
            to_call=view.to_call,
            pot_odds_required=view.pot_odds_required,
            effective_stack=view.effective_stack,
            button_seat=view.button_seat,
            opponent_seats_in_hand=view.opponent_seats_in_hand,
            seats_yet_to_act_after_me=view.seats_yet_to_act_after_me,
            seats_public=view.seats_public,
        )
        return system_text, [{"role": "user", "content": user_text}]

    def _fail_with_api_error(
        self,
        iterations: list[IterationRecord],
        total_tokens: TokenCounts,
        turn_start: float,
        api_retry: int,
        illegal_retry: int,
        no_tool_retry: int,
        *,
        err_type: str,
        detail: str,
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
            api_error=ApiErrorInfo(type=err_type, detail=redact_secret(detail)),
            turn_timeout_exceeded=False,
        )

    def _fallback_default_safe(
        self,
        view: PlayerView,
        iterations: list[IterationRecord],
        total_tokens: TokenCounts,
        turn_start: float,
        api_retry: int,
        illegal_retry: int,
        no_tool_retry: int,
        *,
        tool_usage_error_count: int = 0,
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


def _has_text_rationale_artifact(
    artifacts: tuple[ReasoningArtifact, ...],
) -> bool:
    """True iff at least one artifact carries human-readable rationale text.
    Used by rationale_required strict mode.

    spec §4.6 contract: only RAW (DeepSeek-Reasoner reasoning_content),
    SUMMARY (OpenAI o-series summary), and THINKING_BLOCK (Anthropic
    extended thinking plaintext) carry plaintext rationale. ENCRYPTED
    payloads are opaque base64 — accepting them as rationale would
    silently let the model bypass the rationale requirement by emitting
    encrypted blocks alone. REDACTED has content=None by construction.
    UNAVAILABLE means the provider didn't surface any reasoning at all.
    """
    rationale_kinds = {
        ReasoningArtifactKind.RAW,
        ReasoningArtifactKind.SUMMARY,
        ReasoningArtifactKind.THINKING_BLOCK,
    }
    return any(a.kind in rationale_kinds and a.content and a.content.strip() for a in artifacts)


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
            if not isinstance(bounds, dict) or "min" not in bounds or "max" not in bounds:
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
                        "type": "integer",
                        "minimum": mn,
                        "maximum": mx,
                    },
                },
                "required": ["amount"],
                "additionalProperties": False,
            }
            description = f"{spec.name.replace('_', ' ').capitalize()}: amount in [{mn}, {mx}]"
        else:
            schema = {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            }
            description = spec.name.capitalize()
        out.append(
            {
                "name": spec.name,
                "description": description,
                "input_schema": schema,
            }
        )
    return out


__all__ = ["LLMAgent"]

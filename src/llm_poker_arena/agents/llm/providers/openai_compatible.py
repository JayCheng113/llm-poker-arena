"""OpenAICompatibleProvider — Chat Completions adapter for OpenAI canonical API
and any OpenAI-compatible endpoint (DeepSeek at base_url=https://api.deepseek.com/v1).

spec §4.4 / §4.6 / §11.2:
  - Tool calls returned as `assistant.tool_calls[*]` with JSON-string arguments.
  - Tool result messages are `role: tool, tool_call_id: ..., content: ...` —
    one per call (not bundled into a single user message like Anthropic).
  - DeepSeek-Reasoner returns `message.reasoning_content` (plaintext CoT) —
    surfaced as ReasoningArtifact(kind=RAW). DeepSeek-Chat / OpenAI Chat:
    no reasoning artifact (empty tuple).
  - `seed` is best-effort. Probe tries seed=42; if the provider rejects it
    with a "unknown/unsupported parameter" 400-class error, we set
    `_seed_known_unsupported=True` so subsequent `complete()` calls drop
    seed automatically (avoids burning real tokens just to re-discover the
    same rejection on every turn).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, cast

from openai import (
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
    RateLimitError,
)

from llm_poker_arena.agents.llm.provider_base import (
    LLMProvider,
    ProviderPermanentError,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    ObservedCapability,
    ReasoningArtifact,
    ReasoningArtifactKind,
    TokenCounts,
    ToolCall,
)


def _max_tokens_kwarg(model: str, value: int) -> dict[str, int]:
    """gpt-5.x and o-series require 'max_completion_tokens' instead of
    'max_tokens'. Other OpenAI-compatible providers (DeepSeek, Qwen,
    older OpenAI) still use 'max_tokens'."""
    if model.startswith("gpt-5") or model.startswith("o1") or model.startswith("o3"):
        return {"max_completion_tokens": value}
    return {"max_tokens": value}


# OpenAI's reasoning-model lines (GPT-5.x, o-series, future gpt-6.x) hide
# their chain-of-thought behind the Responses API: Chat Completions only
# returns `usage.completion_tokens_details.reasoning_tokens` (an int), so a
# UI panel built around those models looks silent. The Responses API
# exposes a user-facing `summary` per turn, which is what we want to feed
# into the reasoning panel.
#
# Other OpenAI-compatible providers (DeepSeek, Kimi, Qwen, Grok, Gemini)
# do NOT implement the Responses API — they stay on Chat Completions and
# surface their own thinking via `reasoning_content` (DeepSeek/Kimi) or
# nothing at all (Qwen/Grok/Gemini). So this routing only flips for the
# `openai` provider tag + a reasoning-model prefix.
_OPENAI_REASONING_MODEL_PREFIXES = ("gpt-5", "gpt-6", "o1", "o3", "o4")


def _is_openai_reasoning_model(provider_name: str, model: str) -> bool:
    return provider_name == "openai" and any(
        model.startswith(p) for p in _OPENAI_REASONING_MODEL_PREFIXES
    )


# Gemini's OpenAI-compat shim, when called with
# `extra_body.google.thinking_config.include_thoughts=True`, returns the
# model's reasoning summary INLINE in `content` wrapped in literal
# `<thought>...</thought>` tags. We split those out so:
#   - the visible decision text is clean (no leaking tags),
#   - the thinking summary lands as a SUMMARY reasoning artifact for
#     the UI panel.
#
# Multiple thought blocks are concatenated with a blank line. Missing
# closing tag → no extraction (the input is returned untouched and the
# whole content stays as the visible message — graceful failure).
_THOUGHT_BLOCK_RE = re.compile(r"<thought>(.*?)</thought>", re.DOTALL)


def _split_gemini_thought(content: str) -> tuple[str, str]:
    """Return (visible_content_without_thought, joined_thought_text).

    Both strings are stripped of leading/trailing whitespace so the UI
    doesn't render gratuitous newlines around the panel boxes."""
    if not content or "<thought>" not in content:
        return content, ""
    thoughts = _THOUGHT_BLOCK_RE.findall(content)
    if not thoughts:
        return content, ""
    visible = _THOUGHT_BLOCK_RE.sub("", content).strip()
    summary = "\n\n".join(t.strip() for t in thoughts if t.strip())
    return visible, summary


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        provider_name_value: str,
        model: str,
        api_key: str,
        base_url: str | None = None,
        max_tokens: int = 1024,
        sdk_max_retries: int | None = None,
        enable_thinking_summary: bool = False,
        reasoning_effort: str = "low",
    ) -> None:
        self._provider_name = provider_name_value
        self._model = model
        self._max_tokens = max_tokens
        # AsyncOpenAI accepts base_url=None (= OpenAI canonical endpoint).
        # sdk_max_retries=None lets the SDK use its default (2). Caller
        # bumps it for endpoints with known capacity issues — Gemini AI
        # Studio's 503 spikes are the canonical case, see registry.py
        # `gemini` entry. The SDK does its own exponential backoff on
        # 5xx, so a single LLMAgent api_retry can absorb a multi-second
        # spike instead of immediately censoring the hand.
        client_kwargs: dict[str, Any] = {"api_key": api_key, "base_url": base_url}
        if sdk_max_retries is not None:
            client_kwargs["max_retries"] = sdk_max_retries
        self._client = AsyncOpenAI(**client_kwargs)
        # spec §11.2: probe will set this to True if seed is rejected so
        # that complete() drops seed on subsequent calls. Defaults to None
        # (unknown until probe runs); complete() treats None as "try seed".
        self._seed_known_unsupported: bool | None = None
        # When True, complete() injects Gemini's `extra_body.google.
        # thinking_config.include_thoughts=True` and _normalize() splits
        # the resulting <thought>...</thought> block out of `content` into
        # a SUMMARY-kind reasoning artifact. Only Gemini supports this
        # surface today; verified 2026-04-27.
        self._enable_thinking_summary = enable_thinking_summary
        # OpenAI Responses API `reasoning.effort` knob — low/medium/high.
        # Default "low" is cost-conscious for non-flagship reasoning
        # models; flagships are bumped to "medium" or "high" via
        # MODEL_OVERRIDES (see registry.py). Higher = more reasoning
        # tokens billed at output rate, deeper chain-of-thought
        # captured in the SUMMARY artifact.
        if reasoning_effort not in ("low", "medium", "high"):
            raise ValueError(
                f"reasoning_effort must be low/medium/high, got {reasoning_effort!r}"
            )
        self._reasoning_effort = reasoning_effort

    def provider_name(self) -> str:
        return self._provider_name

    async def complete(
        self,
        *,
        system: str | None = None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        # Fork: OpenAI reasoning models go through the Responses API so we
        # can pull a user-visible reasoning summary (Chat Completions only
        # returns reasoning token COUNTS, not text). Non-reasoning OpenAI
        # models and every other OpenAI-compat provider stay on Chat.
        if _is_openai_reasoning_model(self._provider_name, self._model):
            return await self._complete_via_responses(
                system=system,
                messages=messages,
                tools=tools,
                temperature=temperature,
                seed=seed,
            )

        # Convert our portable Anthropic-style tool spec to OpenAI tool spec.
        # Our spec: {"name": ..., "description": ..., "input_schema": {...}}
        # OpenAI:  {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
        oai_tools: list[dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]

        # Inject the system prompt as a leading system-role message; OpenAI
        # has no separate `system=` kwarg on Chat Completions.
        oai_msgs: list[dict[str, Any]] = []
        if system is not None:
            oai_msgs.append({"role": "system", "content": system})
        oai_msgs.extend(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            **_max_tokens_kwarg(self._model, self._max_tokens),
            "temperature": temperature,
            "messages": cast("Any", oai_msgs),
        }
        if oai_tools:
            kwargs["tools"] = cast("Any", oai_tools)
        # spec §11.2: only attach seed if probe didn't already learn the
        # provider rejects it. Saves a round-trip on every turn for
        # providers known not to accept seed.
        if seed is not None and self._seed_known_unsupported is not True:
            kwargs["seed"] = seed
        # Gemini-specific: ask the OpenAI-compat shim to surface internal
        # thinking. Response will inline a <thought>...</thought> block
        # at the start of `content`; _normalize() will split it out.
        #
        # Wire-format quirk: Gemini wants the request body to literally
        # have a top-level `extra_body` JSON key wrapping the `google`
        # config — but the OpenAI Python SDK's own `extra_body=` kwarg
        # SPREADS its dict to the top level of the body (so a naive
        # `{"google": ...}` ends up as `body.google`, which Gemini
        # rejects with `Unknown name "google"`). Double-wrap so SDK's
        # spread leaves a literal `extra_body` field intact. Verified
        # 2026-04-27 by sniffing the raw httpx request.
        if self._enable_thinking_summary:
            kwargs["extra_body"] = {
                "extra_body": {
                    "google": {"thinking_config": {"include_thoughts": True}}
                }
            }

        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except (APITimeoutError, RateLimitError) as e:
            raise ProviderTransientError(str(e)) from e
        except BadRequestError as e:
            # 400-class. If the message implicates the seed parameter and
            # we did pass seed, retry once without it AND latch
            # `_seed_known_unsupported=True` so future turns skip seed.
            if "seed" in kwargs and _looks_like_seed_unsupported(e):
                self._seed_known_unsupported = True
                kwargs.pop("seed", None)
                try:
                    resp = await self._client.chat.completions.create(**kwargs)
                except (APITimeoutError, RateLimitError) as e2:
                    raise ProviderTransientError(str(e2)) from e2
                except APIStatusError as e2:
                    status = getattr(getattr(e2, "response", None), "status_code", None)
                    if status is not None and status >= 500:
                        raise ProviderTransientError(f"{status}: {e2}") from e2
                    if status == 429:
                        raise ProviderTransientError(f"429 rate limited: {e2}") from e2
                    raise ProviderPermanentError(f"{status}: {e2}") from e2
            else:
                raise ProviderPermanentError(f"400: {e}") from e
        except APIStatusError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and status >= 500:
                raise ProviderTransientError(f"{status}: {e}") from e
            if status == 429:
                raise ProviderTransientError(f"429 rate limited: {e}") from e
            raise ProviderPermanentError(f"{status}: {e}") from e

        return self._normalize(resp)

    def _normalize(self, resp: Any) -> LLMResponse:  # noqa: ANN401
        choice = resp.choices[0]
        msg = choice.message
        finish = getattr(choice, "finish_reason", "stop")
        # Map OpenAI finish_reason → our stop_reason vocabulary.
        if finish == "stop":
            stop_reason = "end_turn"
        elif finish == "tool_calls":
            stop_reason = "tool_use"
        elif finish == "length":
            stop_reason = "max_tokens"
        elif finish == "stop_sequence":
            stop_reason = "stop_sequence"
        else:
            stop_reason = "other"

        tool_calls: list[ToolCall] = []
        for tc in getattr(msg, "tool_calls", None) or []:
            args_str = tc.function.arguments or ""
            try:
                args_dict = json.loads(args_str) if args_str else {}
                if not isinstance(args_dict, dict):
                    args_dict = {}
            except json.JSONDecodeError:
                # Malformed JSON: surface to LLMAgent as empty args. The
                # action validator will reject it as illegal → triggers
                # illegal_action_retry. Better than crashing the agent.
                args_dict = {}
            tool_calls.append(
                ToolCall(
                    name=tc.function.name,
                    args=args_dict,
                    tool_use_id=tc.id,
                )
            )

        text_content = msg.content or ""
        usage = getattr(resp, "usage", None)
        tokens = TokenCounts(
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        # Preserve the raw assistant message dict for replay. The dict carries
        # `reasoning_content` for DeepSeek-Reasoner so extract_reasoning_artifact
        # can find it. For OpenAI the field is simply absent.
        raw_msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else dict(msg)

        # Gemini-only: split <thought>...</thought> out of content. The
        # extracted summary lands under reasoning_content so the
        # downstream artifact-extractor (and replay-stripper) treat it
        # the same as DeepSeek/Kimi reasoning_content. The visible
        # text_content is the remainder; raw_msg_dict["content"] gets
        # the same remainder so replay round trips do NOT carry the
        # <thought> tags back to Gemini.
        if self._enable_thinking_summary and text_content:
            visible, summary = _split_gemini_thought(text_content)
            if summary:
                text_content = visible
                raw_msg_dict["content"] = visible or None
                raw_msg_dict["reasoning_content"] = summary

        return LLMResponse(
            provider=self._provider_name,
            model=resp.model,
            stop_reason=cast("Any", stop_reason),
            tool_calls=tuple(tool_calls),
            text_content=text_content,
            tokens=tokens,
            raw_assistant_turn=AssistantTurn(
                provider=self._provider_name,
                blocks=(raw_msg_dict,),
            ),
        )

    # ------------------------------------------------------------------
    # Responses API path (OpenAI reasoning models only)
    # ------------------------------------------------------------------

    async def _complete_via_responses(
        self,
        *,
        system: str | None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        """OpenAI reasoning-model path. Builds the Responses API request,
        parses the typed `output[]` array (message + function_call +
        reasoning items), and returns an `LLMResponse` whose
        `raw_assistant_turn.blocks[0]` is a Chat-style assistant dict so
        the existing replay / extract pipeline keeps working downstream.
        The reasoning summary is embedded under
        `blocks[0]["reasoning_summary"]` for `extract_reasoning_artifact`
        to pick up."""
        # Tool spec: Responses uses a flat shape (no "function" nesting).
        responses_tools: list[dict[str, Any]] = [
            {
                "type": "function",
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]

        # Convert the Chat-style message list into Responses input items.
        input_items = self._messages_to_responses_input(system, messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": cast("Any", input_items),
            # Responses API: "summary" key requests a user-visible summary
            # of the model's reasoning. "auto" lets the API pick concise
            # vs detailed; effort "low" matches our token budget profile
            # (we want fast turns, not deep reasoning).
            "reasoning": {"effort": self._reasoning_effort, "summary": "auto"},
        }
        if responses_tools:
            kwargs["tools"] = cast("Any", responses_tools)
        # max_output_tokens is the Responses API equivalent of
        # max_completion_tokens; bump higher than Chat's default because
        # reasoning eats from the same budget.
        kwargs["max_output_tokens"] = max(self._max_tokens, 2048)
        # Reasoning models reject `temperature` outright (only the default
        # is accepted) — don't pass it. Same for `seed` on the Responses
        # API: it isn't a documented parameter. Both args are accepted
        # by the signature for API symmetry with the Chat path but go
        # unused here.
        del temperature, seed

        try:
            resp = await self._client.responses.create(**kwargs)
        except (APITimeoutError, RateLimitError) as e:
            raise ProviderTransientError(str(e)) from e
        except BadRequestError as e:
            raise ProviderPermanentError(f"400: {e}") from e
        except APIStatusError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and status >= 500:
                raise ProviderTransientError(f"{status}: {e}") from e
            if status == 429:
                raise ProviderTransientError(f"429 rate limited: {e}") from e
            raise ProviderPermanentError(f"{status}: {e}") from e

        return self._normalize_responses(resp)

    @staticmethod
    def _messages_to_responses_input(
        system: str | None,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Translate the LLMAgent's Chat-format conversation history into
        Responses-format input items. Roles map: system→developer (the
        Responses API renamed it), user/assistant→message; assistant
        tool_calls become standalone function_call items; tool messages
        become function_call_output items keyed by call_id.

        Pure function so unit tests can exercise it without an SDK round
        trip."""
        items: list[dict[str, Any]] = []
        if system is not None:
            items.append({
                "type": "message",
                "role": "developer",
                "content": system,
            })
        for m in messages:
            role = m.get("role")
            if role in ("user", "system"):
                # Defensive: a stray system message in `messages` (rare —
                # we only ever set system via the kwarg) gets the same
                # developer downgrade so the Responses API accepts it.
                mapped_role = "developer" if role == "system" else "user"
                items.append({
                    "type": "message",
                    "role": mapped_role,
                    "content": m.get("content") or "",
                })
            elif role == "assistant":
                content = m.get("content")
                tool_calls = m.get("tool_calls") or []
                if content:
                    items.append({
                        "type": "message",
                        "role": "assistant",
                        "content": content,
                    })
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    items.append({
                        "type": "function_call",
                        "call_id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "arguments": fn.get("arguments", "{}"),
                    })
            elif role == "tool":
                items.append({
                    "type": "function_call_output",
                    "call_id": m.get("tool_call_id", ""),
                    "output": m.get("content") or "",
                })
            # Anything else is silently dropped — there's no fifth role
            # in our message vocab.
        return items

    def _normalize_responses(self, resp: Any) -> LLMResponse:  # noqa: ANN401
        """Parse a Responses API response into our LLMResponse dataclass.

        `resp.output` is a list of items: ResponseReasoningItem,
        ResponseOutputMessage, ResponseFunctionToolCall (in arbitrary
        order). We collect:
          - text: from message items' `content[].text` (only output_text
            content blocks count)
          - tool calls: from function_call items
          - reasoning summary: concatenated `summary[].text` strings
        """
        output_items = getattr(resp, "output", None) or []
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        reasoning_summary_parts: list[str] = []
        sample_finish: str | None = None

        for item in output_items:
            item_type = getattr(item, "type", None)
            if item_type == "message":
                for content_block in getattr(item, "content", None) or []:
                    cb_type = getattr(content_block, "type", None)
                    if cb_type == "output_text":
                        text_parts.append(getattr(content_block, "text", "") or "")
            elif item_type == "function_call":
                args_str = getattr(item, "arguments", "") or ""
                try:
                    args_dict = json.loads(args_str) if args_str else {}
                    if not isinstance(args_dict, dict):
                        args_dict = {}
                except json.JSONDecodeError:
                    # Same fallback as the Chat path: malformed JSON →
                    # empty args, illegal_action_retry kicks in.
                    args_dict = {}
                tool_calls.append(
                    ToolCall(
                        name=getattr(item, "name", ""),
                        args=args_dict,
                        # Responses uses `call_id` as the public id;
                        # store under `tool_use_id` to match our shape.
                        tool_use_id=getattr(item, "call_id", "")
                        or getattr(item, "id", ""),
                    )
                )
            elif item_type == "reasoning":
                for summary_block in getattr(item, "summary", None) or []:
                    txt = getattr(summary_block, "text", "")
                    if txt:
                        reasoning_summary_parts.append(txt)
            sample_finish = getattr(item, "status", sample_finish)

        # Map Responses API status → our stop_reason vocab. The Responses
        # API doesn't have a per-response finish_reason; use status of
        # the last item as a proxy. Most successful turns end with
        # status=="completed"; `incomplete` we map to max_tokens.
        if tool_calls:
            stop_reason = "tool_use"
        elif sample_finish == "incomplete":
            stop_reason = "max_tokens"
        else:
            stop_reason = "end_turn"

        usage = getattr(resp, "usage", None)
        # Responses uses `input_tokens`/`output_tokens` (not the
        # Chat-style `prompt_tokens`/`completion_tokens`).
        tokens = TokenCounts(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        # Build a Chat-shaped raw block so downstream replay/extract code
        # paths don't have to know we used Responses. The reasoning
        # summary lives under a non-OpenAI key (`reasoning_summary`)
        # which `extract_reasoning_artifact` knows to look for.
        text_content = "".join(text_parts)
        raw_msg_dict: dict[str, Any] = {
            "role": "assistant",
            "content": text_content or None,
        }
        if tool_calls:
            raw_msg_dict["tool_calls"] = [
                {
                    "id": tc.tool_use_id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.args),
                    },
                }
                for tc in tool_calls
            ]
        if reasoning_summary_parts:
            raw_msg_dict["reasoning_summary"] = "\n\n".join(reasoning_summary_parts)

        return LLMResponse(
            provider=self._provider_name,
            model=getattr(resp, "model", self._model),
            stop_reason=cast("Any", stop_reason),
            tool_calls=tuple(tool_calls),
            text_content=text_content,
            tokens=tokens,
            raw_assistant_turn=AssistantTurn(
                provider=self._provider_name,
                blocks=(raw_msg_dict,),
            ),
        )

    def build_assistant_message_for_replay(
        self,
        response: LLMResponse,
    ) -> dict[str, Any]:
        """Reconstruct the OpenAI assistant message from raw blocks. The raw
        blocks tuple has exactly ONE element (the message dict), unlike
        Anthropic's per-block list.
        """
        raw_blocks = response.raw_assistant_turn.blocks
        if raw_blocks:
            raw_msg = dict(raw_blocks[0])
            # Both DeepSeek (v4-flash / deepseek-reasoner) and Kimi K2.5
            # default to thinking mode and REQUIRE the reasoning_content
            # field to be round-tripped on subsequent multi-turn calls.
            # Stripping it produces 400 invalid_request_error like:
            #   - DeepSeek: "the `reasoning_content` in the thinking mode
            #     must be passed back to the API."
            #   - Kimi:     "thinking is enabled but reasoning_content is
            #     missing in assistant tool call message at index N"
            # (The first 6-LLM tournament censored 2 hands on Kimi seat 4
            # before this whitelist was extended — codex 2026-04-27.)
            # Whitelist (not blacklist) is intentional: a new provider
            # that emits reasoning_content but doesn't require roundtrip
            # would add cost / token bloat for no reason; opt-in keeps
            # the surface tight.
            if self._provider_name not in {"deepseek", "kimi"}:
                raw_msg.pop("reasoning_content", None)
            # `reasoning_summary` is our internal annotation from the
            # Responses API path (OpenAI reasoning models). It's read
            # by extract_reasoning_artifact for the UI; OpenAI itself
            # has no use for it on a replay round trip, so strip before
            # sending the message back.
            raw_msg.pop("reasoning_summary", None)
            _normalize_assistant_content(raw_msg)
            return raw_msg
        # Fallback: synthesize from text + tool_calls (used when raw is empty).
        out: dict[str, Any] = {
            "role": "assistant",
            "content": response.text_content or None,
        }
        if response.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.tool_use_id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.args),
                    },
                }
                for tc in response.tool_calls
            ]
        _normalize_assistant_content(out)
        return out

    def build_tool_result_messages(
        self,
        *,
        tool_calls: tuple[ToolCall, ...],
        is_error: bool,
        content: str,
    ) -> list[dict[str, Any]]:
        """OpenAI: one role:tool message per tool_call_id. is_error has no
        flag in the OpenAI tool message — encode it textually so the model
        notices."""
        encoded = f"[ERROR] {content}" if is_error else content
        return [
            {"role": "tool", "tool_call_id": tc.tool_use_id, "content": encoded}
            for tc in tool_calls
        ]

    def build_user_text_message(self, text: str) -> dict[str, Any]:
        return {"role": "user", "content": text}

    def extract_reasoning_artifact(
        self,
        response: LLMResponse,
    ) -> tuple[ReasoningArtifact, ...]:
        """Extract a per-turn reasoning artifact for the UI:
          - DeepSeek / Kimi thinking-mode: `reasoning_content` (raw CoT)
            → ReasoningArtifact(kind=RAW)
          - OpenAI reasoning models (GPT-5.x, o-series via Responses
            API): `reasoning_summary` (an OpenAI-summarized blurb, NOT
            raw CoT) → ReasoningArtifact(kind=SUMMARY)
          - Everyone else: empty tuple.
        """
        if not response.raw_assistant_turn.blocks:
            return ()
        msg = response.raw_assistant_turn.blocks[0]
        # Order matters only if a single response carries both, which
        # shouldn't happen — but if it does we'd want both surfaced.
        artifacts: list[ReasoningArtifact] = []
        rc = msg.get("reasoning_content")
        if rc:
            # Gemini's <thought> output goes through reasoning_content but
            # is semantically a SUMMARY (Google compresses it before the
            # client sees it), unlike DeepSeek/Kimi raw chain-of-thought.
            # Use the per-provider flag to pick the right kind.
            kind = (
                ReasoningArtifactKind.SUMMARY
                if self._enable_thinking_summary
                else ReasoningArtifactKind.RAW
            )
            artifacts.append(
                ReasoningArtifact(
                    kind=kind,
                    content=str(rc),
                    provider_raw_index=0,
                )
            )
        rs = msg.get("reasoning_summary")
        if rs:
            artifacts.append(
                ReasoningArtifact(
                    kind=ReasoningArtifactKind.SUMMARY,
                    content=str(rs),
                    provider_raw_index=0,
                )
            )
        return tuple(artifacts)

    async def probe(self) -> ObservedCapability:
        """Send a one-token probe with seed=42 to test seed acceptance and
        observe whether reasoning_content is returned. spec §4.4 HR2-03 says
        probe should also test tool_use+thinking and capture system_fingerprint;
        Phase 3b probe captures system_fingerprint when present but does NOT
        actually drive a tool_use+thinking round (extended thinking enablement
        is deferred). Honest reporting via extra_flags.
        """
        seed_accepted = True
        observed_kinds: list[ReasoningArtifactKind] = []
        kwargs: dict[str, Any] = {
            "model": self._model,
            **_max_tokens_kwarg(self._model, 8),
            "messages": cast("Any", [{"role": "user", "content": "ok"}]),
            "seed": 42,
        }
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except (APITimeoutError, RateLimitError) as e:
            raise ProviderTransientError(f"probe transient: {e}") from e
        except BadRequestError as e:
            # 400-class. Distinguish seed-rejection vs other bad-request.
            if _looks_like_seed_unsupported(e):
                seed_accepted = False
                self._seed_known_unsupported = True
                kwargs.pop("seed", None)
                try:
                    resp = await self._client.chat.completions.create(**kwargs)
                except (APITimeoutError, RateLimitError) as e2:
                    raise ProviderTransientError(f"probe transient: {e2}") from e2
                except APIStatusError as e2:
                    raise ProviderPermanentError(f"probe permanent: {e2}") from e2
            else:
                raise ProviderPermanentError(f"probe bad-request: {e}") from e
        except APIStatusError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and status >= 500:
                raise ProviderTransientError(f"probe transient {status}: {e}") from e
            if status == 429:
                raise ProviderTransientError(f"probe rate-limited: {e}") from e
            raise ProviderPermanentError(f"probe permanent {status}: {e}") from e

        # latch the probe result so subsequent complete() calls reflect it
        if seed_accepted:
            self._seed_known_unsupported = False

        msg = resp.choices[0].message
        if getattr(msg, "reasoning_content", None):
            observed_kinds.append(ReasoningArtifactKind.RAW)

        # spec §4.4: capture system_fingerprint if the API returns one
        # (only OpenAI o-series + 4o models do; DeepSeek doesn't).
        system_fingerprint = getattr(resp, "system_fingerprint", None)

        # spec §4.6: if probe observed nothing, record UNAVAILABLE explicitly
        # (signals "tested, none seen" vs empty tuple "didn't test").
        if not observed_kinds:
            observed_kinds.append(ReasoningArtifactKind.UNAVAILABLE)

        probed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        return ObservedCapability(
            provider=self._provider_name,
            probed_at=probed_at,
            reasoning_kinds=tuple(observed_kinds),
            seed_accepted=seed_accepted,
            tool_use_with_thinking_ok=False,  # see extra_flags
            extra_flags={
                "base_url": str(self._client.base_url) if hasattr(self._client, "base_url") else "",
                "tool_use_with_thinking_probed": False,
                "system_fingerprint": system_fingerprint or "",
            },
        )


def _normalize_assistant_content(msg: dict[str, Any]) -> None:
    """In-place: shape the OpenAI-style assistant message dict so strict
    OpenAI-compatible providers accept it on multi-turn replay.

    Two things:

    1. Replace null / empty `content` with a single space. Kimi
       (api.moonshot.cn) rejects ANY assistant message whose content is
       null or empty string with 400 "message at position N with role
       'assistant' must not be empty." Kimi has even been observed to
       return {content: "", tool_calls: null} itself which we'd then echo
       back, triggering the rejection.

    2. Strip OpenAI-cruft null fields (`function_call: null`,
       `audio: null`, `refusal: null`, `annotations: null`, `tool_calls:
       null`). Gemini's OpenAI-compat shim rejects these with
       "Value is not a struct: null" because its parser interprets the
       fields as expected-to-be-struct and null violates that.

    A single-space placeholder is OpenAI-compatible (OpenAI accepts any
    string content), semantically equivalent (tool calls live in
    `tool_calls`), and unblocks both strict providers.
    """
    content = msg.get("content")
    if content is None or content == "":
        msg["content"] = " "
    # Strip OpenAI legacy / extension fields whose null value confuses
    # other providers' parsers. Only strip when value is None — preserves
    # any field that's actually populated.
    for legacy_field in ("function_call", "audio", "refusal", "annotations"):
        if msg.get(legacy_field) is None and legacy_field in msg:
            msg.pop(legacy_field)
    # tool_calls=null is a special case: keep the key absent rather than
    # =null, since some providers (Gemini) reject the null value here too.
    if msg.get("tool_calls") is None and "tool_calls" in msg:
        msg.pop("tool_calls")


def _looks_like_seed_unsupported(exc: BadRequestError) -> bool:
    """Heuristic: does this 400 error reference the `seed` parameter as the
    cause? Matches OpenAI's 'Unknown parameter: seed' / 'unsupported parameter'
    style messages and DeepSeek's variants. We err on the side of NOT
    suppressing real bad-request errors — only retry without seed when we're
    pretty sure that's the issue.
    """
    msg = str(exc).lower()
    # Common forms across providers we've seen / expect.
    seed_phrases = (
        "unknown parameter: seed",
        "unsupported parameter: seed",
        "'seed' is not a recognized",
        "parameter 'seed'",
        "unrecognized request argument: seed",
        # Gemini OpenAI-compat shim form: "Unknown name \"seed\""
        'unknown name "seed"',
    )
    return any(p in msg for p in seed_phrases)


__all__ = ["OpenAICompatibleProvider"]

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


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        provider_name_value: str,
        model: str,
        api_key: str,
        base_url: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self._provider_name = provider_name_value
        self._model = model
        self._max_tokens = max_tokens
        # AsyncOpenAI accepts base_url=None (= OpenAI canonical endpoint).
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        # spec §11.2: probe will set this to True if seed is rejected so
        # that complete() drops seed on subsequent calls. Defaults to None
        # (unknown until probe runs); complete() treats None as "try seed".
        self._seed_known_unsupported: bool | None = None

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
        """DeepSeek-Reasoner: surface `reasoning_content` as RAW. Other
        OpenAI-compatible models: empty tuple.
        """
        if not response.raw_assistant_turn.blocks:
            return ()
        msg = response.raw_assistant_turn.blocks[0]
        rc = msg.get("reasoning_content")
        if rc is None or rc == "":
            return ()
        return (
            ReasoningArtifact(
                kind=ReasoningArtifactKind.RAW,
                content=str(rc),
                provider_raw_index=0,
            ),
        )

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

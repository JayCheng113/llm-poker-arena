"""AnthropicProvider — adapter for Anthropic Claude via the official SDK.

Phase 3a scope: send messages + tools, normalize response into LLMResponse,
translate APIStatusError into transient (5xx, 429) or permanent (4xx).

Out of scope (3b): extended-thinking blocks, capability probe, system prompt
caching headers.
"""
from __future__ import annotations

from typing import Any, cast

from anthropic import APIStatusError, APITimeoutError, AsyncAnthropic, RateLimitError

from llm_poker_arena.agents.llm.provider_base import (
    LLMProvider,
    ProviderPermanentError,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    ReasoningArtifact,
    ReasoningArtifactKind,
    TokenCounts,
    ToolCall,
)


class AnthropicProvider(LLMProvider):
    def __init__(
        self, *, model: str, api_key: str, max_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = AsyncAnthropic(api_key=api_key)

    async def complete(
        self,
        *,
        system: str | None = None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        try:
            # Anthropic SDK uses TypedDict for messages/tools; we use plain
            # dicts here for cross-provider portability and cast at the boundary.
            create_kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": self._max_tokens,
                "temperature": temperature,
                "messages": cast("Any", messages),
                "tools": cast("Any", tools) if tools else cast("Any", None),
            }
            if system is not None:
                create_kwargs["system"] = system
            resp = await self._client.messages.create(**create_kwargs)
        except (APITimeoutError, RateLimitError) as e:
            raise ProviderTransientError(str(e)) from e
        except APIStatusError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and status >= 500:
                raise ProviderTransientError(f"{status}: {e}") from e
            if status == 429:
                raise ProviderTransientError(f"429 rate limited: {e}") from e
            raise ProviderPermanentError(f"{status}: {e}") from e

        return self._normalize(resp)

    def provider_name(self) -> str:
        return "anthropic"

    def _normalize(self, resp: Any) -> LLMResponse:  # noqa: ANN401
        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []
        raw_blocks: list[dict[str, Any]] = []
        for block in resp.content:
            block_dump = (
                block.model_dump() if hasattr(block, "model_dump") else dict(block)
            )
            raw_blocks.append(block_dump)
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    name=block.name,
                    args=dict(block.input or {}),
                    tool_use_id=block.id,
                ))
            elif block.type == "text":
                text_parts.append(block.text)

        usage = resp.usage
        tokens = TokenCounts(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_input_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            cache_creation_input_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        )

        stop_reason_raw = resp.stop_reason or "other"
        stop_reason = stop_reason_raw if stop_reason_raw in (
            "end_turn", "tool_use", "max_tokens", "stop_sequence",
        ) else "other"

        return LLMResponse(
            provider="anthropic",
            model=resp.model,
            stop_reason=cast("Any", stop_reason),
            tool_calls=tuple(tool_calls),
            text_content="".join(text_parts),
            tokens=tokens,
            raw_assistant_turn=AssistantTurn(
                provider="anthropic", blocks=tuple(raw_blocks),
            ),
        )

    def build_assistant_message_for_replay(
        self, response: LLMResponse,
    ) -> dict[str, Any]:
        """spec §4.4 BR2-07: pass raw blocks through byte-identical so
        thinking/encrypted_thinking/redacted_thinking blocks survive replay.
        Synthesize text+tool_use blocks only when raw is empty (mock case).
        """
        blocks = list(response.raw_assistant_turn.blocks)
        if not blocks:
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

    def build_tool_result_messages(
        self,
        *,
        tool_calls: tuple[ToolCall, ...],
        is_error: bool,
        content: str,
    ) -> list[dict[str, Any]]:
        return [{
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tc.tool_use_id,
                    "is_error": is_error,
                    "content": content,
                }
                for tc in tool_calls
            ],
        }]

    def build_user_text_message(self, text: str) -> dict[str, Any]:
        return {"role": "user", "content": text}

    def extract_reasoning_artifact(
        self, response: LLMResponse,
    ) -> tuple[ReasoningArtifact, ...]:
        """spec §4.6: walk raw blocks, return thinking/encrypted/redacted as
        ReasoningArtifact tuple. Empty tuple if extended thinking is OFF
        (the typical Phase 3b case). The `provider_raw_index` ties each
        artifact back to its position in the raw block list so analysts can
        reconstruct ordering relative to text + tool_use blocks.

        spec §4.6 contract: REDACTED has no plaintext content (`content=None`);
        ENCRYPTED carries an opaque payload (we surface it as a base64-ish
        string so the data is recoverable for forensic inspection, but
        downstream code MUST NOT treat ENCRYPTED.content as human-readable
        rationale). THINKING_BLOCK is the only kind whose `content` is
        plaintext rationale.
        """
        out: list[ReasoningArtifact] = []
        for idx, block in enumerate(response.raw_assistant_turn.blocks):
            btype = block.get("type")
            if btype == "thinking":
                out.append(ReasoningArtifact(
                    kind=ReasoningArtifactKind.THINKING_BLOCK,
                    content=str(block.get("thinking") or ""),
                    provider_raw_index=idx,
                ))
            elif btype == "redacted_thinking":
                # Spec §4.6: REDACTED has no plaintext; content is None.
                # The opaque `data` field is preserved in the raw blocks
                # via build_assistant_message_for_replay; analysts who
                # need it can read raw_assistant_turn.blocks directly.
                out.append(ReasoningArtifact(
                    kind=ReasoningArtifactKind.REDACTED,
                    content=None,
                    provider_raw_index=idx,
                ))
            elif btype == "encrypted_thinking":
                # Spec §4.6: ENCRYPTED carries opaque base64 payload. We
                # store it for forensic recovery but downstream rationale
                # checks must reject it (see _has_text_rationale_artifact
                # in LLMAgent).
                out.append(ReasoningArtifact(
                    kind=ReasoningArtifactKind.ENCRYPTED,
                    content=str(block.get("data") or ""),
                    provider_raw_index=idx,
                ))
        return tuple(out)


__all__ = ["AnthropicProvider"]

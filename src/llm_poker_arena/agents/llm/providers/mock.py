"""MockLLMProvider — preset-driven LLM stub used by ReAct unit tests.

The mock does NOT simulate the wire format of any real provider; tests that
care about wire format use AnthropicProvider with monkeypatched SDK calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from llm_poker_arena.agents.llm.provider_base import (
    LLMProvider,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.types import LLMResponse


@dataclass(frozen=True)
class MockResponseScript:
    """Pre-baked response sequence for a single test.

    `responses[i]` is delivered on the i-th `complete()` call.
    `errors_at_step[i]`, when set, raises the given exception on the i-th call
    BEFORE any response is consumed (so the provider doesn't advance the cursor).
    """

    responses: tuple[LLMResponse, ...] = ()
    errors_at_step: dict[int, Exception] = field(default_factory=dict)


class MockLLMProvider(LLMProvider):
    """Two-cursor mock: `call_index` tracks total calls (drives error injection),
    `response_cursor` indexes into `responses` and only advances when a real
    response is delivered. This way an error at call 0 followed by a real
    response at call 1 returns `responses[0]`, not `responses[1]`.
    """

    def __init__(self, script: MockResponseScript) -> None:
        self._script = script
        self._call_index = 0
        self._response_cursor = 0

    async def complete(
        self,
        *,
        system: str | None = None,  # captured but unused by mock
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        call_idx = self._call_index
        self._call_index += 1
        if call_idx in self._script.errors_at_step:
            raise self._script.errors_at_step[call_idx]
        ridx = self._response_cursor
        if ridx >= len(self._script.responses):
            raise RuntimeError(
                f"MockLLMProvider script exhausted at call {call_idx} "
                f"(response cursor {ridx}, have {len(self._script.responses)} "
                f"responses)"
            )
        resp = self._script.responses[ridx]
        self._response_cursor += 1
        return resp

    def provider_name(self) -> str:
        return "mock"


__all__ = ["MockLLMProvider", "MockResponseScript", "ProviderTransientError"]

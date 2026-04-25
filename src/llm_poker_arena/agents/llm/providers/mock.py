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
    def __init__(self, script: MockResponseScript) -> None:
        self._script = script
        self._cursor = 0

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        idx = self._cursor
        if idx in self._script.errors_at_step:
            self._cursor += 1
            raise self._script.errors_at_step[idx]
        if idx >= len(self._script.responses):
            raise RuntimeError(
                f"MockLLMProvider script exhausted at step {idx} "
                f"(have {len(self._script.responses)} responses)"
            )
        resp = self._script.responses[idx]
        self._cursor += 1
        return resp

    def provider_name(self) -> str:
        return "mock"


__all__ = ["MockLLMProvider", "MockResponseScript", "ProviderTransientError"]

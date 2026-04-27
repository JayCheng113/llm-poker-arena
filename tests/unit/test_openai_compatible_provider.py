"""Unit tests for OpenAICompatibleProvider, covering both OpenAI Chat and
DeepSeek (OpenAI-compatible at base_url=https://api.deepseek.com/v1).
SDK calls are monkeypatched — no network."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_poker_arena.agents.llm.provider_base import (
    ProviderPermanentError,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.providers.openai_compatible import (
    OpenAICompatibleProvider,
    _max_tokens_kwarg,
)
from llm_poker_arena.agents.llm.types import (
    LLMResponse,
    ObservedCapability,
    ReasoningArtifactKind,
    ToolCall,
)


class _FakeFunc:
    def __init__(self, name: str, args_json: str) -> None:
        self.name = name
        self.arguments = args_json


class _FakeToolCall:
    def __init__(self, id_: str, name: str, args_json: str) -> None:
        self.id = id_
        self.type = "function"
        self.function = _FakeFunc(name, args_json)


class _FakeMessage:
    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[_FakeToolCall] | None = None,
        reasoning_content: str | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content

    def model_dump(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls is not None:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in self.tool_calls
            ]
        if self.reasoning_content is not None:
            d["reasoning_content"] = self.reasoning_content
        return d


class _FakeChoice:
    def __init__(self, message: _FakeMessage, finish_reason: str = "tool_calls") -> None:
        self.message = message
        self.finish_reason = finish_reason


class _FakeUsage:
    prompt_tokens = 25
    completion_tokens = 10


class _FakeChatResp:
    def __init__(self, choice: _FakeChoice, model: str) -> None:
        self.choices = [choice]
        self.usage = _FakeUsage()
        self.model = model


def _make_provider_with_fake_create(
    fake_resp: _FakeChatResp,
    *,
    base_url: str | None = None,
    provider_name_value: str = "openai",
    model: str = "gpt-4o-mini",
) -> tuple[OpenAICompatibleProvider, AsyncMock]:
    p = OpenAICompatibleProvider(
        provider_name_value=provider_name_value,
        model=model,
        api_key="sk-test",
        base_url=base_url,
    )
    fake_create = AsyncMock(return_value=fake_resp)
    p._client = MagicMock()
    p._client.chat = MagicMock()
    p._client.chat.completions = MagicMock()
    p._client.chat.completions.create = fake_create
    return p, fake_create


def test_openai_complete_normalizes_tool_call_response() -> None:
    msg = _FakeMessage(
        content="I'll fold.",
        tool_calls=[_FakeToolCall("call_abc", "fold", "{}")],
    )
    resp = _FakeChatResp(_FakeChoice(msg), model="gpt-4o-mini")
    p, _fake = _make_provider_with_fake_create(resp)
    out = asyncio.run(
        p.complete(
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[
                {
                    "name": "fold",
                    "description": "fold the hand",
                    "input_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                }
            ],
            temperature=0.5,
            seed=42,
        )
    )
    assert isinstance(out, LLMResponse)
    assert out.provider == "openai"
    assert len(out.tool_calls) == 1
    assert out.tool_calls[0] == ToolCall(name="fold", args={}, tool_use_id="call_abc")
    assert out.text_content == "I'll fold."
    assert out.tokens.input_tokens == 25
    assert out.tokens.output_tokens == 10
    assert out.tokens.cache_read_input_tokens == 0
    assert out.stop_reason == "tool_use"


def test_openai_complete_parses_arguments_json_to_dict() -> None:
    msg = _FakeMessage(
        content=None,
        tool_calls=[_FakeToolCall("call_x", "raise_to", '{"amount": 300}')],
    )
    resp = _FakeChatResp(_FakeChoice(msg), model="gpt-4o-mini")
    p, _ = _make_provider_with_fake_create(resp)
    out = asyncio.run(
        p.complete(
            system=None,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            temperature=0.5,
            seed=None,
        )
    )
    assert out.tool_calls[0].args == {"amount": 300}


def test_openai_malformed_arguments_json_yields_empty_args() -> None:
    """If the LLM returns invalid JSON in function.arguments, we record args={}
    so validate_action sees missing keys and triggers illegal_action_retry —
    rather than crashing the agent."""
    msg = _FakeMessage(
        content=None,
        tool_calls=[_FakeToolCall("call_y", "raise_to", "{not valid json")],
    )
    resp = _FakeChatResp(_FakeChoice(msg), model="gpt-4o-mini")
    p, _ = _make_provider_with_fake_create(resp)
    out = asyncio.run(
        p.complete(
            system=None,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            temperature=0.5,
            seed=None,
        )
    )
    assert out.tool_calls[0].args == {}


class _FakeAPIStatus(Exception):
    """Test double for openai.APIStatusError. Subclassed so isinstance
    checks behave correctly when monkeypatched into the provider module."""

    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(message or f"status={status}")
        self.response = MagicMock()
        self.response.status_code = status


class _FakeBadRequest(_FakeAPIStatus):
    """Test double for openai.BadRequestError (a 400 subclass of APIStatusError)."""

    def __init__(self, message: str) -> None:
        super().__init__(400, message)


def test_openai_5xx_raises_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """500-class status code → ProviderTransientError (eligible for api_retry).
    Uses monkeypatch.setattr (cleaner than manual try/finally module mutation)."""
    from llm_poker_arena.agents.llm.providers import openai_compatible

    monkeypatch.setattr(openai_compatible, "APIStatusError", _FakeAPIStatus)
    monkeypatch.setattr(openai_compatible, "BadRequestError", _FakeBadRequest)

    p = OpenAICompatibleProvider(
        provider_name_value="openai", model="gpt-4o-mini", api_key="sk-test"
    )
    fake_create = AsyncMock(side_effect=_FakeAPIStatus(503))
    p._client = MagicMock()
    p._client.chat = MagicMock()
    p._client.chat.completions = MagicMock()
    p._client.chat.completions.create = fake_create
    with pytest.raises(ProviderTransientError):
        asyncio.run(p.complete(system=None, messages=[], tools=[], temperature=0.5, seed=None))


def test_openai_4xx_auth_raises_permanent_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """401 Auth → ProviderPermanentError (NOT mistaken for seed-unsupported).
    Critical regression: codex audit flagged that catching every APIStatusError
    misclassified 4xx auth as seed rejection."""
    from llm_poker_arena.agents.llm.providers import openai_compatible

    monkeypatch.setattr(openai_compatible, "APIStatusError", _FakeAPIStatus)
    monkeypatch.setattr(openai_compatible, "BadRequestError", _FakeBadRequest)

    p = OpenAICompatibleProvider(
        provider_name_value="openai", model="gpt-4o-mini", api_key="sk-test"
    )
    fake_create = AsyncMock(side_effect=_FakeAPIStatus(401, "auth failed"))
    p._client = MagicMock()
    p._client.chat = MagicMock()
    p._client.chat.completions = MagicMock()
    p._client.chat.completions.create = fake_create
    with pytest.raises(ProviderPermanentError):
        asyncio.run(p.complete(system=None, messages=[], tools=[], temperature=0.5, seed=42))


def test_openai_400_seed_unsupported_retries_without_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the API rejects seed with a 'unknown parameter: seed' message,
    complete() should retry once without seed and latch _seed_known_unsupported
    so subsequent calls drop seed automatically. Codex audit fix for I5."""
    from llm_poker_arena.agents.llm.providers import openai_compatible

    monkeypatch.setattr(openai_compatible, "APIStatusError", _FakeAPIStatus)
    monkeypatch.setattr(openai_compatible, "BadRequestError", _FakeBadRequest)

    p = OpenAICompatibleProvider(
        provider_name_value="openai", model="gpt-4o-mini", api_key="sk-test"
    )
    # Build a real successful response for the retry path.
    msg = _FakeMessage(content="ok", tool_calls=None)
    success = _FakeChatResp(_FakeChoice(msg, finish_reason="stop"), model="gpt-4o-mini")
    call_seq: list[Any] = [
        _FakeBadRequest("Unknown parameter: seed"),
        success,
    ]
    fake_create = AsyncMock(side_effect=call_seq)
    p._client = MagicMock()
    p._client.chat = MagicMock()
    p._client.chat.completions = MagicMock()
    p._client.chat.completions.create = fake_create

    out = asyncio.run(
        p.complete(
            system=None,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            temperature=0.5,
            seed=42,
        )
    )
    assert out.text_content == "ok"
    assert p._seed_known_unsupported is True
    # First call: kwargs included seed; second call: kwargs did NOT include seed
    assert fake_create.await_count == 2
    first_kwargs = fake_create.await_args_list[0].kwargs
    second_kwargs = fake_create.await_args_list[1].kwargs
    assert first_kwargs.get("seed") == 42
    assert "seed" not in second_kwargs

    # Codex acceptance NIT: verify the latch persists across a SEPARATE
    # later complete() call, not just the immediate retry. Make a third call
    # with a fresh successful response and assert seed is still skipped.
    msg2 = _FakeMessage(content="ok2", tool_calls=None)
    success2 = _FakeChatResp(_FakeChoice(msg2, finish_reason="stop"), model="gpt-4o-mini")
    p._client.chat.completions.create = AsyncMock(return_value=success2)
    out2 = asyncio.run(
        p.complete(
            system=None,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            temperature=0.5,
            seed=42,
        )
    )
    assert out2.text_content == "ok2"
    third_kwargs = p._client.chat.completions.create.await_args_list[0].kwargs
    assert "seed" not in third_kwargs, (
        "_seed_known_unsupported latch should persist; subsequent calls "
        "must drop seed without round-tripping the rejection again"
    )


def test_openai_400_non_seed_bad_request_raises_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 400 BadRequest that is NOT about seed (e.g. malformed messages)
    must NOT trigger the retry-without-seed path; it should raise
    ProviderPermanentError. Codex audit fix for I4."""
    from llm_poker_arena.agents.llm.providers import openai_compatible

    monkeypatch.setattr(openai_compatible, "APIStatusError", _FakeAPIStatus)
    monkeypatch.setattr(openai_compatible, "BadRequestError", _FakeBadRequest)

    p = OpenAICompatibleProvider(
        provider_name_value="openai", model="gpt-4o-mini", api_key="sk-test"
    )
    fake_create = AsyncMock(
        side_effect=_FakeBadRequest(
            "Invalid 'messages[0].role': must be one of system, user, assistant"
        )
    )
    p._client = MagicMock()
    p._client.chat = MagicMock()
    p._client.chat.completions = MagicMock()
    p._client.chat.completions.create = fake_create
    with pytest.raises(ProviderPermanentError):
        asyncio.run(p.complete(system=None, messages=[], tools=[], temperature=0.5, seed=42))
    # Single call only — no retry attempted.
    assert fake_create.await_count == 1
    # Did NOT latch the seed-unsupported flag.
    assert p._seed_known_unsupported is None


def test_openai_build_tool_result_messages_returns_one_per_call() -> None:
    """OpenAI requires N separate role:tool messages, one per tool_call."""
    p = OpenAICompatibleProvider(
        provider_name_value="openai", model="gpt-4o-mini", api_key="sk-test"
    )
    tcs = (
        ToolCall(name="fold", args={}, tool_use_id="call_a"),
        ToolCall(name="raise_to", args={"amount": 300}, tool_use_id="call_b"),
    )
    msgs = p.build_tool_result_messages(
        tool_calls=tcs,
        is_error=True,
        content="bad call",
    )
    assert len(msgs) == 2
    for msg, tc in zip(msgs, tcs, strict=True):
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == tc.tool_use_id
        # is_error is encoded by prefixing content with [ERROR] (OpenAI has
        # no is_error flag in the tool message).
        assert "ERROR" in msg["content"] or "bad call" in msg["content"]


def test_openai_build_assistant_message_for_replay_includes_tool_calls() -> None:
    msg = _FakeMessage(
        content="ok",
        tool_calls=[_FakeToolCall("call_x", "fold", "{}")],
    )
    resp = _FakeChatResp(_FakeChoice(msg), model="gpt-4o-mini")
    p, _ = _make_provider_with_fake_create(resp)
    out = asyncio.run(
        p.complete(
            system=None,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            temperature=0.5,
            seed=None,
        )
    )
    replay = p.build_assistant_message_for_replay(out)
    assert replay["role"] == "assistant"
    assert replay["content"] == "ok"
    assert replay["tool_calls"][0]["id"] == "call_x"
    assert replay["tool_calls"][0]["function"]["name"] == "fold"


def test_openai_build_user_text_message_returns_plain_user() -> None:
    p = OpenAICompatibleProvider(
        provider_name_value="openai", model="gpt-4o-mini", api_key="sk-test"
    )
    assert p.build_user_text_message("hi") == {"role": "user", "content": "hi"}


def test_openai_provider_name_passthrough() -> None:
    p = OpenAICompatibleProvider(
        provider_name_value="deepseek",
        model="deepseek-chat",
        api_key="sk-test",
        base_url="https://api.deepseek.com/v1",
    )
    assert p.provider_name() == "deepseek"


def test_deepseek_reasoner_extracts_reasoning_content_as_raw_artifact() -> None:
    msg = _FakeMessage(
        content="The answer is fold.",
        tool_calls=[_FakeToolCall("call_z", "fold", "{}")],
        reasoning_content="Chain of thought: pot odds < equity, fold is +EV.",
    )
    resp = _FakeChatResp(_FakeChoice(msg), model="deepseek-reasoner")
    p, _ = _make_provider_with_fake_create(
        resp,
        base_url="https://api.deepseek.com/v1",
        provider_name_value="deepseek",
        model="deepseek-reasoner",
    )
    out = asyncio.run(
        p.complete(
            system=None,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            temperature=0.5,
            seed=None,
        )
    )
    arts = p.extract_reasoning_artifact(out)
    assert len(arts) == 1
    assert arts[0].kind == ReasoningArtifactKind.RAW
    assert arts[0].content == "Chain of thought: pot odds < equity, fold is +EV."
    assert arts[0].provider_raw_index == 0


def test_deepseek_chat_no_reasoning_content_returns_empty_tuple() -> None:
    msg = _FakeMessage(content="ok", tool_calls=[_FakeToolCall("c", "fold", "{}")])
    resp = _FakeChatResp(_FakeChoice(msg), model="deepseek-chat")
    p, _ = _make_provider_with_fake_create(
        resp,
        base_url="https://api.deepseek.com/v1",
        provider_name_value="deepseek",
        model="deepseek-chat",
    )
    out = asyncio.run(
        p.complete(
            system=None,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            temperature=0.5,
            seed=None,
        )
    )
    assert p.extract_reasoning_artifact(out) == ()


def test_kimi_replay_preserves_reasoning_content_for_multi_turn() -> None:
    """Regression: Kimi K2.5 (and the K2.x family) defaults to thinking
    mode and 400s with `thinking is enabled but reasoning_content is
    missing in assistant tool call message at index N` if we strip the
    field on the replay path. The first 6-LLM tournament censored 2
    hands on Kimi seat 4 before this whitelist was added — codex P1
    2026-04-27. Mirrors `test_deepseek_replay_preserves_reasoning_content`
    intent for the deepseek branch."""
    msg = _FakeMessage(
        content="Calling, pot odds favor it.",
        tool_calls=[_FakeToolCall("call_kimi_1", "call", "{}")],
        reasoning_content="(internal chain of thought elided by Kimi)",
    )
    resp = _FakeChatResp(_FakeChoice(msg), model="kimi-k2.5")
    p, _ = _make_provider_with_fake_create(
        resp,
        base_url="https://api.moonshot.cn/v1",
        provider_name_value="kimi",
        model="kimi-k2.5",
    )
    out = asyncio.run(
        p.complete(
            system=None,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            temperature=1.0,
            seed=None,
        )
    )
    replay = p.build_assistant_message_for_replay(out)
    assert replay["reasoning_content"] == "(internal chain of thought elided by Kimi)"


def test_openai_replay_strips_reasoning_content() -> None:
    """Counter-test: pure OpenAI (gpt-4o-mini, no thinking mode) should
    NOT carry reasoning_content into replay messages. Whitelist must be
    deepseek+kimi-only — adding more providers without API verification
    risks per-call token bloat / unsupported field errors."""
    msg = _FakeMessage(
        content="ok",
        tool_calls=[_FakeToolCall("c1", "fold", "{}")],
        reasoning_content="should-not-roundtrip",
    )
    resp = _FakeChatResp(_FakeChoice(msg), model="gpt-4o-mini")
    p, _ = _make_provider_with_fake_create(resp)
    out = asyncio.run(
        p.complete(
            system=None,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            temperature=0.5,
            seed=None,
        )
    )
    replay = p.build_assistant_message_for_replay(out)
    assert "reasoning_content" not in replay


def test_openai_probe_returns_observed_capability() -> None:
    msg = _FakeMessage(content="ok", tool_calls=None)
    resp = _FakeChatResp(_FakeChoice(msg, finish_reason="stop"), model="gpt-4o-mini")
    p, fake = _make_provider_with_fake_create(resp)
    cap = asyncio.run(p.probe())
    assert isinstance(cap, ObservedCapability)
    assert cap.provider == "openai"
    # Probe must call create at least once.
    assert fake.await_count >= 1
    # We pass seed=42 in the probe call to test acceptance.
    assert fake.await_args is not None
    kwargs = fake.await_args.kwargs
    assert kwargs.get("seed") == 42
    # No reasoning_content on the fake → reasoning_kinds=(UNAVAILABLE,)
    # (probe observed nothing — record explicitly per spec §4.6).
    assert cap.reasoning_kinds == (ReasoningArtifactKind.UNAVAILABLE,)


def test_deepseek_reasoner_probe_records_raw_kind() -> None:
    msg = _FakeMessage(content="ok", tool_calls=None, reasoning_content="meta thinking")
    resp = _FakeChatResp(_FakeChoice(msg, finish_reason="stop"), model="deepseek-reasoner")
    p, _ = _make_provider_with_fake_create(
        resp,
        base_url="https://api.deepseek.com/v1",
        provider_name_value="deepseek",
        model="deepseek-reasoner",
    )
    cap = asyncio.run(p.probe())
    assert ReasoningArtifactKind.RAW in cap.reasoning_kinds


@pytest.mark.parametrize(
    "model,expected_key",
    [
        ("gpt-4o-mini", "max_tokens"),
        ("gpt-4o", "max_tokens"),
        ("gpt-5", "max_completion_tokens"),
        ("gpt-5.4-mini", "max_completion_tokens"),
        ("gpt-5.5", "max_completion_tokens"),
        ("o1-mini", "max_completion_tokens"),
        ("o3", "max_completion_tokens"),
        ("deepseek-chat", "max_tokens"),
        ("deepseek-v4-flash", "max_tokens"),
        ("qwen3.6-plus", "max_tokens"),
    ],
)
def test_max_tokens_kwarg_routes_by_model_family(model: str, expected_key: str) -> None:
    """gpt-5.x and o-series require max_completion_tokens; others use max_tokens."""
    out = _max_tokens_kwarg(model, 100)
    assert out == {expected_key: 100}

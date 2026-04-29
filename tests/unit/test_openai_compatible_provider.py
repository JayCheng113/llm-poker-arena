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


def test_sdk_max_retries_is_forwarded_to_async_openai_client() -> None:
    """Provider-level capacity mitigation: when registry says a provider
    needs more SDK-level retries (Gemini AI Studio's 503 spikes), that
    number must reach AsyncOpenAI's `max_retries` so its built-in
    exponential backoff has room to ride out the spike. Default (None)
    leaves the SDK's own default (2) untouched."""
    # Default path — no override, SDK default 2 stays.
    default_p = OpenAICompatibleProvider(
        provider_name_value="openai", model="gpt-4o-mini", api_key="sk-test"
    )
    assert default_p._client.max_retries == 2

    # Override path — bumped retry budget reaches the client.
    bumped_p = OpenAICompatibleProvider(
        provider_name_value="gemini",
        model="gemini-2.5-flash",
        api_key="sk-test",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        sdk_max_retries=5,
    )
    assert bumped_p._client.max_retries == 5


def test_registry_make_provider_threads_sdk_max_retries_for_gemini() -> None:
    """Smoke: the registry-driven factory wires `sdk_max_retries` end to
    end. If a future refactor drops the field anywhere along the path
    (registry → make_provider → kwargs → AsyncOpenAI) Gemini silently
    reverts to the 2-retry default and 503-driven censors return."""
    from llm_poker_arena.agents.llm.providers.registry import PROVIDERS, make_provider

    assert PROVIDERS["gemini"].sdk_max_retries == 5
    p = make_provider("gemini", "gemini-2.5-flash", "AIza-test")
    assert p._client.max_retries == 5

    # Counter-check: providers without an override get the SDK default.
    p_openai = make_provider("openai", "gpt-4o-mini", "sk-test")
    assert p_openai._client.max_retries == 2


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
    ("model", "expected_key"),
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


# ---------------------------------------------------------------------------
# OpenAI Responses API path (GPT-5.x, o-series)
# ---------------------------------------------------------------------------

class _FakeSummaryBlock:
    def __init__(self, text: str) -> None:
        self.type = "summary_text"
        self.text = text


class _FakeReasoningItem:
    def __init__(self, summary_texts: list[str]) -> None:
        self.type = "reasoning"
        self.id = "rs_x"
        self.status = "completed"
        self.summary = [_FakeSummaryBlock(t) for t in summary_texts]


class _FakeOutputTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "output_text"
        self.text = text


class _FakeMessageItem:
    def __init__(self, text: str | None = None) -> None:
        self.type = "message"
        self.id = "msg_x"
        self.status = "completed"
        self.role = "assistant"
        self.content = [_FakeOutputTextBlock(text)] if text else []


class _FakeFunctionCallItem:
    def __init__(self, call_id: str, name: str, args_json: str) -> None:
        self.type = "function_call"
        self.id = "fc_x"
        self.call_id = call_id
        self.name = name
        self.arguments = args_json
        self.status = "completed"


class _FakeResponsesUsage:
    input_tokens = 120
    output_tokens = 60


class _FakeResponsesResp:
    def __init__(self, output_items: list[Any], model: str = "gpt-5.4-mini") -> None:
        self.output = output_items
        self.usage = _FakeResponsesUsage()
        self.model = model


def _make_responses_provider_with_fake(
    fake_resp: _FakeResponsesResp,
    *,
    model: str = "gpt-5.4-mini",
) -> tuple[OpenAICompatibleProvider, AsyncMock]:
    p = OpenAICompatibleProvider(
        provider_name_value="openai",
        model=model,
        api_key="sk-test",
    )
    fake_create = AsyncMock(return_value=fake_resp)
    p._client = MagicMock()
    p._client.responses.create = fake_create
    return p, fake_create


def test_openai_reasoning_model_routes_through_responses_api() -> None:
    """gpt-5.x and o-series MUST hit responses.create, not chat.completions.
    Otherwise we lose access to the reasoning summary the UI panel renders."""
    fake_resp = _FakeResponsesResp([
        _FakeMessageItem(text="folding"),
        _FakeFunctionCallItem("call_y", "fold", "{}"),
        _FakeReasoningItem(["Bottom of range, position is bad."]),
    ])
    p, fake_create = _make_responses_provider_with_fake(fake_resp)
    out = asyncio.run(
        p.complete(
            system="be a poker player",
            messages=[{"role": "user", "content": "your turn"}],
            tools=[{"name": "fold", "description": "fold", "input_schema": {"type": "object", "properties": {}}}],
            temperature=0.7,
            seed=None,
        )
    )
    assert fake_create.await_count == 1
    assert fake_create.await_args is not None
    kwargs = fake_create.await_args.kwargs
    # Reasoning kwarg threaded through:
    assert kwargs["reasoning"]["summary"] == "auto"
    # Tool spec uses Responses' flat shape (no "function" nesting):
    assert kwargs["tools"][0]["type"] == "function"
    assert kwargs["tools"][0]["name"] == "fold"
    # System prompt converted to a developer-role message item:
    first = kwargs["input"][0]
    assert first["role"] == "developer"
    assert first["content"] == "be a poker player"
    # Response carries the tool call + summary + text:
    assert len(out.tool_calls) == 1
    assert out.tool_calls[0].name == "fold"
    assert out.text_content == "folding"
    arts = p.extract_reasoning_artifact(out)
    assert len(arts) == 1
    assert arts[0].kind == ReasoningArtifactKind.SUMMARY
    assert arts[0].content is not None
    assert "Bottom of range" in arts[0].content


def test_responses_path_no_summary_returns_empty_artifacts() -> None:
    """If OpenAI returns no reasoning item (low effort can do this),
    extract_reasoning_artifact must NOT fabricate one."""
    fake_resp = _FakeResponsesResp([
        _FakeMessageItem(text="check"),
        _FakeFunctionCallItem("c1", "check", "{}"),
    ])
    p, _ = _make_responses_provider_with_fake(fake_resp)
    out = asyncio.run(p.complete(system=None, messages=[{"role": "user", "content": "hi"}], tools=[], temperature=0.7, seed=None))
    assert p.extract_reasoning_artifact(out) == ()


def test_responses_replay_strips_reasoning_summary_before_send() -> None:
    """The reasoning_summary key is our internal annotation. The OpenAI
    API itself doesn't accept it on a multi-turn input — must be stripped
    when round-tripping through build_assistant_message_for_replay."""
    fake_resp = _FakeResponsesResp([
        _FakeMessageItem(text="raise"),
        _FakeFunctionCallItem("c2", "raise_to", '{"amount": 300}'),
        _FakeReasoningItem(["Ace-king suited from the cutoff is a clear open."]),
    ])
    p, _ = _make_responses_provider_with_fake(fake_resp)
    out = asyncio.run(p.complete(system=None, messages=[{"role": "user", "content": "act"}], tools=[], temperature=0.7, seed=None))
    replay = p.build_assistant_message_for_replay(out)
    assert "reasoning_summary" not in replay
    # Tool calls and content should still survive into the replay form:
    assert replay["content"] == "raise"
    assert replay["tool_calls"][0]["function"]["name"] == "raise_to"


def test_messages_to_responses_input_handles_full_conversation() -> None:
    """Tool-use round trip in the Chat-shaped history must convert into a
    Responses-shaped item list (developer/user messages, function_call
    items, function_call_output items). Pure function — no SDK round
    trip needed."""
    msgs: list[dict[str, Any]] = [
        {"role": "user", "content": "you are seat 0"},
        {
            "role": "assistant",
            "content": "I'll check pot odds first.",
            "tool_calls": [
                {"id": "call_pot", "type": "function", "function": {"name": "pot_odds", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_pot", "content": '{"value": 0.33}'},
        {"role": "user", "content": "now act"},
    ]
    items = OpenAICompatibleProvider._messages_to_responses_input("system_text", msgs)
    types = [it["type"] for it in items]
    # developer (system), user, assistant message text, function_call,
    # function_call_output, user
    assert types == [
        "message", "message", "message", "function_call", "function_call_output", "message",
    ]
    assert items[0]["role"] == "developer"
    assert items[3]["call_id"] == "call_pot"
    assert items[4]["call_id"] == "call_pot"


def test_non_openai_reasoning_model_stays_on_chat_completions() -> None:
    """Other OpenAI-compat providers (DeepSeek, Kimi, etc.) don't have a
    Responses API. Even if their model id starts with 'gpt-5' (it
    wouldn't, but defensive), the routing must NOT divert them off
    chat.completions."""
    msg = _FakeMessage(content="ok", tool_calls=[_FakeToolCall("c", "fold", "{}")])
    resp = _FakeChatResp(_FakeChoice(msg), model="gpt-5.4-mini")
    p, fake = _make_provider_with_fake_create(
        resp,
        provider_name_value="deepseek",
        model="gpt-5.4-mini",  # implausible but exercises the guard
        base_url="https://api.deepseek.com/v1",
    )
    asyncio.run(p.complete(system=None, messages=[{"role": "user", "content": "hi"}], tools=[], temperature=0.5, seed=None))
    # Should have hit chat.completions.create, not responses.create.
    assert fake.await_count == 1


# ---------------------------------------------------------------------------
# Gemini thinking summary path
# ---------------------------------------------------------------------------

def test_split_gemini_thought_extracts_single_block() -> None:
    """The pure split helper: one <thought> block → summary, rest → visible."""
    from llm_poker_arena.agents.llm.providers.openai_compatible import _split_gemini_thought
    visible, summary = _split_gemini_thought(
        "<thought>**Analyzing**\n\nAKs in BB facing 3x. Premium hand.</thought>**Raise.** AKs is too strong to fold."
    )
    assert visible == "**Raise.** AKs is too strong to fold."
    assert summary == "**Analyzing**\n\nAKs in BB facing 3x. Premium hand."


def test_split_gemini_thought_handles_multiple_blocks() -> None:
    """Joined with a blank line so the UI panel reads as paragraphs."""
    from llm_poker_arena.agents.llm.providers.openai_compatible import _split_gemini_thought
    visible, summary = _split_gemini_thought(
        "Pre <thought>first</thought> mid <thought>second</thought> end"
    )
    assert "first" in summary
    assert "second" in summary
    assert "<thought>" not in visible
    assert "Pre" in visible
    assert "end" in visible


def test_split_gemini_thought_graceful_when_unmatched_tag() -> None:
    """Missing closing tag → leave content alone, no extracted summary.
    Reason: making something up risks losing real LLM output."""
    from llm_poker_arena.agents.llm.providers.openai_compatible import _split_gemini_thought
    visible, summary = _split_gemini_thought(
        "<thought>start of thinking but no end ever comes through"
    )
    assert summary == ""
    assert visible == "<thought>start of thinking but no end ever comes through"


def test_split_gemini_thought_no_thought_tag_passes_through() -> None:
    from llm_poker_arena.agents.llm.providers.openai_compatible import _split_gemini_thought
    visible, summary = _split_gemini_thought("Plain decision text only.")
    assert visible == "Plain decision text only."
    assert summary == ""


def test_complete_with_thinking_summary_injects_extra_body() -> None:
    """The extra_body kwarg must reach AsyncOpenAI when the provider
    has enable_thinking_summary=True. Without it Gemini stays silent
    about its reasoning."""
    msg = _FakeMessage(content="<thought>internal thinking goes here</thought>**Raise to 600.**")
    resp = _FakeChatResp(_FakeChoice(msg, finish_reason="stop"), model="gemini-2.5-flash")
    p = OpenAICompatibleProvider(
        provider_name_value="gemini",
        model="gemini-2.5-flash",
        api_key="AIza-test",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        enable_thinking_summary=True,
    )
    fake_create = AsyncMock(return_value=resp)
    p._client = MagicMock()
    p._client.chat.completions.create = fake_create
    asyncio.run(
        p.complete(
            system="play poker",
            messages=[{"role": "user", "content": "act"}],
            tools=[],
            temperature=0.7,
            seed=None,
        )
    )
    assert fake_create.await_args is not None
    kwargs = fake_create.await_args.kwargs
    # Double-wrapped: AsyncOpenAI spreads its `extra_body=` dict to the
    # request body's top level, so we send {extra_body: {google: ...}}
    # and the SDK lays it out as body = {..., extra_body: {google: ...}}
    # — which is the literal shape Gemini's OpenAI-compat shim wants.
    # Naive single-wrap lands as body.google, which Gemini rejects with
    # "Unknown name google" (smoke #2 censored 3/3 hands before this fix).
    assert kwargs.get("extra_body") == {
        "extra_body": {
            "google": {"thinking_config": {"include_thoughts": True}}
        }
    }


def test_gemini_thinking_artifact_is_summary_not_raw() -> None:
    """Gemini reasoning summary semantically matches OpenAI's summary
    artifact kind (compressed, user-facing) — NOT DeepSeek/Kimi raw CoT.
    The provider's enable_thinking_summary flag picks the kind."""
    msg = _FakeMessage(
        content="<thought>**Plan**\n\nNeed to fold; pot odds bad.</thought>Fold."
    )
    resp = _FakeChatResp(_FakeChoice(msg, finish_reason="stop"), model="gemini-2.5-flash")
    p = OpenAICompatibleProvider(
        provider_name_value="gemini",
        model="gemini-2.5-flash",
        api_key="AIza-test",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        enable_thinking_summary=True,
    )
    fake_create = AsyncMock(return_value=resp)
    p._client = MagicMock()
    p._client.chat.completions.create = fake_create
    out = asyncio.run(
        p.complete(
            system=None,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            temperature=0.7,
            seed=None,
        )
    )
    # text_content carries the visible decision (no <thought> leakage):
    assert out.text_content == "Fold."
    assert "<thought>" not in out.text_content
    # Reasoning artifact is SUMMARY-kind:
    arts = p.extract_reasoning_artifact(out)
    assert len(arts) == 1
    assert arts[0].kind == ReasoningArtifactKind.SUMMARY
    assert arts[0].content is not None
    assert "Plan" in arts[0].content


def test_gemini_replay_strips_reasoning_content_for_round_trip() -> None:
    """Gemini is stateless on multi-turn calls — sending reasoning_content
    back produces 'Unknown name reasoning_content' 400. The replay
    builder's existing whitelist (deepseek+kimi only) handles this; the
    test pins that behavior so a future provider tweak doesn't regress."""
    msg = _FakeMessage(
        content="<thought>**Plan**: fold weak hand.</thought>Fold."
    )
    resp = _FakeChatResp(_FakeChoice(msg, finish_reason="stop"), model="gemini-2.5-flash")
    p = OpenAICompatibleProvider(
        provider_name_value="gemini",
        model="gemini-2.5-flash",
        api_key="AIza-test",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        enable_thinking_summary=True,
    )
    fake_create = AsyncMock(return_value=resp)
    p._client = MagicMock()
    p._client.chat.completions.create = fake_create
    out = asyncio.run(p.complete(system=None, messages=[{"role": "user", "content": "hi"}],
                                  tools=[], temperature=0.7, seed=None))
    replay = p.build_assistant_message_for_replay(out)
    assert "reasoning_content" not in replay
    # And the visible content (without <thought>) is what we send back:
    assert replay["content"] == "Fold."


def test_registry_make_provider_threads_thinking_flag_for_gemini() -> None:
    """Smoke: registry → make_provider → OpenAICompatibleProvider, the
    enable_thinking_summary flag must reach the constructor for Gemini
    and stay False for everyone else."""
    from llm_poker_arena.agents.llm.providers.registry import PROVIDERS, make_provider
    assert PROVIDERS["gemini"].enable_thinking_summary is True
    assert PROVIDERS["openai"].enable_thinking_summary is False
    p_g = make_provider("gemini", "gemini-2.5-flash", "AIza-test")
    p_o = make_provider("openai", "gpt-4o-mini", "sk-test")
    assert p_g._enable_thinking_summary is True
    assert p_o._enable_thinking_summary is False

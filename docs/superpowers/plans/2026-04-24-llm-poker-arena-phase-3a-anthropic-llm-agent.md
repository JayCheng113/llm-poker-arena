# Phase 3a: Anthropic LLM Agent MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the minimum architecture that lets a real Anthropic Claude model play 6-max NLHE in this engine — async `Agent` ABC, `TurnDecisionResult` schema, `LLMProvider` ABC, `MockLLMProvider` (for tests), `AnthropicProvider` (for integration), simplified Bounded ReAct loop with K=0 (action-only) and the four retry counters required by spec §4.2.

**Architecture:** Phase 3a deliberately defers utility tools, multi-provider, reasoning-artifact extraction, and Jinja prompts to Phases 3b–3d. The async `Agent.decide(view) -> TurnDecisionResult` contract ships in 3a; the ReAct loop is the simpler "ask once, retry up to 1× per error class, fallback to `default_safe_action`" shape. `Session` migrates to async; existing `RandomAgent` / `RuleBasedAgent` / `HumanCLIAgent` become async wrappers around their existing sync logic.

**Tech Stack:** `anthropic>=0.34` SDK (async client), `pydantic` v2 for schemas, `asyncio.wait_for` for per-iteration + total-turn timeouts, existing PokerKit + storage layers unchanged.

**Spec sections covered:** §4.1 (Agent ABC), §4.2 simplified (Bounded ReAct minus utility branch), §4.3 (IterationRecord schema), §4.4 partial (LLMProvider ABC defined fully; only `complete()` implemented in 3a, others raise `NotImplementedError`), §6.1 (system prompt — hardcoded plain-text version, Jinja deferred to 3d).

**Out of scope (deferred to 3b–3e):** OpenAI / OpenRouter / LiteLLM, capability `probe()`, `extract_reasoning_artifact`, `serialize_assistant_turn` for thinking blocks, `ToolRunner` + utility tools (range parser / equity / pot odds / HUD stats), Jinja prompt templates, full 1000-hand cost run.

---

## Task 0: Branch + dependencies

**Files:**
- Modify: `pyproject.toml` (add anthropic dep)
- Modify: `.env.example` (file already exists from Phase 1 with Phase-4 stubs; rewrite for Phase 3a)
- Modify: `.gitignore` (verify `.env` already ignored; idempotent guard)

- [ ] **Step 1: Confirm clean working tree at HEAD**

```bash
git status --short
git log --oneline -1
```

Expected: working tree clean, HEAD = `c6e603e feat(view): add derived decision fields to PlayerView`.

- [ ] **Step 2: Add anthropic to pyproject.toml deps**

Open `pyproject.toml`, find the `[project.dependencies]` list, add `"anthropic>=0.34,<1.0",` after `"matplotlib>=3.8,<4.0",` (preserving alphabetical-ish order — actually `anthropic` should go first):

```toml
dependencies = [
    "anthropic>=0.34,<1.0",
    "duckdb>=1.0,<2.0",
    "matplotlib>=3.8,<4.0",
    "pokerkit>=0.7,<0.8",
    "pydantic>=2.0",
]
```

- [ ] **Step 3: Install the new dep into the existing venv**

```bash
.venv/bin/pip install -e .
.venv/bin/python -c "import anthropic; print(anthropic.__version__)"
```

Expected: a version `>= 0.34.0`.

- [ ] **Step 4: Rewrite `.env.example`**

The file already exists (Phase 1 commented-out stub for Phase 4). Open it and
replace its full contents with:

```
# Anthropic API key for LLMAgent integration tests + dogfood runs.
# DO NOT commit your real key. Local-only use.
ANTHROPIC_API_KEY=sk-ant-...

# Set to "1" to enable the gated integration test that hits the real
# Anthropic API. Default: skipped.
ANTHROPIC_INTEGRATION_TEST=
```

- [ ] **Step 5: Verify `.env` is in .gitignore (idempotent)**

```bash
grep -q "^\.env$" .gitignore && echo "ok" || echo ".env" >> .gitignore
```

The current `.gitignore` already has `.env` and `.env.local`, so this should
print `ok`. The `||` branch is the safety net.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example .gitignore
git commit -m "chore(deps): add anthropic SDK + .env.example for Phase 3a"
```

---

## Task 1: TurnDecisionResult + IterationRecord schemas

**Files:**
- Create: `src/llm_poker_arena/agents/llm/__init__.py`
- Create: `src/llm_poker_arena/agents/llm/types.py`
- Test: `tests/unit/test_llm_types.py`

**Why a new sub-package:** keeps LLM-specific machinery out of the existing `agents/` namespace so the Phase 1 sync agents (RandomAgent, RuleBasedAgent, HumanCLIAgent) stay reachable at their old import paths.

- [ ] **Step 1: Create empty `agents/llm/__init__.py`**

```bash
touch src/llm_poker_arena/agents/llm/__init__.py
```

- [ ] **Step 2: Write the failing tests for `TurnDecisionResult` schema**

Create `tests/unit/test_llm_types.py`:

```python
"""Tests for LLM agent dataclass schemas (Phase 3a)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from llm_poker_arena.agents.llm.types import (
    ApiErrorInfo,
    AssistantTurn,
    IterationRecord,
    LLMResponse,
    TokenCounts,
    ToolCall,
    TurnDecisionResult,
)
from llm_poker_arena.engine.legal_actions import Action


def test_token_counts_zero_default() -> None:
    z = TokenCounts.zero()
    assert z.input_tokens == 0
    assert z.output_tokens == 0
    assert z.cache_read_input_tokens == 0
    assert z.cache_creation_input_tokens == 0


def test_token_counts_addition() -> None:
    a = TokenCounts(input_tokens=10, output_tokens=20,
                    cache_read_input_tokens=5, cache_creation_input_tokens=0)
    b = TokenCounts(input_tokens=3, output_tokens=4,
                    cache_read_input_tokens=0, cache_creation_input_tokens=2)
    s = a + b
    assert s.input_tokens == 13
    assert s.output_tokens == 24
    assert s.cache_read_input_tokens == 5
    assert s.cache_creation_input_tokens == 2


def test_tool_call_round_trip() -> None:
    tc = ToolCall(name="fold", args={}, tool_use_id="toolu_01")
    assert ToolCall.model_validate(tc.model_dump()) == tc


def test_iteration_record_round_trip() -> None:
    ir = IterationRecord(
        step=1,
        request_messages_digest="sha256:abc",
        provider_response_kind="tool_use",
        tool_call=ToolCall(name="fold", args={}, tool_use_id="t1"),
        text_content="reasoning text",
        tokens=TokenCounts.zero(),
        wall_time_ms=42,
    )
    assert IterationRecord.model_validate(ir.model_dump()) == ir


def test_turn_decision_result_minimal_with_action() -> None:
    r = TurnDecisionResult(
        iterations=(),
        final_action=Action(tool_name="fold", args={}),
        total_tokens=TokenCounts.zero(),
        wall_time_ms=10,
        api_retry_count=0,
        illegal_action_retry_count=0,
        no_tool_retry_count=0,
        tool_usage_error_count=0,
        default_action_fallback=False,
        api_error=None,
        turn_timeout_exceeded=False,
    )
    assert r.final_action is not None
    assert r.final_action.tool_name == "fold"


def test_turn_decision_result_api_error_forbids_final_action() -> None:
    """spec §4.1 BR2-01: api_error != None ↔ final_action == None."""
    with pytest.raises(ValidationError, match="final_action must be None"):
        TurnDecisionResult(
            iterations=(),
            final_action=Action(tool_name="fold", args={}),
            total_tokens=TokenCounts.zero(),
            wall_time_ms=0,
            api_retry_count=1,
            illegal_action_retry_count=0,
            no_tool_retry_count=0,
            tool_usage_error_count=0,
            default_action_fallback=False,
            api_error=ApiErrorInfo(type="ProviderTransient", detail="500"),
            turn_timeout_exceeded=False,
        )


def test_turn_decision_result_is_frozen() -> None:
    r = TurnDecisionResult(
        iterations=(),
        final_action=Action(tool_name="check", args={}),
        total_tokens=TokenCounts.zero(),
        wall_time_ms=0,
        api_retry_count=0, illegal_action_retry_count=0,
        no_tool_retry_count=0, tool_usage_error_count=0,
        default_action_fallback=False, api_error=None,
        turn_timeout_exceeded=False,
    )
    with pytest.raises(ValidationError):
        r.wall_time_ms = 999  # type: ignore[misc]


def test_assistant_turn_preserves_blocks() -> None:
    """spec §4.4 BR2-07: assistant turn blocks must remain a tuple of opaque dicts."""
    at = AssistantTurn(
        provider="anthropic",
        blocks=({"type": "text", "text": "hi"},),
    )
    assert at.role == "assistant"
    assert at.blocks[0]["type"] == "text"


def test_llm_response_round_trip() -> None:
    resp = LLMResponse(
        provider="anthropic",
        model="claude-haiku-4-5",
        stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t1"),),
        text_content="",
        tokens=TokenCounts(input_tokens=100, output_tokens=10,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="anthropic", blocks=()),
    )
    assert LLMResponse.model_validate(resp.model_dump()) == resp


def test_turn_decision_result_json_round_trip() -> None:
    """End-to-end: TurnDecisionResult → JSON → back. Action is a stdlib
    dataclass (not a Pydantic BaseModel), so this proves Pydantic v2's
    dataclass-as-field-type serialization holds for the union with None."""
    r = TurnDecisionResult(
        iterations=(IterationRecord(
            step=1,
            request_messages_digest="sha256:abc123",
            provider_response_kind="tool_use",
            tool_call=ToolCall(name="raise_to", args={"amount": 300},
                               tool_use_id="t1"),
            text_content="reasoning",
            tokens=TokenCounts(input_tokens=50, output_tokens=20,
                               cache_read_input_tokens=10,
                               cache_creation_input_tokens=0),
            wall_time_ms=120,
        ),),
        final_action=Action(tool_name="raise_to", args={"amount": 300}),
        total_tokens=TokenCounts(input_tokens=50, output_tokens=20,
                                 cache_read_input_tokens=10,
                                 cache_creation_input_tokens=0),
        wall_time_ms=120,
        api_retry_count=0, illegal_action_retry_count=0,
        no_tool_retry_count=0, tool_usage_error_count=0,
        default_action_fallback=False,
        api_error=None,
        turn_timeout_exceeded=False,
    )
    blob = r.model_dump_json()
    restored = TurnDecisionResult.model_validate_json(blob)
    assert restored == r


def test_turn_decision_result_json_round_trip_with_api_error() -> None:
    """Censor path: api_error set, final_action=None, must round-trip cleanly."""
    r = TurnDecisionResult(
        iterations=(),
        final_action=None,
        total_tokens=TokenCounts.zero(),
        wall_time_ms=42,
        api_retry_count=1, illegal_action_retry_count=0,
        no_tool_retry_count=0, tool_usage_error_count=0,
        default_action_fallback=False,
        api_error=ApiErrorInfo(type="ProviderTransientError", detail="503"),
        turn_timeout_exceeded=False,
    )
    blob = r.model_dump_json()
    restored = TurnDecisionResult.model_validate_json(blob)
    assert restored == r
    assert restored.final_action is None
    assert restored.api_error is not None
```

- [ ] **Step 3: Run failing tests to confirm**

```bash
.venv/bin/pytest tests/unit/test_llm_types.py -v
```

Expected: ImportError (module doesn't exist yet) — collection error.

- [ ] **Step 4: Implement `agents/llm/types.py`**

```python
"""Pydantic dataclass schemas for LLM agent decision pipeline (spec §4.1, §4.3)."""
from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from llm_poker_arena.engine.legal_actions import Action


def _frozen() -> ConfigDict:
    return ConfigDict(extra="forbid", frozen=True)


class TokenCounts(BaseModel):
    """Provider-agnostic token usage. Anthropic-specific cache fields are
    plumbed through; OpenAI / others zero them in 3b adapters."""

    model_config = _frozen()

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int

    @classmethod
    def zero(cls) -> "TokenCounts":
        return cls(input_tokens=0, output_tokens=0,
                   cache_read_input_tokens=0, cache_creation_input_tokens=0)

    def __add__(self, other: "TokenCounts") -> "TokenCounts":
        return TokenCounts(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + other.cache_read_input_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens + other.cache_creation_input_tokens,
        )


class ToolCall(BaseModel):
    """A single tool call extracted from a provider response."""

    model_config = _frozen()

    name: str
    args: dict[str, Any]
    tool_use_id: str  # provider-assigned id, needed to thread tool_result back


class AssistantTurn(BaseModel):
    """spec §4.4 BR2-07: keep provider's content blocks intact for re-send.

    Phase 3a only stores them; thinking-block byte-identical re-send is 3b's job.
    """

    model_config = _frozen()

    provider: str
    blocks: tuple[dict[str, Any], ...]
    role: Literal["assistant"] = "assistant"


class LLMResponse(BaseModel):
    """Wire-level provider response, normalized for ReAct loop consumption."""

    model_config = _frozen()

    provider: str
    model: str
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "stop_sequence", "other"]
    tool_calls: tuple[ToolCall, ...]
    text_content: str
    tokens: TokenCounts
    raw_assistant_turn: AssistantTurn


class IterationRecord(BaseModel):
    """spec §4.3: one per ReAct loop iteration. Written into agent_view_snapshots."""

    model_config = _frozen()

    step: int
    request_messages_digest: str
    provider_response_kind: Literal["tool_use", "text_only", "error", "no_tool"]
    tool_call: ToolCall | None
    text_content: str
    tokens: TokenCounts
    wall_time_ms: int


class ApiErrorInfo(BaseModel):
    model_config = _frozen()

    type: str
    detail: str


class TurnDecisionResult(BaseModel):
    """spec §4.1: complete decision record returned by Agent.decide()."""

    model_config = _frozen()

    iterations: tuple[IterationRecord, ...]
    final_action: Action | None
    total_tokens: TokenCounts
    wall_time_ms: int

    api_retry_count: int
    illegal_action_retry_count: int
    no_tool_retry_count: int
    tool_usage_error_count: int

    default_action_fallback: bool
    api_error: ApiErrorInfo | None
    turn_timeout_exceeded: bool

    @model_validator(mode="after")
    def _api_error_forbids_action(self) -> Self:
        """spec §4.1 BR2-01: api_error != None ⇒ final_action == None."""
        if self.api_error is not None and self.final_action is not None:
            raise ValueError(
                "final_action must be None when api_error is set "
                "(spec §4.1 BR2-01: censor hand on api_error)"
            )
        return self
```

Note `Action` does NOT inherit from `BaseModel` (it's a dataclass in `engine/legal_actions.py`). Pydantic accepts dataclasses as field types as long as Pydantic can serialize them. If serialization breaks, switch to `Action` field type with `arbitrary_types_allowed=True` in `ConfigDict`.

- [ ] **Step 5: Run tests to verify pass**

```bash
.venv/bin/pytest tests/unit/test_llm_types.py -v
```

Expected: 11 passed. If any fail because Pydantic can't serialize `Action`, fix `_frozen()` to include `arbitrary_types_allowed=True` AND drop `extra="forbid"` for fields with `Action` type only if Pydantic still complains; otherwise convert `Action` from stdlib `@dataclass(frozen=True)` to a Pydantic BaseModel in `engine/legal_actions.py` (preserve all current usages).

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/agents/llm/__init__.py src/llm_poker_arena/agents/llm/types.py tests/unit/test_llm_types.py
git commit -m "feat(agents): TurnDecisionResult + IterationRecord schemas (spec §4.1, §4.3)"
```

---

## Task 2: validate_action pure function

**Files:**
- Modify: `src/llm_poker_arena/engine/legal_actions.py` (add `validate_action`)
- Test: `tests/unit/test_validate_action.py`

**Why:** spec §4.1 ToolRunner has `validate_action(name, args)`; we deliver the function but skip the wrapper class (3c builds ToolRunner). LLMAgent calls `validate_action(view, action)` directly.

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_validate_action.py`:

```python
"""Tests for validate_action pure function (Phase 3a)."""
from __future__ import annotations

from llm_poker_arena.engine.legal_actions import (
    Action,
    ValidationResult,
    validate_action,
)
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.engine.types import Street


def _params() -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=False, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _seats() -> tuple[SeatPublicInfo, ...]:
    return tuple(
        SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                       position_full="x", stack=10_000,
                       invested_this_hand=0, invested_this_round=0,
                       status="in_hand")
        for i in range(6)
    )


def _view(legal: LegalActionSet) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=0.4, effective_stack=10_000,
        seats_public=_seats(), opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=legal, opponent_stats={},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=_params(),
    )


def test_validate_action_accepts_legal_fold() -> None:
    legal = LegalActionSet(tools=(
        ActionToolSpec(name="fold", args={}),
        ActionToolSpec(name="call", args={}),
    ))
    r = validate_action(_view(legal), Action(tool_name="fold", args={}))
    assert r.is_valid
    assert r.reason is None


def test_validate_action_rejects_unknown_tool() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    r = validate_action(_view(legal), Action(tool_name="raise_to", args={"amount": 200}))
    assert not r.is_valid
    assert r.reason is not None
    assert "raise_to" in r.reason


def test_validate_action_accepts_raise_within_bounds() -> None:
    legal = LegalActionSet(tools=(
        ActionToolSpec(name="raise_to",
                       args={"amount": {"min": 200, "max": 10_000}}),
    ))
    r = validate_action(_view(legal), Action(tool_name="raise_to", args={"amount": 500}))
    assert r.is_valid


def test_validate_action_rejects_raise_below_min() -> None:
    legal = LegalActionSet(tools=(
        ActionToolSpec(name="raise_to",
                       args={"amount": {"min": 200, "max": 10_000}}),
    ))
    r = validate_action(_view(legal), Action(tool_name="raise_to", args={"amount": 150}))
    assert not r.is_valid
    assert "min" in (r.reason or "").lower() or "200" in (r.reason or "")


def test_validate_action_rejects_raise_above_max() -> None:
    legal = LegalActionSet(tools=(
        ActionToolSpec(name="raise_to",
                       args={"amount": {"min": 200, "max": 10_000}}),
    ))
    r = validate_action(_view(legal), Action(tool_name="raise_to", args={"amount": 12_000}))
    assert not r.is_valid


def test_validate_action_rejects_raise_missing_amount() -> None:
    legal = LegalActionSet(tools=(
        ActionToolSpec(name="raise_to",
                       args={"amount": {"min": 200, "max": 10_000}}),
    ))
    r = validate_action(_view(legal), Action(tool_name="raise_to", args={}))
    assert not r.is_valid
    assert "amount" in (r.reason or "").lower()


def test_validate_action_accepts_check_no_args() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="check", args={}),))
    r = validate_action(_view(legal), Action(tool_name="check", args={}))
    assert r.is_valid
```

- [ ] **Step 2: Confirm test fails**

```bash
.venv/bin/pytest tests/unit/test_validate_action.py -v
```

Expected: ImportError (validate_action / ValidationResult don't exist).

- [ ] **Step 3: Check whether ValidationResult already exists**

```bash
grep -n "class ValidationResult\|ValidationResult" src/llm_poker_arena/engine/legal_actions.py src/llm_poker_arena/engine/transition.py
```

If `ValidationResult` exists in `transition.py`, import it from there in legal_actions. If not, define it new in legal_actions.

- [ ] **Step 4: Implement validate_action in `legal_actions.py`**

If `ValidationResult` doesn't exist anywhere, add this near the top of the file (after the existing `Action` dataclass):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    """Result of a dry-run action legality check (no engine state mutation)."""

    is_valid: bool
    reason: str | None = None
```

Then add the function at the bottom of the file:

```python
def validate_action(view: "PlayerView", action: "Action") -> ValidationResult:
    """Check whether `action` is legal for `view` without touching engine state.

    Mirrors the legality criteria PokerKit will apply in `apply_action`,
    derived from `view.legal_actions`. Used by LLMAgent to short-circuit
    illegal-action retries without wasting an engine round-trip.

    Phase 3a contract:
      - tool_name must appear in view.legal_actions.tools
      - bet/raise_to actions must include `args["amount"]` and that integer
        must be in the inclusive range advertised by the tool spec.
      - fold/check/call/all_in actions must have `args == {}`.
    """
    legal_specs = {t.name: t for t in view.legal_actions.tools}
    spec = legal_specs.get(action.tool_name)
    if spec is None:
        return ValidationResult(
            is_valid=False,
            reason=(
                f"action {action.tool_name!r} not in legal set for this turn "
                f"(legal: {sorted(legal_specs.keys())})"
            ),
        )

    if action.tool_name in ("bet", "raise_to"):
        amount_obj = action.args.get("amount") if isinstance(action.args, dict) else None
        if amount_obj is None:
            return ValidationResult(
                is_valid=False,
                reason=f"{action.tool_name} requires args['amount'] (got {action.args!r})",
            )
        try:
            amount = int(amount_obj)
        except (TypeError, ValueError):
            return ValidationResult(
                is_valid=False,
                reason=f"{action.tool_name} amount must be int, got {amount_obj!r}",
            )
        bounds = spec.args.get("amount") if isinstance(spec.args, dict) else None
        if isinstance(bounds, dict) and "min" in bounds and "max" in bounds:
            mn, mx = int(bounds["min"]), int(bounds["max"])
            if amount < mn:
                return ValidationResult(
                    is_valid=False,
                    reason=f"{action.tool_name} amount {amount} < min {mn}",
                )
            if amount > mx:
                return ValidationResult(
                    is_valid=False,
                    reason=f"{action.tool_name} amount {amount} > max {mx}",
                )
        return ValidationResult(is_valid=True)

    # fold / check / call / all_in: must have empty args
    if action.args:
        return ValidationResult(
            is_valid=False,
            reason=f"{action.tool_name} takes no args (got {action.args!r})",
        )
    return ValidationResult(is_valid=True)
```

Use `TYPE_CHECKING` import for `PlayerView` to avoid circular imports:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm_poker_arena.engine.views import PlayerView
```

- [ ] **Step 5: Verify tests pass**

```bash
.venv/bin/pytest tests/unit/test_validate_action.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/engine/legal_actions.py tests/unit/test_validate_action.py
git commit -m "feat(engine): validate_action pure function — dry-run legality check for LLMAgent"
```

---

## Task 3: LLMProvider ABC + MockLLMProvider

**Files:**
- Create: `src/llm_poker_arena/agents/llm/provider_base.py`
- Create: `src/llm_poker_arena/agents/llm/providers/__init__.py`
- Create: `src/llm_poker_arena/agents/llm/providers/mock.py`
- Test: `tests/unit/test_mock_llm_provider.py`

- [ ] **Step 1: Create empty `providers/__init__.py`**

```bash
touch src/llm_poker_arena/agents/llm/providers/__init__.py
```

- [ ] **Step 2: Write failing tests for MockLLMProvider**

Create `tests/unit/test_mock_llm_provider.py`:

```python
"""Tests for MockLLMProvider — preset-driven LLM stub for ReAct loop tests."""
from __future__ import annotations

import pytest

from llm_poker_arena.agents.llm.provider_base import (
    LLMProvider,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    TokenCounts,
    ToolCall,
)


@pytest.mark.asyncio
async def test_mock_provider_returns_scripted_responses_in_order() -> None:
    script = MockResponseScript(responses=(
        LLMResponse(
            provider="mock", model="m1", stop_reason="tool_use",
            tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t1"),),
            text_content="", tokens=TokenCounts.zero(),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        ),
        LLMResponse(
            provider="mock", model="m1", stop_reason="tool_use",
            tool_calls=(ToolCall(name="check", args={}, tool_use_id="t2"),),
            text_content="", tokens=TokenCounts.zero(),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        ),
    ))
    p = MockLLMProvider(script=script)
    r1 = await p.complete(messages=[], tools=[], temperature=0.7, seed=None)
    r2 = await p.complete(messages=[], tools=[], temperature=0.7, seed=None)
    assert r1.tool_calls[0].name == "fold"
    assert r2.tool_calls[0].name == "check"


@pytest.mark.asyncio
async def test_mock_provider_raises_when_script_exhausted() -> None:
    script = MockResponseScript(responses=())
    p = MockLLMProvider(script=script)
    with pytest.raises(RuntimeError, match="exhausted"):
        await p.complete(messages=[], tools=[], temperature=0.7, seed=None)


@pytest.mark.asyncio
async def test_mock_provider_raises_transient_error_when_scripted() -> None:
    script = MockResponseScript(
        responses=(),
        errors_at_step={0: ProviderTransientError("simulated 500")},
    )
    p = MockLLMProvider(script=script)
    with pytest.raises(ProviderTransientError, match="simulated 500"):
        await p.complete(messages=[], tools=[], temperature=0.7, seed=None)


@pytest.mark.asyncio
async def test_mock_provider_provider_name() -> None:
    script = MockResponseScript(responses=())
    p = MockLLMProvider(script=script)
    assert p.provider_name() == "mock"


def test_mock_provider_is_an_llm_provider() -> None:
    """Type check: MockLLMProvider implements LLMProvider ABC."""
    script = MockResponseScript(responses=())
    p = MockLLMProvider(script=script)
    assert isinstance(p, LLMProvider)
```

Add `pytest-asyncio` to test deps if not already present (check `pyproject.toml`):

```bash
grep -n "pytest-asyncio" pyproject.toml
```

If absent, add `"pytest-asyncio>=0.23",` to `[project.optional-dependencies].dev` and run `.venv/bin/pip install -e ".[dev]"`.

- [ ] **Step 3: Confirm tests fail**

```bash
.venv/bin/pytest tests/unit/test_mock_llm_provider.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement `provider_base.py`**

```python
"""LLMProvider ABC (spec §4.4). Phase 3a fully defines the interface; only
`complete()` and `provider_name()` get implemented. The other abstract
methods raise NotImplementedError in 3a and are flesh-filled in 3b.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
)


class ProviderTransientError(Exception):
    """Raised by providers for retryable wire errors (HTTP 5xx, rate limit, timeout).

    LLMAgent's ReAct loop catches this and consumes one api_retry slot.
    """


class ProviderPermanentError(Exception):
    """Raised by providers for non-retryable errors (auth fail, bad request).

    LLMAgent does NOT retry; the hand is censored via api_error.
    """


class LLMProvider(ABC):
    """Wire-level adapter for a specific LLM API (Anthropic, OpenAI, ...)."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        """Send a request to the provider and return a normalized LLMResponse.

        Raises ProviderTransientError on retryable failure;
        ProviderPermanentError on non-retryable.
        """

    @abstractmethod
    def provider_name(self) -> str:
        """Stable provider identifier, e.g. 'anthropic'."""

    def serialize_assistant_turn(self, response: LLMResponse) -> AssistantTurn:
        """spec §4.4 BR2-07: re-serialize provider response as assistant message
        so the next round can include it. Phase 3a default: return the raw
        AssistantTurn untouched (Anthropic thinking-block byte-identical
        preservation lands in 3b).
        """
        return response.raw_assistant_turn

    def extract_reasoning_artifact(self, response: LLMResponse) -> Any:  # noqa: ANN401
        """spec §4.4: provider-specific reasoning extraction. 3a stub."""
        raise NotImplementedError("Phase 3b feature — reasoning artifact extraction")

    async def probe(self) -> Any:  # noqa: ANN401
        """spec §4.4 HR2-03: live capability probe. 3a stub."""
        raise NotImplementedError("Phase 3b feature — capability probe")
```

- [ ] **Step 5: Implement `providers/mock.py`**

```python
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
```

- [ ] **Step 6: Verify tests pass**

```bash
.venv/bin/pytest tests/unit/test_mock_llm_provider.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/agents/llm/provider_base.py src/llm_poker_arena/agents/llm/providers/__init__.py src/llm_poker_arena/agents/llm/providers/mock.py tests/unit/test_mock_llm_provider.py
git commit -m "feat(agents): LLMProvider ABC + MockLLMProvider for ReAct testing (spec §4.4)"
```

---

## Task 4: AnthropicProvider (real wire impl, monkeypatch-tested)

**Files:**
- Create: `src/llm_poker_arena/agents/llm/providers/anthropic_provider.py`
- Test: `tests/unit/test_anthropic_provider.py`

**Why monkeypatch the SDK:** unit tests must not hit the real API. Integration test (Task 9) uses the real API gated by env var.

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_anthropic_provider.py`:

```python
"""Tests for AnthropicProvider — Anthropic SDK adapter.

Unit tests monkeypatch `anthropic.AsyncAnthropic` so no network calls happen.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_poker_arena.agents.llm.provider_base import (
    ProviderPermanentError,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)


def _fake_anthropic_response(
    *, stop_reason: str = "tool_use", content_blocks: list[Any] | None = None,
    input_tokens: int = 100, output_tokens: int = 25,
) -> MagicMock:
    """Build a MagicMock that quacks like anthropic.types.Message."""
    msg = MagicMock()
    msg.stop_reason = stop_reason
    msg.model = "claude-haiku-4-5"
    msg.content = content_blocks or []
    msg.usage = MagicMock(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return msg


@pytest.mark.asyncio
async def test_anthropic_provider_normalizes_tool_use_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "fold"
    tool_block.input = {}
    tool_block.id = "toolu_01abc"
    tool_block.model_dump = lambda: {"type": "tool_use", "name": "fold", "input": {}, "id": "toolu_01abc"}
    fake = _fake_anthropic_response(content_blocks=[tool_block])

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake)
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    resp = await p.complete(
        messages=[{"role": "user", "content": "play"}],
        tools=[{"name": "fold", "description": "fold", "input_schema": {"type": "object"}}],
        temperature=0.7, seed=None,
    )
    assert resp.provider == "anthropic"
    assert resp.stop_reason == "tool_use"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "fold"
    assert resp.tool_calls[0].tool_use_id == "toolu_01abc"
    assert resp.tokens.input_tokens == 100
    assert resp.tokens.output_tokens == 25


@pytest.mark.asyncio
async def test_anthropic_provider_normalizes_text_only_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I think I should fold here."
    text_block.model_dump = lambda: {"type": "text", "text": "I think I should fold here."}
    fake = _fake_anthropic_response(stop_reason="end_turn", content_blocks=[text_block])

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake)
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    resp = await p.complete(
        messages=[{"role": "user", "content": "play"}],
        tools=[],
        temperature=0.7, seed=None,
    )
    assert resp.stop_reason == "end_turn"
    assert resp.tool_calls == ()
    assert "fold" in resp.text_content


@pytest.mark.asyncio
async def test_anthropic_provider_translates_503_to_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anthropic

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(
        side_effect=anthropic.APIStatusError(
            "503 service unavailable",
            response=MagicMock(status_code=503),
            body=None,
        )
    )
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    with pytest.raises(ProviderTransientError):
        await p.complete(messages=[], tools=[], temperature=0.7, seed=None)


@pytest.mark.asyncio
async def test_anthropic_provider_translates_400_to_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anthropic

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(
        side_effect=anthropic.APIStatusError(
            "400 invalid request",
            response=MagicMock(status_code=400),
            body=None,
        )
    )
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    with pytest.raises(ProviderPermanentError):
        await p.complete(messages=[], tools=[], temperature=0.7, seed=None)


def test_anthropic_provider_provider_name() -> None:
    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    assert p.provider_name() == "anthropic"
```

- [ ] **Step 2: Confirm tests fail**

```bash
.venv/bin/pytest tests/unit/test_anthropic_provider.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `anthropic_provider.py`**

```python
"""AnthropicProvider — adapter for Anthropic Claude via the official SDK.

Phase 3a scope: send messages + tools, normalize response into LLMResponse,
translate APIStatusError into transient (5xx, 429) or permanent (4xx).

Out of scope (3b): extended-thinking blocks, capability probe, system prompt
caching headers.
"""
from __future__ import annotations

from typing import Any

from anthropic import APIStatusError, APITimeoutError, AsyncAnthropic, RateLimitError

from llm_poker_arena.agents.llm.provider_base import (
    LLMProvider,
    ProviderPermanentError,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
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
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=temperature,
                messages=messages,
                tools=tools or None,
            )
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
            stop_reason=stop_reason,
            tool_calls=tuple(tool_calls),
            text_content="".join(text_parts),
            tokens=tokens,
            raw_assistant_turn=AssistantTurn(
                provider="anthropic", blocks=tuple(raw_blocks),
            ),
        )


__all__ = ["AnthropicProvider"]
```

- [ ] **Step 4: Verify tests pass**

```bash
.venv/bin/pytest tests/unit/test_anthropic_provider.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/llm_poker_arena/agents/llm/providers/anthropic_provider.py tests/unit/test_anthropic_provider.py
git commit -m "feat(agents): AnthropicProvider — Claude SDK adapter (spec §4.4 partial)"
```

---

## Task 5: Async Agent ABC migration

**Files:**
- Modify: `src/llm_poker_arena/agents/base.py`
- Modify: `src/llm_poker_arena/agents/random_agent.py`
- Modify: `src/llm_poker_arena/agents/rule_based.py`
- Modify: `src/llm_poker_arena/agents/human_cli.py`
- Modify: `src/llm_poker_arena/engine/_internal/rebuy.py` (sync→async bridge)
- Modify: many test files in `tests/unit/` and `tests/property/` calling `agent.decide()`
- Test: `tests/unit/test_async_agent_abc.py`

**Why a single big task:** the ABC change is breaking; all 3 existing agents must move at once. Doing this in one commit keeps the suite green at every checkpoint.

- [ ] **Step 1: Write failing test that asserts new ABC shape**

Create `tests/unit/test_async_agent_abc.py`:

```python
"""Tests for the Phase 3a async Agent ABC migration."""
from __future__ import annotations

import asyncio
import inspect

import pytest

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.agents.llm.types import TurnDecisionResult


def test_agent_decide_is_async() -> None:
    """spec §4.1: Agent.decide must be a coroutine function."""
    assert inspect.iscoroutinefunction(Agent.decide)


def test_random_agent_decide_returns_turn_decision_result() -> None:
    from tests.unit.test_random_agent import _seats, _params  # reuse fixture
    from llm_poker_arena.engine.views import (
        ActionToolSpec, LegalActionSet, PlayerView,
    )
    from llm_poker_arena.engine.types import Street

    legal = LegalActionSet(tools=(
        ActionToolSpec(name="fold", args={}),
        ActionToolSpec(name="call", args={}),
    ))
    view = PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=0.4, effective_stack=10_000,
        seats_public=_seats(), opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=legal, opponent_stats={},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=_params(),
    )

    agent = RandomAgent()
    result: TurnDecisionResult = asyncio.run(agent.decide(view))
    assert isinstance(result, TurnDecisionResult)
    assert result.final_action is not None
    assert result.final_action.tool_name in {"fold", "call"}
    assert result.iterations == ()
    assert result.api_error is None
    assert result.default_action_fallback is False


def test_rule_based_agent_returns_turn_decision_result() -> None:
    from tests.unit.test_rule_based_agent import _view  # reuse fixture
    agent = RuleBasedAgent()
    view = _view(hole=("As", "Ad"))  # AA, premium
    result = asyncio.run(agent.decide(view))
    assert isinstance(result, TurnDecisionResult)
    assert result.final_action is not None
    assert result.final_action.tool_name == "raise_to"


def test_human_cli_agent_keeps_input_io_contract() -> None:
    """HumanCLIAgent must still accept input/output streams in __init__."""
    import io
    from llm_poker_arena.agents.human_cli import HumanCLIAgent
    a = HumanCLIAgent(input_stream=io.StringIO("fold\n"), output_stream=io.StringIO())
    assert a.provider_id() == "human:cli_v1"
```

- [ ] **Step 2: Confirm tests fail**

```bash
.venv/bin/pytest tests/unit/test_async_agent_abc.py -v
```

Expected: failures because `Agent.decide` is sync and returns `Action`, not async returning `TurnDecisionResult`.

- [ ] **Step 3: Update `base.py`**

Replace contents of `src/llm_poker_arena/agents/base.py`:

```python
"""Async Agent ABC (spec §4.1, Phase 3a)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from llm_poker_arena.agents.llm.types import TurnDecisionResult
from llm_poker_arena.engine.views import PlayerView


class Agent(ABC):
    """Phase 3 contract: every agent returns a complete decision record.

    Sync agents (RandomAgent / RuleBasedAgent / HumanCLIAgent) implement
    decide() as `async def` and return a TurnDecisionResult with a single
    final_action and empty iterations / zero retries. LLMAgent populates
    iterations + retry counters during ReAct.
    """

    @abstractmethod
    async def decide(self, view: PlayerView) -> TurnDecisionResult:
        """Return a TurnDecisionResult for the given view. May not raise."""

    @abstractmethod
    def provider_id(self) -> str: ...
```

- [ ] **Step 4: Update `random_agent.py`**

Replace decide() body:

```python
"""RandomAgent: uniform sampling over legal actions. Deterministic in turn_seed."""
from __future__ import annotations

import random

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import TokenCounts, TurnDecisionResult
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.views import PlayerView


class RandomAgent(Agent):
    async def decide(self, view: PlayerView) -> TurnDecisionResult:
        rng = random.Random(view.turn_seed)
        tools = view.legal_actions.tools
        if not tools:
            action = Action(tool_name="fold", args={})
        else:
            spec = rng.choice(tools)
            if spec.name in ("bet", "raise_to"):
                bounds = spec.args["amount"]
                mn, mx = int(bounds["min"]), int(bounds["max"])
                action = Action(tool_name=spec.name,
                                args={"amount": rng.randint(mn, mx)})
            else:
                action = Action(tool_name=spec.name, args={})
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

    def provider_id(self) -> str:
        return "random:uniform"
```

- [ ] **Step 5: Update `rule_based.py`**

Wrap the existing sync logic. The existing `decide` body becomes a private `_pick_action` method; the public `decide` is `async` and wraps the result:

Locate the `class RuleBasedAgent(Agent):` block, replace just the public `decide` method:

```python
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
        legal: set[str] = {str(t.name) for t in view.legal_actions.tools}
        bb = view.immutable_session_params.bb
        to_call = view.current_bet_to_match - view.my_invested_this_round
        is_preflop = view.street == Street.PREFLOP

        if is_preflop:
            return self._preflop(view, legal, bb, to_call)
        return self._postflop(view, legal, to_call)
```

Add the imports at the top (TokenCounts, TurnDecisionResult). The existing `_preflop`, `_postflop`, `_safe_check_or_fold`, `_safe_fold_or_check` methods do not need to change.

- [ ] **Step 6: Update `human_cli.py`**

Same pattern — wrap synchronous I/O in async decide:

Find the `decide()` method in `HumanCLIAgent`, rename existing body to `_pick_action`, wrap public `decide` async returning `TurnDecisionResult`:

```python
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
        # ... existing decide() body unchanged ...
```

- [ ] **Step 7: Update `rebuy.py:95` — sync helper bridges to async agents**

`run_single_hand` is a Phase-1 helper still called by 8 property/integration
test files (test_rebuy, test_integration_thousand_hands, test_auto_rebuy,
test_card_conservation, test_chip_conservation, test_stress_50k_sequences,
test_min_raise_reopen, test_playerview_projection_pure). Migrating all 8
to async is out of scope for 3a; instead keep `run_single_hand` sync and
bridge to the async `agent.decide` internally with `asyncio.run`:

Open `src/llm_poker_arena/engine/_internal/rebuy.py`. Add `import asyncio` at
the top. Locate the action-loop body around line 95 — currently:

```python
action = agents[actor].decide(view)
```

Replace with:

```python
decision = asyncio.run(agents[actor].decide(view))
if decision.api_error is not None or decision.final_action is None:
    raise RuntimeError(
        f"agent at seat {actor} returned api_error or null final_action: "
        f"{decision.api_error!r}. The Phase-1 `run_single_hand` helper does "
        f"not implement censor; use `Session` if your agents may emit api_error."
    )
action = decision.final_action
```

This preserves `run_single_hand`'s sync interface (so the 8 caller test files
need no change) while letting it accept the new async `Agent` ABC.

Caveat: `asyncio.run` cannot nest. If any caller of `run_single_hand` ever
runs inside an existing event loop, it will fail with "asyncio.run() cannot
be called from a running event loop". As of HEAD c6e603e, no caller does.
If a future test wraps `run_single_hand` in `asyncio.run`, it must be moved
to use `Session` instead.

- [ ] **Step 8: Update test files calling `agent.decide(view)` synchronously**

Find every test that does `agent.decide(view)`:

```bash
grep -rn "\.decide(" tests/ --include="*.py" | grep -v "_pick_action"
```

For each call site that previously returned an `Action` directly, wrap with `asyncio.run(...)` and read `.final_action`:

```python
# Before:
action = agent.decide(view)
assert action.tool_name == "fold"

# After:
result = asyncio.run(agent.decide(view))
assert result.final_action is not None
assert result.final_action.tool_name == "fold"
```

The candidate files (from current grep):
- `tests/unit/test_random_agent.py` — multiple decide() calls
- `tests/unit/test_rule_based_agent.py` — multiple decide() calls
- `tests/unit/test_human_cli_agent.py` — multiple decide() calls

Update each one carefully, preserving the test's intent. Add `import asyncio` to each file's imports.

- [ ] **Step 9: Run the full agent test subset**

```bash
.venv/bin/pytest tests/unit/test_random_agent.py tests/unit/test_rule_based_agent.py tests/unit/test_human_cli_agent.py tests/unit/test_async_agent_abc.py tests/unit/test_rebuy.py tests/property/ -v
```

Expected: all green. The property/ folder uses `run_single_hand` heavily; if any property test fails with "RuntimeError: cannot be called from a running event loop", that means a test is itself wrapping `run_single_hand` in `asyncio.run` — investigate the specific test (none exist as of HEAD c6e603e).

- [ ] **Step 10: Run the FULL suite to find any other breakage**

```bash
.venv/bin/pytest tests/ 2>&1 | tail -20
```

Address any new failures. Likely culprits: integration tests that use Session (Task 6 will fix Session itself but the existing integration tests may already break here because Session calls `agent.decide()` synchronously). If integration tests fail, mark them with `pytest.skip("Phase 3a Task 6 will fix Session async migration")` — they unblock in Task 6.

- [ ] **Step 11: Commit**

```bash
git add src/llm_poker_arena/agents/base.py src/llm_poker_arena/agents/random_agent.py src/llm_poker_arena/agents/rule_based.py src/llm_poker_arena/agents/human_cli.py tests/unit/
git commit -m "refactor(agents): widen Agent ABC to async decide() -> TurnDecisionResult (spec §4.1)"
```

---

## Task 6: Session async migration

**Files:**
- Modify: `src/llm_poker_arena/session/session.py`
- Modify: `src/llm_poker_arena/cli/play.py` (poker-play entry point uses Session)
- Modify: `src/llm_poker_arena/storage/layer_builders.py` (build_agent_view_snapshot signature)
- Modify: `src/llm_poker_arena/analysis/baseline.py` (run_random_baseline + run_rule_based_baseline call `.run()`)
- Test: `tests/unit/test_session_async.py`

- [ ] **Step 1: Write failing test asserting Session.run is async-callable**

Create `tests/unit/test_session_async.py`:

```python
"""Tests for Session async migration (Phase 3a Task 6)."""
from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _cfg() -> SessionConfig:
    return SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )


def test_session_run_is_a_coroutine_function() -> None:
    """Session.run must be `async def` after Phase 3a Task 6."""
    assert inspect.iscoroutinefunction(Session.run)


def test_session_run_completes_via_asyncio_run(tmp_path: Path) -> None:
    cfg = _cfg()
    agents = [RuleBasedAgent() if i % 2 == 0 else RandomAgent() for i in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="async_test")
    asyncio.run(sess.run())
    # Standard 4 artifacts present
    for fname in ("canonical_private.jsonl", "public_replay.jsonl",
                  "agent_view_snapshots.jsonl", "meta.json"):
        assert (tmp_path / fname).exists()
        assert (tmp_path / fname).stat().st_size > 0


def test_session_writes_iterations_field_in_snapshots(tmp_path: Path) -> None:
    """spec §7.4: iterations field must exist in agent_view_snapshots."""
    cfg = _cfg()
    agents = [RuleBasedAgent() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="iter_test")
    asyncio.run(sess.run())
    line = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()[0]
    rec = json.loads(line)
    # For non-LLM agents, iterations is empty tuple → JSON empty list.
    assert "iterations" in rec
    assert rec["iterations"] == []
```

- [ ] **Step 2: Confirm tests fail**

```bash
.venv/bin/pytest tests/unit/test_session_async.py -v
```

Expected: fails because `Session.run` is sync.

- [ ] **Step 3: Modify `session/session.py`**

Open `src/llm_poker_arena/session/session.py` and apply these surgical edits:

Find the `def run(self) -> None:` line and change to `async def run(self) -> None:`.

Find the `def _run_one_hand(self, hand_id: int) -> None:` line and change to `async def _run_one_hand(self, hand_id: int) -> None:`.

In the `run()` body, change `self._run_one_hand(hand_id)` to `await self._run_one_hand(hand_id)`.

In `_run_one_hand`, find the `chosen = self._agents[actor].decide(view)` line. This now returns a `TurnDecisionResult`, not an `Action`. Replace with:

```python
            decision = await self._agents[actor].decide(view)
            if decision.api_error is not None or decision.final_action is None:
                # spec §4.1 BR2-01: censor hand on api_error.
                # Phase 3a: log and break out of the hand loop; later phases
                # write a 'censored' marker into public_replay.
                self._record_censored_hand(
                    hand_id=hand_id, seat=actor, reason=decision.api_error,
                )
                return
            chosen = decision.final_action
            fallback = decision.default_action_fallback
            iterations_for_snapshot = decision.iterations
            total_tokens_for_snapshot = decision.total_tokens
            wall_time_ms_for_snapshot = decision.wall_time_ms
            api_retry_count = decision.api_retry_count
            illegal_action_retry_count = decision.illegal_action_retry_count
            no_tool_retry_count = decision.no_tool_retry_count
            tool_usage_error_count = decision.tool_usage_error_count
```

Remove the old fallback path (`if not result.is_valid: fallback = True; chosen = default_safe_action(view); ...`); the agent now reports fallback itself via `default_action_fallback`. The engine still calls `apply_action` and asserts validity — if it's still illegal, raise; that'd be an agent bug, not a fallback case:

```python
            result = apply_action(state, actor, chosen)
            if not result.is_valid:
                raise RuntimeError(
                    f"agent at seat {actor} returned action {chosen!r} "
                    f"that pokerkit rejected: {result.reason}. "
                    f"This is an agent contract violation."
                )
```

Update `build_agent_view_snapshot()` call to thread the new fields. Currently it passes hardcoded zeros for retry counts and tokens; update those args to read from the decision:

```python
            snapshot = build_agent_view_snapshot(
                hand_id=hand_id, session_id=self._session_id, seat=actor,
                street=street, timestamp=_now_iso(), view=view,
                action=chosen, turn_index=turn_counter,
                agent_provider=provider, agent_model=model,
                agent_version="phase3a",
                default_action_fallback=fallback,
                iterations=iterations_for_snapshot,
                total_tokens=total_tokens_for_snapshot,
                wall_time_ms=wall_time_ms_for_snapshot,
                api_retry_count=api_retry_count,
                illegal_action_retry_count=illegal_action_retry_count,
                no_tool_retry_count=no_tool_retry_count,
                tool_usage_error_count=tool_usage_error_count,
            )
```

Add the `_record_censored_hand` helper method:

```python
    def _record_censored_hand(
        self, *, hand_id: int, seat: int, reason: object,
    ) -> None:
        """Phase 3a stub: print a warning. 3d adds proper censor record."""
        print(
            f"[SESSION] hand {hand_id} censored: agent at seat {seat} "
            f"returned api_error or null final_action ({reason!r}). "
            f"No action applied; hand abandoned.",
            flush=True,
        )
```

- [ ] **Step 4: Update `build_agent_view_snapshot` signature**

Open `src/llm_poker_arena/storage/layer_builders.py`. Add these imports near
the existing import block:

```python
from collections.abc import Mapping
from typing import cast

from llm_poker_arena.agents.llm.types import IterationRecord, TokenCounts
```

Locate `build_agent_view_snapshot`. Add the new kwargs with mypy-strict-safe
typing (no bare `tuple`, no `object` that gets `dict()`-ed):

```python
def build_agent_view_snapshot(
    *, hand_id: int, session_id: str, seat: int, street: Street,
    timestamp: str, view: PlayerView, action: Action, turn_index: int,
    agent_provider: str, agent_model: str, agent_version: str,
    default_action_fallback: bool,
    iterations: tuple[IterationRecord, ...] = (),
    total_tokens: TokenCounts | Mapping[str, int] | None = None,
    wall_time_ms: int = 0,
    api_retry_count: int = 0,
    illegal_action_retry_count: int = 0,
    no_tool_retry_count: int = 0,
    tool_usage_error_count: int = 0,
) -> AgentViewSnapshot:
```

Inside the function body, populate the new AgentViewSnapshot fields. The
`cast(Any, ...)` is needed because mypy --strict cannot prove `model_dump`
exists at the union-type level even though `IterationRecord` and
`TokenCounts` are both Pydantic BaseModels:

```python
    iter_dump: tuple[dict[str, Any], ...] = tuple(
        cast("Any", ir).model_dump(mode="json") for ir in iterations
    )
    if total_tokens is None:
        total_tokens_dict: dict[str, int] = {}
    elif isinstance(total_tokens, TokenCounts):
        total_tokens_dict = cast("dict[str, int]",
                                 total_tokens.model_dump(mode="json"))
    else:
        total_tokens_dict = dict(total_tokens)
    return AgentViewSnapshot(
        # ... existing fields ...
        iterations=iter_dump,
        total_tokens=total_tokens_dict,
        wall_time_ms=wall_time_ms,
        api_retry_count=api_retry_count,
        illegal_action_retry_count=illegal_action_retry_count,
        no_tool_retry_count=no_tool_retry_count,
        tool_usage_error_count=tool_usage_error_count,
        default_action_fallback=default_action_fallback,
        # ... etc ...
    )
```

If the existing `AgentViewSnapshot` field declaration in `storage/schemas.py`
types `iterations` as `tuple[IterationRecord, ...]` rather than
`tuple[dict[str, Any], ...]`, the field is expecting Pydantic models, not
serialized dicts. In that case skip the `cast`-to-dict and pass `iterations`
through directly — verify the schema first by reading
`src/llm_poker_arena/storage/schemas.py:201-235` before applying this step.

- [ ] **Step 5: Update CLI entry point `cli/play.py`**

Open `src/llm_poker_arena/cli/play.py`. Find the `sess.run()` call and replace with:

```python
import asyncio
asyncio.run(sess.run())
```

- [ ] **Step 5.5: Update `analysis/baseline.py`**

Both `run_random_baseline` (line 28) and `run_rule_based_baseline` (line 41)
end with `.run()` on a Session. Convert each to wrap with `asyncio.run`:

```python
import asyncio  # add at top of file

# In run_random_baseline:
def run_random_baseline(...) -> Path:
    ...
    sess = Session(
        config=cfg, agents=agents, output_dir=output_dir,
        session_id="b1_random",
    )
    asyncio.run(sess.run())
    return output_dir

# Same pattern for run_rule_based_baseline:
def run_rule_based_baseline(...) -> Path:
    ...
    sess = Session(
        config=cfg, agents=agents, output_dir=output_dir,
        session_id="b2_rule_based",
    )
    asyncio.run(sess.run())
    return output_dir
```

If either function previously chained `Session(...).run()` directly without
naming the session variable, split it into two lines so the `asyncio.run`
wraps cleanly.

- [ ] **Step 6: Update existing Session tests that called `sess.run()` synchronously**

```bash
grep -rn "sess.run()\|\.run()" tests/ --include="*.py" | grep -i "session\|sess"
```

For each call site that operates on a `Session`, replace `sess.run()` with `asyncio.run(sess.run())` and `import asyncio` at the top of the file.

The candidate files:
- `tests/unit/test_session_orchestrator.py`
- `tests/integration/*.py` if any

Apply the change.

- [ ] **Step 7: Re-run tests**

```bash
.venv/bin/pytest tests/unit/test_session_async.py tests/unit/test_session_orchestrator.py -v
```

Expected: green. Then full suite:

```bash
.venv/bin/pytest tests/ 2>&1 | tail -10
```

Expected: all green or near it. Address any remaining mismatch.

- [ ] **Step 8: Commit**

```bash
git add src/llm_poker_arena/session/session.py src/llm_poker_arena/cli/play.py src/llm_poker_arena/storage/layer_builders.py tests/
git commit -m "refactor(session): async run() — supports await agent.decide() (spec §4.1)"
```

---

## Task 7: LLMAgent simplified Bounded ReAct (K=0)

**Files:**
- Create: `src/llm_poker_arena/agents/llm/llm_agent.py`
- Test: `tests/unit/test_llm_agent_react_loop.py`

**Why K=0:** Phase 3a has no utility tools. The loop is "ask once for an action; on no_tool retry once; on illegal retry once; on transient retry once; otherwise fallback to default_safe_action or censor on permanent api_error."

- [ ] **Step 1: Write failing tests for the ReAct loop's branches**

Create `tests/unit/test_llm_agent_react_loop.py`:

```python
"""Tests for LLMAgent's K=0 ReAct loop (Phase 3a)."""
from __future__ import annotations

import asyncio

import pytest

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.provider_base import (
    ProviderPermanentError,
    ProviderTransientError,
)
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    TokenCounts,
    ToolCall,
)
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)


def _params() -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=False, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _seats() -> tuple[SeatPublicInfo, ...]:
    return tuple(
        SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                       position_full="x", stack=10_000,
                       invested_this_hand=0, invested_this_round=0,
                       status="in_hand")
        for i in range(6)
    )


def _view(legal: LegalActionSet) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=150, sidepots=(), my_stack=10_000,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=0.4, effective_stack=10_000,
        seats_public=_seats(), opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=legal, opponent_stats={},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=_params(),
    )


def _resp(*tool_calls: ToolCall, stop_reason: str = "tool_use",
          text: str = "") -> LLMResponse:
    return LLMResponse(
        provider="mock", model="m1", stop_reason=stop_reason,
        tool_calls=tuple(tool_calls), text_content=text,
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


def test_happy_path_first_response_is_legal_action() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="fold", args={}, tool_use_id="t1")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="fold", args={})
    assert result.iterations and len(result.iterations) == 1
    assert result.api_retry_count == 0
    assert result.illegal_action_retry_count == 0
    assert result.no_tool_retry_count == 0
    assert result.default_action_fallback is False
    assert result.api_error is None
    assert result.total_tokens.input_tokens == 10


def test_illegal_action_retried_once_then_recovers() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="raise_to", args={"amount": 500},
                       tool_use_id="t1")),  # illegal: not in legal set
        _resp(ToolCall(name="fold", args={}, tool_use_id="t2")),  # legal recovery
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"
    assert result.illegal_action_retry_count == 1
    assert result.default_action_fallback is False


def test_illegal_action_exhausts_retry_then_fallback() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="raise_to", args={"amount": 500}, tool_use_id="t1")),
        _resp(ToolCall(name="raise_to", args={"amount": 500}, tool_use_id="t2")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.illegal_action_retry_count == 1  # consumed budget
    assert result.default_action_fallback is True
    assert result.final_action is not None
    # Default-safe fallback: with to_call > 0 and check not legal, fold.
    assert result.final_action.tool_name == "fold"


def test_no_tool_response_retried_once_then_recovers() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        _resp(stop_reason="end_turn", text="thinking..."),  # no tool call
        _resp(ToolCall(name="fold", args={}, tool_use_id="t2")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.no_tool_retry_count == 1
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"


def test_no_tool_exhausted_falls_back_to_default_safe() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    script = MockResponseScript(responses=(
        _resp(stop_reason="end_turn", text="..."),
        _resp(stop_reason="end_turn", text="still thinking..."),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.no_tool_retry_count == 1
    assert result.default_action_fallback is True


def test_transient_error_retried_once_then_recovers() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(
        responses=(_resp(ToolCall(name="fold", args={}, tool_use_id="t1")),),
        errors_at_step={0: ProviderTransientError("simulated 503")},
    )
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.api_retry_count == 1
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"


def test_transient_error_exhausted_returns_api_error() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(
        responses=(),
        errors_at_step={
            0: ProviderTransientError("503-1"),
            1: ProviderTransientError("503-2"),
        },
    )
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.api_retry_count == 1
    assert result.api_error is not None
    assert result.api_error.type == "ProviderTransientError"
    assert result.final_action is None


def test_permanent_error_immediately_returns_api_error_no_retry() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(
        responses=(),
        errors_at_step={0: ProviderPermanentError("400 bad request")},
    )
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.api_retry_count == 0
    assert result.api_error is not None
    assert result.api_error.type == "ProviderPermanentError"
    assert result.final_action is None


def test_total_turn_timeout_returns_api_error() -> None:
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))

    # Custom MockProvider that sleeps to force timeout
    class SlowMock(MockLLMProvider):
        async def complete(self, **_kw):  # type: ignore[override]
            await asyncio.sleep(2.0)
            raise RuntimeError("unreachable")

    provider = SlowMock(script=MockResponseScript(responses=()))
    agent = LLMAgent(
        provider=provider, model="m1", temperature=0.7,
        total_turn_timeout_sec=0.1,
    )
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.turn_timeout_exceeded is True
    assert result.api_error is not None
    assert result.api_error.type == "TotalTurnTimeout"
    assert result.final_action is None


def test_multi_tool_call_response_increments_tool_usage_error_count() -> None:
    """spec §4.1: when the model emits multiple tool_use blocks in one
    response, that's a tool-misuse error. We bookkeep, retry once via
    illegal-retry budget, and fall back to default_safe if the next response
    is also multi-tool. (For LLMAgent K=0 in 3a; the tool_use_id of the FIRST
    tool call is used to thread the tool_result error.)"""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    multi_tool_response = LLMResponse(
        provider="mock", model="m1", stop_reason="tool_use",
        tool_calls=(
            ToolCall(name="fold", args={}, tool_use_id="t1a"),
            ToolCall(name="call", args={}, tool_use_id="t1b"),  # 2nd is illegal
        ),
        text_content="", tokens=TokenCounts(input_tokens=10, output_tokens=5,
                                             cache_read_input_tokens=0,
                                             cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )
    single_recovery = _resp(ToolCall(name="fold", args={}, tool_use_id="t2"))
    script = MockResponseScript(responses=(multi_tool_response, single_recovery))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.tool_usage_error_count == 1
    assert result.illegal_action_retry_count == 1  # consumed 1 retry slot
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"
    assert result.default_action_fallback is False


def test_action_tool_specs_fails_fast_on_missing_bounds() -> None:
    """The plan removes the silent default [0, 1e9] bounds. If
    compute_legal_tool_set ever emits a bet/raise_to spec without proper
    bounds, the agent must raise immediately instead of papering over."""
    from llm_poker_arena.agents.llm.llm_agent import _action_tool_specs
    bad_legal = LegalActionSet(tools=(
        # raise_to with no amount bounds — engine bug case
        ActionToolSpec(name="raise_to", args={}),
    ))
    view = _view(bad_legal)
    with pytest.raises(ValueError, match="missing amount bounds"):
        _action_tool_specs(view)
```

- [ ] **Step 2: Confirm tests fail**

```bash
.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `llm_agent.py`**

```python
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
    TokenCounts,
    ToolCall,
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
        except asyncio.TimeoutError:
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
        MAX_STEPS = 4  # bounds the loop hard

        api_retry = 0
        illegal_retry = 0
        no_tool_retry = 0
        tool_usage_error_count = 0  # spec §4.1: tracks tool-misuse errors
                                    # (multi-tool-call, malformed args, etc).

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
            except (asyncio.TimeoutError, ProviderTransientError) as e:
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

            # spec §4.1: tool_usage_error_count tracks "model misused the tool
            # interface" (vs illegal action which is "tool used legally but
            # the action chosen isn't in legal set"). A multi-tool-call
            # response in one turn is a misuse — we want exactly one action
            # tool per response. Bookkeep, retry once via illegal-retry budget,
            # else fallback.
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
                    # tool_result must reference the FIRST tool_use_id
                    # because Anthropic protocol requires every tool_use in
                    # the assistant turn to be answered. For 3a we answer
                    # only the first; multi-tool-call is rare and the
                    # subsequent retry should produce a single call.
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
                # Anthropic protocol: when an assistant turn contains a
                # tool_use block, the next user turn MUST contain a
                # corresponding tool_result block (matched by tool_use_id),
                # not a free-form text message. Otherwise the API rejects
                # the request. Use is_error=True to signal the tool call
                # itself was wrong.
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

        # MAX_STEPS reached without commit
        return self._fallback_default_safe(
            view, iterations, total_tokens, turn_start,
            api_retry, illegal_retry, no_tool_retry,
            tool_usage_error_count=tool_usage_error_count,
        )

    def _build_initial_messages(self, view: PlayerView) -> list[dict[str, Any]]:
        return [
            {"role": "user", "content": _user_prompt_for(view)},
        ]

    def _fail_with_api_error(
        self, iterations, total_tokens, turn_start,
        api_retry, illegal_retry, no_tool_retry,
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
        self, view, iterations, total_tokens, turn_start,
        api_retry, illegal_retry, no_tool_retry,
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
    """Convert PlayerView's LegalActionSet into Anthropic tool-call schema.

    Fail-fast on missing bet/raise bounds: if the engine's
    `compute_legal_tool_set` ever returns a `bet` or `raise_to` spec without
    a complete `{"min": int, "max": int}` amount range, that's an engine bug
    and silently filling defaults would mask it (and let the LLM legitimately
    propose 0 or 1e9 as amounts that would round-trip-fail downstream).
    """
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


def _assistant_message(response: Any) -> dict[str, Any]:  # noqa: ANN401
    """Re-serialize provider response as Anthropic-shape assistant message."""
    if hasattr(response, "raw_assistant_turn"):
        blocks = list(response.raw_assistant_turn.blocks)
        return {"role": "assistant", "content": blocks or [
            {"type": "text", "text": response.text_content or ""}
        ]}
    return {"role": "assistant", "content": str(response)}


def _user_text(text: str) -> dict[str, Any]:
    """Plain text user message — only safe when previous assistant turn had
    NO tool_use block (e.g. no_tool_retry path). Anthropic API rejects this
    pattern after a tool_use turn; use _tool_result_user instead."""
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
```

- [ ] **Step 4: Verify ReAct tests pass**

```bash
.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py -v
```

Expected: 11 passed. If `test_total_turn_timeout_returns_api_error` flakes, reduce the test's `total_turn_timeout_sec` to 0.05.

- [ ] **Step 5: Commit**

```bash
git add src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_llm_agent_react_loop.py
git commit -m "feat(agents): LLMAgent K=0 ReAct loop — retry budgets + fallback (spec §4.2)"
```

---

## Task 8: Mock-LLM 6-hand integration test

**Files:**
- Create: `tests/integration/test_llm_session_mock.py`

This test wires LLMAgent + MockLLMProvider into a real Session and verifies the artifacts contain real `iterations` data.

- [ ] **Step 1: Write the integration test**

```python
"""Integration test: 6-hand session with MockLLMProvider-backed LLMAgents.

Asserts that:
  - the run completes (no censor)
  - iterations data lands in agent_view_snapshots.jsonl
  - chip_pnl sums to zero
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.mock import (
    MockLLMProvider,
    MockResponseScript,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    TokenCounts,
    ToolCall,
)
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _fold_response(uid: str) -> LLMResponse:
    return LLMResponse(
        provider="mock", model="m", stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id=uid),),
        text_content="folding", tokens=TokenCounts(
            input_tokens=50, output_tokens=10,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        ),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


def _check_response(uid: str) -> LLMResponse:
    return LLMResponse(
        provider="mock", model="m", stop_reason="tool_use",
        tool_calls=(ToolCall(name="check", args={}, tool_use_id=uid),),
        text_content="checking", tokens=TokenCounts(
            input_tokens=50, output_tokens=10,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        ),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


def _call_response(uid: str) -> LLMResponse:
    return LLMResponse(
        provider="mock", model="m", stop_reason="tool_use",
        tool_calls=(ToolCall(name="call", args={}, tool_use_id=uid),),
        text_content="calling", tokens=TokenCounts(
            input_tokens=50, output_tokens=10,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        ),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


class _AlwaysFolds(LLMAgent):
    """Helper that wires up an LLMAgent whose mock provider returns fold every call."""

    def __init__(self) -> None:
        # 200 responses is way more than 6 hands × 6 seats × max_steps=4 needs.
        responses = tuple(_fold_response(f"t{i}") for i in range(200))
        provider = MockLLMProvider(script=MockResponseScript(responses=responses))
        super().__init__(provider=provider, model="m", temperature=0.7)


def test_six_hand_session_with_mock_llm_agents_completes(tmp_path: Path) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    agents = [_AlwaysFolds() for _ in range(6)]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="llm_mock_test")
    asyncio.run(sess.run())

    # 6 hands written
    private = (tmp_path / "canonical_private.jsonl").read_text().strip().splitlines()
    assert len(private) == 6
    public = (tmp_path / "public_replay.jsonl").read_text().strip().splitlines()
    assert len(public) == 6

    # iterations populated in snapshots
    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    assert len(snaps) >= 6  # at least one turn per hand
    rec0 = json.loads(snaps[0])
    assert rec0["iterations"], "iterations must be non-empty for LLMAgent turns"
    assert rec0["iterations"][0]["provider_response_kind"] == "tool_use"
    assert rec0["iterations"][0]["tool_call"]["name"] == "fold"
    assert rec0["total_tokens"]["input_tokens"] > 0

    # chip_pnl conservation
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0
```

- [ ] **Step 2: Run the test**

```bash
.venv/bin/pytest tests/integration/test_llm_session_mock.py -v
```

Expected: green. If iterations are empty in the snapshot, debug `build_agent_view_snapshot` from Task 6 — likely the iterations kwarg isn't being threaded through.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_llm_session_mock.py
git commit -m "test(integration): 6-hand session with MockLLM-backed LLMAgents (spec §1.3)"
```

---

## Task 9: Real-Anthropic gated integration smoke test

**Files:**
- Create: `tests/integration/test_llm_session_real_anthropic.py`

**Why gated:** every run costs real $$ and can flake on rate limits. CI does NOT run this; developer runs it manually before phase sign-off.

- [ ] **Step 1: Write the gated test**

```python
"""Real Anthropic API smoke test (gated, NOT in CI).

Run only when both env vars are set:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...

Costs $0.01-0.05 per run depending on prompt size + thinking.
Uses claude-haiku-4-5 (cheapest) and 1 hand only.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


pytestmark = pytest.mark.skipif(
    os.getenv("ANTHROPIC_INTEGRATION_TEST") != "1"
    or not os.getenv("ANTHROPIC_API_KEY"),
    reason="needs ANTHROPIC_INTEGRATION_TEST=1 and ANTHROPIC_API_KEY set",
)


def test_real_claude_haiku_plays_one_hand(tmp_path: Path) -> None:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,  # validator demands multiple of 6
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    # Only seat 3 is the LLM; others are RandomAgent to keep cost low.
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    llm_agent = LLMAgent(
        provider=provider, model="claude-haiku-4-5",
        temperature=0.7, total_turn_timeout_sec=60.0,
    )
    agents = [
        RandomAgent(),  # BTN
        RandomAgent(),  # SB
        RandomAgent(),  # BB
        llm_agent,      # UTG ← Claude
        RandomAgent(),  # HJ
        RandomAgent(),  # CO
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="real_anthropic_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    # Find at least one snapshot from seat 3 (the LLM)
    llm_snaps = [json.loads(l) for l in snaps if json.loads(l)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots found"
    rec = llm_snaps[0]
    assert rec["agent"]["provider"] == "anthropic"
    assert rec["agent"]["model"] == "claude-haiku-4-5"
    assert rec["iterations"], "no iterations recorded — provider plumbing broken"
    assert rec["total_tokens"]["input_tokens"] > 0
    assert rec["total_tokens"]["output_tokens"] > 0

    # Final action must be in the legal set at decision time.
    final = rec["final_action"]
    legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
    assert final["type"] in legal_names, (
        f"LLM picked {final['type']!r} but legal set was {legal_names}"
    )

    # chip_pnl conservation still holds
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0
```

- [ ] **Step 2: Verify it skips by default**

```bash
.venv/bin/pytest tests/integration/test_llm_session_real_anthropic.py -v
```

Expected: SKIPPED.

- [ ] **Step 3: Manually run with credentials (developer-driven)**

```bash
export ANTHROPIC_INTEGRATION_TEST=1
export ANTHROPIC_API_KEY=sk-ant-your-real-key
.venv/bin/pytest tests/integration/test_llm_session_real_anthropic.py -v
unset ANTHROPIC_INTEGRATION_TEST
```

Expected: 1 passed; cost ~$0.02. Inspect `tmp_path` printed by pytest fixtures or use `pytest --basetemp=/tmp/anthropic_smoke -s` to find artifacts.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_llm_session_real_anthropic.py
git commit -m "test(integration): real-Anthropic smoke test (gated; manual run only)"
```

---

## Task 10: Final verification + lint

- [ ] **Step 1: Full test suite**

```bash
.venv/bin/pytest tests/ 2>&1 | tail -5
```

Expected: all tests pass (or only the gated real-Anthropic test skipped). Total count should be ~270+ (current 234 + ~35 new from Phase 3a).

- [ ] **Step 2: Lint**

```bash
.venv/bin/ruff check src/ tests/
```

Expected: `All checks passed!`. If issues, fix and re-commit.

- [ ] **Step 3: Strict type check**

```bash
.venv/bin/mypy --strict src/ tests/
```

Expected: `Success: no issues found`. Common issues:
- Anthropic SDK types may not be fully typed; add `# type: ignore[attr-defined]` sparingly with a brief reason comment.
- Mock SDK objects from `unittest.mock` may need `cast` or `# type: ignore`.

- [ ] **Step 4: Run the full suite once more after lint fixes**

```bash
.venv/bin/pytest tests/ 2>&1 | tail -5
```

- [ ] **Step 5: Manual end-to-end smoke (optional but recommended)**

```bash
# Run the existing demo to make sure nothing broke for non-LLM agents
.venv/bin/python -c "
import asyncio, shutil
from pathlib import Path
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.agents.rule_based import RuleBasedAgent

cfg = SessionConfig(
    num_players=6, starting_stack=10_000, sb=50, bb=100,
    num_hands=6, max_utility_calls=5,
    enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
    opponent_stats_min_samples=30, rng_seed=42,
)
agents = [RandomAgent() if i % 2 == 0 else RuleBasedAgent() for i in range(6)]
out = Path('/tmp/phase3a_smoke')
if out.exists(): shutil.rmtree(out)
out.mkdir()
sess = Session(config=cfg, agents=agents, output_dir=out, session_id='3a_smoke')
asyncio.run(sess.run())
print('OK; artifacts in', out)
"
ls /tmp/phase3a_smoke/
```

Expected: 4 standard files (canonical_private.jsonl, public_replay.jsonl, agent_view_snapshots.jsonl, meta.json).

- [ ] **Step 6: Final commit if any lint/type fixes were needed**

```bash
git add -A && git commit -m "fix(phase-3a): post-verification lint + type fixes" || echo "nothing to commit"
```

---

## Phase 3a exit criteria

- [ ] Async `Agent.decide() -> TurnDecisionResult` ABC in place; all 4 existing agents (Random, RuleBased, HumanCLI, LLMAgent) implement it.
- [ ] `LLMProvider` ABC defined; `MockLLMProvider` and `AnthropicProvider` implementations.
- [ ] `LLMAgent` with K=0 simplified ReAct + 3 retry budgets (api/illegal/no_tool) + fallback to default_safe_action + censor on permanent error.
- [ ] `Session.run` async; `agent_view_snapshots.jsonl` contains real iterations + token counts.
- [ ] Mock-driven 6-hand integration test green.
- [ ] Gated real-Anthropic 1-hand smoke test skips by default; manually verified to pass once with real API key.
- [ ] Full test suite, ruff, and mypy --strict all green.
- [ ] No regressions in existing CLI (`poker-play` from Phase 2c) — verified by manual smoke.

---

## Self-review checklist

**Spec coverage:** §4.1 ✓ (Agent + TurnDecisionResult), §4.2 ✓ partial (K=0 simplified), §4.3 ✓ (IterationRecord), §4.4 ✓ partial (LLMProvider ABC + Anthropic complete()), §4.5 deferred to 3d (rationale_required is in prompt but not strict-mode), §4.6 deferred to 3b (reasoning artifacts), §6.1 ✓ partial (hardcoded prompt; Jinja deferred to 3d).

**Placeholder scan:** Each step has actual code, not "TODO". The deferred concerns (probe, extract_reasoning_artifact, serialize_assistant_turn) are explicit `NotImplementedError` stubs — that's intentional, with the next phase that fills them named.

**Type consistency:** `TurnDecisionResult` field names match spec §4.1 verbatim; `IterationRecord` matches spec §4.3 (with provider_response_kind added for Phase-3a-specific tracking that aligns with §7.4 schema). `Action` is the existing `engine/legal_actions.py` dataclass — no rename. `LLMProvider.complete()` signature matches spec §4.4.

**Risk register:**
- R1: `Action` is a stdlib `@dataclass(frozen=True)`. Pydantic v2 supports stdlib dataclasses as field types but may require `arbitrary_types_allowed=True`. Codex pre-verified `model_dump_json` round-trips work; keep an eye on this in Task 1 testing.
- R2: `AgentViewSnapshot` already requires `iterations` (verified at `src/llm_poker_arena/storage/schemas.py:201-235`); the kwarg names match. The risk is the typing of the schema's `iterations` field (does it want Pydantic models or dicts?) — read the schema before Task 6 Step 4 and adjust `iter_dump` typing accordingly.
- R3: `pytest-asyncio` is already in `pyproject.toml:21` with `asyncio_mode = "auto"` at `pyproject.toml:54-58`, so `@pytest.mark.asyncio` is mostly idiom rather than strictly required. Keep the marker for clarity.
- R4: Sync `.run()` callers exist beyond `cli/play.py` and tests — `analysis/baseline.py:37, 50` (Task 6 Step 5.5) and `engine/_internal/rebuy.py:95` (Task 5 Step 7).
- R5: `cli/play.py` uses Session sync; Task 6 Step 5 must update that, and the manual `poker-play` CLI must still work after Phase 3a.
- R6: Anthropic API rejects requests where an assistant turn with `tool_use` blocks is followed by a free-form text user message (instead of a `tool_result` block). All retry paths after a `tool_use` response MUST use `_tool_result_user(...)` — confirmed in Task 7's illegal-action retry and multi-tool-call retry. The `no_tool_retry` path uses `_user_text` which is correct because that path's prior assistant turn had no `tool_use`.
- R7: `run_single_hand` is sync; bridging via `asyncio.run` inside it makes the helper unusable from any caller already inside an event loop. Flag this constraint in `rebuy.py` docstring during Task 5 Step 7 so future async migrations of property tests don't trip on it.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-24-llm-poker-arena-phase-3a-anthropic-llm-agent.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task with two-stage review (spec compliance + code quality) after each. Best for catching schema-drift between tasks, since each task has detailed type signatures that downstream tasks rely on.

**2. Inline Execution** — Execute tasks in this session using executing-plans, with the entire plan loaded into one context. Faster but more risk of running out of context on a 10-task / ~2200-line plan.

**Recommendation: Subagent-Driven, with codex audit on the plan first** (the past 4 phase plans all had ≥1 critical issue caught at codex audit; doing it again here avoids replanning mid-flight).

# Phase 3b: Multi-Provider + Capability Probe + Reasoning Artifacts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (inline mode chosen by user) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an OpenAI-compatible provider (covering OpenAI Chat API and DeepSeek), make the LLMAgent ReAct loop provider-agnostic at the message-format boundary, and wire `LLMProvider.probe()` + `extract_reasoning_artifact()` end-to-end so each session's `meta.json.provider_capabilities` and per-iteration reasoning artifacts are populated for cross-provider analysis.

**Architecture:**
- Move all Anthropic-shaped message construction (`_assistant_message`, `_tool_result_user`, `_multi_tool_result_user`, `_user_text`) **out of `LLMAgent`** and **into the `LLMProvider` ABC** as new abstract methods. Each provider then implements its own wire format. `LLMAgent` becomes a pure protocol-driver that calls `provider.build_*()` whenever it needs to append a message.
- Add three new types to `agents/llm/types.py`: `ReasoningArtifactKind` (str-enum), `ReasoningArtifact`, `ObservedCapability` — matching spec §4.6 + §4.4.
- Extend `IterationRecord` with `reasoning_artifacts: tuple[ReasoningArtifact, ...] = ()` (note: spec §4.3 uses singular field `reasoning_artifact`, but real Anthropic responses can have multiple thinking blocks per turn; tuple is forward-compatible and JSON-dumps cleanly). The single-vs-tuple delta is documented in Task 2 commit message.
- `OpenAICompatibleProvider(provider_name, model, api_key, base_url=None, ...)` — single class, parameterized by `base_url`. `base_url=None` → OpenAI canonical; `base_url="https://api.deepseek.com/v1"` → DeepSeek. Both speak Chat Completions; tool-call shape is identical between them.
- Session at startup probes every distinct `LLMProvider` instance once, collects `ObservedCapability` per seat, writes into `meta.json.provider_capabilities` keyed by seat string (matches spec §7.6 example). Non-LLM agents (Random, RuleBased, HumanCLI) skip probe.

**Tech Stack:**
- `openai>=1.0` SDK (new dep) — for `AsyncOpenAI` + Chat Completions wire format
- `anthropic>=0.34,<1.0` (already a dep) — used for byte-identical thinking-block re-send verification
- DeepSeek's HTTP API is OpenAI-Chat-Completions-compatible; no separate SDK needed
- Existing: `pydantic>=2.0`, `pytest-asyncio`, mypy strict

**Reference docs to consult while executing:**
- Spec `docs/superpowers/specs/2026-04-23-llm-poker-arena-design-v2.md` §4.3 / §4.4 / §4.6 / §7.4 / §7.6 / §11.1 / §11.2
- Memory `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md`
- DeepSeek docs (search `deepseek api reasoning_content`): `message.reasoning_content` field on `deepseek-reasoner`, returns the chain-of-thought in plaintext; `deepseek-chat` (V3) does NOT return it.
- OpenAI Chat Completions tool-call format: `assistant.tool_calls[*].id`, `function.name`, `function.arguments` (JSON string!); response to a tool_call is a `{"role": "tool", "tool_call_id": ..., "content": ...}` message — one per call (NOT bundled into one user message like Anthropic's `tool_result` block list).

---

## File Structure

**New files:**
- `src/llm_poker_arena/agents/llm/providers/openai_compatible.py` — single class covering OpenAI + DeepSeek; ~200 LOC
- `tests/integration/test_llm_session_real_deepseek.py` — gated by `DEEPSEEK_INTEGRATION_TEST=1` + `DEEPSEEK_API_KEY`
- `tests/integration/test_llm_session_real_multi_provider.py` — gated by both `ANTHROPIC_INTEGRATION_TEST=1` and `DEEPSEEK_INTEGRATION_TEST=1`; mixes Claude + DeepSeek + Random in one session
- `tests/unit/test_openai_compatible_provider.py` — unit tests with monkeypatched SDK (no network)
- `tests/unit/test_reasoning_artifact_extraction.py` — unit tests for both providers' `extract_reasoning_artifact`
- `tests/unit/test_provider_message_builders.py` — unit tests for both providers' `build_*` methods (replay round-trip)

**Modified files:**
- `pyproject.toml` — add `openai>=1.0,<2.0` to `[project] dependencies`
- `src/llm_poker_arena/agents/llm/types.py` — add 3 types (`ReasoningArtifactKind`, `ReasoningArtifact`, `ObservedCapability`); extend `IterationRecord` with `reasoning_artifacts` field
- `src/llm_poker_arena/agents/llm/provider_base.py` — add 3 abstract methods (`build_assistant_message_for_replay`, `build_tool_result_messages`, `build_user_text_message`); convert `extract_reasoning_artifact` and `probe` from NotImplementedError stubs to abstract methods (so subclasses must implement)
- `src/llm_poker_arena/agents/llm/providers/anthropic_provider.py` — implement the 5 new abstract methods + verify thinking-block byte-identical preservation
- `src/llm_poker_arena/agents/llm/providers/mock.py` — `MockLLMProvider` implements the 5 new methods (mirrors Anthropic shape so existing 23 ReAct unit tests stay green)
- `src/llm_poker_arena/agents/llm/llm_agent.py` — delete `_assistant_message`, `_user_text`, `_tool_result_user`, `_multi_tool_result_user` module functions; replace call sites with `self._provider.build_*()`; in each happy-path / retry IterationRecord construction, attach `reasoning_artifacts=self._provider.extract_reasoning_artifact(response)`; update rationale_required check to also consider non-empty reasoning artifacts
- `src/llm_poker_arena/storage/meta.py` — `build_session_meta` accepts new `provider_capabilities: dict[str, dict[str, Any]]` kwarg
- `src/llm_poker_arena/session/session.py` — at start of `run()`, probe each unique `LLMProvider` (deduplicate by `id(provider)`), collect per-seat `ObservedCapability` dump, pass to `build_session_meta`
- `tests/unit/test_llm_agent_react_loop.py` — touch only if existing tests break (they shouldn't if MockLLMProvider mirrors Anthropic semantics)
- `tests/unit/test_llm_types.py` — add round-trip tests for new types and extended IterationRecord
- `.env.example` — add `OPENAI_API_KEY=` and `DEEPSEEK_API_KEY=` placeholders (file already exists per Phase 3a Task 0)

**Files NOT touched (intentionally):**
- `src/llm_poker_arena/agents/llm/redaction.py` — redaction regex already handles all three key formats (sk-ant-, sk-, DeepSeek `sk-`); confirmed in Phase 3d Task 6
- `src/llm_poker_arena/agents/llm/prompt_profile.py` — prompts are provider-agnostic Jinja templates
- Any utility-tool / equity / ToolRunner code — that's Phase 3c

---

## Spec Inconsistencies to Reconcile (DOCUMENT, do not silently choose)

While implementing, three spec inconsistencies surface. The plan resolves them as follows; note in commit message of the relevant task:

1. **`IterationRecord.reasoning_artifact` (singular, §4.3) vs `reasoning_artifacts` (plural, what we ship).**  Anthropic extended thinking can emit multiple `thinking` / `redacted_thinking` / `encrypted_thinking` blocks in one assistant turn. Spec §4.6 defines `provider_raw_index` on each `ReasoningArtifact` — implying multiple artifacts coexist. Plural tuple matches §4.6 and is forward-compatible. **Decision: ship `reasoning_artifacts: tuple[ReasoningArtifact, ...] = ()`. Document in Task 2 commit.**
2. **`meta.json.provider_capabilities` field names: §7.6 example uses `reasoning_kinds_observed` + `seed_supported`; §4.4 ABC defines `ObservedCapability` with `reasoning_kinds` + `seed_accepted`.** §7.6 IS the persisted JSON schema that downstream analysts will read; §4.4 is the in-process Pydantic type. **Decision: keep `ObservedCapability` (the in-process type) with §4.4 names (`reasoning_kinds`, `seed_accepted`); at the persistence boundary in `_probe_providers`, MAP into the §7.6-named JSON dict (`reasoning_kinds_observed`, `seed_supported`). Both spec sections stay honest; analysts reading `meta.json` see the §7.6 schema they were promised. Document in Task 7 commit.**
3. **`serialize_assistant_turn` (spec §4.4) vs `build_assistant_message_for_replay` (what we add).** Spec §4.4 defines `serialize_assistant_turn(response) -> AssistantTurn` and attaches the BR2-07 byte-identical preservation contract to it. Phase 3a's default impl returns `response.raw_assistant_turn` unchanged — that satisfies the spec contract structurally (the `AssistantTurn.blocks` tuple already preserves byte-identical blocks). However, LLMAgent's actual practical need at the wire is a `dict[str, Any]` ready to slot into the `messages` list, not a wrapped `AssistantTurn` Pydantic instance. **Decision: keep `serialize_assistant_turn` as the structural / spec-compliance method (Phase 3a default passthrough is fine — verified to round-trip thinking blocks via Task 4 test). Add `build_assistant_message_for_replay(response) -> dict[str, Any]` in Task 3 as the wire-format method LLMAgent actually calls. Both methods read from the same `response.raw_assistant_turn.blocks`, so the BR2-07 invariant holds for both. Document in Task 3 commit.**

## Spec Items Deferred (NOT in Phase 3b)

- **`LLMProvider.static_capability() -> ProviderCapability`** (spec §4.4): a separate offline-config capability declaration distinct from the live probe. Spec marks it as "fallback / offline configuration reference only; runtime takes probe() as source of truth". 3b ships only the probe path because that's what `meta.json.provider_capabilities` consumes. Adding `static_capability` would require defining a `ProviderCapability` type (not yet defined anywhere). Defer until something actually needs offline capability declarations (likely never — probe covers all current use cases).
- **Anthropic extended-thinking enablement on real calls.** Phase 3b implements the byte-identical preservation mechanism and unit-tests it with synthetic block dicts, but does NOT enable `thinking={"type": "enabled", ...}` on real `messages.create` calls. The plumbing is ready when a future phase wants Anthropic CoT for analysis.
- **OpenAI Responses API** (the newer reasoning-tier endpoint replacing Chat Completions for o-series models). Phase 3b implements only Chat Completions because (a) DeepSeek-Reasoner is the cheapest CoT-emitting model and uses Chat-shape, and (b) o-series cost ≫ Haiku cost for the same throughput. Defer to a future "Phase 3b.2: OpenAI Responses API" if/when we want o1/o3 in the experiment matrix.
- **Tool_use + thinking probe round-trip** (spec §4.4 HR2-03): the spec's full HR2-03 contract has probe drive a `tool_choice=any` request in thinking-enabled mode and observe whether the provider accepts the combo. 3b doesn't enable extended thinking, so `tool_use_with_thinking_ok=False` is reported with `extra_flags["tool_use_with_thinking_probed"]=False` to make the "not actually tested" status explicit. When extended thinking gets enabled (above bullet), this probe extension lands too.
- **`AgentDescriptor.temperature` / `agent.seed`** (spec §7.4): Phase 3a / 3d set these to `None` on the snapshot; spec §11.2 expects unsupported providers to record `seed=null`. Codex audit (2026-04-25) flagged that Phase 3b doesn't fix this. Reason for deferral: this is pre-existing 3a tech debt, not a multi-provider concern; populating it requires exposing `LLMAgent._temperature` / `_seed` accessors and changing `build_agent_view_snapshot` signature — touches files orthogonal to provider abstraction. **Slot for fix: Phase 3e** (1000-hand session + cost telemetry), where reproducibility metadata gets first-class attention.
- **`meta.json.retry_summary_per_seat` / `tool_usage_summary` / `total_tokens` aggregation** (spec §7.6): Phase 3a's `build_session_meta` writes empty dicts for these. Codex audit (2026-04-25) flagged that Phase 3b doesn't aggregate them either. Reason for deferral: aggregation across all `TurnDecisionResult` objects requires a session-level accumulator that Phase 3b's Task 7 doesn't add (probe wiring is orthogonal). **Slot for fix: Phase 3e**, alongside cost telemetry which depends on the same per-seat aggregation infrastructure.

---

## Risks Acknowledged Up Front

- **Anthropic SDK extended-thinking blocks**: Phase 3b does NOT enable extended thinking on real calls (default behavior). Byte-identical preservation is implemented and unit-tested with synthetic `thinking` block dicts; live extended-thinking integration is deferred to a future phase if/when we want CoT-from-Anthropic.
- **OpenAI seed parameter behavior**: Spec §11.2 marks OpenAI `seed` as best-effort; some Chat Completions params are deprecated. We pass `seed=` if non-None and let the SDK / API decide. Probe records observed `seed_accepted` based on whether the API rejected the parameter.
- **DeepSeek-Reasoner output**: returns `reasoning_content` separately from `content`. The post-reasoning answer (`content`) may be empty when the model thinks at length and produces a tool call. Phase 3b's `rationale_required` strict-mode check is updated to count non-empty reasoning artifacts as satisfying the rationale requirement (otherwise R1 always trips no_tool_retry).
- **Multi-tool-call protocol mismatch**: Anthropic accepts `assistant: [tool_use, tool_use]` followed by `user: [tool_result, tool_result]`. OpenAI requires `assistant: {tool_calls: [tc1, tc2]}` followed by TWO `role: tool` messages. Our `build_tool_result_messages` returns `list[dict]`, and `LLMAgent` always uses `messages.extend(...)` — provider hides the count delta.

---

## Task 0: Add `openai` SDK dependency + `.env.example` keys

**Files:**
- Modify: `pyproject.toml:11-18` (dependencies block)
- Modify: `.env.example` (already exists from Phase 3a Task 0)

- [ ] **Step 1: Add `openai` dep**

Edit `pyproject.toml:11-18`. Insert `openai>=1.0,<2.0` between `matplotlib` and `pokerkit` to keep the alphabetical order:

```toml
dependencies = [
    "anthropic>=0.34,<1.0",
    "duckdb>=1.0,<2.0",
    "jinja2>=3.1,<4.0",
    "matplotlib>=3.8,<4.0",
    "openai>=1.0,<2.0",
    "pokerkit>=0.7,<0.8",
    "pydantic>=2.0",
]
```

- [ ] **Step 2: Install the new dep**

Run: `.venv/bin/pip install -e .`

Expected: pip resolves `openai>=1.0,<2.0` and any sub-deps (`httpx`, `distro`, `jiter`, `tqdm`, etc.). Verify import: `.venv/bin/python -c "from openai import AsyncOpenAI; print(AsyncOpenAI.__module__)"` — expected output `openai._client`.

- [ ] **Step 3: Update `.env.example`**

Read `.env.example` first (it already has `ANTHROPIC_API_KEY=` from Phase 3a Task 0). Append:

```
# DeepSeek (OpenAI-compatible at base_url=https://api.deepseek.com/v1)
DEEPSEEK_API_KEY=
# OpenAI (canonical Chat Completions API)
OPENAI_API_KEY=
```

- [ ] **Step 4: Sanity-run existing test suite**

Run: `.venv/bin/pytest tests/ -q --no-header -x`

Expected: 306 tests pass + 1 skipped (real-Anthropic), zero new failures from the dep bump.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example
git commit -m "$(cat <<'EOF'
chore(deps): add openai SDK + DeepSeek/OpenAI .env keys (Phase 3b Task 0)

OpenAICompatibleProvider in Task 6 will cover both OpenAI Chat
Completions and DeepSeek (OpenAI-compatible at base_url=
https://api.deepseek.com/v1), so a single openai SDK pin suffices.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: Add `ReasoningArtifact` / `ReasoningArtifactKind` / `ObservedCapability` types

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/types.py:1-140` (append new types at end)
- Test: `tests/unit/test_llm_types.py` (append round-trip test)

- [ ] **Step 1: Write the failing test**

Read `tests/unit/test_llm_types.py` first to see existing patterns. Append:

```python
def test_reasoning_artifact_kind_enum_values() -> None:
    from llm_poker_arena.agents.llm.types import ReasoningArtifactKind
    assert ReasoningArtifactKind.RAW.value == "raw"
    assert ReasoningArtifactKind.SUMMARY.value == "summary"
    assert ReasoningArtifactKind.THINKING_BLOCK.value == "thinking_block"
    assert ReasoningArtifactKind.ENCRYPTED.value == "encrypted"
    assert ReasoningArtifactKind.REDACTED.value == "redacted"
    assert ReasoningArtifactKind.UNAVAILABLE.value == "unavailable"


def test_reasoning_artifact_round_trip() -> None:
    from llm_poker_arena.agents.llm.types import (
        ReasoningArtifact, ReasoningArtifactKind,
    )
    art = ReasoningArtifact(
        kind=ReasoningArtifactKind.RAW,
        content="Let me think about pot odds...",
        provider_raw_index=2,
    )
    blob = art.model_dump_json()
    art2 = ReasoningArtifact.model_validate_json(blob)
    assert art2 == art
    # Encrypted variant: content is opaque base64-ish string.
    enc = ReasoningArtifact(
        kind=ReasoningArtifactKind.ENCRYPTED,
        content="cipher_payload_base64==",
        provider_raw_index=0,
    )
    assert ReasoningArtifact.model_validate_json(enc.model_dump_json()) == enc
    # Unavailable: content is None, index is None.
    none_art = ReasoningArtifact(
        kind=ReasoningArtifactKind.UNAVAILABLE,
        content=None,
        provider_raw_index=None,
    )
    assert ReasoningArtifact.model_validate_json(none_art.model_dump_json()) == none_art


def test_observed_capability_round_trip() -> None:
    from llm_poker_arena.agents.llm.types import (
        ObservedCapability, ReasoningArtifactKind,
    )
    cap = ObservedCapability(
        provider="anthropic",
        probed_at="2026-04-25T10:00:00Z",
        reasoning_kinds=(ReasoningArtifactKind.THINKING_BLOCK,
                         ReasoningArtifactKind.ENCRYPTED),
        seed_accepted=False,
        tool_use_with_thinking_ok=False,
        extra_flags={"system_fingerprint_returned": False},
    )
    blob = cap.model_dump_json()
    cap2 = ObservedCapability.model_validate_json(blob)
    assert cap2 == cap
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_llm_types.py::test_reasoning_artifact_kind_enum_values -v`

Expected: FAIL with `ImportError: cannot import name 'ReasoningArtifactKind'`.

- [ ] **Step 3: Add the new types to `types.py`**

Edit `src/llm_poker_arena/agents/llm/types.py`. Insert at the top of the file, just below the existing imports:

```python
from enum import Enum
```

Then append at the end of the file (after `TurnDecisionResult`):

```python
class ReasoningArtifactKind(str, Enum):
    """spec §4.6: enumeration of reasoning shapes a provider can emit."""

    RAW = "raw"
    SUMMARY = "summary"
    THINKING_BLOCK = "thinking_block"
    ENCRYPTED = "encrypted"
    REDACTED = "redacted"
    UNAVAILABLE = "unavailable"


class ReasoningArtifact(BaseModel):
    """spec §4.6: one provider-emitted reasoning unit (CoT / summary / opaque).

    `provider_raw_index` is the position in the raw response (Anthropic block
    list / DeepSeek field) for forensic traceability.
    """

    model_config = _frozen()

    kind: ReasoningArtifactKind
    content: str | None
    provider_raw_index: int | None


class ObservedCapability(BaseModel):
    """spec §4.4 HR2-03: live probe result. Written to meta.json per seat."""

    model_config = _frozen()

    provider: str
    probed_at: str
    reasoning_kinds: tuple[ReasoningArtifactKind, ...]
    seed_accepted: bool
    tool_use_with_thinking_ok: bool
    extra_flags: dict[str, Any]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_llm_types.py -v`

Expected: all 3 new tests pass; existing tests in this file unchanged.

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/agents/llm/types.py tests/unit/test_llm_types.py && .venv/bin/mypy --strict src/llm_poker_arena/agents/llm/types.py tests/unit/test_llm_types.py`

Expected: zero diagnostics on both files.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/agents/llm/types.py tests/unit/test_llm_types.py
git commit -m "$(cat <<'EOF'
feat(types): add ReasoningArtifact + ObservedCapability + Kind enum (Phase 3b Task 1)

spec §4.4 (HR2-03) + §4.6 (B-01). These types feed iteration records
(reasoning_artifacts) and meta.json.provider_capabilities. Kinds:
raw / summary / thinking_block / encrypted / redacted / unavailable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Extend `IterationRecord` with `reasoning_artifacts` tuple

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/types.py:77-89` (`IterationRecord` class)
- Test: `tests/unit/test_llm_types.py` (append round-trip + default tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_llm_types.py`:

```python
def test_iteration_record_default_reasoning_artifacts_is_empty_tuple() -> None:
    from llm_poker_arena.agents.llm.types import (
        IterationRecord, TokenCounts,
    )
    rec = IterationRecord(
        step=1, request_messages_digest="sha256:abcd",
        provider_response_kind="tool_use", tool_call=None,
        text_content="thinking", tokens=TokenCounts.zero(),
        wall_time_ms=42,
    )
    assert rec.reasoning_artifacts == ()


def test_iteration_record_with_reasoning_artifacts_round_trip() -> None:
    from llm_poker_arena.agents.llm.types import (
        IterationRecord, ReasoningArtifact, ReasoningArtifactKind,
        TokenCounts,
    )
    arts = (
        ReasoningArtifact(
            kind=ReasoningArtifactKind.THINKING_BLOCK,
            content="step 1 of CoT", provider_raw_index=0,
        ),
        ReasoningArtifact(
            kind=ReasoningArtifactKind.ENCRYPTED,
            content="opaque_blob", provider_raw_index=1,
        ),
    )
    rec = IterationRecord(
        step=2, request_messages_digest="sha256:1234",
        provider_response_kind="tool_use", tool_call=None,
        text_content="surface answer", tokens=TokenCounts.zero(),
        wall_time_ms=99, reasoning_artifacts=arts,
    )
    blob = rec.model_dump_json()
    rec2 = IterationRecord.model_validate_json(blob)
    assert rec2 == rec
    assert len(rec2.reasoning_artifacts) == 2
    assert rec2.reasoning_artifacts[0].kind == ReasoningArtifactKind.THINKING_BLOCK
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_llm_types.py::test_iteration_record_default_reasoning_artifacts_is_empty_tuple -v`

Expected: FAIL with `AttributeError: 'IterationRecord' object has no attribute 'reasoning_artifacts'`.

- [ ] **Step 3: Add the field to `IterationRecord`**

Edit `src/llm_poker_arena/agents/llm/types.py:77-89`. Replace the `IterationRecord` class with:

```python
class IterationRecord(BaseModel):
    """spec §4.3: one per ReAct loop iteration. Written into agent_view_snapshots.

    `reasoning_artifacts` is a tuple (not the singular field name in spec §4.3
    code block) because §4.6 ReasoningArtifact carries `provider_raw_index`
    implying a list — Anthropic extended thinking can emit multiple thinking
    blocks per turn. Empty tuple is the default for providers that emit no
    reasoning artifacts (Anthropic without extended thinking, OpenAI Chat,
    DeepSeek-Chat / V3).
    """

    model_config = _frozen()

    step: int
    request_messages_digest: str
    provider_response_kind: Literal["tool_use", "text_only", "error", "no_tool"]
    tool_call: ToolCall | None
    text_content: str
    tokens: TokenCounts
    wall_time_ms: int
    reasoning_artifacts: tuple[ReasoningArtifact, ...] = ()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_llm_types.py -v`

Expected: 5 new tests pass (3 from Task 1 + 2 from this task); existing tests unchanged.

- [ ] **Step 5: Sanity-run the full suite — confirm `IterationRecord` callers still work with default**

Run: `.venv/bin/pytest tests/ -q --no-header -x`

Expected: 311 pass + 1 skip (3 new from Task 1 + 2 new from this task = 5 new, on top of 306 baseline; none of the existing 306 break). LLMAgent's existing IterationRecord constructions don't pass `reasoning_artifacts`, so they get the default `()`.

- [ ] **Step 6: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/agents/llm/types.py tests/unit/test_llm_types.py && .venv/bin/mypy --strict src/llm_poker_arena/agents/llm/types.py`

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/agents/llm/types.py tests/unit/test_llm_types.py
git commit -m "$(cat <<'EOF'
feat(types): IterationRecord.reasoning_artifacts tuple (Phase 3b Task 2)

spec §4.3 used singular `reasoning_artifact` but §4.6's
provider_raw_index implies multiple artifacts coexist (Anthropic
extended thinking can emit multiple thinking blocks per turn). Field
is `reasoning_artifacts: tuple[ReasoningArtifact, ...] = ()` —
plural, default empty. Existing call sites that omit this field
silently inherit the empty default; populating happens in Task 8.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Move provider-specific message construction into `LLMProvider` ABC

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/provider_base.py:30-72` (add 3 abstract methods)
- Modify: `src/llm_poker_arena/agents/llm/providers/anthropic_provider.py` (implement the 3 new methods)
- Modify: `src/llm_poker_arena/agents/llm/providers/mock.py` (implement the 3 new methods)
- Modify: `src/llm_poker_arena/agents/llm/llm_agent.py:194-198, 222-237, 263-271, 308-318, 465-530` (replace inline helpers with provider calls)
- Test: `tests/unit/test_provider_message_builders.py` (NEW)

**Rationale:** OpenAI's tool-result protocol (one `role: tool` message per tool_call_id) is fundamentally different from Anthropic's (one user message with N tool_result blocks). LLMAgent must not know the difference — push it into the provider. After this task: LLMAgent calls `messages.extend(provider.build_tool_result_messages(...))` and `messages.append(provider.build_assistant_message_for_replay(...))`. Existing 23 ReAct unit tests stay green because MockLLMProvider mirrors Anthropic's shape (the tests don't inspect the message dicts; they only count calls and check final action).

- [ ] **Step 1: Write the failing test (provider message-builder contract)**

Create `tests/unit/test_provider_message_builders.py`:

```python
"""Provider must own the message-format wire details. Test contract per provider."""
from __future__ import annotations

from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.llm.providers.mock import MockLLMProvider, MockResponseScript
from llm_poker_arena.agents.llm.types import (
    AssistantTurn, LLMResponse, TokenCounts, ToolCall,
)


def _resp_with_text_and_tool() -> LLMResponse:
    return LLMResponse(
        provider="anthropic", model="claude-haiku-4-5",
        stop_reason="tool_use",
        tool_calls=(
            ToolCall(name="raise_to", args={"amount": 300},
                     tool_use_id="toolu_abc"),
        ),
        text_content="Reasoning: I have AKs and good fold equity.",
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic",
            blocks=(
                {"type": "text", "text": "Reasoning: I have AKs and good fold equity."},
                {"type": "tool_use", "id": "toolu_abc",
                 "name": "raise_to", "input": {"amount": 300}},
            ),
        ),
    )


def test_anthropic_build_assistant_message_for_replay_uses_raw_blocks() -> None:
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    msg = provider.build_assistant_message_for_replay(_resp_with_text_and_tool())
    assert msg["role"] == "assistant"
    assert isinstance(msg["content"], list)
    assert msg["content"][0]["type"] == "text"
    assert msg["content"][1]["type"] == "tool_use"
    assert msg["content"][1]["id"] == "toolu_abc"


def test_anthropic_build_tool_result_messages_returns_single_user_message() -> None:
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    tcs = (
        ToolCall(name="raise_to", args={"amount": 300}, tool_use_id="toolu_abc"),
    )
    msgs = provider.build_tool_result_messages(
        tool_calls=tcs, is_error=True, content="Illegal: not in legal set",
    )
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert msg["content"][0]["type"] == "tool_result"
    assert msg["content"][0]["tool_use_id"] == "toolu_abc"
    assert msg["content"][0]["is_error"] is True


def test_anthropic_build_tool_result_messages_covers_every_tool_use_id() -> None:
    """If the assistant turn had 2 tool_use blocks, we MUST emit 2 tool_result
    blocks in the SAME user message — Anthropic API requires every prior
    tool_use_id to be answered."""
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    tcs = (
        ToolCall(name="fold", args={}, tool_use_id="toolu_aaa"),
        ToolCall(name="raise_to", args={"amount": 300}, tool_use_id="toolu_bbb"),
    )
    msgs = provider.build_tool_result_messages(
        tool_calls=tcs, is_error=True,
        content="Multi-tool calls not allowed; pick one.",
    )
    assert len(msgs) == 1
    blocks = msgs[0]["content"]
    assert {b["tool_use_id"] for b in blocks} == {"toolu_aaa", "toolu_bbb"}


def test_anthropic_build_user_text_message_returns_plain_user() -> None:
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    msg = provider.build_user_text_message("You must call exactly one tool.")
    assert msg == {"role": "user",
                   "content": "You must call exactly one tool."}


def test_mock_provider_implements_same_3_builders() -> None:
    """MockLLMProvider in tests must satisfy the ABC so existing 23 ReAct
    unit tests keep working without touching them."""
    mock = MockLLMProvider(script=MockResponseScript(responses=()))
    # All three methods must exist and return the right shapes (mirrors
    # Anthropic semantics — tests never inspect the inner shape).
    assert callable(mock.build_assistant_message_for_replay)
    assert callable(mock.build_tool_result_messages)
    assert callable(mock.build_user_text_message)
    msg = mock.build_user_text_message("hi")
    assert msg == {"role": "user", "content": "hi"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_provider_message_builders.py -v`

Expected: FAIL — `AttributeError: 'AnthropicProvider' object has no attribute 'build_assistant_message_for_replay'`.

- [ ] **Step 3: Add 3 abstract methods to `LLMProvider` ABC**

Edit `src/llm_poker_arena/agents/llm/provider_base.py`. Insert these abstract methods between `provider_name` and `serialize_assistant_turn` (preserve existing methods):

```python
    @abstractmethod
    def build_assistant_message_for_replay(
        self, response: LLMResponse,
    ) -> dict[str, Any]:
        """Reconstruct the assistant turn (in this provider's wire format) so
        it can be appended to `messages` for the next ReAct iteration. For
        Anthropic this is `{"role":"assistant","content":[blocks...]}` with
        thinking blocks preserved byte-identical (BR2-07). For OpenAI Chat:
        `{"role":"assistant","content":text,"tool_calls":[...]}`.
        """

    @abstractmethod
    def build_tool_result_messages(
        self,
        *,
        tool_calls: tuple[ToolCall, ...],
        is_error: bool,
        content: str,
    ) -> list[dict[str, Any]]:
        """Build the message(s) that respond to the prior assistant turn's
        tool_calls. Returned LIST because OpenAI requires one `role: tool`
        message per tool_call, while Anthropic bundles all tool_results into
        a single user message with N content blocks. LLMAgent always uses
        `messages.extend(...)`.

        EVERY tool_call in the prior assistant turn must be answered, otherwise
        Anthropic returns 400; OpenAI similarly drops the conversation if
        tool_call_ids go unanswered.
        """

    @abstractmethod
    def build_user_text_message(self, text: str) -> dict[str, Any]:
        """Plain user message. Used by LLMAgent's no_tool_retry branch where
        the prior assistant turn had NO tool_calls (so we don't need
        tool_result protocol). Anthropic + OpenAI both accept the canonical
        `{"role":"user","content":text}`.
        """
```

**Keep `serialize_assistant_turn` as-is** (spec §4.4 + BR2-07 attaches the byte-identical contract to this method name; Phase 3a's default passthrough already returns `response.raw_assistant_turn` unchanged — verified by Task 4's replay round-trip test which reads from the same source. See "Spec Inconsistency #3" at top of plan for the full rationale).

`extract_reasoning_artifact` and `probe` stay as NotImplementedError stubs in this task; Tasks 4 / 5 / 6 will convert them to abstract methods one at a time. Add `from llm_poker_arena.agents.llm.types import ToolCall` to the imports (it's already imported as part of `LLMResponse` chain — verify by re-reading the file).

Read first: `src/llm_poker_arena/agents/llm/provider_base.py` start to confirm imports. Then edit.

If `ToolCall` is not imported at top of `provider_base.py`, add to the existing import:

```python
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    ToolCall,
)
```

- [ ] **Step 4: Implement the 3 new methods in `AnthropicProvider`**

Edit `src/llm_poker_arena/agents/llm/providers/anthropic_provider.py`. Append below `_normalize`:

```python
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
```

Add `ToolCall` to the import line at top:

```python
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    TokenCounts,
    ToolCall,
)
```

- [ ] **Step 5: Implement the 3 new methods in `MockLLMProvider`**

Edit `src/llm_poker_arena/agents/llm/providers/mock.py`. Append at the end of `MockLLMProvider`:

```python
    def build_assistant_message_for_replay(
        self, response: LLMResponse,
    ) -> dict[str, Any]:
        """Mirror Anthropic semantics so the existing 23 ReAct unit tests
        (which pre-date the provider abstraction) stay green."""
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
```

Add `ToolCall` to the import line:

```python
from llm_poker_arena.agents.llm.types import LLMResponse, ToolCall
```

- [ ] **Step 6: Replace LLMAgent inline helpers with provider calls**

Edit `src/llm_poker_arena/agents/llm/llm_agent.py`:

1. Delete the four module-level helper functions at the bottom of the file (lines 465–530): `_assistant_message`, `_user_text`, `_tool_result_user`, `_multi_tool_result_user`. Keep `_digest_messages` and `_action_tool_specs`.

2. Inside `_decide_inner`, replace each call site:

   - `messages.append(_assistant_message(response))` → `messages.append(self._provider.build_assistant_message_for_replay(response))`
   - `messages.append(_user_text("You must call exactly one action tool. Try again."))` → `messages.append(self._provider.build_user_text_message("You must call exactly one action tool. Try again."))`
   - `messages.append(_multi_tool_result_user(tool_calls=response.tool_calls, is_error=True, content=err_content))` → `messages.extend(self._provider.build_tool_result_messages(tool_calls=response.tool_calls, is_error=True, content=err_content))`
   - In the `rationale_required strict mode` branch (`messages.append(_tool_result_user(tool_use_id=tc.tool_use_id, is_error=True, content="Reasoning required..."))`) → `messages.extend(self._provider.build_tool_result_messages(tool_calls=(tc,), is_error=True, content="Reasoning required: write 1-3 short paragraphs of reasoning before calling the tool. Try again."))`
   - In the `illegal_action_retry` branch (`messages.append(_tool_result_user(tool_use_id=tc.tool_use_id, is_error=True, content=f"Illegal action: ..."))`) → `messages.extend(self._provider.build_tool_result_messages(tool_calls=(tc,), is_error=True, content=f"Illegal action: {v.reason}. Legal action tools: {[t.name for t in view.legal_actions.tools]}. Call exactly one of those next."))`

3. Verify the file compiles: re-read the whole `llm_agent.py` and confirm no lingering references to `_assistant_message` / `_tool_result_user` / `_multi_tool_result_user` / `_user_text`.

4. Remove the now-orphan import of `LLMResponse` if it's only used inside the deleted helper bodies. Re-check imports — `LLMResponse` is also referenced via `TYPE_CHECKING` block; leave that. Likely no import removal needed.

- [ ] **Step 7: Run the new builder tests + the existing ReAct suite**

Run: `.venv/bin/pytest tests/unit/test_provider_message_builders.py tests/unit/test_llm_agent_react_loop.py -v`

Expected:
- 5 new builder tests pass
- All 23 existing ReAct tests pass (MockLLMProvider mirrors Anthropic shape, so message accumulation in `messages` produces the same shape they did before)

If any ReAct test fails, the most likely cause is mismatched semantics in `MockLLMProvider`'s new methods — re-check Step 5 against Step 4 line-by-line.

- [ ] **Step 8: Run the full suite + lint + mypy**

Run: `.venv/bin/pytest tests/ -q --no-header -x`
Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/`

Expected: 316 pass + 1 skip (5 new builder tests on top of 311); ruff + mypy clean.

- [ ] **Step 9: Commit**

```bash
git add src/llm_poker_arena/agents/llm/provider_base.py \
        src/llm_poker_arena/agents/llm/providers/anthropic_provider.py \
        src/llm_poker_arena/agents/llm/providers/mock.py \
        src/llm_poker_arena/agents/llm/llm_agent.py \
        tests/unit/test_provider_message_builders.py
git commit -m "$(cat <<'EOF'
refactor(agents): provider owns message-format wire details (Phase 3b Task 3)

Move build_assistant_message_for_replay / build_tool_result_messages /
build_user_text_message from LLMAgent module-level helpers into
LLMProvider ABC. AnthropicProvider + MockLLMProvider implement the
Anthropic shape (tool_result content blocks bundled in one user
message). OpenAICompatibleProvider in Task 6 implements the OpenAI
shape (one role:tool message per tool_call). LLMAgent now uses
messages.extend(provider.build_tool_result_messages(...)) and is
provider-shape-agnostic.

Keep serialize_assistant_turn (spec §4.4 + BR2-07 contract attaches
to this method name); Phase 3a's default passthrough satisfies the
byte-identical guarantee structurally. build_assistant_message_for_replay
is the wire-format complement that LLMAgent calls at the message
boundary; both methods read from the same response.raw_assistant_turn.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: AnthropicProvider — `extract_reasoning_artifact` + thinking-block byte-identical preservation

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/providers/anthropic_provider.py` (implement `extract_reasoning_artifact`; rely on Phase 3a's default `serialize_assistant_turn` passthrough; ensure `_normalize` preserves thinking blocks via `model_dump()`)
- Modify: `src/llm_poker_arena/agents/llm/provider_base.py` (mark `extract_reasoning_artifact` abstract)
- Test: `tests/unit/test_reasoning_artifact_extraction.py` (NEW)

- [ ] **Step 1: Write the failing test (AnthropicProvider thinking-block extraction + replay)**

Create `tests/unit/test_reasoning_artifact_extraction.py`:

```python
"""Unit tests for provider-specific reasoning artifact extraction + byte-identical
thinking-block preservation across replay."""
from __future__ import annotations

from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.llm.types import (
    AssistantTurn, LLMResponse, ReasoningArtifactKind,
    TokenCounts, ToolCall,
)


def _resp_with_thinking_blocks() -> LLMResponse:
    """Fake Anthropic response carrying extended-thinking blocks. The blocks
    have provider-specific shape (signature, etc.) that MUST round-trip.
    """
    return LLMResponse(
        provider="anthropic", model="claude-opus-4-7",
        stop_reason="tool_use",
        tool_calls=(
            ToolCall(name="fold", args={}, tool_use_id="toolu_x"),
        ),
        text_content="My final answer: fold.",
        tokens=TokenCounts(input_tokens=10, output_tokens=20,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic",
            blocks=(
                {
                    "type": "thinking",
                    "thinking": "Step 1: pot is 150, I have 72o, fold is correct.",
                    "signature": "sig_step1_payload_base64==",
                },
                {
                    "type": "redacted_thinking",
                    "data": "redacted_payload_base64==",
                },
                {
                    "type": "text",
                    "text": "My final answer: fold.",
                },
                {
                    "type": "tool_use",
                    "id": "toolu_x",
                    "name": "fold",
                    "input": {},
                },
            ),
        ),
    )


def test_anthropic_extract_reasoning_artifact_returns_thinking_and_redacted() -> None:
    provider = AnthropicProvider(model="claude-opus-4-7", api_key="sk-test")
    arts = provider.extract_reasoning_artifact(_resp_with_thinking_blocks())
    assert isinstance(arts, tuple)
    assert len(arts) == 2
    a0, a1 = arts
    assert a0.kind == ReasoningArtifactKind.THINKING_BLOCK
    assert a0.content == "Step 1: pot is 150, I have 72o, fold is correct."
    assert a0.provider_raw_index == 0
    assert a1.kind == ReasoningArtifactKind.REDACTED
    # Per spec §4.6, redacted_thinking has no plaintext rationale — content is
    # None. The opaque `data` field stays in raw_assistant_turn.blocks for
    # forensic access (and is preserved byte-identical across replay so the
    # next API call accepts it), but it's NOT exposed as human-readable text.
    assert a1.content is None
    assert a1.provider_raw_index == 1


def test_anthropic_extract_returns_empty_tuple_when_no_thinking_blocks() -> None:
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    plain = LLMResponse(
        provider="anthropic", model="claude-haiku-4-5",
        stop_reason="end_turn", tool_calls=(),
        text_content="ok", tokens=TokenCounts.zero(),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic",
            blocks=({"type": "text", "text": "ok"},),
        ),
    )
    arts = provider.extract_reasoning_artifact(plain)
    assert arts == ()


def test_anthropic_serialize_assistant_turn_preserves_thinking_blocks_byte_identical() -> None:
    """spec §4.4 BR2-07: thinking blocks must round-trip identically when we
    re-send the assistant turn in the next ReAct iteration."""
    provider = AnthropicProvider(model="claude-opus-4-7", api_key="sk-test")
    resp = _resp_with_thinking_blocks()
    msg = provider.build_assistant_message_for_replay(resp)
    # The blocks list inside the constructed message must be IDENTICAL to
    # the raw blocks tuple — not a re-projection that drops fields.
    assert msg["content"] == list(resp.raw_assistant_turn.blocks)
    # In particular, thinking block's `signature` field is preserved (this
    # is what Anthropic uses to validate the thinking block on next request).
    thinking_block = next(b for b in msg["content"] if b["type"] == "thinking")
    assert thinking_block["signature"] == "sig_step1_payload_base64=="
    redacted = next(b for b in msg["content"] if b["type"] == "redacted_thinking")
    assert redacted["data"] == "redacted_payload_base64=="


def test_anthropic_encrypted_thinking_kind_classified_correctly() -> None:
    """Some Anthropic releases use `encrypted_thinking` instead of
    redacted_thinking. Both have opaque content; we map them to the
    appropriate ReasoningArtifactKind per spec §4.6."""
    provider = AnthropicProvider(model="claude-opus-4-7", api_key="sk-test")
    resp = LLMResponse(
        provider="anthropic", model="claude-opus-4-7",
        stop_reason="end_turn", tool_calls=(),
        text_content="", tokens=TokenCounts.zero(),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic",
            blocks=(
                {"type": "encrypted_thinking",
                 "data": "encrypted_blob=="},
            ),
        ),
    )
    arts = provider.extract_reasoning_artifact(resp)
    assert len(arts) == 1
    assert arts[0].kind == ReasoningArtifactKind.ENCRYPTED
    assert arts[0].content == "encrypted_blob=="


def test_anthropic_normalize_preserves_real_thinking_block_signature() -> None:
    """End-to-end: build a real Anthropic-SDK ThinkingBlock, run it through
    `_normalize()`, and verify the normalized AssistantTurn.blocks dict
    preserves the `signature` field that Anthropic uses to validate the
    thinking block on the next request. This catches the case where
    `model_dump()` would drop SDK-specific fields — codex audit NIT-N2."""
    from anthropic.types import (
        TextBlock, ThinkingBlock, ToolUseBlock, Usage,
    )

    class _FakeAnthropicResp:
        model = "claude-opus-4-7"
        stop_reason = "tool_use"
        # Construct real SDK block instances. Pydantic round-trip via
        # model_dump() must preserve `signature` and `thinking` fields.
        content = [
            ThinkingBlock(
                type="thinking",
                thinking="Considering pot odds...",
                signature="real_sdk_sig_payload==",
            ),
            TextBlock(type="text", text="Final answer."),
            ToolUseBlock(type="tool_use", id="toolu_real",
                         name="fold", input={}),
        ]
        usage = Usage(input_tokens=10, output_tokens=5)

    provider = AnthropicProvider(model="claude-opus-4-7", api_key="sk-test")
    resp = provider._normalize(_FakeAnthropicResp())  # noqa: SLF001
    # The normalized blocks tuple must contain the thinking block dict
    # WITH the `signature` field intact — otherwise the next API call
    # would fail Anthropic's thinking-block validation.
    thinking_dump = next(
        b for b in resp.raw_assistant_turn.blocks if b.get("type") == "thinking"
    )
    assert thinking_dump["thinking"] == "Considering pot odds..."
    assert thinking_dump["signature"] == "real_sdk_sig_payload=="
    # And extract_reasoning_artifact lifts it correctly.
    arts = provider.extract_reasoning_artifact(resp)
    assert len(arts) == 1
    assert arts[0].kind == ReasoningArtifactKind.THINKING_BLOCK
    assert arts[0].content == "Considering pot odds..."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_reasoning_artifact_extraction.py -v`

Expected: FAIL — `extract_reasoning_artifact` raises `NotImplementedError("Phase 3b feature")`.

- [ ] **Step 3: Implement `extract_reasoning_artifact` in `AnthropicProvider`**

Edit `src/llm_poker_arena/agents/llm/providers/anthropic_provider.py`. Append below `build_user_text_message`:

```python
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
                # checks must reject it (see _has_text_rationale_artifact in LLMAgent).
                out.append(ReasoningArtifact(
                    kind=ReasoningArtifactKind.ENCRYPTED,
                    content=str(block.get("data") or ""),
                    provider_raw_index=idx,
                ))
        return tuple(out)
```

Add to imports at top of `anthropic_provider.py`:

```python
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    ReasoningArtifact,
    ReasoningArtifactKind,
    TokenCounts,
    ToolCall,
)
```

- [ ] **Step 4: Mark `extract_reasoning_artifact` abstract in `LLMProvider`**

Edit `src/llm_poker_arena/agents/llm/provider_base.py`. Replace the existing stub:

```python
    def extract_reasoning_artifact(self, response: LLMResponse) -> Any:  # noqa: ANN401
        """spec §4.4: provider-specific reasoning extraction. 3a stub."""
        raise NotImplementedError("Phase 3b feature — reasoning artifact extraction")
```

with:

```python
    @abstractmethod
    def extract_reasoning_artifact(
        self, response: LLMResponse,
    ) -> tuple[ReasoningArtifact, ...]:
        """spec §4.6: extract provider-specific reasoning artifacts (Anthropic
        thinking blocks, DeepSeek `reasoning_content`, OpenAI summary). Return
        empty tuple if the response carries no reasoning artifact. Each
        artifact carries `provider_raw_index` for forensic traceability."""
```

Update `provider_base.py` imports:

```python
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    ReasoningArtifact,
    ToolCall,
)
```

Now MockLLMProvider must implement it. Edit `src/llm_poker_arena/agents/llm/providers/mock.py`. Append:

```python
    def extract_reasoning_artifact(
        self, response: LLMResponse,
    ) -> tuple[ReasoningArtifact, ...]:
        """Mock has no reasoning artifacts unless the test explicitly puts
        them into raw_assistant_turn.blocks (which mock tests don't)."""
        return ()
```

Add to imports:

```python
from llm_poker_arena.agents.llm.types import LLMResponse, ReasoningArtifact, ToolCall
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_reasoning_artifact_extraction.py -v`

Expected: 4 tests pass.

- [ ] **Step 6: Run the full suite + lint + mypy**

Run: `.venv/bin/pytest tests/ -q --no-header -x && .venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/`

Expected: 321 pass + 1 skip (5 new artifact-extraction tests including the real-SDK ThinkingBlock round-trip on top of 316); ruff + mypy clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/agents/llm/providers/anthropic_provider.py \
        src/llm_poker_arena/agents/llm/providers/mock.py \
        src/llm_poker_arena/agents/llm/provider_base.py \
        tests/unit/test_reasoning_artifact_extraction.py
git commit -m "$(cat <<'EOF'
feat(providers): Anthropic extract_reasoning_artifact + byte-identical thinking blocks (Phase 3b Task 4)

Walks raw_assistant_turn.blocks for thinking / redacted_thinking /
encrypted_thinking, returns tuple[ReasoningArtifact] with kind +
content + provider_raw_index. Verifies build_assistant_message_for_replay
preserves thinking blocks (signature/data fields) byte-identical so
extended thinking can round-trip across ReAct iterations (BR2-07).

Mark extract_reasoning_artifact abstract on LLMProvider; MockLLMProvider
returns empty tuple.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: AnthropicProvider — `probe()`

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/providers/anthropic_provider.py` (implement `probe`)
- Modify: `src/llm_poker_arena/agents/llm/provider_base.py` (mark `probe` abstract)
- Modify: `src/llm_poker_arena/agents/llm/providers/mock.py` (implement `probe`)
- Test: `tests/unit/test_anthropic_probe.py` (NEW; uses monkeypatched SDK — no network)
- Test: `tests/integration/test_llm_session_real_anthropic.py` (extend with assertion that probe runs successfully when ANTHROPIC_INTEGRATION_TEST=1)

- [ ] **Step 1: Write the failing test (probe with monkeypatched SDK)**

Create `tests/unit/test_anthropic_probe.py`:

```python
"""Test AnthropicProvider.probe() with a fake SDK response. No network."""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from llm_poker_arena.agents.llm.providers.anthropic_provider import (
    AnthropicProvider,
)
from llm_poker_arena.agents.llm.types import ObservedCapability


class _FakeUsage:
    input_tokens = 5
    output_tokens = 3
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _FakeBlock:
    def __init__(self, type_: str, text: str = "") -> None:
        self.type = type_
        self.text = text

    def model_dump(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type}
        if self.type == "text":
            d["text"] = self.text
        return d


class _FakeResp:
    model = "claude-haiku-4-5"
    stop_reason = "end_turn"
    content = [_FakeBlock("text", "ok")]
    usage = _FakeUsage()


def test_anthropic_probe_returns_observed_capability_with_seed_false() -> None:
    """Anthropic does not accept the `seed` kwarg; probe records seed_accepted=False
    statically. Reasoning_kinds=() because we don't enable extended thinking."""
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key="sk-test")
    fake_create = AsyncMock(return_value=_FakeResp())
    provider._client = MagicMock()  # type: ignore[assignment]
    provider._client.messages = MagicMock()
    provider._client.messages.create = fake_create

    cap = asyncio.run(provider.probe())
    assert isinstance(cap, ObservedCapability)
    assert cap.provider == "anthropic"
    assert cap.seed_accepted is False
    assert cap.tool_use_with_thinking_ok is False
    # spec §4.6: probe observed no artifacts → (UNAVAILABLE,) not empty.
    from llm_poker_arena.agents.llm.types import ReasoningArtifactKind
    assert cap.reasoning_kinds == (ReasoningArtifactKind.UNAVAILABLE,)
    # extra_flags must record that thinking + tool_use was NOT actually
    # tested (vs "tested and failed"). HR2-03 honest reporting.
    assert cap.extra_flags["tool_use_with_thinking_probed"] is False
    assert cap.extra_flags["extended_thinking_enabled"] is False
    # probed_at is an ISO timestamp; should parse-back without error.
    assert "T" in cap.probed_at and cap.probed_at.endswith("Z")
    # The probe should have called the SDK exactly once with a minimal prompt.
    assert fake_create.await_count == 1
    kwargs = fake_create.await_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs["max_tokens"] <= 32  # cheap probe
    assert "seed" not in kwargs  # we don't pass seed because Anthropic ignores it
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_anthropic_probe.py -v`

Expected: FAIL — `probe()` raises `NotImplementedError("Phase 3b feature")`.

- [ ] **Step 3: Implement `probe()` in `AnthropicProvider`**

Edit `src/llm_poker_arena/agents/llm/providers/anthropic_provider.py`. Append:

```python
    async def probe(self) -> ObservedCapability:
        """spec §4.4 HR2-03: minimal cheap probe with HONEST capability
        reporting. Anthropic does not accept `seed` (Anthropic SDK has no
        seed kwarg → seed_accepted=False is a static fact, not a test).
        Phase 3b does NOT enable extended thinking on real calls, so the
        observed reasoning_kinds is `()` and tool_use_with_thinking is
        `not_tested` (flag in extra_flags). A future "Phase 3b.1: extended
        thinking enablement" should extend this probe to actually drive
        a thinking-enabled tool_use round and observe behavior.
        """
        from datetime import UTC, datetime
        try:
            await self._client.messages.create(
                model=self._model,
                max_tokens=8,
                messages=cast("Any", [{"role": "user", "content": "ok"}]),
            )
        except (APITimeoutError, RateLimitError) as e:
            raise ProviderTransientError(f"probe transient: {e}") from e
        except APIStatusError as e:
            raise ProviderPermanentError(f"probe permanent: {e}") from e
        probed_at = (
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        )
        return ObservedCapability(
            provider="anthropic",
            probed_at=probed_at,
            # spec §4.6: probe observed no reasoning artifacts → UNAVAILABLE
            # (not empty tuple — empty would mean "didn't probe"). Anthropic
            # CAN emit reasoning when extended thinking is enabled, but 3b
            # doesn't enable it, so the observed capability is honestly
            # "unavailable in current config".
            reasoning_kinds=(ReasoningArtifactKind.UNAVAILABLE,),
            seed_accepted=False,  # Anthropic SDK has no seed kwarg, factually
            tool_use_with_thinking_ok=False,  # see extra_flags["tool_use_with_thinking_probed"]
            extra_flags={
                "tool_use_with_thinking_probed": False,
                "extended_thinking_enabled": False,
            },
        )
```

Add `ObservedCapability` to imports at top of `anthropic_provider.py`:

```python
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    ObservedCapability,
    ReasoningArtifact,
    ReasoningArtifactKind,
    TokenCounts,
    ToolCall,
)
```

- [ ] **Step 4: Mark `probe` abstract on `LLMProvider`**

Edit `src/llm_poker_arena/agents/llm/provider_base.py`. Replace the existing stub:

```python
    async def probe(self) -> Any:  # noqa: ANN401
        """spec §4.4 HR2-03: live capability probe. 3a stub."""
        raise NotImplementedError("Phase 3b feature — capability probe")
```

with:

```python
    @abstractmethod
    async def probe(self) -> ObservedCapability:
        """spec §4.4 HR2-03: minimal cheap probe; called once per session at
        startup. Result is written to meta.json.provider_capabilities. Used
        to surface real provider behavior (vs the stale spec capability table)
        for cross-provider analysis."""
```

Update imports:

```python
from llm_poker_arena.agents.llm.types import (
    AssistantTurn,
    LLMResponse,
    ObservedCapability,
    ReasoningArtifact,
    ToolCall,
)
```

- [ ] **Step 5: Implement `probe()` on `MockLLMProvider`**

Edit `src/llm_poker_arena/agents/llm/providers/mock.py`. Append:

```python
    async def probe(self) -> ObservedCapability:
        """Mock probe: no network, returns a deterministic fake capability."""
        from datetime import UTC, datetime
        return ObservedCapability(
            provider="mock",
            probed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            reasoning_kinds=(),
            seed_accepted=True,
            tool_use_with_thinking_ok=True,
            extra_flags={"mock": True},
        )
```

Add to imports:

```python
from llm_poker_arena.agents.llm.types import (
    LLMResponse, ObservedCapability, ReasoningArtifact, ToolCall,
)
```

- [ ] **Step 6: Run the new probe test + extend the gated real-Anthropic test**

Run: `.venv/bin/pytest tests/unit/test_anthropic_probe.py -v`

Expected: PASS (1 test).

Now extend `tests/integration/test_llm_session_real_anthropic.py` to ALSO assert that probe ran. Read it first; append a new test below `test_real_claude_haiku_plays_one_hand`:

```python
def test_real_anthropic_probe_returns_observed_capability() -> None:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    cap = asyncio.run(provider.probe())
    assert cap.provider == "anthropic"
    assert cap.seed_accepted is False
    assert cap.probed_at.endswith("Z")
```

- [ ] **Step 7: Run the full suite + lint + mypy**

Run: `.venv/bin/pytest tests/ -q --no-header -x && .venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/`

Expected: 322 pass + 2 skip (1 new unit test + 1 new gated probe test added to test_llm_session_real_anthropic.py joins the original gated session test in skip; on top of 321 after Task 4); ruff + mypy clean.

- [ ] **Step 8: Verify against real Anthropic API (gated)**

Run:

```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_llm_session_real_anthropic.py -v
```

Expected: both tests pass; cost ~$0.01.

- [ ] **Step 9: Commit**

```bash
git add src/llm_poker_arena/agents/llm/providers/anthropic_provider.py \
        src/llm_poker_arena/agents/llm/providers/mock.py \
        src/llm_poker_arena/agents/llm/provider_base.py \
        tests/unit/test_anthropic_probe.py \
        tests/integration/test_llm_session_real_anthropic.py
git commit -m "$(cat <<'EOF'
feat(providers): AnthropicProvider.probe() returns ObservedCapability (Phase 3b Task 5)

spec §4.4 HR2-03. Minimal one-message probe; records seed_accepted=False
(Anthropic ignores seed) and reasoning_kinds=() (extended thinking off
by default). Probe is async and raises Provider*Error like complete().

Mark probe abstract on LLMProvider; MockLLMProvider returns a
deterministic fake.

Gated real-Anthropic test verifies probe survives the live API.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `OpenAICompatibleProvider` — covers OpenAI Chat + DeepSeek

**Files:**
- Create: `src/llm_poker_arena/agents/llm/providers/openai_compatible.py`
- Test: `tests/unit/test_openai_compatible_provider.py` (NEW; monkeypatched SDK — no network)
- Test: `tests/unit/test_reasoning_artifact_extraction.py` (extend with DeepSeek-R1 case)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_openai_compatible_provider.py`:

```python
"""Unit tests for OpenAICompatibleProvider, covering both OpenAI Chat and
DeepSeek (OpenAI-compatible at base_url=https://api.deepseek.com/v1).
SDK calls are monkeypatched — no network."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


from llm_poker_arena.agents.llm.provider_base import (
    ProviderPermanentError, ProviderTransientError,
)
from llm_poker_arena.agents.llm.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from llm_poker_arena.agents.llm.types import (
    LLMResponse, ObservedCapability, ReasoningArtifactKind, ToolCall,
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
        self, content: str | None = None,
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
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments}}
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
    *, base_url: str | None = None, provider_name_value: str = "openai",
    model: str = "gpt-4o-mini",
) -> tuple[OpenAICompatibleProvider, AsyncMock]:
    p = OpenAICompatibleProvider(
        provider_name_value=provider_name_value, model=model,
        api_key="sk-test", base_url=base_url,
    )
    fake_create = AsyncMock(return_value=fake_resp)
    p._client = MagicMock()  # type: ignore[assignment]
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
    out = asyncio.run(p.complete(
        system="sys", messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "fold", "description": "fold the hand",
                "input_schema": {"type": "object", "properties": {},
                                  "additionalProperties": False}}],
        temperature=0.5, seed=42,
    ))
    assert isinstance(out, LLMResponse)
    assert out.provider == "openai"
    assert len(out.tool_calls) == 1
    assert out.tool_calls[0] == ToolCall(name="fold", args={},
                                          tool_use_id="call_abc")
    assert out.text_content == "I'll fold."
    assert out.tokens.input_tokens == 25
    assert out.tokens.output_tokens == 10
    assert out.tokens.cache_read_input_tokens == 0
    assert out.stop_reason == "tool_use"


def test_openai_complete_parses_arguments_json_to_dict() -> None:
    msg = _FakeMessage(
        content=None,
        tool_calls=[_FakeToolCall("call_x", "raise_to",
                                   '{"amount": 300}')],
    )
    resp = _FakeChatResp(_FakeChoice(msg), model="gpt-4o-mini")
    p, _ = _make_provider_with_fake_create(resp)
    out = asyncio.run(p.complete(
        system=None, messages=[{"role": "user", "content": "hi"}],
        tools=[], temperature=0.5, seed=None,
    ))
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
    out = asyncio.run(p.complete(
        system=None, messages=[{"role": "user", "content": "hi"}],
        tools=[], temperature=0.5, seed=None,
    ))
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

    p = OpenAICompatibleProvider(provider_name_value="openai",
                                  model="gpt-4o-mini", api_key="sk-test")
    fake_create = AsyncMock(side_effect=_FakeAPIStatus(503))
    p._client = MagicMock()  # type: ignore[assignment]
    p._client.chat = MagicMock()
    p._client.chat.completions = MagicMock()
    p._client.chat.completions.create = fake_create
    with pytest.raises(ProviderTransientError):
        asyncio.run(p.complete(system=None, messages=[],
                                tools=[], temperature=0.5, seed=None))


def test_openai_4xx_auth_raises_permanent_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """401 Auth → ProviderPermanentError (NOT mistaken for seed-unsupported).
    Critical regression: codex audit flagged that catching every APIStatusError
    misclassified 4xx auth as seed rejection."""
    from llm_poker_arena.agents.llm.providers import openai_compatible
    monkeypatch.setattr(openai_compatible, "APIStatusError", _FakeAPIStatus)
    monkeypatch.setattr(openai_compatible, "BadRequestError", _FakeBadRequest)

    p = OpenAICompatibleProvider(provider_name_value="openai",
                                  model="gpt-4o-mini", api_key="sk-test")
    fake_create = AsyncMock(side_effect=_FakeAPIStatus(401, "auth failed"))
    p._client = MagicMock()  # type: ignore[assignment]
    p._client.chat = MagicMock()
    p._client.chat.completions = MagicMock()
    p._client.chat.completions.create = fake_create
    with pytest.raises(ProviderPermanentError):
        asyncio.run(p.complete(system=None, messages=[],
                                tools=[], temperature=0.5, seed=42))


def test_openai_400_seed_unsupported_retries_without_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the API rejects seed with a 'unknown parameter: seed' message,
    complete() should retry once without seed and latch _seed_known_unsupported
    so subsequent calls drop seed automatically. Codex audit fix for I5."""
    from llm_poker_arena.agents.llm.providers import openai_compatible
    monkeypatch.setattr(openai_compatible, "APIStatusError", _FakeAPIStatus)
    monkeypatch.setattr(openai_compatible, "BadRequestError", _FakeBadRequest)

    p = OpenAICompatibleProvider(provider_name_value="openai",
                                  model="gpt-4o-mini", api_key="sk-test")
    # Build a real successful response for the retry path.
    msg = _FakeMessage(content="ok", tool_calls=None)
    success = _FakeChatResp(_FakeChoice(msg, finish_reason="stop"),
                             model="gpt-4o-mini")
    call_seq = [
        _FakeBadRequest("Unknown parameter: seed"),
        success,
    ]
    fake_create = AsyncMock(side_effect=call_seq)
    p._client = MagicMock()  # type: ignore[assignment]
    p._client.chat = MagicMock()
    p._client.chat.completions = MagicMock()
    p._client.chat.completions.create = fake_create

    out = asyncio.run(p.complete(
        system=None, messages=[{"role": "user", "content": "hi"}],
        tools=[], temperature=0.5, seed=42,
    ))
    assert out.text_content == "ok"
    assert p._seed_known_unsupported is True
    # First call: kwargs included seed; second call: kwargs did NOT include seed
    assert fake_create.await_count == 2
    first_kwargs = fake_create.await_args_list[0].kwargs
    second_kwargs = fake_create.await_args_list[1].kwargs
    assert first_kwargs.get("seed") == 42
    assert "seed" not in second_kwargs


def test_openai_400_non_seed_bad_request_raises_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 400 BadRequest that is NOT about seed (e.g. malformed messages)
    must NOT trigger the retry-without-seed path; it should raise
    ProviderPermanentError. Codex audit fix for I4."""
    from llm_poker_arena.agents.llm.providers import openai_compatible
    monkeypatch.setattr(openai_compatible, "APIStatusError", _FakeAPIStatus)
    monkeypatch.setattr(openai_compatible, "BadRequestError", _FakeBadRequest)

    p = OpenAICompatibleProvider(provider_name_value="openai",
                                  model="gpt-4o-mini", api_key="sk-test")
    fake_create = AsyncMock(side_effect=_FakeBadRequest(
        "Invalid 'messages[0].role': must be one of system, user, assistant"
    ))
    p._client = MagicMock()  # type: ignore[assignment]
    p._client.chat = MagicMock()
    p._client.chat.completions = MagicMock()
    p._client.chat.completions.create = fake_create
    with pytest.raises(ProviderPermanentError):
        asyncio.run(p.complete(system=None, messages=[],
                                tools=[], temperature=0.5, seed=42))
    # Single call only — no retry attempted.
    assert fake_create.await_count == 1
    # Did NOT latch the seed-unsupported flag.
    assert p._seed_known_unsupported is None


def test_openai_build_tool_result_messages_returns_one_per_call() -> None:
    """OpenAI requires N separate role:tool messages, one per tool_call."""
    p = OpenAICompatibleProvider(provider_name_value="openai",
                                  model="gpt-4o-mini", api_key="sk-test")
    tcs = (
        ToolCall(name="fold", args={}, tool_use_id="call_a"),
        ToolCall(name="raise_to", args={"amount": 300}, tool_use_id="call_b"),
    )
    msgs = p.build_tool_result_messages(
        tool_calls=tcs, is_error=True, content="bad call",
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
    out = asyncio.run(p.complete(
        system=None, messages=[{"role": "user", "content": "hi"}],
        tools=[], temperature=0.5, seed=None,
    ))
    replay = p.build_assistant_message_for_replay(out)
    assert replay["role"] == "assistant"
    assert replay["content"] == "ok"
    assert replay["tool_calls"][0]["id"] == "call_x"
    assert replay["tool_calls"][0]["function"]["name"] == "fold"


def test_openai_build_user_text_message_returns_plain_user() -> None:
    p = OpenAICompatibleProvider(provider_name_value="openai",
                                  model="gpt-4o-mini", api_key="sk-test")
    assert p.build_user_text_message("hi") == {"role": "user", "content": "hi"}


def test_openai_provider_name_passthrough() -> None:
    p = OpenAICompatibleProvider(provider_name_value="deepseek",
                                  model="deepseek-chat", api_key="sk-test",
                                  base_url="https://api.deepseek.com/v1")
    assert p.provider_name() == "deepseek"


def test_deepseek_reasoner_extracts_reasoning_content_as_raw_artifact() -> None:
    msg = _FakeMessage(
        content="The answer is fold.",
        tool_calls=[_FakeToolCall("call_z", "fold", "{}")],
        reasoning_content="Chain of thought: pot odds < equity, fold is +EV.",
    )
    resp = _FakeChatResp(_FakeChoice(msg), model="deepseek-reasoner")
    p, _ = _make_provider_with_fake_create(
        resp, base_url="https://api.deepseek.com/v1",
        provider_name_value="deepseek", model="deepseek-reasoner",
    )
    out = asyncio.run(p.complete(
        system=None, messages=[{"role": "user", "content": "hi"}],
        tools=[], temperature=0.5, seed=None,
    ))
    arts = p.extract_reasoning_artifact(out)
    assert len(arts) == 1
    assert arts[0].kind == ReasoningArtifactKind.RAW
    assert arts[0].content == "Chain of thought: pot odds < equity, fold is +EV."
    assert arts[0].provider_raw_index == 0


def test_deepseek_chat_no_reasoning_content_returns_empty_tuple() -> None:
    msg = _FakeMessage(content="ok",
                       tool_calls=[_FakeToolCall("c", "fold", "{}")])
    resp = _FakeChatResp(_FakeChoice(msg), model="deepseek-chat")
    p, _ = _make_provider_with_fake_create(
        resp, base_url="https://api.deepseek.com/v1",
        provider_name_value="deepseek", model="deepseek-chat",
    )
    out = asyncio.run(p.complete(
        system=None, messages=[{"role": "user", "content": "hi"}],
        tools=[], temperature=0.5, seed=None,
    ))
    assert p.extract_reasoning_artifact(out) == ()


def test_openai_probe_returns_observed_capability() -> None:
    msg = _FakeMessage(content="ok", tool_calls=None)
    resp = _FakeChatResp(_FakeChoice(msg, finish_reason="stop"),
                         model="gpt-4o-mini")
    p, fake = _make_provider_with_fake_create(resp)
    cap = asyncio.run(p.probe())
    assert isinstance(cap, ObservedCapability)
    assert cap.provider == "openai"
    # Probe must call create at least once.
    assert fake.await_count >= 1
    # We pass seed=42 in the probe call to test acceptance.
    kwargs = fake.await_args.kwargs
    assert kwargs.get("seed") == 42
    # No reasoning_content on the fake → reasoning_kinds=(UNAVAILABLE,)
    # (probe observed nothing — record explicitly per spec §4.6).
    assert cap.reasoning_kinds == (ReasoningArtifactKind.UNAVAILABLE,)


def test_deepseek_reasoner_probe_records_raw_kind() -> None:
    msg = _FakeMessage(content="ok", tool_calls=None,
                       reasoning_content="meta thinking")
    resp = _FakeChatResp(_FakeChoice(msg, finish_reason="stop"),
                         model="deepseek-reasoner")
    p, _ = _make_provider_with_fake_create(
        resp, base_url="https://api.deepseek.com/v1",
        provider_name_value="deepseek", model="deepseek-reasoner",
    )
    cap = asyncio.run(p.probe())
    assert ReasoningArtifactKind.RAW in cap.reasoning_kinds
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_openai_compatible_provider.py -v`

Expected: FAIL — `ImportError: cannot import name 'OpenAICompatibleProvider' from 'llm_poker_arena.agents.llm.providers.openai_compatible'` (file doesn't exist).

- [ ] **Step 3: Implement `OpenAICompatibleProvider`**

Create `src/llm_poker_arena/agents/llm/providers/openai_compatible.py`:

```python
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
                    "parameters": t.get("input_schema",
                                         {"type": "object", "properties": {}}),
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
            "max_tokens": self._max_tokens,
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
                    status = getattr(getattr(e2, "response", None),
                                      "status_code", None)
                    if status is not None and status >= 500:
                        raise ProviderTransientError(
                            f"{status}: {e2}") from e2
                    if status == 429:
                        raise ProviderTransientError(
                            f"429 rate limited: {e2}") from e2
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
            tool_calls.append(ToolCall(
                name=tc.function.name,
                args=args_dict,
                tool_use_id=tc.id,
            ))

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
        raw_msg_dict = (
            msg.model_dump() if hasattr(msg, "model_dump") else dict(msg)
        )

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
        self, response: LLMResponse,
    ) -> dict[str, Any]:
        """Reconstruct the OpenAI assistant message from raw blocks. The raw
        blocks tuple has exactly ONE element (the message dict), unlike
        Anthropic's per-block list.
        """
        raw_blocks = response.raw_assistant_turn.blocks
        if raw_blocks:
            raw_msg = dict(raw_blocks[0])
            # `reasoning_content` is informational only — strip it when
            # replaying so OpenAI/DeepSeek don't see it back.
            raw_msg.pop("reasoning_content", None)
            return raw_msg
        # Fallback: synthesize from text + tool_calls (used when raw is empty).
        out: dict[str, Any] = {
            "role": "assistant", "content": response.text_content or None,
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
        self, response: LLMResponse,
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
        return (ReasoningArtifact(
            kind=ReasoningArtifactKind.RAW,
            content=str(rc),
            provider_raw_index=0,
        ),)

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
            "max_tokens": 8,
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

        probed_at = (
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        )
        return ObservedCapability(
            provider=self._provider_name,
            probed_at=probed_at,
            reasoning_kinds=tuple(observed_kinds),
            seed_accepted=seed_accepted,
            tool_use_with_thinking_ok=False,  # see extra_flags
            extra_flags={
                "base_url": str(self._client.base_url)
                            if hasattr(self._client, "base_url") else "",
                "tool_use_with_thinking_probed": False,
                "system_fingerprint": system_fingerprint or "",
            },
        )


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
    )
    return any(p in msg for p in seed_phrases)


__all__ = ["OpenAICompatibleProvider"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_openai_compatible_provider.py -v`

Expected: 13 tests pass. The `str(self._client.base_url)` cast on `extra_flags["base_url"]` already handles the case where the OpenAI SDK exposes `base_url` as `httpx.URL` (Pydantic `dict[str, Any]` only accepts JSON-serializable values, so URL→str is required).

- [ ] **Step 5: Run the full suite + lint + mypy**

Run: `.venv/bin/pytest tests/ -q --no-header -x && .venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/`

Expected: 337 pass + 2 skip (15 new OpenAI tests including the seed-unsupported retry + non-seed bad-request paths from codex audit, on top of 322 after Task 5); ruff + mypy clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/agents/llm/providers/openai_compatible.py \
        tests/unit/test_openai_compatible_provider.py
git commit -m "$(cat <<'EOF'
feat(providers): OpenAICompatibleProvider covers OpenAI Chat + DeepSeek (Phase 3b Task 6)

Single class parameterized by base_url:
  - base_url=None → OpenAI canonical endpoint
  - base_url=https://api.deepseek.com/v1 → DeepSeek (OpenAI-compatible)

Wire format:
  - Tool spec: {"type":"function", "function":{...}} (vs Anthropic's
    {"name":..., "input_schema":...}); converted in complete().
  - Tool calls: assistant.tool_calls[*] with JSON-string arguments;
    parsed to dict in _normalize. Malformed JSON → empty args (validator
    will reject as illegal action, triggering retry).
  - Tool result: one role:tool message per tool_call_id (vs Anthropic's
    bundled user message with N tool_result blocks). is_error encoded
    as [ERROR] prefix in content.
  - Reasoning: DeepSeek-Reasoner's `reasoning_content` field surfaced
    as ReasoningArtifact(kind=RAW); other models → empty tuple.
  - Probe: tries seed=42; falls back to no-seed on bad-request and
    records seed_accepted=False.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Session probe wiring → `meta.json.provider_capabilities`

**Files:**
- Modify: `src/llm_poker_arena/storage/meta.py:28-62` (`build_session_meta` accepts new kwarg)
- Modify: `src/llm_poker_arena/session/session.py:112-138` (probe each unique LLM provider at start of `run()`)
- Test: `tests/integration/test_llm_session_mock.py` (extend; verify mock provider's capability lands in meta.json)

- [ ] **Step 1: Write the failing test**

Read `tests/integration/test_llm_session_mock.py` first to find a good insertion point. Append a new test:

```python
def test_session_writes_provider_capabilities_to_meta(tmp_path: Path) -> None:
    """When LLM agents are present, meta.json.provider_capabilities maps
    seat_str → ObservedCapability dump."""
    from llm_poker_arena.agents.llm.llm_agent import LLMAgent
    from llm_poker_arena.agents.llm.providers.mock import (
        MockLLMProvider, MockResponseScript,
    )
    from llm_poker_arena.agents.llm.types import (
        AssistantTurn, LLMResponse, TokenCounts, ToolCall,
    )
    from llm_poker_arena.agents.random_agent import RandomAgent

    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=False,
        opponent_stats_min_samples=30, rng_seed=42,
    )

    def _legal_resp(name: str, tool_use_id: str) -> LLMResponse:
        return LLMResponse(
            provider="mock", model="m1", stop_reason="tool_use",
            tool_calls=(ToolCall(name=name, args={}, tool_use_id=tool_use_id),),
            text_content="r", tokens=TokenCounts.zero(),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        )
    # 200 is a generous buffer for this fold-script smoke test (LLMAgent
    # caps each decision at MAX_STEPS=5 internal iterations; this script
    # serves fold every time so retries shouldn't fire, but 200 absorbs
    # any unexpected behavior without exhausting the script).
    script_a = MockResponseScript(
        responses=tuple(_legal_resp("fold", f"t_a_{i}") for i in range(200)),
    )
    script_b = MockResponseScript(
        responses=tuple(_legal_resp("fold", f"t_b_{i}") for i in range(200)),
    )
    provider_a = MockLLMProvider(script=script_a)
    provider_b = MockLLMProvider(script=script_b)
    llm_a = LLMAgent(provider=provider_a, model="m1", temperature=0.7)
    llm_b = LLMAgent(provider=provider_b, model="m2", temperature=0.7)
    agents = [
        RandomAgent(),  # seat 0
        llm_a,          # seat 1
        RandomAgent(),  # seat 2
        llm_b,          # seat 3
        RandomAgent(),  # seat 4
        RandomAgent(),  # seat 5
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="capabilities_test")
    asyncio.run(sess.run())

    meta = json.loads((tmp_path / "meta.json").read_text())
    caps = meta["provider_capabilities"]
    assert "1" in caps and "3" in caps
    # Random seats should NOT have entries.
    assert "0" not in caps and "2" not in caps and "4" not in caps and "5" not in caps
    # spec §7.6 persisted schema names: seed_supported (NOT seed_accepted),
    # reasoning_kinds_observed (NOT reasoning_kinds).
    assert caps["1"]["provider"] == "mock"
    assert caps["1"]["seed_supported"] is True
    assert isinstance(caps["1"]["reasoning_kinds_observed"], list)
    assert caps["3"]["provider"] == "mock"
    assert "probed_at" in caps["1"]
```

Add `import json` at the top of the test file if not already present.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/integration/test_llm_session_mock.py::test_session_writes_provider_capabilities_to_meta -v`

Expected: FAIL — `KeyError: '1'` or `meta["provider_capabilities"] == {}`.

- [ ] **Step 3: Update `build_session_meta` to accept `provider_capabilities`**

Edit `src/llm_poker_arena/storage/meta.py`. Replace `build_session_meta` signature and body:

```python
def build_session_meta(
    *,
    session_id: str,
    config: SessionConfig,
    started_at: str,
    ended_at: str,
    total_hands_played: int,
    seat_assignment: dict[int, str],
    initial_button_seat: int,
    chip_pnl: dict[int, int],
    session_wall_time_sec: int,
    provider_capabilities: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "version": 2,
        "schema_version": "v2.0",
        "started_at": started_at,
        "ended_at": ended_at,
        "total_hands_played": total_hands_played,
        "planned_hands": config.num_hands,
        "git_commit": _git_commit(),
        "prompt_profile_version": "default-v2",
        "provider_capabilities": (provider_capabilities or {}),
        "chip_pnl": {str(s): int(v) for s, v in chip_pnl.items()},
        "retry_summary_per_seat": {},
        "tool_usage_summary": {},
        "censored_hands_count": 0,
        "censored_hand_ids": [],
        "total_tokens": {},
        "estimated_cost_breakdown": {},
        "session_wall_time_sec": int(session_wall_time_sec),
        "seat_assignment": {str(s): label for s, label in seat_assignment.items()},
        "initial_button_seat": initial_button_seat,
        "seat_permutation_id": "phase2a_default",
    }
```

- [ ] **Step 4: Update `Session.run()` to probe LLM providers**

Edit `src/llm_poker_arena/session/session.py`. In `run()`, just before the `for hand_id in range(...)` loop, add probe collection:

```python
    async def run(self) -> None:
        started_at_iso = _now_iso()
        started_at_monotonic = time.monotonic()
        initial_button_seat = 0
        # Initialize capabilities BEFORE the try so that even probe failure
        # reaches the finally cleanup (writers close, partial meta.json
        # still written). spec §4.4 HR2-03: probe each unique LLMProvider
        # once; non-LLM agents (Random, RuleBased, HumanCLI) skip probe.
        provider_capabilities: dict[str, dict[str, Any]] = {}
        try:
            provider_capabilities = await self._probe_providers()
            for hand_id in range(self._config.num_hands):
                await self._run_one_hand(hand_id)
                self._total_hands_played += 1
        finally:
            ended_at_iso = _now_iso()
            wall_time_sec = max(0, int(time.monotonic() - started_at_monotonic))
            meta = build_session_meta(
                session_id=self._session_id, config=self._config,
                started_at=started_at_iso, ended_at=ended_at_iso,
                total_hands_played=self._total_hands_played,
                seat_assignment={i: self._agents[i].provider_id()
                                 for i in range(self._config.num_players)},
                initial_button_seat=initial_button_seat,
                chip_pnl=self._chip_pnl,
                session_wall_time_sec=wall_time_sec,
                provider_capabilities=provider_capabilities,
            )
            (self._output_dir / "meta.json").write_text(
                json.dumps(meta, sort_keys=True, indent=2)
            )
            for w in (self._private_writer, self._public_writer,
                      self._snapshot_writer, self._censor_writer):
                w.close()
```

Then add the helper inside the `Session` class:

```python
    async def _probe_providers(self) -> dict[str, dict[str, Any]]:
        """For each LLMAgent in the seat list, call provider.probe() once
        and store the §7.6-named JSON dict under the seat's string key.
        Probes per provider instance are deduped (id-based) so two agents
        sharing one provider only probe once and reuse the result.

        The internal Pydantic `ObservedCapability` type uses §4.4 names
        (reasoning_kinds, seed_accepted); we map to §7.6 persisted-schema
        names (reasoning_kinds_observed, seed_supported) at this boundary
        so analysts reading meta.json get the schema spec promises.
        """
        from llm_poker_arena.agents.llm.llm_agent import LLMAgent
        from llm_poker_arena.agents.llm.types import ObservedCapability
        results: dict[str, dict[str, Any]] = {}
        cache: dict[int, dict[str, Any]] = {}
        for seat, agent in enumerate(self._agents):
            if not isinstance(agent, LLMAgent):
                continue
            provider = agent._provider  # noqa: SLF001
            pid = id(provider)
            if pid not in cache:
                cap: ObservedCapability = await provider.probe()
                cache[pid] = _capability_to_meta_json(cap)
            results[str(seat)] = cache[pid]
        return results
```

Add the boundary mapping function at module scope in `session.py` (just below `_split_provider_id`):

```python
def _capability_to_meta_json(cap: ObservedCapability) -> dict[str, Any]:
    """Map in-process ObservedCapability (§4.4 names) to spec §7.6
    persisted JSON schema names. Keeps the Pydantic type clean while
    honoring the meta.json contract analysts depend on.
    """
    return {
        "provider": cap.provider,
        "probed_at": cap.probed_at,
        "reasoning_kinds_observed": [k.value for k in cap.reasoning_kinds],
        "seed_supported": cap.seed_accepted,
        "tool_use_with_thinking_ok": cap.tool_use_with_thinking_ok,
        "extra_flags": dict(cap.extra_flags),
    }
```

Note: `cast("dict[str, Any]", ...)` requires the existing `cast` import (already present in `session.py`). Verify on the current file.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/integration/test_llm_session_mock.py::test_session_writes_provider_capabilities_to_meta -v`

Expected: PASS.

- [ ] **Step 6: Run the full suite + lint + mypy**

Run: `.venv/bin/pytest tests/ -q --no-header -x && .venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/`

Expected: 338 pass + 2 skip (1 new mock-session test on top of 337); ruff + mypy clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/storage/meta.py \
        src/llm_poker_arena/session/session.py \
        tests/integration/test_llm_session_mock.py
git commit -m "$(cat <<'EOF'
feat(session): probe LLM providers at session start, write to meta.json (Phase 3b Task 7)

spec §4.4 HR2-03 / §7.6. Session.run() probes each unique LLMProvider
instance once (deduped by id) and stores per-seat ObservedCapability
dump in meta.json.provider_capabilities. Non-LLM agents (Random,
RuleBased, HumanCLI) are skipped — only seats with LLM agents appear.

Field names match spec §4.4 ObservedCapability (reasoning_kinds /
seed_accepted / tool_use_with_thinking_ok / extra_flags), NOT §7.6's
illustrative-but-stale `reasoning_kinds_observed` / `seed_supported`.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: LLMAgent populates `IterationRecord.reasoning_artifacts` + rationale_required honors them

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/llm_agent.py` (extract artifacts once per successful response; attach to 4 successful-response IterationRecords; leave 2 error-path IterationRecords with default empty tuple = 6 total construction sites in `_decide_inner`)
- Test: `tests/unit/test_llm_agent_react_loop.py` (add 3 new tests)

- [ ] **Step 1: Write the failing tests**

Read `tests/unit/test_llm_agent_react_loop.py` for a usable `_resp()` factory; the existing one returns a response with empty `raw_assistant_turn.blocks`. We need a way to inject reasoning artifacts via the mock. The simplest path: extend `_resp` to optionally take artifact-bearing blocks, OR use AnthropicProvider's extraction directly.

Append new tests:

```python
def test_iteration_record_carries_reasoning_artifacts_from_provider() -> None:
    """When the provider returns reasoning artifacts, LLMAgent attaches them
    to the corresponding IterationRecord."""
    from llm_poker_arena.agents.llm.providers.anthropic_provider import (
        AnthropicProvider,
    )
    from llm_poker_arena.agents.llm.types import (
        AssistantTurn, ReasoningArtifactKind, TokenCounts,
    )

    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    # Build a response that has a thinking block + tool_use, as if from
    # AnthropicProvider with extended thinking on.
    resp = LLMResponse(
        provider="anthropic", model="claude-opus-4-7",
        stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t1"),),
        text_content="My answer.",
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic",
            blocks=(
                {"type": "thinking", "thinking": "Pot odds say fold.",
                 "signature": "sig=="},
                {"type": "text", "text": "My answer."},
                {"type": "tool_use", "id": "t1", "name": "fold", "input": {}},
            ),
        ),
    )
    # We can't use MockLLMProvider here because it doesn't extract artifacts.
    # Instead we patch AnthropicProvider's complete() to return our crafted
    # response, then run the agent. AnthropicProvider's
    # extract_reasoning_artifact will lift the thinking block.
    provider = AnthropicProvider(model="claude-opus-4-7", api_key="sk-test")

    async def _fake_complete(**_: Any) -> LLMResponse:
        return resp
    provider.complete = _fake_complete  # type: ignore[method-assign]

    agent = LLMAgent(provider=provider, model="claude-opus-4-7",
                      temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert len(result.iterations) == 1
    arts = result.iterations[0].reasoning_artifacts
    assert len(arts) == 1
    assert arts[0].kind == ReasoningArtifactKind.THINKING_BLOCK
    assert arts[0].content == "Pot odds say fold."


def test_rationale_required_satisfied_by_non_empty_reasoning_artifact() -> None:
    """When rationale_required=True and text_content is empty BUT the
    response carries a non-empty reasoning artifact (e.g. DeepSeek-R1's
    reasoning_content), LLMAgent treats the rationale as satisfied."""
    from llm_poker_arena.agents.llm.providers.anthropic_provider import (
        AnthropicProvider,
    )
    from llm_poker_arena.agents.llm.types import AssistantTurn, TokenCounts

    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    resp = LLMResponse(
        provider="anthropic", model="claude-opus-4-7",
        stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t1"),),
        text_content="",  # empty surface text
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic",
            blocks=(
                {"type": "thinking",
                 "thinking": "Hidden but non-empty rationale.",
                 "signature": "sig=="},
                {"type": "tool_use", "id": "t1", "name": "fold", "input": {}},
            ),
        ),
    )
    provider = AnthropicProvider(model="claude-opus-4-7", api_key="sk-test")

    async def _fake_complete(**_: Any) -> LLMResponse:
        return resp
    provider.complete = _fake_complete  # type: ignore[method-assign]

    agent = LLMAgent(provider=provider, model="claude-opus-4-7",
                      temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.no_tool_retry_count == 0  # no rationale-empty retry
    assert result.final_action == Action(tool_name="fold", args={})


def test_rationale_required_NOT_satisfied_by_encrypted_or_redacted() -> None:
    """BLOCKER fix: opaque ENCRYPTED / REDACTED artifacts must NOT count as
    satisfying rationale_required, otherwise a model could bypass the
    requirement by emitting only encrypted/redacted blocks. Plain spec
    §4.6 says only RAW / SUMMARY / THINKING_BLOCK carry plaintext rationale.
    """
    from llm_poker_arena.agents.llm.providers.anthropic_provider import (
        AnthropicProvider,
    )
    from llm_poker_arena.agents.llm.types import AssistantTurn, TokenCounts

    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    # Response with empty text + tool_use + ONLY encrypted/redacted blocks.
    bad_resp = LLMResponse(
        provider="anthropic", model="claude-opus-4-7",
        stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t1"),),
        text_content="",  # empty surface text
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic",
            blocks=(
                {"type": "encrypted_thinking", "data": "opaque_payload=="},
                {"type": "redacted_thinking", "data": "more_opaque=="},
                {"type": "tool_use", "id": "t1", "name": "fold", "input": {}},
            ),
        ),
    )
    # Recovery response with proper rationale.
    recovery = LLMResponse(
        provider="anthropic", model="claude-opus-4-7",
        stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t2"),),
        text_content="On reflection, fold is correct.",
        tokens=TokenCounts(input_tokens=12, output_tokens=8,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(
            provider="anthropic", blocks=(),
        ),
    )

    provider = AnthropicProvider(model="claude-opus-4-7", api_key="sk-test")
    call_count = {"n": 0}

    async def _fake_complete(**_: Any) -> LLMResponse:
        call_count["n"] += 1
        return bad_resp if call_count["n"] == 1 else recovery
    provider.complete = _fake_complete  # type: ignore[method-assign]

    agent = LLMAgent(provider=provider, model="claude-opus-4-7",
                      temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    # The first response had only opaque artifacts → no rationale → retry.
    assert result.no_tool_retry_count == 1
    assert result.final_action == Action(tool_name="fold", args={})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py::test_iteration_record_carries_reasoning_artifacts_from_provider tests/unit/test_llm_agent_react_loop.py::test_rationale_required_satisfied_by_non_empty_reasoning_artifact -v`

Expected: both FAIL — first because `reasoning_artifacts` is the default empty tuple; second because the rationale check fires no_tool_retry on empty text_content.

- [ ] **Step 3: Update `LLMAgent._decide_inner` — extract artifacts once per response, attach to all IterationRecords; honor artifacts in rationale check**

Edit `src/llm_poker_arena/agents/llm/llm_agent.py` `_decide_inner`. Find each `IterationRecord(...)` construction (5 sites) and:

1. After the `response = await ...` returns successfully, immediately extract artifacts ONCE per loop iteration:

```python
            iter_ms = int((time.monotonic() - iter_start) * 1000)
            total_tokens = total_tokens + response.tokens
            artifacts = self._provider.extract_reasoning_artifact(response)
```

2. In the no_tool branch:

```python
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
```

3. In the multi-tool-call branch:

```python
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
```

4. In the rationale_required strict branch — replace the condition AND wire artifacts in:

```python
            if (self._prompt_profile.rationale_required
                    and not response.text_content.strip()
                    and not _has_text_rationale_artifact(artifacts)):
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
```

5. In the happy/illegal branch (where IterationRecord is constructed once for both):

```python
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
```

6. The two error-path IterationRecords (`ProviderTransientError` and `ProviderPermanentError`) intentionally do NOT carry artifacts — there is no successful response. Leave them with the default `reasoning_artifacts=()`.

7. Add the helper at module level (just below `_action_tool_specs`):

```python
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
    for a in artifacts:
        if a.kind in rationale_kinds and a.content and a.content.strip():
            return True
    return False
```

Add to imports at the top of `llm_agent.py`:

```python
from llm_poker_arena.agents.llm.types import (
    ApiErrorInfo,
    IterationRecord,
    LLMResponse,
    ReasoningArtifact,
    ReasoningArtifactKind,
    TokenCounts,
    TurnDecisionResult,
)
```

Update the call site in step 4 (rationale_required branch) accordingly: `_has_text_rationale_artifact(artifacts)` instead of `_has_text_artifact(artifacts)`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py -v`

Expected: 23 existing tests + 3 new tests = 26 pass (the 3rd new test is the BLOCKER-fix from codex audit: encrypted/redacted artifacts must NOT satisfy rationale_required).

- [ ] **Step 5: Run the full suite + lint + mypy**

Run: `.venv/bin/pytest tests/ -q --no-header -x && .venv/bin/ruff check src/ tests/ && .venv/bin/mypy --strict src/ tests/`

Expected: 341 pass + 2 skip (3 new ReAct tests on top of 338); clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/agents/llm/llm_agent.py \
        tests/unit/test_llm_agent_react_loop.py
git commit -m "$(cat <<'EOF'
feat(agents): IterationRecord.reasoning_artifacts populated per response (Phase 3b Task 8)

LLMAgent calls provider.extract_reasoning_artifact(response) once per
ReAct iteration and attaches the tuple to every successful-response
IterationRecord (5 sites). Error-path records (api_retry exhaustion)
keep the default empty tuple — no successful response to extract from.

rationale_required strict mode now treats a non-empty reasoning artifact
as satisfying the rationale requirement (otherwise DeepSeek-R1 always
trips no_tool_retry because its surface `content` can be empty when the
chain-of-thought lives in `reasoning_content`).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Real DeepSeek smoke test (gated)

**Files:**
- Create: `tests/integration/test_llm_session_real_deepseek.py`

**Activation:**
```bash
DEEPSEEK_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_llm_session_real_deepseek.py -v
```

DeepSeek API key is in `~/.zshrc:18` (already active in this shell). Cost: ~$0.001 per session at deepseek-chat pricing.

- [ ] **Step 1: Create the gated integration test**

```python
"""Real DeepSeek API smoke test (gated, NOT in CI).

Run only when both env vars are set:
  DEEPSEEK_INTEGRATION_TEST=1
  DEEPSEEK_API_KEY=sk-...

Costs ~$0.001-0.005 per run with deepseek-chat, longer with deepseek-reasoner.
6 hands (validator min) but only seat 3 is the LLM; other seats are RandomAgent.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

pytestmark = pytest.mark.skipif(
    os.getenv("DEEPSEEK_INTEGRATION_TEST") != "1"
    or not os.getenv("DEEPSEEK_API_KEY"),
    reason="needs DEEPSEEK_INTEGRATION_TEST=1 and DEEPSEEK_API_KEY set",
)


def test_real_deepseek_chat_plays_six_hands(tmp_path: Path) -> None:
    api_key = os.environ["DEEPSEEK_API_KEY"]
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    provider = OpenAICompatibleProvider(
        provider_name_value="deepseek", model="deepseek-chat",
        api_key=api_key, base_url="https://api.deepseek.com/v1",
    )
    llm_agent = LLMAgent(
        provider=provider, model="deepseek-chat",
        temperature=0.7, total_turn_timeout_sec=60.0,
    )
    agents = [
        RandomAgent(),  # seat 0 (BTN)
        RandomAgent(),  # SB
        RandomAgent(),  # BB
        llm_agent,      # UTG ← DeepSeek
        RandomAgent(),  # HJ
        RandomAgent(),  # CO
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="real_deepseek_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps
                 if json.loads(line)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots found"
    rec = llm_snaps[0]
    assert rec["agent"]["provider"] == "deepseek"
    assert rec["agent"]["model"] == "deepseek-chat"
    assert rec["iterations"], "no iterations recorded — provider plumbing broken"
    # deepseek-chat should NOT emit reasoning_content; artifacts empty.
    assert all(it.get("reasoning_artifacts", []) == []
               for it in rec["iterations"])
    final = rec["final_action"]
    legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
    assert final["type"] in legal_names

    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["provider_capabilities"]["3"]["provider"] == "deepseek"
    assert sum(meta["chip_pnl"].values()) == 0


def test_real_deepseek_probe_returns_observed_capability() -> None:
    api_key = os.environ["DEEPSEEK_API_KEY"]
    provider = OpenAICompatibleProvider(
        provider_name_value="deepseek", model="deepseek-chat",
        api_key=api_key, base_url="https://api.deepseek.com/v1",
    )
    cap = asyncio.run(provider.probe())
    assert cap.provider == "deepseek"
    assert cap.probed_at.endswith("Z")
    # deepseek-chat: seed accepted (DeepSeek docs say so), reasoning_kinds
    # = (UNAVAILABLE,) since V3 doesn't emit reasoning_content (probe
    # explicitly records "tested, none seen" per spec §4.6).
    from llm_poker_arena.agents.llm.types import ReasoningArtifactKind
    assert cap.seed_accepted is True
    assert cap.reasoning_kinds == (ReasoningArtifactKind.UNAVAILABLE,)
```

- [ ] **Step 2: Run the gated test against the real API**

Run:

```bash
DEEPSEEK_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_llm_session_real_deepseek.py -v
```

Expected: 2 tests pass. Cost ~$0.005. Inspect:
- The output shows DeepSeek snapshots in `tmp_path/agent_view_snapshots.jsonl` (use `--basetemp=/tmp/deepseek_smoke` and inspect after).
- LLM seat 3 makes valid actions (no censored hands).
- meta.json provider_capabilities[3] populated correctly.

If the test fails because `final_action` type isn't in `legal_names` repeatedly: deepseek-chat may need a clearer prompt; check `redact_secret` did not eat a digit; check tool spec shape. Most common failure mode: model returns text-only (no tool_call), triggering no_tool_retry → fallback to default_safe_action. In that case the assertion still passes because `default_safe_action` is always legal — but the snapshot's `default_action_fallback` will be `True`. That's acceptable smoke behavior; do not loosen assertions to mask it.

- [ ] **Step 3: Verify the suite still passes (no gated tests selected)**

Run: `.venv/bin/pytest tests/ -q --no-header -x`

Expected: 341 pass + 4 skip (the 2 real-Anthropic gated + the 2 new real-DeepSeek gated).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_llm_session_real_deepseek.py
git commit -m "$(cat <<'EOF'
test(integration): gated real DeepSeek smoke session (Phase 3b Task 9)

Mirrors Phase 3a's real-Anthropic gated pattern. Activated by
DEEPSEEK_INTEGRATION_TEST=1 + DEEPSEEK_API_KEY. Verifies:
  - 6-hand session with 1 DeepSeek seat + 5 Random
  - agent snapshots carry deepseek provider tag
  - reasoning_artifacts empty for deepseek-chat (V3, no CoT field)
  - meta.json.provider_capabilities[3] = deepseek probe result
  - chip_pnl conserved
  - DeepSeek probe returns seed_accepted=True (DeepSeek docs)

Cost ~$0.005 / run. Verified manually before commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Real multi-provider session smoke (gated)

**Files:**
- Create: `tests/integration/test_llm_session_real_multi_provider.py`

Goal: a single session with **multiple distinct providers** (Anthropic + DeepSeek + Random fillers) to exercise the per-seat probe + per-iteration extract paths together. Verifies the full Phase 3b stack works end-to-end on real APIs.

- [ ] **Step 1: Create the gated multi-provider test**

```python
"""Real multi-provider smoke session: Claude + DeepSeek + Random.

Run only when ALL of:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...
  DEEPSEEK_INTEGRATION_TEST=1
  DEEPSEEK_API_KEY=sk-...

Costs ~$0.02 per run (Claude Haiku ~$0.018, DeepSeek-Chat ~$0.001).
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
from llm_poker_arena.agents.llm.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

pytestmark = pytest.mark.skipif(
    os.getenv("ANTHROPIC_INTEGRATION_TEST") != "1"
    or os.getenv("DEEPSEEK_INTEGRATION_TEST") != "1"
    or not os.getenv("ANTHROPIC_API_KEY")
    or not os.getenv("DEEPSEEK_API_KEY"),
    reason="needs both INTEGRATION_TEST flags + both API keys",
)


def test_real_multi_provider_six_hand_session(tmp_path: Path) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    anth_a = AnthropicProvider(
        model="claude-haiku-4-5",
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )
    anth_b = AnthropicProvider(
        model="claude-haiku-4-5",
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )
    ds = OpenAICompatibleProvider(
        provider_name_value="deepseek", model="deepseek-chat",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com/v1",
    )
    agents = [
        RandomAgent(),  # seat 0
        LLMAgent(provider=anth_a, model="claude-haiku-4-5",
                 temperature=0.7, total_turn_timeout_sec=60.0),
        RandomAgent(),  # seat 2
        LLMAgent(provider=ds, model="deepseek-chat",
                 temperature=0.7, total_turn_timeout_sec=60.0),
        RandomAgent(),  # seat 4
        LLMAgent(provider=anth_b, model="claude-haiku-4-5",
                 temperature=0.7, total_turn_timeout_sec=60.0),
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="real_multi_provider_smoke")
    asyncio.run(sess.run())

    meta = json.loads((tmp_path / "meta.json").read_text())
    caps = meta["provider_capabilities"]
    # Two anthropic agents (different provider instances) + one deepseek.
    assert {caps["1"]["provider"], caps["3"]["provider"], caps["5"]["provider"]} == {
        "anthropic", "deepseek",
    }
    # Random seats absent.
    assert "0" not in caps and "2" not in caps and "4" not in caps
    # chip conservation
    assert sum(meta["chip_pnl"].values()) == 0

    # Inspect one snapshot per LLM provider.
    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    by_provider: dict[str, list[dict]] = {}
    for line in snaps:
        rec = json.loads(line)
        prov = rec["agent"]["provider"]
        by_provider.setdefault(prov, []).append(rec)
    assert "anthropic" in by_provider
    assert "deepseek" in by_provider
    # Anthropic snapshots: reasoning_artifacts may be empty (no extended
    # thinking enabled in 3b) OR populated; either is acceptable.
    # DeepSeek-Chat snapshots: reasoning_artifacts MUST be empty (V3 has no CoT).
    for rec in by_provider["deepseek"]:
        for it in rec["iterations"]:
            assert it.get("reasoning_artifacts", []) == [], (
                "deepseek-chat should not emit reasoning artifacts"
            )
```

- [ ] **Step 2: Run the gated test against both real APIs**

Run:

```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 DEEPSEEK_INTEGRATION_TEST=1 \
  .venv/bin/pytest tests/integration/test_llm_session_real_multi_provider.py -v
```

Expected: PASS. Inspect tmp output for multi-provider snapshot diversity (use `--basetemp=/tmp/multi_provider_smoke`).

- [ ] **Step 3: Verify the suite still passes (gated tests skipped)**

Run: `.venv/bin/pytest tests/ -q --no-header -x`

Expected: 341 pass + 5 skip (2 real-Anthropic + 2 real-DeepSeek + 1 real-multi-provider all gated off).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_llm_session_real_multi_provider.py
git commit -m "$(cat <<'EOF'
test(integration): gated real multi-provider smoke (Phase 3b Task 10)

6-hand session with 2 Claude-Haiku-4.5 + 1 DeepSeek-Chat + 3 Random,
gated by both ANTHROPIC_INTEGRATION_TEST and DEEPSEEK_INTEGRATION_TEST.
Verifies the full Phase 3b stack on real APIs:
  - per-seat probe writes anthropic + deepseek capabilities to meta
  - per-iteration reasoning_artifacts: empty for deepseek-chat
  - chip_pnl conservation across mixed-provider gameplay

Cost ~$0.02 / run. Verified manually before commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Lint + mypy strict cleanup + memory update

**Files:**
- Touch any source files flagged by the final lint pass
- Update `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md`

- [ ] **Step 1: Final lint sweep**

Run: `.venv/bin/ruff check src/ tests/`

Expected: zero diagnostics. If anything surfaces (unused imports, simplifications), fix in place.

- [ ] **Step 2: Final mypy strict sweep**

Run: `.venv/bin/mypy --strict src/ tests/`

Expected: zero diagnostics on all source files. If anything surfaces:
- New types not exported in `agents/llm/__init__.py` if other modules need them externally — re-export.
- `cast("dict[str, Any]", ...)` mismatches around `cap.model_dump(mode="json")` in `session.py` — the dump returns `dict[str, Any]` natively so cast is for forward-compat only.
- `extra_flags={"base_url": str(self._client.base_url)}` if `base_url` is `httpx.URL`.

- [ ] **Step 3: Final pytest with all gates flipped (manual)**

Run:

```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 DEEPSEEK_INTEGRATION_TEST=1 \
  .venv/bin/pytest tests/ -v
```

Expected: 346 pass + 0 skip (341 non-gated + 5 gated tests all run: 2 real-Anthropic + 2 real-DeepSeek + 1 real-multi-provider).

- [ ] **Step 4: Update memory**

Read `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md` first, then prepend a "Phase 3b COMPLETE" block following the same shape as the existing "Phase 3d COMPLETE" block:
- HEAD SHA after Task 10 commit
- count of new tests, total green
- 11 commit log
- non-obvious learnings (collected as task work surfaces them)
- defers to Phase 3c (still: utility tools + ToolRunner) and Phase 3e (1000-hand session)

Update `MEMORY.md` index pointer description to reference Phase 3b done.

- [ ] **Step 5: Commit lint cleanup if any + memory update is a separate file outside the repo (no git op)**

If any lint/mypy fixes were committed in Step 1–2, that's already captured. The memory update lives in `~/.claude/projects/-Users-zcheng256/memory/`, NOT under the project repo — no `git add` needed for it.

Final inventory check:

```bash
git log --oneline -13
git status
```

Expected: clean tree, 11 new commits since `91a8a37` (Tasks 0–10 each produce one commit). Task 11's lint sweep adds an additional commit only if any lint/mypy fix was needed; if Steps 1–2 came up clean, no extra commit. Memory update is a file outside the repo (not staged).

---

## Self-Review Checklist (auditor-facing summary)

After all 11 tasks land, the following statements must hold:

1. **Spec coverage:**
   - §4.4 `LLMProvider.complete` accepts `system=` (already true from 3d) ✓
   - §4.4 `LLMProvider.serialize_assistant_turn` exists; default returns raw turn unchanged ✓ (kept from 3a; preserved per codex audit fix to Spec Inconsistency #3)
   - §4.4 `LLMProvider.extract_reasoning_artifact` is now abstract, implemented by both shipped providers ✓ (Tasks 4, 6)
   - §4.4 `LLMProvider.probe` is now abstract, implemented by both shipped providers ✓ (Tasks 5, 6)
   - §4.4 `ObservedCapability` type defined ✓ (Task 1)
   - §4.4 HR2-03 honest reporting: `tool_use_with_thinking_probed` flag in extra_flags signals "not actually tested" rather than "tested and failed" ✓ (Tasks 5, 6 — codex audit fix I3)
   - §4.6 `ReasoningArtifact` + `ReasoningArtifactKind` defined; persisted in IterationRecord ✓ (Tasks 1, 2, 8)
   - §4.6 BR2-07 thinking-block byte-identical preservation verified via real `anthropic.types.ThinkingBlock` round-trip through `_normalize()` ✓ (Task 4 — codex audit fix N2)
   - §4.6 REDACTED.content=None + ENCRYPTED.content=opaque payload; rationale_required check rejects opaque artifacts ✓ (Tasks 4, 8 — codex BLOCKER fix B1)
   - §4.6 UNAVAILABLE explicitly emitted by probe when no artifacts observed (vs ambiguous empty tuple) ✓ (Tasks 5, 6 — codex audit fix I6)
   - §7.6 `meta.json.provider_capabilities` populated per session, mapped to spec §7.6 schema names (`reasoning_kinds_observed`, `seed_supported`) at persistence boundary ✓ (Task 7 — codex audit fix I2)
   - §11.2 best-effort seed: AnthropicProvider seed_accepted=False (factually); OpenAICompatibleProvider tries seed=42, latches `_seed_known_unsupported` so subsequent `complete()` calls drop seed automatically ✓ (Tasks 5, 6 — codex audit fix I5)
2. **No placeholders:** every step has executable code or commands. Search this file for "TBD", "TODO", "fill in", "implement later" — should yield zero matches.
3. **Type consistency:**
   - `extract_reasoning_artifact(response: LLMResponse) -> tuple[ReasoningArtifact, ...]` — same signature in `provider_base.py`, both providers, and `MockLLMProvider`
   - `build_tool_result_messages(...) -> list[dict[str, Any]]` — same signature; LLMAgent always uses `messages.extend(...)`
   - `IterationRecord.reasoning_artifacts: tuple[ReasoningArtifact, ...] = ()` — same name everywhere it's referenced
   - `ObservedCapability.reasoning_kinds: tuple[ReasoningArtifactKind, ...]` — tuple, not list (frozen Pydantic)
4. **Cross-task integration:** Task 8 depends on Task 4 + Task 6 (both providers must implement extract before LLMAgent can call it generically). Task 7 depends on Task 5 + Task 6 (both providers must implement probe before Session can call it). Task 9 + 10 depend on everything else.
5. **Gated tests:** `pytest.mark.skipif` keys: `ANTHROPIC_INTEGRATION_TEST`, `DEEPSEEK_INTEGRATION_TEST`. Activation via `source <(sed -n '3s/^#//p' ~/.zprofile)` for Anthropic key (commented in `.zprofile:3`). DeepSeek key is already exported from `.zshrc:18`.
6. **Probe failure resilience** (codex audit fix I7): `Session.run()` initializes `provider_capabilities={}` before `try` and runs `_probe_providers()` INSIDE the try block, so even probe failures still trigger the writers' `close()` and meta.json write in the `finally` block.
7. **Codex audit findings status** (2026-04-25 review on `91a8a37` HEAD):
   - 1 BLOCKER (B1: opaque artifacts satisfying rationale_required): FIXED — `_has_text_rationale_artifact` typed by kind
   - 8 IMPORTANT findings: 6 fixed (I1 keep serialize_assistant_turn / I2 §7.6 naming / I3 honest probe flags / I4 OpenAI exception narrowing / I5 seed latch in complete / I6 UNAVAILABLE / I7 probe-inside-try); 2 explicitly deferred (I8 AgentDescriptor temp/seed → Phase 3e; I9 retry/token summaries → Phase 3e)
   - 4 NIT findings: 4 fixed (N1 site count / N2 real-SDK ThinkingBlock test / N3 monkeypatch over module mutation / N4 200-response comment)

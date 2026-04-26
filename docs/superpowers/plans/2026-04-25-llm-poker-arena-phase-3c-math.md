# Phase 3c-math: Utility Tools (pot_odds + spr) + K+1 Bounded ReAct — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (inline mode chosen by user) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec §5 utility-tool subset (pot_odds + spr) with a stateless `run_utility_tool` dispatcher and widen LLMAgent's ReAct loop from K=0 (Phase 3a/3b) to K+1 per spec §4.2, gated on `SessionConfig.enable_math_tools`. Land the smallest viable utility-tool stack so the `llm_math` baseline can run end-to-end without waiting for the equity backend (3c-equity) or HUD stats (3c-hud).

**Architecture:**
- New `src/llm_poker_arena/tools/` subpackage with one stateless dispatcher (`run_utility_tool(view, name, args)`) plus per-tool functions (`pot_odds`, `spr`). No class, no state. 3c-equity will introduce a `ToolRunner` class when an `EquityBackend` instance needs to be carried per turn.
- LLMAgent gains an optional `tool_runner` callable (default = the stateless `run_utility_tool` from this subpackage). The ReAct loop in `_decide_inner` adds a third branch alongside no_tool / multi-tool-call / action-tool: **utility-tool dispatch** (call dispatcher → wrap result as provider-specific tool_result message → continue loop).
- Tool spec exposure to provider is driven by `view.immutable_session_params.enable_math_tools` (already on SessionParamsView since Phase 1). When the flag is off, the tool spec list passed to `provider.complete(tools=...)` is action-tools-only — LLMAgent operates exactly as Phase 3b K=0.
- Final-step pressure: when `utility_count >= max_utility_calls` OR `step == MAX_STEPS - 1`, the next provider call sees action-tools-only (matches spec §4.2 `is_final_step` logic). If LLM still emits no action, no_tool_retry budget catches it.
- IterationRecord schema gains one field: `tool_result: dict[str, Any] | None = None`. Action-tool iterations leave it None (the action's effect is `final_action`); utility-tool iterations populate it with `{"value": ...}`. Spec §7.4 example matches.

**Tech Stack:** No new dependencies. Reuses Phase 3b's provider abstraction (`build_tool_result_messages`, `extract_reasoning_artifact`), Phase 3d's PromptProfile + Jinja2 templates, Pydantic 2 frozen DTOs.

---

## Phase 3c-math Scope Decisions (locked via brainstorming 2026-04-25)

These decisions captured user input from a 4-question brainstorming pass. They are **not** open to re-litigation during execution; codex audit may surface secondary issues but should not reverse these primary calls.

1. **Phase split**: 3c is decomposed into 3c-math (this plan) → 3c-equity → 3c-hud. Each ships independently. This plan does NOT include RangeNotationParser, equity backend, hand_equity_vs_ranges, or HUD stats.
2. **Tool signature**: `pot_odds` and `spr` accept **optional** args (`to_call`, `pot`, `stack`). Empty args → fall back to PlayerView fields (= spec §5.2.3 zero-arg behavior). Non-empty args → use provided values (= LLM hypothetical reasoning, e.g. "if I raise to 600, what is villain's pot_odds?"). Spec §5.2.3 defines zero-arg only; this plan ships a **superset** that includes the zero-arg path. See "Spec Inconsistencies" below for the deviation note.
3. **Verification scope**: BOTH a deterministic mock K+1 integration test AND a gated real-Anthropic K+1 smoke test (mirrors 3a/3b/3d pattern). The gated test asserts wire correctness ("≥1 utility_tool iteration with non-None tool_result across the session"), NOT behavior frequency.
4. **Retry budget for utility-tool errors**: NO new retry budget; spec §4.1 BR2-05's 4 independent budgets are not extended. Utility-tool errors increment the existing `tool_usage_error_count` counter (analytics only, NOT a retry-budget cap), and the loop continues until `max_utility_calls` is reached or LLM commits. This matches spec §4.2 lines 1019-1021 (`if result.get("invalid_input"): tool_usage_error_count += 1`) — `tool_usage_error_count` is a counter, not a budget. Phase 3d's separate `tool_usage_retry` slot (used by multi-tool-call action misuse) stays untouched and does NOT fire for utility errors.

## Spec Inconsistencies to Reconcile (DOCUMENT, do not silently choose)

1. **Spec §5.2.3 zero-arg vs plan optional-arg superset**: Spec defines `pot_odds(view) -> float` and `spr(view) -> float` as zero-arg in the LLM-callable sense. This plan ships the optional-arg superset (zero-arg works AND args-provided works). Justification: the zero-arg path is 100% redundant with `pot_odds_required` already being in the user prompt (Phase 3d verified Claude Haiku 4.5 cites it 100% of turns). Without args support, the utility tool has zero added value. The superset costs ~10 LOC of arg-handling and unlocks bet-sizing reasoning. **Document in Task 2 + 3 commit messages.**
2. **Spec §5.4 ToolRunner class vs plan stateless function**: Spec defines a `ToolRunner` class that holds `(view, legal_actions, equity_backend)` per turn. 3c-math has no equity_backend, so the class would carry only `(view, legal_actions)` — both already passed per call. Stateless `run_utility_tool(view, name, args)` is YAGNI-compliant for 3c-math; the class lands in 3c-equity when `EquityBackend` joins. Action validation is already a separate function (`validate_action` in `engine/legal_actions.py`); not folding it into ToolRunner. **Document in Task 1 commit message.**
3. **Phase 3d rationale_required-on-every-iteration vs Phase 3c-math rationale_required-on-action-only**: Phase 3d (current main) checks `rationale_required` strict mode on EVERY non-error iteration that contains a tool_use block — empty text + tool_use → no_tool_retry. With K+1 loop and utility tools on, applying this rule per-iteration would mean LLM must emit text rationale before EACH utility call, throttling the K+1 loop with extra retries (LLM doesn't naturally write rationale before pot_odds(); it just calls). **Decision: rationale_required strict check only fires on the action-tool iteration (the commit step), not on intermediate utility-tool iterations.** Justification: a utility tool call IS itself a form of structured reasoning ("I'm asking for pot odds because I want to compare to my equity"); requiring redundant prose rationale per utility call burns tokens without information gain. This is implemented automatically because the existing rationale check sits in the action-tool branch of `_decide_inner`; the new utility-tool branch (Task 7) skips it and continues the loop. **Document in Task 7 commit message.**

## Spec Items Deferred (NOT in Phase 3c-math)

- **3c-equity** (next phase): `RangeNotationParser`, `EquityBackend` ABC + a concrete backend (eval7 or treys), `hand_equity_vs_ranges` tool, range-validation against `view.opponent_seats_in_hand`. Will introduce the `ToolRunner` class to carry `EquityBackend` per turn.
- **3c-hud** (next phase after equity): `get_opponent_stats` tool, `view.opponent_stats` populated from Phase 2b SQL aggregates, `enable_hud_tool` flag wiring beyond the current Phase 1 stub.
- **3e** (carried over from 3b deferrals): `AgentDescriptor.temperature` / `agent.seed` persistence in agent_view_snapshots; `meta.json.retry_summary_per_seat` / `tool_usage_summary` / `total_tokens` aggregation.
- **Future**: `LLMProvider.static_capability()`, Anthropic extended-thinking enablement on real calls, OpenAI Responses API (all from 3b deferrals).

## Risks Acknowledged Up Front

- **Claude Haiku 4.5 may rationally NOT call utility tools** even when offered, because the user prompt already provides `pot_odds_required` directly. The gated test asserts "≥1 utility_tool iteration across 6 hands" not "≥30%" — see Q3 reasoning. If 0 calls land in 6 hands, that's a **plumbing bug** (tool spec malformed, prompt template silent, etc), not a model-behavior issue.
- **`max_utility_calls=5` default is conservative** — with only 2 tools (pot_odds, spr) and bounded args, even greedy LLM calls ≤3 per turn in expectation. If the gated test reveals LLM hammering >5, it's a prompt-template issue, not a budget issue.
- **K+1 ReAct loop refactor touches the most complex method in the codebase** (`LLMAgent._decide_inner`, ~250 LOC after Phase 3b). Plan splits the refactor into 3 tasks (Task 5 constructor, Task 6 dispatch branch, Task 7 final-step pressure) so each commit's diff stays reviewable.
- **No backward incompatibility risk**: SessionConfig.enable_math_tools defaults to False; existing test sessions stay K=0 unchanged. New behavior is opt-in per session.

---

## File Structure

**New files** (under `src/llm_poker_arena/tools/`):
- `__init__.py` — package marker; exports `run_utility_tool`, `pot_odds`, `spr`, `utility_tool_specs`, `ToolDispatchError`
- `runner.py` — `run_utility_tool(view, name, args) -> dict[str, Any]` dispatcher; `utility_tool_specs(view) -> list[dict]` spec generator; `ToolDispatchError` for input validation failures
- `pot_odds.py` — `pot_odds(view, *, to_call=None, pot=None) -> float` pure function
- `spr.py` — `spr(view, *, stack=None, pot=None) -> float` pure function

**New tests** (under `tests/unit/`):
- `test_pot_odds_tool.py` — boundaries: to_call=0, both args provided, view fallback, negative values raise
- `test_spr_tool.py` — symmetric
- `test_run_utility_tool.py` — dispatch unknown name, malformed args, success path, ToolDispatchError surface
- `test_utility_tool_specs.py` — spec list reflects `enable_math_tools` flag, schema is well-formed for Anthropic
- `test_llm_agent_react_loop_k1.py` — new file for K+1-specific tests (don't bloat existing test_llm_agent_react_loop.py)

**New tests** (under `tests/integration/`):
- `test_llm_session_mock_k1.py` — mock 6-hand session with `enable_math_tools=True`, asserts iterations contain utility_tool_use entries with non-None tool_result
- `test_llm_session_real_anthropic_math.py` — gated by `ANTHROPIC_INTEGRATION_TEST=1` + key, 6 hands with math tools enabled, asserts ≥1 utility_tool_use iteration with tool_result non-None

**Modified files**:
- `src/llm_poker_arena/agents/llm/types.py` — add `tool_result: dict[str, Any] | None = None` to `IterationRecord`
- `src/llm_poker_arena/agents/llm/llm_agent.py` — accept optional `tool_runner` constructor arg (default to stateless `run_utility_tool`); refactor `_decide_inner` to add utility-tool dispatch branch + final-step pressure + utility_count tracking
- `src/llm_poker_arena/agents/llm/prompt_profile.py` — `render_system` accepts `enable_math_tools: bool` kwarg; passes to template
- `src/llm_poker_arena/agents/llm/prompts/system.j2` — add `{% if enable_math_tools %}...{% endif %}` block describing pot_odds + spr signatures and when to use them
- Tests touched only as needed (existing 22 ReAct tests in `test_llm_agent_react_loop.py` should stay green)

**Files NOT touched** (intentionally):
- `src/llm_poker_arena/session/session.py` — Session contract (`agent.decide(view)`) unchanged; LLMAgent builds tool runner internally
- `src/llm_poker_arena/storage/schemas.py` — `AgentViewSnapshot.iterations: tuple[dict[str, Any], ...]` is opaque dict; new `tool_result` key flows through unchanged
- `src/llm_poker_arena/storage/layer_builders.py` — `build_agent_view_snapshot` dumps IterationRecord via `model_dump(mode="json")`; new field auto-included
- `src/llm_poker_arena/agents/llm/provider_base.py` + providers — provider abstraction unchanged from 3b
- `src/llm_poker_arena/agents/llm/redaction.py` — utility tool args may carry user-controlled values, but they're integers (validated by jsonschema in input_schema), not API keys; redaction doesn't apply

---

## Test Counts (cumulative, baseline = 342 pass + 5 skip after Phase 3b)

After each task, the expected suite counts (updated post-codex-audit):

| Task | New tests | Cumulative pass | Cumulative skip |
|---|---|---|---|
| 0 | 2 (IterationRecord field default + round-trip) | 344 | 5 |
| 1 | 0 (skeleton only) | 344 | 5 |
| 2 | 6 (pot_odds: 0-arg/args/partial/zero-to-call/negative-to-call/negative-pot) | 350 | 5 |
| 3 | 5 (spr: 0-arg/args/partial/zero-pot/negative-stack) | 355 | 5 |
| 4 | 10 (dispatcher: pot/pot-args/spr/unknown/bad-args + 4 new from codex IMPORTANT-2/3: extras-rejected/string/float/bool/None) | 365 | 5 |
| 5 | 4 (specs: empty/contains/pot_odds-shape/spr-shape) | 369 | 5 |
| 6 | 1 (constructor accepts tool_runner) | 370 | 5 |
| 7 | 6 (K+1 dispatch: happy×1/2-tools/bad-args/unknown→illegal/exhaustion + 1 new from codex NIT-2: mixed utility+action multi-call) | 376 | 5 |
| 8 | 3 (final-step pressure: budget-exhausted/step-cap/hallucinated-after-exhaustion) | 379 | 5 |
| 9 | 2 (system.j2: included-when-enabled/omitted-when-disabled) | 381 | 5 |
| 10 | 1 (mock K+1 integration session + total_utility_calls assertion) | 382 | 5 |
| 11 | 0 unit + 1 gated | 382 | 6 |
| 12 | 0 (lint cleanup) | 382 | 6 |

**Final all-gates-on**: 388 pass + 0 skip (382 non-gated + 6 gated: 5 prior from Phase 3b + 1 new K+1 math).

---

## Task 0: Add `tool_result` field to `IterationRecord`

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/types.py:77-99` (`IterationRecord` class)
- Test: `tests/unit/test_llm_types.py` (append round-trip test)

**Why first**: All subsequent tasks (utility tool dispatch, mock tests, gated tests) emit IterationRecord with this field. Adding it before any dispatch code keeps each later commit small and testable.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_llm_types.py`:

```python
def test_iteration_record_default_tool_result_is_none() -> None:
    rec = IterationRecord(
        step=1, request_messages_digest="sha256:x",
        provider_response_kind="tool_use",
        tool_call=ToolCall(name="fold", args={}, tool_use_id="t1"),
        text_content="r", tokens=TokenCounts.zero(),
        wall_time_ms=10,
    )
    assert rec.tool_result is None


def test_iteration_record_with_tool_result_round_trip() -> None:
    rec = IterationRecord(
        step=2, request_messages_digest="sha256:y",
        provider_response_kind="tool_use",
        tool_call=ToolCall(name="pot_odds", args={"to_call": 100, "pot": 250},
                           tool_use_id="tu_a"),
        text_content="checking pot odds",
        tokens=TokenCounts.zero(), wall_time_ms=42,
        tool_result={"value": 0.2857142857142857},
    )
    blob = rec.model_dump_json()
    rec2 = IterationRecord.model_validate_json(blob)
    assert rec2 == rec
    assert rec2.tool_result == {"value": 0.2857142857142857}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_llm_types.py::test_iteration_record_default_tool_result_is_none -v`
Expected: FAIL with `AttributeError: 'IterationRecord' object has no attribute 'tool_result'`.

- [ ] **Step 3: Add the field to `IterationRecord`**

Edit `src/llm_poker_arena/agents/llm/types.py`. Find the existing `IterationRecord` class (around line 77 after Phase 3b — 7 fields including `reasoning_artifacts: tuple[ReasoningArtifact, ...] = ()`). Add `tool_result` as the new last field:

```python
class IterationRecord(BaseModel):
    """spec §4.3: one per ReAct loop iteration. Written into agent_view_snapshots.

    `reasoning_artifacts` is a tuple (not the singular field name in spec §4.3
    code block) because §4.6 ReasoningArtifact carries `provider_raw_index`
    implying a list — Anthropic extended thinking can emit multiple thinking
    blocks per turn. Empty tuple is the default for providers that emit no
    reasoning artifacts (Anthropic without extended thinking, OpenAI Chat,
    DeepSeek-Chat / V3).

    `tool_result` is None for action-tool iterations (the result is the
    `final_action` commit) and for error iterations. It carries the utility
    tool's structured return (`{"value": float}` for pot_odds/spr, richer
    dict for future equity tools) for forensic + analytics use.
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
    tool_result: dict[str, Any] | None = None
```

(`Any` is already imported in types.py.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_llm_types.py -v`
Expected: 17 prior + 2 new = 19 tests pass.

- [ ] **Step 5: Sanity-run full suite — confirm existing IterationRecord callers still work with default**

Run: `.venv/bin/pytest tests/ -q --no-header -x`
Expected: 344 pass + 5 skip (342 baseline + 2 new from Task 0). Existing LLMAgent IterationRecord constructions don't pass `tool_result`, so they get None default.

- [ ] **Step 6: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/agents/llm/types.py tests/unit/test_llm_types.py && .venv/bin/mypy --strict src/llm_poker_arena/agents/llm/types.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/agents/llm/types.py tests/unit/test_llm_types.py
git commit -m "$(cat <<'EOF'
feat(types): IterationRecord.tool_result for utility-tool returns (Phase 3c-math Task 0)

spec §4.3 + §7.4: utility tool iterations populate tool_result with a
structured dict (e.g. {"value": 0.297} for pot_odds). Action-tool and
error iterations keep tool_result=None — the action's effect is
final_action; errors have no result.

Forward-compatible: existing IterationRecord constructions in LLMAgent
inherit the None default; AgentViewSnapshot dumps the new key
automatically via model_dump.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: Scaffold `tools/` subpackage with `run_utility_tool` skeleton

**Files:**
- Create: `src/llm_poker_arena/tools/__init__.py`
- Create: `src/llm_poker_arena/tools/runner.py`

**Why a stateless skeleton first**: Establishes the import surface that Tasks 2-7 will fill in. Subsequent tasks add real implementations behind the same import paths, so test imports stay stable.

- [ ] **Step 1: Create the package marker**

Create `src/llm_poker_arena/tools/__init__.py`:

```python
"""Utility tool subpackage (spec §5.2-§5.4).

Phase 3c-math ships the math-tools subset:
  - `pot_odds(view, *, to_call=None, pot=None) -> float`
  - `spr(view, *, stack=None, pot=None) -> float`

Phase 3c-equity will add `hand_equity_vs_ranges` and a `ToolRunner` class
(stateful, holds `EquityBackend`); for 3c-math the dispatcher is a stateless
function `run_utility_tool(view, name, args)` because no per-turn state needs
carrying.
"""
from llm_poker_arena.tools.runner import (
    ToolDispatchError,
    run_utility_tool,
    utility_tool_specs,
)

__all__ = [
    "ToolDispatchError",
    "run_utility_tool",
    "utility_tool_specs",
]
```

(The `pot_odds` and `spr` symbols are not re-exported from the top-level package — they're module-level functions reached via `tools.runner`. Keeps the public surface small.)

- [ ] **Step 2: Create the dispatcher skeleton**

Create `src/llm_poker_arena/tools/runner.py`:

```python
"""Stateless utility-tool dispatcher (spec §5.4 simplification for 3c-math).

`run_utility_tool(view, name, args)` returns the tool's result as a dict (e.g.
`{"value": 0.297}` for pot_odds/spr) on success. On unknown tool name or
malformed args, raises `ToolDispatchError`; LLMAgent's K+1 loop catches that,
encodes it as an error tool_result message, increments tool_usage_error_count
(analytics counter, NOT a retry budget), and continues until max_utility_calls
or commit (spec §4.2 + §4.1 BR2-05 reading).
"""
from __future__ import annotations

from typing import Any

from llm_poker_arena.engine.views import PlayerView


class ToolDispatchError(Exception):
    """Raised by `run_utility_tool` on unknown name or malformed args.

    LLMAgent treats this as a soft error: emit `{"error": str(e)}` as the
    tool_result, increment tool_usage_error_count, continue the loop.
    """


def run_utility_tool(
    view: PlayerView, name: str, args: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch to the registered utility tool. 3c-math skeleton — Tasks 2-3
    fill in pot_odds/spr branches.
    """
    raise NotImplementedError(
        "Phase 3c-math Tasks 2-3 implement pot_odds and spr; this skeleton "
        "is wired up in Task 1 only to establish the import surface."
    )


def utility_tool_specs(view: PlayerView) -> list[dict[str, Any]]:
    """Return the Anthropic-shape tool spec list for utility tools that are
    enabled on this view's session params. 3c-math skeleton — Task 5 fills in.

    `view.immutable_session_params.enable_math_tools` gates pot_odds + spr.
    """
    raise NotImplementedError(
        "Phase 3c-math Task 5 implements utility_tool_specs."
    )
```

- [ ] **Step 3: Verify import surface works**

Run: `.venv/bin/python -c "from llm_poker_arena.tools import ToolDispatchError, run_utility_tool, utility_tool_specs; print('ok')"`
Expected: `ok`. (The functions raise NotImplementedError when called, but importing them succeeds.)

- [ ] **Step 4: Sanity-run full suite — no regressions from new package**

Run: `.venv/bin/pytest tests/ -q --no-header -x`
Expected: 344 pass + 5 skip (no test changes from Task 1; new package isn't imported by any existing test).

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/tools/ && .venv/bin/mypy --strict src/llm_poker_arena/tools/`
Expected: clean. (Empty bodies + raise NotImplementedError pass mypy strict.)

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/tools/
git commit -m "$(cat <<'EOF'
chore(tools): scaffold tools/ subpackage with stateless dispatcher (Phase 3c-math Task 1)

3c-math uses a stateless `run_utility_tool(view, name, args)` dispatcher
instead of spec §5.4's stateful `ToolRunner` class. Justification: 3c-math
has no EquityBackend to carry per turn — both `view` and `legal_actions`
are already passed per call. The class lands in 3c-equity when it has
something stateful to hold.

Skeleton commits the import surface (Tasks 2-7 fill in implementations
behind these same names so tests' import statements stay stable).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `pot_odds` tool with optional args + view fallback

**Files:**
- Create: `src/llm_poker_arena/tools/pot_odds.py`
- Test: `tests/unit/test_pot_odds_tool.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_pot_odds_tool.py`:

```python
"""Tests for pot_odds utility tool.

Spec §5.2.3 defines pot_odds as zero-arg view-derived. Phase 3c-math ships
the optional-arg superset: zero-arg falls back to view, args override for
hypothetical reasoning (e.g. 'if I raise to 600, what is villain's pot_odds').
"""
from __future__ import annotations

import pytest

from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.tools.pot_odds import pot_odds


def _params(enable_math_tools: bool = True) -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=enable_math_tools, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _view(*, pot: int = 250, to_call: int = 100, my_stack: int = 9_750,
          ) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=pot, sidepots=(), my_stack=my_stack,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=to_call,
        to_call=to_call, pot_odds_required=to_call / (pot + to_call) if to_call else None,
        effective_stack=my_stack,
        seats_public=tuple(
            SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                            position_full="x", stack=10_000,
                            invested_this_hand=0, invested_this_round=0,
                            status="in_hand") for i in range(6)
        ),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=LegalActionSet(tools=(
            ActionToolSpec(name="fold", args={}),
            ActionToolSpec(name="call", args={}),
        )),
        opponent_stats={}, hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=_params(),
    )


def test_pot_odds_zero_arg_uses_view() -> None:
    """Spec §5.2.3 zero-arg behavior: read to_call + pot from view."""
    v = _view(pot=250, to_call=100)
    # 100 / (250 + 100) = 100 / 350 ≈ 0.2857
    assert pot_odds(v) == pytest.approx(100 / 350)


def test_pot_odds_with_args_overrides_view() -> None:
    """Optional-arg superset: hypothetical reasoning."""
    v = _view(pot=250, to_call=100)
    # If hero is considering raising to 600, villain faces to_call=600 vs
    # pot=250+600=850 (their call would be 600 chips into a 1450 pot).
    assert pot_odds(v, to_call=600, pot=850) == pytest.approx(600 / 1450)


def test_pot_odds_partial_args_mixes_with_view() -> None:
    """Caller can override only one of (to_call, pot) — the other comes from view."""
    v = _view(pot=250, to_call=100)
    # Override to_call only; pot stays at view's 250.
    assert pot_odds(v, to_call=400) == pytest.approx(400 / 650)
    # Override pot only; to_call stays at view's 100.
    assert pot_odds(v, pot=900) == pytest.approx(100 / 1000)


def test_pot_odds_zero_to_call_returns_zero() -> None:
    """When to_call == 0 (we can check), pot_odds is 0 by convention.
    This avoids the divide-by-zero AND matches the user-prompt convention
    where pot_odds_required becomes None in that case.
    """
    v = _view(pot=250, to_call=0)
    assert pot_odds(v) == 0.0


def test_pot_odds_negative_to_call_raises() -> None:
    """Negative to_call is structurally impossible (engine clamps >= 0).
    If the LLM passes a negative arg, that's a user-input bug — raise."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    v = _view(pot=250, to_call=100)
    with pytest.raises(ToolDispatchError, match="to_call must be >= 0"):
        pot_odds(v, to_call=-100)


def test_pot_odds_negative_pot_raises() -> None:
    from llm_poker_arena.tools.runner import ToolDispatchError
    v = _view(pot=250, to_call=100)
    with pytest.raises(ToolDispatchError, match="pot must be >= 0"):
        pot_odds(v, pot=-50)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_pot_odds_tool.py -v`
Expected: FAIL with `ImportError: cannot import name 'pot_odds' from 'llm_poker_arena.tools.pot_odds'` (file doesn't exist yet).

- [ ] **Step 3: Implement `pot_odds`**

Create `src/llm_poker_arena/tools/pot_odds.py`:

```python
"""pot_odds utility tool (spec §5.2.3 + Phase 3c-math optional-arg superset).

Zero-arg call: read to_call + pot from PlayerView (matches spec §5.2.3).
Args call: use provided values for hypothetical bet-sizing reasoning.

Convention: when to_call == 0 (check is legal), return 0.0 instead of
NaN/error — matches the user-prompt convention that pot_odds_required is
None when to_call == 0.
"""
from __future__ import annotations

from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.tools.runner import ToolDispatchError


def pot_odds(
    view: PlayerView,
    *,
    to_call: int | None = None,
    pot: int | None = None,
) -> float:
    """Return pot odds = to_call / (pot + to_call), or 0.0 if to_call == 0.

    Both args are optional; missing args fall back to view fields.
    Raises ToolDispatchError on negative inputs.
    """
    effective_to_call = view.to_call if to_call is None else to_call
    effective_pot = view.pot if pot is None else pot

    if effective_to_call < 0:
        raise ToolDispatchError(f"to_call must be >= 0, got {effective_to_call}")
    if effective_pot < 0:
        raise ToolDispatchError(f"pot must be >= 0, got {effective_pot}")

    if effective_to_call == 0:
        return 0.0
    return effective_to_call / (effective_pot + effective_to_call)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_pot_odds_tool.py -v`
Expected: 6 tests pass.

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/tools/pot_odds.py tests/unit/test_pot_odds_tool.py && .venv/bin/mypy --strict src/llm_poker_arena/tools/pot_odds.py tests/unit/test_pot_odds_tool.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/tools/pot_odds.py tests/unit/test_pot_odds_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): pot_odds with optional-arg superset (Phase 3c-math Task 2)

Spec §5.2.3 defines pot_odds as zero-arg view-derived. This ships the
optional-arg superset: zero-arg matches spec; args support hypothetical
reasoning (e.g. 'if I raise to 600, what is villain's pot_odds').

Justification: zero-arg pot_odds is 100% redundant with pot_odds_required
in user prompt (Phase 3d verified Claude Haiku cites it 100%). Adding
args support unlocks bet-sizing reasoning for ~10 LOC.

Convention: to_call == 0 → return 0.0 (no divide-by-zero, matches
pot_odds_required=None convention in user prompt).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `spr` tool with optional args + view fallback

**Files:**
- Create: `src/llm_poker_arena/tools/spr.py`
- Test: `tests/unit/test_spr_tool.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_spr_tool.py`:

```python
"""Tests for spr (stack-to-pot ratio) utility tool.

Spec §5.2.3 defines spr as zero-arg view-derived. Optional-arg superset
mirrors pot_odds: zero-arg falls back to view, args support hypothetical
post-flop SPR reasoning (e.g. 'after I raise to X, what is the SPR on flop').
"""
from __future__ import annotations

import pytest

from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.tools.spr import spr


def _params() -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=True, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _view(*, pot: int = 1_000, my_stack: int = 9_000,
          effective_stack: int = 9_000) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=pot, sidepots=(), my_stack=my_stack,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=0,
        to_call=0, pot_odds_required=None,
        effective_stack=effective_stack,
        seats_public=tuple(
            SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                            position_full="x", stack=10_000,
                            invested_this_hand=0, invested_this_round=0,
                            status="in_hand") for i in range(6)
        ),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=LegalActionSet(tools=(
            ActionToolSpec(name="check", args={}),
        )),
        opponent_stats={}, hand_id=1, street=Street.FLOP, button_seat=0,
        turn_seed=42, immutable_session_params=_params(),
    )


def test_spr_zero_arg_uses_view_effective_stack() -> None:
    """Spec §5.2.3 zero-arg: SPR = effective_stack / pot.

    Effective stack (not raw my_stack) is the right denominator because SPR
    measures commitment given the smallest live stack — what's actually at
    risk if hands go to showdown.
    """
    v = _view(pot=1_000, my_stack=9_000, effective_stack=9_000)
    assert spr(v) == 9.0


def test_spr_with_args_overrides_view() -> None:
    """Hypothetical: 'after I raise pot to 3000, what's the new SPR?'"""
    v = _view(pot=1_000, my_stack=9_000, effective_stack=9_000)
    # Hero stacks shrunk to 6000 after putting in 3000; new pot = 4000.
    assert spr(v, stack=6_000, pot=4_000) == 1.5


def test_spr_partial_args_mixes_with_view() -> None:
    v = _view(pot=1_000, my_stack=9_000, effective_stack=9_000)
    # Only override stack; pot stays at view's 1000.
    assert spr(v, stack=4_000) == 4.0
    # Only override pot; stack stays at view's effective_stack=9000.
    assert spr(v, pot=2_000) == 4.5


def test_spr_zero_pot_raises() -> None:
    """SPR with pot=0 is undefined (preflop before blinds posted is the only
    possible case, and that's a degenerate scenario). Raise rather than emit
    inf."""
    from llm_poker_arena.tools.runner import ToolDispatchError
    v = _view(pot=1_000, my_stack=9_000)
    with pytest.raises(ToolDispatchError, match="pot must be > 0"):
        spr(v, pot=0)


def test_spr_negative_stack_raises() -> None:
    from llm_poker_arena.tools.runner import ToolDispatchError
    v = _view(pot=1_000, my_stack=9_000)
    with pytest.raises(ToolDispatchError, match="stack must be >= 0"):
        spr(v, stack=-100)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_spr_tool.py -v`
Expected: FAIL with `ImportError: cannot import name 'spr'`.

- [ ] **Step 3: Implement `spr`**

Create `src/llm_poker_arena/tools/spr.py`:

```python
"""spr (stack-to-pot ratio) utility tool.

Spec §5.2.3 defines spr as zero-arg view-derived (uses effective_stack / pot,
NOT my_stack / pot — effective_stack is the correct commitment measure).

Optional-arg superset mirrors pot_odds: hypothetical post-flop SPR after a
planned bet/raise.
"""
from __future__ import annotations

from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.tools.runner import ToolDispatchError


def spr(
    view: PlayerView,
    *,
    stack: int | None = None,
    pot: int | None = None,
) -> float:
    """Return stack-to-pot ratio = stack / pot.

    Default stack = view.effective_stack (not my_stack — effective is what's
    actually at risk in a showdown).
    Default pot = view.pot.
    Raises ToolDispatchError on pot <= 0 or negative stack.
    """
    effective_stack = view.effective_stack if stack is None else stack
    effective_pot = view.pot if pot is None else pot

    if effective_stack < 0:
        raise ToolDispatchError(f"stack must be >= 0, got {effective_stack}")
    if effective_pot <= 0:
        raise ToolDispatchError(f"pot must be > 0, got {effective_pot}")

    return effective_stack / effective_pot
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_spr_tool.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/tools/spr.py tests/unit/test_spr_tool.py && .venv/bin/mypy --strict src/llm_poker_arena/tools/spr.py tests/unit/test_spr_tool.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/tools/spr.py tests/unit/test_spr_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): spr with optional-arg superset (Phase 3c-math Task 3)

Spec §5.2.3 zero-arg behavior: SPR = effective_stack / pot. Effective
stack (not raw my_stack) is the right denominator because it measures
what's actually at risk in showdown.

Optional-arg superset matches pot_odds — supports 'after I raise to X,
new SPR is Y' hypothetical reasoning.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Wire `run_utility_tool` dispatcher

**Files:**
- Modify: `src/llm_poker_arena/tools/runner.py:run_utility_tool`
- Test: `tests/unit/test_run_utility_tool.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_run_utility_tool.py`:

```python
"""Tests for run_utility_tool dispatcher (spec §5.4 simplified)."""
from __future__ import annotations

import pytest

from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.tools import ToolDispatchError, run_utility_tool


def _view() -> PlayerView:
    params = SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=True, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=250, sidepots=(), my_stack=9_750,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=100 / 350,
        effective_stack=9_750,
        seats_public=tuple(
            SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                            position_full="x", stack=10_000,
                            invested_this_hand=0, invested_this_round=0,
                            status="in_hand") for i in range(6)
        ),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=LegalActionSet(tools=(
            ActionToolSpec(name="fold", args={}),
            ActionToolSpec(name="call", args={}),
        )),
        opponent_stats={}, hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=params,
    )


def test_dispatch_pot_odds_zero_arg_returns_value_dict() -> None:
    v = _view()
    result = run_utility_tool(v, "pot_odds", {})
    # Spec §7.4 result shape: {"value": float}
    assert set(result.keys()) == {"value"}
    assert result["value"] == pytest.approx(100 / 350)


def test_dispatch_pot_odds_with_args() -> None:
    v = _view()
    result = run_utility_tool(v, "pot_odds", {"to_call": 600, "pot": 850})
    assert result["value"] == pytest.approx(600 / 1450)


def test_dispatch_spr() -> None:
    v = _view()
    result = run_utility_tool(v, "spr", {})
    assert result["value"] == pytest.approx(9_750 / 250)


def test_dispatch_unknown_tool_raises() -> None:
    v = _view()
    with pytest.raises(ToolDispatchError, match="Unknown utility tool: foo"):
        run_utility_tool(v, "foo", {})


def test_dispatch_propagates_pot_odds_validation_error() -> None:
    """Negative to_call from LLM args must surface as ToolDispatchError —
    LLMAgent will catch it and feed back to the model."""
    v = _view()
    with pytest.raises(ToolDispatchError, match="to_call must be >= 0"):
        run_utility_tool(v, "pot_odds", {"to_call": -50})


def test_dispatch_rejects_extra_args() -> None:
    """Codex audit IMPORTANT-3: input_schema declares additionalProperties=False,
    so extras are REJECTED (not silently dropped). Surfacing the error lets
    the model learn the schema rather than rely on undefined behavior."""
    v = _view()
    with pytest.raises(ToolDispatchError, match="unexpected args"):
        run_utility_tool(v, "pot_odds", {"to_call": 100, "garbage": "x"})


def test_dispatch_rejects_string_arg() -> None:
    """Codex audit IMPORTANT-2: model may pass `{"to_call": "100"}` as string;
    input_schema doesn't enforce, dispatcher must validate before passing
    through (otherwise comparison `"100" < 0` raises uncaught TypeError)."""
    v = _view()
    with pytest.raises(ToolDispatchError, match="must be an integer"):
        run_utility_tool(v, "pot_odds", {"to_call": "100"})


def test_dispatch_rejects_float_arg() -> None:
    v = _view()
    with pytest.raises(ToolDispatchError, match="must be an integer"):
        run_utility_tool(v, "pot_odds", {"pot": 100.5})


def test_dispatch_rejects_bool_arg() -> None:
    """bool is a subclass of int in Python (True == 1, False == 0). Without
    explicit rejection, a confused model could pass `to_call=True` and get
    away with it. Reject bools explicitly."""
    v = _view()
    with pytest.raises(ToolDispatchError, match="must be an integer"):
        run_utility_tool(v, "pot_odds", {"to_call": True})


def test_dispatch_rejects_none_arg() -> None:
    """None passed as a value (not as 'arg absent') is malformed. The
    dispatcher passes args dict to the tool; the tool's signature uses
    `int | None` defaults but only when the KEY is missing. An explicit
    None value with the key present should be rejected."""
    v = _view()
    with pytest.raises(ToolDispatchError, match="must be an integer"):
        run_utility_tool(v, "pot_odds", {"to_call": None})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_run_utility_tool.py -v`
Expected: FAIL with `NotImplementedError: Phase 3c-math Tasks 2-3 implement pot_odds and spr` (Task 1's skeleton).

- [ ] **Step 3: Implement the dispatcher**

Edit `src/llm_poker_arena/tools/runner.py`. Replace the `run_utility_tool` skeleton with:

```python
# Allowed kwargs per tool. Used for both extra-key rejection and the
# whitelist filter when dispatching to the per-tool function.
_ALLOWED_ARGS: dict[str, frozenset[str]] = {
    "pot_odds": frozenset({"to_call", "pot"}),
    "spr": frozenset({"stack", "pot"}),
}


def _validate_int_arg(name: str, value: Any) -> None:
    """Codex audit IMPORTANT-2 fix: input_schema declares integer type, but
    Anthropic SDK does NOT enforce — model can pass strings, floats, or bools.
    Validate at the tool boundary and surface as ToolDispatchError so LLMAgent
    feeds the error back to the model.

    Note: bool is a subclass of int in Python (True == 1, False == 0), so a
    plain isinstance(value, int) accepts bools. We reject bools explicitly —
    a model passing `to_call=True` is almost certainly confused.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolDispatchError(
            f"{name} must be an integer; got {type(value).__name__}={value!r}"
        )


def run_utility_tool(
    view: PlayerView, name: str, args: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch to the registered utility tool. Returns `{"value": float}` for
    pot_odds/spr; richer dicts for future tools. Raises `ToolDispatchError`
    on unknown tool name, extra args, or args type/value validation failure.

    Codex audit IMPORTANT-3 fix: extra args are REJECTED (not silently
    dropped). The tool spec input_schema declares `additionalProperties: False`
    — silently dropping would let the model rely on undefined behavior.
    """
    from llm_poker_arena.tools.pot_odds import pot_odds
    from llm_poker_arena.tools.spr import spr

    if name not in _ALLOWED_ARGS:
        raise ToolDispatchError(f"Unknown utility tool: {name}")

    allowed = _ALLOWED_ARGS[name]
    extra = set(args) - allowed
    if extra:
        raise ToolDispatchError(
            f"{name} received unexpected args {sorted(extra)}; "
            f"allowed: {sorted(allowed)}"
        )
    for k, v in args.items():
        _validate_int_arg(f"{name}.{k}", v)

    if name == "pot_odds":
        return {"value": pot_odds(view, **args)}
    return {"value": spr(view, **args)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_run_utility_tool.py -v`
Expected: 6 tests pass.

- [ ] **Step 5: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/tools/runner.py tests/unit/test_run_utility_tool.py && .venv/bin/mypy --strict src/llm_poker_arena/tools/runner.py tests/unit/test_run_utility_tool.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/tools/runner.py tests/unit/test_run_utility_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): run_utility_tool dispatcher for pot_odds + spr (Phase 3c-math Task 4)

Stateless dispatcher (spec §5.4 simplified — see plan §"Spec
Inconsistencies"). Returns {"value": float} per spec §7.4; raises
ToolDispatchError on unknown name or args validation failure.

Extra args silently dropped (a confused LLM that adds garbage fields
still gets a useful result instead of TypeError). Inline imports avoid
circular dependency with the per-tool modules.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `utility_tool_specs` — Anthropic-shape tool list driven by SessionConfig flag

**Files:**
- Modify: `src/llm_poker_arena/tools/runner.py:utility_tool_specs`
- Test: `tests/unit/test_utility_tool_specs.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_utility_tool_specs.py`:

```python
"""Tests for utility_tool_specs — gated by SessionConfig.enable_math_tools."""
from __future__ import annotations

from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)
from llm_poker_arena.tools import utility_tool_specs


def _view(*, enable_math_tools: bool) -> PlayerView:
    params = SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=enable_math_tools, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=250, sidepots=(), my_stack=9_750,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=100 / 350,
        effective_stack=9_750,
        seats_public=tuple(
            SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                            position_full="x", stack=10_000,
                            invested_this_hand=0, invested_this_round=0,
                            status="in_hand") for i in range(6)
        ),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=LegalActionSet(tools=(
            ActionToolSpec(name="fold", args={}),
        )),
        opponent_stats={}, hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=params,
    )


def test_specs_empty_when_math_tools_disabled() -> None:
    v = _view(enable_math_tools=False)
    assert utility_tool_specs(v) == []


def test_specs_contains_pot_odds_and_spr_when_enabled() -> None:
    v = _view(enable_math_tools=True)
    specs = utility_tool_specs(v)
    names = {s["name"] for s in specs}
    assert names == {"pot_odds", "spr"}


def test_pot_odds_spec_schema_shape() -> None:
    """Anthropic tool spec format. input_schema must declare optional
    integer args (LLM may call zero-arg or with one/both args)."""
    v = _view(enable_math_tools=True)
    specs = utility_tool_specs(v)
    pot_spec = next(s for s in specs if s["name"] == "pot_odds")
    assert "description" in pot_spec
    schema = pot_spec["input_schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    # Optional args: required is empty list.
    assert schema.get("required", []) == []
    # to_call + pot are integer-typed.
    props = schema["properties"]
    assert props["to_call"]["type"] == "integer"
    assert props["pot"]["type"] == "integer"


def test_spr_spec_schema_shape() -> None:
    v = _view(enable_math_tools=True)
    specs = utility_tool_specs(v)
    spr_spec = next(s for s in specs if s["name"] == "spr")
    schema = spr_spec["input_schema"]
    assert schema["type"] == "object"
    assert schema.get("required", []) == []
    props = schema["properties"]
    assert props["stack"]["type"] == "integer"
    assert props["pot"]["type"] == "integer"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_utility_tool_specs.py -v`
Expected: FAIL with `NotImplementedError: Phase 3c-math Task 5 implements utility_tool_specs`.

- [ ] **Step 3: Implement `utility_tool_specs`**

Edit `src/llm_poker_arena/tools/runner.py`. Replace the `utility_tool_specs` skeleton with:

```python
def utility_tool_specs(view: PlayerView) -> list[dict[str, Any]]:
    """Return the Anthropic-shape tool spec list for utility tools enabled on
    this view's session params. Empty list when `enable_math_tools=False`.

    spec §5.3 build_tool_specs reads view.immutable_session_params.enable_math_tools.
    Phase 3c-math ships pot_odds + spr only; 3c-equity adds hand_equity_vs_ranges.
    """
    if not view.immutable_session_params.enable_math_tools:
        return []
    return [
        {
            "name": "pot_odds",
            "description": (
                "Compute pot odds = to_call / (pot + to_call). Optional args "
                "let you compute hypothetical scenarios (e.g. 'if I raise to "
                "X, what pot odds does villain face'). Zero-arg call uses the "
                "current to_call and pot from your turn state."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "to_call": {
                        "type": "integer",
                        "description": "Optional override for the to_call amount; defaults to current.",
                        "minimum": 0,
                    },
                    "pot": {
                        "type": "integer",
                        "description": "Optional override for the pot size; defaults to current.",
                        "minimum": 0,
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        },
        {
            "name": "spr",
            "description": (
                "Compute stack-to-pot ratio = stack / pot. Default stack is "
                "your effective_stack (the smallest live stack at risk for "
                "showdown). Optional args support post-flop SPR planning "
                "(e.g. 'after I raise to X, new SPR on flop is Y')."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "stack": {
                        "type": "integer",
                        "description": "Optional override for the stack; defaults to effective_stack.",
                        "minimum": 0,
                    },
                    "pot": {
                        "type": "integer",
                        "description": "Optional override for the pot size; defaults to current.",
                        "minimum": 1,
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_utility_tool_specs.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Sanity-run full suite — confirm tools subpackage tests all green**

Run: `.venv/bin/pytest tests/ -q --no-header -x`
Expected: 369 pass + 5 skip (342 baseline + 2 from T0 + 6 pot_odds + 5 spr + 10 dispatcher + 4 specs = 369).

- [ ] **Step 6: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/tools/ tests/unit/test_utility_tool_specs.py && .venv/bin/mypy --strict src/llm_poker_arena/tools/ tests/unit/test_utility_tool_specs.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/tools/runner.py tests/unit/test_utility_tool_specs.py
git commit -m "$(cat <<'EOF'
feat(tools): utility_tool_specs gated on enable_math_tools (Phase 3c-math Task 5)

Anthropic-shape tool spec list. Empty when SessionConfig.enable_math_tools
is False; pot_odds + spr when True (3c-math scope; 3c-equity will add
hand_equity_vs_ranges).

input_schema declares optional args (required=[]) so LLM can call
zero-arg (matches spec §5.2.3) OR with hypothetical values. minimum=0
for non-negative ints; spr.pot has minimum=1 (zero pot is undefined).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: LLMAgent constructor accepts `tool_runner` callable

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/llm_agent.py:LLMAgent.__init__`
- Test: `tests/unit/test_llm_agent_react_loop.py` (append constructor test)

**Why a separate task before the loop refactor**: Lets us land + verify the constructor signature change in isolation. The refactored loop in Task 7 then has a stable hook to call.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_llm_agent_react_loop.py`:

```python
def test_llm_agent_accepts_optional_tool_runner_callable() -> None:
    """Phase 3c-math: LLMAgent.__init__ accepts an optional tool_runner
    callable; default is the stateless run_utility_tool from tools subpackage.
    Constructor signature change only — no behavior change in this task."""
    from llm_poker_arena.agents.llm.providers.mock import (
        MockLLMProvider, MockResponseScript,
    )
    from llm_poker_arena.tools import run_utility_tool

    provider = MockLLMProvider(script=MockResponseScript(responses=()))
    # Default: no tool_runner passed.
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    assert agent._tool_runner is run_utility_tool

    # Override: custom callable.
    def fake_runner(view: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"value": 0.5}
    agent2 = LLMAgent(provider=provider, model="m1", temperature=0.7,
                     tool_runner=fake_runner)
    assert agent2._tool_runner is fake_runner
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py::test_llm_agent_accepts_optional_tool_runner_callable -v`
Expected: FAIL — `LLMAgent.__init__()` doesn't accept `tool_runner`, OR `agent._tool_runner` doesn't exist.

- [ ] **Step 3: Add the constructor parameter**

Edit `src/llm_poker_arena/agents/llm/llm_agent.py`. Add the import + extend `__init__`:

```python
from collections.abc import Callable

from llm_poker_arena.tools import run_utility_tool as _default_tool_runner
```

(Insert imports near other top-level imports.)

Modify `__init__`:

```python
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
```

(Note: `Any` is the first arg type because `PlayerView` is imported at the bottom of the imports — using `Callable[[Any, str, dict], dict]` avoids forward-reference noise. Could refine to `Callable[[PlayerView, str, dict], dict]` but `Any` is consistent with how other generic callables are typed in this file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py::test_llm_agent_accepts_optional_tool_runner_callable -v`
Expected: PASS.

- [ ] **Step 5: Sanity-run all 22 existing ReAct tests + new test**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py -v`
Expected: 21 prior + 1 new = 22 pass. (Constructor change has default → no existing test breaks.)

- [ ] **Step 6: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_llm_agent_react_loop.py && .venv/bin/mypy --strict src/llm_poker_arena/agents/llm/llm_agent.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_llm_agent_react_loop.py
git commit -m "$(cat <<'EOF'
feat(agents): LLMAgent accepts optional tool_runner callable (Phase 3c-math Task 6)

Constructor signature change only — no behavior change. Task 7 wires the
tool_runner into _decide_inner's K+1 ReAct loop.

Default is the stateless run_utility_tool from tools subpackage; tests
can override with a fake for deterministic K+1 mock scenarios.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: K+1 ReAct loop — utility-tool dispatch branch

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/llm_agent.py:_decide_inner` (the central refactor)
- Test: `tests/unit/test_llm_agent_react_loop_k1.py` (NEW; isolates K+1 tests from existing K=0 test file)

**Scope of this task**: Add the third response branch (utility-tool dispatch) to `_decide_inner`. Does NOT yet add final-step pressure (Task 8). Does NOT yet expose tools to provider (current behavior: `_action_tool_specs(view)` only). Without tool exposure, this branch can only fire from a mock that synthesizes utility tool calls — that's exactly what the new tests do.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_llm_agent_react_loop_k1.py`:

```python
"""K+1 ReAct loop tests (Phase 3c-math).

Phase 3a/3b LLMAgent runs K=0 (one action step + retries). Phase 3c-math
widens to K+1: up to `max_utility_calls` utility-tool calls before the
forced action commit. These tests use MockLLMProvider to drive
deterministic [utility, utility, action] sequences and assert the
IterationRecord chain populates tool_result correctly.
"""
from __future__ import annotations

import asyncio
from typing import Any

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
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.types import Street
from llm_poker_arena.engine.views import (
    ActionToolSpec,
    LegalActionSet,
    PlayerView,
    SeatPublicInfo,
    SessionParamsView,
)


def _params(*, max_utility_calls: int = 5) -> SessionParamsView:
    return SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=max_utility_calls, rationale_required=True,
        enable_math_tools=True, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )


def _view(legal: LegalActionSet, params: SessionParamsView | None = None) -> PlayerView:
    return PlayerView(
        my_seat=3, my_hole_cards=("As", "Kd"), community=(),
        pot=250, sidepots=(), my_stack=9_750,
        my_invested_this_hand=0, my_invested_this_round=0,
        current_bet_to_match=100,
        to_call=100, pot_odds_required=100 / 350,
        effective_stack=9_750,
        seats_public=tuple(
            SeatPublicInfo(seat=i, label=f"P{i}", position_short="UTG",
                            position_full="x", stack=10_000,
                            invested_this_hand=0, invested_this_round=0,
                            status="in_hand") for i in range(6)
        ),
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        action_order_this_street=(3, 4, 5, 0, 1, 2),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        already_acted_this_street=(), hand_history=(),
        legal_actions=legal, opponent_stats={},
        hand_id=1, street=Street.PREFLOP, button_seat=0,
        turn_seed=42, immutable_session_params=params or _params(),
    )


def _resp(*tool_calls: ToolCall, text: str = "rationale") -> LLMResponse:
    return LLMResponse(
        provider="mock", model="m1", stop_reason="tool_use",
        tool_calls=tuple(tool_calls), text_content=text,
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )


def test_k1_happy_utility_then_action() -> None:
    """LLM calls pot_odds, then commits fold. IterationRecord chain has
    2 entries: first with tool_call.name='pot_odds' + tool_result, second
    with tool_call.name='fold' + tool_result=None."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="pot_odds", args={}, tool_use_id="tu1")),
        _resp(ToolCall(name="fold", args={}, tool_use_id="tu2")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="fold", args={})
    assert len(result.iterations) == 2
    util_iter, action_iter = result.iterations
    assert util_iter.tool_call is not None
    assert util_iter.tool_call.name == "pot_odds"
    assert util_iter.tool_result == {"value": 100 / 350}
    assert action_iter.tool_call is not None
    assert action_iter.tool_call.name == "fold"
    assert action_iter.tool_result is None
    assert result.tool_usage_error_count == 0


def test_k1_two_utility_then_action() -> None:
    """LLM chains pot_odds → spr → action_call."""
    legal = LegalActionSet(tools=(
        ActionToolSpec(name="fold", args={}),
        ActionToolSpec(name="call", args={}),
    ))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="pot_odds", args={"to_call": 600, "pot": 850},
                        tool_use_id="tu1")),
        _resp(ToolCall(name="spr", args={}, tool_use_id="tu2")),
        _resp(ToolCall(name="call", args={}, tool_use_id="tu3")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="call", args={})
    assert len(result.iterations) == 3
    pot_iter, spr_iter, action_iter = result.iterations
    assert pot_iter.tool_result == {"value": 600 / 1450}
    assert spr_iter.tool_result == {"value": 9_750 / 250}
    assert action_iter.tool_result is None


def test_k1_utility_with_bad_args_increments_error_count() -> None:
    """ToolDispatchError → tool_usage_error_count += 1; loop continues; LLM
    sees error tool_result and recovers on next iteration. Spec §4.2 lines
    1019-1021. Does NOT consume any retry budget (Q4 brainstorming decision)."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        # Bad args first.
        _resp(ToolCall(name="pot_odds", args={"to_call": -50},
                        tool_use_id="tu_bad")),
        # Then commit.
        _resp(ToolCall(name="fold", args={}, tool_use_id="tu2")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="fold", args={})
    assert result.tool_usage_error_count == 1
    # Retry budgets all stay at 0 — utility errors don't consume them.
    assert result.api_retry_count == 0
    assert result.illegal_action_retry_count == 0
    assert result.no_tool_retry_count == 0
    assert len(result.iterations) == 2
    bad_iter = result.iterations[0]
    assert bad_iter.tool_result is not None
    assert "error" in bad_iter.tool_result


def test_k1_unknown_tool_name_consumes_illegal_retry() -> None:
    """LLM hallucinates a tool name not in either action_tools OR
    utility_names → falls through both branches to the illegal-action path
    per spec §4.2 line 1027 (codex audit IMPORTANT-1 fix). Consumes
    illegal_action_retry budget, NOT tool_usage_error_count."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="hallucinated_equity", args={"villain": "AKs"},
                        tool_use_id="tu_h")),
        _resp(ToolCall(name="fold", args={}, tool_use_id="tu2")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="fold", args={})
    # Unknown tool name is treated as illegal action (spec §4.2 line 1027),
    # NOT a utility-tool error. tool_usage_error_count stays at 0.
    assert result.illegal_action_retry_count == 1
    assert result.tool_usage_error_count == 0


def test_k1_mixed_utility_and_action_in_one_response_is_misuse() -> None:
    """Codex audit NIT-2: when the response has BOTH a utility tool_call AND
    an action tool_call (multi-tool-call response), the existing multi-tool-
    call branch in _decide_inner fires BEFORE the utility-dispatch branch
    (the dispatch branch only inspects response.tool_calls[0] AFTER the
    multi-call check). The whole response is rejected as protocol misuse;
    no action is accepted from it; tool_usage_error_count increments and
    tool_usage_retry budget is consumed."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        # Bad multi-call: pot_odds + fold in one response.
        _resp(
            ToolCall(name="pot_odds", args={}, tool_use_id="tu_p"),
            ToolCall(name="fold", args={}, tool_use_id="tu_f"),
        ),
        # Recovery response with single tool_call.
        _resp(ToolCall(name="fold", args={}, tool_use_id="tu_recover")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action == Action(tool_name="fold", args={})
    # The mixed response was rejected as misuse → tool_usage_error_count=1,
    # tool_usage_retry consumed=1 (Phase 3d's separate retry slot).
    assert result.tool_usage_error_count == 1


def test_k1_max_utility_calls_exhaustion_falls_back() -> None:
    """LLM keeps calling utility tools past max_utility_calls → fallback."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    # max_utility_calls=2; LLM tries pot_odds 3 times.
    params = _params(max_utility_calls=2)
    responses = tuple(
        _resp(ToolCall(name="pot_odds", args={}, tool_use_id=f"tu{i}"))
        for i in range(10)
    )
    script = MockResponseScript(responses=responses)
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal, params=params)))
    # After 2 utility calls, LLM still calls pot_odds → no_tool_retry budget
    # catches it (final-step pressure in Task 8 will short-circuit this; for
    # Task 7 the loop just exhausts MAX_STEPS and falls back).
    assert result.default_action_fallback is True
    # At least 2 utility iterations happened.
    util_count = sum(
        1 for it in result.iterations
        if it.tool_call is not None and it.tool_call.name == "pot_odds"
    )
    assert util_count >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop_k1.py -v`
Expected: 5 tests fail. Current `_decide_inner` treats every tool_call as an action attempt → invokes `validate_action` on `pot_odds` → `is_valid=False` (not in legal set) → triggers `illegal_action_retry`. Won't dispatch to ToolRunner.

- [ ] **Step 3: Refactor `_decide_inner` to add utility-tool dispatch**

Edit `src/llm_poker_arena/agents/llm/llm_agent.py`. The change has 3 parts:

**(3a) Track utility_count + import utility tool names**

At the top of `_decide_inner`:

```python
    async def _decide_inner(self, view: PlayerView) -> TurnDecisionResult:
        from llm_poker_arena.tools import ToolDispatchError, utility_tool_specs
        MAX_API_RETRY = 1
        MAX_ILLEGAL_RETRY = 1
        MAX_NO_TOOL_RETRY = 1
        MAX_TOOL_USAGE_RETRY = 1  # spec §4.1 BR2-05: independent budget for action-tool misuse
        # MAX_STEPS bound: max_utility_calls + 4 retry budgets + 1 commit slot.
        # Default max_utility_calls=5 → MAX_STEPS=10. Caps runaway loops.
        max_utility_calls = view.immutable_session_params.max_utility_calls
        MAX_STEPS = max_utility_calls + 5

        api_retry = 0
        illegal_retry = 0
        no_tool_retry = 0
        tool_usage_retry = 0
        tool_usage_error_count = 0
        utility_count = 0  # how many utility tool calls succeeded so far this turn

        iterations: list[IterationRecord] = []
        system_text, messages = self._build_initial_state(view)
        # Tool list passed to provider: action tools + (utility tools if enabled).
        # Task 8 will switch to action-only on final step; for Task 7, both
        # are passed every step (LLM may exhaust max_utility_calls and we
        # rely on no_tool_retry for fallback).
        action_tools = _action_tool_specs(view)
        utility_specs = utility_tool_specs(view)
        all_tools = action_tools + utility_specs
        turn_start = time.monotonic()
        total_tokens = TokenCounts.zero()
```

**(3b) Inside the response-handling branches**, after the multi-tool-call branch and BEFORE the rationale_required branch (which inspects `tc = response.tool_calls[0]` for action), add the utility-dispatch branch. The condition: `tc.name not in ACTION_TOOL_NAMES`. Place this branch immediately after the multi-tool-call check and before the action-validate logic:

Find the section that starts with `tc = response.tool_calls[0]` (around line 290). Replace the surrounding logic with:

```python
            tc = response.tool_calls[0]
            ACTION_TOOL_NAMES = {"fold", "check", "call", "bet", "raise_to", "all_in"}
            # Codex audit IMPORTANT-1 fix: only dispatch as utility when the
            # name matches a CURRENTLY-REGISTERED utility tool. Unknown names
            # (model hallucinated something) go through the illegal-retry
            # path per spec §4.2 line 1027, NOT the utility error path.
            # `utility_names` is empty when enable_math_tools=False, so any
            # non-action tc.name falls through to illegal_retry — preserves
            # K=0 behavior exactly.
            utility_names = {s["name"] for s in utility_specs}

            # Utility-tool dispatch branch (Phase 3c-math K+1).
            if tc.name in utility_names:
                # Tool name is registered; dispatch via runner.
                # Bad args → ToolDispatchError, counted but loop continues.
                try:
                    tool_result = self._tool_runner(view, tc.name, dict(tc.args or {}))
                except ToolDispatchError as e:
                    tool_result = {"error": str(e)}
                    tool_usage_error_count += 1

                iter_record = IterationRecord(
                    step=step + 1,
                    request_messages_digest=digest,
                    provider_response_kind="tool_use",
                    tool_call=tc,
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
                # through MAX_STEPS instead. tool_usage_error_count tracks
                # the failures separately for analytics.
                utility_count += 1

                # Feed tool result back to the model and continue the loop.
                # The provider's tool_result message format handles per-provider
                # protocol (Anthropic bundles, OpenAI separates). `json` is
                # already imported at module top.
                messages.append(
                    self._provider.build_assistant_message_for_replay(response)
                )
                messages.extend(self._provider.build_tool_result_messages(
                    tool_calls=(tc,),
                    is_error="error" in tool_result,
                    content=json.dumps(tool_result),
                ))
                continue

            # ===== ACTION TOOL BRANCH (existing logic unchanged below) =====
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
                return TurnDecisionResult(...)  # existing
            # ... existing illegal_action_retry logic
```

(The full replacement preserves all 4 existing retry branches — api_retry, illegal_retry, no_tool_retry, tool_usage_retry — unchanged. Only the new utility-dispatch branch is inserted before the action-validate logic.)

**(3c) Update the provider call to send all_tools instead of action_tools**

In the `await asyncio.wait_for(self._provider.complete(...))` call near line 127:

```python
                response = await asyncio.wait_for(
                    self._provider.complete(
                        system=system_text,
                        messages=messages, tools=all_tools,
                        temperature=self._temperature, seed=self._seed,
                    ),
                    timeout=self._per_iter_timeout,
                )
```

(Renamed `action_tools` → `all_tools`. When `enable_math_tools=False`, `utility_tool_specs(view)` returns `[]` so `all_tools == action_tools` — Phase 3a/3b behavior preserved.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop_k1.py -v`
Expected: 5 K+1 tests pass.

- [ ] **Step 5: Verify ALL existing 22 ReAct tests still pass (no regression)**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py -v`
Expected: 22 pass (no behavior change for K=0 paths since utility_tool_specs returns [] when enable_math_tools=False, AND test fixtures use enable_math_tools=False).

- [ ] **Step 6: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_llm_agent_react_loop_k1.py && .venv/bin/mypy --strict src/llm_poker_arena/agents/llm/llm_agent.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_llm_agent_react_loop_k1.py
git commit -m "$(cat <<'EOF'
feat(agents): K+1 ReAct utility-tool dispatch branch (Phase 3c-math Task 7)

LLMAgent._decide_inner gains a third response branch (after no_tool and
multi-tool-call): utility-tool dispatch. When tc.name is not in the
action set, dispatch via self._tool_runner; on success populate
IterationRecord.tool_result with the dict and increment utility_count;
on ToolDispatchError emit {"error": ...} and increment
tool_usage_error_count (counter only — no retry-budget consumption per
spec §4.1 BR2-05 reading + plan Q4 decision).

Tool list passed to provider now = action_tools + utility_specs (empty
when enable_math_tools=False, preserving Phase 3a/3b K=0 behavior).
MAX_STEPS scales with max_utility_calls.

Final-step pressure (force action_only_tools on last step) lands in Task 8.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Final-step pressure — switch to action-only tools when budget exhausted

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/llm_agent.py:_decide_inner`
- Test: `tests/unit/test_llm_agent_react_loop_k1.py` (append final-step tests)

**Why a separate task**: Task 7 ships the dispatch branch but always sends both action + utility tool specs. This task adds the spec §4.2 `is_final_step` logic: when `utility_count >= max_utility_calls` OR when this is the last step (`step == MAX_STEPS - 1`), pass `action_tools` only — denying the LLM the option to call more utilities and forcing a commit.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_llm_agent_react_loop_k1.py`:

```python
def test_k1_final_step_excludes_utility_specs() -> None:
    """When utility_count == max_utility_calls, the next provider call must
    receive ONLY action tools (no pot_odds/spr in the spec list).

    This is the spec §4.2 is_final_step pressure: deny the model the option
    to ask another utility, forcing it to commit.
    """
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    params = _params(max_utility_calls=1)
    captured_tools: list[list[dict[str, Any]]] = []

    class CapturingMock(MockLLMProvider):
        async def complete(self, **kw: Any) -> LLMResponse:
            captured_tools.append(list(kw["tools"]))
            return await super().complete(**kw)

    script = MockResponseScript(responses=(
        # Step 1: utility call (uses up the only budget).
        _resp(ToolCall(name="pot_odds", args={}, tool_use_id="tu1")),
        # Step 2: action commit (mock doesn't choose tools, but the spec
        # list at this step should not include pot_odds anymore).
        _resp(ToolCall(name="fold", args={}, tool_use_id="tu2")),
    ))
    provider = CapturingMock(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    asyncio.run(agent.decide(_view(legal, params=params)))
    # Step 1 saw both action + utility tools.
    step1_names = {t["name"] for t in captured_tools[0]}
    assert "pot_odds" in step1_names
    assert "fold" in step1_names
    # Step 2 (after utility budget exhausted): action tools ONLY.
    step2_names = {t["name"] for t in captured_tools[1]}
    assert "pot_odds" not in step2_names
    assert "spr" not in step2_names
    assert "fold" in step2_names


def test_k1_action_only_after_two_utility_calls_exhausts_budget() -> None:
    """Codex audit NIT-1 fix: this test exercises the
    `utility_count >= max_utility_calls` branch of is_final_step (NOT the
    `step == MAX_STEPS - 1` branch — that one's harder to hit deterministically
    because it requires burning all 4 retry budgets while keeping
    utility_count below max_utility_calls).

    With max_utility_calls=2, after 2 utility calls the next step sees
    action-only tools.
    """
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    params = _params(max_utility_calls=2)
    captured_tools: list[list[dict[str, Any]]] = []

    class CapturingMock(MockLLMProvider):
        async def complete(self, **kw: Any) -> LLMResponse:
            captured_tools.append(list(kw["tools"]))
            return await super().complete(**kw)

    # Use up both utility budget calls then commit.
    script = MockResponseScript(responses=(
        _resp(ToolCall(name="pot_odds", args={}, tool_use_id="t1")),
        _resp(ToolCall(name="spr", args={}, tool_use_id="t2")),
        _resp(ToolCall(name="fold", args={}, tool_use_id="t3")),
    ))
    provider = CapturingMock(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    asyncio.run(agent.decide(_view(legal, params=params)))
    # After 2 utility calls (budget exhausted), step 3 has action-only.
    assert "pot_odds" not in {t["name"] for t in captured_tools[2]}


def test_k1_final_step_utility_call_after_exhaustion_short_circuits_to_fallback() -> None:
    """If somehow LLM still emits a utility tool call when only action tools
    were offered (provider ignored the tool list, hallucinated, etc),
    LLMAgent treats it as 'didn't follow protocol' → no_tool_retry budget,
    then fallback if exhausted. Mirrors spec §4.2 lines 994-1015."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    params = _params(max_utility_calls=1)
    script = MockResponseScript(responses=(
        # Step 1: utility (uses budget).
        _resp(ToolCall(name="pot_odds", args={}, tool_use_id="t1")),
        # Step 2: hallucinated utility despite action-only tool list. This
        # should consume no_tool_retry (interpretation: model defied the
        # tool list = didn't follow protocol).
        _resp(ToolCall(name="pot_odds", args={}, tool_use_id="t2")),
        # Step 3: still hallucinated utility → fallback.
        _resp(ToolCall(name="pot_odds", args={}, tool_use_id="t3")),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal, params=params)))
    assert result.default_action_fallback is True
    assert result.no_tool_retry_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop_k1.py::test_k1_final_step_excludes_utility_specs tests/unit/test_llm_agent_react_loop_k1.py::test_k1_final_step_when_step_at_cap tests/unit/test_llm_agent_react_loop_k1.py::test_k1_final_step_utility_call_after_exhaustion_short_circuits_to_fallback -v`
Expected: at least the first 2 fail (Task 7 always passes `all_tools` regardless of step).

- [ ] **Step 3: Add `is_final_step` logic**

Edit `src/llm_poker_arena/agents/llm/llm_agent.py`. Inside `_decide_inner`'s `for step in range(MAX_STEPS)` loop, replace the line that builds the provider call with:

```python
        for step in range(MAX_STEPS):
            digest = _digest_messages(messages)
            iter_start = time.monotonic()
            # spec §4.2 is_final_step: pass action-only tools when utility
            # budget is exhausted OR this is the last allowed step.
            is_final_step = (
                utility_count >= max_utility_calls
                or step == MAX_STEPS - 1
            )
            tools_this_step = action_tools if is_final_step else all_tools
            try:
                response = await asyncio.wait_for(
                    self._provider.complete(
                        system=system_text,
                        messages=messages, tools=tools_this_step,
                        temperature=self._temperature, seed=self._seed,
                    ),
                    timeout=self._per_iter_timeout,
                )
```

Additionally, in the utility-tool dispatch branch from Task 7, when `is_final_step` is True AND the tool_call name is a utility tool (which shouldn't happen because action-only was passed, but the LLM might hallucinate), treat it as a no-action attempt:

Find the utility-dispatch branch start (`if tc.name not in ACTION_TOOL_NAMES:`). Wrap it:

```python
            # Utility-tool dispatch branch.
            if tc.name in utility_names:
                if is_final_step:
                    # LLM defied the action-only tool list. Treat as
                    # no_tool: didn't follow protocol. Spec §4.2 lines 994-1015.
                    iter_record = IterationRecord(
                        step=step + 1,
                        request_messages_digest=digest,
                        provider_response_kind="no_tool",
                        tool_call=tc,
                        text_content=redact_secret(response.text_content),
                        tokens=response.tokens,
                        wall_time_ms=iter_ms,
                        reasoning_artifacts=artifacts,
                    )
                    iterations.append(iter_record)
                    if no_tool_retry < MAX_NO_TOOL_RETRY:
                        no_tool_retry += 1
                        messages.append(
                            self._provider.build_assistant_message_for_replay(response)
                        )
                        messages.extend(self._provider.build_tool_result_messages(
                            tool_calls=(tc,),
                            is_error=True,
                            content=(
                                "You have exhausted your utility-tool budget. "
                                "Call exactly one action tool now."
                            ),
                        ))
                        continue
                    return self._fallback_default_safe(
                        view, iterations, total_tokens, turn_start,
                        api_retry, illegal_retry, no_tool_retry,
                        tool_usage_error_count=tool_usage_error_count,
                    )

                # Normal utility dispatch (Task 7 logic).
                try:
                    tool_result = self._tool_runner(view, tc.name, dict(tc.args or {}))
                except ToolDispatchError as e:
                    tool_result = {"error": str(e)}
                    tool_usage_error_count += 1
                # ... existing dispatch logic from Task 7
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop_k1.py -v`
Expected: 8 K+1 tests pass (5 from Task 7 + 3 from Task 8).

- [ ] **Step 5: Sanity-run full suite**

Run: `.venv/bin/pytest tests/ -q --no-header -x`
Expected: 379 pass + 5 skip.

- [ ] **Step 6: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_llm_agent_react_loop_k1.py && .venv/bin/mypy --strict src/llm_poker_arena/agents/llm/llm_agent.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_llm_agent_react_loop_k1.py
git commit -m "$(cat <<'EOF'
feat(agents): K+1 final-step pressure (action-only tools) (Phase 3c-math Task 8)

spec §4.2 is_final_step: when utility_count >= max_utility_calls OR
this is MAX_STEPS-1, pass action-only tool spec list to provider —
denying utility tools so the model is forced to commit.

If LLM still hallucinates a utility call when offered action-only,
treat as no_tool ('didn't follow protocol'); consume no_tool_retry
budget; fallback to default_safe_action when exhausted (mirrors spec
§4.2 lines 994-1015).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Prompt template — `system.j2` enable_math_tools block

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/prompt_profile.py:render_system` (add kwarg)
- Modify: `src/llm_poker_arena/agents/llm/prompts/system.j2` (add conditional block)
- Modify: `src/llm_poker_arena/agents/llm/llm_agent.py:_build_initial_state` (pass new kwarg)
- Test: `tests/unit/test_llm_agent_react_loop.py` (extend the existing render test)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_llm_agent_react_loop.py`:

```python
def test_system_prompt_includes_math_tools_block_when_enabled() -> None:
    """When SessionConfig.enable_math_tools=True, system.j2 renders a block
    listing pot_odds + spr signatures and when to use them."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    captured_systems: list[str | None] = []

    class Capturing(MockLLMProvider):
        async def complete(self, **kw: Any) -> LLMResponse:
            captured_systems.append(kw.get("system"))
            return await super().complete(**kw)

    script = MockResponseScript(responses=(
        _resp(ToolCall(name="fold", args={}, tool_use_id="t1")),
    ))
    provider = Capturing(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    # _params() default has enable_math_tools=False; override.
    params_with_math = SessionParamsView(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
        max_utility_calls=5, rationale_required=True,
        enable_math_tools=True, enable_hud_tool=False,
        opponent_stats_min_samples=30,
    )
    view_with_math = PlayerView(
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
        turn_seed=42, immutable_session_params=params_with_math,
    )
    asyncio.run(agent.decide(view_with_math))
    sys_text = captured_systems[0]
    assert sys_text is not None
    assert "pot_odds" in sys_text
    assert "spr" in sys_text


def test_system_prompt_omits_math_tools_block_when_disabled() -> None:
    """The default (enable_math_tools=False) must NOT mention pot_odds/spr
    in the system prompt — preserves K=0 baseline behavior."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    captured_systems: list[str | None] = []

    class Capturing(MockLLMProvider):
        async def complete(self, **kw: Any) -> LLMResponse:
            captured_systems.append(kw.get("system"))
            return await super().complete(**kw)

    script = MockResponseScript(responses=(
        _resp(ToolCall(name="fold", args={}, tool_use_id="t1")),
    ))
    provider = Capturing(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    asyncio.run(agent.decide(_view(legal)))  # default _params() has enable_math_tools=False
    sys_text = captured_systems[0]
    assert sys_text is not None
    # The phrase "pot odds" already appears in the rationale guidance ("use
    # pot_odds_required directly"), but the tool-listing block adds
    # "pot_odds(" with parens — that's the marker we're checking.
    assert "pot_odds(" not in sys_text
    assert "spr(" not in sys_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py::test_system_prompt_includes_math_tools_block_when_enabled tests/unit/test_llm_agent_react_loop.py::test_system_prompt_omits_math_tools_block_when_disabled -v`
Expected: first FAIL (template doesn't have the block); second PASS (template doesn't mention pot_odds( yet).

- [ ] **Step 3: Add `enable_math_tools` kwarg to PromptProfile.render_system**

Edit `src/llm_poker_arena/agents/llm/prompt_profile.py`. Modify the `render_system` method signature + body:

```python
    def render_system(
        self, *, num_players: int, sb: int, bb: int, starting_stack: int,
        enable_math_tools: bool = False,
    ) -> str:
        tpl = self._env.get_template(self.system_template)
        return tpl.render(
            num_players=num_players,
            sb=sb, bb=bb, starting_stack=starting_stack,
            rationale_required=self.rationale_required,
            language=self.language,
            enable_math_tools=enable_math_tools,
        )
```

(Default False keeps existing callers working with K=0 behavior.)

- [ ] **Step 4: Pass `enable_math_tools` from `_build_initial_state`**

Edit `src/llm_poker_arena/agents/llm/llm_agent.py:_build_initial_state`. Find the `system_text = self._prompt_profile.render_system(...)` call and add the kwarg:

```python
        system_text = self._prompt_profile.render_system(
            num_players=params.num_players,
            sb=params.sb, bb=params.bb,
            starting_stack=params.starting_stack,
            enable_math_tools=params.enable_math_tools,
        )
```

- [ ] **Step 5: Add the conditional block to `system.j2`**

Edit `src/llm_poker_arena/agents/llm/prompts/system.j2`. Append after the existing `WHEN THINKING, CONSIDER` block, BEFORE the `Respond in {{ language }}` line:

```jinja
{%- if enable_math_tools %}

UTILITY TOOLS AVAILABLE THIS SESSION
- pot_odds(to_call?, pot?) — returns required equity = to_call / (pot + to_call). Zero-arg uses your current to_call and pot. Pass args to ask hypothetically: e.g. `pot_odds(to_call=600, pot=850)` to check what villain would face if you raised to 600 into a 250 pot. Returns {"value": float}.
- spr(stack?, pot?) — returns stack-to-pot ratio (effective_stack / pot by default). Pass args for post-flop planning: e.g. `spr(stack=6000, pot=4000)` to estimate the SPR after a planned raise. Returns {"value": float}.

WHEN TO USE TOOLS
- Use pot_odds when comparing different bet sizes (the current pot_odds_required only covers calling; tools cover hypothetical raise/shove sizing).
- Use spr to plan post-flop commitment when considering a preflop raise that would change your effective_stack vs pot ratio.
- Skip tools entirely when your decision is obvious (premium hand vs strong fold equity, blatant fold vs marginal scenario).
- After at most {{ max_utility_calls | default(5) }} utility tool calls per turn, you must commit an action.
{%- endif %}
```

(Note: `max_utility_calls` is added as a render kwarg in this same step — see Step 6 below.)

- [ ] **Step 6: Pass `max_utility_calls` to render_system as well**

Update `prompt_profile.py:render_system`:

```python
    def render_system(
        self, *, num_players: int, sb: int, bb: int, starting_stack: int,
        enable_math_tools: bool = False,
        max_utility_calls: int = 5,
    ) -> str:
        tpl = self._env.get_template(self.system_template)
        return tpl.render(
            num_players=num_players,
            sb=sb, bb=bb, starting_stack=starting_stack,
            rationale_required=self.rationale_required,
            language=self.language,
            enable_math_tools=enable_math_tools,
            max_utility_calls=max_utility_calls,
        )
```

Update `llm_agent.py:_build_initial_state`:

```python
        system_text = self._prompt_profile.render_system(
            num_players=params.num_players,
            sb=params.sb, bb=params.bb,
            starting_stack=params.starting_stack,
            enable_math_tools=params.enable_math_tools,
            max_utility_calls=params.max_utility_calls,
        )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py -v`
Expected: 22 prior + 2 new = 24 tests pass.

- [ ] **Step 8: Sanity-run full suite**

Run: `.venv/bin/pytest tests/ -q --no-header -x`
Expected: 381 pass + 5 skip.

- [ ] **Step 9: Lint + mypy**

Run: `.venv/bin/ruff check src/llm_poker_arena/agents/llm/ tests/unit/test_llm_agent_react_loop.py && .venv/bin/mypy --strict src/llm_poker_arena/agents/llm/`
Expected: clean.

- [ ] **Step 10: Commit**

```bash
git add src/llm_poker_arena/agents/llm/prompt_profile.py src/llm_poker_arena/agents/llm/prompts/system.j2 src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_llm_agent_react_loop.py
git commit -m "$(cat <<'EOF'
feat(prompt): system.j2 utility-tools block when enable_math_tools (Phase 3c-math Task 9)

Conditional Jinja block describes pot_odds + spr signatures, when to
use vs skip, and the per-turn max_utility_calls bound. Driven by
SessionConfig.enable_math_tools (via SessionParamsView), NOT by a new
PromptProfile field — separation of concerns: PromptProfile handles
prompt-shape (rationale_required, language); SessionConfig handles
tool-system config (enable_math_tools).

Default enable_math_tools=False on render_system kwarg keeps K=0
sessions unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Mock K+1 integration test + populate `total_utility_calls`

**Files:**
- Create: `tests/integration/test_llm_session_mock_k1.py`
- Modify: `src/llm_poker_arena/storage/layer_builders.py:build_agent_view_snapshot` (compute total_utility_calls from iterations — codex audit IMPORTANT-4 fix)

**Why combined**: Spec §7.4 has `total_utility_calls` field which Phase 2a hardcoded to 0. With utility tools actually firing in 3c-math, this field needs to be populated — and the mock K+1 integration test is the natural place to add a regression assertion. Computing from iterations (count entries with non-None tool_result) avoids touching TurnDecisionResult schema.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_llm_session_mock_k1.py`:

```python
"""Integration: 6-hand session with mock LLM agent driving K+1 ReAct loop
including utility tools. Verifies the full pipeline:

  - utility tool calls flow through Session → LLMAgent → ToolRunner
  - IterationRecord with tool_result lands in agent_view_snapshots.jsonl
  - meta.json provider_capabilities still populated correctly
  - chip_pnl conservation holds
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
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session


def _utility_then_fold(uid_prefix: str, n_responses: int) -> tuple[LLMResponse, ...]:
    """Cycle: pot_odds → fold → pot_odds → fold → ... so every other turn
    has at least one utility tool call before commit."""
    out: list[LLMResponse] = []
    for i in range(n_responses):
        if i % 2 == 0:
            tc = ToolCall(name="pot_odds", args={},
                          tool_use_id=f"{uid_prefix}_p{i}")
        else:
            tc = ToolCall(name="fold", args={},
                          tool_use_id=f"{uid_prefix}_f{i}")
        out.append(LLMResponse(
            provider="mock", model="m1", stop_reason="tool_use",
            tool_calls=(tc,), text_content="r",
            tokens=TokenCounts(input_tokens=10, output_tokens=5,
                               cache_read_input_tokens=0,
                               cache_creation_input_tokens=0),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        ))
    return tuple(out)


def test_six_hand_session_with_k1_utility_tool_calls(tmp_path: Path) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,  # crucial — turns on utility tool exposure
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    # Generous response buffer: 6 hands × ~10 turns × cycle of 2 = ~120
    # responses needed for the LLM seat. Use 300 to be safe.
    script = MockResponseScript(responses=_utility_then_fold("a", 300))
    provider = MockLLMProvider(script=script)
    llm_agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    agents = [
        RandomAgent(),  # seat 0 (BTN)
        RandomAgent(),  # SB
        RandomAgent(),  # BB
        llm_agent,      # UTG ← LLM with math tools
        RandomAgent(),  # HJ
        RandomAgent(),  # CO
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="mock_k1_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps
                 if json.loads(line)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots"

    # Across all LLM-seat snapshots, count iterations that called a utility
    # tool. We expect at least one (in fact many — every other LLM turn
    # has the utility-call pattern).
    utility_iters = []
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc is not None and tc["name"] in ("pot_odds", "spr"):
                utility_iters.append(it)
    assert utility_iters, (
        "no utility_tool iterations recorded — K+1 dispatch path "
        "is not wiring through to agent_view_snapshots"
    )
    # Each utility iteration must have a non-None tool_result with "value" key.
    for it in utility_iters:
        assert it["tool_result"] is not None
        assert "value" in it["tool_result"], (
            f"tool_result missing value key: {it['tool_result']}"
        )

    # Codex audit IMPORTANT-4: AgentViewSnapshot.total_utility_calls must
    # reflect actual utility iteration count, not hardcoded 0. For LLM
    # snapshots that contained utility iterations, the field should be
    # >= 1 (spec §7.4).
    snaps_with_utility = [
        rec for rec in llm_snaps
        if any(
            it.get("tool_call") and it["tool_call"]["name"] in ("pot_odds", "spr")
            for it in rec["iterations"]
        )
    ]
    assert snaps_with_utility, "no LLM snapshots had utility iterations"
    for snap in snaps_with_utility:
        expected = sum(
            1 for it in snap["iterations"]
            if it.get("tool_call")
            and it["tool_call"]["name"] in ("pot_odds", "spr")
        )
        assert snap["total_utility_calls"] == expected, (
            f"total_utility_calls={snap['total_utility_calls']} but "
            f"counted {expected} utility iterations in this snapshot"
        )

    # chip_pnl conservation still holds.
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0
```

- [ ] **Step 2: Run test to verify it FAILS on total_utility_calls assertion**

Run: `.venv/bin/pytest tests/integration/test_llm_session_mock_k1.py -v`
Expected: FAIL on `assert snap["total_utility_calls"] >= 1` (or similar — currently hardcoded to 0 in build_agent_view_snapshot).

- [ ] **Step 3: Compute `total_utility_calls` in `build_agent_view_snapshot`**

Edit `src/llm_poker_arena/storage/layer_builders.py`. Find the `build_agent_view_snapshot` function (around line 176). Replace the hardcoded `total_utility_calls=0` line with computation from iterations:

```python
    # Codex audit IMPORTANT-4 fix: Phase 2a hardcoded total_utility_calls=0
    # because no utility tools fired. Phase 3c-math enables math tools, so
    # count utility iterations from the iterations tuple. Spec §7.4 wants
    # this populated. Both successful (tool_result has "value") and failed
    # (tool_result has "error") utility attempts count — matches spec §4.2
    # line 1017 (utility_count increments on attempt, not just success).
    total_utility_calls = sum(
        1 for ir in iterations if ir.tool_result is not None
    )
```

Then in the `AgentViewSnapshot(...)` constructor call, replace `total_utility_calls=0` with `total_utility_calls=total_utility_calls`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/integration/test_llm_session_mock_k1.py -v`
Expected: PASS — total_utility_calls now reflects actual count.

- [ ] **Step 5: Sanity-run full suite**

Run: `.venv/bin/pytest tests/ -q --no-header -x`
Expected: 382 pass + 5 skip.

- [ ] **Step 4: Lint + mypy**

Run: `.venv/bin/ruff check tests/integration/test_llm_session_mock_k1.py && .venv/bin/mypy --strict tests/integration/test_llm_session_mock_k1.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_llm_session_mock_k1.py
git commit -m "$(cat <<'EOF'
test(integration): mock K+1 session with utility tool calls (Phase 3c-math Task 10)

End-to-end verification: 6-hand session with one mock LLM seat that
cycles pot_odds → fold per turn. Asserts:
  - utility_tool iterations land in agent_view_snapshots.jsonl
  - tool_result dict carries "value" key
  - K+1 dispatch wires through Session → LLMAgent → ToolRunner →
    snapshots without dropping fields
  - chip_pnl conservation (no censor / fallback regression)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Gated real-Anthropic K+1 verification

**Files:**
- Create: `tests/integration/test_llm_session_real_anthropic_math.py`

**Activation:**
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_llm_session_real_anthropic_math.py -v
```

Cost: ~$0.025 per run (Claude Haiku 4.5, 6 hands, K+1 with utility tool overhead).

- [ ] **Step 1: Create the gated test**

Create `tests/integration/test_llm_session_real_anthropic_math.py`:

```python
"""Real Anthropic K+1 smoke test (gated, NOT in CI).

Run only when:
  ANTHROPIC_INTEGRATION_TEST=1
  ANTHROPIC_API_KEY=sk-ant-...

Costs ~$0.02-0.04 per run with Claude Haiku 4.5, 6 hands, math tools enabled.

Codex audit IMPORTANT-5 fix: this test does NOT require Claude to organically
call ≥1 utility tool. Anthropic API call shape (no tool_choice="any") makes
utility usage purely a model-behavior choice — Claude may rationally skip
utility tools when pot_odds_required is already in the user prompt.

Assertions are wire-correctness only:
  - Session runs to completion without crash
  - All seat-3 final_actions are in the legal set (or default_safe_action
    fallback fired, which is also legal)
  - meta.json provider_capabilities still populated (Phase 3b regression guard)
  - chip_pnl conserves
  - IF utility iterations appear, their tool_result has the expected shape

Frequency / behavior-driven assertions belong in DuckDB analysis post-session,
not in a gated wire test.
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


def test_real_claude_haiku_session_with_math_tools_completes(tmp_path: Path) -> None:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=True,  # the new flag under test
        enable_hud_tool=False,
        rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    provider = AnthropicProvider(model="claude-haiku-4-5", api_key=api_key)
    llm_agent = LLMAgent(
        provider=provider, model="claude-haiku-4-5",
        temperature=0.7, total_turn_timeout_sec=60.0,
    )
    agents = [
        RandomAgent(),  # BTN
        RandomAgent(),  # SB
        RandomAgent(),  # BB
        llm_agent,      # UTG ← Claude with math tools
        RandomAgent(),  # HJ
        RandomAgent(),  # CO
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="real_anthropic_math_smoke")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    llm_snaps = [json.loads(line) for line in snaps
                 if json.loads(line)["seat"] == 3]
    assert llm_snaps, "no seat-3 snapshots"

    # Wire-correctness assertions (codex audit IMPORTANT-5: no behavior
    # frequency requirement; Claude may rationally skip utility tools).

    # 1. Every final_action must be in the legal set (or default_safe_action,
    #    which is always legal). Same as Phase 3a's assertion shape.
    for rec in llm_snaps:
        final = rec["final_action"]
        legal_names = [t["name"] for t in rec["view_at_turn_start"]["legal_actions"]["tools"]]
        assert final["type"] in legal_names, (
            f"final action {final!r} not in legal set {legal_names}"
        )

    # 2. IF any utility iteration appears, validate its shape.
    #    (Don't REQUIRE one to appear — that's behavior, not wiring.)
    for rec in llm_snaps:
        for it in rec["iterations"]:
            tc = it.get("tool_call")
            if tc is not None and tc["name"] in ("pot_odds", "spr"):
                assert it["tool_result"] is not None, (
                    "utility iteration without tool_result — dispatch broken"
                )
                # tool_result should have "value" (success) or "error" (bad args).
                assert "value" in it["tool_result"] or "error" in it["tool_result"], (
                    f"unexpected tool_result shape: {it['tool_result']}"
                )

    # 3. chip_pnl conservation (no censor / fallback regression on infra).
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert sum(meta["chip_pnl"].values()) == 0

    # 4. Provider capabilities populated (Phase 3b regression guard).
    assert meta["provider_capabilities"]["3"]["provider"] == "anthropic"
```

- [ ] **Step 2: Verify gate-skipped run still works**

Run: `.venv/bin/pytest tests/ -q --no-header -x`
Expected: 382 pass + 6 skip (the new gated joins the existing 5).

- [ ] **Step 3: Live verify against real Anthropic API**

Run:
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_llm_session_real_anthropic_math.py -v --basetemp=/tmp/anthropic_math_smoke
```

Expected: PASS in 60-180s, ~$0.025 cost. Inspect `/tmp/anthropic_math_smoke/.../agent_view_snapshots.jsonl` to see whether Claude organically chose to call utility tools.

Codex audit IMPORTANT-5 fix: this test does NOT require utility calls — it
only verifies wire correctness (no crash, legal final actions, snapshot
shape). If Claude organically chose 0 utility tool calls across 6 hands,
that is acceptable model behavior (pot_odds_required is already in the user
prompt; the tool adds no value at hand-evaluation precision unless LLM is
sizing bets, which Random opponents make rare). Frequency analysis lives in
DuckDB SQL post-session, not in this gated wire test.

If the test fails for OTHER reasons (e.g. final_action not in legal set,
chip_pnl not conserving, provider_capabilities missing): that IS a wiring
bug to investigate.

- [ ] **Step 4: Lint**

Run: `.venv/bin/ruff check tests/integration/test_llm_session_real_anthropic_math.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_llm_session_real_anthropic_math.py
git commit -m "$(cat <<'EOF'
test(integration): gated real-Anthropic K+1 math-tools smoke (Phase 3c-math Task 11)

Mirrors Phase 3a/3b's real-API gated pattern. 6 hands with Claude Haiku
4.5 in seat 3, math tools enabled. Codex audit IMPORTANT-5 fix:
assertions are wire-correctness only (no crash, legal final actions,
snapshot/meta shape), NOT behavior frequency. Claude may organically
call 0 utility tools per turn because pot_odds_required is already in
the user prompt — that is acceptable model behavior, not a bug.

If utility iterations appear, validate their tool_result shape; otherwise
just verify the session completed cleanly.

Cost ~$0.025 / run. Verified manually pre-commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Lint sweep + memory update

**Files:**
- Touch any source file flagged by final ruff/mypy
- Update `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md`

- [ ] **Step 1: Final ruff check on all changed files**

Run: `.venv/bin/ruff check src/ tests/`
Expected: clean. Fix any drift inline.

- [ ] **Step 2: Final mypy strict on all changed files**

Run: `.venv/bin/mypy --strict src/ tests/`
Expected: clean. Fix any drift inline.

- [ ] **Step 3: Final test run with all gates flipped**

Run:
```bash
source <(sed -n '3s/^#//p' ~/.zprofile)
ANTHROPIC_INTEGRATION_TEST=1 DEEPSEEK_INTEGRATION_TEST=1 \
  .venv/bin/pytest tests/ -v 2>&1 | tail -10
```

Expected: 388 pass + 0 skip (382 non-gated + 6 gated: 2 real-Anthropic + 1 new K+1 math + 2 real-DeepSeek + 1 multi-provider).

- [ ] **Step 4: Update memory**

Read `~/.claude/projects/-Users-zcheng256/memory/project_llm_poker_arena.md`. Insert a new "Phase 3c-math COMPLETE" block at the top of the status section (replaces or sits above current "Phase 3b COMPLETE" pointer):

```markdown
**Status as of 2026-04-25 (latest)**: **Phase 3c-math COMPLETE** at HEAD `<sha>`. 376 tests pass with all gates on (370 unit/non-gated + 6 gated: 2 Anthropic + 1 new K+1 math + 2 DeepSeek + 1 multi-provider); 370 + 6 skip in default CI mode. ruff + mypy --strict clean.

**Phase 3c-math commits** (12 commits on top of Phase 3b's `d3fda47`):
- `<sha>` plan baseline
- `<sha>` Task 0: IterationRecord.tool_result field
- `<sha>` Task 1: tools/ subpackage scaffold
- `<sha>` Task 2: pot_odds tool with optional-arg superset
- `<sha>` Task 3: spr tool with optional-arg superset
- `<sha>` Task 4: run_utility_tool dispatcher
- `<sha>` Task 5: utility_tool_specs gated on enable_math_tools
- `<sha>` Task 6: LLMAgent constructor accepts tool_runner
- `<sha>` Task 7: K+1 ReAct utility-tool dispatch branch
- `<sha>` Task 8: K+1 final-step pressure (action-only tools)
- `<sha>` Task 9: system.j2 utility-tools block
- `<sha>` Task 10: mock K+1 integration test
- `<sha>` Task 11: gated real-Anthropic K+1 verification

**Phase 3c-math non-obvious learnings**:
- (Fill in during execution as surfaces emerge — e.g., Anthropic tool spec parsing quirks, prompt-template phrasing that boosts adoption, etc.)

**Phase 3c-math defers**:
- 3c-equity: RangeNotationParser, EquityBackend, hand_equity_vs_ranges, ToolRunner class
- 3c-hud: get_opponent_stats, opponent_stats memory, enable_hud_tool wiring
- 3e (carried from 3b): AgentDescriptor seed/temp; meta retry/token aggregation
```

Update the description field of the memory file to reflect 3c-math completion.

Update `~/.claude/projects/-Users-zcheng256/memory/MEMORY.md` index entry's one-liner if it changed.

- [ ] **Step 5: Final inventory**

Run: `git log --oneline d3fda47..HEAD && git status`
Expected: clean tree, 13 new commits since `d3fda47` (1 plan baseline + 12 task commits). Memory file is outside the repo — no `git add` needed for it.

---

## Self-Review Checklist (auditor-facing summary)

After all 12 tasks land, the following statements must hold:

1. **Spec coverage:**
   - §4.2 K+1 ReAct loop with `is_final_step` action-only pressure ✓ (Tasks 7, 8)
   - §4.3 IterationRecord.tool_result field present ✓ (Task 0)
   - §5.2.3 pot_odds + spr utility tools (with optional-arg superset documented) ✓ (Tasks 2, 3)
   - §5.3 build_tool_specs reads view.immutable_session_params.enable_math_tools ✓ (Task 5; lives as `utility_tool_specs(view)` in tools/runner.py)
   - §5.4 ToolRunner shipped as stateless function (deviation documented) ✓ (Tasks 1, 4)
   - §6 system prompt mentions utility tools when enabled ✓ (Task 9)
   - §7.4 agent_view_snapshots iterations carry tool_result + tool_call ✓ (Task 0 via schema; flows through unchanged)
2. **Brainstorming decisions honored:**
   - 3c split: only pot_odds + spr ship; equity + HUD deferred ✓
   - Optional-arg superset on both tools ✓
   - Mock + gated verification both present ✓
   - No 5th retry budget; tool_usage_error_count is counter not budget ✓
3. **Type consistency:**
   - `run_utility_tool(view, name, args) -> dict[str, Any]` — same sig in runner.py and LLMAgent calls ✓
   - `utility_tool_specs(view) -> list[dict[str, Any]]` — same shape returned and consumed ✓
   - `IterationRecord.tool_result: dict[str, Any] | None = None` — same name everywhere referenced ✓
4. **No placeholders:** every step has executable code or commands. Search this file for "TBD", "TODO", "fill in", "implement later" — should yield zero matches outside the explicit "Phase 3c-equity will add" deferral notes.
5. **Cross-task integration:** Task 7 depends on Task 4 + Task 5 (dispatcher + specs). Task 8 depends on Task 7. Task 9 depends on Task 6 (constructor). Task 10 depends on all of 0-9. Task 11 depends on Task 10's pattern.
6. **Codex audit findings status** (to be filled in after the codex audit round): expected pattern matches Phase 3b — 1 BLOCKER risk on rationale interaction with utility tools (no_text + utility_call vs rationale_required), several IMPORTANTs on edge-case handling.

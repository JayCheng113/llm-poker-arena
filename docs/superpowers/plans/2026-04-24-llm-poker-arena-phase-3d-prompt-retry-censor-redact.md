# Phase 3d: Prompt + Retry + Censor + Redact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four production-quality gaps surfaced by the Phase 3a + real-Anthropic smoke test: (1) Jinja-templated prompts with `my_position_short` + derived-field plumbing (spec §6), (2) `rationale_required` strict mode (§4.5), (3) four genuinely independent retry budgets (§4.1 BR2-05), (4) full §4.1 BR2-01 censor record + secret redaction.

**Architecture:** All changes are in the LLM-agent / session / storage layers. Engine + PlayerView untouched. New `agents/llm/prompts/` subpackage owns Jinja templates + `PromptProfile` loader. `LLMProvider.complete` gains a `system: str | None` parameter so the system prompt rides Anthropic's separate `system=` field (Phase 3a fold-into-user-message wasted ~900 tokens/turn). `LLMAgent.__init__` accepts an optional `prompt_profile`; default loads `default-v2.toml` from package data, cached via `lru_cache`. Session writes a new `censored_hands.jsonl` artifact when an api_error/null-action terminates a hand mid-flight. `redact_secret(text)` lives in `agents/llm/redaction.py` and is applied to `ApiErrorInfo.detail` + `IterationRecord.text_content` at construction time. `_run_one_hand` wraps the per-hand work in try/except so RuntimeError (engine bug) discards staged snapshots and reraises rather than silently leaving half-state.

**Tech Stack:** `jinja2>=3.1` (new dep), existing `pyyaml`-free YAML via `tomllib`-style load... wait, project has no `pyyaml`. Phase 3d does NOT add pyyaml — instead use **TOML** for `prompts/default-v2.toml` (Python 3.11+ has stdlib `tomllib`, zero new deps). Spec §6.3 shows YAML; we deviate to TOML for the same key/value content, which is plan-acknowledged.

**Spec sections covered:** §4.1 BR2-01 (full censor record), §4.1 BR2-05 (4 independent retry budgets), §4.5 (rationale_required strict mode), §6.1 + §6.2 + §6.3 (Jinja templates + PromptProfile), and security improvement §11+ (redact secrets before persistence).

**Codex NIT items addressed:** B5 (BR2-01 censor stub), B6 (tool_usage_error_count shares illegal_retry slot), B9 (raw error strings persisted).

**Out of scope (deferred to 3b/3c/3e):** OpenAI/DeepSeek/LiteLLM providers (3b), capability `probe()` (3b), reasoning artifact extraction (3b), ToolRunner + utility tools (3c), 1000-hand mixed-LLM cost run (3e).

---

## Task 0: Dependencies + scaffolding

**Files:**
- Modify: `pyproject.toml` (add jinja2)
- Create: `src/llm_poker_arena/agents/llm/prompts/__init__.py`
- Create: `src/llm_poker_arena/agents/llm/prompts/default-v2.toml`
- Create: `src/llm_poker_arena/agents/llm/prompts/system.j2`
- Create: `src/llm_poker_arena/agents/llm/prompts/user.j2`

- [ ] **Step 1: Confirm clean working tree at HEAD**

```bash
git status --short
git log --oneline -1
```

Expected: HEAD = `58005c6`. Working tree may have `uv.lock` untracked — leave it.

- [ ] **Step 2: Add jinja2 dep**

Edit `pyproject.toml`'s `[project.dependencies]` block, add `"jinja2>=3.1,<4.0",` so the list reads (alphabetical):

```toml
dependencies = [
    "anthropic>=0.34,<1.0",
    "duckdb>=1.0,<2.0",
    "jinja2>=3.1,<4.0",
    "matplotlib>=3.8,<4.0",
    "pokerkit>=0.7,<0.8",
    "pydantic>=2.0",
]
```

- [ ] **Step 3: Install + smoke-test**

```bash
.venv/bin/pip install -e .
.venv/bin/python -c "import jinja2; print(jinja2.__version__)"
```

Expected: a 3.x version.

- [ ] **Step 4: Create the prompts subpackage skeleton**

```bash
mkdir -p src/llm_poker_arena/agents/llm/prompts
touch src/llm_poker_arena/agents/llm/prompts/__init__.py
```

- [ ] **Step 5: Create `default-v2.toml`**

Per spec §6.3 (translated YAML → TOML, same keys):

```toml
# Phase 3d default prompt profile.
# Spec §6.3 anchors. TOML chosen over YAML to avoid pyyaml dep
# (Python 3.11+ stdlib tomllib).

name = "default-v2"
language = "en"
persona = ""                       # blank = no persona prefix
reasoning_prompt = "light"
rationale_required = true          # spec §4.5 H-14 default
stats_min_samples = 30
card_format = "Ah Kh"
player_label_format = "Player_{seat}"
position_label_format = "{short} ({full})"

# Phase 3d-specific: which Jinja files to load
[templates]
system = "system.j2"
user = "user.j2"
```

- [ ] **Step 6: Create `system.j2` (closely follows spec §6.1)**

```jinja
You are a player in a No-Limit Texas Hold'em 6-max cash game simulation.

SESSION PARAMETERS
- Variant: NLHE, {{ num_players }} players
- Starting stack: {{ starting_stack }} chips ({{ starting_stack // bb }} BB at {{ sb }}/{{ bb }})
- Auto-rebuy: each hand starts with stacks reset to starting_stack
- Rake: none
- Rotation: dealer button moves clockwise

YOUR ROLE
- Fixed seat for entire session.
- See only your hole cards.

YOUR OBJECTIVE
- Maximize chip EV over all hands.
- Decisions final once submitted (action tool_call).

HOW TO ACT
- Receive state + subset of legal action tools each turn.
{%- if rationale_required %}
- First write reasoning in your response content (1-3 short paragraphs).
- Then call exactly one action tool.
- Empty content + tool call only is treated as a no-tool retry.
{%- else %}
- Call exactly one action tool. You may optionally write brief reasoning, but it is not required.
{%- endif %}
- Tools not in the list are not legal this turn.
- Bet/raise amounts must be integers in the range advertised by the tool.

KEY DERIVED FIELDS PROVIDED IN STATE
- to_call: chips you must add to call (= current_bet_to_match - my_invested_this_round, clamped >= 0).
- pot_odds_required: float in [0, 1] — minimum equity to break even on a call alone (= to_call / (pot + to_call)). null when to_call == 0.
- effective_stack: min(my_stack, max opponent stack among non-folded). Use this, not raw stacks, for SPR / commitment math.
- seats_yet_to_act_after_me: actual remaining queue this street, in order; empty if you close the action.
- action_order_this_street: canonical street order including folded seats — for position-relative reasoning.

{%- if rationale_required %}

WHEN THINKING, CONSIDER
- Hand strength (current and future equity)
- Opponents' likely ranges given their actions and stats
- Pot odds (use `pot_odds_required` directly, do not re-derive)
- Your position (use `my_position_short` directly) and stack depth (use `effective_stack`)
{%- endif %}

Respond in {{ language | default("English") }}.
```

- [ ] **Step 7: Create `user.j2`**

```jinja
=== STATE ===
hand_id: {{ hand_id }}
street: {{ street }}
my_seat: {{ my_seat }}
my_position_short: {{ my_position_short }}
my_position_full: {{ my_position_full }}
my_hole_cards: {{ my_hole_cards | join(' ') }}
community: {% if community %}{{ community | join(' ') }}{% else %}(none){% endif %}
pot: {{ pot }}
my_stack: {{ my_stack }}
to_call: {{ to_call }}
pot_odds_required: {{ pot_odds_required }}
effective_stack: {{ effective_stack }}
button_seat: {{ button_seat }}
opponents_in_hand: {{ opponent_seats_in_hand | list }}
seats_yet_to_act_after_me: {{ seats_yet_to_act_after_me | list }}

=== SEATS ===
{%- for s in seats_public %}
seat {{ s.seat }} ({{ s.position_short }}): stack={{ s.stack }} invested_round={{ s.invested_this_round }} status={{ s.status }}{% if s.seat == my_seat %} ← me{% endif %}
{%- endfor %}

=== YOUR TURN ===
The legal action tools are listed below this message. Briefly explain your reasoning, then call exactly one tool.
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/llm_poker_arena/agents/llm/prompts/
git commit -m "chore(deps): add jinja2 + default-v2 prompt scaffolding (Phase 3d)"
```

---

## Task 1: PromptProfile loader + render + LLMProvider.complete system param

**Files:**
- Create: `src/llm_poker_arena/agents/llm/prompt_profile.py`
- Modify: `src/llm_poker_arena/agents/llm/provider_base.py` (add `system` kwarg to complete)
- Modify: `src/llm_poker_arena/agents/llm/providers/mock.py` (accept + ignore system)
- Modify: `src/llm_poker_arena/agents/llm/providers/anthropic_provider.py` (pass system to SDK)
- Test: `tests/unit/test_prompt_profile.py`
- Test: `tests/unit/test_anthropic_provider.py` (assert system param threaded through)

**Why bundle the LLMProvider.complete change here**: Phase 3a's
`_build_initial_messages` folded the entire system prompt into a leading
user message. With Phase 3a's prompt that was ~900 tokens; with Phase 3d's
richer Jinja prompt it could grow to ~1200. Anthropic's API has a separate
`system=` parameter that benefits from prompt caching (saves ~10x on cached
runs) and avoids token re-tokenization each turn. Adding the param now is
1 ABC line + 2 implementation lines + 1 test assertion; deferring to 3b
forces 3d to ship with a known token waste.

- [ ] **Step 1: Write failing tests**

```python
"""Tests for PromptProfile (Phase 3d)."""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_poker_arena.agents.llm.prompt_profile import (
    PromptProfile,
    load_default_prompt_profile,
)


def test_default_profile_loads_and_has_expected_fields() -> None:
    p = load_default_prompt_profile()
    assert p.name == "default-v2"
    assert p.language == "en"
    assert p.rationale_required is True
    assert p.stats_min_samples == 30


def test_render_system_prompt_substitutes_session_params() -> None:
    p = load_default_prompt_profile()
    text = p.render_system(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
    )
    assert "100 BB" in text
    assert "50/100" in text
    assert "First write reasoning" in text  # rationale_required=True branch


def test_render_system_prompt_omits_rationale_when_disabled(
    tmp_path: Path,
) -> None:
    """Custom profile with rationale_required=False uses the else branch."""
    custom_toml = tmp_path / "no_rationale.toml"
    custom_toml.write_text(
        'name = "no-rat"\n'
        'language = "en"\n'
        'persona = ""\n'
        'reasoning_prompt = "light"\n'
        'rationale_required = false\n'
        'stats_min_samples = 30\n'
        'card_format = "Ah Kh"\n'
        'player_label_format = "Player_{seat}"\n'
        'position_label_format = "{short} ({full})"\n'
        '[templates]\n'
        'system = "system.j2"\n'
        'user = "user.j2"\n'
    )
    p = PromptProfile.from_toml(custom_toml)
    text = p.render_system(
        num_players=6, sb=50, bb=100, starting_stack=10_000,
    )
    assert "First write reasoning" not in text
    assert "may optionally write brief reasoning" in text


def test_render_user_prompt_includes_my_position_short() -> None:
    """Phase 3a smoke test showed Claude inferring wrong positions; the
    prompt must now spell out my_position_short directly."""
    p = load_default_prompt_profile()
    text = p.render_user(
        hand_id=0, street="preflop",
        my_seat=3,
        my_position_short="UTG",
        my_position_full="Under the Gun",
        my_hole_cards=("9c", "5h"),
        community=(),
        pot=150, my_stack=10_000, to_call=100,
        pot_odds_required=0.4, effective_stack=10_000,
        button_seat=0,
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        seats_public=(),
    )
    assert "my_position_short: UTG" in text
    assert "my_position_full: Under the Gun" in text
    assert "to_call: 100" in text
    assert "pot_odds_required: 0.4" in text
    assert "effective_stack: 10000" in text
    assert "9c 5h" in text
    assert "(none)" in text  # community empty


def test_render_user_prompt_includes_seats_table() -> None:
    from llm_poker_arena.engine.views import SeatPublicInfo
    seats = tuple(
        SeatPublicInfo(
            seat=i, label=f"P{i}",
            position_short=("BTN", "SB", "BB", "UTG", "HJ", "CO")[i],
            position_full="x",
            stack=10_000 - (50 if i == 1 else 100 if i == 2 else 0),
            invested_this_hand=0,
            invested_this_round=(50 if i == 1 else 100 if i == 2 else 0),
            status="in_hand",
        )
        for i in range(6)
    )
    p = load_default_prompt_profile()
    text = p.render_user(
        hand_id=0, street="preflop", my_seat=3,
        my_position_short="UTG", my_position_full="Under the Gun",
        my_hole_cards=("As", "Kd"), community=(), pot=150,
        my_stack=10_000, to_call=100, pot_odds_required=0.4,
        effective_stack=10_000, button_seat=0,
        opponent_seats_in_hand=(0, 1, 2, 4, 5),
        seats_yet_to_act_after_me=(4, 5, 0, 1, 2),
        seats_public=seats,
    )
    assert "← me" in text  # marker on seat 3
    assert "(BTN)" in text  # seat 0
    assert "stack=9950" in text  # SB after blinds
```

- [ ] **Step 2: Confirm tests fail**

```bash
.venv/bin/pytest tests/unit/test_prompt_profile.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `prompt_profile.py`**

```python
"""PromptProfile: TOML-defined Jinja prompt config for LLMAgent (spec §6.3)."""
from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DEFAULT_TOML = _PROMPTS_DIR / "default-v2.toml"


@dataclass(frozen=True)
class PromptProfile:
    """Spec §6.3 PromptProfile. Holds config + renders system/user prompts."""

    name: str
    language: str
    persona: str
    reasoning_prompt: str
    rationale_required: bool
    stats_min_samples: int
    card_format: str
    player_label_format: str
    position_label_format: str
    system_template: str  # filename relative to prompts/
    user_template: str
    _env: Environment

    @classmethod
    def from_toml(cls, path: Path) -> "PromptProfile":
        with path.open("rb") as f:
            data = tomllib.load(f)
        templates = data.get("templates", {})
        env = Environment(
            loader=FileSystemLoader(str(_PROMPTS_DIR)),
            undefined=StrictUndefined,
            trim_blocks=False,
            lstrip_blocks=False,
        )
        return cls(
            name=str(data["name"]),
            language=str(data["language"]),
            persona=str(data.get("persona", "")),
            reasoning_prompt=str(data["reasoning_prompt"]),
            rationale_required=bool(data["rationale_required"]),
            stats_min_samples=int(data["stats_min_samples"]),
            card_format=str(data["card_format"]),
            player_label_format=str(data["player_label_format"]),
            position_label_format=str(data["position_label_format"]),
            system_template=str(templates.get("system", "system.j2")),
            user_template=str(templates.get("user", "user.j2")),
            _env=env,
        )

    def render_system(
        self, *, num_players: int, sb: int, bb: int, starting_stack: int,
    ) -> str:
        tpl = self._env.get_template(self.system_template)
        return tpl.render(
            num_players=num_players,
            sb=sb, bb=bb, starting_stack=starting_stack,
            rationale_required=self.rationale_required,
            language=self.language,
        )

    def render_user(
        self,
        *,
        hand_id: int, street: str,
        my_seat: int, my_position_short: str, my_position_full: str,
        my_hole_cards: tuple[str, str],
        community: Iterable[str],
        pot: int, my_stack: int, to_call: int,
        pot_odds_required: float | None,
        effective_stack: int,
        button_seat: int,
        opponent_seats_in_hand: Iterable[int],
        seats_yet_to_act_after_me: Iterable[int],
        seats_public: Iterable[Any],
    ) -> str:
        tpl = self._env.get_template(self.user_template)
        return tpl.render(
            hand_id=hand_id, street=street,
            my_seat=my_seat,
            my_position_short=my_position_short,
            my_position_full=my_position_full,
            my_hole_cards=tuple(my_hole_cards),
            community=tuple(community),
            pot=pot, my_stack=my_stack, to_call=to_call,
            pot_odds_required=pot_odds_required,
            effective_stack=effective_stack,
            button_seat=button_seat,
            opponent_seats_in_hand=tuple(opponent_seats_in_hand),
            seats_yet_to_act_after_me=tuple(seats_yet_to_act_after_me),
            seats_public=tuple(seats_public),
        )


@lru_cache(maxsize=1)
def load_default_prompt_profile() -> PromptProfile:
    """Cached so multiple LLMAgent instances share one parse + Jinja env."""
    return PromptProfile.from_toml(_DEFAULT_TOML)


__all__ = ["PromptProfile", "load_default_prompt_profile"]
```

Note: `_env` field on a frozen dataclass — Jinja Environment is mutable but we never mutate it; freezing the dataclass-attribute reassignment is what we care about.

- [ ] **Step 4: Verify tests pass**

```bash
.venv/bin/pytest tests/unit/test_prompt_profile.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Update package data so `default-v2.toml` + `*.j2` ship in wheels**

Open `pyproject.toml`, find `[tool.hatch.build.targets.wheel]` and add:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/llm_poker_arena"]

[tool.hatch.build.targets.wheel.force-include]
"src/llm_poker_arena/agents/llm/prompts" = "llm_poker_arena/agents/llm/prompts"
```

Verify package install picks it up:

```bash
.venv/bin/pip install -e .
.venv/bin/python -c "from llm_poker_arena.agents.llm.prompt_profile import load_default_prompt_profile; print(load_default_prompt_profile().name)"
```

Expected: `default-v2`.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/agents/llm/prompt_profile.py tests/unit/test_prompt_profile.py pyproject.toml
git commit -m "feat(agents): PromptProfile loader + Jinja render (spec §6.3)"
```

---

## Task 2: LLMAgent uses PromptProfile

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/llm_agent.py`
- Modify: `tests/unit/test_llm_agent_react_loop.py` (assertions on rendered prompt)

- [ ] **Step 1: Write failing test asserting Jinja path is exercised**

Add to `tests/unit/test_llm_agent_react_loop.py`:

```python
def test_llm_agent_renders_my_position_short_in_user_prompt() -> None:
    """Regression for Phase 3a smoke finding: Claude was inferring the
    wrong position from raw seat indices. The Jinja-rendered user prompt
    must spell out my_position_short directly."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    captured: list[list[dict[str, object]]] = []

    class Capturing(MockLLMProvider):
        async def complete(self, **kw):  # type: ignore[override, no-untyped-def]
            captured.append(list(kw["messages"]))
            return await super().complete(**kw)

    script = MockResponseScript(responses=(
        _resp(ToolCall(name="fold", args={}, tool_use_id="t1")),
    ))
    provider = Capturing(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.final_action is not None

    # The first message is the user prompt containing the rendered template.
    first = captured[0][0]
    assert first["role"] == "user"
    content = first["content"]
    text = content if isinstance(content, str) else (
        content[0].get("text", "") if isinstance(content, list) and content else ""
    )
    assert "my_position_short:" in text
    # _seats() makes everyone "UTG" so position_short for seat 3 is "UTG"
    assert "UTG" in text
    assert "to_call: 100" in text
    assert "pot_odds_required: 0.4" in text
```

- [ ] **Step 2: Confirm test fails**

Expected: assertion fails because current LLMAgent emits `_user_prompt_for(view)` flat string without my_position_short field.

- [ ] **Step 3: Modify LLMAgent.__init__ to accept PromptProfile**

In `src/llm_poker_arena/agents/llm/llm_agent.py`:

Replace the existing `__init__`:

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
        prompt_profile: "PromptProfile | None" = None,
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
```

- [ ] **Step 4: Replace `_build_initial_messages` to use Jinja**

Replace `_build_initial_messages`:

```python
    def _build_initial_state(
        self, view: PlayerView,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Returns (system_prompt, initial_messages). The system prompt is
        passed via LLMProvider.complete(system=...) so Anthropic prompt
        caching can take effect."""
        params = view.immutable_session_params
        system_text = self._prompt_profile.render_system(
            num_players=params.num_players,
            sb=params.sb, bb=params.bb,
            starting_stack=params.starting_stack,
        )
        my_seat_info = view.seats_public[view.my_seat]
        user_text = self._prompt_profile.render_user(
            hand_id=view.hand_id,
            street=view.street.value,
            my_seat=view.my_seat,
            my_position_short=my_seat_info.position_short,
            my_position_full=my_seat_info.position_full,
            my_hole_cards=view.my_hole_cards,
            community=view.community,
            pot=view.pot,
            my_stack=view.my_stack,
            to_call=view.to_call,
            pot_odds_required=view.pot_odds_required,
            effective_stack=view.effective_stack,
            button_seat=view.button_seat,
            opponent_seats_in_hand=view.opponent_seats_in_hand,
            seats_yet_to_act_after_me=view.seats_yet_to_act_after_me,
            seats_public=view.seats_public,
        )
        return system_text, [{"role": "user", "content": user_text}]
```

- [ ] **Step 4.5: Plumb `system` through `_decide_inner`**

Replace the existing `_build_initial_messages(view)` call site in
`_decide_inner` (single line near top of function) with:

```python
        system_text, messages = self._build_initial_state(view)
```

Then update the inner `await asyncio.wait_for(self._provider.complete(...))`
call to pass `system=system_text` as a kwarg:

```python
                response = await asyncio.wait_for(
                    self._provider.complete(
                        system=system_text,
                        messages=messages, tools=action_tools,
                        temperature=self._temperature, seed=self._seed,
                    ),
                    timeout=self._per_iter_timeout,
                )
```

This requires LLMProvider.complete + MockLLMProvider.complete +
AnthropicProvider.complete to all accept `system: str | None = None` —
those edits are part of this task (per the Files list update at task
header).

In `provider_base.py`:

```python
    @abstractmethod
    async def complete(
        self,
        *,
        system: str | None = None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        """Send a request and return a normalized LLMResponse.

        `system` is the cached system prompt (Anthropic uses messages.create
        `system=...`). Providers without a separate system slot may prepend
        it to the first user message internally.
        """
```

In `mock.py` add `system` to the signature; the mock ignores it (or
captures into a list for tests):

```python
    async def complete(
        self,
        *,
        system: str | None = None,  # captured but unused by mock
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        seed: int | None,
    ) -> LLMResponse:
        # ... existing body unchanged ...
```

In `anthropic_provider.py`:

```python
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
            create_kwargs: dict[str, Any] = dict(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=temperature,
                messages=cast("Any", messages),
                tools=cast("Any", tools) if tools else cast("Any", None),
            )
            if system is not None:
                create_kwargs["system"] = system
            resp = await self._client.messages.create(**create_kwargs)
        # ... rest of error handling unchanged ...
```

Add a regression test in `tests/unit/test_anthropic_provider.py`:

```python
@pytest.mark.asyncio
async def test_anthropic_provider_threads_system_param_to_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """system kwarg must reach the Anthropic SDK as messages.create(system=...).
    Phase 3a folded system into user message which wastes tokens + breaks
    prompt caching."""
    captured: dict[str, Any] = {}

    async def fake_create(**kw):  # type: ignore[no-untyped-def]
        captured.update(kw)
        return _fake_anthropic_response(content_blocks=[])

    fake_client = MagicMock()
    fake_client.messages.create = fake_create
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    await p.complete(
        system="You are a poker bot.",
        messages=[{"role": "user", "content": "play"}],
        tools=[], temperature=0.7, seed=None,
    )
    assert captured["system"] == "You are a poker bot."


@pytest.mark.asyncio
async def test_anthropic_provider_omits_system_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """system=None ⇒ no `system` key passed (cleaner than empty string)."""
    captured: dict[str, Any] = {}

    async def fake_create(**kw):  # type: ignore[no-untyped-def]
        captured.update(kw)
        return _fake_anthropic_response(content_blocks=[])

    fake_client = MagicMock()
    fake_client.messages.create = fake_create
    monkeypatch.setattr(
        "llm_poker_arena.agents.llm.providers.anthropic_provider.AsyncAnthropic",
        lambda **_kw: fake_client,
    )

    p = AnthropicProvider(model="claude-haiku-4-5", api_key="fake")
    await p.complete(
        system=None,
        messages=[{"role": "user", "content": "play"}],
        tools=[], temperature=0.7, seed=None,
    )
    assert "system" not in captured
```

- [ ] **Step 5: Drop the dead `_user_prompt_for` + `_SYSTEM_PROMPT` from llm_agent.py**

The old hardcoded prompt string and helper are replaced by Jinja. Remove them entirely (no compat shim).

- [ ] **Step 6: Run full LLMAgent test set**

```bash
.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py tests/unit/test_prompt_profile.py -v
```

Expected: all green, including the new prompt-rendering regression.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_llm_agent_react_loop.py
git commit -m "feat(agents): LLMAgent renders prompts via PromptProfile (spec §6.1, §6.2)"
```

---

## Task 3: rationale_required strict mode

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/llm_agent.py`
- Modify: `tests/unit/test_llm_agent_react_loop.py`

**Spec §4.5**: `rationale_required=True` ⇒ "first write reasoning in your response content". Phase 3a's prompt mentioned reasoning but the loop didn't enforce. Phase 3d **enforces**: when rationale_required=True, an assistant response with a tool_use block but **no preceding text block** counts as a no_tool_retry-equivalent (consume MAX_NO_TOOL_RETRY budget + retry once asking for reasoning).

- [ ] **Step 1: Write failing tests**

```python
def test_rationale_required_strict_mode_retries_on_empty_text() -> None:
    """When rationale_required=True (default), an LLM response with tool_use
    but no text content triggers a 'rationale missing' retry (consumes the
    no_tool_retry slot — text-only emit is the same family of error)."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    no_text_response = LLMResponse(
        provider="mock", model="m1", stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t1"),),
        text_content="",  # empty — violates rationale_required
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )
    recovery = LLMResponse(
        provider="mock", model="m1", stop_reason="tool_use",
        tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t2"),),
        text_content="I am folding because 9-5o is weak.",
        tokens=TokenCounts(input_tokens=10, output_tokens=10,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )
    script = MockResponseScript(responses=(no_text_response, recovery))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.no_tool_retry_count == 1
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"


def test_rationale_required_false_accepts_empty_text() -> None:
    """When the profile has rationale_required=False, an empty-text response
    with a legal tool call is accepted directly (no retry)."""
    from llm_poker_arena.agents.llm.prompt_profile import PromptProfile
    from pathlib import Path
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
        f.write(
            'name = "no-rat"\nlanguage = "en"\npersona = ""\n'
            'reasoning_prompt = "light"\nrationale_required = false\n'
            'stats_min_samples = 30\ncard_format = "Ah Kh"\n'
            'player_label_format = "Player_{seat}"\n'
            'position_label_format = "{short} ({full})"\n'
            '[templates]\nsystem = "system.j2"\nuser = "user.j2"\n'
        )
        toml_path = Path(f.name)
    profile = PromptProfile.from_toml(toml_path)
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    script = MockResponseScript(responses=(
        LLMResponse(
            provider="mock", model="m1", stop_reason="tool_use",
            tool_calls=(ToolCall(name="fold", args={}, tool_use_id="t1"),),
            text_content="",  # empty — fine when rationale_required=False
            tokens=TokenCounts(input_tokens=10, output_tokens=5,
                               cache_read_input_tokens=0,
                               cache_creation_input_tokens=0),
            raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
        ),
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7,
                     prompt_profile=profile)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.no_tool_retry_count == 0  # no retry consumed
    assert result.final_action is not None
```

- [ ] **Step 2: Confirm tests fail**

Expected: first test fails because current loop doesn't check text_content; second test passes (or fails differently if profile import paths are wrong).

- [ ] **Step 3: Add rationale check in the LLMAgent ReAct loop**

In `_decide_inner`, find the block that processes a single tool_call response (after multi-tool-call branch, before `tc = response.tool_calls[0]`). Add the rationale check:

```python
            # Phase 3d: rationale_required strict mode (spec §4.5).
            # When the profile demands reasoning, an empty text_content with
            # a tool_use block is treated as "no rationale" — same family of
            # error as no_tool, consume the no_tool_retry budget.
            if (self._prompt_profile.rationale_required
                    and not response.text_content.strip()):
                # Record + retry/fallback.
                tc = response.tool_calls[0]
                iter_record = IterationRecord(
                    step=step + 1,
                    request_messages_digest=digest,
                    provider_response_kind="no_tool",  # reusing kind for now
                    tool_call=tc,
                    text_content="",
                    tokens=response.tokens,
                    wall_time_ms=iter_ms,
                )
                iterations.append(iter_record)
                if no_tool_retry < MAX_NO_TOOL_RETRY:
                    no_tool_retry += 1
                    messages.append(_assistant_message(response))
                    messages.append(_tool_result_user(
                        tool_use_id=tc.tool_use_id,
                        is_error=True,
                        content=(
                            "Reasoning required: write 1-3 short paragraphs "
                            "of reasoning before calling the tool. Try again."
                        ),
                    ))
                    continue
                return self._fallback_default_safe(
                    view, iterations, total_tokens, turn_start,
                    api_retry, illegal_retry, no_tool_retry,
                    tool_usage_error_count=tool_usage_error_count,
                )
```

This block goes immediately before the final-tc-validation block. Make sure it falls through correctly when text is non-empty.

- [ ] **Step 4: Verify tests pass**

```bash
.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py -v
```

Expected: all green, including the 2 new rationale tests.

- [ ] **Step 5: Commit**

```bash
git add src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_llm_agent_react_loop.py
git commit -m "feat(agents): rationale_required strict mode — empty text → no_tool retry (spec §4.5)"
```

---

## Task 4: Four genuinely independent retry budgets (codex B6)

**Files:**
- Modify: `src/llm_poker_arena/agents/llm/llm_agent.py`
- Modify: `tests/unit/test_llm_agent_react_loop.py`

**Codex B6**: spec §4.1 BR2-05 demands four independent budgets. Phase 3a folded `tool_usage_error_count` into the `illegal_retry` slot. Phase 3d splits it: introduce `MAX_TOOL_USAGE_RETRY = 1` and `tool_usage_retry` counter; multi-tool-call retry consumes the new slot, not illegal_retry.

- [ ] **Step 1: Write failing test**

```python
def test_tool_usage_error_does_not_consume_illegal_retry_budget() -> None:
    """spec §4.1 BR2-05: tool_usage_error_count and illegal_retry have
    independent budgets. After a multi-tool-call (consumes tool_usage slot),
    a subsequent illegal-action attempt must STILL have its own retry slot."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),
                                   ActionToolSpec(name="call", args={})))
    multi_tool_response = LLMResponse(
        provider="mock", model="m1", stop_reason="tool_use",
        tool_calls=(
            ToolCall(name="fold", args={}, tool_use_id="t1a"),
            ToolCall(name="call", args={}, tool_use_id="t1b"),
        ),
        text_content="reasoning here",
        tokens=TokenCounts(input_tokens=10, output_tokens=5,
                           cache_read_input_tokens=0,
                           cache_creation_input_tokens=0),
        raw_assistant_turn=AssistantTurn(provider="mock", blocks=()),
    )
    illegal_response = _resp(
        ToolCall(name="raise_to", args={"amount": 500},  # not in legal set
                 tool_use_id="t2"),
        text="reasoning",
    )
    legal_recovery = _resp(
        ToolCall(name="fold", args={}, tool_use_id="t3"),
        text="reasoning",
    )
    script = MockResponseScript(responses=(
        multi_tool_response, illegal_response, legal_recovery,
    ))
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.tool_usage_error_count == 1
    assert result.illegal_action_retry_count == 1
    assert result.final_action is not None
    assert result.final_action.tool_name == "fold"
    assert result.default_action_fallback is False
```

- [ ] **Step 2: Confirm test fails**

Expected: with current code, multi-tool consumes illegal_retry, so the subsequent illegal-action exhausts and the final action falls back to default_safe. Test should fail the `default_action_fallback is False` assertion.

- [ ] **Step 3: Add `MAX_TOOL_USAGE_RETRY` and `tool_usage_retry` to the loop**

In `_decide_inner`:

```python
        MAX_API_RETRY = 1
        MAX_ILLEGAL_RETRY = 1
        MAX_NO_TOOL_RETRY = 1
        MAX_TOOL_USAGE_RETRY = 1  # spec §4.1 BR2-05: independent budget
        MAX_STEPS = 5  # bumped to accommodate 4 independent retries

        api_retry = 0
        illegal_retry = 0
        no_tool_retry = 0
        tool_usage_retry = 0  # phase 3d: separate from tool_usage_error_count
        tool_usage_error_count = 0
```

In the multi-tool-call branch, replace `illegal_retry` budget check with the new dedicated counter:

```python
            # Multi-tool-call response is misuse: count + retry on tool_usage_retry slot.
            if len(response.tool_calls) > 1:
                tool_usage_error_count += 1
                first_tc = response.tool_calls[0]
                # ... iter_record build ...
                if tool_usage_retry < MAX_TOOL_USAGE_RETRY:
                    tool_usage_retry += 1
                    messages.append(_assistant_message(response))
                    err_content = (
                        f"Multiple tool calls in one response are not "
                        f"allowed. Got {len(response.tool_calls)} calls; "
                        f"call exactly one action tool."
                    )
                    messages.append(_multi_tool_result_user(
                        tool_calls=response.tool_calls,
                        is_error=True,
                        content=err_content,
                    ))
                    continue
                return self._fallback_default_safe(
                    view, iterations, total_tokens, turn_start,
                    api_retry, illegal_retry, no_tool_retry,
                    tool_usage_error_count=tool_usage_error_count,
                )
```

- [ ] **Step 4: Run + verify pass**

```bash
.venv/bin/pytest tests/unit/test_llm_agent_react_loop.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_llm_agent_react_loop.py
git commit -m "fix(agents): split tool_usage_retry from illegal_retry budget (spec §4.1 BR2-05)"
```

---

## Task 5: BR2-01 full censor record (codex B5)

**Files:**
- Modify: `src/llm_poker_arena/storage/schemas.py` (add CensoredHandRecord)
- Modify: `src/llm_poker_arena/session/session.py` (write to writer; drop buffered turn snapshots)
- Modify: `src/llm_poker_arena/storage/layer_builders.py` (add `build_censored_hand_record`)
- Test: `tests/unit/test_session_censor.py`

**Phase 3a stub**: `_record_censored_hand` printed to stdout. Already-buffered turn snapshots remained in `_snapshot_writer.buffer` and would flush on close.

**Phase 3d full impl**:
1. New `runs/<session>/censored_hands.jsonl` artifact, one line per censored hand.
2. Per spec §4.1 BR2-01 "censor 整手": when censor fires, **discard** the buffered turn snapshots AND the buffered public events for that hand_id. Don't flush partials.

- [ ] **Step 1: Write failing test**

```python
"""Tests for full BR2-01 censor record (Phase 3d Task 5)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import (
    ApiErrorInfo,
    TokenCounts,
    TurnDecisionResult,
)
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.engine.views import PlayerView
from llm_poker_arena.session.session import Session


class _CensoringAgent(Agent):
    """Agent whose first decision returns api_error → forces censor."""

    def __init__(self) -> None:
        self._calls = 0

    async def decide(self, view: PlayerView) -> TurnDecisionResult:
        self._calls += 1
        if self._calls == 1:
            return TurnDecisionResult(
                iterations=(),
                final_action=None,
                total_tokens=TokenCounts.zero(),
                wall_time_ms=10,
                api_retry_count=1,
                illegal_action_retry_count=0,
                no_tool_retry_count=0,
                tool_usage_error_count=0,
                default_action_fallback=False,
                api_error=ApiErrorInfo(
                    type="ProviderTransientError", detail="503 timeout",
                ),
                turn_timeout_exceeded=False,
            )
        # Subsequent hands: legal fold-only fallback.
        from llm_poker_arena.engine.legal_actions import default_safe_action
        return TurnDecisionResult(
            iterations=(),
            final_action=default_safe_action(view),
            total_tokens=TokenCounts.zero(),
            wall_time_ms=0,
            api_retry_count=0, illegal_action_retry_count=0,
            no_tool_retry_count=0, tool_usage_error_count=0,
            default_action_fallback=True,
            api_error=None, turn_timeout_exceeded=False,
        )

    def provider_id(self) -> str:
        return "censor:test"


def test_censored_hand_writes_to_censored_hands_jsonl(tmp_path: Path) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    # Seat 3 censors on hand 0; everyone else is RandomAgent.
    agents = [
        RandomAgent(), RandomAgent(), RandomAgent(),
        _CensoringAgent(),
        RandomAgent(), RandomAgent(),
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="censor_test")
    asyncio.run(sess.run())

    censor_path = tmp_path / "censored_hands.jsonl"
    assert censor_path.exists(), "censored_hands.jsonl must be written"
    lines = censor_path.read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["hand_id"] == 0
    assert rec["seat"] == 3
    assert rec["api_error"]["type"] == "ProviderTransientError"
    assert "503" in rec["api_error"]["detail"]


def test_censored_hand_does_not_emit_partial_canonical_record(
    tmp_path: Path,
) -> None:
    """BR2-01 'censor 整手': hand 0 must NOT appear in canonical_private."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    agents = [
        RandomAgent(), RandomAgent(), RandomAgent(),
        _CensoringAgent(),
        RandomAgent(), RandomAgent(),
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="censor_test_2")
    asyncio.run(sess.run())

    private = (tmp_path / "canonical_private.jsonl").read_text().strip().splitlines()
    private_hand_ids = {json.loads(line)["hand_id"] for line in private}
    assert 0 not in private_hand_ids, (
        f"hand 0 was censored but appears in canonical_private: {private_hand_ids}"
    )
    # Hands 1-5 should still be there (the agent's _calls > 1 path returns
    # safe fallback, so subsequent hands complete normally).
    assert {1, 2, 3, 4, 5}.issubset(private_hand_ids)


def test_censored_hand_does_not_emit_partial_public_record(
    tmp_path: Path,
) -> None:
    """Same for public_replay."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    agents = [
        RandomAgent(), RandomAgent(), RandomAgent(),
        _CensoringAgent(),
        RandomAgent(), RandomAgent(),
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="censor_test_3")
    asyncio.run(sess.run())

    public = (tmp_path / "public_replay.jsonl").read_text().strip().splitlines()
    public_hand_ids = {json.loads(line)["hand_id"] for line in public}
    assert 0 not in public_hand_ids


def test_censored_hand_drops_partial_turn_snapshots(tmp_path: Path) -> None:
    """The first agent of hand 0 was the censor (seat 3, UTG since
    button=0). Before seat 3 acted, seats 0-2 don't act preflop (button=0
    means UTG=3 acts first), so no snapshots from earlier seats exist in
    hand 0. But this test ensures NO snapshots from hand 0 leak — even
    seat 3's own forced view (which we projected before censor)."""
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=6, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=42,
    )
    agents = [
        RandomAgent(), RandomAgent(), RandomAgent(),
        _CensoringAgent(),
        RandomAgent(), RandomAgent(),
    ]
    sess = Session(config=cfg, agents=agents, output_dir=tmp_path,
                   session_id="censor_test_4")
    asyncio.run(sess.run())

    snaps = (tmp_path / "agent_view_snapshots.jsonl").read_text().strip().splitlines()
    snap_hand_ids = {json.loads(line)["hand_id"] for line in snaps}
    assert 0 not in snap_hand_ids
```

- [ ] **Step 2: Confirm tests fail**

Expected: `censored_hands.jsonl` doesn't exist; partial records leak.

- [ ] **Step 3: Add `CensoredHandRecord` to `storage/schemas.py`**

Append after the existing AgentViewSnapshot block:

```python
# ----------------------------------------------------------- censored_hands

class CensoredHandRecord(BaseModel):
    """spec §4.1 BR2-01: one line per hand abandoned due to api_error or
    null final_action. Hand records (canonical_private + public_replay) are
    NOT written for censored hands; this is the analyst's only signal."""

    model_config = _frozen()

    hand_id: int
    seat: int  # the seat whose decide() returned api_error
    api_error: dict[str, str]  # {"type": ..., "detail": ...}
    timestamp: str
    session_id: str
```

- [ ] **Step 4: Add builder in `storage/layer_builders.py`**

```python
def build_censored_hand_record(
    *, hand_id: int, seat: int, session_id: str,
    api_error: object,  # ApiErrorInfo or None
    timestamp: str,
) -> "CensoredHandRecord":
    """Build the censored_hands.jsonl record for a hand abandoned per
    spec §4.1 BR2-01."""
    if api_error is None:
        err_dict = {"type": "NullFinalAction", "detail": "agent returned final_action=None without api_error (should not happen post-3d validator, defensive)"}
    elif hasattr(api_error, "model_dump"):
        err_dict = {
            "type": str(getattr(api_error, "type", "Unknown")),
            "detail": str(getattr(api_error, "detail", "")),
        }
    else:
        err_dict = {"type": "Unknown", "detail": str(api_error)}
    return CensoredHandRecord(
        hand_id=hand_id, seat=seat, session_id=session_id,
        api_error=err_dict, timestamp=timestamp,
    )
```

Add `CensoredHandRecord` to the import from `storage.schemas` at the top of layer_builders.py.

- [ ] **Step 5: Modify Session to flush-on-success / discard-on-censor**

In `src/llm_poker_arena/session/session.py`:

Open the `_run_one_hand` body. The key insight: `BatchedJsonlWriter.write()` adds to a buffer; `flush()` actually writes to disk. If we keep all writes for a hand in a per-hand staging buffer and only commit them at hand-end, censor can drop them.

Add to `__init__`:

```python
        self._censor_writer = BatchedJsonlWriter(self._output_dir / "censored_hands.jsonl")
```

Update `run()` finally block to also close `_censor_writer`:

```python
            for w in (self._private_writer, self._public_writer,
                      self._snapshot_writer, self._censor_writer):
                w.close()
```

In `_run_one_hand`, change the snapshot-writing path to stage instead of write directly. Also wrap the whole body in try/except so RuntimeError (engine bug) discards staged data instead of leaving it in limbo:

```python
    async def _run_one_hand(self, hand_id: int) -> None:
        # Phase 3d: stage per-hand artifacts so censor can discard them
        # atomically AND so a mid-hand RuntimeError doesn't leave half-state.
        staged_snapshots: list[dict[str, Any]] = []
        try:
            # ... existing body, replacing self._snapshot_writer.write(...) with:
            staged_snapshots.append(snapshot.model_dump(mode="json"))
            # ... eventually, on hand-success path, commit staged data:
            for snap in staged_snapshots:
                self._snapshot_writer.write(snap)
            # ... build_canonical_private_hand + build_public_hand_record + writes
        except RuntimeError as e:
            # Engine-level bug (e.g. _maybe_advance_between_streets cap
            # exhaustion). Don't write half-state; surface the error.
            print(
                f"[SESSION] hand {hand_id} aborted with RuntimeError "
                f"({e!r}); discarding {len(staged_snapshots)} staged snapshots.",
                flush=True,
            )
            raise
```

The censor branch (api_error / null final_action) is INSIDE the try block
and uses `return`, which bypasses the staged-commit path — staged data
naturally drops. Only the RuntimeError path needed explicit handling.

Replace the censor branch:

```python
            decision = await self._agents[actor].decide(view)
            if decision.api_error is not None or decision.final_action is None:
                # spec §4.1 BR2-01: censor full hand. Discard staged
                # per-hand artifacts; emit one censor record.
                from llm_poker_arena.storage.layer_builders import (
                    build_censored_hand_record,
                )
                censor_rec = build_censored_hand_record(
                    hand_id=hand_id, seat=actor,
                    session_id=self._session_id,
                    api_error=decision.api_error,
                    timestamp=_now_iso(),
                )
                self._censor_writer.write(censor_rec.model_dump(mode="json"))
                # Drop staged snapshots; do not write any canonical_private or
                # public_replay record for this hand.
                return
```

After the `while ... actor_index ...` loop completes (hand finished cleanly), commit the staged snapshots:

```python
        for snap in staged_snapshots:
            self._snapshot_writer.write(snap)
        # ... then build_canonical_private_hand + build_public_hand_record + writes
```

The existing public_replay flush already happens after the loop, so it's already deferred. Only the snapshot writes need staging.

Drop the existing `_record_censored_hand` print stub.

- [ ] **Step 6: Verify tests pass**

```bash
.venv/bin/pytest tests/unit/test_session_censor.py tests/unit/test_session_orchestrator.py tests/unit/test_session_async.py -v
```

Expected: all green. The non-censor session tests should still pass because the staged-snapshots commit happens unconditionally on the success path.

- [ ] **Step 7: Commit**

```bash
git add src/llm_poker_arena/storage/schemas.py src/llm_poker_arena/storage/layer_builders.py src/llm_poker_arena/session/session.py tests/unit/test_session_censor.py
git commit -m "feat(session): full BR2-01 censor record + drop partial hand artifacts (spec §4.1)"
```

---

## Task 6: Secret redaction (codex B9)

**Files:**
- Create: `src/llm_poker_arena/agents/llm/redaction.py`
- Modify: `src/llm_poker_arena/agents/llm/llm_agent.py` (apply redaction to ApiErrorInfo.detail + IterationRecord.text_content)
- Test: `tests/unit/test_redaction.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests for redact_secret (Phase 3d Task 6)."""
from __future__ import annotations

from llm_poker_arena.agents.llm.redaction import redact_secret


def test_redacts_anthropic_api_key() -> None:
    text = "Auth failed for sk-ant-api03-abc123def456_xy-z bla bla"
    redacted = redact_secret(text)
    assert "sk-ant-api03-abc123def456_xy-z" not in redacted
    assert "<REDACTED_API_KEY>" in redacted


def test_redacts_openai_api_key() -> None:
    text = "x sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx y"
    redacted = redact_secret(text)
    assert "sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" not in redacted
    assert "<REDACTED_API_KEY>" in redacted


def test_redacts_deepseek_api_key() -> None:
    text = "Bearer sk-49009f5abcdef0123456789abcdef0123 done"
    redacted = redact_secret(text)
    assert "sk-49009f5abcdef0123456789abcdef0123" not in redacted
    assert "<REDACTED_API_KEY>" in redacted


def test_does_not_touch_legitimate_text() -> None:
    text = "I will fold because 9-5o is weak."
    redacted = redact_secret(text)
    assert redacted == text


def test_redact_handles_none_safely() -> None:
    """Defensive: callers may pass None; should return empty string."""
    assert redact_secret(None) == ""


def test_redact_handles_multiple_secrets_in_one_string() -> None:
    text = "key1 sk-ant-api03-aaa111 and key2 sk-proj-bbb222ccc333"
    redacted = redact_secret(text)
    assert "<REDACTED_API_KEY>" in redacted
    # Both secrets must be gone
    assert "sk-ant-api03-aaa111" not in redacted
    assert "sk-proj-bbb222ccc333" not in redacted
```

- [ ] **Step 2: Confirm tests fail**

Expected: ImportError.

- [ ] **Step 3: Implement `redaction.py`**

```python
"""Redact API keys + secrets from strings before persistence (codex B9 fix).

Pattern matches common API key prefixes from major providers:
  - Anthropic: sk-ant-...
  - OpenAI: sk-proj-..., sk-..., session keys
  - DeepSeek + OpenAI-compatible: sk-...
  - Generic Bearer tokens (long base64-ish strings)

Conservative: false positives are fine (over-redact); false negatives leak
keys. The intended consumer is `ApiErrorInfo.detail` and
`IterationRecord.text_content`, both of which contain provider exception
messages or model output — neither expected to contain literal API keys
in normal operation.
"""
from __future__ import annotations

import re

# Match `sk-` followed by 32+ chars of [A-Za-z0-9_-]; covers Anthropic
# (sk-ant-api03-...), OpenAI (sk-proj-..., sk-...), DeepSeek (sk-...).
_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{12,}")

# Generic long-string secret heuristic: 40+ char base64-ish runs after
# 'Bearer '/'Token ' or 'Authorization:'.
_BEARER_PATTERN = re.compile(
    r"(?i)(bearer|token|authorization:?)\s+[A-Za-z0-9+/=_-]{40,}"
)


def redact_secret(text: str | None) -> str:
    """Return `text` with API keys + Bearer tokens replaced by a sentinel."""
    if text is None:
        return ""
    out = _SK_PATTERN.sub("<REDACTED_API_KEY>", text)
    out = _BEARER_PATTERN.sub(
        lambda m: f"{m.group(1)} <REDACTED_API_KEY>", out
    )
    return out


__all__ = ["redact_secret"]
```

- [ ] **Step 4: Apply redaction in LLMAgent**

In `llm_agent.py`, find where `ApiErrorInfo(type=..., detail=str(e))` is constructed (the two `_fail_with_api_error` calls). Wrap `str(e)` with `redact_secret`. Add the import:

```python
from llm_poker_arena.agents.llm.redaction import redact_secret
```

Find every `IterationRecord` construction with `text_content=str(e)` or `text_content=response.text_content` and wrap the value with `redact_secret(...)`:

```python
            iter_record = IterationRecord(
                step=step + 1,
                request_messages_digest=digest,
                provider_response_kind="error",
                tool_call=None,
                text_content=redact_secret(str(e)),
                tokens=TokenCounts.zero(),
                wall_time_ms=int((time.monotonic() - iter_start) * 1000),
            )
```

Same for the success-path `text_content=response.text_content` — wrap with `redact_secret(response.text_content)`. (Defensive: model output shouldn't contain keys, but cheap to redact.)

In `_fail_with_api_error`:

```python
            api_error=ApiErrorInfo(type=err_type, detail=redact_secret(detail)),
```

- [ ] **Step 5: Verify tests pass + write integration assertion**

Add to `test_llm_agent_react_loop.py`:

```python
def test_api_error_detail_is_redacted_when_provider_msg_contains_key() -> None:
    """Codex B9: provider exceptions may carry API key fragments. The
    persisted ApiErrorInfo.detail MUST be redacted before reaching the
    AgentViewSnapshot."""
    legal = LegalActionSet(tools=(ActionToolSpec(name="fold", args={}),))
    fake_key = "sk-ant-api03-fake-leaked-key-aaaaaa"
    err = ProviderPermanentError(f"401 unauthorized: bad key {fake_key}")
    script = MockResponseScript(
        responses=(),
        errors_at_step={0: err},
    )
    provider = MockLLMProvider(script=script)
    agent = LLMAgent(provider=provider, model="m1", temperature=0.7)
    result = asyncio.run(agent.decide(_view(legal)))
    assert result.api_error is not None
    assert fake_key not in result.api_error.detail
    assert "<REDACTED_API_KEY>" in result.api_error.detail
```

```bash
.venv/bin/pytest tests/unit/test_redaction.py tests/unit/test_llm_agent_react_loop.py -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/llm_poker_arena/agents/llm/redaction.py src/llm_poker_arena/agents/llm/llm_agent.py tests/unit/test_redaction.py tests/unit/test_llm_agent_react_loop.py
git commit -m "fix(security): redact API keys from ApiErrorInfo + iteration text (codex B9)"
```

---

## Task 7: Real-Anthropic re-smoke + verification

**Files:**
- (no source changes; just run + record observations)

- [ ] **Step 1: Lint + mypy**

```bash
.venv/bin/ruff check src/ tests/
.venv/bin/mypy --strict src/ tests/
```

Expected: both clean.

- [ ] **Step 2: Full suite**

```bash
.venv/bin/pytest tests/ --tb=short -q
```

Expected: all green.

- [ ] **Step 3: Re-run gated real-Anthropic smoke**

```bash
source <(sed -n '3s/^#//p' ~/.zprofile) && \
ANTHROPIC_INTEGRATION_TEST=1 .venv/bin/pytest tests/integration/test_llm_session_real_anthropic.py -v
```

Expected: PASSED in ~20-30s.

- [ ] **Step 4: Re-run the manual narration session and inspect**

```bash
source <(sed -n '3s/^#//p' ~/.zprofile) && \
.venv/bin/python -c "
import asyncio, json, os
from pathlib import Path
import shutil

import sys
sys.path.insert(0, '/Users/zcheng256/llm-poker-arena/src')

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.providers.anthropic_provider import AnthropicProvider
from llm_poker_arena.agents.random_agent import RandomAgent
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

cfg = SessionConfig(
    num_players=6, starting_stack=10_000, sb=50, bb=100,
    num_hands=6, max_utility_calls=5,
    enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
    opponent_stats_min_samples=30, rng_seed=42,
)
provider = AnthropicProvider(model='claude-haiku-4-5', api_key=os.environ['ANTHROPIC_API_KEY'])
llm_agent = LLMAgent(provider=provider, model='claude-haiku-4-5', temperature=0.7)
agents = [RandomAgent()] * 3 + [llm_agent] + [RandomAgent()] * 2

out = Path('/tmp/anthropic_smoke_3d')
if out.exists(): shutil.rmtree(out)
out.mkdir()
sess = Session(config=cfg, agents=agents, output_dir=out, session_id='anthropic_demo_3d')
asyncio.run(sess.run())
print('done')
"
echo "---"
echo "=== Claude (seat 3) per-turn — verify Phase 3d prompt improvements ==="
python3 -c "
import json
from pathlib import Path
snaps = Path('/tmp/anthropic_smoke_3d/agent_view_snapshots.jsonl').read_text().strip().splitlines()
for line in snaps:
    rec = json.loads(line)
    if rec['seat'] != 3: continue
    view = rec['view_at_turn_start']
    iters = rec['iterations']
    final = rec['final_action']
    pos = view['seats_public'][3]['position_short']
    print(f'hand {rec[\"hand_id\"]} ({view[\"street\"]}, my_position={pos}): '
          f'hole={\" \".join(view[\"my_hole_cards\"])} '
          f'pot={view[\"pot\"]} to_call={view[\"to_call\"]} → {final[\"type\"]}')
    text = iters[0]['text_content']
    has_pos = 'my_position_short' in text or pos in text[:200]
    has_pod = 'pot_odds_required' in text or str(view.get('pot_odds_required'))[:4] in text[:200]
    print(f'  reasoning mentions position field: {has_pos}')
    print(f'  reasoning mentions pot_odds: {has_pod}')
    print(f'  text head: {text[:150]}...')
    print()
"
```

Verify:
- Claude correctly identifies position (no longer guessing "cutoff" for UTG).
- Claude references `pot_odds_required` directly instead of re-deriving.
- All 6 hands complete, 0 censor.
- Cost remains ~$0.01 per 6-hand session.

- [ ] **Step 5: Record observations + final commit**

```bash
git add -A && git commit -m "chore(phase-3d): post-verification cleanup" || echo "nothing to commit"
git log --oneline -10
```

---

## Phase 3d exit criteria

- [ ] Jinja-templated prompts via `PromptProfile.from_toml(...)`; default profile loads from package data; `my_position_short` + derived fields appear in rendered output.
- [ ] `rationale_required=True` (default) enforces non-empty text_content; empty text + tool_use consumes no_tool_retry budget.
- [ ] Four genuinely independent retry budgets: api_retry, illegal_retry, no_tool_retry, tool_usage_retry. Multi-tool-call no longer drains illegal_retry.
- [ ] `runs/<session>/censored_hands.jsonl` written on api_error/null final_action; partial canonical_private + public_replay + agent_view_snapshots records for the censored hand are dropped (not flushed).
- [ ] `redact_secret()` applied to `ApiErrorInfo.detail` + `IterationRecord.text_content`; sk- prefixed keys + Bearer tokens hidden behind sentinel.
- [ ] Real-Anthropic smoke re-run shows Claude using `my_position_short` and `pot_odds_required` from the rendered prompt instead of re-inferring.
- [ ] Full test suite + ruff + mypy --strict all green.
- [ ] No regressions in poker-play CLI or existing baseline runners.

---

## Self-review checklist

**Spec coverage:** §4.1 BR2-01 ✓ (full censor record), §4.1 BR2-05 ✓ (4 independent budgets), §4.5 ✓ (rationale_required strict), §6.1 ✓ (system Jinja), §6.2 ✓ (user Jinja), §6.3 ✓ partial (TOML instead of YAML — plan-acknowledged deviation, identical key set).

**Placeholder scan:** Each step has actual code. The redact_secret regex is permissive but covers the major providers; if a future provider uses a non-sk-prefixed key format, Phase 3d redaction misses it (acknowledge in plan, not block).

**Type consistency:** PromptProfile fields all named consistently; CensoredHandRecord uses dict[str, str] for api_error to dodge a forward-reference dependency on ApiErrorInfo. All retry counter names match Phase 3a + spec.

**Risk register:**
- R1: TOML choice deviates from spec §6.3 YAML. If a future analyst expects to round-trip YAML, the deviation surfaces. Plan declared. Worst case: add pyyaml in Phase 3e.
- R2: PromptProfile `_env: Environment` on a frozen dataclass. Pydantic equivalent would `arbitrary_types_allowed`; we used stdlib dataclass which has no such constraint. Watch for re-instantiation cost — Jinja Environment caches templates, so reusing a single profile across turns is the fast path.
- R3: Staged snapshots in Session add per-hand memory growth. With ~10 turns/hand and ~5KB/snapshot, that's ~50KB/hand peak. Acceptable for 1000-hand sessions.
- R4: redact_secret regex `sk-[A-Za-z0-9_-]{12,}` may over-match in pathological cases (e.g., a hand-history string with "sk-foo" 13+ chars). Acceptable trade — over-redaction is a feature.
- R5: `default-v2.toml` loads via `tomllib.load(open("rb"))` which doesn't traverse package-data path correctly in zipped installs. Mitigation: use `Path(__file__).parent / ...` (already in code). For pip-installed wheels this is sufficient because hatch's `force-include` ships the file.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-24-llm-poker-arena-phase-3d-prompt-retry-censor-redact.md`.**

Recommendation: **codex audit first**, then inline execution (this plan is much smaller than 3a — 7 tasks, ~1500 lines — and the dependencies between tasks are linear, so subagent-driven adds overhead without much benefit). Real-Anthropic re-smoke at Task 7 doubles as the empirical verification that prompt improvements landed.

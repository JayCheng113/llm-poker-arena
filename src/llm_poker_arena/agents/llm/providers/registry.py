"""Single source of truth for provider configuration.

Two callers historically duplicated provider URLs / env-var names:
  - `cli/play.py` (`_PROVIDER_TABLE`)
  - `web/scripts/generate-demo-*.py` (hard-coded per-provider blocks)

A divergence bit us during 6-LLM smoke: cli/play.py used Kimi's
international endpoint (`api.moonshot.ai`) but the user's API key is
China-region (`api.moonshot.cn`). The generator had been quietly fixed
in-line, leaving the CLI broken. This module centralizes the table so
fixing it once is the only fix needed.

Add a new provider here → both the CLI and every demo generator pick
it up automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderConfig:
    """One row in the registry.

    `is_anthropic` flips the provider class (Anthropic SDK vs. OpenAI-compat
    shim). `base_url=None` means the SDK uses its own default (Anthropic,
    OpenAI). `sdk_max_retries=None` keeps the AsyncOpenAI SDK default of 2;
    set higher for providers known to throw 5xx during capacity spikes
    (Gemini AI Studio is the canonical example — see Gemini entry below).
    `enable_thinking_summary=True` opts the provider into the Gemini-style
    `extra_body.google.thinking_config.include_thoughts` request — the
    response then contains `<thought>...</thought>` blocks the provider
    parses out as a SUMMARY artifact. Only Gemini supports this today.
    Per-model temperature overrides live in `MODEL_OVERRIDES`, not here —
    they're a model-specific quirk, not a provider-wide one.
    """

    provider_name: str
    env_var: str
    base_url: str | None = None
    is_anthropic: bool = False
    sdk_max_retries: int | None = None
    enable_thinking_summary: bool = False


# Per-model overrides keyed by "provider:model". Today this is only used
# for temperature locks (Kimi k2.5), but future model quirks (frequency
# penalty caps, max-tokens minima, etc.) belong here too.
#
# Why not on ProviderConfig: a provider-wide lock is wrong — Kimi k2.5
# specifically requires temperature=1.0, but there's no guarantee future
# Kimi releases will. Locking by model means we don't accidentally clamp
# `kimi-k2.6` or a future variant. (codex P1 finding 2026-04-27.)
MODEL_OVERRIDES: dict[str, dict[str, Any]] = {
    # Kimi K2.5 enforces temperature=1.0 (any other value 400s with
    # "invalid temperature: only 1 is allowed for this model").
    "kimi:kimi-k2.5": {"enforced_temperature": 1.0},
    # Kimi K2.6 inherits the same temperature constraint — empirically
    # verified 2026-04-29 (flagship-all smoke censored 2/2 K2.6 hands
    # with "invalid temperature: only 1 is allowed for this model"
    # before this lock was added). The k2.5→k2.6 release notes don't
    # mention this; verify per-model on each new variant.
    "kimi:kimi-k2.6": {"enforced_temperature": 1.0},
    # OpenAI Responses API `reasoning.effort` per-model. Default in the
    # provider is "low" (cheap, terse summaries). Bump to "medium" or
    # "high" for flagship comparisons where we want the model to
    # actually think — at the cost of 3-10x reasoning tokens, billed
    # at output rate. The mini variant stays "low" since the model
    # itself is cost-targeted; pulling the lever wouldn't be apples-
    # to-apples with the rest of the mini lineup.
    "openai:gpt-5.4-mini": {"reasoning_effort": "low"},
    "openai:gpt-5.5":      {"reasoning_effort": "medium"},
}


PROVIDERS: dict[str, ProviderConfig] = {
    "anthropic": ProviderConfig(
        provider_name="anthropic",
        env_var="ANTHROPIC_API_KEY",
        is_anthropic=True,
    ),
    "openai": ProviderConfig(
        provider_name="openai",
        env_var="OPENAI_API_KEY",
    ),
    "deepseek": ProviderConfig(
        provider_name="deepseek",
        env_var="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com/v1",
    ),
    "qwen": ProviderConfig(
        provider_name="qwen",
        env_var="QWEN_API_KEY",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    "kimi": ProviderConfig(
        provider_name="kimi",
        env_var="KIMI_API_KEY",
        # User's key is China-region — moonshot.cn (the .ai international
        # endpoint 401s on this key). If you have a .ai key, swap this URL
        # locally; do not push the swap (most users on this codebase have
        # the .cn key).
        base_url="https://api.moonshot.cn/v1",
    ),
    "grok": ProviderConfig(
        provider_name="grok",
        env_var="GROK_API_KEY",
        base_url="https://api.x.ai/v1",
    ),
    "openrouter": ProviderConfig(
        provider_name="openrouter",
        env_var="OPENROUTER_API_KEY",
        # OpenRouter is a multi-provider gateway with a single OpenAI-
        # compatible endpoint — useful for models that aren't on AI
        # Studio (e.g. gemini-3.x lives on Vertex AI; OpenRouter wraps
        # Vertex into the same OpenAI surface as everything else).
        # Model id includes a "vendor/" prefix, e.g.
        # "google/gemini-3.1-pro-preview". OpenRouter forwards a flat
        # ~5% markup over the underlying provider's pricing.
        base_url="https://openrouter.ai/api/v1",
    ),
    "gemini": ProviderConfig(
        provider_name="gemini",
        env_var="GEMINI_API_KEY",
        # Trailing slash matters: AsyncOpenAI client appends
        # /chat/completions and Google's edge has historically been
        # whitespace-strict on the path concat.
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        # AI Studio (the free / preview-tier endpoint we use here) is
        # known to throw 503 "model experiencing high demand" during
        # capacity spikes — community reports + our own first 30-hand
        # tournament both saw 503 censors. Spike duration is typically
        # tens of seconds; SDK default max_retries=2 with ~6s total
        # backoff isn't enough. Bump to 5 so AsyncOpenAI's own
        # exponential backoff covers ~30-60s of spike. Vertex AI / paid
        # tier is more stable but needs GCP setup outside this repo;
        # this is the cheapest mitigation that helps. (codex 2026-04-27.)
        sdk_max_retries=5,
        # Surface Gemini's internal thinking. The OpenAI-compat shim
        # accepts `extra_body.google.thinking_config.include_thoughts=True`
        # and inlines the model's reasoning summary into the response
        # `content` wrapped in <thought>...</thought>. The provider
        # extracts those blocks into a SUMMARY artifact so the UI panel
        # has something to show — without this Gemini's reasoning panel
        # is completely empty (verified 2026-04-27 smoke).
        enable_thinking_summary=True,
    ),
}


def make_provider(provider_tag: str, model: str, api_key: str) -> Any:
    """Build a provider instance from a registry tag.

    Lazy imports keep the registry free of heavy SDK deps when callers
    only need the metadata (env var, URL, etc.) for validation.
    """
    if provider_tag not in PROVIDERS:
        raise ValueError(
            f"unknown provider tag {provider_tag!r}; supported: "
            f"{sorted(PROVIDERS)}"
        )
    cfg = PROVIDERS[provider_tag]
    if cfg.is_anthropic:
        from llm_poker_arena.agents.llm.providers.anthropic_provider import (
            AnthropicProvider,
        )

        return AnthropicProvider(model=model, api_key=api_key)
    from llm_poker_arena.agents.llm.providers.openai_compatible import (
        OpenAICompatibleProvider,
    )

    kwargs: dict[str, Any] = {
        "provider_name_value": cfg.provider_name,
        "model": model,
        "api_key": api_key,
    }
    if cfg.base_url is not None:
        kwargs["base_url"] = cfg.base_url
    if cfg.sdk_max_retries is not None:
        kwargs["sdk_max_retries"] = cfg.sdk_max_retries
    if cfg.enable_thinking_summary:
        kwargs["enable_thinking_summary"] = True
    # Per-(provider,model) reasoning_effort override for the OpenAI
    # Responses API path (gpt-5.x / o-series). Provider's default is
    # "low"; MODEL_OVERRIDES lifts it for flagship models.
    eff = MODEL_OVERRIDES.get(f"{provider_tag}:{model}", {}).get("reasoning_effort")
    if eff is not None:
        kwargs["reasoning_effort"] = eff
    return OpenAICompatibleProvider(**kwargs)


def resolved_temperature(
    provider_tag: str, requested: float, model: str | None = None
) -> float:
    """Pick the actual temperature: caller's choice unless a specific
    `provider:model` row in MODEL_OVERRIDES enforces a fixed value
    (e.g. kimi:kimi-k2.5 → 1.0). Quietly overrides — log at the call
    site if you want to surface the swap.

    `model=None` keeps backward compatibility with old callers that
    don't pass model: in that case we look at all overrides for the
    provider and apply only if there's exactly one (catches the common
    case but won't silently clamp the wrong model when multiple exist)."""
    if model is not None:
        key = f"{provider_tag}:{model}"
        if key in MODEL_OVERRIDES and "enforced_temperature" in MODEL_OVERRIDES[key]:
            return float(MODEL_OVERRIDES[key]["enforced_temperature"])
        return requested
    # Legacy path: no model → only honor a lock if it's unambiguous
    matches = [
        v["enforced_temperature"]
        for k, v in MODEL_OVERRIDES.items()
        if k.startswith(f"{provider_tag}:") and "enforced_temperature" in v
    ]
    if len(matches) == 1:
        return float(matches[0])
    return requested

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
    shim). `enforced_temperature` lets a provider lock the sampling temp
    (Kimi K2.5 only accepts 1.0, for example). `base_url=None` means the
    SDK uses its own default (Anthropic, OpenAI).
    """

    provider_name: str
    env_var: str
    base_url: str | None = None
    is_anthropic: bool = False
    enforced_temperature: float | None = None


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
        # Kimi K2.5 enforces temperature=1.0 (any other value 400s with
        # "invalid temperature: only 1 is allowed for this model").
        enforced_temperature=1.0,
    ),
    "grok": ProviderConfig(
        provider_name="grok",
        env_var="GROK_API_KEY",
        base_url="https://api.x.ai/v1",
    ),
    "gemini": ProviderConfig(
        provider_name="gemini",
        env_var="GEMINI_API_KEY",
        # Trailing slash matters: AsyncOpenAI client appends
        # /chat/completions and Google's edge has historically been
        # whitespace-strict on the path concat.
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
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
    return OpenAICompatibleProvider(**kwargs)


def resolved_temperature(provider_tag: str, requested: float) -> float:
    """Pick the actual temperature: caller's choice unless the provider
    enforces a fixed value (Kimi). Quietly overrides — log at the call
    site if you want to surface the swap."""
    cfg = PROVIDERS.get(provider_tag)
    if cfg and cfg.enforced_temperature is not None:
        return cfg.enforced_temperature
    return requested

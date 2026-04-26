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

# Match `sk-` followed by 12+ chars of [A-Za-z0-9_-]; covers Anthropic
# (sk-ant-api03-...), OpenAI (sk-proj-..., sk-...), DeepSeek (sk-...).
_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{12,}")

# Generic long-string secret heuristic: 40+ char base64-ish runs after
# 'Bearer '/'Token ' or 'Authorization:'.
_BEARER_PATTERN = re.compile(r"(?i)(bearer|token|authorization:?)\s+[A-Za-z0-9+/=_-]{40,}")


def redact_secret(text: str | None) -> str:
    """Return `text` with API keys + Bearer tokens replaced by a sentinel."""
    if text is None:
        return ""
    out = _SK_PATTERN.sub("<REDACTED_API_KEY>", text)
    out = _BEARER_PATTERN.sub(lambda m: f"{m.group(1)} <REDACTED_API_KEY>", out)
    return out


__all__ = ["redact_secret"]

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
    text = "key1 sk-ant-api03-aaa111bbb222 and key2 sk-proj-bbb222ccc333ddd"
    redacted = redact_secret(text)
    assert "<REDACTED_API_KEY>" in redacted
    assert "sk-ant-api03-aaa111bbb222" not in redacted
    assert "sk-proj-bbb222ccc333ddd" not in redacted

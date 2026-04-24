"""Smoke test: verifies pytest + package import work."""
from __future__ import annotations


def test_package_imports() -> None:
    import llm_poker_arena

    assert llm_poker_arena.__doc__ is not None


def test_pytest_is_wired() -> None:
    assert 1 + 1 == 2

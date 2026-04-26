"""Smoke: Phase 2a subpackages exist and are importable."""

from __future__ import annotations


def test_storage_subpackage_importable() -> None:
    import llm_poker_arena.storage as storage

    assert storage.__doc__ is not None


def test_session_subpackage_importable() -> None:
    import llm_poker_arena.session as session

    assert session.__doc__ is not None

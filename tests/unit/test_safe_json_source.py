"""Tests for safe_json_source (spec §8.2 path whitelist + SQL literal escaping)."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_accepts_paths_under_runs_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve())
    from llm_poker_arena.storage.duckdb_query import safe_json_source

    session_dir = tmp_path / "session_2026-04-24_a8f3b2"
    session_dir.mkdir()
    p = session_dir / "public_replay.jsonl"
    p.touch()
    result = safe_json_source(p)
    assert str(p.resolve()) in result
    assert result.startswith("'")
    assert result.endswith("'")


def test_rejects_paths_outside_runs_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setattr("llm_poker_arena.storage.duckdb_query.RUNS_ROOT", runs_root.resolve())
    from llm_poker_arena.storage.duckdb_query import safe_json_source

    outside = tmp_path / "elsewhere" / "evil.jsonl"
    outside.parent.mkdir(parents=True)
    outside.touch()
    with pytest.raises(ValueError, match="not under trusted runs root"):
        safe_json_source(outside)


def test_rejects_path_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setattr("llm_poker_arena.storage.duckdb_query.RUNS_ROOT", runs_root.resolve())
    from llm_poker_arena.storage.duckdb_query import safe_json_source

    # Path with `..` that resolves outside runs_root.
    traversal = runs_root / ".." / "etc" / "passwd"
    with pytest.raises(ValueError, match="not under trusted runs root"):
        safe_json_source(traversal)


def test_escapes_single_quotes_in_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve())
    from llm_poker_arena.storage.duckdb_query import safe_json_source

    weird = tmp_path / "session_o'malley" / "public.jsonl"
    weird.parent.mkdir()
    weird.touch()
    result = safe_json_source(weird)
    assert "''" in result  # single quote doubled
    assert result.startswith("'")
    assert result.endswith("'")


def test_open_session_public_only_without_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """public_events view exists; hands + actions do NOT (no access token)."""
    monkeypatch.setattr("llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve())
    from llm_poker_arena.storage.duckdb_query import open_session

    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    (session_dir / "public_replay.jsonl").write_text('{"hand_id":0,"street_events":[]}\n')
    con = open_session(session_dir)
    try:
        views = {
            row[0]
            for row in con.sql("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()
        }
        assert "public_events" in views
        assert "hands" not in views
        assert "actions" not in views
    finally:
        con.close()


def test_open_session_with_token_exposes_all_three_views(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve())
    from llm_poker_arena.storage.access_control import PRIVATE_ACCESS_TOKEN
    from llm_poker_arena.storage.duckdb_query import open_session

    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    (session_dir / "public_replay.jsonl").write_text('{"hand_id":0,"street_events":[]}\n')
    (session_dir / "canonical_private.jsonl").write_text('{"hand_id":0}\n')
    (session_dir / "agent_view_snapshots.jsonl").write_text('{"hand_id":0,"seat":0}\n')
    con = open_session(session_dir, access_token=PRIVATE_ACCESS_TOKEN)
    try:
        views = {
            row[0]
            for row in con.sql("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()
        }
        assert {"public_events", "hands", "actions"}.issubset(views)
    finally:
        con.close()


def test_open_session_with_bad_token_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("llm_poker_arena.storage.duckdb_query.RUNS_ROOT", tmp_path.resolve())
    from llm_poker_arena.storage.duckdb_query import open_session

    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    (session_dir / "public_replay.jsonl").write_text('{"hand_id":0,"street_events":[]}\n')
    with pytest.raises(PermissionError, match="access_token"):
        open_session(session_dir, access_token="wrong-token")

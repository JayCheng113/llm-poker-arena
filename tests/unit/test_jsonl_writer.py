"""Tests for BatchedJsonlWriter (durability + batch semantics)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from llm_poker_arena.storage.jsonl_writer import BatchedJsonlWriter


def _lines(p: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def test_writes_buffer_flushes_at_batch_size(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    w = BatchedJsonlWriter(p)
    # BATCH_SIZE=10 so first 9 don't flush.
    for i in range(9):
        w.write({"i": i})
    assert _lines(p) == []  # still buffered
    w.write({"i": 9})  # 10th write triggers flush
    assert len(_lines(p)) == 10
    w.close()


def test_close_drains_remaining(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    w = BatchedJsonlWriter(p)
    for i in range(3):
        w.write({"i": i})
    assert _lines(p) == []
    w.close()
    assert len(_lines(p)) == 3


def test_time_based_flush(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """After FLUSH_INTERVAL_MS elapses since last flush, next write triggers a drain.

    Note: monkeypatch BEFORE construction so `__init__`'s `_last_flush_ns`
    capture uses the mocked clock. Starting `clock` at a non-trivial value
    (1e9) avoids negative-elapsed foot-guns if anything subtracts from it.
    """
    p = tmp_path / "out.jsonl"
    clock = [1_000_000_000]  # start at a large value; writer's __init__ captures this
    monkeypatch.setattr(
        "llm_poker_arena.storage.jsonl_writer.time.monotonic_ns",
        lambda: clock[0],
    )
    w = BatchedJsonlWriter(p)  # captures _last_flush_ns = 1_000_000_000
    w.write({"i": 0})  # elapsed = 0 < interval → buffered
    assert _lines(p) == []
    clock[0] += (BatchedJsonlWriter.FLUSH_INTERVAL_MS + 50) * 1_000_000
    w.write({"i": 1})  # elapsed ≥ interval → flush both
    assert len(_lines(p)) == 2
    w.close()


def test_json_serialization_is_deterministic(tmp_path: Path) -> None:
    """Dict keys must serialize in sorted order for diff-friendliness."""
    p = tmp_path / "out.jsonl"
    w = BatchedJsonlWriter(p)
    # Intentionally unsorted-key dicts.
    w.write({"b": 2, "a": 1, "c": 3})
    w.close()
    text = p.read_text().strip()
    # json.dumps with sort_keys=True → '{"a": 1, "b": 2, "c": 3}'
    assert text == '{"a": 1, "b": 2, "c": 3}'


def test_append_mode_preserves_prior_content(tmp_path: Path) -> None:
    """Reopening a writer on the same path appends; prior lines survive."""
    p = tmp_path / "out.jsonl"
    w1 = BatchedJsonlWriter(p)
    w1.write({"i": 0})
    w1.close()
    w2 = BatchedJsonlWriter(p)
    w2.write({"i": 1})
    w2.close()
    assert _lines(p) == [{"i": 0}, {"i": 1}]


def test_write_after_close_raises(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    w = BatchedJsonlWriter(p)
    w.close()
    with pytest.raises(RuntimeError, match="closed"):
        w.write({"i": 0})

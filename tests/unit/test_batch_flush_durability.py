"""Durability: BatchedJsonlWriter loses ≤ BATCH_SIZE entries on SIGKILL."""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from llm_poker_arena.storage.jsonl_writer import BatchedJsonlWriter


@pytest.mark.skipif(sys.platform == "win32", reason="fork-based test; Unix only")
def test_sigkill_loses_at_most_batch_size_entries(tmp_path: Path) -> None:
    out = tmp_path / "durability.jsonl"
    # Intentionally NOT a multiple of BATCH_SIZE: if we used 50 (=5*BATCH_SIZE)
    # the last flush triggers exactly at i=49 and the SIGKILL hits an empty
    # buffer — the test would pass trivially without exercising partial loss.
    # 47 guarantees 7 entries are in buffer at SIGKILL time.
    total = 47
    pid = os.fork()
    if pid == 0:
        # Child
        w = BatchedJsonlWriter(out)
        for i in range(total):
            w.write({"i": i})
            # Don't flush — rely on BATCH_SIZE + FLUSH_INTERVAL_MS only.
            if i == total - 1:
                # Kill before close() can drain.
                os.kill(os.getpid(), signal.SIGKILL)
        os._exit(0)
    else:
        # Parent
        (_, status) = os.waitpid(pid, 0)
        assert os.WIFSIGNALED(status)
        assert os.WTERMSIG(status) == signal.SIGKILL

    # Verify file contents.
    time.sleep(0.05)  # fsyncs settle
    lines = out.read_text().splitlines() if out.exists() else []
    written = len(lines)
    lost = total - written
    assert 0 <= lost <= BatchedJsonlWriter.BATCH_SIZE, (
        f"expected ≤ {BatchedJsonlWriter.BATCH_SIZE} lost, got lost={lost}, "
        f"written={written}"
    )
    # Any written line must be valid JSON.
    for line in lines:
        json.loads(line)


@pytest.mark.skipif(sys.platform == "win32", reason="fork-based test; Unix only")
def test_sigterm_drains_buffer_and_terminates(tmp_path: Path) -> None:
    """SIGTERM drains the buffer AND re-raises default termination.

    Prior plan drafts used `os._exit(0)` after the self-signal, which would
    mask a handler that swallowed SIGTERM without re-raising. This test
    asserts the child actually terminates BY signal (WIFSIGNALED) — that
    catches the "SIGTERM silently swallowed" regression the writer's handler
    is specifically designed to avoid.
    """
    out = tmp_path / "sigterm.jsonl"
    pid = os.fork()
    if pid == 0:
        # Child
        w = BatchedJsonlWriter(out)
        for i in range(3):
            w.write({"i": i})
        # 3 entries < BATCH_SIZE; buffer not yet flushed. Signal ourselves.
        os.kill(os.getpid(), signal.SIGTERM)
        # Should never reach here — handler drains and re-raises default.
        # If we do reach here, the handler swallowed the signal (regression).
        os._exit(99)
    else:
        (_, status) = os.waitpid(pid, 0)

    assert os.WIFSIGNALED(status), (
        f"child did not terminate by signal; SIGTERM handler likely swallowed the "
        f"signal without re-raising. status={status!r}"
    )
    assert os.WTERMSIG(status) == signal.SIGTERM

    lines = out.read_text().splitlines() if out.exists() else []
    # All 3 buffered entries should be present — drain ran BEFORE termination.
    assert len(lines) == 3

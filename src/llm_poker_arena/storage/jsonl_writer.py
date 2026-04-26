"""Buffered JSONL writer with periodic/size-based fsync + crash-safe drain.

Spec §8.1 / H-10. Guarantees:
  - Flush every `BATCH_SIZE` records OR `FLUSH_INTERVAL_MS` since last flush.
  - Drain + fsync on atexit and SIGTERM.
  - Crash at arbitrary point loses at most `BATCH_SIZE` buffered records.

Each record serializes as one line via `json.dumps(..., sort_keys=True)` for
deterministic output (diff-friendly under same input).
"""

from __future__ import annotations

import atexit
import json
import os
import signal
import time
from pathlib import Path
from typing import Any


class BatchedJsonlWriter:
    """Buffered append-only JSONL writer."""

    BATCH_SIZE: int = 10
    FLUSH_INTERVAL_MS: int = 200

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._buffer: list[str] = []
        self._f = self._path.open("a", encoding="utf-8")
        self._last_flush_ns: int = time.monotonic_ns()
        self._closed: bool = False
        atexit.register(self._drain_silent)
        # SIGTERM: drain then let the default handler terminate the process.
        # `signal.getsignal` returns an int (SIG_DFL/SIG_IGN) for non-Python
        # handlers, so we cannot just call it. Instead, drain, restore the
        # previous handler, and re-send SIGTERM so the process actually exits.
        # If a prior handler was a callable (e.g. another writer chained), we
        # restore it and re-send so the chain continues.
        prev = signal.getsignal(signal.SIGTERM)

        def _on_sigterm(signum: int, frame: Any) -> None:  # noqa: ANN401
            self._drain_silent()
            # Restore prior handler and re-send SIGTERM so chain continues or
            # default termination fires. Without this, SIGTERM gets swallowed.
            signal.signal(signal.SIGTERM, prev)
            os.kill(os.getpid(), signal.SIGTERM)

        signal.signal(signal.SIGTERM, _on_sigterm)

    def write(self, record: dict[str, Any]) -> None:
        """Append one record. Flushes if batch-size or time-interval triggered."""
        if self._closed:
            raise RuntimeError("BatchedJsonlWriter is closed")
        self._buffer.append(json.dumps(record, sort_keys=True))
        if len(self._buffer) >= self.BATCH_SIZE:
            self._flush()
            return
        # time-based flush
        if (time.monotonic_ns() - self._last_flush_ns) >= self.FLUSH_INTERVAL_MS * 1_000_000:
            self._flush()

    def flush(self) -> None:
        """Force-drain the buffer to disk (hand-end checkpoint)."""
        self._flush()

    def close(self) -> None:
        """Drain buffer and close the underlying file.

        IO errors from `_flush()` PROPAGATE — an explicit `close()` is the
        caller's signal that they want to know whether data made it to disk.
        The file is still closed in a `finally` block so the file descriptor
        is cleaned up even on error.
        `_drain_silent()` is reserved for atexit + signal handlers where
        raising would be actively harmful.
        """
        if self._closed:
            return
        try:
            self._flush()
        finally:
            self._f.close()
            self._closed = True

    # ----- internals -----

    def _flush(self) -> None:
        if not self._buffer:
            return
        self._f.write("\n".join(self._buffer) + "\n")
        self._f.flush()
        os.fsync(self._f.fileno())
        self._buffer.clear()
        self._last_flush_ns = time.monotonic_ns()

    def _drain_silent(self) -> None:
        """atexit-safe: never raise."""
        try:  # noqa: SIM105 — explicit form is clearer for atexit drain path
            self._flush()
        except Exception:  # noqa: BLE001 — atexit path, must not propagate
            pass

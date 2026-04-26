"""Access-bounded JSONL readers (spec §7.5 / HR2-06).

PublicLogReader: only needs public_replay.jsonl. Can be used on a session
directory where private files were stripped before publishing.

PrivateLogReader: needs all three layers + a valid access_token. Does NOT
inherit from PublicLogReader — would otherwise force private files to exist
for public-only workflows.

Phase 2a stub: `require_private_access` accepts a single sentinel token.
Phase 3+ will wire real credential management.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

PRIVATE_ACCESS_TOKEN: str = "dev-local-private-v1"


def require_private_access(token: str) -> None:
    if token != PRIVATE_ACCESS_TOKEN:
        raise PermissionError(
            "PrivateLogReader requires a valid access_token "
            "(Phase 2a: use PRIVATE_ACCESS_TOKEN sentinel from storage.access_control)"
        )


class PublicLogReader:
    """Read public_replay.jsonl only. No private-file dependency."""

    def __init__(self, session_dir: Path) -> None:
        self._session_dir = Path(session_dir)
        self._public_path = self._session_dir / "public_replay.jsonl"
        if not self._public_path.exists():
            raise FileNotFoundError(
                f"Public replay not found at {self._public_path}. "
                f"PublicLogReader only needs public_replay.jsonl; private files are not required."
            )

    def iter_events(self) -> Iterator[dict[str, Any]]:
        """Yield one record per line.

        Spec §7.3 shape: each line is a HAND-level record
        `{"hand_id": N, "street_events": [...]}`, NOT a single event. Method
        name `iter_events` is kept to match spec §7.5 but the yielded unit is
        a whole hand; iterate `record["street_events"]` for atomic events.
        """
        with self._public_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)


class PrivateLogReader:
    """Read all three layers. Requires access_token whitelist check."""

    def __init__(self, session_dir: Path, access_token: str) -> None:
        require_private_access(access_token)
        self._session_dir = Path(session_dir)
        self._private_path = self._session_dir / "canonical_private.jsonl"
        self._public_path = self._session_dir / "public_replay.jsonl"
        self._snapshots_path = self._session_dir / "agent_view_snapshots.jsonl"
        for p in (self._private_path, self._public_path, self._snapshots_path):
            if not p.exists():
                raise FileNotFoundError(f"Required session file missing: {p}")

    def iter_private_hands(self) -> Iterator[dict[str, Any]]:
        with self._private_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def iter_snapshots(self) -> Iterator[dict[str, Any]]:
        with self._snapshots_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def public_reader(self) -> PublicLogReader:
        return PublicLogReader(self._session_dir)

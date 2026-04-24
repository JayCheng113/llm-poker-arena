"""Tests for PublicLogReader and PrivateLogReader (trust boundary enforcement)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_poker_arena.storage.access_control import (
    PRIVATE_ACCESS_TOKEN,
    PrivateLogReader,
    PublicLogReader,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in records) + "\n")


def test_public_reader_works_without_private_files(tmp_path: Path) -> None:
    # Spec §7.3: one line per hand (not one line per event).
    _write_jsonl(tmp_path / "public_replay.jsonl",
                 [{"hand_id": 0, "street_events": [
                     {"type": "hand_started", "hand_id": 0, "button_seat": 0,
                      "blinds": {"sb": 50, "bb": 100}},
                     {"type": "hand_ended", "hand_id": 0, "winnings": {"0": 0}},
                 ]}])
    r = PublicLogReader(tmp_path)
    hands = list(r.iter_events())
    assert len(hands) == 1
    assert hands[0]["hand_id"] == 0
    assert hands[0]["street_events"][0]["type"] == "hand_started"


def test_public_reader_raises_when_public_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="public_replay.jsonl"):
        PublicLogReader(tmp_path)


def test_private_reader_requires_all_three_files(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "public_replay.jsonl",
                 [{"hand_id": 0, "street_events": []}])
    with pytest.raises(FileNotFoundError, match="canonical_private.jsonl"):
        PrivateLogReader(tmp_path, access_token=PRIVATE_ACCESS_TOKEN)


def test_private_reader_rejects_wrong_token(tmp_path: Path) -> None:
    for name in ("canonical_private.jsonl", "public_replay.jsonl", "agent_view_snapshots.jsonl"):
        _write_jsonl(tmp_path / name, [{"ok": True}])
    with pytest.raises(PermissionError, match="access_token"):
        PrivateLogReader(tmp_path, access_token="wrong")


def test_private_reader_iterates_all_three_layers(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "canonical_private.jsonl", [{"hand_id": 0}])
    _write_jsonl(tmp_path / "public_replay.jsonl",
                 [{"hand_id": 0, "street_events": []}])
    _write_jsonl(tmp_path / "agent_view_snapshots.jsonl", [{"hand_id": 0, "seat": 1}])
    r = PrivateLogReader(tmp_path, access_token=PRIVATE_ACCESS_TOKEN)
    assert list(r.iter_private_hands()) == [{"hand_id": 0}]
    assert list(r.iter_snapshots()) == [{"hand_id": 0, "seat": 1}]
    # public sub-reader still works
    pub = r.public_reader()
    assert list(pub.iter_events()) == [{"hand_id": 0, "street_events": []}]

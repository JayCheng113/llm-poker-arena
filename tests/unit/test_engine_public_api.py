"""Sanity check: every Phase-1 public symbol is importable from llm_poker_arena.engine."""

from __future__ import annotations

EXPECTED = {
    "Action",
    "ActionRecord",
    "ActionToolSpec",
    "AgentSnapshot",
    "CardStr",
    "Chips",
    "HandContext",
    "LegalActionSet",
    "OpponentStatsOrInsufficient",
    "PlayerView",
    "PublicView",
    "RANKS",
    "SUITS",
    "SeatId",
    "SeatPublicInfo",
    "SessionConfig",
    "SessionParamsView",
    "SidePotInfo",
    "Street",
    "StreetHistory",
    "TransitionResult",
    "apply_action",
    "build_player_view",
    "build_public_view",
    "compute_legal_tool_set",
    "default_safe_action",
    "is_valid_card_str",
}


def test_public_api_exports_are_complete() -> None:
    import llm_poker_arena.engine as engine

    missing = EXPECTED - set(dir(engine))
    assert not missing, f"missing from engine public API: {sorted(missing)}"

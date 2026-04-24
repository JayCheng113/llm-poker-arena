"""Public engine API for Phase 1.

Outer code imports from this module only. `_internal/*` is off-limits.
"""
from __future__ import annotations

from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.legal_actions import (
    Action,
    compute_legal_tool_set,
    default_safe_action,
)
from llm_poker_arena.engine.projections import build_player_view, build_public_view
from llm_poker_arena.engine.transition import TransitionResult, apply_action
from llm_poker_arena.engine.types import (
    RANKS,
    SUITS,
    CardStr,
    Chips,
    SeatId,
    Street,
    is_valid_card_str,
)
from llm_poker_arena.engine.views import (
    ActionRecord,
    ActionToolSpec,
    AgentSnapshot,
    LegalActionSet,
    OpponentStatsOrInsufficient,
    PlayerView,
    PublicView,
    SeatPublicInfo,
    SessionParamsView,
    SidePotInfo,
    StreetHistory,
)

__all__ = [
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
]

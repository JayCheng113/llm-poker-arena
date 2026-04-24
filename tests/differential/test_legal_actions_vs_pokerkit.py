"""S-02: compute_legal_tool_set must align with PokerKit's native can_* predicates."""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from llm_poker_arena.engine._internal.poker_state import CanonicalState
from llm_poker_arena.engine._internal.rebuy import derive_deck_seed
from llm_poker_arena.engine.config import HandContext, SessionConfig
from llm_poker_arena.engine.legal_actions import compute_legal_tool_set


@given(
    rng_seed=st.integers(min_value=0, max_value=2_000),
    hand_id=st.integers(min_value=0, max_value=50),
)
@settings(max_examples=100, deadline=None)
def test_our_legal_names_match_pokerkit_predicates(rng_seed: int, hand_id: int) -> None:
    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=60, max_utility_calls=5,
        enable_math_tools=False, enable_hud_tool=False, rationale_required=True,
        opponent_stats_min_samples=30, rng_seed=rng_seed,
    )
    ctx = HandContext(
        hand_id=hand_id, deck_seed=derive_deck_seed(rng_seed, hand_id),
        button_seat=hand_id % 6, initial_stacks=(10_000,) * 6,
    )
    state = CanonicalState(cfg, ctx)
    raw = state._state  # noqa: SLF001
    actor = int(getattr(raw, "actor_index", None) or getattr(raw, "actor", 0) or 0)

    legal = compute_legal_tool_set(state, actor)
    names = {t.name for t in legal.tools}

    pk_can_fold = bool(raw.can_fold()) if hasattr(raw, "can_fold") else False
    pk_can_check_or_call = bool(raw.can_check_or_call()) if hasattr(raw, "can_check_or_call") else False
    pk_can_complete = bool(raw.can_complete_bet_or_raise_to()) if hasattr(raw, "can_complete_bet_or_raise_to") else False

    # Contract derived from spec §3.3:
    # - fold present iff PokerKit allows fold AND there's something to call.
    # - check XOR call present iff PokerKit allows check_or_call.
    # - bet XOR raise_to present iff PokerKit allows complete_bet_or_raise_to.
    if not pk_can_fold:
        assert "fold" not in names
    if not pk_can_check_or_call:
        assert "check" not in names
        assert "call" not in names
    else:
        assert ("check" in names) ^ ("call" in names), names
    if not pk_can_complete:
        assert "bet" not in names
        assert "raise_to" not in names
    else:
        assert ("bet" in names) ^ ("raise_to" in names), names

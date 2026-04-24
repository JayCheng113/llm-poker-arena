# PokerKit 0.7.3 API Reference (empirically confirmed for llm-poker-arena Phase 1)

Discovered on 2026-04-24 against installed `pokerkit==0.7.3` in `.venv/`. Use this as the authoritative attribute-name reference for plan T6-T9 implementation. If the plan and this doc disagree, this doc wins.

All findings below were produced by running probe scripts under `.venv/bin/python` (the user's machine segfaults on `uv run pytest`/`uv run python` because of a readline import quirk; use `.venv/bin/python` directly).

---

## A. Card construction

`Card` is a **frozen dataclass** in `pokerkit.utilities`, re-exported as `pokerkit.Card`. Both imports work and resolve to the same class:

```python
from pokerkit import Card                        # canonical
from pokerkit.utilities import Card              # also fine; pokerkit.Card is pokerkit.utilities.Card -> True
```

**Constructor signature** (verbatim from `inspect.signature`):
```
Card(rank: 'Rank', suit: 'Suit') -> None
```
So `Card("As")` and `Card(text="As")` **both fail** — the dataclass requires a `Rank` enum and a `Suit` enum:
```python
from pokerkit import Card, Rank, Suit
c = Card(rank=Rank("A"), suit=Suit("s"))   # works; Rank/Suit accept single-char strings
```

**The canonical recipe is `Card.parse(text)`**, which returns an `Iterator[Card]` (a generator):
```python
list(Card.parse("As"))      # [As]                    -- one card
list(Card.parse("AsKh"))    # [As, Kh]                -- two cards
```

`Card.parse(...)` is the only construction path that takes string notation. Always wrap in `list(...)` if you need a sequence (it's a generator, not a tuple).

**Critical str/repr quirk** (counter-intuitive):
```python
c = next(Card.parse("As"))
str(c)    # 'ACE OF SPADES (As)'    -- VERBOSE
repr(c)   # 'As'                    -- COMPACT
```
This is **opposite** the typical Python convention. **For prompts and logging, use `repr(c)` or f-string `{c!r}` to get the compact form `'As'`**. Do NOT rely on `str(c)` to give you `"As"` — it gives `"ACE OF SPADES (As)"`. There is no bracket-wrapping (`'[As]'` does not appear) and no unicode-suit form (`'A♠'` does not appear).

`Rank` enum members: `ACE='A'`, `DEUCE='2'`, `TREY='3'`, `FOUR='4'`, ..., `KING='K'`, `UNKNOWN='?'`.
`Suit` enum members: `CLUB='c'`, `DIAMOND='d'`, `HEART='h'`, `SPADE='s'`, `UNKNOWN='?'`.

`Card` API also exposes accept-anything helpers via the `CardsLike` type alias — most state methods that take cards accept either a `Card`, a string like `"AsKh"`, or an iterable of `Card`s. So you can usually just pass the string directly to `state.deal_hole("As")` and skip explicit Card construction.

---

## B. Automation enum members

`pokerkit.Automation` is a `StrEnum`. **Full member list** (verified by iterating `Automation`):

| Name                         | Value                       |
|------------------------------|-----------------------------|
| `ANTE_POSTING`               | `'Ante posting'`            |
| `BET_COLLECTION`             | `'Bet collection'`          |
| `BLIND_OR_STRADDLE_POSTING`  | `'Blind or straddle posting'` |
| `CARD_BURNING`               | `'Card burning'`            |
| `HOLE_DEALING`               | `'Hole dealing'`            |
| `BOARD_DEALING`              | `'Board dealing'`           |
| `RUNOUT_COUNT_SELECTION`     | `'Runout-count selection'`  |
| `HOLE_CARDS_SHOWING_OR_MUCKING` | `'Hole cards showing or mucking'` |
| `HAND_KILLING`               | `'Hand killing'`            |
| `CHIPS_PUSHING`              | `'Chips pushing'`           |
| `CHIPS_PULLING`              | `'Chips pulling'`           |

**Name-by-name confirmation against the plan's expected list:**

| Plan-expected     | Actually exists? | Notes |
|-------------------|------------------|-------|
| `ANTE_POSTING`    | yes (exact) | |
| `BET_COLLECTION`  | yes (exact) | |
| `BLIND_OR_STRADDLE_POSTING` | yes (exact) | |
| `CARD_BURNING`    | yes (exact) | |
| `BOARD_DEALING`   | yes (exact) | |
| `HOLE_DEALING`    | yes (exact) | |
| `HAND_KILLING`    | yes (exact) | |
| `CHIPS_PUSHING`   | yes (exact) | |
| `CHIPS_PULLING`   | yes (exact) | |
| `RUNOUT_COUNT_SELECTION` | yes (exact) | |

All 10 plan-expected names exist verbatim. **No renames required.** There is one extra member, `HOLE_CARDS_SHOWING_OR_MUCKING`, which the plan can ignore (we want manual showdown).

For our use case (manual hole/board/burn dealing, automated bookkeeping), the canonical automation tuple is:
```python
automations=(
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)
```
(Deliberately **excludes** `HOLE_DEALING`, `BOARD_DEALING`, `CARD_BURNING` so the engine driver can feed cards manually, and excludes `HOLE_CARDS_SHOWING_OR_MUCKING` so we control showdown reveals.)

---

## C. NoLimitTexasHoldem.create_state

Verbatim signature from `inspect.signature(NoLimitTexasHoldem.create_state)`:

```
(automations: 'tuple[Automation, ...]',
 ante_trimming_status: 'bool',
 raw_antes: 'ValuesLike',
 raw_blinds_or_straddles: 'ValuesLike',
 min_bet: 'int',
 raw_starting_stacks: 'ValuesLike',
 player_count: 'int',
 *,
 mode: 'Mode' = <Mode.TOURNAMENT: 'Tournament'>,
 starting_board_count: 'int' = 1,
 divmod: 'Callable[[int, int], tuple[int, int]]' = <function divmod>,
 rake: 'Callable[[int, State], tuple[int, int]]' = <function rake>) -> 'State'
```

Per-kwarg confirmation against the plan:

| Plan kwarg               | Exists? | Notes |
|--------------------------|---------|-------|
| `automations`            | yes | tuple of `Automation` |
| `ante_trimming_status`   | yes | bool, required |
| `raw_antes`              | yes | accepts int (broadcast to all seats) or tuple per seat |
| `raw_blinds_or_straddles`| yes | accepts tuple `(50, 100)` for SB/BB |
| `min_bet`                | yes | int |
| `raw_starting_stacks`    | yes | accepts int (broadcast) or tuple |
| `player_count`           | yes | int |

All seven plan-expected kwargs exist with the exact names. No renames.

**Three additional keyword-only optional args** (kwarg-only, defaults, safe to ignore for MVP):
- `mode: Mode = Mode.TOURNAMENT` — `Mode` enum has `TOURNAMENT='Tournament'` and `CASH_GAME='Cash-game'`.
- `starting_board_count: int = 1` — leave at 1 for standard NLHE.
- `divmod`, `rake` — function hooks; defaults are fine.

**Canonical call for 6-max NLHE 50/100 with 100bb stacks** (verified to construct successfully):
```python
state = NoLimitTexasHoldem.create_state(
    automations=(
        Automation.ANTE_POSTING,
        Automation.BET_COLLECTION,
        Automation.BLIND_OR_STRADDLE_POSTING,
        Automation.HAND_KILLING,
        Automation.CHIPS_PUSHING,
        Automation.CHIPS_PULLING,
    ),
    ante_trimming_status=False,
    raw_antes=0,
    raw_blinds_or_straddles=(50, 100),
    min_bet=100,
    raw_starting_stacks=10000,
    player_count=6,
)
```

Note: parameters are POSITIONAL_OR_KEYWORD, so positional calls also work, but **always use kwargs** for clarity.

---

## D. State attributes

After constructing the canonical state above and dealing 12 hole cards (one card at a time, alternating dealee), the following are confirmed:

### Current actor

| Question | Answer |
|----------|--------|
| Whose turn is it?  | **`state.actor_index`** — int seat index, or **`None`** when no action required (between streets, hand over, mid-deal). |
| Pre-deal value | `None` (because `hole_dealee_index=0` is set instead — dealing must happen first). |
| Post 12-card-deal value | `2` (UTG, the seat after the BB). |
| Hand-over value | `None`, and `state.status` becomes `False`. |
| Method version exists? | No `state.actor` (without `_index`); no `state.turn_index` (don't confuse with `state.actor_indices`, which is a `deque` of upcoming seats). |

**`state.is_actor_required` does NOT exist.** Use `state.actor_index is not None` as the "someone needs to act" predicate.

### Card containers

| Plan-name | Reality | Type / shape |
|-----------|---------|--------------|
| `state.hole_cards` | EXISTS, attribute | `list[list[Card]]` of length `player_count`. Index by seat. Each inner list grows as cards are dealt. Empty `[]` for folded seats after `HAND_KILLING` (mucked cards move to `state.mucked_cards`). |
| `state.community_cards` | DOES NOT EXIST | use `state.board_cards`. |
| `state.board_cards` | EXISTS, attribute | **`list[list[Card]]`** — outer index is "card-slot on the board" (0..4 for flop/turn/river), inner list is the runouts at that slot. For standard single-runout NLHE, every inner list has exactly 1 card. Example after flop: `[[2d], [2h], [2s]]` (NOT `[2d, 2h, 2s]`). |
| Flat board access | use **`list(state.get_board_cards(0))`** to flatten board 0 to `[2d, 2h, 2s, ...]`. |
| `state.burn_cards` | EXISTS, attribute, `list[Card]`. |
| `state.mucked_cards` | EXISTS, attribute, **flat** `list[Card]` of every card that was folded/killed. |

### Stacks / bets / pot

| Name | Type | Behavior |
|------|------|----------|
| `state.stacks` | `list[int]`, length=player_count | Behind-stack chips per seat. Updated as bets collected. |
| `state.bets`   | `list[int]`, length=player_count | Per-seat current street bet. Resets to all-zero after `BET_COLLECTION`. |
| `state.starting_stacks` | `tuple[int, ...]` | Immutable record of stacks at hand start. |
| `state.payoffs` | `list[int]` | Net P&L per seat for this hand (negative = lost). |
| `state.antes`, `state.blinds_or_straddles` | tuples | Configured values. |
| `state.total_pot_amount` | `int`, attribute | **CANONICAL pot accessor.** = collected `pots` + uncollected `bets`. Works at all times. |
| `state.pots` | **generator** of `Pot` | Re-computed each access. Each `Pot` has `.amount` (== `.unraked_amount`), `.raked_amount`, `.unraked_amount`, `.player_indices` (tuple of eligible seat indices). **EMPTY until first `BET_COLLECTION` happens** — i.e., during preflop pre-collection, `list(state.pots) == []`. After flop deal it would be `[Pot(amount=600, player_indices=(0,1,2,3,4,5))]`. |
| `state.pot_amounts` | generator of `int` | Same as `[p.amount for p in state.pots]`. Same emptiness caveat. |

**Plan delta:** the plan probably wants to write `state.pots[0].amount` — that will fail (generator, not subscriptable; also empty during pre-collection windows). Use `state.total_pot_amount` for any "current pot size" prompt field.

### Status / state flags

| Name | Type | Meaning |
|------|------|---------|
| `state.status` | `bool` | Hand-active flag. `True` while hand is in progress, flips to `False` when settled. |
| `state.statuses` | `list[bool]` | Per-seat "still in hand" flag. Seats that fold flip to `False`. |
| `state.all_in_status` | `bool` | True when no further action possible (everyone all-in or folded to one). |
| `state.folded_status` | `bool` | Internal — likely "current actor's last action was fold"; not load-bearing for our purposes. |

### Operations history

| Name | Type | Notes |
|------|------|-------|
| `state.operations` | `list[Operation]` | Append-only event log. Each entry is a typed dataclass like `BlindOrStraddlePosting(...)`, `HoleDealing(...)`, `Folding(...)`, `CompletionBettingOrRaisingTo(...)`. Use this for hand-history dumps. |

### Streets

| Name | Type | Behavior |
|------|------|----------|
| `state.street_index` | `int | None` | 0=preflop, 1=flop, 2=turn, 3=river. **`None` after the hand ends.** |
| `state.street_count` | `int` | Total street count (4 for NLHE). |
| `state.street` | `Street` dataclass | Current street's config (burn/deal/draw spec). Mostly internal. |
| `state.streets` | tuple of `Street` | All four. |
| `state.street_indices` | `range` | `range(0, 4)`. |

There's no `state.street_name` enum — derive a name from `state.street_index` (`{0: "preflop", 1: "flop", 2: "turn", 3: "river"}`) or from `len(list(state.get_board_cards(0)))` (0=preflop, 3=flop, 4=turn, 5=river).

### Other useful attributes (not plan-asked but worth knowing)

- `state.player_indices` → `range(0, player_count)`.
- `state.player_count` → int, the configured count.
- `state.checking_or_calling_amount` → int, the cost to call (the amount your bet must be raised to match the high bet). 0 means a check is free.
- `state.actor_indices` → a `deque` of upcoming actor seats this street (don't iterate destructively).
- `state.deck`, `state.deck_cards` → remaining undealt deck. `state.deck_cards` is a `deque[Card]`. Useful for "draw a random card" if you'd rather not specify card identities yourself.
- `state.cards_in_play`, `state.cards_not_in_play`, `state.reserved_cards`, `state.discarded_cards` → exist; mostly internal.

---

## E. State legality query methods

All return `bool`. Verified by direct call.

| Method | Signature | Notes |
|--------|-----------|-------|
| `state.can_fold()` | `() -> bool` | True only when `actor_index is not None` AND folding is legal in current spot. |
| `state.can_check_or_call()` | `() -> bool` | True when an actor is up. Distinguish check vs call by `state.checking_or_calling_amount` (0 == check). |
| `state.can_complete_bet_or_raise_to(amount=None)` | `(amount: int | None = None) -> bool` | **Amount is OPTIONAL.** With no arg, returns True if any raise is legal at all. With an arg, returns True if that specific raise-to amount is legal. |
| `state.min_completion_betting_or_raising_to_amount` | **attribute** (NOT method) | `int | None`. The minimum legal raise-to total for the current actor. **`None` when no raise is legal** (e.g. all-in actor, hand over, all opponents already all-in). |
| `state.max_completion_betting_or_raising_to_amount` | **attribute** (NOT method) | `int | None`. Same shape; for NLHE this equals `actor_stack + actor_current_bet` (i.e. shove). `None` when no raise is legal. |

**Plan delta:** the plan may model `min_completion_betting_or_raising_to_amount` as a method (`()`). It is an **attribute**. Drop the parens.

Other related legality queries that exist (not in the plan but useful):
- `state.can_burn_card(card=None) -> bool`
- `state.can_deal_board(cards=None) -> bool`
- `state.can_deal_hole(cards=None, player_index=None) -> bool`
- `state.can_show_or_muck_hole_cards(...)`, `state.can_kill_hand(...)`, `state.can_win_now(player_index)`, etc.

---

## F. State action methods

All action methods accept an optional kwarg-only `commentary: str | None = None` (we don't use it). All return a typed `Operation` object describing what happened (and append it to `state.operations`).

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `state.fold()` | `(*, commentary=None)` | `Folding` | No args. |
| `state.check_or_call()` | `(*, commentary=None)` | `CheckingOrCalling` | No args. Picks check or call automatically based on `checking_or_calling_amount`. |
| `state.complete_bet_or_raise_to(amount)` | `(amount: int | None = None, *, commentary=None)` | `CompletionBettingOrRaisingTo` | **`amount` is the target TOTAL bet, not an increment.** E.g. with bets `[50, 100, 0, 0, 0, 0]`, calling `complete_bet_or_raise_to(300)` makes the actor's bet exactly 300 (increment of 200 if they had 100 in, 300 if they had 0). |
| `state.deal_hole(cards=None, player_index=None)` | `(cards: CardsLike | int | None = None, player_index: int | None = None, *, commentary=None)` | `HoleDealing` | **Defaults to the current `hole_dealee_index`** if `player_index` not supplied. **One Card → one card to that player.** Two-char string `"AsKs"` → both cards to the same player. **You can pass cards to a different player explicitly via `player_index=`.** Engine cycles dealee automatically. After all 12 holes are dealt, `hole_dealee_index → None` and `actor_index` becomes the UTG seat. |
| `state.deal_board(cards=None)` | `(cards: CardsLike | int | None = None, *, commentary=None)` | `BoardDealing` | **For flop, pass 3 cards in one call** like `deal_board("2d2h2s")` (engine knows the flop street wants 3). Turn/river take 1 card. The number expected per street is `state.board_dealing_count` after the burn happens. |
| `state.burn_card(card=None)` | `(card: CardsLike | None = None, *, commentary=None)` | `CardBurning` | **`card` is OPTIONAL** — pass `None` and the engine will burn from the top of the deck. If you pass a `Card`/string, the engine uses that exact card and emits a `UserWarning` if the card isn't ideally chosen (this is informational, not an error). Required before each post-preflop board deal because we exclude `Automation.CARD_BURNING`. |

**Important pre/post conditions:**
- `state.deal_hole(...)` cycles `hole_dealee_index` automatically. After 12 calls (6 players × 2 rounds, single-card or pair-card calls — the engine just totals them), `actor_index` becomes valid.
- After preflop action completes, `street_index` advances to 1, `actor_index` becomes `None`, and `can_burn_card()` becomes `True`. You must call `state.burn_card(...)` then `state.deal_board(...)` before flop action begins.
- After last (river) action completes, `street_index → None`, `status → False`, payoffs are populated, stacks are settled.

---

## G. Misc

### Validity / sanity check

- **No `state.is_valid()` method exists.** The closest analog is `state.status` (bool, True while hand active). The poker engine validates each action internally — bad calls raise (e.g. raising below `min_completion_betting_or_raising_to_amount` raises a `ValueError`). For "did the hand finish cleanly", check `state.status is False` AND `state.actor_index is None` AND `sum(state.payoffs) == 0` (zero-sum sanity).

### Street introspection

There's no `state.street_name` or "what street are we on" enum. Three reliable derivations:

```python
# Option 1: by street_index (works during action)
STREET_NAMES = {0: "preflop", 1: "flop", 2: "turn", 3: "river"}
street_name = STREET_NAMES.get(state.street_index, "complete")  # None -> "complete"

# Option 2: by board card count (works between hands too)
n_board = sum(len(slot) for slot in state.board_cards)
# 0->preflop, 3->flop, 4->turn, 5->river

# Option 3: also useful — flatten board 0:
board_flat = list(state.get_board_cards(0))   # [2d, 2h, 2s, Ts, Js] etc
```

### Surprises

- **`Card.parse()` returns a generator** (not a list/tuple). Always wrap in `list(...)` before indexing.
- **`str(card)` is verbose ("ACE OF SPADES (As)")**, **`repr(card)` is compact ("As")**. Reverse of typical Python.
- **`state.pots` is a generator AND empty during in-flight betting** (only populated after `BET_COLLECTION`). For a "pot size for the prompt" use `state.total_pot_amount` which always works.
- **`state.board_cards` is `list[list[Card]]`** (outer index = card slot, inner list = runout cards). Use `state.get_board_cards(0)` to flatten.
- **`min_completion_betting_or_raising_to_amount` is an ATTRIBUTE**, not a method. No parens. Returns `None` when raising is illegal — guard before reading.
- **`state.deal_hole(card)` deals exactly the cards passed**, defaulting to the current `hole_dealee_index`. If you supply a 2-char string like `"AsKs"`, both cards go to the same player. If you supply 1-char-each over 12 calls, the engine cycles seats.
- **`state.burn_card(card)` may emit `UserWarning`** if the chosen card is "not recommended" (e.g. duplicates a card already accounted for). Suppress or ignore — it's informational.

---

## Plan deltas (concrete)

These are the actionable adjustments T6-T9 implementers must make. **Skim this section first before coding.**

1. **Use `repr(card)` (or `f"{card!r}"`) for compact card strings, NOT `str(card)`.**
   - `str(card) == "ACE OF SPADES (As)"`; `repr(card) == "As"`.
   - Anywhere the plan writes `str(c) for c in state.hole_cards[i]`, change to `repr(c)` or `f"{c!r}"`.

2. **`Card.parse(text)` returns a generator. Wrap in `list(...)` before indexing.**
   - Plan code like `card = Card.parse("As")` will get a generator, not a Card. Use `card = next(Card.parse("As"))` or `cards = list(Card.parse("AsKh"))`.
   - Better: `state.deal_hole("As")` accepts the string directly via `CardsLike` — skip explicit Card construction entirely in the engine driver.

3. **Use `state.total_pot_amount` for pot size in prompts. NOT `state.pots[0].amount`.**
   - `state.pots` is a generator. `state.pots[0]` raises `TypeError`. And it's empty during betting windows.
   - `total_pot_amount` is an int and always correct (collected pots + in-flight bets).

4. **Use `list(state.get_board_cards(0))` for the flat community-card list.**
   - `state.board_cards` is `list[list[Card]]` (multi-runout container). `state.community_cards` does not exist.
   - For a single-runout NLHE hand, `[c for slot in state.board_cards for c in slot]` also works.

5. **`state.is_actor_required` does not exist. Use `state.actor_index is not None`.**
   - Same predicate, but you have to check the index directly.

6. **`min_completion_betting_or_raising_to_amount` and `max_...` are ATTRIBUTES, not methods.**
   - Drop the parens. Read as `state.min_completion_betting_or_raising_to_amount`.
   - Both are `int | None`. Guard with `if state.min_completion_betting_or_raising_to_amount is not None:` before using.

7. **`state.deal_hole()` cycles dealees one card at a time by default.**
   - To deal a full preflop, call `state.deal_hole(card_str)` 12 times, one card per call. The engine maintains `hole_dealee_index` and rotates it. After the 12th call, `hole_dealee_index → None` and `actor_index` becomes the UTG seat.
   - Alternative: call `state.deal_hole("AsKs", player_index=0)` to give both cards to seat 0 in one shot (and so on). Pick one approach and use it consistently.

8. **Burn before each post-preflop board deal.**
   - Because we exclude `Automation.CARD_BURNING`, T6/T7's engine driver must call `state.burn_card(None)` (or with a specified card) before each `state.deal_board(...)` for flop/turn/river. `state.can_burn_card()` returns True when a burn is required.
   - Passing `state.burn_card(None)` is safest — engine picks from the top of the deck and avoids the "card not recommended" warning.

9. **`state.statuses` (per-seat bool) ≠ `state.status` (whole-hand bool).**
   - Don't confuse the two. `status` (singular) = is hand still in progress; `statuses` (plural) = per-seat "still in hand" (False after fold).

10. **`state.street_index` becomes `None` when the hand ends.**
    - Don't access integer arithmetic on it without guarding. Same for `actor_index`.

11. **No `state.is_valid()`. Use `state.status is False and state.actor_index is None` as a "hand resolved cleanly" check.**

12. **`Automation` member names all match the plan exactly.** No renames needed. Just import `from pokerkit import Automation` and use `Automation.HOLE_DEALING` etc.

13. **All `create_state` kwargs match the plan exactly.** Use the canonical call in section C verbatim.

---

## Minimal working example

Self-contained Python snippet that constructs a 6-max NLHE state, manually deals 12 hole cards from a list, manages preflop action, deals the flop (burn + 3 cards), and prints per-seat hole cards. Verified to run cleanly under `.venv/bin/python`.

```python
"""MWE: 6-max NLHE 50/100, manual deal flow, no automation of cards."""
from pokerkit import Automation, NoLimitTexasHoldem

state = NoLimitTexasHoldem.create_state(
    automations=(
        Automation.ANTE_POSTING,
        Automation.BET_COLLECTION,
        Automation.BLIND_OR_STRADDLE_POSTING,
        Automation.HAND_KILLING,
        Automation.CHIPS_PUSHING,
        Automation.CHIPS_PULLING,
    ),
    ante_trimming_status=False,
    raw_antes=0,
    raw_blinds_or_straddles=(50, 100),  # SB, BB
    min_bet=100,
    raw_starting_stacks=10000,           # 100bb each
    player_count=6,
)

# Deal 12 hole cards: one per seat, two passes. The engine cycles `hole_dealee_index`.
hole_cards = ["As", "Kh", "Qd", "Jc", "Tc", "9s",
              "8d", "7h", "6c", "5s", "4d", "3h"]
for c in hole_cards:
    state.deal_hole(c)

# After 12 deals, dealing is done and action is open to UTG (seat 2).
assert state.actor_index == 2, f"expected UTG (seat 2), got {state.actor_index}"
assert state.hole_dealee_index is None

# Print per-seat hole cards (use repr for compact form, NOT str).
for seat in state.player_indices:
    cards = state.hole_cards[seat]
    print(f"  seat {seat}: {[repr(c) for c in cards]}")
# Expected:
#   seat 0: ['As', '8d']
#   seat 1: ['Kh', '7h']
#   seat 2: ['Qd', '6c']
#   seat 3: ['Jc', '5s']
#   seat 4: ['Tc', '4d']
#   seat 5: ['9s', '3h']

# Preflop: everyone calls.
while state.actor_index is not None:
    state.check_or_call()

# Burn + flop. (Burn required because CARD_BURNING is not automated.)
assert state.can_burn_card()
state.burn_card()                  # let engine pick from top of deck
state.deal_board("2d2h2s")          # 3 cards in one call

# Pot size for prompts:
print("flop pot:", state.total_pot_amount)             # -> 600
print("flop board (flat):", list(state.get_board_cards(0)))  # -> [2d, 2h, 2s]
print("street:", state.street_index)                    # -> 1 (flop)
```

This MWE has been executed end-to-end and produces the expected output. If a downstream T6/T7 implementer hits any other API mismatch not covered here, escalate before guessing.

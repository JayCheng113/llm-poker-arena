# Decision-type deep dive — flagship 102-hand session

Distilled from the same `runs/demo-6llm-flagship/` data the [Live demo](https://jaycheng113.github.io/llm-poker-arena/?session=demo-6llm-flagship) renders, but bucketed so the per-LLM **style** falls out instead of drowning in 1,069 individual decisions. Source: [`scripts/analyze_decision_types.py`](../scripts/analyze_decision_types.py).

## VPIP by position

Voluntary money in pot, broken out by seat-relative position. BTN / CO are the cheapest spots to enter; UTG / HJ are the most expensive. A model that opens too wide from UTG bleeds chips; a model that folds too tight on the BTN misses easy pots.

| LLM | UTG | HJ | CO | BTN | SB | BB |
|---|---|---|---|---|---|---|
| claude-sonnet-4-6 | 22% (4/18) | 33% (6/18) | 50% (9/18) | 47% (8/17) | 24% (4/17) | 21% (3/14) |
| deepseek-chat | 6% (1/18) | 21% (4/19) | 28% (5/18) | 28% (5/18) | 18% (3/17) | 7% (1/14) |
| gpt-5.4-mini | 24% (4/17) | 44% (8/18) | 44% (8/18) | 47% (8/17) | 47% (8/17) | 35% (6/17) |
| qwen3.6-plus | 12% (2/17) | 12% (2/17) | 33% (6/18) | 47% (9/19) | 18% (3/17) | 29% (5/17) |
| kimi-k2.5 | 0% (0/17) | 18% (3/17) | 12% (2/17) | 12% (2/17) | 24% (4/17) | 35% (6/17) |
| gemini-2.5-flash | 6% (1/17) | 12% (2/17) | 22% (4/18) | 18% (3/17) | 18% (3/17) | 19% (3/16) |

## Behavior by pot type

How each LLM acts depending on whether the pot is heads-up (2 players), multi-way (3+), or already had a 3-bet preflop (=both players show real strength). Combine across all post-flop streets. Reading: which actions does each LLM reach for in which spots?

### Heads Up

| LLM | Action distribution |
|---|---|
| claude-sonnet-4-6 | n=120 fold:54% check:8% call:3% bet:12% raise_to:23% |
| deepseek-chat | n=113 fold:75% check:9% call:10% bet:1% raise_to:5% |
| gpt-5.4-mini | n=148 fold:41% check:11% call:18% bet:12% raise_to:18% |
| qwen3.6-plus | n=125 fold:58% check:17% call:14% bet:2% raise_to:9% |
| kimi-k2.5 | n=103 fold:77% check:2% call:8% bet:4% raise_to:9% all_in:1% |
| gemini-2.5-flash | n=100 fold:77% check:5% call:6% bet:4% raise_to:8% |

### Multi Way

| LLM | Action distribution |
|---|---|
| claude-sonnet-4-6 | n=19 fold:26% check:42% call:16% bet:16% |
| deepseek-chat | n=21 fold:14% check:33% call:19% bet:29% raise_to:5% |
| gpt-5.4-mini | n=13 fold:31% check:23% call:8% bet:31% raise_to:8% |
| qwen3.6-plus | n=22 fold:23% check:27% call:32% bet:9% raise_to:5% all_in:5% |
| kimi-k2.5 | n=16 fold:56% check:6% call:25% bet:6% raise_to:6% |
| gemini-2.5-flash | n=17 fold:47% check:35% call:6% bet:12% |

### 3Bet Pot

| LLM | Action distribution |
|---|---|
| claude-sonnet-4-6 | n=11 fold:18% check:9% call:27% bet:36% raise_to:9% |
| deepseek-chat | n=9 fold:22% check:11% call:22% bet:44% |
| gpt-5.4-mini | n=14 fold:29% check:14% call:43% bet:14% |
| qwen3.6-plus | n=10 fold:40% check:10% call:40% bet:10% |
| kimi-k2.5 | n=4 fold:100% |
| gemini-2.5-flash | n=7 fold:57% call:14% raise_to:14% all_in:14% |

## Behavior by street

Same model, different streets. Look for the LLM whose fold rate spikes on the river (= can't bluff-catch) or whose bet rate spikes on the flop (= mandatory c-bet bot).

### Preflop

| LLM | Action distribution |
|---|---|
| claude-sonnet-4-6 | n=102 fold:65% check:2% call:7% raise_to:26% |
| deepseek-chat | n=104 fold:80% check:2% call:12% raise_to:6% |
| gpt-5.4-mini | n=104 fold:57% check:3% call:15% raise_to:25% |
| qwen3.6-plus | n=105 fold:69% check:6% call:17% raise_to:9% |
| kimi-k2.5 | n=102 fold:81% check:1% call:7% bet:1% raise_to:9% all_in:1% |
| gemini-2.5-flash | n=102 fold:82% check:2% call:7% bet:1% raise_to:8% |

### Flop

| LLM | Action distribution |
|---|---|
| claude-sonnet-4-6 | n=29 fold:10% check:21% call:10% bet:52% raise_to:7% |
| deepseek-chat | n=16 fold:12% check:44% call:12% bet:25% raise_to:6% |
| gpt-5.4-mini | n=34 fold:15% check:24% call:26% bet:35% |
| qwen3.6-plus | n=25 fold:24% check:28% call:28% bet:16% raise_to:4% |
| kimi-k2.5 | n=13 fold:46% check:8% call:31% bet:15% |
| gemini-2.5-flash | n=13 fold:23% check:31% call:8% bet:23% raise_to:8% all_in:8% |

### Turn

| LLM | Action distribution |
|---|---|
| claude-sonnet-4-6 | n=13 fold:23% check:62% bet:15% |
| deepseek-chat | n=17 fold:24% check:35% call:12% bet:29% |
| gpt-5.4-mini | n=25 fold:16% check:24% call:12% bet:44% raise_to:4% |
| qwen3.6-plus | n=15 fold:13% check:53% call:20% raise_to:13% |
| kimi-k2.5 | n=7 fold:43% check:14% bet:29% raise_to:14% |
| gemini-2.5-flash | n=6 fold:17% check:50% bet:33% |

### River

| LLM | Action distribution |
|---|---|
| claude-sonnet-4-6 | n=6 check:33% bet:67% |
| deepseek-chat | n=6 fold:17% check:50% bet:33% |
| gpt-5.4-mini | n=12 fold:8% check:42% call:42% bet:8% |
| qwen3.6-plus | n=12 fold:8% check:58% call:8% bet:17% all_in:8% |
| kimi-k2.5 | n=1 call:100% |
| gemini-2.5-flash | n=3 fold:33% check:67% |

## Response to ≥ half-pot bets (postflop only)

When a non-trivial bet (≥ half pot, post-flop) lands in front of them, what do they do? High fold % = exploitable / nit; high call % = calling station; high raise = aggressive.

| LLM | Fold | Call | Raise | n |
|---|---|---|---|---|
| claude-sonnet-4-6 | 60% | 40% | 0% | 5 |
| deepseek-chat | 50% | 33% | 17% | 6 |
| gpt-5.4-mini | 43% | 50% | 7% | 14 |
| qwen3.6-plus | 33% | 58% | 8% | 12 |
| kimi-k2.5 | 56% | 33% | 11% | 9 |
| gemini-2.5-flash | 75% | 25% | 0% | 4 |

## Auto-generated takeaways

- **Position discipline** (BTN−UTG VPIP gap): widest is qwen3.6-plus (+36pp), narrowest is kimi-k2.5 (+12pp). A wider gap means the model adjusts entry frequency to position; a narrow or negative gap means it plays the same range everywhere.
- **Bluff-resistance** (call+raise rate vs ≥ half-pot bets): stickiest is qwen3.6-plus (folds only 33%), most exploitable to big bets is kimi-k2.5 (folds 56%). The latter is the obvious bluff target; the former is who you only bet for value.
- **Multi-way comfort**: in 3+ player pots kimi-k2.5 folds 56% of the time vs deepseek-chat's 14%. Higher fold% is correct equity-wise (multi-way realizes less), but extreme tightness leaves money on the table when other seats keep checking down.
- **River bluff-catching**: claude-sonnet-4-6 folds the river only 0% (n=6, most willing to call thin), deepseek-chat folds 17% (n=6, rarely defends rivers). In a vacuum the catcher loses to polarized betting and wins vs bluffs; the avoider is the opposite. 4 of 6 seats reached the n≥6 threshold — treat as directional.
- **3-bet pot aggression**: claude-sonnet-4-6 keeps barreling (45% bet-or-raise in 3-bet pots) while kimi-k2.5 shuts down (0%). Sample sizes are small (3-bet pots are rare in this lineup) — read as directional, not statistically significant.

---

*Generated by `scripts/analyze_decision_types.py` from `runs/demo-6llm-flagship/`. Re-run after every new tournament to refresh.*
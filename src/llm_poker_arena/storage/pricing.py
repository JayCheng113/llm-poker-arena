"""Per-(provider, model) USD pricing table for cost estimation in meta.json.

Prices are USD per 1M tokens, sampled 2026-04-27 from each provider's
official pricing page. Update PRICE_TABLE_VERSION when refreshed so
analysts can detect drift.

Each entry is a 4-tuple: (input, output, cache_read, cache_creation).
- `input` = per-1M input tokens (cache miss)
- `output` = per-1M output tokens
- `cache_read` = per-1M cache hit / cache read tokens (Anthropic ephemeral
   cache reads, DeepSeek "cache hit", OpenAI cached input). 0.0 means the
   provider doesn't support a cache discount on this model.
- `cache_creation` = per-1M cache write / 5-minute cache creation tokens
   (Anthropic only). 0.0 elsewhere.

Source notes (codex P1 2026-04-27 review caught the prior table being
2-3× off in places — Opus 4.7 was 15/75 should be 5/25, Gemini 2.5 Flash
was 0.075/0.30 should be 0.30/2.50, etc.):
  - Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
  - OpenAI:    https://developers.openai.com/api/docs/pricing
  - DeepSeek:  https://api-docs.deepseek.com/quick_start/pricing
  - Qwen:      https://www.alibabacloud.com/help/en/model-studio/model-pricing
               (cross-checked against https://tokenmix.ai/blog/qwen-3-6-plus-review-benchmark-pricing-2026)
  - Kimi:      https://platform.kimi.ai/docs/pricing/chat
  - Gemini:    https://ai.google.dev/pricing  (paid tier, ≤200k input)
  - Grok:      https://docs.x.ai/developers/models
"""

from __future__ import annotations

PRICE_TABLE_VERSION = "2026-04-27b"

# (input_per_M, output_per_M, cache_read_per_M, cache_creation_per_M)
_TABLE: dict[str, tuple[float, float, float, float]] = {
    # --- Anthropic ---
    # cache_read = 10% of input, cache_creation (5m) = 1.25× input.
    "anthropic:claude-haiku-4-5":   (1.00,  5.00,  0.10,  1.25),
    "anthropic:claude-sonnet-4-6":  (3.00, 15.00,  0.30,  3.75),
    "anthropic:claude-sonnet-4-5":  (3.00, 15.00,  0.30,  3.75),
    "anthropic:claude-opus-4-7":    (5.00, 25.00,  0.50,  6.25),  # was 15/75 (codex P1)
    "anthropic:claude-opus-4-6":    (5.00, 25.00,  0.50,  6.25),
    "anthropic:claude-opus-4-1":    (15.00, 75.00, 1.50, 18.75),  # legacy 4.1 still at old prices

    # --- OpenAI (gpt-5.x family uses max_completion_tokens; pricing same shape) ---
    # cache_read = 10% of input across the 5.x line.
    "openai:gpt-5.4-mini":          (0.75,  4.50,  0.075, 0.0),
    "openai:gpt-5.4":               (2.50, 15.00,  0.25,  0.0),  # was 3.00 input (codex P1)
    "openai:gpt-5.5":               (5.00, 30.00,  0.50,  0.0),
    "openai:gpt-4o-mini":           (0.15,  0.60,  0.075, 0.0),
    "openai:gpt-4o":                (2.50, 10.00,  1.25,  0.0),

    # --- DeepSeek (legacy chat alias = v4-flash non-thinking) ---
    # cache hit ≈ 1/10 of cache miss for the V4 line (codex P1: was 10× too high).
    "deepseek:deepseek-chat":       (0.14,  0.28,  0.014, 0.0),
    "deepseek:deepseek-reasoner":   (0.14,  0.28,  0.014, 0.0),  # legacy alias
    "deepseek:deepseek-v4-flash":   (0.14,  0.28,  0.014, 0.0),
    "deepseek:deepseek-v4-pro":     (0.435, 0.87,  0.0044, 0.0),

    # --- Qwen (DashScope OpenAI-compat endpoint) ---
    "qwen:qwen3.6-plus":            (0.28,  0.66,  0.0,   0.0),  # was 0.325/1.95 (off)
    "qwen:qwen3.5-flash":           (0.10,  0.40,  0.0,   0.0),
    "qwen:qwen3-max":               (0.78,  3.90,  0.0,   0.0),  # was 1.04/4.16 (off)
    # Two-tier on DashScope: ≤128K = $1.30/$7.80, 128K-256K = $2/$12.
    # Our turn-level input never approaches 128K (a session history
    # caps ~50K), so we ship the lower tier. Revise if context > 128K.
    "qwen:qwen3.6-max-preview":     (1.30,  7.80,  0.0,   0.0),

    # --- Kimi (Moonshot) ---
    "kimi:kimi-k2.5":               (0.60,  2.50,  0.10,  0.0),  # was 0.44/2.00 (low)
    "kimi:kimi-k2.6":               (0.60,  2.50,  0.10,  0.0),

    # --- Google Gemini (AI Studio OpenAI-compat shim, paid tier ≤200k) ---
    "gemini:gemini-2.5-flash":      (0.30,  2.50,  0.075, 0.0),  # was 0.075/0.30 (way off)
    "gemini:gemini-2.5-pro":        (1.25, 10.00,  0.125, 0.0),
    "gemini:gemini-3-flash":        (0.50,  3.00,  0.125, 0.0),  # was 0.10/0.40 (off)
    "gemini:gemini-3.1-pro":        (2.00, 12.00,  0.20,  0.0),

    # --- xAI Grok (codex P1: missing entirely from prior table) ---
    "grok:grok-4.20-beta-2":        (2.00,  6.00,  0.0,   0.0),
    "grok:grok-4.1-fast":           (0.20,  0.50,  0.0,   0.0),
    "grok:grok-4":                  (3.00, 15.00,  0.0,   0.0),

    # --- OpenRouter (multi-vendor gateway). Model id is the vendor-
    # prefixed form OpenRouter exposes, e.g. "google/gemini-3.1-pro-
    # preview". OpenRouter quotes "the same as the underlying provider"
    # for these flagship models, so the rates here mirror Vertex AI's
    # native gemini-3.1-pro pricing ($2/$12).
    "openrouter:google/gemini-3.1-pro-preview": (2.00, 12.00, 0.0, 0.0),
}


def estimate_cost_usd(
    seat_assignment: dict[int, str],
    total_tokens_per_seat: dict[int, dict[str, int]],
) -> dict[str, object]:
    """Build the meta.estimated_cost_breakdown dict.

    Returns:
        {
          "price_table_version": "...",
          "total_usd": float,
          "per_seat": {
            "<seat>": {
              "agent": "anthropic:claude-haiku-4-5",
              "input_tokens": int,
              "output_tokens": int,
              "cache_read_input_tokens": int,
              "cache_creation_input_tokens": int,
              "input_usd": float,
              "output_usd": float,
              "cache_read_usd": float,
              "cache_creation_usd": float,
              "total_usd": float,
              "priced": bool,           # False if model not in table
            }
          }
        }
    """
    out: dict[str, object] = {
        "price_table_version": PRICE_TABLE_VERSION,
        "total_usd": 0.0,
        "per_seat": {},
    }
    total = 0.0
    per_seat: dict[str, dict[str, object]] = {}
    for seat, agent in seat_assignment.items():
        toks = total_tokens_per_seat.get(seat, {}) or {}
        inp = int(toks.get("input_tokens", 0) or 0)
        outp = int(toks.get("output_tokens", 0) or 0)
        cache_r = int(toks.get("cache_read_input_tokens", 0) or 0)
        cache_w = int(toks.get("cache_creation_input_tokens", 0) or 0)
        # cache_read + cache_creation are charged separately (NOT a subset
        # of input tokens — Anthropic reports them as siblings).
        if agent in _TABLE:
            p_in, p_out, p_cache_r, p_cache_w = _TABLE[agent]
            input_usd = inp / 1e6 * p_in
            output_usd = outp / 1e6 * p_out
            cache_r_usd = cache_r / 1e6 * p_cache_r
            cache_w_usd = cache_w / 1e6 * p_cache_w
            row_total = input_usd + output_usd + cache_r_usd + cache_w_usd
            priced = True
        else:
            input_usd = output_usd = cache_r_usd = cache_w_usd = row_total = 0.0
            priced = False
        per_seat[str(seat)] = {
            "agent": agent,
            "input_tokens": inp,
            "output_tokens": outp,
            "cache_read_input_tokens": cache_r,
            "cache_creation_input_tokens": cache_w,
            "input_usd": round(input_usd, 6),
            "output_usd": round(output_usd, 6),
            "cache_read_usd": round(cache_r_usd, 6),
            "cache_creation_usd": round(cache_w_usd, 6),
            "total_usd": round(row_total, 6),
            "priced": priced,
        }
        total += row_total
    out["per_seat"] = per_seat
    out["total_usd"] = round(total, 6)
    return out

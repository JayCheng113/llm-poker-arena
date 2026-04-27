"""Per-(provider, model) USD pricing table for cost estimation in meta.json.

Prices are USD per 1M tokens, sampled April 2026. Update PRICE_TABLE_VERSION
when refreshed so consumers can detect drift.

Source links per provider are in USAGE.md "Provider notes" section.
"""

from __future__ import annotations

PRICE_TABLE_VERSION = "2026-04-27"

# Each entry: (input_per_M_USD, output_per_M_USD, cache_read_per_M_USD)
# cache_read price is for Anthropic-style ephemeral cache reads; other
# providers ignore the third element (we only ever use it for Anthropic).
_TABLE: dict[str, tuple[float, float, float]] = {
    # Anthropic
    "anthropic:claude-haiku-4-5":   (1.00, 5.00, 0.10),
    "anthropic:claude-sonnet-4-6":  (3.00, 15.00, 0.30),
    "anthropic:claude-opus-4-7":    (15.00, 75.00, 1.50),
    # OpenAI (GPT-5 family uses max_completion_tokens; pricing same shape)
    "openai:gpt-5.4-mini":          (0.75, 4.50, 0.0),
    "openai:gpt-5.4":               (3.00, 15.00, 0.0),
    "openai:gpt-5.5":               (5.00, 30.00, 0.0),
    "openai:gpt-4o-mini":           (0.15, 0.60, 0.0),
    "openai:gpt-4o":                (2.50, 10.00, 0.0),
    # DeepSeek (legacy chat alias = v4-flash non-thinking)
    "deepseek:deepseek-chat":       (0.27, 1.10, 0.027),
    "deepseek:deepseek-reasoner":   (0.55, 2.19, 0.055),
    "deepseek:deepseek-v4-flash":   (0.14, 0.28, 0.028),
    "deepseek:deepseek-v4-pro":     (0.435, 0.87, 0.04),
    # Qwen (DashScope OpenAI-compat endpoint)
    "qwen:qwen3.6-plus":            (0.325, 1.95, 0.0),
    "qwen:qwen3.5-flash":           (0.10, 0.40, 0.0),
    "qwen:qwen3-max":               (1.04, 4.16, 0.0),
    # Kimi (Moonshot)
    "kimi:kimi-k2.5":               (0.44, 2.00, 0.0),
    "kimi:kimi-k2.6":               (0.60, 2.40, 0.0),
    # Google Gemini (AI Studio OpenAI-compat shim)
    "gemini:gemini-2.5-flash":      (0.075, 0.30, 0.0),
    "gemini:gemini-2.5-pro":        (1.25, 10.00, 0.0),
    "gemini:gemini-3-flash":        (0.10, 0.40, 0.0),
    "gemini:gemini-3.1-pro":        (2.00, 12.00, 0.0),
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
              "input_usd": float,
              "output_usd": float,
              "cache_read_usd": float,
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
        cache = int(toks.get("cache_read_input_tokens", 0) or 0)
        # cache_read tokens are charged separately (NOT a subset of input
        # tokens — Anthropic reports them as siblings).
        if agent in _TABLE:
            p_in, p_out, p_cache = _TABLE[agent]
            input_usd = inp / 1e6 * p_in
            output_usd = outp / 1e6 * p_out
            cache_usd = cache / 1e6 * p_cache
            row_total = input_usd + output_usd + cache_usd
            priced = True
        else:
            input_usd = output_usd = cache_usd = row_total = 0.0
            priced = False
        per_seat[str(seat)] = {
            "agent": agent,
            "input_tokens": inp,
            "output_tokens": outp,
            "cache_read_input_tokens": cache,
            "input_usd": round(input_usd, 6),
            "output_usd": round(output_usd, 6),
            "cache_read_usd": round(cache_usd, 6),
            "total_usd": round(row_total, 6),
            "priced": priced,
        }
        total += row_total
    out["per_seat"] = per_seat
    out["total_usd"] = round(total, 6)
    return out

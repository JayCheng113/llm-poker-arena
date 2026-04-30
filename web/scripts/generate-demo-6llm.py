#!/usr/bin/env python3
"""Generate the 6-LLM showdown — every seat is a different provider.

Recipe:
  - seat 0: Claude Haiku 4.5            (Anthropic)
  - seat 1: deepseek-chat               (DeepSeek, non-thinking alias)
  - seat 2: gpt-5.4-mini                (OpenAI)
  - seat 3: qwen3.6-plus                (Alibaba Qwen via DashScope)
  - seat 4: kimi-k2.5                   (Moonshot Kimi)
  - seat 5: gemini-2.5-flash            (Google AI Studio, OpenAI-compat shim)
  - Hands: 30 (default; --hands 6 for smoke)
  - Seed: 23 (different from demo-tournament=17 to give a fresh deal)
  - max_total_tokens=2_000_000 ($2 budget cap; with 6 LLMs costs grow ~50%
    over the 4-LLM tournament so we lift the ceiling).

All six models are picked from the same "small/fast" tier (Anthropic
Haiku, OpenAI mini, Google Flash, etc.) so the showdown compares
similar-capability models rather than mixing flagship vs. budget.

Usage:
  .venv/bin/python web/scripts/generate-demo-6llm.py            # 30 hands
  .venv/bin/python web/scripts/generate-demo-6llm.py --hands 6  # smoke
"""
# ruff: noqa: E402 — sys.path + .env loader must run before src/ imports
import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

# Manual .env loader (no python-dotenv dep)
_env_file = _REPO / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

from llm_poker_arena.agents.llm.llm_agent import LLMAgent
from llm_poker_arena.agents.llm.prompt_profile import (
    load_default_prompt_profile,
    with_overrides,
)
from llm_poker_arena.agents.llm.providers.registry import (
    PROVIDERS,
    make_provider,
    resolved_temperature,
)
from llm_poker_arena.engine.config import SessionConfig
from llm_poker_arena.session.session import Session

# OpenAI's GPT-5 family + o-series are reasoning-model lines whose
# moderation + system-prompt safety check rejects "first write reasoning"
# framing with `invalid_prompt`. The first 6-LLM tournament censored
# hand 13 on seat 2 (gpt-5.4-mini) for exactly this reason —
# codex 2026-04-27. Workaround: these models get rationale_required=False,
# letting them rely on their built-in reasoning instead of an explicit
# text block.
#
# Prefix-based instead of an exhaustive list (codex P1 follow-up):
# `gpt-5.4-mini`, `gpt-5-nano`, `gpt-5.1`, `gpt-5.2-codex`, future
# `gpt-5*`/`gpt-6*` — same family, same moderation behavior. An exact
# allow-list silently regresses the moment a new variant ships.
_NO_RATIONALE_PREFIXES = ("gpt-5", "gpt-6", "o1", "o3", "o4")


def _is_no_rationale_model(model: str) -> bool:
    return any(model.startswith(p) for p in _NO_RATIONALE_PREFIXES)

# Six providers, one seat each — sourced from the registry so adding a
# provider there auto-extends the env-key check.
#
# Two named lineups to date:
#   - "mini" (default): the cost-balanced "small/fast" tier across the
#     six provider families. Shipped as `demo-6llm` on Pages.
#   - "flagship": single-variable change — Anthropic's seat upgraded
#     from Haiku 4.5 to Sonnet 4.6 to test whether Sonnet's stronger
#     decision-making narrows the gap with the field. The other five
#     seats stay at the mini-tier model so any P&L delta isolates the
#     Anthropic-side change. Shipped as `demo-6llm-flagship`.
LINEUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "mini": (
        ("anthropic", "claude-haiku-4-5"),       # seat 0
        ("deepseek", "deepseek-chat"),           # seat 1
        ("openai", "gpt-5.4-mini"),              # seat 2
        ("qwen", "qwen3.6-plus"),                # seat 3
        ("kimi", "kimi-k2.5"),                   # seat 4
        ("gemini", "gemini-2.5-flash"),          # seat 5
    ),
    "flagship": (
        ("anthropic", "claude-sonnet-4-6"),      # seat 0 — upgraded
        ("deepseek", "deepseek-chat"),           # seat 1 — same
        ("openai", "gpt-5.4-mini"),              # seat 2 — same
        ("qwen", "qwen3.6-plus"),                # seat 3 — same
        ("kimi", "kimi-k2.5"),                   # seat 4 — same
        ("gemini", "gemini-2.5-flash"),          # seat 5 — same
    ),
    # All-flagship: every seat uses each provider's strongest currently-
    # available model. Cost projection (2026-04-29 smokes): ~$11/100hands
    # base, $16-27 realistic. Gemini routes through OpenRouter because
    # gemini-3.1-pro lives on Vertex AI (no AI Studio OpenAI-compat
    # support) and OpenRouter wraps it without GCP setup overhead.
    "flagship-all": (
        ("anthropic", "claude-opus-4-7"),                      # seat 0
        ("deepseek", "deepseek-v4-pro"),                       # seat 1
        ("openai", "gpt-5.5"),                                 # seat 2
        ("qwen", "qwen3.6-max-preview"),                       # seat 3
        ("kimi", "kimi-k2.6"),                                 # seat 4
        ("openrouter", "google/gemini-3.1-pro-preview"),       # seat 5
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hands", type=int, default=30,
                        help="hands to play (must be multiple of 6; default 30)")
    parser.add_argument("--out", default="demo-6llm",
                        help="session id / output dir name")
    parser.add_argument(
        "--lineup", choices=tuple(LINEUPS), default="mini",
        help="seat lineup preset (default 'mini' = the cost-balanced "
             "small/fast tier across all 6 providers; 'flagship' upgrades "
             "the Anthropic seat to claude-sonnet-4-6 to test stronger-"
             "model decision quality at the same field).",
    )
    parser.add_argument(
        "--max-tokens-cap", type=int, default=2_000_000,
        help="SessionConfig.max_total_tokens (USD-equivalent budget cap; "
             "default 2,000,000 ≈ $0.83 with the mini lineup, ≈ $1.7 with "
             "flagship). 100-hand flagship runs need ~8M.",
    )
    parser.add_argument(
        "--replace-seat", action="append", default=[], metavar="SEAT=AGENT",
        help="Replace one of the LLM seats with a non-LLM agent. SEAT is "
             "the seat index (0–5); AGENT is 'exploit' (per-opponent "
             "ExploitBotAgent) or 'rule_based' (generic TAG bot). The "
             "replaced seat skips its provider's API key check. Repeatable. "
             "Used for the falsification experiment in "
             "docs/llm-decision-profile.md.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="overwrite existing runs/<out>/ and web/public/data/<out>/. "
             "Without this flag the script aborts if either dir exists, "
             "so a $1+ tournament run is not silently nuked.",
    )
    parser.add_argument(
        "--seed", type=int, default=23,
        help="SessionConfig.rng_seed (deck shuffle + button rotation). "
             "Default 23 matches the historical demo runs; use a fresh "
             "value for OUT-OF-SAMPLE pilots (the exploit rules in "
             "ExploitBotAgent were derived from seed=23, so re-using it "
             "would be in-sample overfit).",
    )
    args = parser.parse_args()

    if args.hands % 6 != 0:
        sys.exit(f"--hands ({args.hands}) must be a multiple of 6 (6 players)")

    # Parse --replace-seat 5=exploit into {5: 'exploit'}.
    replacements: dict[int, str] = {}
    for spec in args.replace_seat:
        if "=" not in spec:
            sys.exit(f"--replace-seat must be SEAT=AGENT, got {spec!r}")
        seat_str, agent_kind = spec.split("=", 1)
        seat_idx = int(seat_str)
        if not 0 <= seat_idx < 6:
            sys.exit(f"--replace-seat seat must be 0–5, got {seat_idx}")
        if agent_kind not in ("exploit", "rule_based"):
            sys.exit(f"--replace-seat agent must be 'exploit' or 'rule_based', got {agent_kind!r}")
        replacements[seat_idx] = agent_kind

    seat_lineup = LINEUPS[args.lineup]
    # Skip the env-key check for replaced seats (their provider isn't called).
    required_env = tuple(
        PROVIDERS[tag].env_var
        for i, (tag, _) in enumerate(seat_lineup)
        if i not in replacements
    )
    for k in required_env:
        if not os.environ.get(k):
            sys.exit(f"{k} not set; check .env")

    # Pre-flight 4: refuse to clobber an existing run unless --force.
    # Why: the prior behaviour was a silent shutil.rmtree before each run,
    # which once cost a 30-hand 6-LLM tournament to a typo'd --out arg.
    session_dir = _REPO / "runs" / args.out
    web_target = _REPO / "web" / "public" / "data" / args.out
    for dir_to_check in (session_dir, web_target):
        if dir_to_check.exists() and not args.force:
            sys.exit(
                f"refusing to overwrite existing {dir_to_check}\n"
                f"pass --force to delete it, or pick a new --out name."
            )

    cfg = SessionConfig(
        num_players=6, starting_stack=10_000, sb=50, bb=100,
        num_hands=args.hands, max_utility_calls=5,
        enable_math_tools=True,
        enable_hud_tool=True,
        rationale_required=True,
        opponent_stats_min_samples=10,
        rng_seed=args.seed,
        max_total_tokens=args.max_tokens_cap,
    )

    # Pre-flight 2 (rev): timeout geometry math.
    #   MAX_API_RETRY=2 ⇒ 3 wait_for(per_iter_timeout) calls
    #   per_iter_timeout = 60s (LLMAgent default)
    #   inter-retry backoff ≈ 0.5–1.0s × 2 sleeps
    # Worst case before total_turn_timeout fires: 3*60 + 2*1 = 182s.
    # 180s (the LLMAgent default) RACES this and would false-positive
    # TotalTurnTimeout exactly when a 3rd retry was about to succeed —
    # codex P0 finding before the 30-hand official tournament.
    # 200s gives ~18s of headroom for OS / network jitter.
    # Kimi keeps a wider envelope because per-call latency p95 is ~45s
    # (observed during smoke), so any retry burns most of one window.
    NORMAL_TIMEOUT = 200.0
    SLOW_TIMEOUT = 260.0
    SLOW_PROVIDERS = {"kimi"}  # observed to need extra headroom

    # codex 2nd-pass: Gemini gets sdk_max_retries=5 (registry.py) so the
    # AsyncOpenAI client backs off through ~30s of 503 spike before
    # surfacing the error. That entire backoff burns inside ONE
    # asyncio.wait_for(per_iteration_timeout) wrap. Default 60s is too
    # tight: SDK backoff caps at 8s/step, but 503 + Retry-After header
    # + slow refresh can push a single SDK call past 60s. Bump just
    # this seat's per-iteration timeout to 90s so the SDK gets to
    # finish its retry budget without the outer wrap pulling the rug.
    GEMINI_PER_ITER_TIMEOUT = 90.0

    base_profile = load_default_prompt_profile()

    # ExploitBot needs to know each opponent's model identity so it can
    # route per-target rules. Build the map once from seat_lineup before
    # we start instantiating agents.
    opponent_models = {i: model for i, (_, model) in enumerate(seat_lineup)}

    agents = []
    for i, (provider_tag, model) in enumerate(seat_lineup):
        # Replacement seats skip the LLM entirely.
        if i in replacements:
            kind = replacements[i]
            if kind == "exploit":
                from llm_poker_arena.agents.exploit_bot import (
                    ExploitBotAgent,
                    ExploitTargets,
                )
                # Pass identities of the OTHER 5 seats (the bot itself
                # isn't an opponent of itself).
                targets = ExploitTargets(
                    by_seat={s: m for s, m in opponent_models.items() if s != i}
                )
                agents.append(ExploitBotAgent(targets=targets))
            elif kind == "rule_based":
                from llm_poker_arena.agents.rule_based import RuleBasedAgent
                agents.append(RuleBasedAgent())
            else:
                sys.exit(f"unknown replacement kind: {kind}")
            continue

        api_key = os.environ[PROVIDERS[provider_tag].env_var]
        timeout = SLOW_TIMEOUT if provider_tag in SLOW_PROVIDERS else NORMAL_TIMEOUT
        # GPT-5 reasoning models reject explicit chain-of-thought framing.
        # Override their profile to skip the rationale text and rely on
        # the model's built-in reasoning. Other seats keep the default.
        if _is_no_rationale_model(model):
            profile = with_overrides(base_profile, rationale_required=False)
        else:
            profile = base_profile
        agent_kwargs: dict[str, Any] = {
            "provider": make_provider(provider_tag, model, api_key),
            "model": model,
            # resolved_temperature pins kimi:kimi-k2.5 to 1.0; every
            # other (provider, model) pair gets the requested 0.7.
            "temperature": resolved_temperature(provider_tag, 0.7, model=model),
            "total_turn_timeout_sec": timeout,
            "prompt_profile": profile,
        }
        # See GEMINI_PER_ITER_TIMEOUT comment above for rationale.
        if provider_tag == "gemini":
            agent_kwargs["per_iteration_timeout_sec"] = GEMINI_PER_ITER_TIMEOUT
        agents.append(LLMAgent(**agent_kwargs))

    if session_dir.exists():
        shutil.rmtree(session_dir)

    sess = Session(config=cfg, agents=agents, output_dir=session_dir,
                   session_id=args.out)
    asyncio.run(sess.run())

    if web_target.exists():
        shutil.rmtree(web_target)
    web_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(session_dir, web_target)

    # Pre-flight 12: auto-rebuild the web manifest so the new session is
    # immediately picked up by the picker without a separate bundle step.
    # No-op (with a warning) if node isn't installed — the artifacts are
    # already on disk and the user can run `node web/scripts/bundle-demos.mjs`
    # later by hand.
    bundle_script = _REPO / "web" / "scripts" / "bundle-demos.mjs"
    try:
        subprocess.run(["node", str(bundle_script)], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"warning: manifest rebuild skipped ({e}); "
              f"run `node {bundle_script}` manually.", file=sys.stderr)

    print(f"6-LLM session generated (lineup={args.lineup}):")
    print(f"  runs/{args.out}/")
    print(f"  web/public/data/{args.out}/")


if __name__ == "__main__":
    main()

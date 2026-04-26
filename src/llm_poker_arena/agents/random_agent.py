"""RandomAgent: uniform sampling over legal actions. Deterministic in turn_seed."""

from __future__ import annotations

import random

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.agents.llm.types import TokenCounts, TurnDecisionResult
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.views import PlayerView


class RandomAgent(Agent):
    """Uniform-random pick among legal tools; reproducible under view.turn_seed."""

    async def decide(self, view: PlayerView) -> TurnDecisionResult:
        rng = random.Random(view.turn_seed)
        tools = view.legal_actions.tools
        if not tools:
            action = Action(tool_name="fold", args={})
        else:
            spec = rng.choice(tools)
            if spec.name in ("bet", "raise_to"):
                bounds = spec.args["amount"]
                mn, mx = int(bounds["min"]), int(bounds["max"])
                action = Action(tool_name=spec.name, args={"amount": rng.randint(mn, mx)})
            else:
                action = Action(tool_name=spec.name, args={})
        return TurnDecisionResult(
            iterations=(),
            final_action=action,
            total_tokens=TokenCounts.zero(),
            wall_time_ms=0,
            api_retry_count=0,
            illegal_action_retry_count=0,
            no_tool_retry_count=0,
            tool_usage_error_count=0,
            default_action_fallback=False,
            api_error=None,
            turn_timeout_exceeded=False,
        )

    def provider_id(self) -> str:
        return "random:uniform"

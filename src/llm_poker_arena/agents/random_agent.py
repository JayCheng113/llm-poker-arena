"""RandomAgent: uniform sampling over legal actions. Deterministic in turn_seed."""
from __future__ import annotations

import random

from llm_poker_arena.agents.base import Agent
from llm_poker_arena.engine.legal_actions import Action
from llm_poker_arena.engine.views import PlayerView


class RandomAgent(Agent):
    """Uniform-random pick among legal tools; reproducible under view.turn_seed."""

    def decide(self, view: PlayerView) -> Action:
        rng = random.Random(view.turn_seed)
        tools = view.legal_actions.tools
        if not tools:
            # Should never happen if view is well-formed; guard anyway.
            return Action(tool_name="fold", args={})

        spec = rng.choice(tools)
        if spec.name in ("bet", "raise_to"):
            bounds = spec.args["amount"]
            mn, mx = int(bounds["min"]), int(bounds["max"])
            amt = rng.randint(mn, mx)
            return Action(tool_name=spec.name, args={"amount": amt})
        return Action(tool_name=spec.name, args={})

    def provider_id(self) -> str:
        return "random:uniform"

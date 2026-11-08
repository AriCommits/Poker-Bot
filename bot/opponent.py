"""Conservative counts of actions actually visible to the bot."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from game import Action, Observation


@dataclass
class OpponentModel:
    counts: Counter = field(default_factory=Counter)
    hand_index: int | None = None
    history_seen: int = 0

    def observe(self, obs: Observation) -> None:
        if self.hand_index != obs.hand_index:
            self.hand_index = obs.hand_index
            self.history_seen = 0
        for action in obs.action_history[self.history_seen:]:
            if not action.is_me:
                self.counts[(action.street, action.action)] += 1
        self.history_seen = len(obs.action_history)

    def raise_rate(self, street, prior: int) -> float:
        raises = sum(self.counts[(street, a)] for a in (Action.RAISE_HALF, Action.RAISE_POT))
        total = sum(self.counts[(street, a)] for a in Action)
        return (raises + prior * 0.5) / (total + prior) if total + prior else 0.5

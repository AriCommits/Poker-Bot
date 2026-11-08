"""Conservative local accounting; the judge's actual remaining bank is unknown."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class TimeBudget:
    total: float
    hands: int
    reserve: float
    per_decision_cap: float
    decisions_per_hand: float
    call_overhead: float = 0.0
    clock: Callable[[], float] = time.perf_counter
    spent: float = 0.0

    def record(self, start: float, overhead: float = 0.0) -> None:
        self.spent += max(0.0, self.clock() - start) + max(0.0, overhead)

    def allowance(self, hand_index: int) -> float:
        available = max(0.0, self.total - self.reserve - self.spent)
        remaining = max(1, self.hands - hand_index)
        share = available / (remaining * max(1.0, self.decisions_per_hand))
        return min(self.per_decision_cap, max(0.0, share - self.call_overhead))

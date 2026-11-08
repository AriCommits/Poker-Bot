"""Profile local strategy time; this does not reproduce judge network charges."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["POKER_TIME_BUDGET"] = "1"
os.environ["POKER_ADAPTIVE_SAMPLING"] = "1"
started = time.perf_counter()
import agent
from game import Action, AgentConfig, Game, make_deal
startup = time.perf_counter() - started


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hands", type=int, default=1000)
    parser.add_argument("--seed", default="profile")
    args = parser.parse_args()
    if args.hands < 1:
        parser.error("hands must be positive")
    memory = {}
    agent.new_half(AgentConfig(num_hands=args.hands), memory)
    timings = {}
    for i in range(args.hands):
        game = Game(make_deal(args.seed, i), button_seat=i % 2, hand_index=i)
        while not game.is_terminal:
            obs = game.observation(game.to_act)
            if game.to_act == 0:
                start = time.perf_counter()
                action = agent.choose_action(obs, memory)
                timings.setdefault(obs.street.name, []).append(time.perf_counter() - start)
            else:
                action = Action.CHECK_CALL
            game.apply(action)
        agent.on_hand_end(game.hand_result(0), memory)
    report = {street: {"calls": len(values), "mean_ms": statistics.mean(values) * 1000,
                       "max_ms": max(values) * 1000} for street, values in timings.items()}
    print(json.dumps({"startup_seconds": startup, "local_spent_seconds": memory["budget"].spent,
                      "budget_fallbacks": memory.get("budget_fallbacks", 0), "streets": report}, indent=2))


if __name__ == "__main__":
    main()

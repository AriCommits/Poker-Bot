"""Evaluate preflop predictions on independent random showdown outcomes."""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluator import omaha_score, warmup
from bot.tables import lookup_preflop_equity, parse_preflop_table


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--baseline", type=Path, default=ROOT / "data" / "preflop_equity.json")
    parser.add_argument("--hands", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=12345)
    args = parser.parse_args()
    if args.hands < 1:
        parser.error("hands must be positive")
    candidate_raw = json.loads(args.candidate.read_text())
    if candidate_raw.get("seed") == args.seed:
        parser.error("validation seed must differ from generation seed")
    tables = [parse_preflop_table(json.loads(p.read_text())) for p in (args.baseline, args.candidate)]
    sums = [0.0, 0.0, 0.0]
    rng = random.Random(args.seed)
    warmup()
    for _ in range(args.hands):
        cards = rng.sample(range(36), 15)
        a, b, board = cards[:5], cards[5:10], cards[10:]
        sa, sb = omaha_score(a, board), omaha_score(b, board)
        for hand, utility in ((a, 1.0 if sa > sb else 0.5 if sa == sb else 0.0),
                              (b, 1.0 if sb > sa else 0.5 if sa == sb else 0.0)):
            predictions = [lookup_preflop_equity(hand, table=t) for t in tables] + [0.5]
            for i, prediction in enumerate(predictions):
                sums[i] += (prediction - utility) ** 2
    print(json.dumps({"seed": args.seed, "hands": args.hands,
                      "mean_squared_error": dict(zip(("baseline", "candidate", "global_prior"),
                                                       (s / (2 * args.hands) for s in sums)))}, indent=2))


if __name__ == "__main__":
    main()

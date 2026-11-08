#!/usr/bin/env python3
"""Build a coarse preflop equity dictionary via Monte Carlo self-play samples.

Usage (from poker-bot/):
    python scripts/build_preflop_table.py --hands 20000 --seed 7 --out data/preflop_candidate.json

Writes data/preflop_equity.json mapping feature_key → estimated equity.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluator import NUM_CARDS, omaha_score, warmup  # noqa: E402
from bot.features import extract_features, feature_key  # noqa: E402


def deal_hand(rng: random.Random) -> tuple[list[int], list[int], list[int]]:
    deck = list(range(NUM_CARDS))
    rng.shuffle(deck)
    return deck[0:5], deck[5:10], deck[10:15]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hands", type=int, default=20000, help="random matchups to simulate")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--prior-count", type=float, default=50.0,
                        help="pseudo-observations shrinking each bucket toward 0.5")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "preflop_candidate.json",
    )
    args = parser.parse_args()
    if args.hands < 1 or args.prior_count < 0:
        parser.error("hands must be positive and prior-count nonnegative")

    warmup()
    rng = random.Random(args.seed)
    wins: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)

    for _ in range(args.hands):
        h0, h1, board = deal_hand(rng)
        s0 = omaha_score(h0, board)
        s1 = omaha_score(h1, board)
        if s0 > s1:
            u0, u1 = 1.0, 0.0
        elif s0 < s1:
            u0, u1 = 0.0, 1.0
        else:
            u0 = u1 = 0.5

        for hole, utility in ((h0, u0), (h1, u1)):
            key = feature_key(extract_features(hole))
            wins[key] += utility
            counts[key] += 1

    table = {"schema_version": 1, "feature_version": 1, "deck": "short-deck-36-plo5",
             "hands": args.hands, "seed": args.seed, "prior": 0.5,
             "prior_count": args.prior_count,
             "buckets": {key: {"count": counts[key], "utility": wins[key],
                               "equity": round((wins[key] + args.prior_count * 0.5) /
                                               (counts[key] + args.prior_count), 6)}
                         for key in sorted(counts)}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {len(counts)} keys from {args.hands} hands to {args.out}")


if __name__ == "__main__":
    main()

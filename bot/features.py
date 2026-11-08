"""Fast hole-card feature extraction for Short Deck PLO5 preflop lookups."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from evaluator import ACE, card_rank, card_suit


@dataclass(frozen=True)
class HoleFeatures:
    """Compact preflop descriptors used as dictionary keys / score inputs."""

    pair_count: int          # number of distinct paired ranks (0-2 typical)
    max_pair_rank: int       # highest paired rank, or -1
    suited_count: int        # max cards of one suit (2-5)
    double_suited: bool      # at least two suits with 2+ cards each
    connectedness: int       # how well ranks form rundowns (0-10-ish)
    high_card_points: int    # sum of top ranks (A=8 ... 6=0), skewed to highs
    ace_count: int
    bare_aces: int           # aces not part of a pair
    unique_ranks: int
    score: int               # single integer strength used for bucket lookup


def _connectedness(ranks: list[int]) -> int:
    """Reward rundowns / wrap potential. Ace can play low (as -1 beside 6)."""
    uniq = sorted(set(ranks))
    # Also consider ace-low wheel connectivity (A-6-7-8-9).
    extended = list(uniq)
    if ACE in uniq:
        extended.append(-1)  # ace as below six
        extended = sorted(set(extended))

    best_run = 1
    run = 1
    for i in range(1, len(extended)):
        gap = extended[i] - extended[i - 1]
        if gap == 1:
            run += 1
            best_run = max(best_run, run)
        elif gap == 2:
            run = max(1, run)  # one-gap still useful in PLO
            best_run = max(best_run, run + 1)
            run = 1
        else:
            run = 1

    # Pairwise closeness bonus.
    close_pairs = 0
    for i, r in enumerate(uniq):
        for s in uniq[i + 1:]:
            if abs(s - r) <= 2:
                close_pairs += 1
            if ACE in (r, s) and min(r, s) <= 1:  # A with 6/7
                close_pairs += 1

    return best_run * 2 + close_pairs


def extract_features(hole_cards: list[int] | tuple[int, ...]) -> HoleFeatures:
    """Compute cheap features from five hole cards."""
    ranks = [card_rank(c) for c in hole_cards]
    suits = [card_suit(c) for c in hole_cards]

    rank_counts = Counter(ranks)
    suit_counts = Counter(suits)

    pairs = [(r, n) for r, n in rank_counts.items() if n >= 2]
    pair_count = len(pairs)
    max_pair_rank = max((r for r, _ in pairs), default=-1)

    suited_count = max(suit_counts.values()) if suit_counts else 0
    double_suited = sum(1 for n in suit_counts.values() if n >= 2) >= 2

    connectedness = _connectedness(ranks)
    high_card_points = sum(sorted(ranks, reverse=True)[:3])
    ace_count = rank_counts.get(ACE, 0)
    bare_aces = ace_count if ACE not in {r for r, _ in pairs} else max(0, ace_count - 2)
    unique_ranks = len(rank_counts)

    # Heuristic score → later mapped to approximate equity via lookup table.
    score = 0
    score += pair_count * 12
    if max_pair_rank >= 0:
        score += max_pair_rank * 2
    # Trips / quads in hand are rare and strong for PLO5 (still need board help).
    for _, n in pairs:
        if n >= 3:
            score += 18
    score += max(0, suited_count - 1) * 6
    if double_suited:
        score += 8
    score += connectedness * 3
    score += high_card_points
    score += ace_count * 5
    score += bare_aces * 2
    # Prefer more unique ranks for wrap potential unless we have pairs.
    if pair_count == 0:
        score += max(0, unique_ranks - 3) * 2

    return HoleFeatures(
        pair_count=pair_count,
        max_pair_rank=max_pair_rank,
        suited_count=suited_count,
        double_suited=double_suited,
        connectedness=connectedness,
        high_card_points=high_card_points,
        ace_count=ace_count,
        bare_aces=bare_aces,
        unique_ranks=unique_ranks,
        score=score,
    )


def feature_key(feat: HoleFeatures) -> str:
    """Coarse dictionary key for preflop equity lookups."""
    pair_bucket = min(feat.pair_count, 2)
    suit_bucket = 3 if feat.suited_count >= 3 else (2 if feat.suited_count == 2 else 1)
    conn_bucket = min(feat.connectedness // 3, 4)
    high_bucket = min(feat.high_card_points // 8, 4)
    ace_bucket = min(feat.ace_count, 2)
    ds = 1 if feat.double_suited else 0
    return f"p{pair_bucket}_s{suit_bucket}_c{conn_bucket}_h{high_bucket}_a{ace_bucket}_d{ds}"

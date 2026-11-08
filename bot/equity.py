"""Monte Carlo equity estimates for Short Deck 5-Card PLO."""

from __future__ import annotations

import random
import math
import time
from typing import Sequence

from evaluator import NUM_CARDS, omaha_score
from game import Street

from bot.config import BotConfig, DEFAULT_CONFIG


def _remaining_cards(dead: Sequence[int]) -> list[int]:
    dead_set = set(dead)
    return [c for c in range(NUM_CARDS) if c not in dead_set]


def estimate_equity(
    hole: Sequence[int],
    board: Sequence[int],
    street: Street,
    rng: random.Random,
    config: BotConfig = DEFAULT_CONFIG,
    opp_hole: Sequence[int] | None = None,
    deadline: float | None = None,
    thresholds: Sequence[float] = (),
    range_strength: float = 0.0,
) -> float:
    """Estimate P(win) + 0.5 * P(tie) vs a random opponent hand (or known hole).

    Uses a small sample count tuned for the tournament time bank. On the river
    with a full board, opponent hands are sampled without redealing the board.
    """
    board = list(board)
    hole = list(hole)
    n_board = len(board)
    dead_cards = hole + board + (list(opp_hole) if opp_hole is not None else [])
    if (len(hole) != 5 or n_board not in (0, 3, 4, 5)
            or (opp_hole is not None and len(opp_hole) != 5)
            or len(set(dead_cards)) != len(dead_cards)
            or any(card < 0 or card >= NUM_CARDS for card in dead_cards)):
        raise ValueError("invalid or duplicate cards")

    if street == Street.PREFLOP or n_board == 0:
        # Caller should prefer the preflop lookup table; this path is a fallback.
        samples = min(12, config.max_samples_per_decision)
    elif street == Street.FLOP or n_board == 3:
        samples = config.samples.flop
    elif street == Street.TURN or n_board == 4:
        samples = config.samples.turn
    else:
        samples = config.samples.river

    samples = max(1, min(samples, config.max_samples_per_decision))
    need_board = 5 - n_board

    rem = _remaining_cards(dead_cards)
    draw_count = need_board + (5 if opp_hole is None else 0)
    if len(rem) < draw_count:
        raise ValueError("not enough cards to complete the deal")
    total = squares = 0.0
    count = 0
    for _ in range(samples):
        if count and deadline is not None and time.perf_counter() >= deadline:
            break
        draw = rng.sample(rem, draw_count)
        if opp_hole is None:
            opp = draw[:5]
            fill = draw[5:]
            if range_strength > 0 and rng.random() < min(1.0, range_strength):
                # A bounded two-candidate proxy, deliberately experimental.
                from bot.features import extract_features
                other = rng.sample(rem, draw_count)
                if extract_features(other[:5]).score > extract_features(opp).score:
                    opp, fill = other[:5], other[5:]
        else:
            opp = list(opp_hole)
            fill = draw

        full_board = board + fill
        hero = omaha_score(hole, full_board)
        villain = omaha_score(opp, full_board)
        utility = 1.0 if hero > villain else 0.5 if hero == villain else 0.0
        total += utility
        squares += utility * utility
        count += 1
        if (config.adaptive_sampling and thresholds and count >= max(2, config.initial_samples)
                and count % max(1, config.sample_batch_size) == 0):
            mean = total / count
            variance = max(0.0, (squares - count * mean * mean) / (count - 1))
            # A small floor avoids false certainty after identical early outcomes.
            margin = 1.96 * math.sqrt(max(variance, 0.05) / count)
            if all(abs(mean - boundary) > margin for boundary in thresholds):
                break

    return total / count


def pot_odds(to_call: int, pot: int) -> float:
    """Fraction of the final pot you must win to break even on a call."""
    if to_call <= 0:
        return 0.0
    return to_call / (pot + to_call)


def required_equity(to_call: int, pot: int, edge: float = 0.0) -> float:
    """Pot odds plus an optional edge cushion."""
    return min(0.95, pot_odds(to_call, pot) * (1.0 + edge))

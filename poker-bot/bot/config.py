"""Tunable bot percentages and thresholds — edit here, not scattered in code."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class StreetSamples:
    """Monte Carlo sample counts per street (keep small for the 8s time bank)."""

    flop: int = 16
    turn: int = 24
    river: int = 40


@dataclass(frozen=True)
class EquityBuckets:
    """Equity cutoffs used when mapping strength → action mix.

    Values are win-probability in [0, 1]. Inclusive lower bounds for each label.
    """

    monster: float = 0.72
    strong: float = 0.58
    medium: float = 0.45
    weak: float = 0.32
    trash: float = 0.0


@dataclass(frozen=True)
class ActionMix:
    """Action frequencies for a strength bucket. Keys must sum roughly to 1.0.

    Missing keys are treated as 0. Only legal actions are sampled at decision time.
    """

    fold: float = 0.0
    check_call: float = 0.0
    raise_half: float = 0.0
    raise_pot: float = 0.0


@dataclass(frozen=True)
class BotConfig:
    """Central strategy config. Prefer changing these numbers over editing policy logic.

    Decision flow:
      1. Estimate equity (preflop lookup dict, or live Monte Carlo postflop).
      2. Compare equity to pot odds; fold when clearly behind required price.
      3. Sample a mixed action from the strength-bucket frequency table.
      4. Occasionally force a pot shove (all-in-ish) when equity is high enough.
    """

    # --- identity / RNG ---
    rng_seed: int = 42

    # --- Monte Carlo ---
    samples: StreetSamples = field(default_factory=StreetSamples)
    # Cap total MC work even if caller asks for more.
    max_samples_per_decision: int = 48
    adaptive_sampling: bool = False
    initial_samples: int = 8
    sample_batch_size: int = 4
    budget_enabled: bool = False
    budget_reserve_seconds: float = 2.0
    budget_call_overhead_seconds: float = 0.0008
    max_decision_seconds: float = 0.015
    expected_decisions_per_hand: float = 4.0
    opponent_model_enabled: bool = False
    opponent_prior_actions: int = 30

    # --- pot-odds / EV ---
    # Call if equity >= pot_odds * (1 + call_edge). Higher = tighter.
    call_edge: float = 0.04
    # Extra equity required above pot odds before we open-raise / value-bet.
    raise_edge: float = 0.08
    # Avoid folding cheap calls when estimated equity meets the required price.
    cheap_call_pot_fraction: float = 0.12

    # --- bluffing / mixing ---
    # Pure bluff rate when we have a free bet (to_call == 0) and weak equity.
    bluff_frequency: float = 0.06
    # Prefer half-pot over pot when bluffing this often (rest use pot).
    bluff_half_pot_share: float = 0.70
    # Semi-bluff: medium equity + draw-ish board → raise a bit more often.
    semi_bluff_bonus: float = 0.10

    # --- random all-in / pot shove ---
    # When equity >= all_in_equity_threshold, roll all_in_probability to jam pot.
    all_in_equity_threshold: float = 0.68
    forced_pot_raise_enabled: bool = True
    all_in_probability: float = 0.18
    # Also allow a tiny random pot shove with medium hands (chaos / cover).
    speculative_all_in_probability: float = 0.02
    speculative_all_in_min_equity: float = 0.48

    # --- preflop ---
    # If preflop lookup equity is below this and we face a raise, fold more.
    preflop_fold_equity: float = 0.38
    # Open / 3-bet more from the button.
    button_aggression_bonus: float = 0.05

    # --- strength buckets ---
    buckets: EquityBuckets = field(default_factory=EquityBuckets)

    # Mixed strategies keyed by bucket name. These are the "probability dictionaries"
    # the bot samples from after equity is estimated.
    mixes: dict[str, ActionMix] = field(default_factory=lambda: {
        "monster": ActionMix(fold=0.00, check_call=0.10, raise_half=0.25, raise_pot=0.65),
        "strong": ActionMix(fold=0.02, check_call=0.28, raise_half=0.40, raise_pot=0.30),
        "medium": ActionMix(fold=0.15, check_call=0.55, raise_half=0.22, raise_pot=0.08),
        "weak": ActionMix(fold=0.45, check_call=0.45, raise_half=0.08, raise_pot=0.02),
        "trash": ActionMix(fold=0.78, check_call=0.20, raise_half=0.02, raise_pot=0.00),
    })

    # Preflop feature → approximate equity lookup. Built/extended in tables.py.
    # Kept here as defaults so a single dataclass is the source of truth for knobs;
    # the full dict lives in data/preflop_equity.json and is merged at load time.
    preflop_equity_floor: float = 0.28
    preflop_equity_ceiling: float = 0.70

    def bucket_for_equity(self, equity: float) -> str:
        """Map a win probability to a named strength bucket."""
        b = self.buckets
        if equity >= b.monster:
            return "monster"
        if equity >= b.strong:
            return "strong"
        if equity >= b.medium:
            return "medium"
        if equity >= b.weak:
            return "weak"
        return "trash"

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable snapshot of the config."""
        return asdict(self)


DEFAULT_CONFIG = BotConfig()

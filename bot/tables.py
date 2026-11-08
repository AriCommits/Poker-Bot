"""Probability dictionaries for fast equity / action lookups."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from bot.config import BotConfig, DEFAULT_CONFIG
from bot.features import HoleFeatures, extract_features, feature_key

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PREFLOP_EQUITY_PATH = DATA_DIR / "preflop_equity.json"

@lru_cache(maxsize=1)
def load_preflop_equity_table() -> dict[str, float]:
    """Load situation → equity dictionary from JSON (empty dict if absent)."""
    if not PREFLOP_EQUITY_PATH.exists():
        return {"__prior__": 0.5}
    try:
        with PREFLOP_EQUITY_PATH.open() as f:
            raw = json.load(f)
        return parse_preflop_table(raw)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {"__prior__": 0.5}


def parse_preflop_table(raw: dict) -> dict[str, float]:
    """Accept the versioned artifact or the original float-only table."""
    if "schema_version" in raw:
        if raw["schema_version"] != 1 or raw.get("feature_version") != 1 or raw.get("deck") != "short-deck-36-plo5":
            raise ValueError("unsupported preflop artifact")
        values = {str(k): float(v["equity"]) for k, v in raw["buckets"].items()}
        values["__prior__"] = float(raw["prior"])
    else:
        values = {str(k): float(v) for k, v in raw.items()}
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in values.values()):
        raise ValueError("invalid equity")
    return values


def lookup_preflop_equity(
    hole_cards: list[int] | tuple[int, ...],
    config: BotConfig = DEFAULT_CONFIG,
    table: Mapping[str, float] | None = None,
) -> float:
    """Fast preflop equity estimate via feature-key dictionary lookup."""
    feat = extract_features(hole_cards)
    return lookup_preflop_equity_from_features(feat, config, table)


def lookup_preflop_equity_from_features(
    feat: HoleFeatures,
    config: BotConfig = DEFAULT_CONFIG,
    table: Mapping[str, float] | None = None,
) -> float:
    """Resolve equity from a feature key, falling back to the global prior."""
    tbl = table if table is not None else load_preflop_equity_table()
    key = feature_key(feat)
    if key in tbl:
        equity = tbl[key]
    else:
        equity = tbl.get("__prior__", 0.5)

    return max(config.preflop_equity_floor, min(config.preflop_equity_ceiling, equity))


def action_frequency_dict(config: BotConfig) -> dict[str, dict[str, float]]:
    """Expose bucket → action probability dictionaries for inspection / tooling."""
    return {
        name: {
            "fold": mix.fold,
            "check_call": mix.check_call,
            "raise_half": mix.raise_half,
            "raise_pot": mix.raise_pot,
        }
        for name, mix in config.mixes.items()
    }

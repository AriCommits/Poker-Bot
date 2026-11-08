"""Equity + mixed-strategy decision policy for Short Deck PLO5."""

from __future__ import annotations

import random
from typing import Sequence

from game import Action, Observation, Street

from bot.config import BotConfig, DEFAULT_CONFIG
from bot.equity import estimate_equity, pot_odds, required_equity
from bot.tables import load_preflop_equity_table, lookup_preflop_equity


_ACTION_ATTR = {
    Action.FOLD: "fold",
    Action.CHECK_CALL: "check_call",
    Action.RAISE_HALF: "raise_half",
    Action.RAISE_POT: "raise_pot",
}


def _estimate_hero_equity(
    obs: Observation,
    rng: random.Random,
    config: BotConfig,
    deadline: float | None = None,
    opponent=None,
) -> float:
    if obs.street == Street.PREFLOP or not obs.board:
        table = load_preflop_equity_table()
        equity = lookup_preflop_equity(obs.hole_cards, config, table)
        if obs.is_button:
            equity = min(0.72, equity + config.button_aggression_bonus * 0.5)
        return equity
    call = min(obs.to_call, obs.my_stack)
    need = required_equity(call, obs.pot, config.call_edge)
    boundaries = (config.buckets.weak, config.buckets.medium, config.buckets.strong,
                  config.buckets.monster, need, need + config.raise_edge)
    strength = 0.0
    if config.opponent_model_enabled and opponent is not None:
        opponent_raised = any(not a.is_me and a.street == obs.street and
                              a.action in (Action.RAISE_HALF, Action.RAISE_POT)
                              for a in obs.action_history)
        if opponent_raised:
            strength = max(0.0, 0.5 - opponent.raise_rate(obs.street, config.opponent_prior_actions))
    return estimate_equity(
        hole=obs.hole_cards,
        board=obs.board,
        street=obs.street,
        rng=rng,
        config=config,
        deadline=deadline,
        thresholds=boundaries,
        range_strength=strength,
    )


def _weights_for_bucket(
    bucket: str,
    legal: Sequence[Action],
    config: BotConfig,
    *,
    to_call: int,
) -> dict[Action, float]:
    mix = config.mixes.get(bucket, config.mixes["medium"])
    weights: dict[Action, float] = {}
    for action in legal:
        attr = _ACTION_ATTR[action]
        w = float(getattr(mix, attr, 0.0))
        # Can't fold when check is free — zero that weight if somehow present.
        if action == Action.FOLD and to_call <= 0:
            w = 0.0
        weights[action] = max(0.0, w)
    return weights


def _sample_action(weights: dict[Action, float], rng: random.Random, legal: Sequence[Action]) -> Action:
    total = sum(weights.values())
    if total <= 0:
        # Safe fallback: check/call if possible, else any legal action.
        if Action.CHECK_CALL in legal:
            return Action.CHECK_CALL
        return legal[0]
    roll = rng.random() * total
    acc = 0.0
    for action, w in weights.items():
        acc += w
        if roll < acc:
            return action
    return next(iter(weights))


def _maybe_all_in(
    equity: float,
    legal: Sequence[Action],
    rng: random.Random,
    config: BotConfig,
) -> Action | None:
    """Random pot shove when equity is high (or rare speculative jam)."""
    if Action.RAISE_POT not in legal:
        return None
    if equity >= config.all_in_equity_threshold and rng.random() < config.all_in_probability:
        return Action.RAISE_POT
    if (
        equity >= config.speculative_all_in_min_equity
        and rng.random() < config.speculative_all_in_probability
    ):
        return Action.RAISE_POT
    return None


def _apply_pot_odds_gate(
    equity: float,
    obs: Observation,
    weights: dict[Action, float],
    config: BotConfig,
) -> dict[Action, float]:
    """Tilt frequencies toward fold / call based on price vs equity."""
    # A short stack can call for less than the amount currently outstanding.
    to_call = min(obs.to_call, obs.my_stack)
    if to_call <= 0:
        return weights

    need = required_equity(to_call, obs.pot, config.call_edge)
    cheap = to_call <= max(obs.big_blind, int(obs.pot * config.cheap_call_pot_fraction))

    out = dict(weights)
    if equity + 1e-9 < need:
        # Too expensive: heavily prefer fold when legal.
        if Action.FOLD in out:
            for a in list(out):
                if a != Action.FOLD:
                    out[a] *= 0.15
            out[Action.FOLD] = max(out.get(Action.FOLD, 0.0), 0.85)
        # Remove raise weight when clearly behind.
        if Action.RAISE_HALF in out:
            out[Action.RAISE_HALF] *= 0.05
        if Action.RAISE_POT in out:
            out[Action.RAISE_POT] *= 0.02
    elif equity >= need + config.raise_edge:
        # Getting a good price with a strong hand: boost raises.
        if Action.RAISE_POT in out:
            out[Action.RAISE_POT] *= 1.5
        if Action.RAISE_HALF in out:
            out[Action.RAISE_HALF] *= 1.25
        if Action.FOLD in out:
            out[Action.FOLD] *= 0.25
    if cheap and equity + 1e-9 >= need and Action.FOLD in out:
        # A cheap call at a favorable price should not be folded by the mix.
        out[Action.FOLD] = 0.0
        if Action.CHECK_CALL in out:
            out[Action.CHECK_CALL] *= 1.3

    return out


def _maybe_bluff(
    equity: float,
    obs: Observation,
    weights: dict[Action, float],
    rng: random.Random,
    config: BotConfig,
) -> dict[Action, float]:
    """Small bluff / semi-bluff frequency when checking is free."""
    if obs.to_call > 0:
        return weights
    out = dict(weights)
    bucket = config.bucket_for_equity(equity)
    if bucket in ("trash", "weak") and rng.random() < config.bluff_frequency:
        if Action.RAISE_HALF in out and rng.random() < config.bluff_half_pot_share:
            out[Action.RAISE_HALF] = max(out.get(Action.RAISE_HALF, 0.0), 0.8)
            out[Action.CHECK_CALL] = 0.2
            if Action.RAISE_POT in out:
                out[Action.RAISE_POT] = 0.0
        elif Action.RAISE_POT in out:
            out[Action.RAISE_POT] = max(out.get(Action.RAISE_POT, 0.0), 0.8)
            out[Action.CHECK_CALL] = 0.2
    elif bucket == "medium":
        # Semi-bluff bump.
        if Action.RAISE_HALF in out:
            out[Action.RAISE_HALF] *= 1.0 + config.semi_bluff_bonus
        if Action.RAISE_POT in out:
            out[Action.RAISE_POT] *= 1.0 + config.semi_bluff_bonus * 0.5
    return out


def choose_action_from_obs(
    obs: Observation,
    memory: dict,
    config: BotConfig | None = None,
) -> Action:
    """Main decision entry: equity → bucket mix → pot-odds gate → sample."""
    cfg = config or memory.get("config") or DEFAULT_CONFIG
    rng: random.Random = memory.get("rng") or random.Random(cfg.rng_seed)
    memory["rng"] = rng

    legal = tuple(obs.legal_actions)
    if not legal:
        return Action.CHECK_CALL

    # Only one legal choice — take it.
    if len(legal) == 1:
        return legal[0]

    try:
        budget = memory.get("budget")
        deadline = None
        if cfg.budget_enabled and budget is not None:
            allowance = budget.allowance(obs.hand_index)
            if allowance <= 0:
                memory["budget_fallbacks"] = memory.get("budget_fallbacks", 0) + 1
                return Action.CHECK_CALL if obs.to_call <= 0 and Action.CHECK_CALL in legal else (
                    Action.FOLD if Action.FOLD in legal else legal[0])
            deadline = budget.clock() + allowance
        equity = _estimate_hero_equity(obs, rng, cfg, deadline, memory.get("opponent"))
    except Exception:
        # Never crash the match: fall back to check/call.
        return Action.CHECK_CALL if Action.CHECK_CALL in legal else legal[0]

    memory["last_equity"] = equity
    call_amount = min(obs.to_call, obs.my_stack)
    memory["last_pot_odds"] = pot_odds(call_amount, obs.pot)

    # Do not let a speculative pot raise bypass the price gate.
    can_force_raise = call_amount <= 0 or equity >= (
        required_equity(call_amount, obs.pot, cfg.call_edge) + cfg.raise_edge
    )
    jammed = _maybe_all_in(equity, legal, rng, cfg) if can_force_raise and cfg.forced_pot_raise_enabled else None
    if jammed is not None:
        return jammed

    bucket = cfg.bucket_for_equity(equity)
    memory["last_bucket"] = bucket

    weights = _weights_for_bucket(bucket, legal, cfg, to_call=obs.to_call)
    weights = _apply_pot_odds_gate(equity, obs, weights, cfg)
    weights = _maybe_bluff(equity, obs, weights, rng, cfg)

    # Keep only legal actions with positive weight after filters.
    weights = {a: w for a, w in weights.items() if a in legal and w > 0}
    action = _sample_action(weights, rng, legal)
    if action not in legal:
        return Action.CHECK_CALL if Action.CHECK_CALL in legal else legal[0]
    return action

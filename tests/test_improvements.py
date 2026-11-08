from dataclasses import replace
import random

import pytest

from bot.budget import TimeBudget
from bot.config import DEFAULT_CONFIG, StreetSamples
from bot.equity import estimate_equity
from bot.opponent import OpponentModel
from bot.policy import choose_action_from_obs
from bot.tables import parse_preflop_table, lookup_preflop_equity
from game import Action, ObservedAction, Street
from test_policy import _obs


def test_budget_reserve_and_remaining_hands():
    now = [10.0]
    budget = TimeBudget(8, 100, 2, 1, 2, clock=lambda: now[0])
    assert budget.allowance(0) == pytest.approx(0.03)
    now[0] += 1
    budget.record(10)
    assert budget.spent == 1
    assert budget.allowance(50) == pytest.approx(0.05)
    budget.spent = 6
    assert budget.allowance(50) == 0


def test_opponent_counts_only_new_visible_actions():
    model = OpponentModel()
    action = ObservedAction(Street.PREFLOP, False, Action.RAISE_POT, 5, 6)
    obs = _obs(action_history=(action,))
    model.observe(obs)
    model.observe(obs)
    assert model.counts[(Street.PREFLOP, Action.RAISE_POT)] == 1
    model.observe(_obs(hand_index=1, action_history=(action,)))
    assert model.counts[(Street.PREFLOP, Action.RAISE_POT)] == 2
    assert model.raise_rate(Street.PREFLOP, 30) == pytest.approx(17 / 32)


def test_versioned_preflop_prior_and_validation():
    raw = {"schema_version": 1, "feature_version": 1, "deck": "short-deck-36-plo5",
           "prior": 0.5, "buckets": {"unrelated": {"equity": 0.6}}}
    table = parse_preflop_table(raw)
    assert lookup_preflop_equity([0, 1, 2, 3, 4], table=table) == 0.5
    raw["prior"] = float("nan")
    with pytest.raises(ValueError):
        parse_preflop_table(raw)


def test_equity_seeded_and_known_opponent():
    cfg = replace(DEFAULT_CONFIG, adaptive_sampling=False, samples=StreetSamples(12, 12, 12))
    args = dict(hole=[0, 1, 2, 3, 4], board=[10, 11, 12, 13, 14],
                opp_hole=[5, 6, 7, 8, 9], street=Street.RIVER, config=cfg)
    a = estimate_equity(rng=random.Random(8), **args)
    b = estimate_equity(rng=random.Random(9), **args)
    assert a == b
    assert a in (0.0, 0.5, 1.0)


def test_equity_rejects_impossible_deal():
    # More than five board cards cannot produce a valid completion.
    with pytest.raises(ValueError):
        estimate_equity([0, 1, 2, 3, 4], list(range(5, 11)), Street.RIVER,
                        random.Random(0))
    with pytest.raises(ValueError):
        estimate_equity([0, 1, 2, 3, 4], [4, 5, 6], Street.FLOP, random.Random(0))


def test_exhausted_budget_returns_legal_fallback():
    budget = TimeBudget(1, 100, 1, 0.01, 2)
    memory = {"budget": budget, "rng": random.Random(2)}
    obs = _obs()
    config = replace(DEFAULT_CONFIG, budget_enabled=True)
    assert choose_action_from_obs(obs, memory, config) == Action.FOLD
    assert memory["budget_fallbacks"] == 1
    obs = _obs(to_call=0, legal_actions=(Action.CHECK_CALL, Action.RAISE_POT))
    assert choose_action_from_obs(obs, memory, config) == Action.CHECK_CALL


def test_forced_raise_can_be_disabled(monkeypatch):
    monkeypatch.setattr("bot.policy._estimate_hero_equity", lambda *args: 0.7)
    monkeypatch.setattr("bot.policy._maybe_all_in", lambda *args: pytest.fail("forced raise was called"))
    config = replace(DEFAULT_CONFIG, forced_pot_raise_enabled=False)
    obs = _obs()
    assert choose_action_from_obs(obs, {"rng": random.Random(0)}, config) in obs.legal_actions

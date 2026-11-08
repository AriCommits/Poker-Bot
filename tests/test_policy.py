"""Unit tests for the equity / mix policy (no HTTP server)."""

from __future__ import annotations

import random
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluator import warmup
from game import Action, Observation, Street

from bot.config import DEFAULT_CONFIG
from bot.features import extract_features, feature_key
from bot.policy import _apply_pot_odds_gate, _sample_action, choose_action_from_obs
from bot.tables import lookup_preflop_equity


@pytest.fixture(scope="module", autouse=True)
def _warm():
    warmup()


def _obs(**kwargs) -> Observation:
    base = dict(
        hand_index=0,
        street=Street.PREFLOP,
        hole_cards=(0, 4, 8, 12, 35),  # mixed junk + Ace
        board=(),
        pot=3,
        to_call=1,
        my_bet=1,
        opp_bet=2,
        my_stack=79,
        opp_stack=78,
        is_button=True,
        legal_actions=(Action.FOLD, Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT),
        raise_to={Action.RAISE_HALF: 4, Action.RAISE_POT: 6},
        min_raise_to=4,
        raises_this_street=0,
        action_history=(),
        big_blind=2,
    )
    base.update(kwargs)
    return Observation(**base)


def test_feature_key_stable():
    hole = [0, 1, 8, 12, 35]
    a = feature_key(extract_features(hole))
    b = feature_key(extract_features(hole))
    assert a == b
    assert a.startswith("p")


def test_preflop_equity_in_range():
    eq = lookup_preflop_equity([32, 33, 34, 35, 28], DEFAULT_CONFIG)  # strong-ish aces/kings
    assert 0.28 <= eq <= 0.70


def test_choose_action_always_legal():
    memory = {"rng": random.Random(0), "config": DEFAULT_CONFIG}
    for i in range(50):
        obs = _obs(hand_index=i)
        action = choose_action_from_obs(obs, memory, DEFAULT_CONFIG)
        assert action in obs.legal_actions


def test_free_check_never_folds():
    memory = {"rng": random.Random(1), "config": DEFAULT_CONFIG}
    obs = _obs(
        to_call=0,
        my_bet=0,
        opp_bet=0,
        pot=6,
        legal_actions=(Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT),
        street=Street.FLOP,
        board=(1, 10, 20),
    )
    for _ in range(30):
        action = choose_action_from_obs(obs, memory, DEFAULT_CONFIG)
        assert action != Action.FOLD
        assert action in obs.legal_actions


def test_profitable_cheap_call_has_no_fold_weight():
    obs = _obs(to_call=1, pot=20)
    weights = {Action.FOLD: 0.45, Action.CHECK_CALL: 0.45}
    result = _apply_pot_odds_gate(0.4, obs, weights, DEFAULT_CONFIG)
    assert result[Action.FOLD] == 0
    assert result[Action.CHECK_CALL] > 0


def test_short_stack_uses_actual_call_amount():
    obs = _obs(to_call=20, my_stack=2, pot=20)
    weights = {Action.FOLD: 0.45, Action.CHECK_CALL: 0.45}
    result = _apply_pot_odds_gate(0.2, obs, weights, DEFAULT_CONFIG)
    assert result[Action.FOLD] == 0


def test_forced_raise_respects_call_price(monkeypatch):
    monkeypatch.setattr("bot.policy._estimate_hero_equity", lambda *args: 0.48)
    cfg = replace(DEFAULT_CONFIG, speculative_all_in_probability=1.0)
    obs = _obs(to_call=90, pot=100, my_stack=100)
    memory = {"rng": random.Random(0)}
    # The gate leaves a small raise chance, but it must not force a pot raise.
    assert choose_action_from_obs(obs, memory, cfg) != Action.RAISE_POT


def test_zero_weight_is_not_selected_at_zero_roll():
    class ZeroRng:
        def random(self):
            return 0.0

    weights = {Action.FOLD: 0.0, Action.CHECK_CALL: 1.0}
    assert _sample_action(weights, ZeroRng(), tuple(weights)) == Action.CHECK_CALL

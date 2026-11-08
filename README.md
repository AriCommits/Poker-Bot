# Poker Bot — Short Deck 5-Card Pot-Limit Omaha

Heads-up Short Deck (36-card) 5-Card Pot-Limit Omaha bot for the TAMU Datathon Poker Bot Challenge.

Built on the official [heads-up-bundle](https://github.com/tamu-datathon-org/heads-up-bundle) starter.

## Strategy overview

1. **Preflop** — cheap feature extraction → dictionary lookup (`data/preflop_equity.json`).
2. **Postflop** — Monte Carlo equity vs a random opponent hand. Budget-limited and adaptive sampling are available as experiments.
3. **Decisions** — compare equity to pot odds, then sample from **action-frequency dictionaries** by strength bucket.
4. **Pot raises** — a configurable random chance can force a pot-sized raise when equity clears the price gate. A pot raise is all-in only when the stack is small enough; `forced_pot_raise_enabled` can disable this separate rule for experiments.

Call pricing uses the amount the bot can actually put in when short-stacked.
The experimental local budget tracks bot-controlled time and reserves headroom; it cannot read
the judge's remaining bank or account exactly for network and server overhead.
The equity estimates are approximate and assume a random opponent; favorable
pot odds alone do not guarantee a profitable decision against every range.

All tunable percentages live in one place: `bot/config.py` (`BotConfig` dataclass).

## Layout

| Path | Role |
|------|------|
| `agent.py` | Tournament entrypoint (edit strategy hooks only) |
| `bot/config.py` | **`BotConfig` dataclass** — thresholds, mixes, all-in rates |
| `bot/features.py` | Preflop hole-card features |
| `bot/tables.py` | Probability dictionary loaders / lookups |
| `bot/equity.py` | Adaptive Monte Carlo equity + pot odds |
| `bot/budget.py` | Conservative local time budget |
| `bot/opponent.py` | Observed opponent actions and experimental range model |
| `bot/policy.py` | Action selection |
| `data/preflop_equity.json` | Precomputed feature → equity table |
| `game.py` / `evaluator.py` | Official rules + hand evaluator (don't rely on local edits in tournament) |

## Quick start

```bash
cd poker-bot
pip install -r requirements.txt

# Generate an experimental table and validate it with a different seed.
# The active preflop_equity.json is not overwritten by this command.
python3 scripts/build_preflop_table.py --hands 30000 --seed 71
python3 tools/validate_preflop_table.py data/preflop_candidate.json --hands 30000 --seed 137

# unit tests for the policy
python3 -m pytest -q tests/test_policy.py test_agent.py

# local match (3 terminals)
python3 agent.py
python3 baseline-bots/baseline_random.py
python3 judge_engine.py --deals 100 --seed 7

# Compare complete committed and working-tree snapshots; each run is saved separately.
python3 tools/benchmark_changes.py --baseline-ref HEAD --deals 1000 --seeds 101 103
# Ablate one candidate at a time (save separate runs).
python3 tools/benchmark_changes.py --candidate-table data/preflop_candidate.json
python3 tools/benchmark_changes.py --candidate-opponent-model
python3 tools/benchmark_changes.py --candidate-disable-forced-raise
python3 tools/benchmark_changes.py --candidate-time-budget --candidate-adaptive-sampling
```

## Knobs to tweak first

In `bot/config.py`:

- `mixes` — fold/call/raise frequencies per equity bucket
- `all_in_equity_threshold` / `all_in_probability` — random pot shoves
- `bluff_frequency` — free-bet bluffs
- `call_edge` / `raise_edge` — pot-odds tightness
- `samples` — MC count per street (keep low; time bank is 8s / 1000 hands)
- `budget_reserve_seconds` and `max_decision_seconds` — conservative time headroom
- `opponent_model_enabled` — experimental, off by default until match-tested

Time budgeting and adaptive sampling are also off by default pending clean
full-length validation. Set `POKER_TIME_BUDGET=1` and
`POKER_ADAPTIVE_SAMPLING=1` to try them. `POKER_OPPONENT_MODEL=1` enables the
experimental opponent model, and `POKER_DISABLE_FORCED_RAISE=1` disables the
separate forced-raise rule.

The versioned candidate preflop artifact records counts and shrinks each bucket
toward 50% equity. It is not the active table until it passes both held-out
calibration and clean match comparisons. Benchmark confidence intervals are
approximate; compare held-out seeds and investigate all skipped calls.

## Submission note

The tournament expects a **public** repo whose root contains `agent.py`. This project currently lives under the `hackathons` monorepo as `poker-bot/`. For official submission, publish this folder as its own public GitHub repository (or copy it out) and submit that URL + commit SHA.

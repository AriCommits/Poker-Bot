# Plan 1: Reliable Equity and Adaptive Poker Strategy

## Summary

Improve the short-deck five-card Omaha bot through measured, independently switchable changes: protect its per-half time budget and spend simulations where decisions need them; rebuild and validate its preflop equity estimates; use a cautious opponent model to inform sampled ranges; and test whether removing the separate forced pot-raise rule simplifies strategy without hurting results. The end state is a reproducible benchmark and validation process that promotes only variants supported by clean evidence under the tournament's runtime constraints.

## Goals

- Reproduce baseline and candidate results against all four bundled opponents using paired deals, fixed seeds, saved configuration and runtime metadata, and explicit fault and timeout reporting.
- Measure per-decision and per-half compute costs and implement a conservative budget with bounded, adaptive postflop sampling; return a legal action when the budget is tight.
- Generate deterministic preflop artifacts with per-bucket counts and smoothed estimates; evaluate calibration on separately generated held-out deals.
- Track only observable opponent behavior, avoid counting actions twice, and test an optional, bounded range-aware equity estimator against the random-range baseline.
- Compare the current forced pot-raise rule with a simpler action-mix-only variant by ablation; retain the better-supported behavior rather than assuming removal improves play.
- Run correctness tests, startup and tournament-like timing checks, and held-out paired matches; document outcomes and retain the current behavior when evidence is inconclusive.

## Non-Goals

- Building a full game-theoretic solver, neural network, real-time tree search, or guaranteed unexploitable strategy.
- Changing official poker rules, the server protocol, opponent bots, or judge scoring; do not depend on changes to tournament-provided engine files.
- Claiming that raw showdown equity equals expected value on earlier streets or that the bundled opponents represent all tournament opponents.
- Automatically publishing, submitting, or deploying the bot.

## Background / Context

- The bot uses a feature-key preflop table, then 16/24/40 flop/turn/river Monte Carlo samples against random hands, bucketed action mixes, pot-odds adjustments, and a separate random forced-pot-raise path. The table builder currently retains buckets with as few as five observations and does not save their counts.
- The initial comparison at `benchmarks/policy-comparison/RESULTS.md` used three seeds and 1,000 duplicate deals per seed. Two old-policy calling-station halves and one new-policy always-half half exhausted the eight-second bank, contaminating those matches with judge defaults. The clean calling-station comparison has only one seed. Treat this as a baseline, not proof of tournament strength.
- `AgentConfig` provides the initial `time_bank_seconds` and `num_hands`, but observations expose no remaining judge clock. The judge charges elapsed request time less per-request network grace and handles batched results; the bot cannot perfectly reconstruct that measurement. Account for local handling time conservatively, leave reserve for unmeasured overhead and end-of-half work, and validate with the unmodified judge under realistic load.
- An observation contains the current hand's visible action history, which grows between decisions. `HandResult` does not include full action history and only reveals opponent hole cards at showdown. Avoid inferring unobserved folds or opponent hands; reset per-half state in `new_half` and deduplicate by hand index and history position.
- Match results report `paired_bb` over both halves, in big blinds per paired deal. Confidence intervals are approximate; action RNG and shared match state can induce dependence, and tuning on the same seeds risks overfitting.

## Features / Tasks

### B1: Establish reproducible benchmark and analysis
**Files:** `tools/benchmark_changes.py` (modify), `tests/test_benchmark.py` (new), `README.md` (modify)
**Complexity:** M
**Depends on:** None

Generalize the existing runner to compare explicitly identified, immutable baseline and candidate snapshots, including all strategy files and generated artifacts, rather than silently mixing a HEAD policy with working-tree files. Use distinct output directories, record commits or content hashes, configuration, Python/dependency versions, seeds, deal counts, hardware/runtime context, and command lines; never overwrite the prior experiment. Reuse a full-game snapshot for each variant, run the unmodified HTTP judge against the four bundled opponents, and clean up subprocesses on failure. Verify ports and startup failures explicitly. Save JSON results and summarize mean paired-deal differences and approximate uncertainty, with per-agent error, forfeit, timeout, and skipped-call counts. Exclude any entire affected seed pair from the clean comparison, but retain and report all raw results. Add a test of pairing, exclusions, and snapshot identification using small fixtures. Predeclare separate development and held-out seeds, plus a repeat protocol for noisy or time-limited results. Preserve the existing results as historical evidence.

### T1: Profile and establish a conservative time budget
**Files:** `agent.py` (modify), `bot/config.py` (modify), `bot/budget.py` (new), `tools/profile_decisions.py` (new), `tests/test_budget.py` (new), `README.md` (modify)
**Complexity:** M
**Depends on:** B1

Measure warm startup, per-street decision latency, total locally observed request-handling cost, evaluator time, and judge-reported charged time across diverse actions and long halves. Initialize a per-half budget using `AgentConfig`; track monotonic local time for all bot-controlled work, including delivered hand results, and reserve configurable headroom for server/network overhead the bot cannot observe. Do not claim the local counter is the judge's actual remaining time. Provide bounded per-decision allocation based on estimated remaining hands, with a hard conservative per-request cap and a low-work fallback that returns a legal action. Test reset, budget depletion, reserve, and legal fallback with an injectable clock; compare local estimates with judge statistics and report any underestimation. Use the official smoke/build check and repeated full-length matches to target zero skipped calls, errors, or forfeits, while recognizing host load prevents an absolute guarantee.

### T2: Make equity sampling efficient and adaptive
**Files:** `bot/equity.py` (modify), `bot/policy.py` (modify), `bot/config.py` (modify), `bot/budget.py` (modify), `tests/test_equity.py` (new), `tests/test_policy.py` (modify)
**Complexity:** L
**Depends on:** T1

Profile before optimizing. Hoist invariant dead-card and remaining-deck work out of the sample loop and preserve uniform valid deals, exact two-hole/three-board evaluation, tie handling, and known-opponent behavior. Allocate a small initial batch and, only if budget remains, add bounded batches when uncertainty could change a bucket or price decision. Use sample variance or a conservative interval for win/tie utilities, not a fixed equity margin disguised as certainty. Keep configurable minimum/maximum work and a safe response when no extra samples fit. Validate collision-free dealing, reproducibility with seeded RNG, known-opponent and tie cases, and sampled equity against a substantially higher-sample independent reference on fixed states. Compare latency and error under equal compute budgets; revert adaptive complexity if it does not earn its cost.

### P1: Build a calibrated preflop artifact
**Files:** `scripts/build_preflop_table.py` (modify), `bot/tables.py` (modify), `bot/config.py` (modify), `data/preflop_equity.json` (modify), `tools/validate_preflop_table.py` (new), `tests/test_preflop_table.py` (new), `README.md` (modify)
**Complexity:** L
**Depends on:** B1

Generate more independent random matchups offline with explicit seeds and reproducible metadata. Save bucket counts, total win/tie utility, smoothing parameters, deck/rule and feature-schema versions; use count-weighted shrinkage to a separately defined broad prior for sparse buckets. Pick and document a coherent fallback for unseen buckets instead of assuming score bands are calibrated; validate that fallback independently. Define a versioned schema and either support legacy float-only tables during migration or supply a clear safe fallback when the artifact is missing or invalid. Do not silently present the unsmoothed estimates as high-confidence facts. Use disjoint generation and validation seeds to report coverage, sample counts, calibration and error versus the current table and a simple global prior, including rare buckets and confidence limits. Verify deterministic regeneration and loader bounds. Promote a new artifact only if held-out quality and match benchmarks support it, with no startup or size regression.

### O1: Record observable opponent tendencies
**Files:** `bot/opponent.py` (new), `agent.py` (modify), `bot/config.py` (modify), `tests/test_opponent.py` (new)
**Complexity:** M
**Depends on:** B1

Maintain compact per-half, street-aware counts of observed opponent checks/calls and raise sizes, keyed by situation where enough observations exist. Consume only new entries from `Observation.action_history` using hand index and history offset; handle repeated observations, hand transitions, and half resets. Update showdown-derived observations only when `opp_hole` is provided, and do not count an unobserved fold as a known event. Use conservative prior counts and minimum evidence so early tendencies stay near defaults. Add deterministic tests for deduplication, unseen terminal actions, showdown visibility, and reset. Keep the model disabled by default until O2 is validated.

### O2: Add bounded range-aware equity as an experiment
**Files:** `bot/opponent.py` (modify), `bot/equity.py` (modify), `bot/policy.py` (modify), `bot/config.py` (modify), `tests/test_opponent.py` (modify), `tests/test_equity.py` (modify)
**Complexity:** L
**Depends on:** T2, O1

Define a small, inspectable likelihood model conditioned on observable street, bet size and history; blend it with a uniform range using the prior and evidence from O1. Preserve card removal, five-card valid hands, and known-opponent mode. Use bounded candidate generation or weighting, never unbounded rejection, and fall back to the random-range estimator when observations are sparse, weights degenerate, or time is short. Separate range weighting from guesses about opponent folding; action history alone does not reveal ground-truth hands. Test sample validity, determinism, sensitivity to inputs, prior behavior, fallback, and runtime. Evaluate on synthetic opponents with known tendencies plus all bundled opponents, including held-out seeds. Enable only if the clean paired benchmark and time-bank criteria support it.

### S1: Ablate and simplify forced pot raises
**Files:** `bot/policy.py` (modify), `bot/config.py` (modify), `tests/test_policy.py` (modify), `README.md` (modify)
**Complexity:** M
**Depends on:** B1

Expose a configuration switch that disables the extra forced pot-raise path while leaving action-mix raises and the existing pot-price gate intact. Measure the isolated effect using matched seeds before combining it with other changes. Check that free checks, legal-action filtering, and call-price handling remain correct. Remove obsolete forced-raise settings only if the mix-only variant meets the promotion criteria in V1; otherwise retain the current path and document the result. A pot-sized raise is not necessarily an all-in.

### V1: Integrate, validate, and choose defaults
**Files:** `tools/benchmark_changes.py` (modify), `bot/config.py` (modify), `tests/test_policy.py` (modify), `README.md` (modify), `benchmarks/README.md` (new)
**Complexity:** L
**Depends on:** T2, P1, O2, S1

Run unit and protocol tests, the official container smoke/build check where available, and repeated full-length tournament-like matches. Measure each feature in isolation against the same frozen baseline, then evaluate the combined candidate and key interactions on held-out seeds. Predeclare decision thresholds and sample sizes before inspecting held-out results: require zero recorded errors/forfeits/skipped calls in the validation runs, held-out preflop calibration improvement for P1, and no material deterioration against any opponent, with uncertainty reported for both per-opponent and overall paired differences. An interval overlapping a practical deterioration bound is inconclusive, not proof of equivalence. Record raw and clean metrics, timing distribution, exclusions, versions, seed split, and limits; repeat or leave a feature disabled when evidence is insufficient. Record final defaults, commands, and rollback configuration without overwriting the prior experiment.

## New Dependencies

| Package | Feature | Optional? |
| --- | --- | --- |
| None | Use the standard library and existing runtime/test dependencies. | N/A |

## File Change Summary

| File | Action (new/modify/delete) |
| --- | --- |
| `agent.py` | Modify |
| `bot/budget.py` | New |
| `bot/config.py` | Modify |
| `bot/equity.py` | Modify |
| `bot/opponent.py` | New |
| `bot/policy.py` | Modify |
| `bot/tables.py` | Modify |
| `data/preflop_equity.json` | Modify |
| `scripts/build_preflop_table.py` | Modify |
| `tools/benchmark_changes.py` | Modify |
| `tools/profile_decisions.py` | New |
| `tools/validate_preflop_table.py` | New |
| `tests/test_benchmark.py` | New |
| `tests/test_budget.py` | New |
| `tests/test_equity.py` | New |
| `tests/test_opponent.py` | New |
| `tests/test_policy.py` | Modify |
| `tests/test_preflop_table.py` | New |
| `README.md` | Modify |
| `benchmarks/README.md` | New |

## Open Questions

- What practical performance-regression bound and compute budget should be predeclared for each opponent? Choose and record them in B1 before tuning, based on observed variance and available runtime.
- How much offline simulation and artifact size are acceptable for the final submission? Start with a bounded pilot and scale only if held-out calibration benefits justify the cost.
- Does the tournament runtime provide less compute headroom than this Windows host? Validate in the provided container and on representative hardware before enabling costly variants.
- Are additional, stronger opponents available for held-out evaluation? The bundled bots are useful regression tests but offer limited strategic coverage.

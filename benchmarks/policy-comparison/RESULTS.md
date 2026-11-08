# Policy comparison — 2026-11-07

The old policy was loaded from commit `b540f80a399ef96f353f66b12abdbfe3a63cae60` (policy blob `1ec89a8e347f4518282e74792a5ac831d4028204`). The new policy was working-tree blob `0249c313a33c6199aaaf03c971284c0b5144da94`. Both used the same other working-tree files. Each match used 1,000 duplicate deals (2,000 hands), seeds 7, 19, and 37, and the judge's normal time bank. JSON files contain the original match results.

The following are new-minus-old big blinds per paired deal, with approximate 95% normal intervals based on the standard error of per-deal paired differences. Seed pairs with any timeout, skipped call, error, or forfeit were excluded entirely. This is a local experiment, not proof of performance against tournament opponents.

| Opponent | Clean paired deals | Difference | Approximate 95% interval |
| --- | ---: | ---: | ---: |
| Random | 3,000 | +1.198 | +0.024 to +2.373 |
| Calling station | 1,000 | -0.358 | -1.209 to +0.493 |
| Always half pot | 2,000 | +2.274 | +0.897 to +3.652 |
| Always pot | 3,000 | +1.392 | +0.300 to +2.484 |

Excluded: old calling station seed 7 (321 skipped calls) and 19 (350); new always-half seed 19 (55). Those halves exhausted their time banks, so the judge used default actions. There were no recorded errors or forfeits in any match. Timing depends on host load and the normal confidence approximation does not account for all possible correlations across a match.

This historical run used the original runner, which compared the HEAD policy with other working-tree files. The updated runner compares complete snapshots and writes a new directory for each run; its results should not be treated as exactly the same experimental setup.

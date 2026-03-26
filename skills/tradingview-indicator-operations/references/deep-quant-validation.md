# Deep Quant Validation

## Validation Matrix

| Family | Test | Evidence | Pass Gate |
| --- | --- | --- | --- |
| Determinism | Re-run same range and compare signal timestamps | Signal timestamp diff list | No timestamp drift |
| No-repaint | Replay and live-bar observation around trigger bars | Replay notes and chart captures | No historical signal relocation |
| Stop/Target Integrity | Verify stop family and TP levels under multiple ATR regimes | Sample rows for each stop family | Level math matches contract |
| Target Eligibility | Validate `targetEligible20pt` against computed path points | Direct numeric comparison | 100 percent consistency on sampled bars |
| Event Response | Stress event modes across cross-asset state combinations | Event mode transition table | Expected mode mapping holds |
| Session Logic | Validate bucket transitions at time boundaries | Boundary case table | No off-by-one bucket errors |
| Harness Integration | Validate pivot and LuxAlgo harness exports are wired and non-null when expected | Export field sample set | Fields populate with coherent values |
| Alert Semantics | Validate alert trigger equals on-chart state trigger | Alert firing log vs state table | No false-positive mismatches in sampled cases |
| Strategy Parity | Compare indicator and strategy export/logic parity | Parity script output | No contract drift |

## Required Quant Outputs

1. Test matrix with `PASS`, `PARTIAL`, or `FAIL` for each family.
2. Severity-ranked defect list (`P0` to `P3`).
3. Suggested fix and regression test per failed checkpoint.
4. GO or NO-GO decision with next blocker.

## Deep Backtesting Protocol

When Deep Backtesting is required:

1. Define symbol, timeframe, date range, and configuration packet.
2. Capture baseline metrics before edits.
3. Re-run after edits with identical settings.
4. Compare trade distribution, hit rates, and drawdown behavior.
5. Reject claims that are not backed by side-by-side evidence.

## Metric Set

Capture these metrics when available:

- total trades
- win rate
- profit factor
- max drawdown
- avg MAE
- avg MFE
- TP1 hit rate
- TP2 conditional hit rate
- stop-first rate

## Review Quality Rules

- Prefer direct evidence over intuition.
- Separate deterministic defects from optional enhancements.
- Tie every recommendation to a measurable validation gate.

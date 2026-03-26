# TradingView Pine Limits (Snapshot: 2026-03-26)

Source:
- https://www.tradingview.com/pine-script-docs/writing/limitations/

Use these limits as hard constraints during design and review.

## Time Limits

- Compilation timeout: 2 minutes per compile attempt.
- Consecutive compile overages: after 3 warnings, 1-hour compile ban.
- Total execution time: 20 seconds for basic accounts, 40 seconds for other accounts.
- Loop time limit: 500 ms per loop per bar.

## Visual Limits

- Max plot counts per script: 64.
- Default visible recent drawings: 50 lines, boxes, polylines, labels.
- Max drawing IDs:
- lines: 500
- boxes: 500
- labels: 500
- polylines: 100
- Max tables shown on chart: 9 (one per chart position).

## request.* Limits

- Unique `request.*()` calls: 40 (64 on Ultimate).
- Combined tuple elements returned across all `request.*()` calls: 127.
- Lower-timeframe intrabars by plan:
- non-professional plans: 100,000
- Expert: 125,000
- Ultimate: 200,000

## Script Size and Memory Limits

- Compiled token limit per script: 100,000.
- Total compiled tokens across imported libraries: 1,000,000.
- Variables per scope: 1,000.
- Compilation request size: 5 MB.
- Collections max elements:
- arrays: 100,000
- matrices: 100,000
- maps: 50,000 key-value pairs

## History and Bar Position Limits

- Max bars back for most series: 5,000.
- Larger built-in buffers (`open`, `high`, `low`, `close`, `time`): up to 10,000.
- Drawings with `xloc.bar_index`: up to 10,000 bars in the past and 500 bars in the future.

## Chart and Strategy Limits

- Minimum chart bars by account plan can range from 5,000 to 40,000 when historical data exists.
- Backtesting order cap: 9,000 orders.
- Deep Backtesting order cap: 1,000,000 orders.

## Practical Guard Rails

- Start warning at 75 percent of hard limits.
- Reject new logic that pushes `request.*()` calls near cap without de-duplication plan.
- Reject heavy visual additions when plot count budget is low.
- Prefer deterministic simplification over near-limit complexity.

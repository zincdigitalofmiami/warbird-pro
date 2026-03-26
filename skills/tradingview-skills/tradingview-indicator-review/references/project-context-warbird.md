# Warbird Project Context

## Dynamic Discovery Rules

1. Read `AGENTS.md` first and resolve the active plan path from that file.
2. Treat the active plan as higher priority than stale archived plans.
3. Re-read `AGENTS.md` when user direction changes mid-task.

## Current Snapshot (2026-03-26)

### Canonical Contract

- Canonical trade object: MES 15m fib setup.
- Canonical key: MES 15m bar-close timestamp in `America/Chicago`.
- Pine is canonical signal surface; Next.js dashboard mirrors that contract.

### Current Pine Surfaces

- Indicator: `indicators/v6-warbird-complete.pine`
- Strategy: `indicators/v6-warbird-complete-strategy.pine`

### Current Gate Baseline

- `scripts/guards/pine-lint.sh indicators/v6-warbird-complete.pine`: pass with one warning.
- `scripts/guards/check-contamination.sh`: pass.
- `scripts/guards/check-indicator-strategy-parity.sh`: fail due hidden export drift (strategy contains fields indicator does not expose).
- `npm run build`: pass.

### Current Code Metrics Snapshot

- Indicator lines: 947
- Strategy lines: 1023
- Indicator `request.security()` calls: 11
- Indicator `request.economic()` calls: 3

## Data Surfaces for Matching Suggestions

Use these surfaces when tying indicator suggestions to data or schema changes.

### Market Data

- `mes_1m`
- `mes_15m`
- `cross_asset_1h`
- `cross_asset_1d`

### Economic Data

- `econ_rates_1d`
- `econ_yields_1d`
- `econ_fx_1d`
- `econ_vol_1d`
- `econ_inflation_1d`
- `econ_labor_1d`
- `econ_activity_1d`
- `econ_money_1d`
- `econ_commodities_1d`
- `econ_indexes_1d`
- `econ_calendar`

### News and Event Context

- `news_signals` (market-impact polarity, not trade-direction engine)
- `econ_news_topics`
- `econ_news_rss_articles`
- `econ_news_finnhub_articles`

### Warbird Decision Surfaces

- `warbird_triggers_15m`
- `warbird_conviction`
- `warbird_setups`
- `warbird_setup_events`
- `warbird_risk`

## Suggestion Mapping Template

For each recommendation, map all of the following:

1. Pine logic section(s) and file path(s)
2. Hidden export fields changed or added (`ml_*`)
3. Data surface dependencies (table names)
4. Validation gates required before release

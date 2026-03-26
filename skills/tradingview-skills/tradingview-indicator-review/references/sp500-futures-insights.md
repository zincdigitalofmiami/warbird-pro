# S&P Futures Insights (MES/ES)

Use this reference when reviewing, building, repairing, or optimizing MES/ES indicators.

## Contract Mechanics

- MES tick size: `0.25` index points.
- MES tick value: `$1.25` per tick.
- ES tick value: `$12.50` per tick.
- Keep signal logic contract-agnostic where possible and apply sizing downstream.

## Session Structure (America/Chicago)

- CME equity index RTH focus window: `08:30` to `15:00` CT.
- Open impulse risk: first 30 to 60 minutes after `08:30` CT.
- Midday liquidity decay: roughly `11:30` to `13:00` CT.
- Cash close transition risk: `14:50` to `15:10` CT.
- Overnight (ETH) can distort volatility baselines; separate RTH vs ETH analytics when possible.

## Rollover and Continuity

- Quarterly roll months: `H`, `M`, `U`, `Z`.
- Ensure historical tests use consistent continuation logic; avoid mixing unadjusted roll gaps with live logic conclusions.

## Cross-Asset Regime Cues

- DXY strength often pressures index futures risk sentiment.
- US10Y yield shocks can reprice equity duration quickly.
- VIX spikes are risk-off context flags, especially when paired with negative breadth.
- NQ leadership changes can front-run directional pressure in ES/MES.

## Event Risk

- High-impact US releases (CPI, NFP, FOMC) can invalidate normal intraday assumptions.
- Require explicit event-mode logic and post-release cooldown handling.
- Do not interpret single-bar post-release spikes as stable trend confirmation without follow-through.

## Quant Notes for ML Exports

- Preserve bar-close determinism for all exported `ml_*` fields.
- Prevent future leakage in features tied to targets, stops, or event windows.
- Keep export semantics stable across indicator and strategy surfaces.

# Nexus Night Hard Checkpoint - 2026-05-15

## Snapshot

- Checkpoint type: end-of-day hard lock
- Repo state at checkpoint: clean (`git status --short` returned no changes)
- Pine edits in this checkpoint: none
- Active lane: Nexus-only
- Scope lock: no V9 surfaces touched

## Locked Plan (Saved)

The next implementation window is the Nexus single-gauge layer inspired by the
On-Chain/Market-Sentiment style presentation, while preserving the existing
footprint-first signal authority.

Core gauge contract:

1. One neat gauge (0-100, center 50) as fast state read.
2. Keep oscillator as context layer (no replacement).
3. Footprint quality fail-closed behavior remains mandatory.
4. Real exhaustion remains gas-out authority.
5. Add export-only diagnostics for AG follow-up.

Planned export-only additions:

- `nexus_live_pressure_meter`
- `nexus_pressure_side`
- `nexus_buyer_gas_remaining`
- `nexus_seller_gas_remaining`
- `nexus_gas_remaining_active`
- `nexus_pressure_slowdown`
- `nexus_long_confidence`
- `nexus_short_confidence`
- `nexus_confidence_state`

## Freeze Boundary (Until Edit Window Is Reopened)

Do not modify these surfaces while the current active run/defer window is in
effect:

- `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
- `scripts/duckdb_local/workspaces/warbird_nexus_ml_rsi_15m/build_nexus_15m_dataset.py`
- `scripts/duckdb_local/workspaces/warbird_nexus_ml_rsi_15m/train_nexus_15m_heavy.py`
- In-flight Nexus manifests/reports/artifacts

Authority references:

- `quality/RUN_NEXUS_INDICATOR.md`
- `quality/results/2026-05-15-nexus-live-meter-deferred-hold.md`

## Resume Checklist (First Actions Tomorrow)

1. Confirm active-run freeze is lifted and Pine edit window is explicitly approved.
2. Run TradingView readiness doctor:

```bash
python3 scripts/ag/tv_connection_doctor.py --json
```

3. If TradingView work is planned, enforce preflight + slot safety before Pine
   mutation.
4. Implement in two slices:
   - Slice A: gauge UI/state only (no behavior change to trigger logic)
   - Slice B: export diagnostics + training feature wiring
5. Run Nexus resume gates before completion claim.

## Mandatory Verification Gates After Pine Change

```bash
curl -s -X POST "https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=admin&v=3" \
  -H 'Referer: https://www.tradingview.com/' \
  -F "source=<indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine"
./scripts/guards/pine-lint.sh indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
./scripts/guards/check-contamination.sh
./scripts/guards/check-no-tv-force.sh
npm run build
./.venv/bin/python -m pytest quality/test_functional.py -k nexus -q
```

## Next AG Run Requirements After Gauge Changes

1. Re-export TradingView chart CSV after Pine export-surface changes.
2. Rebuild isolated Nexus dataset:

```bash
python scripts/duckdb_local/workspaces/warbird_nexus_ml_rsi_15m/build_nexus_15m_dataset.py \
  --source-csv "/Users/zincdigital/Downloads/CME_MINI_MES1!, 15_d464a.csv"
```

3. Validate manifest/splits quickly before heavy fit:

```bash
python scripts/duckdb_local/workspaces/warbird_nexus_ml_rsi_15m/train_nexus_15m_heavy.py \
  --manifest scripts/duckdb_local/workspaces/warbird_nexus_ml_rsi_15m/exports/nexus_15m_dataset.manifest.json \
  --section all_features \
  --validate-only
```

4. Use section sequence and section targets exactly:

- `footprint_delta_flow` -> `label_volume_expansion_next_12b`
- `volume_flow` -> `label_volume_expansion_next_12b`
- `oscillator_regime` -> `label_abs_move_ge_0p5atr_5b`
- `divergence_exhaustion` -> `label_swing_low_next_12b`
- `signal_tier_composite` -> `label_volume_expansion_next_12b`

5. Heavy run template (apply per section with correct `--section` and `--target`):

```bash
python scripts/duckdb_local/workspaces/warbird_nexus_ml_rsi_15m/train_nexus_15m_heavy.py \
  --manifest scripts/duckdb_local/workspaces/warbird_nexus_ml_rsi_15m/exports/nexus_15m_dataset.manifest.json \
  --section footprint_delta_flow \
  --target label_volume_expansion_next_12b \
  --time-limit 14400 \
  --hpo-trials 80 \
  --num-bag-folds 5 \
  --num-bag-sets 2 \
  --num-stack-levels 1 \
  --dynamic-stacking auto \
  --model-profile neural_scout
```

6. Do not proceed to the next section unless section decision is
   `save_and_proceed`.

## Skill Map (Use On Resume)

Nexus implementation skills:

- `.claude/skills/tc-indicators-basics/SKILL.md`
- `.claude/skills/tc-math/SKILL.md`
- `.claude/skills/tc-operators/SKILL.md`
- `.claude/skills/tc-technical-analysis/SKILL.md`
- `.claude/skills/tc-advanced-pine/SKILL.md`
- `.claude/skills/tc-plots/SKILL.md`
- `.claude/skills/tc-visual-output/SKILL.md`
- `.claude/skills/tc-bar-coloring/SKILL.md`
- `.claude/skills/tv-preflight/SKILL.md`
- `.claude/skills/verify-tv-slot/SKILL.md`
- `.claude/skills/cdp-down-recovery/SKILL.md`
- `.claude/skills/pine-tuning-optimizations/SKILL.md`

Training and evaluation skills:

- `.claude/skills/preflight-training/SKILL.md`
- `.github/skills/training-quant-trading/SKILL.md`
- `.github/skills/training-ag-best-practices/SKILL.md`
- `.github/skills/training-shap/SKILL.md`
- `.github/skills/training-monte-carlo/SKILL.md`

## Chart Graphics References

- Pine visuals overview: https://www.tradingview.com/pine-script-docs/visuals/overview/
- Tables: https://www.tradingview.com/pine-script-docs/visuals/tables/
- Plots: https://www.tradingview.com/pine-script-docs/visuals/plots/
- Fills: https://www.tradingview.com/pine-script-docs/visuals/fills/
- Lines and boxes: https://www.tradingview.com/pine-script-docs/visuals/lines-and-boxes/

## Morning Restart Goal

Resume with a single objective: deliver the neat gauge in a safe, fail-closed,
Nexus-only slice, then re-export and run sectioned AG retraining with manifest
and chronological-proof discipline.
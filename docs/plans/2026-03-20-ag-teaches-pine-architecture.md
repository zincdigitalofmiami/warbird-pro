# Warbird Pro — AF Struct+IM Indicator Plan

**Date:** 2026-03-20
**Status:** Active Plan — Single Source of Truth
**Scope:** MES 15m fib-outcome contract: indicator + dashboard operator surface + AG training pipeline

**THIS IS THE ONLY PLAN TO UPDATE.**

- All architecture changes, implementation phases, UI decisions, and status updates for this indicator live in this file.
- Do not create new architecture or plan docs for this indicator without explicit approval.
- All other plan docs are archived under `docs/plans/archive/`.

Historical note: any remaining references below to the paired strategy, parity-only checkpoints, or Deep Backtesting are archived execution history unless a newer update-log entry explicitly reactivates them.

Historical retention note: cloud core data window is `2024-01-01T00:00:00Z` forward only. Local offline training warehouse extends to `2018-01-01T00:00:00Z` per 2026-03-30 directive (LuxAlgo suggestion) — 8 years of comparable electronic futures data for AG training depth.

Binding note: the 2026-03-28 update-log entries supersede older references below to right-side TradingView tables, `LONG READY` / `SHORT READY` action labels, dashboard-local fib computation, Markdown report blobs, and any schema language that still treats `EXPIRED` / `NO_REACTION` as canonical economic model truth.

### Next Blocking Order (2026-03-29 updated — Pine recovery complete)

1. ~~**Pine indicator recovery**~~ — **DONE.** `isValid`/`atr` fixed (commit `c506c48`), output budget fixed at 63/64 (cut 8 alerts + 2 plot exports + bgcolor), TradingView paste-and-load validated with all 15 TA Core Pack exports visible in Style tab. Three standalone harnesses retired and replaced by embedded TA core pack.
2. **Fib engine hardening** — anchor quality drives everything; confirm left/right bar space, direction logic, multi-timeframe alignment (15m fibs + 1H/4H structure must agree in direction for trigger), exhaustion signal preservation, anchor-span visual gap (lines should extend to full swing area), and intermediate waypoint lines (1.382, 1.50, 1.786) as drawing objects.
3. **Canonical writer checkpoint** — port or replace the legacy `detect-setups` / `score-trades` Vercel routes as Supabase Edge Functions that write to the reconciled canonical tables. Fix CME continuity-gap handling before calling the writer live.
4. **Dashboard/admin/API reader cutover** — cut `/admin`, `/api/admin/status`, and dashboard consumers off legacy tables and onto the canonical snapshot/candidate surfaces plus the new Admin packet views. TradingView webhook alerts (entry long, entry short, pivot break reversal) can drive real-time dashboard state via Supabase Edge Function webhook receiver.
5. **Local warehouse / selector buildout** — stand up the AG workbench (`scripts/ag/*`), local PostgreSQL snapshot mirror, diagnostic tables, and packet publish-up lifecycle. AG config is locked: `best_quality`, 5 bag folds, 2 stack levels, `log_loss`, walk-forward with purge/embargo, SHAP 5-step pipeline, Admin dashboard reporting for noise/golden-zones/indicator-settings discovery.
6. **Legacy table retirement** — drop `warbird_triggers_15m`, `warbird_conviction`, `warbird_risk`, `warbird_setups`, `warbird_setup_events`, `measured_moves`, `warbird_forecasts_1h` only after all readers/writers are migrated.

---

## Update Log

- 2026-03-30: **Kirk chart reading teaching session — foundational methodology locked.** Key directives absorbed into memory and plan: (1) **Structure before indicators** — horizontal S/R from prior high-volume swing highs/lows is the primary chart read; fibs/EMAs/indicators confirm, they don't lead. (2) **Fibonacci universality** — pivots, S/R, trendlines, and fib retracements are all expressions of the same Fibonacci mathematics; demonstrated to-the-tick precision across 4H→1H→15m (fib 6388.98 vs M(S4) 6388.25 = 0.73pts, fib 6482.00 vs structural level 6482.75 = 0.75pts). (3) **Volume as the force at Fibonacci levels** — exhaustion score + RVOL determine whether a level holds (rejection) or breaks (market structure change); same level produces opposite outcomes depending on volume. (4) **Post-sweep entry methodology** — enter AFTER the liquidity sweep, not at the level; 10-tick SL is possible because liquidity is already harvested; this is how Kirk would trade with minimal risk. (5) **S/R flip as AG feature** — when support breaks it becomes resistance via trapped traders seeking breakeven exits; volume at original pivot determines flip strength. (6) **Training data floor extended to 2018-01-01** per LuxAlgo suggestion — 8 years of Fibonacci structure for AG training depth (cloud core stays 2024-01-01). (7) **Fractal timeframe alignment confirmed** — monthly fib levels appear on 15m and even 1m charts to the tick; the same structure exists at every scale. AG feature implications: fib proximity + MTF S/R proximity + pivot proximity converging near zero = highest probability zones; SHAP will discover these cluster together because they measure the same underlying Fibonacci structure. V7 features `ml_exhaustion_score`, `ml_rvol_at_entry`, `ml_liq_sweep_bull/bear` are the key discriminators.
- 2026-03-30: v7 indicator verified and pushed (commit `ffb26f8`). AG label surface fixed (`lastExitOutcome`, `tradeDir`), 9 collinear plots removed, cooldown 4→8, PIT documentation added. Plot budget: 52 plots + 3 alertconditions = 55/64 (9 slots headroom). All 4 gates passed: pine-facade compile, pine-lint, check-contamination, npm build.
- 2026-03-29: Locked Admin candidate table staple columns per user directive. The table that replaces legacy "Measured Moves" on `/admin` MUST include Dir, Target, TP1 Hit, TP2 Hit, SL Hit, Status as non-negotiable staple columns. The existing `target_hit_state` column in `warbird_admin_candidate_rows_v` (migration 038) is ambiguous — it must be split into three explicit computed columns: `tp1_hit`, `tp2_hit`, `sl_hit` (each emitting HIT/MISS/OPEN). Full locked column set: Time, Dir, Entry, Target, TP1 Hit, TP2 Hit, SL Hit, Status (non-negotiable), plus SL Price, TP2 Price, Fib Level, Outcome, Decision (recommended operator context). See locked spec section below view table definition.
- 2026-03-29: Added TradingView → Dashboard webhook architecture section. The 3 kept Pine alertconditions (entry long, entry short, pivot break .50 reversal) are the live event bridge from Pine to the dashboard command center via TradingView webhook → Supabase Edge Function (`tv-alert-webhook`) → canonical tables → Supabase Realtime → dashboard. The 8 cut alerts are reconstituted as dashboard-side derived state from stored fib engine + intermarket data. Fixed CLAUDE.md: budget corrected to 63/64 (bgcolor removed), blocking order updated (Pine recovery DONE), fib recompute claim removed (cut in commit 77ec03e).
- 2026-03-29: Plan deep cleanup — removed ~600 lines of accumulated noise. Collapsed Phase 2 checkpoint locks (5 checkpoints, 280 lines → 6-line summary). Collapsed Phase 3 retired section (220 lines → 3-line summary). Marked Required Harness Modules as SUPERSEDED by TA core pack (commit `c506c48`). Updated Phase 4 training order to remove harness admission steps. Updated Feature-Family De-Duplication Rule to reference TA core pack. Rewrote Section 20 Immediate Next Steps with current reality (struck completed items, removed harness references). Fixed packet format alert line (now 3 alerts: entry long, entry short, pivot break reversal). Audited Pine export contract lists against current Pine file and marked cut exports. Marked completed items in Forensic Review / What Must Change. Fixed March 23 Delta harness references. Fixed line 3040 contradiction (said "Supabase does not own any cron schedules" — corrected to "Vercel"). Updated Blocking Order #1 to DONE with TV-validated 63/64 budget.
- 2026-03-29: Fib visual gap identified vs Auto Fib GOLDEN TARGET reference. Two improvements needed: (1) anchor span — fib lines should extend left to cover the full anchor high/low swing area, not just the pivot bar (purely visual for operator geometry). (2) Intermediate waypoint lines — the locked fib inventory already includes `1.382`, `1.500`, `1.786` as gray waypoints but WB v6 does not draw them yet. Price reacts to these levels and the model may benefit from waypoint-touch features. Both improvements apply to Pine and dashboard fib renderers. No output budget impact — these are `line.new()` / `label.new()` drawing objects, not `plot()` calls. Also removed `bgcolor()` regime tint and `showBg` input (never used) — budget now 63/64 with 1 slot headroom.
- 2026-03-29: Pine output budget fix — TradingView-validated blocker. Manual TradingView paste-and-load confirmed the indicator loads but TradingView silently drops all outputs after position 64. `alertcondition()` counts toward the 64-output hard cap — `pine-lint.sh` had a bug claiming they do not (line 96 explicitly excluded them). Actual budget was 74/64 (62 plot + 1 bgcolor + 11 alertcondition), not the 63/64 the lint script reported. `ml_tp2_hit_event` and the entire 15-metric TA Core Pack (lines 816–830) were invisible to TradingView — never exported. Agreed cut plan: (1) Remove 8 `alertcondition()` calls, keeping only `WARBIRD ENTRY LONG`, `WARBIRD ENTRY SHORT`, and `PIVOT BREAK (against) + Regime Opposed` (the .50 reversal warning — fires when price breaks pivot against fib direction with intermarket regime confirmation, maps to `setupFailedMoveReversal` archetype, contributes 45 pts to `eventReversalScore`). (2) Remove 2 plot exports: `er_20` (AG computes from `mes_15m` OHLCV trivially) and `vix_pct_252d` (AG computes from FRED VIX data). (3) Remove dead helper bools `riskOnFlip`/`riskOffFlip` (only the cut RISK-ON/RISK-OFF alerts consumed them). (4) Fix `pine-lint.sh` to count `alertcondition()` toward the 64-output budget. Budget after cuts: 60 plot + 1 bgcolor + 3 alertcondition = 64/64 exact cap. All non-essential alerts move to the Next.js dashboard. All hidden `display=display.none` `plot()` calls must remain — that is the only Pine data-export mechanism for AG training. Next: TradingView re-validate to confirm all 15 TA Core Pack exports now appear in Style tab.
- 2026-03-29: Outcome contract reset checkpoint. Canonical economic outcomes are now locked to `TP2_HIT` / `TP1_ONLY` / `STOPPED` / `REVERSAL` with `OPEN` as operational-only (excluded from training labels). Removed censored/timed-out wording from the active plan and model-spec alignment sections, and aligned draft canonical schema surfaces (`037`, `038`) plus TypeScript canonical payload types to the same contract. Legacy `score-trades` no longer writes `EXPIRED`; setups remain open until TP/SL resolution. Admin/dashboard outcome presentation now emits `TP2_HIT` / `TP1_ONLY` / `STOPPED` / `REVERSAL` / `OPEN` instead of `WIN` / `LOSS` / `EXPIRED`. Validation: `./scripts/guards/pine-lint.sh` (pass with known warning), `npm run lint` (pass), `npm run build` (pass). Next blocker: finalize the TA-only indicator simplification checkpoint (remove the three custom harness dependencies) and keep trade/admin surfaces intact during that feature swap.
- 2026-03-28: Pine type-safety hardening — added explicit type annotations (`float`, `bool`, `int`, `string`, `color`) to every global-scope variable declaration in `indicators/v6-warbird-complete.pine`. Prior state had 80+ implicitly-typed globals — a known Pine v6 compile-failure vector. Every `input.*()`, fib constant, color/width constant, computed series, intermarket flag, structure condition, event bool, and drawing variable now carries an explicit type. Also fixed output budget (removed 2 duplicate exports: `adx_14`/`ml_adx_14` and `fib_direction`/`ml_direction_code` — now 63/64) and fixed 2 `log.info()` calls that exceeded Pine v6's 5-arg format limit. Updated `scripts/guards/pine-lint.sh` to count `bgcolor()`/`fill()`/`hline()` in the output budget and fixed method-call false positives and grep `|| echo 0` bugs. Pine-lint passes: 63/64 outputs, 6/40 `request.security()` calls, 0 errors. `npm run build` passes. Status: NOT yet TradingView-validated. Pine recovery is not complete until manual paste-and-load in TradingView confirms the indicator compiles and loads without error.
- 2026-03-28: Locked the corrected mental model for the full system. This entry supersedes any prior confusion about what AG decides vs what price action/structure decides. Binding rules confirmed: (1) Fib anchor placement is determined by price action and swing structure — AG does NOT place anchors, it tunes fib engine settings (left/right bar space, anchor spacing, direction logic) through SHAP discovery. (2) Multi-timeframe direction alignment is structural — 15m fibs plus 1H/4H market structure must all agree in direction for a valid trigger; this is not a model-decided gate. (3) Entry trigger is the hardest and most important problem — AG optimizes the conditions but the difficulty is real; the crown jewel is entry, not confirmation. (4) Exhaustion signal is preserved — it found tops and bottoms through pivots, candlestick formations, and volume, tied to the REVERSAL outcome label; exhaustion is not noise. (5) Outcome labels are exactly: `TP2_HIT` / `TP1_ONLY` / `STOPPED` / `REVERSAL` / `OPEN` (OPEN is operational-only, not a training label). (6) Original locked AG configuration is confirmed from plan line 2817–2838 and `train-warbird.py`: `best_quality` preset, 5 bag folds, 2 stack levels, `log_loss` eval metric, `["KNN","FASTAI"]` excluded, 7200s time limit, walk-forward with 40-bar purge and 80-bar embargo, IC ranking → cluster dedup → 15–25 features per fold, features in ≥4/5 folds = robust (keep in Pine), <2/5 = fragile (remove). (7) Promotion thresholds are confirmed: mean OOS TP1 AUC-ROC ≥ 0.65, TP2 ≥ 0.60, TP1 calibration error ≤ 10%, worst fold TP1 AUC ≥ 0.55, stop rate on high-confidence ≤ 30%, high-confidence signals/week 3–25, AUC stability across folds ≤ 0.15. (8) SHAP pipeline is confirmed 5-step: TreeExplainer on best tree model → golden zone extraction via quantile binning → surrogate decision tree (max_depth=4) for rule extraction → rolling median across 4 weekly retrains for stability → encode as Pine inputs. (9) SHAP reporting to Admin dashboard must include: which model in the zoo made it, all settings for Pine, what was noise, what data was noise and what needs more data, feature importance rankings, golden zones per feature, indicator settings discovery (RSI 8 vs 14, EMA 21 vs 50, etc.). (10) AG trains on ALL MISSED trades — learning why setups were missed; `label_origin` field distinguishes `forward_scan` (synthetic) vs `setup_event` (real outcome); scored outcomes feed back into training labels. (11) Lateral crons keep running — they feed the AG training warehouse; nothing is paused for this mental model correction. (12) Volume and liquidity are the most important feature families — VWAP, all volume types, liquidity metrics; AG classifies which correlation pairs matter (may be different from current NQ/VIX/DXY/US10Y/HYG/LQD/BANK set). (13) Local AG warehouse gets up to 5 years of comparable electronic futures data for training depth; cloud core stays 2024-01-01 forward. No invented terminology, no premature infrastructure — Pine compiles first, fib engine is the focus, schema follows the core. Next blocker order updated below.
- 2026-03-28: Removed the legacy `prob_hit_*` aliases from the active shared signal/API contract. Binding rule: `hit_*_first` and `prob_hit_*` names are now deletion-only debt inside the old local `scripts/warbird/*` workbench and must not be reintroduced as fallback fields in new API, dashboard/Admin, packet, or schema surfaces. *(Blocker order superseded: the corrected blocking order above moves Pine recovery to #1 and fib engine hardening to #2, ahead of the canonical writer cutover.)*
- 2026-03-28: Completed the schema/admin contract reconciliation checkpoint. The draft schema package now matches the locked hierarchy, outcome semantics, and cloud-vs-local boundary, and was syntax-validated in a disposable Postgres 17 instance. Cloud publish-up is now structured around `warbird_training_runs`, `warbird_training_run_metrics`, `warbird_packets`, `warbird_packet_activations`, `warbird_packet_metrics`, `warbird_packet_feature_importance`, `warbird_packet_setting_hypotheses`, and `warbird_packet_recommendations`; raw SHAP remains local-only in `warbird_shap_results` and `warbird_shap_indicator_settings`. Admin requirements are now locked to two explicit surfaces: screenshot-style candidate/signal rows via `warbird_admin_candidate_rows_v` and full model/training metrics via `warbird_active_training_run_metrics_v`, alongside the packet KPI/explanation/recommendation views. *(Blocker order superseded: see corrected blocking order above — Pine recovery is #1.)*
- 2026-03-28: Saved a restart-safe checkpoint handoff at `docs/decisions/2026-03-28-schema-admin-contract-handoff.md` capturing the repo audit, external research conclusions, locked architecture/schema decisions, validation results, excluded dirty files, and the exact next blocking sequence for a new chat.
- 2026-03-28: Locked the hierarchy-first architecture checkpoint. Binding direction: the outcome contract now drives the platform, not the current model family; Warbird is split into `Generator` (Pine + admitted harnesses), `Selector` (offline model stack scoring frozen MES 15m fib candidates), and `Diagnostician` (research stack explaining wins, losses, and improvement paths). Canonical cloud tables exist to preserve point-in-time setup truth, realized path truth, and published decision/signal lineage only; explanatory features, SHAP outputs, ablation results, stop-out attribution, and entry-definition experiments belong in local research tables. `EXPIRED` / `NO_REACTION` are no longer treated as canonical economic model outcomes, and unresolved rows remain `OPEN` until they resolve to an economic outcome. The current 2026-03-30 schema drafts (`037`, `038`, and the local warehouse draft) are retained as design inputs only and are not deployable truth until rewritten against this lock. Next blocker: rewrite the schema drafts to match the locked hierarchy and truth semantics before any remote apply or reader/writer cutover.
- 2026-03-27: Locked the architecture reset after a live repo audit. Current repo truth is `NO-GO`: `indicators/v6-warbird-complete.pine` is not TradingView-loadable (`isValid` / `atr` undeclared in the active file and downstream `log.info` type failures), the dashboard still recomputes fib geometry through the legacy `scripts/warbird/fib-engine.ts` helper instead of rendering a shared packet, `/admin` still leans on stale `measured_moves`, and the live `warbird_*` decision/outcome tables are empty. Binding delta: the adaptive fib engine snapshot is now the canonical base object; the canonical flow is `fib_engine_snapshot -> candidate -> outcome -> decision -> signal`; decision vocabulary is locked to `TAKE_TRADE`, `WAIT`, `PASS`; TradingView keeps execution-facing visuals/alerts plus the exhaustion precursor diamond while operator tables move to the dashboard; five years of comparable electronic futures data is approved for offline training research only, while cloud core support tables remain `2024-01-01T00:00:00Z` forward. The exact snapshot/candidate/outcome schema is now locked in this plan and `WARBIRD_MODEL_SPEC.md`. Next blocker: implement the migration, cut dashboard consumers off local fib computation, and replace the legacy `warbird_triggers_15m` / `warbird_conviction` / `warbird_risk` / `warbird_setups` path with the canonical normalized tables.
- 2026-03-27: Applied live retention-floor trim migration `supabase/migrations/20260327000024_trim_pre_2024_core_history.sql` to keep core historical data at `2024-01-01T00:00:00Z` forward only. Validation confirmed zero pre-2024 rows remain in `econ_rates_1d`, `econ_yields_1d`, `econ_fx_1d`, `econ_vol_1d`, `econ_inflation_1d`, `econ_labor_1d`, `econ_activity_1d`, `econ_money_1d`, `econ_commodities_1d`, `econ_indexes_1d`, `geopolitical_risk_1d`, and legacy `econ_news_1d`; MES and cross-asset intraday tables were already clean. Next blocker: finish the remaining Jan 1 2024 forward-only core backfill gaps, especially `cross_asset_1d` and stale `econ_inflation_1d` freshness.
- 2026-03-26: Locked the Supabase Edge cron cutover guardrails. Runtime truth for recurring ingestion is `pg_cron -> pg_net -> Supabase Edge Functions -> Supabase DB`; Vercel/`npm run build` remains only the frontend app deploy gate and is not evidence that Edge Functions package, deploy, or run. Required cutover order is now: fix Supabase-function-only packaging/runtime issues, deploy each function with the Supabase toolchain, invoke each function directly with `x-cron-secret`, then apply the pg_cron cutover migration. Hard stop: do not call the cutover complete while any live pg_cron helper still targets a Vercel URL or while Edge runtime correctness is inferred from the Vercel build instead of direct function deploy/invoke proof.
- 2026-03-26: Restored `app/api/cron/google-news/route.ts` and `scripts/poll-google-news.py` as dormant research assets for later evaluation. They are intentionally unscheduled and not part of the active ingestion contract.
- 2026-03-26: Bound the active Pine path back to indicator-only by explicit user direction. The paired Pine strategy, local indicator/strategy parity, and Deep Backtesting are retired from the active blocking path. `indicators/v6-warbird-complete-strategy.pine` and `scripts/guards/check-indicator-strategy-parity.sh` remain as legacy scratch/reference surfaces only and do not block indicator work unless the plan is explicitly reopened.
- 2026-03-26: Rolled back the indicator-side fixed-color fib budget hack in `indicators/v6-warbird-complete.pine` after it changed the live operator-visible fib presentation without explicit approval. The four hidden-export removals (`ml_msb_bull_break`, `ml_msb_bear_break`, `ml_luminance_over_upper`, `ml_luminance_over_lower`) remain in both indicator and strategy to preserve parity, but the fib color inputs are restored and the live TradingView plot-budget blocker is reopened pending an approved non-visual reduction path.
- 2026-03-26: Completed a bounded Pine exhaustion-budget checkpoint in `indicators/v6-warbird-complete.pine`: removed the native exhaustion `plotshape()` and exhaustion `alertcondition()`, preserved `fib_exh_flag` logic, and moved exhaustion visibility into the bottom-left `WARBIRD METRICS` table (`EXH ON/OFF`, live energy %, `AT FIB`). Validation passed (`./scripts/guards/pine-lint.sh`, `./scripts/guards/check-contamination.sh`, `npm run build`). Next blocker remains additional live plot-count reduction to reach TradingView's `<=64` hard cap.
- 2026-03-26: Verified the backend checkpoint and tightened the remaining defects: `20260326000018` now preserves cutover state via `*_legacy_20260326` backup copies instead of renaming live production tables in place, `indicators/v6-warbird-complete.pine` and `indicators/v6-warbird-complete-strategy.pine` now export the 52-field minimum live packet (`53` and `56` total plot-style calls respectively), and `scripts/guards/check-indicator-strategy-parity.sh` now enforces real total plot counts instead of hidden-field count alone. Local gates passed (`pine-lint`, parity, `npm run build`). Next blocker is manual TradingView Strategy Tester + Deep Backtesting validation on the now-loadable scripts.
- 2026-03-26: Manual TradingView validation established the live Pine blocker the local guards had missed: TradingView enforces a hard maximum of `64` plot counts per script, hidden `display.none` plots still count, and the current Warbird indicator/strategy export surfaces exceed that budget and will not load. Repo guards and status docs were updated so parity success no longer implies loadability. The next blocking Pine checkpoint is export-budget reduction to a `<=64` live plot-count contract.
- 2026-03-26: Applied the raw-news schema (`20260326000019`) and Supabase cron wrapper migration (`20260326000020`) to the live database, created Vault route-url secrets for Newsfilter/Finnhub, and verified live pg_cron ownership for both provider pulls. Current live blocker is no longer schema or scheduling; it is the missing Vault provider secrets `warbird_newsfilter_api_key` and `warbird_finnhub_api_key`, which cause both cron wrapper functions to skip before fetch.
- 2026-03-26: Corrected Pine / TradingView toolchain reality in the active plan and docs. The current Codex profile does not actually have `pinescript-server`, a TradingView chart MCP, or a TradingView CLI configured, so any references to CLI/MCP chart capture are conditional future capability, not a current execution path. Present truth is: repo guard scripts + installed skills for Pine authoring, and manual TradingView UI for live chart validation and Deep Backtesting.
- 2026-03-26: Removed Google News from the active ingestion contract after live validation showed Google RSS article links are aggregator URLs that would require custom decoding. Deleted the Google cron route and poller, locked Newsfilter as the primary curated article source, and kept Finnhub as the secondary metadata/open-data source. Validation passed with `npm run build` and `python3 -m py_compile scripts/raw_news_contract.py scripts/poll-finnhub-news.py scripts/poll-newsfilter-news.py`.
- 2026-03-26: Absorbed execution delta for the fib-engine and validation contract: AG/training must use point-in-time fib snapshots materialized from confirmed lookback/confluence state instead of repaint-prone live chart reads, Deep Backtesting is required but not sufficient by itself, pivot state is a critical trigger/reversal gate (distance matters, but it is not the sole decision maker), intermarket trigger alignment must respect each symbol's correlative path across 15m/1H/4H, and overlapping MA/volume/trend features across the three installed harnesses must be de-duplicated by feature family.
- 2026-03-26: Completed a bounded `news_signals` contract-alignment checkpoint: added `supabase/migrations/20260326000016_news_signal_direction.sql` with a dedicated `market_impact_direction` enum, updated the active news writers at that checkpoint to emit `BULLISH` / `BEARISH`, normalized dataset readers for legacy plus new values, and validated with `npm run build` plus `python3 -m py_compile scripts/build-dataset.py`. Next blocker: pair promoted news signals with MES price-action context before live use, then replace the legacy `warbird_forecasts_1h` path.
- 2026-03-26: Locked the balanced architecture decision: production remains cloud-first (`provider -> cloud Supabase -> live routes/dashboard`), the local database is snapshot-based training/research only, legacy `warbird_forecasts_1h` semantics are retired in favor of MES 15m fib-outcome state (`tp1_probability`, `tp2_probability`, `reversal_risk`), and `news_signals` is locked as a derived `BULLISH`/`BEARISH` event-response surface that must be paired with price action before promotion.
- 2026-03-26: Cut MES live ingestion to a Supabase-owned minute schedule (`supabase/migrations/20260326000015_mes_1m_supabase_cron.sql`) that calls `/api/cron/mes-1m`, removed the Supabase `mes-catchup` schedule, and reduced live MES processing to incremental `ohlcv-1m` pulls with touched-bucket `mes_15m` rollups only; `mes-catchup` now remains manual backfill/rebuild-only.
- 2026-03-24: Applied TradingView dashboard correction in Phase 3 manual-validation path: top-right table offset tuned (down/left via spacer row/col), correlation view switched from single-symbol to the plan-frozen cross-asset set (`NQ`, `DXY`, `US10Y`, `VIX`), and strategy-side top-right panel now includes closed trades, win rate, wins/losses, and profit factor. Operator note: `1h` signal preference observed, but canonical contract remains MES `15m` unless the plan lock is explicitly reopened.
- 2026-03-24: Added Massive provider limit guards (bounded retries, `429` handling, `Retry-After` compliance, exponential backoff) in both live cron ingestion and the 2-year backfill path to keep inflation-expectations pulls stable under plan limits.
- 2026-03-24: Validated Massive REST auth with `MASSIVE_API_KEY` in `.env.local`, confirmed `GET /fed/v1/inflation-expectations` live pull, and completed 2-year backfill (`scripts/backfill-massive-inflation-expectations.py`) writing 165 rows across 7 provider-tagged inflation-expectation series into `econ_inflation_1d` (`2024-04-01` to `2026-03-01`).
- 2026-03-24: Implemented `MASSIVE_API_KEY` runtime wiring in `.env.local`, added Massive inflation-expectations ingestion (`/api/cron/massive/inflation-expectations` + `scripts/backfill-massive-inflation-expectations.py`), and deactivated FRED `T5YIE`/`T10YIE` to prevent source overlap.
- 2026-03-24: Locked a provider-agnostic macro requirement for Phase 4 (`yields`, `inflation`, `inflation expectations`, `labor market`) with Massive `/fed` endpoints approved as optional parity/fallback ingestion while Databento remains the only intraday market-data contract.
- 2026-03-24: Validated Newsfilter Query API auth/endpoint docs and live endpoint behavior; access is API-key gated (`POST https://api.newsfilter.io/search`) and remains blocked as `pending_provider_access` until a valid key is issued.
- 2026-03-24: Added a curated Newsfilter tertiary raw-news contract (exact source allowlist + S&P/watchlist gating) under the same Phase 4 Google/Finnhub raw-news workflow and promotion gates.
- 2026-03-24: Added a Phase 4 plan delta for a lean Finnhub open-data secondary news feed folded into the existing Google News work, with strict relevance gating and no premium sentiment/tick dependencies.
- 2026-03-24: Added an explicit Phase 3 manual TradingView Strategy Tester + Deep Backtesting validation protocol, evidence checklist, and close criteria to unblock deterministic Phase 3 closure before Phase 4.
- 2026-03-24: Completed Phase 3 checkpoint 2 local parity preflight by adding `scripts/guards/check-indicator-strategy-parity.sh`, validating hidden export parity and core predicate/encoding parity between indicator and strategy, and locking manual TradingView Deep Backtesting as the remaining blocker.
- 2026-03-24: Completed Phase 3 checkpoint 1 by creating `indicators/v6-warbird-complete-strategy.pine` as a true Pine `strategy()` with indicator-parity entry predicates, deterministic stop/target execution using the locked stop-family + `20pt+` gate, and full hidden export contract parity with `indicators/v6-warbird-complete.pine`; validation gates passed.
- 2026-03-24: Completed Phase 2 implementation checkpoint 5 in `indicators/v6-warbird-complete.pine` by replacing the interim local pivot path with admitted BigBeluga harness signals, wiring admitted LuxAlgo MSB/OB + Luminance export families into the always-on hidden contract, and reclassifying setup-event wiring to harness-backed states; validation gates passed.
- 2026-03-24: Plan delta absorbed from execution directive: `Luminance Breakout Engine [LuxAlgo]` is now a required exact-copy standalone harness (not later-phase candidate).
- 2026-03-24: Completed Phase 2 implementation checkpoint 4 by admitting the required standalone exact-copy `Luminance Breakout Engine [LuxAlgo]` harness at `indicators/harnesses/luxalgo-luminance-breakout-engine-harness.pine`, confirming source access, and wiring hidden luminance harness exports for training capture.
- 2026-03-24: Completed Phase 2 implementation checkpoint 3 by admitting the required standalone exact-copy `Market Structure Break & OB Probability Toolkit [LuxAlgo]` harness at `indicators/harnesses/luxalgo-msb-ob-probability-toolkit-harness.pine`, confirming source access, and wiring hidden MSB/OB harness exports for training capture.
- 2026-03-24: Completed Phase 2 implementation checkpoint 2 by admitting the required standalone exact-copy `Pivot Levels [BigBeluga]` harness at `indicators/harnesses/bigbeluga-pivot-levels-harness.pine`, confirming source access, and wiring hidden pivot harness exports for training capture.
- 2026-03-26: Supabase is now the sole cron/function producer. `score-trades` Supabase pg_cron stopped and removed from `Supabase cron migration files`. All recurring job scheduling is Supabase pg_cron only. The app runtime is frontend dashboard and route handlers only.
- 2026-03-26: Completed cost/abuse hardening checkpoint: public read APIs now require authenticated user cookies instead of service-role reads, admin coverage moved to low-cost Supabase RPC + 5 minute polling, dashboard duplicate polling collapsed, FRED and cross-asset ingestion made incremental, measured-moves retired as a writer in favor of `detect-setups`, dedup loops moved to unique-key upserts, and cron auth now fails closed when `CRON_SECRET` is missing.
- 2026-03-24: Completed Phase 2 implementation checkpoint 1 in `indicators/v6-warbird-complete.pine`: structural fib-direction hardening, explicit directional `0/1` levels, bounded stop-family + `20pt+` eligibility interface, always-on hidden export contract fields, and the first always-on hidden event-response block; validation gates passed.
- 2026-03-23: Rewrote the active plan from the live audit: locked current Supabase pg_cron reality vs target Supabase-owned runtime, exact Databento/FRED/news scope, raw Google News intake contract, cloud realtime/dashboard surfaces, and the 2-consecutive-PT1-miss rollback rule.
- 2026-03-23: Absorbed the March 23 execution delta into an explicit phase-order lock and recorded a Phase 2 kickoff audit against `indicators/v6-warbird-complete.pine`.
- 2026-03-23: Added audited Phase 4 operations requirements for the local PostgreSQL training warehouse, cloud publish-up tables, and packet / run lifecycle after verifying the linked Supabase project and live Supabase schema.
- 2026-03-23: Added phased execution guide for canonical 15m contract, cloud-first production plus local training publish-up flow, third-party Pine admission gate, BigBeluga pivot replacement, required harness-module admission for BigBeluga plus LuxAlgo Market Structure Break & OB Probability Toolkit, and later-phase candidate evaluation rules.
- 2026-03-22: Added dependency-security remediation checkpoint order (plan updates first, then implementation). Scope includes Next.js and transitive lockfile remediation plus `xlsx` ingestion-surface removal/replacement.
- 2026-03-20: Converted the active plan into a single-indicator plan.
- 2026-03-20: Archived older plan docs and removed them from the active path.
- 2026-03-20: AG model concept — fib continuation probability engine with TP1/TP2 targets (1.236/1.618 extensions), re-entry signals, full macro/economic training context, and Pine config packet output.
- 2026-03-20: Added "AG Models Pine's Configuration Space" — AG output must be Pine-native (exact input values, thresholds, weights, gates, module decisions).
- 2026-03-20: Added Forensic Review of current script — 8 high-risk problems to fix before AG training.
- 2026-03-20: Restructured plan around Canonical Goal / Canonical Outputs / Canonical Standards / Locked v1 Mechanisms. The product goal and chart-output surface are canonical. The v1 build path is now locked.

---

## Supabase Edge Cutover Guardrails (2026-03-26)

This checkpoint is binding for the current ingestion-runtime migration.

1. Runtime truth for recurring ingestion is `pg_cron -> pg_net -> Supabase Edge Functions -> Supabase DB`.
2. Vercel remains the frontend/dashboard app deploy surface only. `npm run build` is still required before push, but it is **not** proof that `supabase/functions/*` package or run.
3. The old App Router cron routes are reference-only during the port. They are not the acceptance surface for the cutover.
4. Required fix order:
   - Fix Supabase-function-only packaging/runtime issues first.
   - Keep imports and configuration Supabase/Deno-native.
   - Deploy each function through the Supabase toolchain.
   - Invoke each deployed function directly with `x-cron-secret`.
   - Apply the pg_cron cutover migration only after direct function invocation succeeds.
5. Required Supabase-native constraints:
   - `verify_jwt = false` per cron-called function in `supabase/config.toml`
   - `x-cron-secret` header validation inside each Edge Function
   - Edge Function secrets, not Vercel headers, for provider/API keys
   - function-local dependency/config handling that follows official Supabase Edge Function docs when `npm:`, `node:`, or JSON module imports are used
6. Hard stops:
   - Do not mark the cutover complete while any live pg_cron helper still targets a Vercel URL.
   - Do not use Vercel build success as evidence that the Edge runtime is healthy.
   - Do not apply the cutover migration before the target Edge Functions deploy and respond successfully via their `/functions/v1/<name>` URLs.
7. Minimum proof required before close:
   - each target function deployed
   - each target function invoked directly with `x-cron-secret`
   - live Vault has the edge base URL and edge cron secret
   - live Edge Function secrets exist for provider/data-source credentials
   - pg_cron helper functions point to `https://qhwgrzqjcdtdqppvhhme.supabase.co/functions/v1/<name>`

---

## Security Remediation Checkpoint (2026-03-22)

This checkpoint is execution-ordered and is part of the active plan:

1. Update plan state and remediation intent in docs first.
2. Patch all open Dependabot vulnerabilities in the repository.
3. Run verification gates (`npm audit`, `npm run build`) before merge/push.

Locked constraints for this checkpoint:

- Keep scope minimal to vulnerability closure and direct runtime-path disambiguation.
- No unrelated refactors.
- Preserve production boundary rules and cron guardrails.
- Keep dependency changes explicit and auditable in lockfile history.

---

## Canonical Goal

Deliver the best possible **fib continuation/reversal entry indicator** on TradingView for MES, with:

- actionable entries on chart
- TP1 (1.236 extension) and TP2 (1.618 extension) path visualization
- an early-warning exhaustion diamond that can lead a later trigger by a few bars
- a mirrored dashboard operator surface that renders the same fib engine state with probabilities, audit stats, and richer cross-asset visuals than Pine can support
- AG used aggressively to improve it offline
- manual chart validation plus point-in-time dataset checks used to prove it

The goal is canonical. Whatever it takes to get there is what we do.

---

## Canonical Outputs (split by surface)

These are the required outputs. Each must map to a defined calculation. Each must come from real data.

### TradingView / Pine

| Output | Definition |
|--------|-----------|
| **Entry marker** | Exact bar where the indicator publishes a trade signal at a fib pullback level |
| **Decision state** | `TAKE_TRADE`, `WAIT`, or `PASS` for the current candidate. This is a policy decision, not a realized outcome. |
| **Target eligibility** | 20pt+ pass/fail |
| **Stop level** | From a bounded, deterministic stop family — not a per-trade model output |
| **TP1 / TP2 levels** | The 1.236 and 1.618 fib extension prices |
| **Fib / pivot / zone lines** | The operator-visible execution geometry from the canonical fib engine, rendered with the operator-approved colors, line widths, line styles, and level labeling contract |
| **Exhaustion diamond** | A precursor visual that can warn ahead of a later trigger when exhaustion context is active at a fib or pivot interaction |
| **Re-entry signal** | When a pullback after TP1 is a continuation opportunity |

### Dashboard / Operator Surface

| Output | Definition |
|--------|-----------|
| **TP1 probability** | Probability the current setup reaches the 1.236 fib extension. Must be defensible and calibrated — when it says 70%, it should be right about 70% of the time. |
| **TP2 probability** | Probability the current setup reaches the 1.618 fib extension. Same calibration standard. |
| **Reversal risk** | Probability that the continuation fails into a reversal or shock-failure path. |
| **Win rate** | Historical hit rate for the current setup bucket (fib level, regime, session, direction). Based on real backtested data, not a guess. |
| **Stats window** | What history/regime/sample the displayed numbers are based on |
| **MAE / MFE context** | Expected and bounded excursion context used to support the displayed probabilities |
| **Decision reasons** | Why the policy is currently `TAKE_TRADE`, `WAIT`, or `PASS` |
| **Cross-asset visuals** | Time-synced operator charts and regime state that Pine cannot carry as chart tables |

---

## Canonical Standards

1. Every stat on the chart must come from real data — never mocked, never fabricated.
2. Every probability/win rate must be defensible and calibrated.
3. Whatever appears in TradingView or the dashboard must map to a defined calculation.
4. Pine must remain the visible production surface.
5. AG is offline only — never in the live signal path.
6. The dashboard may be visually richer than Pine, but it must render the same canonical fib engine state rather than compute a second fib engine locally.
7. Visual chart validation and local point-in-time dataset checks must agree closely enough before a fib or trigger mechanic is trusted.
8. The operator-approved fib presentation is a visual contract. Colors, line thicknesses, line styles, and level-label presentation may not change without explicit approval.
9. Deep Backtesting and paired-strategy parity are optional research tools only; they are not active blockers for the indicator path unless explicitly reopened.
10. **NEVER hand-roll code when a working implementation exists.** Copy the exact working code. Adapt the interface, not the internals. If you can't explain why your version differs line-by-line, you don't understand it well enough to rewrite it. Hand-rolled library integrations produce broken signals that poison AG training data.

---

## Hierarchy Lock (2026-03-28)

This hierarchy is now binding for the active path:

1. **Trading objective**
   - improve MES 15m fib-based entries so more valid setups reach TP1 / TP2 and fewer low-quality entries stop out
2. **Canonical trade object**
   - one frozen MES 15m fib candidate at bar close
3. **Truth contract**
   - the primary economic questions are extension attainment versus stop failure on that frozen candidate
   - unresolved rows remain `OPEN` until they resolve; `OPEN` is operational-only and excluded from training labels
4. **Canonical schema**
   - stores point-in-time setup truth, realized path truth, and published signal lineage
5. **Feature / research layer**
   - stores explanatory and experimental context that may change over time
6. **Model stack**
   - selected to answer the truth contract, not to redefine it

Warbird is split into three engines:

- **Generator**
  - Pine and admitted exact-copy harnesses define the candidate entry object
- **Selector**
  - offline models score whether a candidate is worth taking
- **Diagnostician**
  - local research explains why trades won/lost and what should change in features, settings, or entry definition

Boundary rules:

1. Canonical cloud tables must not become feature soup.
2. SHAP outputs, ablation results, stop-out attribution, and parameter-search artifacts are research-only until explicitly promoted.
3. AutoGluon is the first selector layer. It is not the owner of the canonical schema.
4. Quantile/pinball models are for excursions and uncertainty bands, not primary extension-hit truth.
5. Monte Carlo is downstream policy simulation, not label definition.
6. Volatility sidecars such as GARCH are optional feature families that must earn inclusion through lift and stability evidence.

---

## Locked v1 Mechanisms

The chart-output surface is canonical. The v1 mechanism for producing those outputs is now locked.

### Primary v1 delivery path

Use a **hybrid Pine + AG packet** architecture:

1. Pine computes the canonical adaptive fib engine snapshot, candidate state, precursor visuals, and the deterministic `confidence_score` from current bar context.
2. AG trains offline on point-in-time fib engine snapshots, calibrates the score, and produces a Pine-ready packet of:
   - score-to-probability mappings
   - win-rate tables
   - reversal-risk tables
   - stop-family decisions
   - module keep/remove calls
   - exact Pine input values
3. Pine renders only the execution-facing chart surface:
   - fib / pivot / zone lines
   - entry markers
   - bounded stop and target levels
   - exhaustion precursor diamond
   - alertconditions
4. The dashboard renders the operator-facing stats and visuals by:
   - identifying the current setup bucket
   - identifying the current confidence bin
   - looking up the calibrated TP1 / TP2 / reversal / win-rate stats from the latest promoted packet
   - rendering cross-asset and sentiment views from the same MES 15m contract

This is the primary v1 path.

### Allowed fallback

If the full bucketed calibration surface is too sparse in early testing, the fallback is:

- Pine-embedded probability bands keyed off fewer variables
- coarser confidence bins
- coarser bucket hierarchy

Fallback is allowed only if it preserves defensible calibration and real sample counts.

### Update cadence

The packet update cadence for v1 is:

- offline retrain / recalibration on demand during development
- promoted packet refresh no more than once per week in normal operation

No intraday live model serving.

### Locked dashboard-stat formulas

These definitions are canonical for v1:

- `confidence_score`
  - deterministic Pine score on a `0-100` scale computed from live Pine features and rules
- `tp1_probability_display`
  - empirical TP1 hit rate for the current `setup_bucket x confidence_bin`, calibrated offline by AG
- `tp2_probability_display`
  - empirical TP2 hit rate for the current `setup_bucket x confidence_bin`, calibrated offline by AG
- `reversal_risk_display`
  - empirical `REVERSAL` rate for the current `setup_bucket x confidence_bin`
- `win_rate_display`
  - empirical rate of `TP1_ONLY OR TP2_HIT` for the current `setup_bucket x confidence_bin`
- `stats_window_display`
  - training date range + sample count used for the displayed bucketed stats

### Locked bucket hierarchy

#### Confidence bins

Use 5 bins for v1:

- `BIN_1 = 0-19`
- `BIN_2 = 20-39`
- `BIN_3 = 40-59`
- `BIN_4 = 60-79`
- `BIN_5 = 80-100`

#### Setup bucket key

The primary bucket key is:

- `direction`
- `setup_archetype`
- `fib_level_touched`
- `regime_bucket`
- `session_bucket`

#### Setup archetype values

Use these v1 archetypes:

- `ACCEPT_CONTINUATION`
- `ZONE_REJECTION`
- `PIVOT_CONTINUATION`
- `FAILED_MOVE_REVERSAL`
- `REENTRY_AFTER_TP1`

#### Regime bucket values

Use these v1 regime buckets:

- `RISK_ON`
- `NEUTRAL`
- `RISK_OFF`
- `CONFLICT`

#### Session bucket values

Use these v1 session buckets in `America/Chicago`:

- `RTH_OPEN = 08:30-09:30`
- `RTH_CORE = 09:30-11:30`
- `LUNCH = 11:30-13:00`
- `RTH_PM = 13:00-15:00`
- `ETH = all other bars`

### Locked bucket fallback ladder

If the current `setup_bucket x confidence_bin` does not meet the minimum sample floor, Pine must walk this fallback ladder:

1. `direction x setup_archetype x fib_level_touched x regime_bucket x session_bucket x confidence_bin` with `n >= 40`
2. `direction x fib_level_touched x regime_bucket x session_bucket x confidence_bin` with `n >= 60`
3. `direction x fib_level_touched x regime_bucket x confidence_bin` with `n >= 80`
4. `direction x fib_level_touched x confidence_bin` with `n >= 120`
5. `direction x confidence_bin` with `n >= 200`
6. global confidence-bin baseline

If even the final fallback is under-sampled, Pine must display `LOW SAMPLE` and suppress the stat as actionable.

### Stop logic — bounded Pine-implementable family

AG does NOT invent a per-trade stop. AG chooses among a **bounded family** of deterministic stop methods that Pine can implement:

1. Fib invalidation (break below the fib level touched)
2. Fib invalidation + ATR buffer
3. Structure breach (break of swing low/high)
4. Fixed ATR multiple from entry

AG's job: evaluate which stop family member works best for which fib level / regime, and output that as a Pine config decision. Not a learned float.

---

## Scope (updated 2026-03-27)

This plan covers the full MES 15m fib-outcome contract:

- the live Pine indicator (`indicators/v6-warbird-complete.pine`)
- the mirrored dashboard operator surface (render-only consumer of the canonical fib engine state)
- the canonical Supabase schema for snapshots, candidates, outcomes, signals, and packets
- the Edge Function writers that produce canonical rows
- the offline AG optimization loop that tunes the indicator and produces packets
- the local training warehouse and publish-up lifecycle

This plan does not include:

- the paired Pine strategy (research-only unless explicitly reopened)
- Deep Backtesting as an active delivery blocker
- FastAPI
- Cloudflare Tunnel
- live AG inference
- browser extensions that inject TradingView inputs

---

## Core Architecture

### Live Trading

The live chart runs a Pine **indicator**.

That indicator must:

- calculate all live signal logic inside Pine
- pull all permitted live external series through TradingView-supported `request.*()` calls
- draw the fib structure and entry context on the chart
- keep dense operator tables off-chart and emit only the execution-facing TradingView surface
- fire alerts from Pine only

### Validation

Validation for the active path is indicator-only.

Active validation exists to:

- verify live chart behavior on the canonical MES `15m` surface
- confirm the operator-visible table/levels/labels are correct
- check point-in-time dataset alignment for AG and offline analysis
- reject regressions before they contaminate offline calibration work

### Optimization

AutoGluon is not connected live to the chart.

AutoGluon exists only to:

- rank which settings and features improve entry quality
- identify noisy settings to remove
- suggest tighter parameter ranges
- help choose the next Pine parameter set to test

The live chart never waits on AG.

---

## Non-Negotiable Rules

1. If Pine cannot compute it or request it live from TradingView-supported data, it cannot be part of the live signal.
2. Every live entry must be explainable from Pine-visible state on that bar.
3. No hidden server-side decision engine.
4. No dynamic input injection hacks.
5. The indicator is the only active Pine surface. Any strategy file is research-only and cannot block indicator work unless explicitly reopened.
6. The optimization target is not “looks smart.” It is entry quality:
   - reaches TP1 / TP2 with the `20pt+` eligibility gate satisfied
   - acceptable adverse excursion
   - acceptable signal count

---

## What Must Change In The Current Script

### Required Functional Changes

1. ~~Add explicit **0 fib line**.~~ DONE.
2. ~~Add explicit **1 fib line**.~~ DONE.
3. ~~Promote the script from a structure/regime overlay into a true **entry engine**.~~ DONE.
4. ~~Separate the code into fib engine, intermarket engine, entry predicate, visuals.~~ DONE.
5. ~~Add a side table area on the chart edge.~~ Moved to dashboard — TradingView chart tables retired from active path.
6. ~~Add entry markers that show exactly where the trade is actionable.~~ DONE.
7. ~~Add a strict 20-point minimum target gate.~~ DONE.

### Required Design Changes

1. ~~Stop treating intermarket as just confirmation color.~~ DONE — weighted scored regime with hysteresis.
2. ~~Turn every external series into a scored feature or explicit gate.~~ DONE.
3. ~~Reduce duplicated logic and repeated `request.*()` calls.~~ DONE — 6 of 40 budget used.
4. ~~Build one shared rule block for both the indicator and the strategy.~~ Retired — strategy path retired 2026-03-26.

---

## Forensic Review Of The Current Script

This review exists to carve off weak mechanics before AG training and before Deep Backtesting becomes the validation source.

### Forced Review Standard

This section is not a generic cleanup list. It is a forced **high-reason logic review**.

Every major module must be reviewed:

1. **Before** changes
   - identify what the module is actually doing
   - identify what the module claims to be doing
   - identify where those differ
   - identify whether the current mechanic is valid for live Pine, export, Deep Backtesting, and AG training
2. **During** redesign
   - compare at least two viable replacements when the mechanic is weak
   - choose the simpler mechanic unless the stronger one has a clear material advantage
   - document why the chosen replacement is more trustworthy
3. **After** implementation
   - verify the mechanic is internally coherent
   - verify the mechanic is Pine-reproducible
   - verify the mechanic exports usable data if AG needs it
   - verify the mechanic works identically enough for both indicator and strategy use

No module should move into AG training or Deep Backtesting just because it “looks better.” It must survive a high-reason logic review first.

### High-Risk Problems To Resolve Before AG

1. The intermarket MTF mechanics are not trustworthy yet.
   - `request.security()` is pulling `close` from `tfIM`, but EMA and slope are then computed on the chart timeframe from repeated higher-timeframe values.
   - That distorts `maLen`, `slopeBars`, and the regime logic.
   - Direction:
     - compute EMA, slope, and any regime-state transforms inside the requested timeframe context
     - reduce the intermarket engine to a small set of defensible states first: trend, slope, distance-from-mean, agreement
     - prove the higher-timeframe implementation in Deep Backtesting before letting AG optimize its settings

2. The news proxy mechanics are too weak for v1.
   - The current proxy uses lower-timeframe `request.security()` and then measures lookback on chart bars, not proxy-timeframe bars.
   - It also hard-overrides `riskOn` / `riskOff`, which is too aggressive for a synthetic news proxy.
   - Direction:
     - demote this to a secondary modifier, not a hard regime override
     - prefer deterministic macro-event windows and Pine-supported economic context before synthetic lower-timeframe shock logic
     - only restore a richer macro proxy if it survives a separate reasoning and validation pass

3. Fib direction is too unstable.
   - `fibBull = close >= fibMidpoint` lets direction flip based on current price location inside the range, not on a true swing-leg definition.
   - That can invert base, direction, and targets without a real structural change.
   - Direction:
     - replace midpoint direction with an ordered swing-leg or anchored-leg direction model
     - direction should change only when structural conditions justify a new leg, not when price floats around the midpoint
     - make leg direction a first-class exported state for both strategy and AG dataset building

4. The confluence anchor is not yet a validated continuation anchor.
   - The `8/13/21/34/55` window family is a reasonable candidate search space.
   - But the current chooser is range-based, not explicitly continuation-based.
   - Direction:
     - keep the window family, but test it as a candidate leg-definition surface rather than assuming it is already correct
     - compare the current confluence chooser against at least one more explicit continuation-leg method
     - promote only the anchor logic that produces the cleanest continuation/reversal separation in Deep Backtesting

5. The script has no deterministic trade contract yet.
   - There is no explicit entry price rule.
   - There is no stop family.
   - There is no strict `+20` eligibility gate.
   - Without those, Deep Backtesting cannot prove anything and AG labels like `reached_tp1`, `reached_tp2`, and `outcome` are not well-defined.
   - Direction:
     - define one explicit trade contract for v1: entry trigger, stop family, target path, invalidation rule
     - treat stop logic as a bounded family AG may select from, not an unconstrained learned artifact
     - freeze the `+20` rule as an eligibility gate before dataset labels are generated

6. Core fib/entry data is drawn, not exported.
   - The script currently renders important levels with line objects while the `plot()` calls are `na`.
   - For TradingView export and dataset-building, key levels and states must exist as plotted or otherwise extractable Pine series.
   - Do not rely on visual line objects as the feature-export surface.
   - Direction:
     - promote all key fib levels, state flags, and eligibility states into exportable series
     - separate chart rendering from dataset exposure
     - build the strategy/indicator shared core so export-worthy series are explicit, named, and stable

7. The optimization surface currently includes noise.
   - Visual toggles, colors, widths, lookback draw settings, and line-extension settings are not AG targets.
   - `oneShotEvent` is also not part of the true market model and should not be treated as a core optimization variable.
   - Direction:
     - divide settings into three buckets:
       - AG-searchable market logic
       - Pine-required but non-searchable structural settings
       - visual-only settings
     - only the first bucket belongs in the AG optimization surface

8. The symbol set is not frozen yet.
   - `NQ`, `VIX`, `DXY`, and `US10Y` are reasonable first-pass candidates.
   - `BANK`, credit proxies, oil, and any additional cross-asset series must be verified and justified before they are allowed into the production contract.
   - Direction:
     - start with the smallest defensible live series set
     - add `BANK`, credit, oil, or additional symbols only if holdout and Deep Backtesting evidence show material value
     - do not let AG search a drifting symbol universe

### Keep As Candidate Logic

- confluence-anchor concept
- `8/13/21/34/55` anchor family as a candidate search space
- accept / reject / retest structure archetypes
- weighted intermarket regime concept
- `NQ`, `VIX`, `DXY`, `US10Y` as first-pass context candidates

### Cut Or Demote For v1 Until Proven

- lower-timeframe news proxy as currently written
- hard override of `riskOn` / `riskOff` from the news proxy
- visual/style settings from the AG search space
- `oneShotEvent` from the AG search space
- arbitrary symbol expansion before the live-series inventory is frozen

### Must Be Built Before Deep Backtesting And AG

1. ~~Rebuild intermarket EMA/slope so requested-timeframe logic is computed correctly.~~ DONE.
2. ~~Replace midpoint-based fib direction with a true ordered swing-leg direction model.~~ DONE.
3. ~~Add explicit `0` and `1` fib lines.~~ DONE.
4. ~~Add a deterministic stop family.~~ DONE — bounded family with fib invalidation, fib+ATR, structure breach, fixed ATR.
5. ~~Add the strict `+20` eligibility gate.~~ DONE.
6. ~~Expose key fib and state values as exportable Pine series.~~ DONE — 60 hidden exports.
7. ~~Build the paired Pine strategy.~~ Retired — strategy path retired 2026-03-26.

### Preferred Directional Replacements

When a module is marked weak, prefer these replacements unless a better alternative survives review:

- Intermarket MTF:
  compute state in-request rather than deriving it from repeated requested closes on the chart timeframe
- Macro/news:
  deterministic event windows and Pine-supported macro context before synthetic lower-timeframe shock proxies
- Fib direction:
  anchored leg-direction logic rather than midpoint state flips
- Anchor selection:
  continuation-valid leg selection rather than visually convenient range capture
- Stop logic:
  bounded stop families with explicit invalidation rules rather than vague adaptive stops
- Export surface:
  named series for every AG-relevant state rather than line-object-only visuals
- AG search space:
  market-logic settings only, never visual or presentation settings

### Order Of Operations

1. Run the high-reason logic review on each core module.
2. Harden the mechanics with directional replacements, not ad hoc tweaks.
3. Build the strategy and establish baseline Deep Backtesting behavior.
4. Freeze the surviving feature and setting surface.
5. Export valid feature columns.
6. Let AG optimize only the hardened Pine surface.

### Rule

AG is not allowed to optimize broken mechanics.

If a setting or module is not mechanically trustworthy in Pine first, it does not belong in the AG search space yet.

The bar for promotion is:

- logically coherent
- Pine-valid
- export-valid if AG needs it
- Deep Backtesting-valid
- simple enough to defend

---

## Live Data Boundary

### Pine Can Pull Live

The indicator may use TradingView-supported live pulls such as:

- `request.security()` for market symbols and proxies
- `request.economic()` for supported economic series
- built-in chart OHLCV and any requested symbol OHLCV

### Pine Cannot Pull Live

The indicator cannot depend on:

- arbitrary HTTP APIs
- local files
- Supabase rows
- Python outputs
- custom AG predictions

### Implication

All “advanced” logic must be built from:

- MES price and volume
- requested intermarket symbols
- requested economic series
- Pine-computed derived features

---

## Live Inputs To Build

### A. Fib Structure Engine

Keep and improve:

- confluence anchor selection
- active fib period selection
- structural break re-anchoring
- zone logic
- lookback intelligence beyond a simple zigzag
- point-in-time anchor stability suitable for offline snapshot materialization

Add:

- `0` line
- `1` line
- explicit distance to 0 / 1 / pivot / zone / target
- target-size eligibility gate for the 20-point requirement

### B. Intermarket Engine

**SUPERSEDED (2026-03-30):** The v1 intermarket basket below was replaced with flow-based LEADING indicators. See v7 design doc for current basket.

~~Locked v1 live intermarket series: NQ1!, BANK, VIX, DXY, US10Y, HYG, LQD~~ — REPLACED

**Current v7 intermarket basket (flow-based leading indicators):**

- `USI:TICK` — NYSE uptick/downtick (institutional program trading, zero threshold)
- `USI:VOLD` — NYSE up vol − down vol (money flow, zero threshold)
- `CBOE:VVIX` — Vol of vol (leads VIX by 1-3 bars, level threshold)
- `CBOE:VIX` + `CBOE:VIX3M` — VIX term structure ratio (< 0.92 calm, > 1.0 stress)
- `AMEX:HYG` — High-yield credit (EMA trend, credit leads equity)
- `CME_MINI:RTY1!` — Russell 2000 small-cap (EMA trend, breaks down/recovers first)
- `CBOE:SKEW` — Tail-risk hedging (daily level threshold)
- `USI:ADD` — NYSE Advance-Decline breadth (daily, divergence = exhaustion)

Regime gate: all 7 must agree for confirmation. No weighted scoring. Hysteresis: 3 bars to flip, 4 bars cooldown, 16 bars neutralize stale. AG decides correlations and weights from data.

Intermarket trigger rule:

1. TICK + VOLD are the anchor — institutional flow is the foundation. Both must agree.
2. All 7 symbols must agree for regime confirmation. No partial credit, no weighted scoring.
3. AG will discover optimal thresholds and correlations via SHAP. Hand-coded values are starting points only.

### C. Volatility / Credit / Macro Engine

The plan uses only TradingView-available live series.

Locked v1 live macro / credit inputs:

- VIX
- US10Y
- credit proxy = `HYG / LQD`
- `request.economic("US", "IRSTCB01")` for Fed funds
- `request.economic("US", "CPALTT01")` for CPI YoY
- `request.economic("US", "LRHUTTTTUSM156S")` for unemployment
- `request.economic("US", "BSCICP02")` for PMI manufacturing
- Pine calendar logic for `is_fomc_week`, `is_cpi_day`, `is_nfp_day`

Important constraint:

- “Credit” is not assumed to exist as a magical direct feed.
- `VVIX`, `JNK`, GDP growth, and any extra economic fields are v2 candidates, not v1 requirements.

### D. Volume Engine

“Volume of all types” will be interpreted as Pine-available volume state, not fictional order-book access.

Planned volume features:

- chart volume
- relative volume vs rolling baseline
- volume acceleration
- bar spread x volume interaction
- cross-asset volume proxies where the requested symbols expose volume

No unsupported order-book assumptions will be baked into v1.

### E. Session / Market State Engine

Planned live session features:

- regular session / overnight state
- session opening shock window
- lunch/noise window
- time-since-break
- bars-since-zone-touch
- bars-since-regime-flip

---

## Entry System Definition

The entry system is not “any accept/reject event.”

It becomes a scored entry predicate that must answer one question:

**Is this bar an entry worth taking if it passes the `20pt+` eligibility gate and has a credible path to TP1 / TP2?**

### Entry Predicate v1

A valid entry must include:

1. valid fib anchor and non-degenerate range
2. valid 20+ point path to target
3. acceptable structure event
4. acceptable intermarket regime
5. acceptable volatility / credit / macro state
6. acceptable volume state
7. no explicit conflict state

### Structure Event Candidates

The strategy will compare at least these structure archetypes:

- break -> retest -> accept
- rejection from decision zone
- pivot reclaim / pivot loss
- continuation after one clean pullback
- reversal after regime-aligned failed move

### Decision States

The policy layer should output one clear decision state:

- `TAKE_TRADE`
- `WAIT`
- `PASS`

These are decision codes only. Realized outcome labels remain separate.

---

## Shared Pine Architecture

One Pine artifact is active on the live path:

### 1. Live Indicator

Purpose:

- chart visualization
- live entry markers
- exhaustion precursor diamond
- alerts
- hidden export packet

Required outputs:

- 0 / 1 / pivot / zone / target lines
- entry markers
- stop
- target 1
- target 2
- exhaustion precursor diamond
- alertconditions
- hidden export packet

### 2. Research Strategy Surface (legacy unless explicitly reopened)

Purpose:

- Deep Backtesting
- historical parameter comparison
- trade outcome measurement

This surface is reference-only unless a newer update-log entry explicitly reactivates it.

### Shared Core

These must remain identical between any research strategy and the live indicator whenever the strategy path is reopened:

- fib anchor selection
- external series pulls
- feature calculations
- entry predicate
- target eligibility logic

---

## Dashboard Operator Surface Plan

TradingView chart tables are retired from the active path. The dashboard is the operator-facing surface for dense state, stats, and cross-asset visuals, but it must render the same MES 15m fib engine state rather than recompute fib geometry locally.

### Dashboard Contents v1

Top block:

- symbol
- timeframe
- active fib engine version
- direction

Signal block:

- decision state
- target eligibility (`20pt+` pass/fail)
- entry price
- stop level
- target 1
- target 2
- exhaustion precursor state

Regime block:

- intermarket regime
- volatility state
- credit state
- macro posture

Component block:

- NQ
- BANK
- VIX
- DXY
- US10Y
- credit proxy
- volume state

Structure block:

- break / accept / reject state
- bars since event
- active score

### Visual Direction

The dashboard should feel dense and intentional, not like default Pine debug output:

- compact
- synchronized around the main MES chart
- readable at trading size
- color-coded state bars
- minimal wasted text

Mini charts for correlation symbols and richer sentiment/regime visuals are explicitly allowed here. Arc gauges are optional. Decision reasons, state bars, and synchronized context are the priority.

### Locked Fib Visual Inventory (TV Settings Capture 2026-03-27)

The screenshots captured on 2026-03-27 are now the operator-approved level inventory for the visible fib surface. The rebuild must preserve these active levels, labels, and color families unless explicitly reapproved.

| Level | Role | Label / Text | Color family | Default visibility |
| --- | --- | --- | --- | --- |
| `0.382` | retracement | `.382` | orange | active |
| `0.500` | midpoint | custom midpoint text | white | active |
| `0.618` | retracement | `618` | orange | active |
| `0.786` | retracement | `0.786` | gray | active |
| `1.000` | anchor completion | `1` | white | active |
| `1.236` | target 1 | `TARGET 1` | neon green | active |
| `1.382` | target waypoint | unlabeled | gray | active |
| `1.500` | target waypoint | `1.50` | gray | active |
| `1.618` | target 2 | `TARGET 2` | neon green | active |
| `1.786` | target waypoint / extension | `1.786` | gray | active |
| `2.000` | target 3 | `TARGET 3` | neon green | active |
| `2.382` | target extension | unlabeled | neon green | active |
| `2.618` | target 4 | `TARGET 4` | neon green | active |
| `3.618` | target 5 | `TARGET 5` | neon green | active |
| `4.236` | target extension | unlabeled | light blue | active |
| `-0.236` | stop level 1 | `SL1` | red | active |
| `-0.618` | stop extension | `-0.618` | dark red | active |

Visible-but-not-fully-captured note:

- the chart reference also shows an upper `.236` line; do not change or drop it without a direct full settings capture

Unchecked levels from the same settings capture are out of scope and must be omitted completely from the rebuild. They are not part of the locked visible fib inventory unless explicitly reapproved in a later checkpoint.

Implementation note:

- the exact line thicknesses, dash styles, and label placement must still be inventoried directly from the approved live TradingView settings before implementation
- the intermediate extension waypoints (`1.382`, `1.500`, `1.786`, and similar survivors) are operator-approved visuals and research candidates, but they do not force extra base-table columns unless waypoint-touch telemetry proves useful

Visual gap vs Auto Fib GOLDEN TARGET reference (observed 2026-03-29):

- **Anchor span**: the Auto Fib GOLDEN TARGET lines extend left from the anchor high/low area covering all bars in the swing, giving better visual geometry of the fib structure. WB v6 lines currently start from a narrower anchor point. The left edge of fib lines should reach the full anchor bar area, not just the pivot bar. This is purely visual for the trader.
- **Intermediate waypoint lines**: price reacts to the intermediate extension levels (1.382, 1.50, 1.786) between targets. These faint gray lines are in the locked inventory above but are NOT yet drawn by WB v6. They need to be added as faint/dotted lines in Pine. The model may also benefit from waypoint-touch features — evaluate during AG feature selection.
- **Both surfaces**: implement the anchor-span and waypoint visuals in Pine (WB v6 indicator) AND on the dashboard fib renderer so both operator views match.
- **No budget concern**: these are `line.new()` / `label.new()` drawing objects, NOT `plot()` calls — they do not count toward the 64-output cap.

### TradingView → Dashboard Webhook Architecture

The dashboard is the command center. TradingView webhook alerts are the live event bridge from Pine to the dashboard. This replaces the need for a server-side setup detection cron.

#### Flow

```
Pine alertcondition() fires
  → TradingView sends POST to webhook URL
    → Supabase Edge Function (tv-alert-webhook) receives POST
      → validates payload + shared secret
      → writes to canonical tables (warbird_fib_candidates_15m, warbird_signals_15m, etc.)
        → Supabase Realtime pushes change to dashboard
          → dashboard renders live state
```

#### Alert payload contract

TradingView webhook alerts send JSON in the POST body. The `message` field in `alertcondition()` supports `{{close}}`, `{{time}}`, `{{exchange}}`, `{{ticker}}`, and other placeholders. The 3 kept alerts and their payloads:

| Alert | Pine trigger | Webhook payload purpose |
|-------|-------------|------------------------|
| `WARBIRD ENTRY LONG` | `entryLongTrigger` | Create candidate + signal row with direction=LONG, entry/stop/TP levels from current fib state |
| `WARBIRD ENTRY SHORT` | `entryShortTrigger` | Create candidate + signal row with direction=SHORT, entry/stop/TP levels from current fib state |
| `PIVOT BREAK (against) + Regime Opposed` | `breakAgainstEvent` | Write reversal warning event to signal_events, update candidate decision state |

#### Edge Function: `tv-alert-webhook`

Required implementation:

1. Validate webhook secret (TradingView supports custom headers or URL-embedded tokens)
2. Parse alert name and `{{close}}` / `{{time}}` from payload
3. For entry alerts: snapshot current fib engine state from the latest `warbird_fib_engine_snapshots_15m` row, create `warbird_fib_candidates_15m` + `warbird_signals_15m` rows
4. For pivot break alert: find the active signal, write a `REVERSAL_DETECTED` event to `warbird_signal_events`
5. Log to `job_log`

#### Dashboard consumption

- Supabase Realtime subscription on `warbird_signals_15m` and `warbird_signal_events`
- Dashboard receives INSERT/UPDATE events in real-time — no polling
- The 8 alerts cut from Pine (ACCEPT, REJECT, TARGET HITs, CONFLICT, RISK-ON/OFF flips) can be reconstituted as dashboard-side derived state from the stored fib engine snapshot + intermarket regime data — no Pine budget cost

#### Rules

1. The webhook Edge Function writes to canonical tables (037 schema), not legacy tables
2. Pine is the signal source — the dashboard renders, it does not re-derive entry decisions
3. The webhook secret must be stored in Supabase Vault, not hardcoded
4. Webhook delivery is best-effort (TradingView retries but does not guarantee exactly-once) — the writer must be idempotent on natural key

---

## AutoGluon Optimization Loop

AG is offline only.

### Training Goal

Optimize for entry quality, not prediction vanity.

Primary labels:

- reached TP1
- reached TP2
- categorical outcome (`TP2_HIT`, `TP1_ONLY`, `STOPPED`, `REVERSAL`, `OPEN`)
- max favorable excursion
- max adverse excursion

### Optimization Targets

AG should search for settings that improve:

- precision of actionable entries
- stop-before-target reduction
- acceptable signal frequency
- favorable MAE / MFE profile

### Parameter Families To Optimize

Fib engine:

- confluence tolerance
- active period set
- zone ratios
- target ratios
- 20-point eligibility threshold details

Structure logic:

- retest window
- rejection definition

Intermarket:

- timeframe
- EMA length
- slope bars
- neutral band
- scoring model
- weights
- confirm bars
- cooldown

News / macro proxy:

- proxy timeframe
- lookback bars
- shock thresholds
- hold bars

Volume:

- baseline lengths
- shock thresholds
- relative volume gates

### AG Deliverable

AG should output:

- best parameter set
- runner-up parameter sets
- feature importance
- settings to remove because they are noisy
- settings to lock because they are robust across walk-forward windows

AG does not output live trades.

---

## AutoGluon Model Specification

Claude must treat the AG work as an **indicator optimization and entry-quality modeling problem**, not a live inference architecture.

### Training Unit

The base training unit is a **15-minute MES bar** where the indicator has enough context to evaluate a potential entry.

Each row should represent:

- one bar
- one direction (`LONG` or `SHORT`)
- one frozen parameter set
- one fully Pine-reproducible feature snapshot

### Feature Boundary

Claude must only train on features that can be reproduced inside Pine from:

- chart OHLCV
- `request.security()` pulls
- `request.economic()` pulls
- Pine-computed transforms

If a feature cannot be recreated in Pine for live use, it must be excluded from the production feature set even if it improves offline metrics.

### Labels

The AG workflow should model at least these targets:

- `reached_tp1`
- `reached_tp2`
- `outcome`
- `max_favorable_excursion`
- `max_adverse_excursion`
- `bars_to_tp1`
- `bars_to_tp2`

Optional secondary labels:

- `fib_level_touched`
- `session_quality_bucket`

### Parameter Search Space

Claude should treat the indicator inputs as a formal search space, not as ad hoc tweaks.

Minimum search scope:

- fib confluence tolerance
- pivot / zone / target / down-magnet ratios
- retest bars
- rejection mode
- intermarket timeframe
- EMA length
- slope bars
- neutral band
- intermarket scoring weights
- confirmation bars
- cooldown bars
- news proxy timeframe
- shock thresholds
- proxy hold bars
- volume baseline lengths
- volume thresholds

### Model Objective

The AG objective is to maximize **entry quality** under realistic signal frequency.

Primary optimization target:

- strong TP1 / TP2 discrimination and calibration on `20pt+` eligible setups

Primary penalties:

- `STOPPED` and `REVERSAL` outcomes
- excessive signal count
- unstable parameter sets across walk-forward windows

### Validation Protocol

Claude must use time-aware validation only:

- expanding window or walk-forward validation
- no random split
- no shuffled folds

Minimum validation outputs:

- TP1 / TP2 hit-rate quality on high-confidence eligible setups
- TP1 / TP2 calibration quality
- stop-before-target rate
- MAE / MFE distribution
- results by session/regime
- parameter stability across windows

### Selection Rule

The selected production configuration is not the single best in-sample score.

Claude must promote the parameter set that is:

- strong out of sample
- stable across windows
- explainable in Pine
- not dependent on unsupported data
- not overtrading

### Production Handoff From AG

Claude’s AG work must produce a Pine-ready handoff:

- best parameter set
- top 3 runner-up parameter sets
- features to keep
- features to remove
- thresholds/weights to encode in Pine
- notes on which settings are robust versus fragile

Claude must not leave the outcome as “the model knows.” The outcome must be a Pine-implementable ruleset and parameter set.

---

## Claude Handoff Constraints

Claude is allowed to:

- deepen the AG model design
- define the dataset builder logic
- define the label generation logic
- define the parameter search and walk-forward protocol
- tighten the indicator’s live feature inventory

Claude is not allowed to:

- reintroduce dashboards
- reintroduce FastAPI / Cloudflare / webhook return loops
- assume Pine can consume custom HTTP responses
- introduce non-Pine live dependencies
- drift this plan into a different product

Claude’s job is to finish the AG model concept **for this indicator only**.

---

## Claude Execution Brief

Claude must review this plan as the single active architecture document and then complete the AG concept around one narrow objective:

- optimize this indicator for the highest-quality MES entry signals that can realistically reach `+20` points before stop

Claude must treat that as an **entry-ranking and parameter-optimization problem**, not as a generic forecasting project and not as a live model-serving project.

### Required Claude Deliverables

Claude must add or tighten the following inside this plan and any directly supporting implementation docs/scripts:

1. a formal dataset-builder design for this indicator
2. exact label definitions and horizon rules for the `+20 before stop` objective
3. a search-space definition for every indicator setting worth tuning
4. the AG training and validation protocol
5. the model-selection rule for promoting one Pine-ready configuration
6. the final Pine handoff format:
   - parameter values
   - feature keep/remove calls
   - thresholds
   - scoring weights
   - notes on fragile vs robust settings

### Required Claude Reasoning Standard

Claude must use deep reasoning and explicitly stress-test:

- long vs short symmetry
- session dependence
- regime dependence
- whether one global parameter set is weaker than regime-specific parameter sets
- whether any candidate feature improves metrics but fails the Pine live-data rule
- whether a higher-scoring configuration is too unstable to promote

### Required Claude Boundary

Claude may design:

- offline training pipelines
- dataset builders
- labeling rules
- AG experiments
- Pine-implementable outputs

Claude may not design:

- live inference servers
- dashboard sync loops
- browser automation for TradingView inputs
- non-Pine live dependencies
- any architecture outside this indicator and its paired validation strategy

---

## AG Work Product

The AG work is complete only when it can hand Pine a production-ready optimization packet.

### Minimum Optimization Packet

The output packet must contain:

- selected production parameter set
- top 3 alternates with why they lost
- selected feature inventory
- rejected feature inventory with reason for rejection
- best-performing long configuration
- best-performing short configuration
- recommendation on unified vs split long/short settings
- walk-forward summary table
- session/regime breakdown
- Pine implementation notes

### Promotion Rule

No configuration gets promoted just because it wins one metric.

The promoted configuration must satisfy all of these:

1. strong out-of-sample TP1 / TP2 quality on `20pt+` eligible setups
2. acceptable stop-before-target rate
3. acceptable weekly signal count
4. stability across walk-forward windows
5. full reproducibility in Pine with live TradingView-accessible data

### Failure Rule

If AG cannot find a stable configuration that materially improves entry quality, the outcome must say so plainly.

Do not fake confidence, do not hide instability, and do not force a Pine handoff from a weak model.

---

## Build Phases

### 2026-03-23 Execution Guide — Fold Into All Phases

This section is execution guidance for all agents working the active plan. It does not replace the phases below. It constrains how they are executed.

#### March 23 Delta Execution Order Lock (Absorbed)

The March 23 execution delta is binding execution order for all Phase 2+ work:

1. Freeze the MES 15m contract across Pine, dataset, and AG packet surfaces before module expansion.
2. Harden the shared fib core and hidden export contract before admitting bolt-on modules.
3. Build the always-on hidden event-response block before decorative bolt-ons.
4. Embed the TA core pack (15 deterministic metrics) as the canonical ML export surface.
5. Export real TradingView data with the fib contract plus TA core pack outputs loaded.
6. Run module admission in stages: fib + event-response + TA core pack baseline, then parameter and joint configuration.

Historical note: steps 4-8 originally referenced three standalone harness bolt-ins (BigBeluga, LuxAlgo MSB/OB, LuxAlgo Luminance). Those harnesses were retired on 2026-03-28 and replaced by the embedded TA core pack.

#### 2026-03-26 Execution Correction

The project must not return to the earlier “build the full indicator zoo first” approach.

From this point forward:

1. Build only the minimal exportable Pine core required to generate a point-in-time training surface.
2. Train first on that surface and publish SHAP / feature-admission evidence.
3. Add or keep indicator modules, assets, and settings only if the training evidence shows they matter and the live Pine surface can mirror them.
4. If a setting or module exists only because it seemed intuitively useful before training, it is a removal candidate until SHAP / admission evidence says otherwise.

Minimal Pine export surface means:

1. fib lines / fib-state fields
2. pivot-state / pivot-distance fields
3. admitted indicator and harness outputs from the canonical indicator surface

It does not mean preloading extra UI/config sprawl or unrelated experimental modules into Pine before training evidence exists.

#### Contract First

1. The canonical trade object is now the **MES 15m fib setup**, keyed by the MES 15m bar-close timestamp in `America/Chicago`.
2. Any remaining `1H` wording in older drafts or reference files is legacy and must not drive new implementation.
3. Pine is the canonical signal surface.
4. The Next.js dashboard is the mirrored operator surface and may render the same fib engine/state alongside TradingView, but it must consume the same 15m contract rather than acting as a separate decision engine.
5. Every live, strategy, dataset, AG, and dashboard artifact must map back to the same 15m setup contract before any module work continues.
6. If a candidate feature or script cannot align exactly to the 15m bar-close contract, it is research-only and cannot enter the production path.

#### Data Flow Rule

1. Production ownership is cloud-first:
   - `provider -> cloud Supabase -> live routes/dashboard`
2. Local work is training/research only:
   - `cloud snapshots + TradingView exports/capture -> local warehouse -> publish approved artifacts back to cloud`
3. Do **not** build or extend a standing cloud-to-local sync subsystem or a local-first production ingestion path.
4. Use local capture only for explicit training inputs:
   - TradingView chart exports
   - validated local TradingView CLI / MCP capture only after the exact server or binary is installed and documented in the active environment
   - explicit cloud snapshot loads into the local warehouse
   - local research datasets
5. Publish promoted artifacts **from local to cloud** only:
   - promoted packets
   - training reports
   - SHAP summaries
   - approved feature metrics
6. Cloud Supabase remains the production system of record for recurring ingestion, cron ownership, dashboard state, and operator-facing live tables.

#### Third-Party Pine Admission Gate

Third-party scripts are allowed only through this gate:

1. Source must be open-source and reviewable.
2. Internal logic must be copied exactly. Interface-only adaptation is allowed:
   - input naming/grouping
   - visual disabling
   - hidden `plot()` exports
   - alert payload wiring
   - wrapper glue for strategy / export harnesses
3. No internal math rewrites, no partial reimplementations, no "clean-room" approximations.
4. Every admitted script must first land as a **standalone feature harness**, not inside the main indicator.
5. Harness output must be timestamp-aligned to the MES 15m bar close and exported for local AG training before any promotion decision.
6. Only modules that survive out-of-sample admission may be folded into the main indicator / strategy pair.
7. If exact-copy harnessing is not possible, stop the work. Do not substitute a hand-rolled internal copy.

#### Required Harness Modules — SUPERSEDED (2026-03-28)

The three standalone harnesses (BigBeluga Pivot Levels, LuxAlgo MSB/OB Toolkit, LuxAlgo Luminance Engine) were retired on 2026-03-28 (commit `c506c48`) and replaced by the embedded 15-metric TA core pack. The harness files were deleted from the repo (`indicators/harnesses/` directory removed). The TA core pack provides: EMAs (21/50/100/200), MACD histogram, RSI(14), ATR(14), ADX(14), volume raw, vol SMA(20), vol ratio, vol acceleration, bar spread × vol, OBV, MFI(14). All 15 are exported as `ml_*` hidden plots. Zero downstream consumers in TypeScript, API routes, or DB used the harness exports — the TA core pack covers the same feature space more efficiently within the 64-output budget.

#### Third-Party Source Acquisition Guide

Use these exact source pages and platform docs. Do not rely on summaries, screenshots, rewrites, or copied snippets from unknown blogs.

| Artifact | Status | Primary source link | Code access signal | Retrieval workflow | Logic that must survive exact-copy harnessing |
| --- | --- | --- | --- | --- | --- |
| `Pivot Levels [BigBeluga]` | Required | [TradingView open-source page](https://www.tradingview.com/script/h5TO1j8H-Pivot-Levels-BigBeluga/) | Script page shows `OPEN-SOURCE SCRIPT` and `Chart Source code` | Open the TradingView script page, confirm `OPEN-SOURCE SCRIPT`, click `Source code`, load it in Pine Editor, save a private working copy, then build the harness from that copy only | Pivot layer detection, level extension logic, any volume / importance logic the source exposes, mitigation / state transitions if present |
| `Market Structure Break & OB Probability Toolkit [LuxAlgo]` | Required | [TradingView open-source page](https://www.tradingview.com/script/ObcbP092-Market-Structure-Break-OB-Probability-Toolkit-LuxAlgo/) and [LuxAlgo library page](https://www.luxalgo.com/library/indicator/market-structure-break-ob-probability-toolkit/) | TradingView script page shows `OPEN-SOURCE SCRIPT` and `Chart Source code` | Open the TradingView script page directly, confirm `OPEN-SOURCE SCRIPT`, click `Source code`, load it in Pine Editor, save a private working copy, then build the harness from that copy only | Momentum Z-Score validated MSB logic, OB creation from the candle preceding confirmed MSB, POC line logic, HP-OB score logic, session-range logic, mitigation logic, overlap filtering |
| `Luminance Breakout Engine [LuxAlgo]` | Required | [TradingView open-source page](https://www.tradingview.com/script/FIWesyBd-Luminance-Breakout-Engine-LuxAlgo/) and [LuxAlgo library page](https://www.luxalgo.com/library/indicator/luminance-breakout-engine/) | TradingView script page shows `OPEN-SOURCE SCRIPT` and `Chart Source code` | Open the TradingView script page directly, confirm `OPEN-SOURCE SCRIPT`, click `Source code`, load it in Pine Editor, save a private working copy, then build the harness from that copy only | Weighted composite ROC engine, adaptive deviation envelope, breakout glow triggers, order-block origin logic, volume split stats |

Source-handling rules:

1. Save the original retrieved source in a private working copy before any interface edits.
2. Record the exact source URL in the active plan or phase audit when a harness starts.
3. Record whether the script page showed `OPEN-SOURCE SCRIPT` and `Chart Source code`.
4. Do not publish copied third-party code from this repository. TradingView House Rules still apply.
5. If a source page no longer exposes `OPEN-SOURCE SCRIPT`, stop and report before touching the harness.

#### TradingView Platform Guides And Hard Constraints

Use these official TradingView references when implementing or validating the live Pine path:

| Topic | Source | Binding use in this project |
| --- | --- | --- |
| Pine data requests | [Other timeframes and data](https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/) | Governs `request.security()`, `request.security_lower_tf()`, dynamic requests, and historical warm-up rules |
| Pine request limits | [Pine limitations](https://www.tradingview.com/pine-script-docs/v5/writing/limitations/) | Governs the 40-unique-call ceiling and tuple-return limits |
| Economic data | [Economic data available in Pine](https://www.tradingview.com/support/solutions/43000665359-what-economic-data-is-available-in-pine/) | Governs `request.economic()` field availability and code lookup |
| Webhook alerts | [Webhook alerts](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/) | Governs external POST-based operator / logging workflows |
| News alerts | [News alerts](https://www.tradingview.com/support/solutions/43000762838-news-alerts/) | Governs News Flow alerts; these notify the operator / webhook layer, not Pine directly |
| Built-in Pine source access | [Built-in script source code](https://www.tradingview.com/support/solutions/43000481659-i-want-to-see-the-source-code-of-a-built-in-script/) | Use when adapting TradingView built-ins or validating Pine workflows |
| Pine editor copy workflow | [Create new script](https://my.tradingview.com/support/solutions/43000711497/) | Governs saving a private editable copy from loaded source |

TradingView implementation constraints for this project:

1. Pine cannot directly ingest headline text from TradingView News Flow. This is an inference from the available official docs: Pine exposes `request.*()` market/economic data functions, while News Flow alerts deliver notifications / webhooks outside Pine.
2. Any webhook path must terminate at a public HTTPS endpoint, not a local-only production dependency.
3. Dynamic `request.*()` datasets must be requested on historical bars before realtime use.
4. Lower-timeframe reaction logic should prefer `request.security_lower_tf()` or carefully prewarmed `request.security()` patterns.
5. Every added `request.*()` call must be counted against the same indicator-wide budget before merge.

#### Event-Response Module Requirement

The main indicator must gain an always-on hidden event-response block. This block is not optional after the March 23, 2026 failure mode review.

Minimum candidate inputs:

1. MES / NQ / dollar-state proxy / ZN / VIX reaction state
2. lower-timeframe volume shock / expansion state
3. reversal-vs-continuation state after the impulse
4. scheduled macro proximity / release windows
5. inflation / rates / geopolitical regime context
6. pivot interaction state

The event-response block's purpose is to suppress, delay, confirm, or reclassify a valid 15m fib setup. It is not allowed to become a separate trade engine detached from the fib contract.

Required Phase 2 event-response export interface:

| Hidden export | Meaning | Encoding rule |
| --- | --- | --- |
| `ml_event_mode_code` | current event regime | `0=none`, `1=shock_continuation`, `2=shock_failure`, `3=deescalation_squeeze`, `4=inflation_scare`, `5=rates_relief`, `6=headline_conflict` |
| `ml_event_shock_score` | normalized shock intensity | `0-100` deterministic Pine score |
| `ml_event_reversal_score` | reversal risk after impulse | `0-100` deterministic Pine score |
| ~~`ml_event_volume_shock`~~ | lower-timeframe volume shock state | cut from Pine exports during budget reduction — AG computes from `ml_vol_ratio` + `ml_vol_acceleration` server-side |
| ~~`ml_event_macro_window_code`~~ | scheduled macro window state | cut from Pine exports during budget reduction — AG computes from `econ_calendar` data server-side |
| `ml_event_tick_state` | TICK institutional flow state | `-1`, `0`, `1` |
| `ml_event_vold_state` | VOLD money flow state | `-1`, `0`, `1` |
| `ml_event_vvix_state` | VVIX vol-of-vol state | `-1`, `0`, `1` |
| `ml_event_vts_state` | VIX term structure state | `-1`, `0`, `1` |
| `ml_event_hyg_state` | HYG credit state | `-1`, `0`, `1` |
| `ml_event_rty_state` | RTY small-cap state | `-1`, `0`, `1` |
| `ml_event_skew_state` | SKEW tail-risk state | `-1`, `0`, `1` |
| `ml_vts_ratio` | VIX/VIX3M term structure ratio | float (< 0.92 calm, > 1.0 stress) |
| `ml_event_pivot_interaction_code` | interaction with pivot state | `0=none`, `1=support`, `2=resistance`, `3=rejection`, `4=breakthrough`, `5=cluster_conflict` |

#### Checkpoint Audit, Memory, And Document Discipline

Every locked checkpoint and every phase completion must perform the same closeout sequence:

1. Update the active plan with:
   - checkpoint or phase name
   - files touched
   - validations run
   - blockers found
   - next blocking item
2. Update `WARBIRD_MODEL_SPEC.md` if the model contract changed.
3. Update `AGENTS.md` if repo rules, guardrails, or hard workflow constraints changed.
4. Update `CLAUDE.md` if current project status or live operational truth changed.
5. Update agent memory with 1-3 concrete observations:
   - current canonical contract
   - current required harness status
   - current phase blocker or promotion decision
6. Do not open the next checkpoint until the previous checkpoint’s audit/update sequence is complete.

Required between-checkpoint audits:

1. Pine checkpoint: lint, contamination check, build, source-alignment review.
2. Data-contract checkpoint: timestamp alignment, leakage check, dropped-row counts, schema-drift review.
3. Cloud ops checkpoint: live table inventory, migration drift, publish-up target review.
4. Harness checkpoint: source-access confirmation, exact-copy confirmation, hidden-export contract review, no-repaint review.

### Phase 1: Series Inventory Freeze

1. Inventory every live series the indicator wants.
2. Verify exact TradingView ticker or economic-series availability.
3. Freeze the initial v1 external series list.
4. Eliminate any data source Pine cannot request reliably.
5. Freeze the canonical 15m setup contract before adding any new module surface.
6. Inventory the required harness modules as separate harnesses, not as immediate main-indicator merges.

Phase 1 target files and outputs:

- `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`
- `WARBIRD_MODEL_SPEC.md`
- `AGENTS.md`
- `CLAUDE.md`
- `indicators/v6-warbird-complete.pine`
- `lib/ingestion/fred.ts`
- `app/api/cron/fred/[category]/route.ts`

Phase 1 must produce:

1. One contract audit table listing:
   - canonical element
   - current file source
   - conflicting legacy source
   - action required
2. One live-series inventory table listing:
   - symbol or economic field
   - Pine request path
   - timeframe
   - request-budget count
   - Tier 1 or Tier 2
3. One harness inventory table listing:
   - module name
   - required or later-phase
   - source URL
   - open-source confirmed yes/no
   - target harness file path
4. One blocker list for any symbol, field, or source that cannot align to the 15m contract

Planned harness file paths:

- `indicators/harnesses/bigbeluga-pivot-levels-harness.pine`
- `indicators/harnesses/luxalgo-msb-ob-probability-toolkit-harness.pine`
- `indicators/harnesses/luxalgo-luminance-breakout-engine-harness.pine`

### Phase 2: Refactor The Current Script

1. Add 0 and 1 fib lines.
2. Isolate fib calculations.
3. Isolate intermarket calculations.
4. Add volatility / credit / macro modules.
5. Add volume-state module.
6. Create one explicit entry predicate.
7. Add the hidden event-response block.
8. Replace the current pivot path with the BigBeluga-based pivot harness / integration path.
9. Bolt in the Market Structure Break & OB Probability Toolkit harness path as a required standalone module after the event-response interface is in place.
10. Bolt in the Luminance Breakout Engine harness path as a required standalone module after MSB / OB harness admission.

Phase 2 target files:

- `indicators/v6-warbird-complete.pine`
- `indicators/harnesses/bigbeluga-pivot-levels-harness.pine`
- `indicators/harnesses/luxalgo-msb-ob-probability-toolkit-harness.pine`
- `indicators/harnesses/luxalgo-luminance-breakout-engine-harness.pine`

Phase 2 required hidden export contract (current actual exports):

- `ml_confidence_score`, `ml_direction_code`, `ml_setup_archetype_code`, `ml_fib_level_touched`, `ml_stop_family_code`
- `ml_event_mode_code`, `ml_event_shock_score`, `ml_event_reversal_score`, `ml_event_nq_state`, `ml_event_dxy_state`, `ml_event_zn_state`, `ml_event_vix_state`, `ml_event_pivot_interaction_code`
- `ml_ema21_dir`, `ml_ema50_dir`, `ml_ema200_dir`, `ml_ema21_dist_pct`, `ml_ema50_dist_pct`, `ml_ema200_dist_pct`
- `ml_entry_long_trigger`, `ml_entry_short_trigger`, `ml_tp1_hit_event`, `ml_tp2_hit_event`
- TA Core Pack: `ml_ema_21`, `ml_ema_50`, `ml_ema_100`, `ml_ema_200`, `ml_macd_hist`, `ml_rsi_14`, `ml_atr_14`, `ml_adx_14`, `ml_volume_raw`, `ml_vol_sma_20`, `ml_vol_ratio`, `ml_vol_acceleration`, `ml_bar_spread_x_vol`, `ml_obv`, `ml_mfi_14`

Note: `ml_target_eligible_20pt`, `ml_regime_bucket_code`, `ml_session_bucket_code`, `ml_event_volume_shock`, `ml_event_macro_window_code` were in the original Phase 2 contract but are not currently exported. They were cut during the output budget reduction. AG can compute these server-side from the existing exports + Supabase data.

Live-surface constraint:

- TradingView hard-caps each script at `64` plot counts.
- Hidden `display.none` plots still count toward that cap.
- The live indicator contract must fit within that budget even when local parity passes.

Phase 2 hard implementation order:

1. Harden fib direction in `indicators/v6-warbird-complete.pine`
2. Add explicit `0` and `1` fib lines
3. Add `20pt+` eligibility logic and bounded stop-family interface
4. Freeze always-on hidden export names
5. Add the event-response block and exports
6. Only then start the required BigBeluga harness
7. Only after BigBeluga source access and export contract are clean, start the required MSB / OB harness
8. Only after MSB / OB source access and export contract are clean, start the required Luminance harness

Phase 2 required audit outputs:

1. exact line references for every replaced midpoint or local pivot path
2. export-field inventory before and after edits
3. source-access confirmation for each harness
4. explicit note of any still-missing export fields

#### Phase 2 Completion Summary

Phase 2 was completed across 5 checkpoints on 2026-03-24. All checkpoints passed validation gates. On 2026-03-28 (commit `c506c48`), the three standalone harnesses (BigBeluga Pivot Levels, LuxAlgo MSB/OB Toolkit, LuxAlgo Luminance Engine) were retired and replaced by the embedded 15-metric TA core pack. The harness files were deleted from the repo. The current Pine export surface is the TA core pack (15 metrics) plus the pre-ML feature exports and event-response block. See the update log entries for 2026-03-24 through 2026-03-29 for the full execution history.

### Phase 3: Strategy Path — RETIRED (2026-03-26)

The paired strategy, parity guard, and Deep Backtesting protocol were retired from the active blocking path on 2026-03-26. `indicators/v6-warbird-complete-strategy.pine` and `scripts/guards/check-indicator-strategy-parity.sh` remain as legacy scratch/reference surfaces. They do not block indicator work unless explicitly reopened. See update log entries for 2026-03-24 through 2026-03-26 for checkpoint history.

### Phase 4: Dataset + AG Loop

1. Export chart data with the final feature columns.
2. Build labels tied to TP1 / TP2 / outcome, with `20pt+` used as an eligibility gate.
3. Train AG on settings and feature robustness.
4. Select the best candidate rule set.
5. Train module admission first, then parameter admission, then joint configuration.
6. Treat each required third-party script as a standalone exported feature family before main-indicator promotion.
7. Publish results upward from local after evaluation; do not add a recurring cloud-to-local sync layer.

Phase 4 decision rule:

1. Phase 4 is the filter for what truly earns its way into the live indicator.
2. SHAP, admission reports, and out-of-sample validation decide which assets, modules, and setting families survive.
3. Do not expand the live indicator with additional settings or “zoo” modules ahead of that evidence.
4. Minimal exportability comes before expansion; evidence-driven promotion comes before UI/config sprawl.

Phase 4 exact local targets:

- local PostgreSQL database: `warbird_training`
- local AG scripts:
  - `scripts/ag/build-fib-snapshots.py`
  - `scripts/ag/load-source-snapshots.py`
  - `scripts/ag/build-fib-dataset.py`
  - `scripts/ag/compute-features.py`
  - `scripts/ag/train-fib-model.py`
  - `scripts/ag/evaluate-configs.py`
  - `scripts/ag/generate-packet.py`
  - `scripts/ag/publish-artifacts.py`
Phase 4 exact training order:

1. fib + event-response + TA core pack baseline
2. parameter admission inside surviving feature families
3. joint configuration on surviving feature families only

Historical note: the original order included 3 standalone harness admission steps (BigBeluga, MSB/OB, Luminance) — those harnesses were retired on 2026-03-28 and replaced by the embedded TA core pack.

Phase 4 exact local warehouse entities:

- source-snapshot tables:
  - `mes_1m`
  - `mes_15m`
  - `mes_1h`
  - `mes_4h`
  - `mes_1d`
  - `cross_asset_1h`
  - `cross_asset_1d`
  - `options_stats_1d`
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
  - `macro_reports_1d`
  - `geopolitical_risk_1d`
  - `trump_effect_1d`
- `warbird_training_runs`
- `warbird_training_run_metrics`
- `warbird_shap_results`
- `warbird_shap_indicator_settings`
- `warbird_snapshot_pine_features`
- `warbird_candidate_macro_context`
- `warbird_candidate_microstructure`
- `warbird_candidate_path_diagnostics`
- `warbird_candidate_stopout_attribution`
- `warbird_feature_ablation_runs`
- `warbird_entry_definition_experiments`

Phase 4 exact cloud publish-up entities:

- `warbird_training_runs`
- `warbird_training_run_metrics`
- `warbird_packets`
- `warbird_packet_activations`
- `warbird_packet_metrics`
- `warbird_packet_feature_importance`
- `warbird_packet_setting_hypotheses`
- `warbird_packet_recommendations`
- realtime dashboard/Admin surfaces:
  - `mes_1m`
  - `mes_15m`
  - `warbird_active_signals_v`
  - `warbird_admin_candidate_rows_v`
  - `warbird_active_training_run_metrics_v`
  - `warbird_active_packet_metrics_v`
  - `warbird_active_packet_feature_importance_v`
  - `warbird_active_packet_setting_hypotheses_v`
  - `warbird_active_packet_recommendations_v`

### Phase 5: Indicator UI Build

1. Inventory and lock the exact operator-approved fib visual spec first: colors, line widths, line styles, level labels, and exhaustion-diamond presentation.
2. Build the execution-facing TradingView surface only: entry markers, level lines, exhaustion precursor diamond, and concise alertconditions.
3. Keep operator tables and rich diagnostics in the dashboard.
4. Ensure the indicator remains within Pine limits.
5. Keep pivots, required harness intelligence, and candidate bolt-on intelligence hidden unless explicitly promoted to the visible surface.

Phase 5 must not begin until Phase 4 has produced at least one packet candidate with stable bucket outputs and documented sample counts.

The mirrored dashboard operator surface must map exactly to:

- decision state
- TP1 probability
- TP2 probability
- reversal risk
- win rate
- stats window
- regime
- conflict
- stop family
- TP1 / TP2 path

### Phase 6: Walk-Forward Validation

1. Re-test the candidate settings out of sample.
2. Compare against prior settings.
3. Promote only if entry-quality metrics improve.
4. Require every promoted required harness module or candidate bolt-on to prove additive value over the fib + event-response baseline.

Phase 6 closeout must update:

- active plan status
- `WARBIRD_MODEL_SPEC.md` if packet or contract semantics changed
- `CLAUDE.md` current status
- memory with the promoted / rejected module decision

---

## Success Metrics

The indicator is successful only if it improves entry quality on the chart.

Primary metrics:

- percent of eligible signals that reach TP1
- percent of eligible signals that reach TP2
- stop-before-target rate
- average MAE before TP1
- average time to TP1
- signal count per week

Secondary metrics:

- percent of signals filtered out versus baseline
- expectancy improvement versus baseline
- regime-specific performance consistency

---

## Open Research Items

These are non-blocking v2 questions, not blockers for v1:

1. Whether `RTY1!` or `YM1!` add material value beyond the locked v1 basket.
2. Whether `VVIX`, `JNK`, crude, or gold add enough value to justify request-budget expansion.
3. Whether one unified model works best, or whether separate long and short parameter sets are required.
4. Whether a compact gauge improves table usability over bar-state rows after v1 is visually complete.

---

## AG Model Concept — Locked Specification

### Status: LOCKED (2026-03-20, revised)

AG is a **fib continuation probability engine** that models both the market AND the Pine indicator's configuration space. AG trains on thousands of historical fib pullbacks with full market context — macro events (CPI, FOMC, GDP, NFP), intermarket state, indicators, volatility — and outputs the probability of hitting the 1.236 and 1.618 fib extensions. AG also learns when a pullback is actually a reversal.

**Critical framing:** AutoGluon must treat the Pine indicator as the production surface and the Pine input space as the optimization surface. Every AG conclusion must terminate in a Pine-implementable setting, threshold, weight, gate, or rule selection. If AG produces an insight that cannot be expressed through Pine inputs, Pine logic, Pine-requestable data, or Pine-rendered outputs, that insight is not production-ready and cannot be promoted.

AG is offline only. Pine owns the live signal. AG teaches Pine what it learned.

---

### 1. AG Models Pine's Configuration Space

AG is not just modeling the market. AG is modeling the Pine indicator configuration space.

AG must understand:

- Every Pine input in the indicator
- What each setting changes in the live logic
- Which settings interact with each other
- Which outputs Pine can actually render, alert on, and calculate live

The AG output is NOT "here's a smart model" or "here's a probability blob." The AG output must be **Pine-native**:

- Exact input values (e.g., `tfIM = 60`, `retestBars = 4`)
- Exact thresholds (e.g., `neutralBandPct = 0.08`)
- Exact weights for scoring
- Exact on/off feature decisions (e.g., `useIntermarket = true`, `creditFilter = shorts_only`)
- Exact rule/gate selections (e.g., `rejectWick = false`)
- Exact stop/target family selection
- Exact long/short split decision if needed

AG helps answer not just entry/targets but also:

- What the indicator must expose as inputs
- What states it must calculate
- What filters it must support
- What table outputs it must show
- What alerts it must fire
- Which modules are worth keeping versus dead weight

**Pine indicator = production interface. AG = optimizer for that interface.**

Operational correction:

1. We do not pre-load the indicator with every plausible rule, asset, and setting family and then hope AG sorts it out later.
2. We build the minimal exportable core first.
3. AG + SHAP + admission testing decide what is actually important.
4. Only then do surviving assets, settings, and feature families earn permanent places in the live indicator and packet contract.

Before AG is fully useful, the indicator needs a defined contract:

- Inputs (all tunable parameters)
- Internal computed states
- Decision states (`TAKE_TRADE`, `WAIT`, `PASS`)
- Realized outcome states kept separate from the decision codes
- Alerts
- Visualization / dashboard fields

Then AG can output things like:

- `useIntermarket = true` should stay
- `tfIM = 60` outperforms 15 and 240
- `neutralBandPct` should be 0.08
- VIX and DXY are useful, BANK is weak in holdout
- `retestBars = 4` is robust
- `rejectWick = false` is better than `true`
- news proxy hold = 8 bars
- credit filter improves shorts only
- re-entry mode adds noise, remove from v1
- the operator surface must show: decision state, target eligibility, regime context, stop family, TP1/TP2 path

---

### 2. Dataset Builder Design

#### Data Source

Training data comes from **two sources**:

1. **Supabase DB / local research extracts** — MES 15m OHLCV, cross-asset prices, FRED economic series, GPR index, Trump Effect, news signals, economic calendar, pulled into local research workflows without introducing a standing cloud-to-local sync subsystem
2. **TradingView local exports and any later-validated chart capture tooling** — fib lines, pivot-state fields, and admitted indicator / harness outputs from the canonical indicator surface. Do not assume CLI/MCP chart capture exists until the exact tool is installed and documented.

For indicators present on the TradingView chart but not yet in our dataset, we **create the missing indicator in Pine Script first** (using Pine tools and skills), **test it**, then add its output to the training dataset alongside the rest of the data.

The dataset builder must:

1. Pull base OHLCV + cross-asset + macro data into the local research workflow without adding a recurring sync subsystem
2. Ingest TradingView exports for indicator columns, plus any later-validated CLI/MCP chart captures only after the exact tool is installed and documented
3. Materialize point-in-time fib snapshots before downstream feature assembly
4. Create and test any missing Pine indicators or standalone feature harnesses needed for features
5. Identify every fib pullback event in the history from the snapshot surface
6. Compute all features at each pullback
7. Generate forward-looking labels (TP1/TP2 hit, reversal, stop, pullback depth)
8. Output a single CSV ready for AG training

#### Locked Dataset Alignment Contract

The dataset builder must obey these alignment rules:

1. **Canonical timezone**
   - all timestamps normalize to `America/Chicago`
2. **Canonical bar key**
   - every training row is keyed by the MES 15m **bar close timestamp**
3. **TradingView CSV join**
   - TradingView exports must be normalized to the same MES 15m bar-close timestamp
   - if a CSV row cannot be matched exactly after timezone normalization, it is rejected and logged
4. **Cross-asset join**
   - cross-asset series are joined **as-of bar close**
   - only the most recent value available at or before the MES bar close may be used
5. **Economic / macro join**
   - no economic value may appear in the dataset before its release-effective timestamp
   - if a release timestamp is unknown, that field cannot be used as a Tier 1 production feature
   - unknown-timestamp macro fields remain Tier 2 research-only
6. **Session tagging**
   - `session_bucket` and RTH/ETH state are assigned from the MES bar timestamp before feature merges
7. **No lookahead**
   - every feature must be available as of the current MES bar close
   - future daily values, same-day unreleased macro values, and revised values from the future are forbidden
8. **Missing-value rule**
   - rows missing critical Tier 1 fields are dropped and counted
   - the dataset builder must log dropped-row counts by reason
9. **Leakage check**
   - the builder must run a final leakage audit confirming that no joined feature timestamp exceeds the MES row timestamp

#### Fib Snapshot Surface For AG

The fib engine is a first-class state surface and must be materialized point-in-time for training.

Rules:

1. AG training must consume explicit fib snapshots, not ad hoc recomputation from a fully known history window.
2. The snapshot builder must emit one row per MES 15m bar close, keyed by the canonical bar timestamp.
3. Each snapshot may use only data available at or before that bar close, including pivot confirmation/right-bar rules.
4. Once a snapshot row is written for a bar, later anchor discoveries may not rewrite that historical row.

#### Locked normalized operational tables

The next migration must normalize the live decision surface around these tables:

1. `warbird_fib_engine_snapshots_15m`
   - one row per `symbol_code + timeframe + bar_close_ts + fib_engine_version`
   - the canonical frozen fib engine snapshot at MES 15m bar close
2. `warbird_fib_candidates_15m`
   - one row per candidate derived from a snapshot
   - canonical candidate key is `symbol_code + timeframe + bar_close_ts + candidate_seq`
   - carries the policy decision code `TAKE_TRADE` / `WAIT` / `PASS`
3. `warbird_candidate_outcomes_15m`
   - one row per candidate, regardless of decision
   - carries realized outcome truth plus MAE / MFE
4. `warbird_signals_15m`
   - one row per published TradingView signal where the candidate decision is `TAKE_TRADE`
5. `warbird_signal_events`
   - lifecycle events for published signals only

Rules:

1. Decision codes and realized outcomes must remain separate.
2. Missed winners and correct skips become visible only if every candidate receives an outcome row, not only published signals.
3. The dashboard must render from these canonical tables or compatibility views over them; it must not recompute fib geometry locally.
4. Compatibility views may exist during cutover, but the normalized tables above are the new source of truth.
5. Accuracy beats feature count. Example context fields such as retrace-depth variants, volume state, EMA distance, daily 200d distance, or other candidate-side signals are admitted only if they are point-in-time clean, exactly defined, and worth the added complexity.

Locked truth semantics for the next schema rewrite:

- `warbird_decision_code`
  - `TAKE_TRADE`
  - `WAIT`
  - `PASS`
- realized economic truth must distinguish:
  - TP2 reached before stop
  - TP1 reached before stop while TP2 is not yet realized
  - stop before TP1
  - stop after TP1 but before TP2
  - reversal when the locked reversal rule is satisfied
- unresolved rows remain `OPEN` until they resolve to an economic outcome
- exact enum names and exact column names for these semantics are part of the next schema rewrite checkpoint, not this lock
5. Snapshot rows must record, at minimum:
   - active anchor high / low
   - anchor timestamps / bar indexes
   - selected lookback family or period set
   - active fib direction
   - 0 / 1 / pivot / TP1 / TP2 prices
   - target-eligibility state
   - pivot-distance and pivot-state fields used by the trigger
6. The canonical implementation surface for offline fib snapshots is Python in `scripts/ag/build-fib-snapshots.py`, because it needs deterministic materialization for AG and leakage audits.
7. A simple zigzag-only anchor path is not sufficient for Warbird. The engine must preserve the lookback/confluence intelligence that makes the fib state useful, while still being point-in-time clean.
8. User-referenced non-open-source fib indicators, including `Auto Fib Golden Target (with custom text)` when source is unavailable, may be behavior references only. They are not approved code sources and may not be cloned internally.

#### Feature Boundary — Two Tiers

**Tier 1: Pine-Live Features** — computable in Pine from chart OHLCV, `request.security()`, `request.economic()`, or Pine transforms. These drive the live indicator signal.

**Tier 2: Research-Only Context** — macro event data (FRED, GPR, Trump Effect, news signals) that AG uses to discover regime patterns and validate hypotheses. Tier 2 data does NOT produce production features directly. If AG discovers a Tier 2 insight (e.g., "CPI day pullbacks fail more often"), it can only become production-ready if there is an **exact Pine analogue** — either via `request.economic()`, Pine calendar logic, or a Tier 1 proxy that AG can prove correlates (e.g., VIX spike on CPI day). If no Pine analogue exists, the insight stays in the research report but does NOT enter the Pine indicator.

**Rule:** AG trains on everything available. But only Tier 1 features can become production features. Tier 2 insights must pass through a Pine-analogue gate before they influence the live indicator.

#### Feature-Family De-Duplication Rule

The TA core pack and pre-ML exports together form the production feature surface. Do not add redundant variants of the same concept.

Rules:

1. Do not keep overlapping MA / trend / volume features from multiple export blocks unless they encode materially different information.
2. If the TA core pack already exports the canonical state for a concept family (e.g., volume via `ml_vol_ratio` + `ml_vol_acceleration`), a separate hand-built copy is research-only until it proves additive value.
3. AG admission should compare feature families, not reward the same idea repeated in different columns.
4. Any future third-party harness re-admission must go through the Third-Party Pine Admission Gate and prove additive value over the TA core pack baseline.

Neural-layer policy (research-only unless promoted):

1. Neural feature extraction from text/event data is allowed for offline discovery only.
2. Candidate neural cues include policy/lobbying-style event text, obscure news context, and cross-source narrative drift.
3. Neural outputs must be timestamp-aligned to MES 15m bar close and leak-audited before any model training use.
4. No neural score may enter live Pine unless a deterministic Pine-analogue or mirrored-live contract is proven additive and non-breaking.

#### Pine-Reproducible Feature Set

**A. Fib Structure Features** (from chart OHLCV)

Fib-structure rules:

1. The live and offline fib engine may use confirmed lookback/confluence logic, but the training surface must come from frozen point-in-time snapshots.
2. Do not reduce the Warbird fib engine to a simple zigzag feature family.
3. Pivot distance and pivot-state features are critical to trigger admission and reversal derivation, but they are not the sole final decision maker.

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `fib_anchor_high` | chart OHLCV | Multi-period confluence anchor high |
| `fib_anchor_low` | chart OHLCV | Multi-period confluence anchor low |
| `fib_range` | derived | `anchor_high - anchor_low` |
| `fib_retrace_ratio` | derived | Deepest retrace level reached (0.236–0.786) |
| `dist_to_fib_0` | derived | Points from close to 0-level |
| `dist_to_fib_1` | derived | Points from close to 1-level |
| `dist_to_nearest_zone` | derived | Points from close to nearest zone level |
| `target_distance_pts` | derived | Distance from entry to TP1 in points |
| `target_eligible_20pt` | derived | Boolean: target path ≥ 20 points |
| `fib_range_atr_ratio` | derived | `fib_range / ATR(14)` — quality filter |

**B. Intermarket Features** (from `request.security()`) — **UPDATED 2026-03-30: flow-based leading indicators**

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `tick_state` | `request.security("USI:TICK")` | TICK flow state: > 0 bull, < 0 bear |
| `vold_state` | `request.security("USI:VOLD")` | VOLD flow state: > 0 bull, < 0 bear |
| `vvix_level` | `request.security("CBOE:VVIX")` | VVIX level (< 17 risk-on, > 25 risk-off) |
| `vts_ratio` | derived | VIX/VIX3M term structure (< 0.92 calm, > 1.0 stress) |
| `hyg_trend` | `request.security("AMEX:HYG")` | HYG EMA slope state: -1/0/1 |
| `rty_trend` | `request.security("CME_MINI:RTY1!")` | RTY EMA slope state: -1/0/1 |
| `skew_level` | `request.security("CBOE:SKEW")` | SKEW level (< 140 risk-on, > 155 risk-off, daily) |
| `add_value` | `request.security("USI:ADD")` | NYSE A/D breadth (daily) |
| `intermarket_alignment` | derived | Count of 7 symbols in agreement (0-7) |

**C. Volatility Features** (from chart OHLCV + `request.security()`)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `atr_14` | chart OHLCV | ATR(14) on 15m |
| `atr_ratio_5_20` | derived | `ATR(5) / ATR(20)` — volatility expansion/contraction |
| `realized_vol_20` | derived | 20-bar realized volatility |
| `vix_regime` | derived | Low/Normal/High/Extreme (quartile buckets) |

**C2. Economic / Macro Features** (from `request.economic()` + Supabase for training)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `fed_funds_rate` | `request.economic("US", "IRSTCB01")` | Current Fed funds rate |
| `cpi_yoy` | `request.economic("US", "CPALTT01")` | CPI year-over-year |
| `gdp_growth` | `request.economic("US", "NAEXKP01")` | GDP growth rate |
| `unemployment` | `request.economic("US", "LRHUTTTTUSM156S")` | Unemployment rate |
| `pmi_manufacturing` | `request.economic("US", "BSCICP02")` | PMI manufacturing |
| `is_fomc_week` | Pine calendar logic | Boolean: is this FOMC week? |
| `is_cpi_day` | Pine calendar logic | Boolean: is CPI releasing today? |
| `is_nfp_day` | Pine calendar logic | Boolean: is Non-Farm Payroll today? |
| `bars_since_major_release` | derived | Bars since last major economic release |

AG trains on the FULL economic context from all 10 Supabase FRED tables + GPR + Trump Effect. What Pine gets is the distilled version: `request.economic()` for live levels, plus calendar-based event windows that AG learned are significant. Example: AG discovers "CPI day pullbacks to 0.5 have 25% lower TP1 rate before 10am ET" → Pine encodes `is_cpi_day AND hour < 10 → reduce confidence`.

**Research-Only Macro Context (Tier 2 — AG uses for discovery, NOT direct production features)**

| Feature | Source | Pine Analogue (required for promotion) |
|---------|--------|---------------------------------------|
| Full FRED series (all 10 tables) | Supabase `econ_*_1d` | Must find exact `request.economic()` equivalent OR prove a Tier 1 proxy (e.g., US10Y, VIX) captures the same signal |
| GPR geopolitical risk index | Supabase `geopolitical_risk_1d` | Must prove VIX + intermarket captures the same signal, OR stays research-only |
| Trump Effect / policy uncertainty | Supabase `trump_effect_1d` | Must prove a Pine time/calendar analogue exists, OR stays research-only |
| Economic calendar events | Supabase + user-maintained | Pine calendar logic (`is_fomc_week`, `is_cpi_day`) IF AG proves these events materially change outcomes |

**Promotion gate:** A Tier 2 insight only enters Pine if there is an exact Pine analogue that AG can prove correlates. "AG discovered it matters" is not enough — "AG proved Pine feature X captures the same signal" is required.

#### Locked Pine request budget

The v1 indicator must stay under this request budget:

- target operating budget: `<= 12` unique `request.*()` calls
- hard ceiling: `<= 16` unique `request.*()` calls

Planned v7 usage (UPDATED 2026-03-30):

- `request.security()` — intermarket 60min:
  - `USI:TICK`
  - `USI:VOLD`
  - `CBOE:VVIX`
  - `CBOE:VIX`
  - `CBOE:VIX3M`
  - `AMEX:HYG`
  - `CME_MINI:RTY1!`
- `request.security()` — intermarket daily:
  - `CBOE:SKEW`
  - `USI:ADD`
- `request.economic()`:
  - `IRSTCB01`
  - `CPALTT01`
  - `LRHUTTTTUSM156S`
  - `BSCICP02`

This yields a planned base budget of `11` unique `request.*()` calls, leaving limited room for future additions.

**D. Volume Features** (from chart OHLCV)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `volume` | chart | Raw bar volume |
| `vol_sma_20` | derived | 20-bar volume SMA |
| `vol_ratio` | derived | `volume / vol_sma_20` |
| `vol_acceleration` | derived | `vol_ratio - vol_ratio[1]` |
| `bar_spread_x_vol` | derived | `(high - low) * volume` — effort vs result |

**E. Session / Market State Features** (from Pine time functions)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `session_state` | `syminfo.session` | RTH=1, ETH=0 |
| `hour_utc` | `hour(time, "UTC")` | Hour of day (0-23) |
| `minutes_since_rth_open` | derived | Minutes since 09:30 ET |
| `is_opening_30min` | derived | Boolean: within first 30min of RTH |
| `is_lunch_noise` | derived | Boolean: 11:30-13:00 ET |
| `day_of_week` | `dayofweek` | 1-7 |
| `bars_since_structure_break` | derived | Bars since last pivot break |

**F. Oscillator / TA Features** (from Pine built-ins)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `rsi_8` | `ta.rsi(close, 8)` | RSI with Kirk's length |
| `rsi_14` | `ta.rsi(close, 14)` | Standard RSI |
| `stoch_k` | `ta.stoch(close, high, low, 14)` | Stochastic %K |
| `macd_hist` | derived | MACD(8,17,9) histogram |
| `squeeze_on` | derived | BB inside KC boolean |
| `squeeze_momentum` | derived | Squeeze momentum value |
| `ema_9_slope` | derived | EMA(9) slope over 3 bars |
| `price_vs_ema_20` | derived | `(close - EMA(20)) / ATR(14)` |
| `price_vs_sma_50` | derived | `(close - SMA(50)) / ATR(14)` |

**Total production features: ~40**

#### Feature Delivery to Pine

**Nothing is rejected from AG training.** AG trains on everything. The question is only how Pine consumes each feature:

| Feature Category | AG Trains On | Pine Receives As |
|-----------------|-------------|-----------------|
| FRED economic series (all 10 tables) | Full daily values from Supabase | `request.economic()` for key levels + calendar rules AG learned |
| GPR geopolitical risk | Daily index from Supabase | VIX + intermarket proxy (AG identifies which proxies correlate) |
| Trump Effect / policy uncertainty | Daily index from Supabase | Calendar event windows + VIX regime |
| News sentiment counts by segment | Hourly counts from Supabase | Time-of-day volatility rules AG learned |
| Order book depth | Not available for training either | Not applicable |
| Cross-asset volume | Unreliable on continuous contracts | Excluded from Pine — AG uses for research only |

---

### 3. Training Unit Definition

Each training row represents **one fib pullback event**:

- **One 15-minute bar** where price touched or crossed a fib level during a trend
- **One direction** (LONG or SHORT, from trend context)
- **One fib level touched** (0.236, 0.382, 0.5, 0.618, 0.786)
- **One frozen Pine indicator parameter set** (every indicator input fixed for that training run — AG treats the Pine input space as the optimization surface)
- **One full feature snapshot** (Tier 1 Pine-live features + Tier 2 macro context from Supabase)

#### What Constitutes a Fib Pullback Event

A row is generated when:

1. A valid fib anchor exists (non-degenerate range ≥ 10 points)
2. Price is in a trend (higher highs/lows for LONG, lower highs/lows for SHORT)
3. Price pulls back and touches or crosses a fib level on this bar
4. The 1.236 extension is ≥ 20 points away (minimum viable trade filter)
5. Sufficient lookback data exists for all features (≥ 50 prior bars)

Not every bar is a training row. Only bars where a fib pullback event occurs.

#### Reversal Rows

AG also trains on failed continuations / reversals — price broke through the fib level, structure died, conditions shifted. These rows have `outcome = REVERSAL` and teach AG when NOT to signal. AG learns the difference between "healthy pullback to 0.382 before continuation" and "0.618 break where VIX spiked, yields moved, NQ diverged — trend is dead."

---

### 4. Label Definitions

All labels are computed from future price action. Targets are the 1.236 and 1.618 fib extensions (dynamic). Stop is determined by a **bounded family** of deterministic methods (see Locked v1 Mechanisms) — AG chooses which family member works best, not an unconstrained learned distance.

#### Primary Labels

| Label | Type | Definition |
|-------|------|------------|
| `reached_tp1` | binary | Price reached the 1.236 fib extension in trade direction within horizon |
| `reached_tp2` | binary | Price reached the 1.618 fib extension in trade direction within horizon |
| `outcome` | categorical | `TP2_HIT`, `TP1_ONLY`, `STOPPED`, `REVERSAL`, `OPEN` |

#### Outcome Logic

For LONG on bar `i` with entry = close[i]:

```
tp1_price = anchor_low + fib_range * 1.236
tp2_price = anchor_low + fib_range * 1.618
fib_level_price = price at the fib level touched

for each future bar j in [i+1, i+1+max_horizon]:
    track max_favorable_excursion
    track max_adverse_excursion
    track pullback_depth (entry - lowest low before TP1)

    if high[j] >= tp2_price: outcome = TP2_HIT, break
    if high[j] >= tp1_price: mark tp1 hit

    # Stop = bounded family member (fib invalidation, fib+ATR, structure breach, or fixed ATR)
    if low[j] < stop_price:  # stop_price from the selected stop family member
        if structure also broken: outcome = REVERSAL
        else: outcome = STOPPED
        break

if timed out:
    if tp1 hit: outcome = TP1_ONLY
    else: outcome = OPEN
```

Maximum horizon: 40 bars (10 hours of 15m bars).

Stopped trades get **higher penalty weight** during training (weight = 2.0) so AG learns what causes failures. `OPEN` rows are operational-only and excluded from training targets.

#### Secondary Labels

| Label | Type | Definition |
|-------|------|------------|
| `fib_level_touched` | categorical | Which fib level (0.236/0.382/0.5/0.618/0.786) |
| `max_favorable_excursion` | float | Max points in trade direction within horizon |
| `max_adverse_excursion` | float | Max points against trade direction |
| `pullback_depth_from_entry` | float | Deepest pullback before TP1 — used to evaluate which stop family member would have been optimal (not a live model output) |
| `stop_family_best` | categorical | Which bounded stop method (fib_invalidation / fib_atr / structure_breach / fixed_atr) would have avoided the stop while staying tight |
| `bars_to_tp1` | int or NaN | Bars to reach 1.236 extension |
| `bars_to_tp2` | int or NaN | Bars to reach 1.618 extension |
| `session_at_entry` | categorical | RTH / ETH |
| `had_reentry_opportunity` | binary | After TP1, did price pull back ≥ 5 pts before TP2? |
| `macro_event_active` | binary | Was a major economic release within ±2 hours? |

---

### 5. Parameter Search Space

AG treats the Pine indicator's input schema as the optimization surface. Every parameter below must map directly to a Pine `input.*()` declaration in the actual hardened indicator.

**IMPORTANT:** The parameter families below are a **candidate starting point**. After the Forensic Review items are fixed and the indicator is hardened (Phase 2), the search space MUST be rebuilt from the actual indicator's `input.*()` declarations. Parameters like `tfIM`, `requireAnchors`, explicit intermarket weights, `vixMaxRiskOn`, `use10YConfirm`, and the current proxy settings from the existing script must be included if they survive hardening. Parameters that do not exist in the hardened indicator's input schema must be removed.

#### Approach

1. Map every `input.*()` in the hardened Pine indicator → that is the search space
2. Define 20-50 discrete configurations (Latin hypercube sampling over the actual inputs)
3. For each, build the dataset with those Pine inputs frozen
4. Train AG on `reached_tp1` and `reached_tp2` for each
5. Compare out-of-sample calibration and discrimination
6. Promote the best — output is exact Pine input values

#### Parameter Families

**Fib Engine:**

| Parameter | Range | Step | Default |
|-----------|-------|------|---------|
| `confluence_tolerance_pct` | 0.5%–3.0% | 0.5% | 1.5% |
| `anchor_periods` | [21,34,55], [34,55,89], [21,55,89] | discrete | [21,34,55] |
| `zone_width_atr_mult` | 0.3–1.0 | 0.1 | 0.5 |
| `min_range_pts` | 10, 15, 20 | discrete | 10 |

**Structure Logic:**

| Parameter | Range | Step | Default |
|-----------|-------|------|---------|
| `retest_window_bars` | 3–10 | 1 | 5 |
| `rejection_mode` | wick_ratio, close_beyond, both | discrete | both |

**Intermarket Engine:**

| Parameter | Range | Step | Default |
|-----------|-------|------|---------|
| `im_ema_length` | 10, 15, 20, 30 | discrete | 20 |
| `im_slope_bars` | 3, 5, 8 | discrete | 5 |
| `im_neutral_band_pct` | 0.05%, 0.1%, 0.2% | discrete | 0.1% |
| `im_min_agreement` | 2, 3, 4 (out of 6 markets) | discrete | 3 |
| `im_confirm_bars` | 1, 2, 3 | discrete | 2 |
| `im_cooldown_bars` | 0, 2, 4 | discrete | 2 |

**Volume Engine:**

| Parameter | Range | Step | Default |
|-----------|-------|------|---------|
| `vol_baseline_bars` | 10, 20, 30 | discrete | 20 |
| `vol_spike_threshold` | 1.3, 1.5, 2.0 | discrete | 1.5 |
| `vol_gate_enabled` | true, false | discrete | true |

**Session / State:**

| Parameter | Range | Step | Default |
|-----------|-------|------|---------|
| `block_opening_minutes` | 0, 15, 30 | discrete | 15 |
| `block_lunch_window` | true, false | discrete | true |
| `eth_allowed` | true, false | discrete | true |

**Target: ~25 parameter combinations for the initial grid** (Latin hypercube sampling from the full space, not exhaustive Cartesian product).

---

### 6. Unified vs Split Configuration Decision

Default: start unified with `direction` as a feature. AG decides whether direction matters for probability estimates. Split into separate LONG/SHORT Pine configs only if directional probability accuracy diverges > 10pp out-of-sample. AG's output on this is a concrete Pine recommendation: either one parameter set for both, or two sets with a direction switch.

---

### 7. AG Training Protocol

#### Model Type: Multi-Output Probability + Stop Distance

AG trains two probability models and evaluates stop families:

1. **TP1 model**: `reached_tp1` → calibrated probability of hitting 1.236 extension → used to validate Pine's deterministic confidence score
2. **TP2 model**: `reached_tp2` → calibrated probability of hitting 1.618 extension → same validation purpose
3. **Stop family evaluation**: AG compares the bounded stop family members (fib invalidation, fib+ATR, structure breach, fixed ATR) across fib levels and regimes → outputs which family member to use as a Pine config decision

All probability models use `predict_proba()` for calibrated output.

#### AutoGluon Configuration

```python
tp1_predictor = TabularPredictor(
    label="reached_tp1",
    problem_type="binary",
    eval_metric="log_loss",           # calibrated probabilities
    path=output_dir / "tp1",
)

tp1_predictor.fit(
    train_data=train_df,
    tuning_data=val_df,
    time_limit=7200,
    presets="best_quality",
    num_bag_folds=5,
    num_stack_levels=2,
    excluded_model_types=["KNN", "FASTAI"],
    ag_args_fit={"num_cpus": 10, "num_early_stopping_rounds": 50},
)
# Same config for TP2 model
# Stop family evaluation: compare outcomes across the 4 bounded stop methods per fib level/regime
```

#### Why Log Loss

AG uses log_loss so its offline probability estimates are calibrated. This calibration is used to **validate** that Pine's deterministic confidence scores map to real-world hit rates. Pine does NOT call `predict_proba()` live. Pine computes a deterministic score from its features; AG's offline calibration proves what that score means in terms of real probability. The mechanism for getting probability onto the chart is the locked v1 path defined in Locked v1 Mechanisms above.

---

### 8. Walk-Forward Validation Protocol

Expanding window with purge + embargo (Lopez de Prado):

- **Min training**: 3 months (~6,000 bars) | **Validation**: 1 month (~2,000 bars)
- **Purge**: 40 bars | **Embargo**: 80 bars | **Folds**: 5 expanding windows

#### Per-Fold Metrics

- TP1/TP2 offline probability calibration (validates Pine's deterministic confidence score)
- TP1/TP2 AUC-ROC (discrimination power)
- Stop rate by stop family member (which family member performs best per fib level?)
- Signals per week at various confidence thresholds
- Feature importance (top 10 — which Pine features matter most?)
- Performance by fib level touched (does 0.618 behave differently than 0.382?)
- Performance by session (RTH vs ETH) and direction (LONG vs SHORT)
- Performance during macro event windows vs quiet periods (Tier 2 research insight)
- Which Pine modules contributed vs were dead weight

#### Stability: AUC > 0.60 every fold, calibration error < 10%

---

### 9. Feature Selection Protocol

Per-fold on training data: IC ranking → cluster dedup → 15-25 features.
Cross-fold: features in ≥ 4/5 folds = robust (keep in Pine). < 2/5 = fragile (remove from Pine).

AG also reports which Pine indicator modules are worth keeping vs dead weight. This directly maps to Pine: "remove this module" or "keep this module with these settings."

---

### 10. Promotion Rule

| Metric | Threshold |
|--------|-----------|
| Mean OOS TP1 AUC-ROC | ≥ 0.65 |
| Mean OOS TP2 AUC-ROC | ≥ 0.60 |
| TP1 calibration error | ≤ 10% |
| Worst fold TP1 AUC | ≥ 0.55 |
| Stop rate on high-confidence calls | ≤ 30% |
| High-confidence signals per week | 3–25 |
| AUC stability across folds | ≤ 0.15 |

Pine reproducibility gate: every feature computable in Pine v6 with ≤ 40 `request.security()` + `request.economic()` calls total.

**The promoted output is a Pine config packet** — exact input values, exact thresholds, exact weights, exact on/off decisions, exact rule/gate selections. Not a model blob. Not a notebook conclusion.

---

### 11. Failure Rule

If no configuration meets thresholds: report honestly, identify failure mode, deliver failure packet with same format but marked FAILED. Do not force a promotion. Do not hide instability.

---

### 12. Pine-Ready Optimization Packet Format

The AG work product plugs directly into Pine's input schema and rule schema.

```
WARBIRD AG OPTIMIZATION PACKET
================================
Status: PROMOTED | FAILED
Model: Fib continuation probability engine
Training Data:
- date range
- pullback event count
- MES bar count
- sample counts by bucket depth
- packet generated at timestamp

PINE INPUT VALUES (exact — plug directly into indicator)
----------------------------------
confluence_tolerance_pct: X.X%
anchor_periods: [A, B, C]
zone_width_atr_mult: X.X
min_range_pts: XX
retest_window_bars: X
rejection_mode: [mode]
im_ema_length: XX
im_slope_bars: X
im_neutral_band_pct: X.X%
im_min_agreement: X
im_confirm_bars: X
im_cooldown_bars: X
vol_baseline_bars: XX
vol_spike_threshold: X.X
vol_gate_enabled: [bool]
block_opening_minutes: XX
block_lunch_window: [bool]
eth_allowed: [bool]
[every surviving Pine input with its optimized value]

MODULE KEEP/REMOVE DECISIONS
----------------------------------
useIntermarket: [true/false] — [reason]
useNewsProxy: [true/false] — [reason]
useCreditFilter: [true/false/shorts_only] — [reason]
useReentryMode: [true/false] — [reason]
[every surviving module with AG's recommendation]

TP1/TP2 HIT RATES BY FIB LEVEL
----------------------------------
0.236: TP1=XX%, TP2=XX% (N obs)
0.382: TP1=XX%, TP2=XX%
0.5:   TP1=XX%, TP2=XX%
0.618: TP1=XX%, TP2=XX%
0.786: TP1=XX%, TP2=XX%

STOP FAMILY SELECTION (Pine-implementable, bounded)
----------------------------------
- per fib level: selected stop family member (`fib_invalidation` / `fib_atr` / `structure` / `fixed_atr`)
- per regime: any regime-specific stop-family overrides

MACRO EVENT RESEARCH (Tier 2 — only promoted if Pine analogue proven)
----------------------------------
- CPI day: TP1 delta, TP2 delta, reversal delta, Pine analogue status
- FOMC week: TP1 delta, TP2 delta, reversal delta, Pine analogue status
- NFP day: TP1 delta, TP2 delta, reversal delta, Pine analogue status
- every other promoted macro insight with Pine analogue status

CONFIDENCE SCORE CALIBRATION (maps Pine's deterministic score to real probability)
----------------------------------
- `BIN_1` through `BIN_5` calibration table for TP1 / TP2 / reversal
- reversal-warning threshold and suppression rules

RE-ENTRY CONDITIONS
----------------------------------
- explicit re-entry rule by setup archetype / regime

WALK-FORWARD SUMMARY
----------------------------------
| Fold | TP1 AUC | TP2 AUC | Cal | Stop% | Signals/wk |
|------|---------|---------|-----|-------|------------|

BREAKDOWN
----------------------------------
By fib level / session bucket / direction / regime bucket / macro event

PINE IMPLEMENTATION NOTES
----------------------------------
- total `request.security()` + `request.economic()` calls used vs v1 budget
- exact Pine functions/modules required for packet compatibility
- table fields required: action, TP1 probability, TP2 probability, reversal risk, win rate, stats window, regime, conflict, stop family, TP1/TP2 path
- alerts kept: entry long, entry short, pivot break reversal (.50 warning). All other alerts moved to dashboard.
```

---

### 13. Implementation Files

| File | Purpose |
|------|---------|
| `scripts/ag/build-fib-snapshots.py` | Materialize point-in-time MES 15m fib state snapshots with frozen anchors and trigger-context fields for AG |
| `scripts/ag/build-fib-dataset.py` | Find all fib pullback events, compute features (Tier 1 + Tier 2 from Supabase), generate labels |
| `scripts/ag/train-fib-model.py` | TP1/TP2 probability models + stop-family evaluation with walk-forward CV |
| `scripts/ag/evaluate-configs.py` | Parameter grid evaluation — each config maps to a Pine input set |
| `scripts/ag/generate-packet.py` | Generate Pine-ready optimization packet with exact input values |

Existing files (`build-dataset.py`, `train-warbird.py`, `fib-engine.ts`, `trigger-15m.ts`) are reference only — different model architecture.

---

### 14. Audited Runtime, Scheduling, and Ownership Snapshot (2026-03-23)

This snapshot is based on the linked Supabase project, the repo runtime surfaces, the production environment variable set, and the live Supabase/Postgres database.

#### Verified live environment

1. Supabase project `warbird-pro` is linked and active as a Next.js deployment.
2. Production environment variables include the required Supabase/Postgres connection surface plus `DATABENTO_API_KEY` and `FRED_API_KEY`.
3. Supabase cloud now has the raw-news schema and raw-news Supabase cron wrapper migrations applied live (`20260326000019`, `20260326000020`) in addition to the earlier baseline schema.
4. Local PostgreSQL 17 is installed, running on `:5432`, and `warbird_training` now exists locally.
5. The repo currently has **no** `supabase/functions/` directory and **no** repo-owned `pg_cron` schedule definitions.

#### Current runtime ownership: Supabase pg_cron is the sole schedule producer

Supabase pg_cron owns all recurring job scheduling. Supabase hosts the Next.js App Router route handlers that pg_cron calls via pg_net. Vercel does not own any cron schedules.

1. All recurring jobs are triggered by Supabase pg_cron via pg_net HTTP POST to the App Router route.
2. Supabase is retained only for dashboard delivery and read-oriented API/UI surfaces.

| Responsibility | Current route | Current schedule | Current write surface |
| --- | --- | --- | --- |
| MES minute pull (primary) | `app/api/cron/mes-1m/route.ts` | Supabase `pg_cron`: `* * * * 0-5` (`public.run_mes_1m_pull`) | `mes_1m`, `mes_15m`, `job_log` |
| MES catch-up (legacy manual only) | `app/api/cron/mes-catchup/route.ts` | no recurring schedule | `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`, `job_log` |
| Cross-asset catch-up | `app/api/cron/cross-asset/route.ts` | `*/15 * * * *` | `cross_asset_1h`, `cross_asset_1d`, `job_log` |
| FRED rates | `app/api/cron/fred/[category]/route.ts` | `0 5 * * *` | `econ_rates_1d`, `job_log` |
| FRED yields | `app/api/cron/fred/[category]/route.ts` | `0 6 * * *` | `econ_yields_1d`, `job_log` |
| FRED vol | `app/api/cron/fred/[category]/route.ts` | `0 7 * * *` | `econ_vol_1d`, `job_log` |
| FRED inflation (realized only) | `app/api/cron/fred/[category]/route.ts` | `0 8 * * *` | `econ_inflation_1d`, `job_log` |
| Massive inflation expectations | `app/api/cron/massive/inflation-expectations/route.ts` | `30 8 * * *` | `econ_inflation_1d`, `job_log` |
| FRED fx | `app/api/cron/fred/[category]/route.ts` | `0 9 * * *` | `econ_fx_1d`, `job_log` |
| FRED labor | `app/api/cron/fred/[category]/route.ts` | `0 10 * * *` | `econ_labor_1d`, `job_log` |
| FRED activity | `app/api/cron/fred/[category]/route.ts` | `0 11 * * *` | `econ_activity_1d`, `job_log` |
| FRED commodities | `app/api/cron/fred/[category]/route.ts` | `0 12 * * *` | `econ_commodities_1d`, `job_log` |
| FRED money | `app/api/cron/fred/[category]/route.ts` | `0 13 * * *` | `econ_money_1d`, `job_log` |
| FRED indexes | `app/api/cron/fred/[category]/route.ts` | `0 14 * * *` | `econ_indexes_1d`, `job_log` |
| Economic calendar | `app/api/cron/econ-calendar/route.ts` | `0 15 * * *` | `econ_calendar`, `job_log` |
| Geopolitical risk | `app/api/cron/gpr/route.ts` | `0 19 * * *` | `geopolitical_risk_1d`, `job_log` |
| Trump effect | `app/api/cron/trump-effect/route.ts` | `30 19 * * *` | `trump_effect_1d`, `job_log` |
| Detect setups | `app/api/cron/detect-setups/route.ts` | `*/5 12-21 * * 1-5` | legacy `warbird_*` setup stack, `job_log` |
| Measured moves | `app/api/cron/measured-moves/route.ts` | `0 18 * * 1-5` | `measured_moves`, `job_log` |
| Score trades | `app/api/cron/score-trades/route.ts` | **STOPPED** — removed from Supabase cron migration files 2026-03-26 | `trade_scores`, `job_log` |
| Legacy forecast check | `app/api/cron/forecast/route.ts` | `30 * * * 1-5` | legacy `warbird_forecasts_1h`, `job_log` |

#### Target runtime ownership: Supabase-owned schedules and functions

The target runtime for recurring jobs is:

1. Supabase-owned schedules
2. Supabase-owned function execution for recurring ingestion, aggregation, and publish-up work
3. Supabase retained only for dashboard delivery and read-oriented API/UI surfaces

Target Supabase-owned recurring function inventory:

| Target function | Replaces current route | Writes |
| --- | --- | --- |
| `mes-1m-pull` | `/api/cron/mes-1m` | `mes_1m`, `mes_15m`, `job_log` |
| `mes-catchup` (legacy/manual) | `/api/cron/mes-catchup` | `mes_*`, `job_log` |
| `cross-asset` | `/api/cron/cross-asset` | `cross_asset_*`, `job_log` |
| `fred-rates` | `/api/cron/fred/rates` | `econ_rates_1d`, `job_log` |
| `fred-yields` | `/api/cron/fred/yields` | `econ_yields_1d`, `job_log` |
| `fred-vol` | `/api/cron/fred/vol` | `econ_vol_1d`, `job_log` |
| `fred-inflation` | `/api/cron/fred/inflation` | `econ_inflation_1d`, `job_log` |
| `massive-inflation-expectations` | `/api/cron/massive/inflation-expectations` | `econ_inflation_1d`, `job_log` |
| `fred-fx` | `/api/cron/fred/fx` | `econ_fx_1d`, `job_log` |
| `fred-labor` | `/api/cron/fred/labor` | `econ_labor_1d`, `job_log` |
| `fred-activity` | `/api/cron/fred/activity` | `econ_activity_1d`, `job_log` |
| `fred-commodities` | `/api/cron/fred/commodities` | `econ_commodities_1d`, `job_log` |
| `fred-money` | `/api/cron/fred/money` | `econ_money_1d`, `job_log` |
| `fred-indexes` | `/api/cron/fred/indexes` | `econ_indexes_1d`, `job_log` |
| `econ-calendar` | `/api/cron/econ-calendar` | `econ_calendar`, `job_log` |
| `gpr` | `/api/cron/gpr` | `geopolitical_risk_1d`, `job_log` |
| `trump-effect` | `/api/cron/trump-effect` | `trump_effect_1d`, `job_log` |
| `detect-setups` | `/api/cron/detect-setups` | canonical setup tables + dashboard live state + `job_log` |
| `measured-moves` | `/api/cron/measured-moves` | `measured_moves`, `job_log` |
| `score-trades` | `/api/cron/score-trades` | trade outcomes + `job_log` |
| `setup-outcome-publish` (legacy `/api/cron/forecast` route name until cutover) | `/api/cron/forecast` | `warbird_active_signals_v`, `warbird_active_packet_metrics_v`, `warbird_active_packet_recommendations_v`, `job_log` |

#### Runtime rules

1. Supabase pg_cron is the only schedule producer. No recurring schedules in `Supabase cron migration files`.
2. Every recurring job must keep `job_log` writes, deterministic schedule ownership, and explicit input/output table lists.
3. Local research runs are allowed, but recurring production ownership must end up in Supabase, not Supabase and not a local always-on process.
4. Supabase is for the Next.js frontend dashboard and read-oriented API/UI route handlers only.

---

### 15. Approved Data Scope And Provider Contract

This is the exact approved source boundary for Phase 1 through Phase 4 work.

#### Provider boundary

1. Databento `GLBX.MDP3 Standard ($179 / month)` is the approved exchange-data boundary.
2. FRED is the approved macro / release / calendar boundary.
3. Massive is approved for one live macro exception only: `GET /fed/v1/inflation-expectations`; treasury yields, realized inflation, and labor market remain FRED-sourced.
4. Massive stocks/indices intraday or delayed market-data products are not part of the Warbird feature contract; Databento remains the sole market intraday source.
5. Google Finance watchlist / AI summary capture is approved as **manual operator / research capture only** and is not a recurring training or live contract.

#### Databento schema scope

| Schema | Status | Use |
| --- | --- | --- |
| `ohlcv-1m` | Required | default live bar bridge and local training bar source for MES |
| `ohlcv-1h` | Required | higher-timeframe context and cross-asset backfill |
| `ohlcv-1d` | Required | daily context and official higher-timeframe history |
| `definition` | Required | symbol metadata, roll mapping, instrument identity |
| `statistics` | Required | official open interest / settlement / exchange-provided statistics |
| `ohlcv-1s` | Later-phase only | evidence-gated research; not default dashboard or training path |
| `trades` | Later-phase only | evidence-gated MES microstructure research only |
| `mbp-1` | Later-phase only | evidence-gated MES order-book research only |
| `mbp-10` | Later-phase only | evidence-gated MES order-book research only |
| `mbo` | Later-phase only | evidence-gated MES order-book research only |

Hard rules:

1. Default live/dashboard bridge is `ohlcv-1m`, not `ohlcv-1s`.
2. Use one Databento live session per live path; do not create duplicate paid sessions for identical subscriptions.
3. Do not plan around data products outside the current subscription.

#### Approved market symbols

| Role | Required baseline | Approved later-context additions |
| --- | --- | --- |
| Canonical traded object | `MES` | none |
| Equity confirmation | `ES`, `NQ` | `YM`, `RTY` |
| Rates / liquidity | `ZN`, `ZF`, `ZB`, `SR3` | `ZT` only if later explicitly added to `symbols` |
| FX / dollar proxy | `6E`, `6J` | none |
| Energy / commodity shock | `CL` | `GC`, `NG` |

#### Options scope

1. Options are limited to `MES.OPT` and `ES.OPT`.
2. `SPX` options are blocked under the current provider boundary.
3. Do not hand-roll Greeks.
4. Do not persist columns that imply provider-backed Greeks unless the provider actually emits them for the approved contract.
5. Initial options work is official-statistics-first. If 15m option-state features are pursued, they must be built from approved provider data with a clean timestamp contract before any schema expansion is treated as canonical.

#### Exact FRED series map

| Table | Exact approved series |
| --- | --- |
| `econ_rates_1d` | `FEDFUNDS`, `DFF`, `SOFR` |
| `econ_yields_1d` | `DGS2`, `DGS5`, `DGS10`, `DGS30`, `T10Y2Y`, `T10Y3M` |
| `econ_fx_1d` | `DTWEXBGS`, `DEXUSEU`, `DEXJPUS` |
| `econ_vol_1d` | `VIXCLS`, `OVXCLS` |
| `econ_inflation_1d` | `CPILFESL`, `CPIAUCSL` (FRED realized inflation) |
| `econ_labor_1d` | `UNRATE`, `PAYEMS`, `ICSA`, `CCSA` |
| `econ_activity_1d` | `INDPRO`, `RSXFS`, `DGORDER` |
| `econ_money_1d` | `M2SL`, `WALCL` |
| `econ_commodities_1d` | `DCOILWTICO`, `GVZCLS` |
| `econ_indexes_1d` | `USEPUINDXD`, `BAMLH0A0HYM2` |

#### Massive inflation-expectations map (approved exception)

| Table | Massive field | Provider-tagged `series_id` |
| --- | --- | --- |
| `econ_inflation_1d` | `forward_years_5_to_10` | `MASSIVE_IE_FORWARD_YEARS_5_TO_10` |
| `econ_inflation_1d` | `market_10_year` | `MASSIVE_IE_MARKET_10_YEAR` |
| `econ_inflation_1d` | `market_5_year` | `MASSIVE_IE_MARKET_5_YEAR` |
| `econ_inflation_1d` | `model_10_year` | `MASSIVE_IE_MODEL_10_YEAR` |
| `econ_inflation_1d` | `model_1_year` | `MASSIVE_IE_MODEL_1_YEAR` |
| `econ_inflation_1d` | `model_30_year` | `MASSIVE_IE_MODEL_30_YEAR` |
| `econ_inflation_1d` | `model_5_year` | `MASSIVE_IE_MODEL_5_YEAR` |

#### Mandatory macro package (provider-agnostic)

These four macro domains are required in every Phase 4+ training snapshot:

1. `yields`
2. `inflation`
3. `inflation_expectations`
4. `labor_market`

Source policy:

1. `yields`, `inflation` (realized), and `labor_market` remain on the existing FRED ingestion path.
2. `inflation_expectations` is sourced from Massive endpoint `GET /fed/v1/inflation-expectations`.
3. Massive inflation-expectations rows are mapped into `econ_inflation_1d` via deterministic provider-tagged `series_id` values and logged via `job_log`; no second macro feature path is allowed.

Dollar-state rule:

1. Local research uses FRED broad-dollar and FX proxies, not a separate paid `DXY` provider feed.
2. The hidden export name `ml_event_dxy_state` remains the stable contract label for the dollar-state proxy.
3. Pine may use `DXY` directly only if the TradingView live path is validated and semantically mapped back to the same dollar-state concept.

#### Promotion-parity rule

1. If a feature cannot be computed in Pine exactly, or mirrored into the live stack as an approved realtime state, it cannot drive live decisions.
2. The only valid feature classes are:
   - Pine-native
   - mirrored-live
   - research-only
3. Research-only features may inform model discovery and reports, but not live indicator logic.

---

### 16. Local Training Warehouse Requirement

The AG system needs a local PostgreSQL training warehouse. This is the research and training workbench for the MES 15m contract. It is not the live production decision owner.

#### Current local status

1. PostgreSQL 17 is installed and running on `:5432`.
2. Python `3.12` is installed.
3. AutoGluon `1.5.0` is installed globally.
4. `warbird_training` exists locally.
5. A project-local Python venv does not exist yet.
6. `scripts/ag/` remains effectively empty and is still a blocking gap.
7. A local Supabase stack is not running yet, so current local execution truth is PostgreSQL-first, not full local Supabase-first.

#### Local warehouse responsibilities

1. Hold explicit source snapshots aligned to the MES 15m bar-close contract.
2. Hold feature-engineering staging tables and auditable training artifacts.
3. Hold SHAP, calibration, packet candidates, and evaluation outputs.
4. Never become a required always-on dependency for the cloud dashboard or live chart.

#### Exact local source-snapshot surface

The local warehouse may materialize explicit snapshots of:

- `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`
- `cross_asset_1h`, `cross_asset_1d`
- `options_stats_1d`
- `econ_rates_1d`, `econ_yields_1d`, `econ_fx_1d`, `econ_vol_1d`, `econ_inflation_1d`, `econ_labor_1d`, `econ_activity_1d`, `econ_money_1d`, `econ_commodities_1d`, `econ_indexes_1d`
- `econ_calendar`, `macro_reports_1d`, `geopolitical_risk_1d`, `trump_effect_1d`

Every snapshot table or extract must record:

- source table name
- snapshot timestamp
- source max timestamp
- load timestamp

#### Exact local training / ops tables

| Table | Purpose | Minimum key columns |
| --- | --- | --- |
| `warbird_training_runs` | one row per AG run | `run_id`, `created_at`, `contract_version`, `dataset_date_range`, `feature_count`, `packet_status`, `tp1_auc`, `tp2_auc`, `calibration_error` |
| `warbird_training_run_metrics` | local full metric rows per run/target/split | `run_id`, `target_name`, `split_code`, `metric_family`, `metric_name`, `metric_value`, `is_primary` |
| `warbird_shap_results` | local feature-level explainability per run | `run_id`, `feature_name`, `feature_family`, `tier`, `mean_abs_shap`, `rank_in_run` |
| `warbird_shap_indicator_settings` | local SHAP-derived indicator-setting candidates | `run_id`, `indicator_family`, `parameter_name`, `suggested_numeric_value`, `stability_score` |
| `warbird_snapshot_pine_features` | point-in-time Pine hidden exports per snapshot | `snapshot_id`, `feature_contract_version`, `ml_confidence_score`, `ml_direction_code`, `ml_setup_archetype_code` |
| `warbird_candidate_macro_context` | local Tier 2 macro context | `candidate_id`, `bar_date`, `macro_window_active`, `gpr_level` |
| `warbird_candidate_microstructure` | local OHLCV-derived 1m context | `candidate_id`, `window_bars`, `window_start_ts`, `window_end_ts`, `vol_ratio_at_entry`, `atr_14_at_touch` |
| `warbird_candidate_path_diagnostics` | local path-first-touch diagnostics | `candidate_id`, `first_touch_code`, `bars_to_tp1`, `bars_to_tp2`, `bars_to_stop` |
| `warbird_candidate_stopout_attribution` | local stop-out attribution surface | `candidate_id`, `stop_driver_code`, `stop_driver_confidence`, `notes_json` |
| `warbird_feature_ablation_runs` | local feature-family add/remove experiments | `ablation_run_id`, `baseline_run_id`, `candidate_run_id`, `feature_family`, `metric_name`, `delta_metric_value` |
| `warbird_entry_definition_experiments` | local entry-definition experiment results | `experiment_id`, `experiment_code`, `anchor_policy_code`, `retrace_rule_code`, `tp1_before_sl_rate`, `tp2_before_sl_rate` |

#### Required local implementation files

| File | Responsibility |
| --- | --- |
| `scripts/ag/load-source-snapshots.py` | explicit local loads from approved source tables or extracts |
| `scripts/ag/build-fib-dataset.py` | 15m-aligned dataset assembly and label construction |
| `scripts/ag/compute-features.py` | deterministic non-leaky feature computation and bucket assignment |
| `scripts/ag/train-fib-model.py` | staged AutoGluon module admission and packet training |
| `scripts/ag/evaluate-configs.py` | packet candidate comparison, fold review, calibration checks |
| `scripts/ag/generate-packet.py` | Pine-ready packet assembly |
| `scripts/ag/publish-artifacts.py` | idempotent publish-up to cloud ops tables |

#### Local warehouse rules

1. Populate it through explicit cloud snapshots and local TradingView capture flows only.
2. Do not build or extend a standing cloud-to-local sync subsystem or a local-first production ingestion path.
3. The local warehouse may hold scratch tables and intermediate joins.
4. No live production endpoint may depend on the local warehouse being up.
5. Research news collection may target local, but recurring production-owned raw-news retention remains cloud-first; local copies are optional research mirrors only.

---

### 17. Cloud Publish-Up And Dashboard Realtime Requirement

Cloud is the display, realtime, and operator-facing operations surface. It is not the local model-training workbench.

#### Verified current cloud state

1. Legacy cloud tables from the earlier 1H / 4H architecture still exist and do not match the locked MES 15m fib-outcome contract:
   - `warbird_forecasts_1h`
   - `warbird_daily_bias`
   - `warbird_structure_4h`
   - `warbird_conviction`
   - `warbird_risk`
2. `public.models` exists but is empty and is not the right packet / activation lifecycle table.
3. `trade_scores` exists but is empty and reflects the older predicted-price / MAE / MFE path.
4. No cloud tables currently exist for:
   - `warbird_training_runs`
   - `warbird_training_run_metrics`
   - `warbird_packets`
   - `warbird_packet_activations`
   - `warbird_packet_metrics`
   - `warbird_packet_feature_importance`
   - `warbird_packet_setting_hypotheses`
   - `warbird_packet_recommendations`
5. No cloud storage buckets are in active use for model/report artifacts.

#### Required cloud publish-up entities

| Table | Purpose | Minimum key columns |
| --- | --- | --- |
| `warbird_training_runs` | published run registry | `run_id`, `created_at`, `contract_version`, `symbol_code`, `timeframe`, `dataset_date_range`, `feature_count`, `tp1_auc`, `tp2_auc`, `calibration_error`, `packet_status` |
| `warbird_training_run_metrics` | full training/evaluation metrics for Admin and model review | `run_id`, `target_name`, `split_code`, `fold_code`, `metric_family`, `metric_name`, `metric_value`, `is_primary` |
| `warbird_packets` | AG scoring/model packet registry | `packet_id`, `run_id`, `created_at`, `contract_version`, `symbol_code`, `timeframe`, `status`, `packet_json`, `sample_count`, `promoted_at`, `superseded_at` |
| `warbird_packet_activations` | immutable activation log | `activation_id`, `packet_id`, `activated_at`, `deactivated_at`, `activation_reason`, `rollback_reason`, `is_current` |
| `warbird_packet_metrics` | structured Admin KPIs per packet target/split | `packet_id`, `target_name`, `split_code`, `auc`, `log_loss`, `brier_score`, `calibration_error`, `resolved_count`, `open_count` |
| `warbird_packet_feature_importance` | published top drivers for active packet review | `packet_id`, `target_name`, `feature_family`, `feature_name`, `importance_source_code`, `importance_rank`, `mean_abs_importance` |
| `warbird_packet_setting_hypotheses` | structured indicator and entry-definition suggestions | `packet_id`, `target_name`, `indicator_family`, `parameter_name`, `action_code`, `stability_score`, `support_summary_json` |
| `warbird_packet_recommendations` | structured AI-generated Admin guidance | `packet_id`, `section_code`, `priority`, `recommendation_code`, `title`, `summary_text`, `rationale_json`, `action_json` |

#### Required cloud realtime dashboard entities

Current dashboard consumers already expect `mes_1m` and `mes_15m`. Keep those. The Next.js dashboard and any TradingView-facing mirror must consume the same MES 15m fib/state contract. Add these:

| Table | Purpose | Minimum key columns |
| --- | --- | --- |
| `warbird_fib_engine_snapshots_15m` | canonical frozen fib engine state per MES 15m bar close (provenance is `fib_engine_version`, not packet) | `snapshot_id`, `bar_close_ts`, `symbol_code`, `timeframe`, `fib_engine_version`, `anchor_hash`, `direction`, `anchor_high`, `anchor_low`, `resolved_left_bars`, `resolved_right_bars`, `target_eligible_20pt` |
| `warbird_fib_candidates_15m` | canonical candidate + decision state per MES 15m bar close | `candidate_id`, `snapshot_id`, `bar_close_ts`, `symbol_code`, `timeframe`, `candidate_seq`, `setup_archetype_code`, `fib_level_touched`, `entry_price`, `stop_loss`, `tp1_price`, `tp2_price`, `decision_code`, `reason_code`, `packet_id` |
| `warbird_candidate_outcomes_15m` | candidate-level realized truth for both taken and skipped trades | `outcome_id`, `candidate_id`, `bar_close_ts`, `symbol_code`, `timeframe`, `outcome_code`, `mae_pts`, `mfe_pts`, `scorer_version`, `scored_at` |
| `warbird_signals_15m` | published TradingView signals only | `signal_id`, `candidate_id`, `bar_close_ts`, `symbol_code`, `timeframe`, `status`, `emitted_at`, `tv_alert_ready`, `packet_id` |
| `warbird_signal_events` | lifecycle events for published signals only | `signal_event_id`, `signal_id`, `ts`, `event_type`, `price` |

The dashboard compatibility/live views should then be derived from those canonical tables:

| View | Purpose | Minimum source contract |
| --- | --- | --- |
| `warbird_active_signals_v` | mirrored current signal and candidate state for chart/dashboard rendering | latest joined row from `warbird_signals_15m` + `warbird_fib_candidates_15m` + `warbird_candidate_outcomes_15m` |
| `warbird_admin_candidate_rows_v` | Admin candidate row surface — **locked staple columns: Dir, Target, TP1 Hit, TP2 Hit, SL Hit, Status** (plus Time, Entry, SL Price, TP2 Price, Fib Level, Outcome, Decision). Replaces legacy "Measured Moves". View must expose explicit `tp1_hit`, `tp2_hit`, `sl_hit` computed columns — not the ambiguous single `target_hit_state`. | current rows from `warbird_fib_candidates_15m` + `warbird_fib_engine_snapshots_15m` + `warbird_signals_15m` + `warbird_candidate_outcomes_15m` |
| `warbird_active_training_run_metrics_v` | Admin full-metric surface for the active packet run | current row from `warbird_packet_activations` + `warbird_packets` + `warbird_training_run_metrics` |
| `warbird_active_packet_metrics_v` | Admin packet KPI surface | current row from `warbird_packet_activations` + `warbird_packets` + `warbird_packet_metrics` |
| `warbird_active_packet_feature_importance_v` | Admin feature-driver surface | current row from `warbird_packet_activations` + `warbird_packets` + `warbird_packet_feature_importance` |
| `warbird_active_packet_setting_hypotheses_v` | Admin indicator-setting suggestion surface | current row from `warbird_packet_activations` + `warbird_packets` + `warbird_packet_setting_hypotheses` |
| `warbird_active_packet_recommendations_v` | formatted Admin AI-guidance surface | current row from `warbird_packet_activations` + `warbird_packets` + `warbird_packet_recommendations` |

#### Locked Admin candidate table staple columns (2026-03-29)

The Admin candidate table (replacing legacy "Measured Moves") MUST include these columns. The first 8 are non-negotiable staples; the remaining 5 are recommended operator context.

| # | Column | View field | Values | Notes |
|---|--------|-----------|--------|-------|
| 1 | **Time** | `bar_close_ts` | timestamp | Row identity, sort descending |
| 2 | **Dir** | `direction` | LONG / SHORT | Color-coded badge |
| 3 | **Entry** | `entry_price` | numeric | Entry price level |
| 4 | **Target** | `tp1_price` | numeric | TP1 target price (canonical target) |
| 5 | **TP1 Hit** | `tp1_hit` | HIT / MISS / OPEN | Explicit derived state — replaces `target_hit_state` |
| 6 | **TP2 Hit** | `tp2_hit` | HIT / MISS / OPEN | Explicit derived state — new column |
| 7 | **SL Hit** | `sl_hit` | HIT / MISS / OPEN | Explicit derived state — new column |
| 8 | **Status** | `status` | ACTIVE / TP1_HIT / TP2_HIT / STOPPED / CANCELLED | Signal lifecycle state |
| 9 | SL Price | `stop_loss` | numeric | Mechanical stop level |
| 10 | TP2 Price | `tp2_price` | numeric | Full extension target |
| 11 | Fib Level | `fib_level_touched` | enum | Which fib level triggered |
| 12 | Outcome | `outcome_state` | TP2_HIT / TP1_ONLY / STOPPED / REVERSAL / OPEN | Final resolved state |
| 13 | Decision | `decision_code` | TAKE_TRADE / WAIT / PASS | Model policy decision |

**Required view changes to migration 038 before Admin cutover:**

Replace the single ambiguous `target_hit_state` column in `warbird_admin_candidate_rows_v` with three explicit columns:

```sql
case when o.tp1_before_sl then 'HIT'
     when o.sl_before_tp1 or o.sl_after_tp1_before_tp2 then 'MISS'
     else 'OPEN' end                                            as tp1_hit,

case when o.tp2_before_sl then 'HIT'
     when o.outcome_code in ('TP1_ONLY','STOPPED','REVERSAL') then 'MISS'
     else 'OPEN' end                                            as tp2_hit,

case when o.sl_before_tp1 or o.sl_after_tp1_before_tp2 then 'HIT'
     when o.outcome_code in ('TP2_HIT','TP1_ONLY') then 'MISS'
     else 'OPEN' end                                            as sl_hit,
```

#### Locked replacement semantics for the legacy forecast surface

1. `warbird_forecasts_1h` is a legacy misnamed surface from the pre-15m architecture and must not drive new work.
2. Its replacement contract is the MES 15m setup outcome surface:
   - `warbird_fib_candidates_15m.tp1_probability`
   - `warbird_fib_candidates_15m.tp2_probability`
   - `warbird_fib_candidates_15m.reversal_risk`
   - `warbird_fib_candidates_15m.decision_code`
3. No new publish-up contract may use predicted-price tables as the primary model output.

#### Cloud rules

1. Keep the new tables in `public`.
2. Do not overload `public.models` or `trade_scores` for the new packet lifecycle.
3. Keep cloud tables strictly publish-up targets, dashboard state, and run history.
4. Do not make cloud tables part of the direct live Pine decision path.
5. Do not create new predicted-price or `1H forecast` tables; the live model surface is MES 15m setup-outcome state keyed by `bar_close_ts`.
6. Every publish-up write must be idempotent on its natural key.
7. Cloud Realtime is the dashboard transport; Databento is not a dashboard-direct contract.
8. `warbird_triggers_15m`, `warbird_conviction`, `warbird_risk`, `warbird_setups`, `warbird_setup_events`, and `measured_moves` are **legacy/operational only**. They are not the canonical AG training truth, must not drive new architecture, and will be retired once the canonical tables above exist and all readers have migrated. The legacy `detect-setups` and `score-trades` routes that write to these tables are unscheduled bridge code pending the canonical Edge Function writer.

#### Cloud pruning sequence

Do not drop a table until its current readers and writers are removed or replaced.

Current audited prune candidates by class:

1. Dormant / zombie cloud candidates:
   - `trade_scores`
   - `vol_states`
   - `sources`
   - `policy_news_1d`
   - `options_ohlcv_1d`
2. Legacy 1H / 4H tables to retire only after route migration:
   - `warbird_forecasts_1h`
   - `warbird_daily_bias`
   - `warbird_structure_4h`
   - `warbird_conviction`
   - `warbird_risk`

Current repo dependencies that block immediate removal:

1. `app/api/cron/detect-setups/route.ts` still reads or writes `warbird_forecasts_1h`, `warbird_daily_bias`, `warbird_structure_4h`, `warbird_conviction`.
2. `app/api/cron/forecast/route.ts` still reads `warbird_forecasts_1h`.
3. `app/api/admin/status/route.ts` still audits multiple dormant and legacy tables.
4. `scripts/warbird/predict-warbird.py` still writes `warbird_forecasts_1h` and `warbird_risk`.

Cloud-prune order:

1. build local warehouse and local AG scripts
2. add cloud publish-up tables and realtime dashboard tables
3. cut routes and scripts off the dormant / legacy tables
4. migrate dashboard and `admin/status` to the new publish-up and live-state surface
5. only then write drop migrations for retired cloud tables

---

### 18. Model Packet, Activation, And Rollback Lifecycle

The packet lifecycle is a first-class contract surface. It cannot stay implied.

#### Required statuses

Packet status values must include at least:

- `CANDIDATE`
- `PROMOTED`
- `FAILED`
- `ROLLED_BACK`
- `SUPERSEDED`

#### Lifecycle rules

1. Every local AG run must produce a traceable run record.
2. Every packet candidate must reference its source training run.
3. Only one packet may be active for a given `symbol_code + timeframe + contract_version`.
4. Promotion and rollback must be reversible state transitions, not destructive rewrites.
5. Use `warbird_packet_activations` for the activation log rather than mutating packet history in place.

#### Exact rollback trigger

The hard rollback / review trigger is:

- **2 consecutive initiated trades from the active packet that fail to hit PT1**

Interpretation rules:

1. Count only initiated trades from the active packet.
2. `WAIT` and `PASS` are not misses.
3. A single miss does not trigger rollback.
4. The second consecutive PT1 miss opens the rollback/retrain path immediately.

#### Required rollback response

When the 2-consecutive-PT1-miss rule is hit:

1. write the failure event and packet context to `warbird_packet_activations`, `warbird_packet_metrics`, and `warbird_packet_recommendations`
2. mark the current packet under review
3. retrain the affected model path with fresh data
4. review the packet logs and failure samples before a new promotion
5. if a prior promoted packet exists and remains valid, reactivate it explicitly rather than silently mutating the failing packet row

#### Required run contents

Each run must capture, directly or by referenced artifacts:

1. TP1 model outputs
2. TP2 model outputs
3. reversal-risk outputs
4. stop-family evaluation outputs
5. bucket calibration outputs
6. SHAP and feature-admission outputs
7. the exact active packet / prior packet comparison used in any rollback decision

#### Explicit non-goals

The model lifecycle does **not** require:

1. live cloud inference
2. cloud-to-local training sync
3. dashboard writes from Pine
4. generic model-serving endpoints for the chart path

---

### 19. Immediate Next Steps (updated 2026-03-29)

Completed items are struck through. Current blocking order is at the top of this plan.

1. ~~**Pine indicator recovery**~~ — DONE. Output budget 63/64, TradingView-validated, TA core pack visible, 3 alerts kept.
2. ~~**Phase 2 hardening**~~ — DONE. Fib direction, 0/1 lines, 20pt+ gate, stop-family, event-response, hidden exports.
3. ~~**Supabase pg_cron sole schedule producer**~~ — DONE. MES minute path live, `score-trades` stopped, all schedules in pg_cron.
4. **Fib engine hardening** — anchor-span visual gap, intermediate waypoint lines (1.382, 1.50, 1.786), direction logic, MTF alignment.
5. **Canonical writer checkpoint** — port `detect-setups` / `score-trades` to Supabase Edge Functions writing canonical tables.
6. **Dashboard/admin reader cutover** — cut off legacy tables, webhook alerts from TradingView → Edge Function → Supabase Realtime → dashboard.
7. **Stand up the local AG workbench** — venv, `scripts/ag/*.py` (load-source-snapshots, compute-features, build-fib-dataset, train-fib-model, evaluate-configs, generate-packet, publish-artifacts).
8. **Export 12+ months of TradingView MES 15m data** with canonical fib contract + TA core pack exports loaded.
9. **Train the staged baseline** — fib + event-response + TA core pack baseline → parameter admission → joint configuration.
10. **Add cloud publish-up tables** — `warbird_training_runs`, `warbird_packets`, `warbird_packet_activations`, `warbird_packet_metrics`, `warbird_packet_feature_importance`, `warbird_packet_setting_hypotheses`, `warbird_packet_recommendations`, plus dashboard views.
11. **Define packet activation and rollback transitions** including the 2-consecutive-PT1-miss rule.
12. **Migrate dashboard and admin/status consumers** to the new publish-up and live-state surface.
13. **Only after reader/writer cutover is complete, drop dormant or superseded cloud tables.**

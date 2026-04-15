# Warbird-Pro — Agent Rules

Read this file before any work.

## Agent Bootstrap

Use this root `AGENTS.md` as the workspace instruction surface. `.github/copilot-instructions.md` exists as a **thin redirector** that defers to this file for GitHub Copilot Chat compatibility; do not expand it into a competing instruction source. Any substantive rule belongs here.

### Read Order

- Start here: `AGENTS.md`
- Canonical docs index: `docs/INDEX.md`
- Then follow `docs/INDEX.md` read order exactly:
  - `docs/MASTER_PLAN.md`
  - `docs/contracts/README.md`
  - `docs/contracts/ag_local_training_schema.md`
  - `docs/runbooks/README.md`
  - `docs/contracts/schema_migration_policy.md`
  - `docs/cloud_scope.md`
  - `WARBIRD_MODEL_SPEC.md`
  - `CLAUDE.md`
  - `docs/agent-safety-gates.md`
  - `Powerdrill/reports/2026-04-06-powerdrill-findings.md`

### PowerDrill MCP

- Tracked `/.mcp.json` is the shared non-secret MCP bootstrap only (`memory`, `sequentialthinking`, `pinescript-server`, `tradingview`).
- PowerDrill secret remote config must stay out of tracked files. Kilo uses gitignored `/.kilo/kilo.json`.
- For Claude Code / Cursor after clone, add the PowerDrill MCP entry only to the local untracked `.mcp.json`. Do not commit PowerDrill keys or remote URLs with embedded secrets.
- When PowerDrill-grounded work is requested, use the PowerDrill memorylake first. Treat that memorylake as the PowerDrill retrieval surface before relying on summarized repo notes.

### Default Preflight

- Check repo state with `git status --short` before edits.
- Use `rg --files` and `rg -n` to scope the touched surface before changing code.
- Treat the local `warbird` PG17 warehouse and cloud Supabase as separate databases. Never collapse them.
- Never trust prior agent claims, stale docs, or build success as proof of schema truth.

### Default Verification

- `npm run build` is the baseline gate before every push.
- `npm run lint` is the standard lint gate for TypeScript and Next.js work.
- If any `.pine` file is touched, run the full Pine verification flow in `CLAUDE.md` and `docs/agent-safety-gates.md`.

### Repo Map

- `app/` and `components/`: Next.js App Router runtime and UI.
- `supabase/functions/`: active ingestion and cron-owned Edge Functions.
- `supabase/migrations/`: cloud-serving DDL only. No local warehouse DDL here.
- `local_warehouse/migrations/`: local-only DDL and migration ledger management for the canonical `warbird` PG17 warehouse.
- `scripts/ag/`: Python warehouse build, feature engineering, training, SHAP, publish-up.
- `data/`: raw Databento archives, parquet inputs, HG source files.
- `artifacts/`: append-only model outputs, reports, SHAP artifacts. Raw SHAP in `artifacts/shap/{run_id}/`.
- `lib/`: shared market, setup, chart, and Supabase utilities.
- `indicators/v7-warbird-institutional.pine`: active Pine work surface.
- `docs/MASTER_PLAN.md`, `docs/contracts/`, and `docs/cloud_scope.md`: active architecture, interfaces, and cloud-scope authority.
- `docs/research/`: tracked research baselines and current-state audits that remain referenced by the canonical docs index.

### Common Gotchas

- The canonical contract is MES 15m fib setups keyed to the MES 15m bar-close in `America/Chicago`.
- Pine is the canonical live signal surface; the dashboard mirrors stored engine state and is not a separate decision engine.
- The local `warbird` database on PG17 (`127.0.0.1:5432`) is the canonical warehouse truth. It owns the full data zoo: market history, AG lineage tables, the canonical training view, features, labels, SHAP artifacts, and all non-serving data.
- Supabase (`qhwgrzqjcdtdqppvhhme`) is the reduced cloud serving database for frontend, TradingView/indicator support, packet distribution, curated SHAP/admin reports, and other explicitly plan-approved published surfaces. It must not become a mirror of local.
- `rabid_raccoon` is a bootstrap-only legacy input on the same PG instance. After the one-time bootstrap into `warbird`, it is reference-only and must not be treated as canonical again.
- Canonical AG contract is **four canonical local AG tables and one canonical training view.** No version suffixes are allowed on canonical names.
- Exact local AG schema authority: `docs/contracts/ag_local_training_schema.md`.
- No mock data
- Cloud promotion is manual. Local training and SHAP must complete first; publish-up happens only after explicit approval.

## Active Plan

There is exactly one active architecture plan and one active documentation entrypoint:

- `docs/INDEX.md`
- `docs/MASTER_PLAN.md` — Warbird Full Reset Plan v5

Everything else is archived or reference-only and should not drive current implementation unless explicitly reopened through the index.

## Contract First

- The canonical trade object is the **MES 15m fib setup**.
- The canonical key is the MES 15m bar-close timestamp in `America/Chicago`.
- Any remaining `1H` wording in old docs, specs, scripts, or comments is legacy and must not drive new work.
- Pine is the canonical **live generator** (signal surface). The Next.js dashboard is the mirrored operator surface on the same contract, not a separate decision engine.
- The **training generator** is the Python reconstruction pipeline in `scripts/ag/`. It reconstructs fib snapshots, generates interactions, expands into stop-family variants, labels forward outcomes, and populates the four canonical local AG tables. `ag_training` is a canonical view over those tables.
- Canonical AG contract is **four canonical local AG tables and one canonical training view.**
- The four canonical local AG tables are:
  - `ag_fib_snapshots` — frozen fib engine state at bar close
  - `ag_fib_interactions` — **stop-agnostic** parent interaction surface; records bar × fib level context; does not carry stop geometry
  - `ag_fib_stop_variants` — **stop-specific candidate surface**; one row per `(interaction, stop family)`; `stop_family_id` is a real categorical AG feature
  - `ag_fib_outcomes` — realized forward path outcomes; one row per stop variant
- The canonical training view is:
  - `ag_training` — canonical flat join of the three tables with `WHERE outcome_label != 'CENSORED'`
- Canonical names never use version suffixes.
- Live model outputs are TP1/TP2/reversal outcome state for the MES 15m fib setup, not predicted-price forecasts.
- `news_signals` and all news/options surfaces are retired from the active contract. Do not build new schema, writer logic, dashboard logic, or training assumptions around them unless the user explicitly reopens it.
- AutoGluon is offline only and may only promote Pine-ready packet outputs.
- First model target is locked to multiclass `outcome_label`.
- First feature scope is locked to `MES 1m/15m/1h/4h + SP500 spot + macro`.
- Macro scope is locked to the curated FRED regime set + `econ_calendar` only. No news or narrative sources.

## Stack

- Next.js (App Router) — frontend dashboard and route handlers only (frontend is TradingView)
- Supabase (Postgres, Auth, Realtime, RLS, pg_cron) — cloud serving only, NO Prisma, NO ORM
- Local PG17 `warbird` database — canonical warehouse, training, SHAP, artifacts
- AutoGluon (local Python) — entry gate model, offline only
- TradingView + Rabid Raccoon v2 Pine Script — all visualization
- Supabase pg_cron — sole scheduling and recurring function producer for cloud ingestion

## Hard Rules

### Data — Zero Tolerance

- NEVER use mock, demo, placeholder, or fake data. Every data point must be real.
- If a feature has no real data yet, show NOTHING.
- NEVER query inactive symbols from Databento. Only `is_active=true AND data_source='DATABENTO'`.
- Core historical retention starts at `2020-01-01T00:00:00Z`. Do not preserve, backfill, or train on pre-2020 core rows unless the user explicitly reopens that contract.

### Naming

- Table prefix: `mes_`, `cross_asset_`, `econ_`, `warbird_`, `ag_`
- NEVER use `bhg_`, `BHG`, `mkt_futures_`, or rabid-raccoon legacy naming
- All database columns: snake_case. No ORM mapping.
- Canonical names never use version suffixes.

### Database

- There are exactly two databases in scope:
  - **Local `warbird`** on PG17 (`127.0.0.1:5432`) — canonical warehouse, training, artifacts, raw SHAP, diagnostics
  - **Cloud Supabase** (`qhwgrzqjcdtdqppvhhme`) — serving-only for frontend, indicator/runtime, packets, dashboard/admin read models, curated SHAP/report surfaces
- Local warehouse DDL lives in `local_warehouse/migrations/` with its own `local_schema_migrations` ledger. Not in `supabase/migrations/`.
- Cloud DDL lives in `supabase/migrations/` only.
- Supabase client for cloud. Service role for writes, anon for reads.
- RLS on all cloud tables. Admin client: `lib/supabase/admin.ts`
- No Prisma. No Drizzle. No ORM.
- `rabid_raccoon` is bootstrap-only. After the one-time import into `warbird`, it is legacy reference only.
- Any cloud table that does not serve frontend, indicator/runtime, packet distribution, curated SHAP/admin reports, or another explicitly locked plan surface is retirement debt and should be removed.
- Do not trust docs, status notes, prior agent claims, or `npm run build` as proof of schema truth.
- Before claiming any route, script, table, or view works, verify it against the actual database(s) with direct DB checks (`to_regclass`, `information_schema`, RPC/query checks, migration ledger checks) in the environment that matters.
- If local and cloud differ, say so explicitly. Do not collapse them into one "current state."

### Removed from Canonical Local Build

These are explicitly excluded from the canonical AG training zoo:

- `cross_asset_1d`
- cross-asset futures feature admission for first-run AG training
- all news surfaces
- all options surfaces
- all options backup CSV inputs
- all legacy setup/trade/news tables (`warbird_setups`, `scored_trades`, `news_signals`, `econ_news_1d`, `policy_news_1d`)

### Scheduling

- All cron routes validate `CRON_SECRET` and log to `job_log`.
- All cron routes: `export const maxDuration = 60`
- Supabase pg_cron is the sole schedule producer for cloud ingestion. No recurring schedules outside `Supabase cron migration files`.
- Dead schedules must be removed by updating the corresponding `Supabase cron migration files` definitions.

### Pine Indicator — Zero Tolerance

- NEVER edit `indicators/v7-warbird-institutional.pine` without explicit approval
  in the current session. State intent, wait for approval, then edit.
- NEVER push Pine changes to TradingView Pine Editor without explicit approval.
- Pine budget baselines (verified 2026-04-13):
  Institutional (`v7-warbird-institutional.pine`): 51/64 (46 plot + 2 plotshape + 3 alertcondition, 13 headroom)
  Strategy (`v7-warbird-strategy.pine`): 52/64 (50 plot + 2 plotshape, 12 headroom)
  Request budget: 4 `request.security()` + 1 `request.footprint()` = 5 paths (both files)
  Any implementation must be priced against these baselines before code is written.
- `request.footprint()` must be treated as a tightly budgeted call path.
  All footprint-derived features must be computed from one cached object per bar.
- Pine verification pipeline is mandatory before every Pine commit:
  1. pine-facade curl compiler check (authoritative compiler, run first)
  2. pine-lint.sh (0 errors required, errors block commit)
  3. check-contamination.sh
  4. npm run build
     All four must pass. STATUS: INCOMPLETE if any fail.
- Indicator data capture is automated via Pine alert -> webhook -> Supabase.
  Do not use manual TV CSV export as an ongoing process.
  Manual export is one-time historical seed only.

### Backtest and Execution Minimums

- Commission floor for MES backtesting: $1.00/side minimum.
- Slippage floor: 1 tick minimum. 2 ticks recommended.
- IS/OOS walk-forward splits: minimum one-session embargo between training
  window end and test window start. Not optional.
- AutoGluon internal ensembling is prohibited by default for the MES
  time-series harness. Do not enable `num_bag_folds > 0`,
  `num_stack_levels > 0`, `dynamic_stacking=auto`, or weighted ensemble
  re-enablement unless a purged temporal child splitter is explicitly
  implemented and approved.
- Training zoo contract: `scripts/ag/train_ag_baseline.py` must import with
  `CANONICAL_ZOO` containing all 7 families — `GBM`, `CAT`, `XGB`, `RF`,
  `XT`, `NN_TORCH`, `FASTAI`. Any edit that removes or renames a family
  dies at import time via `_assert_canonical_zoo()` and is refused by the
  `.githooks/commit-msg` guard. Override only with a deliberate
  `ZOO_CHANGE_APPROVED:` token in the commit message. **GBM-only runs
  do not exist on this project** — they have silently masqueraded as "full
  zoo" before and wasted wall time. Use the `training-gbm-only` skill as
  an iteration probe only, never as final model selection.
- Training data floor: `ag_training` row count must not fall below
  `EXPECTED_AG_TRAINING_ROWS_FLOOR = 327,000`. `load_base_training()`
  raises `SystemExit` below the floor. Raise the floor (with evidence)
  whenever the pipeline legitimately grows the count; never lower it
  silently. This catches half-loaded / truncated pipelines.
- Local git hooks: after clone, run
  `git config core.hooksPath .githooks` once so the `commit-msg` zoo
  guard is active. The guard pairs with
  `./scripts/guards/check-canonical-zoo.sh`, which can be invoked
  directly and is also listed in the `training-pre-audit` skill.
- Hard stop requirement: structural stop at `0.618 x ATR(14)` from entry.
  Emergency stop at `1.000 x ATR(14)`. Both rendered on chart from entry bar.
- Consecutive loss block: at 2 consecutive losses, signal warning. At 3, halt
  recommended. Prevent revenge re-entry clusters.
- Opening bar suppressor: no new entry signals during 9:30-9:44 ET.

### Production Boundary

- The local `warbird` PG17 warehouse is the canonical long-horizon warehouse. It holds the full data zoo, AG lineage tables and training view, raw SHAP, and all non-serving data.
- Cloud Supabase receives only published serving surfaces after manual promotion.
- Cloud never receives: `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_outcomes`, `ag_training`, raw features, raw labels, raw SHAP matrices, raw SHAP interaction matrices.
- Cloud frontend, indicator/runtime, and admin surfaces may read only the reduced Supabase surfaces explicitly published there.
- No local Supabase, no Docker-local runtime DB, and no third database.

### Build & Deploy

- `npm run build` must pass before every push.
- No `/* */` block comments to disable code. Use `//` only.
- No `--no-verify` on git hooks.
- Push to repo → merge to main → deployment pipeline auto-deploys.

### Process

- One task at a time. Complete fully.
- Less complexity, fewer moving parts, better naming.
- NEVER refactor or "improve" code outside the current task.
- NEVER add or remove dependencies without asking.
- Before each phase or checkpoint, reread the active plan section that governs that work.
- Before proposing writer, schema, or training architecture, map every required fact to an exact plan line and an exact persisted home (`table.column`, view field, or explicitly named local research entity). If you cannot point to where a fact lives, mark it missing before proposing implementation.
- After each locked phase or checkpoint, update the active plan with findings, validations, blockers, and the next blocking item.
- Update `WARBIRD_MODEL_SPEC.md` when the model contract changes.
- Update `CLAUDE.md` when current status or live operational truth changes.
- Update `AGENTS.md` only when repo rules or hard workflow constraints change.
- Update memory with the current canonical contract, required harness status, and current blocker when a phase locks.

### Memory & Session Handoff — Non-Negotiable

- `.remember/` files are **append-only**. NEVER overwrite any `.remember/today-*.md`, `.remember/now.md`, `.remember/recent.md`, or `.remember/archive.md`. All session history is permanent.
- Durable memory state for this repo lives on the external drive at `/Volumes/Satechi Hub/warbird-pro-state/`. Do not move durable memory back onto internal-disk cache/temp paths.
- The workspace `.remember/` path is a compatibility path into `/Volumes/Satechi Hub/warbird-pro-state/remember/`.
- To save a session entry: append to `today-YYYY-MM-DD.md` using Edit (not Write/Bash overwrite). Update `now.md` with the current rolling state.
- Persistent cross-session memories resolve through `/Users/zincdigital/.claude/projects/-Volumes-Satechi-Hub-warbird-pro/memory/`, which is the compatibility path for the external store at `/Volumes/Satechi Hub/warbird-pro-state/claude-project-memory/`. Store typed files there (`project_`, `feedback_`, `user_`, `reference_`) and always add a pointer line to `MEMORY.md`.
- MCP memory for this repo must resolve to `/Volumes/Satechi Hub/warbird-pro-state/mcp-memory/memory.jsonl`.
- Never use a Bash heredoc or the Write tool to overwrite an existing `.remember` file.
- Keep timestamped safety copies under `/Volumes/Satechi Hub/warbird-pro-state/backups/` before any future path migration or cleanup.
- At session end, roll `now.md` content into the dated `today-` file, then save any project/feedback memories that should persist to future sessions.

### No Hand-Rolling — Copy Working Code

- When a working implementation exists (library example, reference indicator, proven pattern), **COPY IT EXACTLY**.
- Adapt the INTERFACE (inputs, outputs, variable names). Do NOT rewrite the INTERNALS.
- If you can't explain why your version differs line-by-line from the reference, you don't understand it well enough to rewrite it.
- This applies to: library integrations, API call patterns, algorithm ports, Pine Script engine code — EVERYTHING.
- Violating this rule produces broken code that looks right but behaves wrong, wastes hours of debugging, and poisons downstream model training with inaccurate signals.

### Migration Discipline — Non-Negotiable

- **NEVER apply DDL to remote Supabase outside a migration file.** Every `execute_sql` that runs DDL creates ledger drift.
- If DDL was applied directly (MCP, psql, SQL editor), **immediately stamp the version into `supabase_migrations.schema_migrations`** and ensure a corresponding local migration file exists.
- Before running `supabase db push`, **verify the remote ledger matches local files** via `list_migrations` or `supabase db diff --linked`.
- When reconciling drift: audit EVERY object each migration should have created against the live DB. Do not assume "applied directly" — verify each one.
- After any DDL change, run `get_advisors` (security type) to catch missing RLS or policy issues.
- Local warehouse migrations use `local_warehouse/migrations/` with the `local_schema_migrations` ledger. These never go through Supabase CLI.

## MES Ingestion — Current State

**Primary (real-time):** `mes-1m` Edge Function, called every minute by Supabase pg_cron (`warbird_mes_1m_pull`). Connects to the **Databento Live API** (TCP gateway, `ohlcv-1s`, `MES.c.0` continuous contract, `stype_in=continuous`). Aggregates 1s → 1m, upserts `mes_1m`, rolls up touched 15m buckets into `mes_15m`. **Zero lag** — data arrives within the current minute.

**Fallback:** For gaps > 60 minutes, falls back to the Databento Historical API (`ohlcv-1m`). Historical API has ~10-15 min publication delay — used only for large catch-ups, never for live chart display.

**Hourly:** `mes-hourly` Edge Function pulls `ohlcv-1h` and `ohlcv-1d` directly from Databento Historical API (`MES.c.0`, `stype_in=continuous`). Rolls 1h → 4h locally (Databento has no `ohlcv-4h` schema). No application-level 1m→1h or 1h→1d aggregation.

**Symbology:** All MES Databento calls use `MES.c.0` (calendar front-month continuous) with `stype_in=continuous`. No manual contract-roll logic. The `contract-roll.ts` files are dead code.

**Retention floor:** `2020-01-01T00:00:00Z`.

**Databento schemas (Standard $179/mo):** ohlcv-1s, ohlcv-1m, ohlcv-1h, ohlcv-1d, definition, statistics. Currently using: ohlcv-1s (Live API for real-time), ohlcv-1m (Historical API fallback), ohlcv-1h, ohlcv-1d.

**Note:** This ingestion feeds cloud Supabase for live chart serving. The local `warbird` warehouse bootstraps its MES data from `rabid_raccoon` (one-time) and does not depend on cloud ingestion for canonical training truth.

## Training Skills Registry

Eleven training-specific skills are mirrored across three locations so any VS Code-hosted AI (Claude Code, Kilocode, GitHub Copilot Chat, Codex, etc.) can discover and consume them. Format is `SKILL.md` with `name` + `description` YAML frontmatter.

**Locations (all three contain identical copies):**
- `.claude/skills/<name>/SKILL.md` — Claude Code native (invoked via `Skill` tool)
- `.kilocode/skills/<name>/SKILL.md` — Kilocode native (auto-loaded by name match)
- `.github/skills/<name>/SKILL.md` — Copilot + generic consumer location

**These are testing-phase skills — the Master Plan wording in `docs/MASTER_PLAN.md` is expected to evolve during training iteration. Skill files reference the plan but do NOT treat it as frozen production contract.**

| Skill | When to use |
|-------|-------------|
| `training-pre-audit` | BEFORE every training launch — warehouse/row-count/constraint/interpreter/zoo checks |
| `training-gbm-only` | Fast GBM-only iteration / pipeline smoke test |
| `training-full-zoo` | Full multi-family AutoGluon run (GBM+CAT+XGB+RF+XT+NN_TORCH+FASTAI) for model comparison / promotion candidate |
| `training-shap` | Feature importance + leakage audit on a completed run |
| `training-monte-carlo` | P&L Monte Carlo on completed predictors: stop_family EV, threshold sweep, entry-condition breakdowns. Flat 1-tick fee, 1 contract, MES $5/pt |
| `training-quant-trading` | Time-series discipline — walk-forward, session embargo, IID-leakage signals, eval-metric choice, position sizing, friction model |
| `training-ag-best-practices` | AutoGluon 1.5 config gotchas: hyperparameters dict lockout, num_bag_folds/num_stack_levels interaction, OMP Apple Silicon, `finally:` transaction safety |
| `training-ag-feature-finder` | AutoGluon 1.5 features not yet adopted on this project — inventory + adoption notes |
| `training-supabase-data` | Training read patterns for local warbird PG17; legacy/stale table warnings |
| `training-tv-backtesting` | TradingView strategy-tester workflow for validating Pine strategy vs trained-model expectations |
| `training-indicator-optimization` | Sweep indicator parameters (ZigZag Deviation/Depth/Threshold/MinFibRange) via `tv_auto_tune.py` + `tune_strategy_params.py` |

**Tool-specific invocation notes:**
- **Claude Code** — use the `Skill` tool with the skill name (e.g., `Skill(skill="training-pre-audit")`).
- **Kilocode** — skills auto-load when context matches the `description` field; reference by name in chat to force-load.
- **GitHub Copilot Chat** — Copilot Chat will pick up `.github/skills/` content in workspace context; reference the skill path to steer a conversation.
- **Codex / any AGENTS.md-aware tool** — read this registry section first, then open the relevant SKILL.md from any of the three locations.

**Session-learned failure modes each skill prevents (from the 2026-04-15 training session):**
- AUTOGLOON ↔ AUTOGLUON spelling drift between migration 014 and trainer → `training-pre-audit` check 4
- Hardcoded `hyperparameters={"GBM": [...]}` masquerading as "full zoo" → `training-full-zoo` + `training-ag-best-practices`
- AutoGluon default IID bag-fold split destroying session embargo → `training-quant-trading` + `training-ag-best-practices`
- `.venv-autogluon` referenced in stale handoffs but doesn't exist → `training-pre-audit` check 6
- `replace_run_metrics` CheckViolation inside `finally:` block rolling back SUCCEEDED upsert → `training-ag-best-practices` transaction-safety section
- Predictor feature drift (FRED columns missing from later inference) → `training-monte-carlo` NaN-pad pattern
- Confusing market-context optimization with indicator-parameter optimization → `training-monte-carlo` vs `training-indicator-optimization` explicit distinction

**When adding new training skills:**
1. Create `.claude/skills/<new-name>/SKILL.md` first (Claude Code native location)
2. Copy to `.kilocode/skills/<new-name>/SKILL.md` and `.github/skills/<new-name>/SKILL.md`
3. Append a row to the table above in this section
4. Do not modify existing skills without reading them first; they encode expensive lessons

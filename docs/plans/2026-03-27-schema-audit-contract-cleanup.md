# Warbird Pro: Schema Audit & Contract Cleanup

> **For Claude:** REQUIRED SUB-SKILLS:
> - `superpowers:executing-plans` — task-by-task execution with review checkpoints
> - `superpowers:verification-before-completion` — before ANY commit
> - `superpowers:subagent-driven-development` — if subagent execution chosen
> - `superpowers:requesting-code-review` — at Phase 3 and Phase 5 gates

**Goal:** Fix the broken lint gate, align all user-facing copy and docs to the MES 15m fib-outcome contract, delete duplicate/retired cron routes, add auth form accessibility, and close the news_signals access gap.

**Architecture:** Cleanup-only pass. No new features. Every phase has a gate that must pass before proceeding. Pine files are NOT touched. Every deletion is evidence-backed.

**Tech Stack:** Next.js 16 App Router, Supabase Postgres (migrations), ESLint 9 flat config, next/image

---

## Pre-Work Audit Summary

Full impact analysis was performed before this plan was written. Evidence is recorded here so the implementing engineer can verify before acting.

### Quant Logic Audit (trigger-15m.ts, indicators.ts)

| Item | File | Verdict | Evidence |
|------|------|---------|----------|
| `anchorRange` param | `scripts/warbird/trigger-15m.ts:313` | **Dead code** — safe to suppress | Passed at line 475, never read in function body (lines 315-396). Zero references in `WARBIRD_MODEL_SPEC.md`. No TODOs. Not in any feature tier. |
| `trendAlignment` var | `scripts/warbird/trigger-15m.ts:351-357` | **Abandoned exploration** — safe to suppress | Computed but never wired to score. Lines 359+ never reference it. Zero references in model spec. |
| `newUpper`/`newLower` | `lib/ta/indicators.ts:408-409` | **Style fix only** — `let` → `const` | Assigned once per loop iteration, never reassigned within scope. Algorithm unchanged. Supertrend function is actively used by `computeMarketSentiment()` → `evaluateTrigger()` → `detect-setups` route. |
| `deleted` counter | `app/api/cron/mes-catchup/route.ts:55,74` | **Dead code** — safe to remove | Accumulated but never logged, returned, or read. Route itself is marked legacy. |

### Cron Route Deletion Audit

| Route | Edge Function? | pg_cron calls? | Safe to delete? | Evidence |
|-------|---------------|----------------|-----------------|----------|
| `mes-hourly` | Yes (`supabase/functions/mes-hourly/`) | Edge Function (migration 023 line 104) | **YES** | Identical logic, same tables |
| `fred/[category]` | Yes (`supabase/functions/fred/`) | Edge Function (migration 023 line 187) | **YES** | Same logic, query param vs path param |
| `massive/inflation` | Yes (`supabase/functions/massive-inflation/`) | Edge Function (migration 023 line 229) | **YES** | Identical logic |
| `massive/inflation-expectations` | Yes (`supabase/functions/massive-inflation-expectations/`) | Edge Function (migration 023 line 229) | **YES** | Identical logic |
| `trump-effect` | Yes (`supabase/functions/trump-effect/`) | Edge Function (migration 027 line 132) | **YES** | Identical logic |
| `forecast` | No | No — stub returning `legacy_forecast_path_removed` | **YES** | Self-disabled |
| `measured-moves` | No | No — stub returning `retired_canonical_writer_detect_setups` | **YES** | Self-disabled |
| `mes-catchup` | No | No — disabled by default, manual backfill only | **YES** | Self-disabled |
| **`gpr`** | Yes BUT crashes (XLSX memory) | **Vercel route** (migration 029 line 43-44) | **NO — KEEP** | Migration 029 explicitly reverts GPR to Vercel. pg_cron calls `/api/cron/gpr` on Vercel. Deleting breaks GPR ingestion. |
| `detect-setups` | No | Unknown trigger | **KEEP** | No Edge Function. Active core logic. |
| `score-trades` | No | Unknown trigger | **KEEP** | No Edge Function. Active core logic. |

### Marketing Copy Audit (vs active plan + model spec)

| Claim in `app/page.tsx` | Line | Accurate? | Evidence |
|--------------------------|------|-----------|----------|
| "machine learning forecasting" | 47 | **NO** — forecaster path retired | `forecast/route.ts` returns `legacy_forecast_path_removed`. Active plan is 15m fib-outcome. |
| "AutoGluon 1H core forecaster" | 146 | **NO** — 1H path retired | Active plan (`ag-teaches-pine` line 13): "canonical trade object is the MES 15m fib setup" |
| "Price levels, MAE bands, target zones" | 146 | **NO** — model outputs are outcomes | `WARBIRD_MODEL_SPEC.md` line 99: outcomes are `TP1_ONLY`, `TP2_HIT`, `STOPPED`, `REVERSAL`, `NO_TRADE` |
| "< 2s Data Latency" | 74 | **Unverifiable** — no live measurement | Hard-coded stat, no backing data |
| "19 Data Pipelines" | 75 | **Stale** — pipeline count changed | Cron routes reduced, Edge Functions added |
| "24/5 Market Coverage" | 76 | **YES** | MES trades Sun evening – Fri close |
| "5 lookback windows" | 131 | **YES** | Active plan line 459: confluence family `8/13/21/34/55` |
| "ML-driven" | 126 | **NO** — model not live yet | Should be "rule-driven" until AG training completes |

### news_signals Access Audit

- Migration 008 (line 97-98): Original RLS on `news_signals` table: `authenticated` SELECT
- Migration 028 (line 160): Drops table, recreates as materialized view — **no RLS reapplied**
- Materialized views CANNOT have RLS in Postgres — must use GRANT instead
- No app code currently queries `news_signals` directly (grep confirms zero hits in `app/`, `components/`, `lib/`)
- `news_signals` is refreshed by `security definer` function via pg_cron every 15 min

### Auth Forms Audit

- `components/ui/input.tsx` uses `{...props}` spread — `name` and `autoComplete` will pass through
- Forms use Supabase SDK with state variables, NOT FormData — `name` is for browser autocomplete, not submission
- Adding `name`/`autoComplete` is purely UX improvement, zero functional risk

### README Env Var Audit

| Var in README | Used in code? | Evidence |
|---------------|---------------|----------|
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | **NO** — code uses `PUBLISHABLE_KEY` | `lib/supabase/client.ts:6`, `server.ts:14`, `proxy.ts:22` all use `PUBLISHABLE_KEY` |
| `WARBIRD_FORECAST_WRITER_URL` | **NO** | grep: zero hits in `.ts`/`.tsx` files |
| `WARBIRD_FORECAST_WRITER_TOKEN` | **NO** | grep: zero hits in `.ts`/`.tsx` files |
| `WARBIRD_MAX_FORECAST_AGE_MS` | **NO** | grep: zero hits in `.ts`/`.tsx` files |
| `WARBIRD_FORECAST_WRITER_TIMEOUT_MS` | **NO** | grep: zero hits in `.ts`/`.tsx` files |

---

## Phase 1: Unblock the Lint Gate (P0)

**Gate:** `npm run lint` must exit with 0 errors, 0 warnings.

### Task 1.1: Fix 8 ESLint issues

**Files:**
- Modify: `components/theme-switcher.tsx:20`
- Modify: `components/ui/sidebar.tsx:610`
- Modify: `lib/ta/indicators.ts:408-409`
- Modify: `app/api/cron/mes-catchup/route.ts:55,74`
- Modify: `components/ui/combobox.tsx:277`
- Modify: `scripts/warbird/trigger-15m.ts:313,351`

**Pre-edit verification:** Re-run `npm run lint` to confirm the 8 issues still match this list. If new issues appeared, STOP and update this plan.

**Step 1: Suppress intentional hydration guard in theme-switcher.tsx**

```tsx
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydration guard for next-themes
    setMounted(true);
  }, []);
```
Why suppress, not fix: This is the canonical next-themes hydration pattern. Refactoring to `useSyncExternalStore` would add complexity for zero benefit.

**Step 2: Suppress intentional skeleton variation in sidebar.tsx**

```tsx
  const width = React.useMemo(() => {
    // eslint-disable-next-line react-hooks/purity -- intentional skeleton width variation (shadcn/ui)
    return `${Math.floor(Math.random() * 40) + 50}%`
  }, [])
```
Why suppress, not fix: This is shadcn/ui's `SidebarMenuSkeleton`. Random width is intentional UX for loading placeholders.

**Step 3: Change `let` to `const` in indicators.ts (lines 408-409)**

```ts
    const newUpper = hl2 + factor * atrVal;
    const newLower = hl2 - factor * atrVal;
```
Safety: Verified — each variable is assigned once per loop iteration and never reassigned. Algorithm behavior unchanged. Supertrend pipeline actively used.

**Step 4: Remove unused `deleted` accumulator in mes-catchup/route.ts**

Delete line 55 (`let deleted = 0;`) and line 74 (`deleted += data.length;`). This route is marked legacy and scheduled for deletion in Phase 2. The counter was never logged or returned.

**Step 5: Prefix unused `children` in combobox.tsx (line 277)**

```tsx
  children: _children,
```

**Step 6: Prefix unused `anchorRange` in trigger-15m.ts (line 313)**

```ts
  _anchorRange: number,
```
Safety: Verified — parameter never read in function body. Not in model spec. Not a planned feature.

**Step 7: Prefix unused `trendAlignment` in trigger-15m.ts (line 351)**

```ts
  let _trendAlignment = 0;
```
And update lines 355-356 references to `_trendAlignment`.

Safety: Verified — variable computed but never used in score calculation. Not in model spec.

### Task 1.2: Verify lint gate

```bash
npm run lint   # MUST: 0 errors, 0 warnings
npm run build  # MUST: clean build
```

**If lint fails with NEW issues:** Do not proceed. Update this plan.

### Task 1.3: Commit

```bash
git add components/theme-switcher.tsx components/ui/sidebar.tsx components/ui/combobox.tsx lib/ta/indicators.ts app/api/cron/mes-catchup/route.ts scripts/warbird/trigger-15m.ts
git commit -m "fix: resolve all 8 ESLint errors — unblock lint gate"
```

### CHECKPOINT 1

Before proceeding to Phase 2:
- [ ] `npm run lint` exits 0
- [ ] `npm run build` exits 0
- [ ] No quant logic altered (only suppressions and `let` → `const`)
- [ ] Use `superpowers:requesting-code-review` on the diff

---

## Phase 2: Contract Alignment (P1)

**Gate:** All user-facing copy matches the MES 15m fib-outcome contract per the active plan and model spec.

### Task 2.1: Align marketing page (`app/page.tsx`)

**Pre-edit verification:** Read `docs/plans/2026-03-20-ag-teaches-pine-architecture.md` lines 13-14 and `WARBIRD_MODEL_SPEC.md` line 99 to confirm the canonical terminology before writing copy.

**Reference terms from spec:**
- Model outcomes: `TP1_ONLY`, `TP2_HIT`, `STOPPED`, `REVERSAL`, `NO_TRADE`
- Canonical object: "MES 15m fib setup"
- TP1 = 1.236 fib extension, TP2 = 1.618 fib extension
- Stop = bounded family (fib invalidation, Fib+ATR, structure, fixed ATR)

**Step 1: Add next/image import**

```tsx
import Image from "next/image";
```

**Step 2: Replace raw `<img>` tags with next/image**

Line 12-13 — remove eslint-disable comment:
```tsx
<Image src="/warbird-logo.svg" alt="Warbird Pro" className="h-10 w-auto" width={120} height={40} />
```

Line 30-31 — remove eslint-disable comment:
```tsx
<Image src="/chart_watermark.svg" alt="" className="w-[600px] h-[600px]" width={600} height={600} />
```

**Step 3: Fix hero description (lines 44-47)**

Replace:
```
ML-powered Fibonacci confluence engine for S&P 500 futures.
Backtested signals, high-frequency setup detection, and machine learning
forecasting — built on real market data.
```
With:
```
Fibonacci confluence engine for MES micro S&P 500 futures.
Backtested 15-minute setup detection with quantitative entry classification — built on real market data.
```

**Step 4: Fix stats (lines 74-76)**

Replace hard-coded unverifiable stats:
```tsx
<StatBlock value="15m" label="Signal Resolution" />
<StatBlock value="5" label="Fib Lookbacks" />
<StatBlock value="24/5" label="Market Coverage" />
```
All three are verifiable: 15m is canonical timeframe, 5 is the `8/13/21/34/55` confluence family, 24/5 is MES trading hours.

**Step 5: Fix "ML Forecasting" IntelCard (lines 144-148)**

Replace:
```tsx
<IntelCard
  title="ML Forecasting"
  description="AutoGluon 1H core forecaster. Price levels, MAE bands, and target zones."
  accent={false}
/>
```
With:
```tsx
<IntelCard
  title="Setup Classification"
  description="15-minute fib-outcome engine. TP1/TP2 measured-move targets with mechanical stop-loss."
  accent={false}
/>
```

**Step 6: Fix "ML-driven" subtitle (line 126)**

Change `Backtested and ML-driven.` to `Backtested and rule-driven.`

**Step 7: Fix CTA "Machine learning" copy (line 160)**

Change to:
```
Fibonacci confluence meets quantitative setup classification. Backtested on real MES futures data.
```

**Step 8: Fix transition-all (lines 55, 164)**

Line 55: `transition-all duration-200` → `transition-colors duration-200`
Line 164: `transition-all duration-200` → `transition-colors duration-200`

**Step 9: Verify**

```bash
npm run build  # MUST pass
```

**Step 10: Commit**

```bash
git add app/page.tsx
git commit -m "fix: align marketing page to MES 15m fib-outcome contract"
```

### Task 2.2: Delete duplicate/retired App Router cron routes

**Pre-delete safety checks (ALL must pass):**

```bash
# 1. Verify NO code imports from these routes
grep -r "cron/mes-hourly\|cron/fred\|cron/massive\|cron/forecast\|cron/measured-moves\|cron/mes-catchup\|cron/trump-effect" app/ lib/ components/ --include="*.ts" --include="*.tsx" -l
# Expected: no results

# 2. Verify GPR is NOT in the delete list (pg_cron calls Vercel per migration 029)
cat supabase/migrations/20260328000029_gpr_vercel_fallback.sql | head -8
# Expected: confirms "ONE approved Vercel cron exception"

# 3. Verify vercel.json has no cron config
cat vercel.json
# Expected: {}
```

**If ANY pre-check fails:** STOP. Re-audit before proceeding.

**Routes to DELETE (7 — NOT 8, GPR stays):**

| Directory | Reason |
|-----------|--------|
| `app/api/cron/mes-hourly/` | Edge Function at `supabase/functions/mes-hourly/` — pg_cron calls Edge |
| `app/api/cron/fred/` | Edge Function at `supabase/functions/fred/` — pg_cron calls Edge |
| `app/api/cron/massive/` | Edge Functions for both inflation paths — pg_cron calls Edge |
| `app/api/cron/trump-effect/` | Edge Function at `supabase/functions/trump-effect/` — pg_cron calls Edge |
| `app/api/cron/forecast/` | Self-disabled: returns `legacy_forecast_path_removed` |
| `app/api/cron/measured-moves/` | Self-disabled: returns `retired_canonical_writer_detect_setups` |
| `app/api/cron/mes-catchup/` | Self-disabled: returns `legacy_route_disabled_use_mes_1m` |

**Routes to KEEP (3):**

| Directory | Reason |
|-----------|--------|
| `app/api/cron/detect-setups/` | Active core logic, no Edge Function equivalent |
| `app/api/cron/score-trades/` | Active core logic, no Edge Function equivalent |
| `app/api/cron/gpr/` | **pg_cron calls this Vercel route** (migration 029). XLSX memory exceeds Edge runtime. |

**Step 1: Delete**

```bash
rm -rf app/api/cron/mes-hourly
rm -rf app/api/cron/fred
rm -rf app/api/cron/massive
rm -rf app/api/cron/trump-effect
rm -rf app/api/cron/forecast
rm -rf app/api/cron/measured-moves
rm -rf app/api/cron/mes-catchup
```

**Step 2: Verify remaining routes**

```bash
ls app/api/cron/
# Expected: detect-setups/ gpr/ score-trades/
```

**Step 3: Verify**

```bash
npm run build  # MUST pass
npm run lint   # MUST pass (no new issues from deletion)
```

**Step 4: Commit**

```bash
git add -A app/api/cron/
git commit -m "chore: delete 7 duplicate/retired App Router cron routes — Edge Functions are canonical

GPR route kept: pg_cron calls Vercel per migration 029 (XLSX memory exceeds Edge runtime)."
```

### CHECKPOINT 2

Before proceeding to Phase 3:
- [ ] `npm run lint` exits 0
- [ ] `npm run build` exits 0
- [ ] `ls app/api/cron/` shows exactly: `detect-setups/`, `gpr/`, `score-trades/`
- [ ] Marketing page copy matches active plan terminology
- [ ] Use `superpowers:requesting-code-review` on the cumulative diff

---

## Phase 3: Hardening (P2)

**Gate:** Auth forms pass accessibility checks, README matches running code, news_signals has explicit access control.

### Task 3.1: Auth form accessibility

**Files:**
- Modify: `components/login-form.tsx`
- Modify: `components/sign-up-form.tsx`

**Pre-edit verification:** Confirm `components/ui/input.tsx` spreads `{...props}` onto `<input>` (it does — verified).

**Step 1: Fix login-form.tsx**

Email input (line 64-71) — add `name` and `autoComplete`:
```tsx
<Input
  id="email"
  name="email"
  type="email"
  autoComplete="email"
  placeholder="m@example.com"
  required
  value={email}
  onChange={(e) => setEmail(e.target.value)}
/>
```

Password input (line 83-89) — add `name` and `autoComplete`:
```tsx
<Input
  id="password"
  name="password"
  type="password"
  autoComplete="current-password"
  required
  value={password}
  onChange={(e) => setPassword(e.target.value)}
/>
```

Error display (line 91) — add accessibility:
```tsx
{error && <p className="text-sm text-red-500" role="alert" aria-live="polite">{error}</p>}
```

Loading text (line 93) — fix ellipsis:
```tsx
{isLoading ? "Logging in\u2026" : "Login"}
```

**Step 2: Fix sign-up-form.tsx**

Email input (line 71-78) — add `name="email"` and `autoComplete="email"`.

Password input (line 84-90) — add `name="password"` and `autoComplete="new-password"`.

Repeat password input (line 96-102) — add `name="repeat-password"` and `autoComplete="new-password"`.

Error display (line 104):
```tsx
{error && <p className="text-sm text-red-500" role="alert" aria-live="polite">{error}</p>}
```

Loading text (line 106):
```tsx
{isLoading ? "Creating an account\u2026" : "Sign up"}
```

**Step 3: Verify**

```bash
npm run build  # MUST pass
npm run lint   # MUST pass
```

**Step 4: Commit**

```bash
git add components/login-form.tsx components/sign-up-form.tsx
git commit -m "fix: add name, autocomplete, aria-live to auth forms"
```

### Task 3.2: Align README to current contract

**Files:**
- Modify: `README.md`

**Step 1: Fix architecture section (lines 23-27)**

Replace:
```markdown
- Daily bias: macro directional shadow
- 4H structure: confirms or denies trend
- 1H core forecaster: the only ML model in v1
- 1H fib geometry: the only fib-anchor timeframe
- 15M trigger: rule-based entry confirmation against 1H context
```
With:
```markdown
- Daily bias: macro directional shadow
- 4H structure: confirms or denies trend
- 15m fib-outcome engine: TP1_ONLY / TP2_HIT / STOPPED / REVERSAL / NO_TRADE classification
- 15m fib geometry: multi-period confluence with 5-window family (8/13/21/34/55)
- 15m trigger: oscillator extremes at fib zones with mechanical stop-loss (SL = -0.236 fib extension)
```

**Step 2: Fix env var name (line 81)**

Change `NEXT_PUBLIC_SUPABASE_ANON_KEY` to `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`.

**Step 3: Remove retired env vars (lines 86-87)**

Delete:
```
WARBIRD_FORECAST_WRITER_URL
WARBIRD_FORECAST_WRITER_TOKEN
```

**Step 4: Clean optional tuning section (lines 93-94)**

Delete:
```
WARBIRD_MAX_FORECAST_AGE_MS
WARBIRD_FORECAST_WRITER_TIMEOUT_MS
```

**Step 5: Verify and commit**

```bash
npm run build
git add README.md
git commit -m "docs: align README to 15m contract, fix env var names, remove retired vars"
```

### Task 3.3: Add news_signals materialized view access grant

**Files:**
- Create: `supabase/migrations/20260329000034_news_signals_access_grant.sql`

**Pre-edit verification:** Confirm no app code queries `news_signals` with the `anon` role. Grep found zero hits in `app/`, `components/`, `lib/`. The view is refreshed by a `security definer` function and queried only by authenticated dashboard users (when future dashboard work wires it in).

**Step 1: Create migration**

```sql
-- Restrict news_signals materialized view to authenticated users only.
-- Migration 028 dropped the RLS-protected news_signals table and recreated
-- it as a materialized view. Materialized views cannot have RLS in Postgres,
-- so we use GRANT to restrict SELECT access explicitly.
--
-- Source tables (econ_news_article_assessments, geopolitical_risk_1d,
-- trump_effect_1d) retain their own RLS policies. This GRANT adds an
-- explicit boundary on the aggregated view itself.
revoke all on news_signals from anon, public;
grant select on news_signals to authenticated;
grant select on news_signals to service_role;
```

**Step 2: Verify and commit**

```bash
npm run build
git add supabase/migrations/20260329000034_news_signals_access_grant.sql
git commit -m "fix: restrict news_signals materialized view to authenticated role"
```

### CHECKPOINT 3

Before proceeding to Phase 4:
- [ ] `npm run lint` exits 0
- [ ] `npm run build` exits 0
- [ ] Auth forms have `name`, `autoComplete`, `role="alert"`, `aria-live="polite"`
- [ ] README env vars match actual code usage
- [ ] news_signals migration restricts `anon` access

---

## Phase 4: Final Verification

**Gate:** All gates green. No regressions. Cumulative diff reviewed.

### Task 4.1: Run all gates

```bash
npm run lint   # 0 errors, 0 warnings
npm run build  # clean build
```

### Task 4.2: Verify cron route inventory

```bash
ls app/api/cron/
# Expected EXACTLY: detect-setups/ gpr/ score-trades/
```

### Task 4.3: Spot-check marketing copy

Read `app/page.tsx` and verify:
- No references to "1H", "forecaster", "forecasting", "ML-powered", "ML-driven"
- Stats are verifiable (15m, 5, 24/5)
- No raw `<img>` tags
- No `transition-all`

### Task 4.4: Code review

Use `superpowers:requesting-code-review` on the full diff from this plan's work:

```bash
git diff HEAD~N  # where N = number of commits from this plan
```

Review criteria:
- No quant logic altered beyond `let` → `const` and underscore prefixes
- GPR route preserved
- Marketing copy uses spec terminology
- No accidental deletions

### Task 4.5: Update CLAUDE.md current status

Update the "What Works" and "What Doesn't Work Yet" sections to reflect:
- ESLint gate now passes (`npm run lint` is a real gate again)
- Duplicate cron routes deleted (list remaining: detect-setups, gpr, score-trades)
- GPR exception documented
- `news_signals` access boundary restored via GRANT
- Auth forms have proper accessibility attributes
- `eslint.config.mjs` uses native flat config (no more `FlatCompat` bridge)

---

## Deferred Items (NOT in this plan)

### P3: Dashboard waterfall optimization

The dashboard makes 3 separate client-side fetches after auth:
1. `/api/warbird/dashboard?days=7&limit=100` (60s poll)
2. `/api/live/mes15m/summary` (60s poll)
3. `/api/pivots/mes` (one-time)

Fix: combine initial data load into server component after auth, use client subscriptions for deltas only. Separate plan — larger blast radius.

### P3: Edge Function for GPR

The GPR route is the ONE approved Vercel cron exception because `npm:xlsx` exceeds Deno Edge runtime memory (~150MB). Future fix: find a CSV alternative or use a lighter XLS parser. Tracked in migration 029 comments.

### P3: detect-setups and score-trades trigger mechanism

These two routes have no Edge Function equivalent and their trigger mechanism is unclear (not visible in pg_cron migrations). Need to audit Supabase dashboard for manually-created cron jobs before any migration.

---

## Execution Order

```
Phase 1: Unblock Lint Gate
  Task 1.1  Fix 8 ESLint issues
  Task 1.2  Verify lint gate
  Task 1.3  Commit
  ── CHECKPOINT 1 (code review) ──

Phase 2: Contract Alignment
  Task 2.1  Align marketing page
  Task 2.2  Delete 7 cron routes (GPR STAYS)
  ── CHECKPOINT 2 (code review) ──

Phase 3: Hardening
  Task 3.1  Auth form accessibility
  Task 3.2  Align README
  Task 3.3  news_signals access grant
  ── CHECKPOINT 3 ──

Phase 4: Final Verification
  Task 4.1  All gates
  Task 4.2  Cron inventory
  Task 4.3  Marketing spot-check
  Task 4.4  Full code review
  Task 4.5  Update CLAUDE.md
```

# Warbird Strategy 5m — Verification Ledger

> **Purpose:** Replace the audit doc's top-down spec with bottom-up verified facts. Each row is one assumption that must be ground-truthed before a plan section depending on it can be written. **No plan content gets written outside this ledger until the verifications it depends on land VERIFIED.**

**Process:**
1. Each row defines an assumption + a one-step verification + what plan section(s) it blocks.
2. Verifications are sequenced by what other verifications depend on them.
3. Each verification has a `STATUS`: `UNVERIFIED`, `VERIFYING` (Kirk-or-Claude actively running it), `VERIFIED`, or `FAILED`.
4. **No verification runs without explicit Kirk GO**, except for read-only repo inspection done by Claude when asked.
5. When a verification lands `FAILED`, dependent rows are paused; the plan section that depended on it is rewritten or scoped out.

**Kirk's interaction pattern per row:**
- Claude proposes the verification step (what to run, where, expected output).
- Kirk says `GO V<n>` to approve, or revises the step.
- Either Kirk runs the experiment (when it requires TV / chart / hands), or Claude runs it (when it's repo / file inspection) with explicit GO.
- Claude reports result + updates STATUS.
- Kirk reads result, marks `APPROVED` (move to next verification) or pushes back.

**Document discipline:**
- Add rows in priority batches of ≤3.
- Do not write ahead.
- Do not edit landed rows except to update STATUS.
- The audit doc at `docs/runbooks/wb_strat_5m_simple_phaseA_preflight.md` is **parked** as reference; do not pull design from it before its underlying assumptions are verified here.

---

## V1 — TV chart-export CSV mechanism for hidden plots

**Assumption (drawn from the existing Nexus parquet manifest's `notes` field):** TradingView's "Export chart data" CSV will include the value of an indicator plot if and only if that plot is currently rendered visible (`display=display.all` rather than `display=display.none`) in the loaded Pine code. To capture `nexus_*` columns, an operator must temporarily edit the Nexus pine file to flip the relevant `plot(..., display=display.none)` calls to `display=display.all`, save & reload, then export, then revert.

**Why it matters:** The CSV Kirk attached today (`CME_MINI_MES1!, 5_1ce7e.csv`) had only `time, open, high, low, close` — no volume, no nexus_*. That's consistent with a baseline export of a chart that didn't have the Nexus indicator visibly emitting those plots, but it's also consistent with the procedure not working as I assume. If the procedure doesn't work, footprint capture for the strategy 5m profile is impossible without a different export path, and Stage 4 of the prior plan is invalid.

**Verification step (Kirk-run, ~10 minutes):**
1. Open `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` in TradingView Pine Editor.
2. Save a backup copy of the file outside the repo (paranoia — Claude will not touch it).
3. Edit lines 745–757 (the `plot(..., display=display.none, ...)` block emitting `nexus_fp_available`, `nexus_fp_bar_delta`, `nexus_fp_total_volume`, `nexus_norm_cum_delta`, `nexus_delta_slope`, `nexus_bar_delta_ratio`, `nexus_delta_dir`, `nexus_gasout_bull`, `nexus_gasout_bear`, `nexus_mode_minutes`, `nexus_signal_tier`). Change every `display = display.none` on those lines to `display = display.all`.
4. Save → Add to Chart on MES1! 5m. Confirm chart re-renders (Nexus values now appear as separate plots; chart looks ugly, that's fine).
5. **TradingView menu → File → Export Chart Data** (NOT "Export Strategy Tester"). In the dialog, select the Nexus indicator and confirm UTC timestamps.
6. Save the CSV. Drop the path here as a reply.
7. Revert the Nexus pine file to original (`display = display.none` on those lines). Save again. Confirm chart re-renders cleanly.

**Acceptance check Claude will run when CSV path lands:**
- Inspect CSV header. PASS if at minimum these columns are present: `time, open, high, low, close, volume, nexus_fp_available, nexus_fp_bar_delta, nexus_fp_total_volume, nexus_signal_tier`. FAIL if any of those four `nexus_*` columns are missing.
- Read first 5 rows to confirm timestamp format and verify `nexus_fp_available` is 1 on at least some bars (proves footprint resolved at all).

**Blocks:** V2 (footprint history depth — depends on knowing capture works), V3 (CSV format inspection — depends on having a real CSV to inspect), and every plan section that references footprint capture.

**STATUS:** `VERIFYING` — Kirk authorized 2026-04-28. Awaiting CSV path from Step 6 of the procedure.

**Notes / open questions raised by this verification:**
- If Step 5 produces a CSV that includes `nexus_*` columns but timestamps are local-tz instead of UTC, that's a partial pass — flagged for V3.
- If TV's "Export Chart Data" dialog requires a paid plan tier or has row-count limits, surface that immediately; we'll need an alternative.
- If TV silently truncates the chart range to a recent window when exporting, that gets caught by V2 (history depth) but record it here too.

---

## V2 — Actual footprint history depth on Kirk's TV chart

**Assumption (challenged by today's session):** TV `request.footprint()` data is available going back ~12 months (the IS window I had proposed). The existing Nexus capture covers only 2026-01-11 onward, but I attributed that to the capture session's chart range rather than to a TV storage limit.

**Why it matters:** This sets the IS window length. If footprint truly only covers 3.5 months, the audit doc's "IS = 2025-04-28 → 2026-04-01" is wrong by 7+ months and the trial budget / min-trades floor / yearly_consistency-out call all need re-evaluation.

**Verification step (depends on V1 passing — Kirk-run, ~5 minutes):**
1. With V1's CSV in hand, scan from oldest row forward.
2. Find the first row where `nexus_fp_available == 1`. Record that timestamp.
3. Find the last row where `nexus_fp_available == 1` before any gap of more than 2 hours. Record that timestamp.
4. Report:
   - First-bar-with-footprint timestamp
   - Last-bar-with-footprint timestamp
   - Total contiguous-with-footprint duration (days)
   - Any internal gaps (regions where `nexus_fp_available == 0` between two regions where it's 1)

**Acceptance check Claude will run:**
- Print the histogram of `nexus_fp_available` values per calendar day.
- Compute IS-window-feasible range as `[first_bar_with_fp, last_bar_with_fp − 7d_embargo − 21d_OOS]`.
- Note: If actual feasible IS is < 90 days, surface that the trial budget should drop from 1000 (overfit risk on tiny windows).

**Blocks:** All references to the IS window in any future plan (currently §7 of the parked audit doc), the trial budget decision, and the min-trades floor.

**STATUS:** `UNVERIFIED` (depends on V1)

**Notes:**
- The existing Nexus parquet's `usable_footprint_rows = 20002 / 20765` ratio means 96.3% of bars had footprint in that capture. We'll get a similar ratio for the new capture, but the date range is what matters.
- If V2 reveals footprint depth is shorter than expected, it does NOT mean the project is dead — it means the IS window narrows and we re-evaluate trial budget, scoring, and Phase B feasibility.

---

## V3 — TV CSV column schema and timestamp encoding

**Assumption:** TV "Export Chart Data" CSV produces UTC bar-OPEN timestamps as Unix epoch seconds (consistent with Kirk's earlier-attached `CME_MINI_MES1!, 5_1ce7e.csv` which had `time` column with values like `1775128200`). Other column names (open, high, low, close, then indicator plots) are emitted as-is from Pine plot titles.

**Why it matters:** The strategy 5m profile's `load_data()` joins the footprint CSV (now parquet) against `data/mes_5m.parquet`. Databento timestamps in the parquet are bar-OPEN UTC. If TV uses bar-CLOSE timestamps or local-tz timestamps, the join silently drops rows or merges wrong bars. This is exactly the kind of silent-correctness bug that ruins parity tests downstream.

**Verification step (Claude-run, depends on V1 passing — read-only):**
1. Read the V1 CSV header line.
2. Read first 10 data rows.
3. Compare timestamps against `data/mes_5m.parquet` rows in the same calendar minute window using:
   ```python
   import pandas as pd
   csv = pd.read_csv("<V1 CSV path>")
   parquet = pd.read_parquet("data/mes_5m.parquet")
   # Convert TV time (Unix seconds) to UTC datetime
   csv["ts_utc"] = pd.to_datetime(csv["time"], unit="s", utc=True)
   # Find the row in parquet with matching timestamp
   for csv_row in csv.head(10).itertuples():
       parquet_match = parquet[parquet["ts"] == csv_row.ts_utc]
       print(csv_row.ts_utc, csv_row.open, "vs parquet:", parquet_match[["open","high","low","close"]].head(1).to_dict("records"))
   ```
4. PASS if at least 9 of 10 head rows align timestamp-for-timestamp AND open prices match within 0.25 (one MES tick). FAIL if timestamps don't align or prices differ systematically.

**Acceptance check:**
- Side-by-side first 5 rows table: TV CSV timestamp + OHLC vs. Databento parquet timestamp + OHLC.
- Any time-zone or bar-edge offset discovered must be documented for the eventual `load_data()` join logic.

**Blocks:** Any future plan section that defines `load_data()`, the parity test (Stage 4 task 4 of parked audit), and the OOS validation step.

**STATUS:** `UNVERIFIED` (depends on V1)

**Notes:**
- If timestamps DO mismatch, the fix is a known offset (e.g., +0s vs +300s for bar-close). It's not a project-killer, but it MUST be characterized before any join code is written. A 1-bar offset is enough to invalidate all parity tests.
- Databento OHLC values may differ slightly from TV's chart values due to roll/contract handling (MES1! vs continuous). If V3 reveals systematic OHLC delta, that's a separate finding — flagged for a future verification row.

---

## Pending future rows (priorities)

These will be added in batches of ≤3 only AFTER the relevant prior verifications land VERIFIED. Drafted here as a heads-up for Kirk; rows below this line are NOT yet active.

- V4 — `request.footprint()` plan-tier / rate-limit / row-count constraints on TV
- V5 — `runner.py` interface compatibility with a strategy-style profile (it currently serves indicator-style profiles)
- V6 — Pine v6 syntax validation of the proposed `simpleLadderReclaim` helper (compile-only test; no chart needed)
- V7 — Bar Magnifier + `process_orders_on_close=false` semantics — what does Python re-sim need to mimic
- V8 — All 40 `ml_*` plot expression chains — full enumeration of which depend on §2.2 deletion list
- V9 — `check-indicator-strategy-parity.sh` actual scope (names? defaults? counts?)
- V10 — Existing `study.db` deletion dance while optuna-dashboard at port 8101 holds the file
- V11 — `--n-jobs 2` SQLite WAL mode for `study.db`
- V12 — Strategy `commission_type=cash_per_contract` + `slippage=1` exact application semantics
- V13 — TV strategy export trades CSV column inventory and one-trade-per-row vs entry+exit format
- V14 — Embargo enforcement smoke test (profile must refuse a trade at `ts >= EMBARGO_START`)
- V15 — `optuna_dashboard` study card user_attrs that runner.py writes (so port 8101 renders complete)
- V16 — `_simulate_outcome` from institutional profile — single-bracket adaptation viability
- V17 — Min-trades floor calibration once V2 lands

---

## Sign-off pattern

When Kirk has reviewed this header + V1/V2/V3 above, reply:

```
GO V1
[any V1/V2/V3 step revisions]
```

Or:

```
REVISE LEDGER
[changes wanted to format, priorities, or row content]
```

Claude will not advance to V4–V17 without an explicit `EXPAND LEDGER` from Kirk after V3 lands.

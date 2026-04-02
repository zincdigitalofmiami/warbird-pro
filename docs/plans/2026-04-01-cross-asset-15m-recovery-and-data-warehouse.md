# Cross-Asset 15m Recovery & Data Warehouse Consolidation Plan

**Created:** 2026-04-01
**Status:** DRAFT — pending user approval
**Scope:** Recover lost cross_asset_15m data, audit and consolidate all cross-asset data sources, establish safe batch download workflow with external drive archive.

---

## Situation

On 2026-04-01, Phase 1 of the local-db-migration plan truncated `cross_asset_15m` from cloud Supabase (175,909 rows). The plan assumed rabid_raccoon was the recovery source. **Raccoon has no 15m cross-asset data** — only `mkt_futures_mes_15m` (MES only), `mkt_futures_1h`, and `mkt_futures_1d`. The 175,909 rows were originally produced by a Databento batch backfill (the live cross-asset cron only writes 1h and 1d, not 15m). The data is not recoverable from raccoon. It must be re-pulled from Databento.

**Root cause:** Plan defect — truncation before verifying copy. QA gatekeeper failed to catch the missing recovery path.

---

## Data Inventory Audit (Current State)

### What exists on the external drive (`/Volumes/Satechi Hub/`)

| Location | Contents | Format | Notes |
|----------|----------|--------|-------|
| `Databento Data Dump/GLBX-20260202-WH33638BK6.zip` | 25 GB batch download — `definition` schema for 20 options parent symbols, 2010-06 → 2026-02 | DBN/zstd, monthly splits | **Options definitions only** — NO OHLCV data |
| `Databento Data Dump/Options/` | Extracted version of above | `.definition.dbn.zst` files | Same — definitions, not price data |
| `Historical Data/Databento/raw/databento_futures_ohlcv_1h.parquet` | **4,967,276 rows**, 84 symbols, 1h OHLCV | Parquet | **Includes NQ/RTY/CL/HG/6E/6J from 2010-06 → 2025-12-15** |
| `Historical Data/Databento/raw/databento_futures_ohlcv_1d.parquet` | **290,174 rows**, 81 symbols, 1d OHLCV | Parquet | Same symbol coverage |
| `Historical Data/Databento/raw/databento_options_ohlcv_1d.parquet` | Options OHLCV 1d | Parquet | Not yet audited |
| `Historical Data/Databento/symbols/` | Symbol-partitioned OHLCV (6B, 6E, 6J, CL, ES, HG, NQ, etc.) | Hive-partitioned dirs | Partial — only some years present |

### What exists in rabid_raccoon (READ-ONLY, DEAD — DO NOT WRITE)

| Table | Rows | Symbols | Range | Quality |
|-------|------|---------|-------|---------|
| `mkt_futures_1h` | 546,453 | 20 symbols incl NQ(36,298) RTY(36,281) CL(36,081) 6E(30,869) 6J(26,988) | 2020-01-01 → 2026-03-05 | ✅ 0 NULL OHLC, 0 h<l, 0 neg vol (verified for 5 basket symbols) |
| `mkt_futures_1d` | 46,443 | NQ(1,923) RTY(1,923) CL(1,919) 6E(1,867) 6J(1,841) | 2020-01-01 → 2026-03-05 | Not yet spot-checked |
| `mkt_futures_mes_15m` | 159,911 | MES only | 2020+ | N/A — not cross-asset |
| `mkt_futures_mes_1m` | 3,660 | MES only | 2026-03-04 → 2026-03-09 | Tiny — only ~5 days |
| `mkt_options_ohlcv_1d` | 27,004 | 15 parent symbols (ES.OPT, NQ.OPT, LO.OPT, etc.) | 2020-01-01 → 2026-02-24 | Aggregated daily — not individual strikes |
| `mkt_options_statistics_1d` | 56 | Unknown | Unknown | Tiny |
| **NO `mkt_futures_15m` table** | — | — | — | **CONFIRMED: raccoon has NO 15m cross-asset data** |

### What exists in local Supabase (training warehouse)

| Table | Rows | Source | Notes |
|-------|------|--------|-------|
| `cross_asset_15m` | 20,553 | Databento backfill (HG only) | **Missing: NQ, RTY, CL, 6E, 6J** |
| `cross_asset_1h` | 178,379 | Raccoon migration | 6 symbols, 2020 → 2026-03 |
| `cross_asset_1d` | 11,098 | Raccoon migration | 6 symbols, 2020 → 2026-03 |

### What exists in cloud Supabase (production)

| Table | Rows | Notes |
|-------|------|-------|
| `cross_asset_15m` | 0 | **TRUNCATED — this is what we're recovering** |
| `cross_asset_1h` | 167,418 | Live, growing from cron |
| `cross_asset_1d` | 15 | Small cron re-accumulation |

---

## Recovery Strategy

### Why Databento batch download (not streaming)

| Factor | Streaming (`get_range`) | Batch (`submit_job`) |
|--------|------------------------|---------------------|
| Duplicate cost | Charged every re-pull | Free re-download for 30 days |
| Disconnection risk | Yes, for large pulls | No — download at your pace |
| Archive copy | None | `.dbn.zst` file on external drive |
| Size suitability | < 5 GB recommended | > 5 GB recommended |

**Source:** [Databento: Streaming vs batch download](https://databento.com/docs/faqs/streaming-vs-batch-download)

### Why `ohlcv-1m` → resample to 15m (not direct `ohlcv-1h` downsample)

- Databento has no `ohlcv-15m` schema. Available: 1s, 1m, 1h, 1d.
- 15m must be constructed from 1m. Cannot upsample 1h → 15m.
- `ohlcv-1m` is free on Standard $179/mo plan.
- **Source:** [Databento: OHLCV schema](https://databento.com/docs/schemas-and-data-formats/ohlcv) — "If you need other sampling intervals, we recommend that you construct OHLCV aggregates from trades data or subsample the OHLCV schema with the nearest resolution on client side."

### Why audit RR data quality first

- RR has 1h and 1d for the basket symbols, 2020-01-01 → 2026-03-05.
- If RR data is clean and complete, no need to re-pull 1h/1d from Databento — only need 1m for 15m construction.
- Initial quality check: **0 NULL OHLC, 0 high<low, 0 negative volume** for NQ/RTY/CL/6E/6J 1h. Promising.
- COVID spot-check: NQ 2020-03-16 low 6927.00, high 7564.00. Reasonable for NQ during crash week.
- **Full quality audit required before deciding** to use or overwrite.

### Resampling requirements (from user review)

Per the user's explicit corrections, the 1m→15m resampling must be:

1. **Session-aware** — cannot bridge CME Globex maintenance windows or weekends
2. **Symbol-partitioned** — each symbol resampled independently
3. **Right-edge labeled** — 15m bar timestamp = bar close time (Warbird canonical key)
4. **Completeness-tracked** — every 15m bar carries:
   - `constituent_1m_count` (how many 1m bars were aggregated)
   - `is_complete` (boolean: did all expected 1m bars exist?)
   - Ideally `session_id` or equivalent session boundary logic
5. **No interpolation in canonical tables** — if a bar is incomplete, mark it, don't fake it
6. **Use Polars** for local research/training surface generation

**Source:** [Databento: OHLCV Resampling Best Practices](https://databento.com/docs/examples/basics-historical/ohlcv-resampling/best-practices) — "Databento only sends an OHLCV record if a trade happens in that interval."

---

## Plan Phases

### Phase 0: RR Data Quality Audit

**Goal:** Determine if RR 1h and 1d data is "perfect" and usable, or if Databento needs to overwrite it.

**Audit checklist for each basket symbol (NQ, RTY, CL, 6E, 6J, HG):**

- [ ] 0 NULLs in OHLCV columns *(DONE for 1h basket-5 — all pass)*
- [ ] 0 rows where high < low *(DONE for 1h basket-5 — all pass)*
- [ ] 0 negative volume *(DONE for 1h basket-5 — all pass)*
- [ ] Date range covers 2020-01-01 → 2026-03-05 *(DONE — confirmed)*
- [ ] No large gaps during trading hours (check for missing weeks/months)
- [ ] Spot-check vs known market events (COVID crash, VIX spike, rate hike cycle)
- [ ] Compare RR 1h counts vs external drive parquet counts for same date range
- [ ] Compare sample values (same symbol, same timestamp) between RR and parquet
- [ ] Verify 1d data quality (same checks)
- [ ] Audit options data: `mkt_options_ohlcv_1d` — 27,004 rows, 15 parent symbols, check schema compatibility

**Decision gate:**
- If all checks pass → use RR 1h/1d as-is in local Supabase, only batch-download 1m for 15m construction
- If ANY check fails for a symbol → batch-download that symbol's full OHLCV from Databento and overwrite

**Checkpoint:** Report audit findings with evidence before proceeding to Phase 1.

### Phase 1: Databento Batch Download

**Goal:** Get `ohlcv-1m` data for all 6 basket symbols, 2020-01-01 → present, as archived `.dbn.zst` files on the external drive.

**Batch job parameters:**
```python
client.batch.submit_job(
    dataset="GLBX.MDP3",
    symbols=["NQ.c.0", "RTY.c.0", "CL.c.0", "HG.c.0", "6E.c.0", "6J.c.0"],
    schema="ohlcv-1m",
    stype_in="continuous",
    start="2020-01-01",
    end="2026-04-02",  # day after today
    encoding="dbn",
    compression="zstd",
    split_duration="month",   # monthly file splits for manageability
    delivery="download",
)
```

**Source:** [Databento: Batch downloads](https://databento.com/docs/faqs/streaming-vs-batch-download) — "Recommended for data requests over 5 GB" and "Download the same data multiple times over a 30 day period, for no additional charge."

**Archive location:** `/Volumes/Satechi Hub/Databento Data Dump/ohlcv-1m-basket-2020/`

**Cost:** $0.00 expected — OHLCV is free on Standard plan. Verify with `client.metadata.get_cost()` before submitting.

**Safety:**
- Estimate cost FIRST — abort if non-zero
- Download to external drive — safe from any agent touching the repo
- Keep the `.dbn.zst` files permanently as the canonical archive

**Checkpoint:** All monthly files downloaded and verified (file count matches expected months, no zero-byte files).

### Phase 2: Resample 1m → 15m (Polars)

**Goal:** Build session-aware, right-edge-labeled 15m bars with completeness tracking.

**Script:** New Python script: `scripts/build-training-15m.py`

**Input:** `.dbn.zst` files from Phase 1 (read via `databento` Python library)
**Output:** Polars DataFrame → upsert to local Supabase `cross_asset_15m`

**Resampling logic (must match Databento documented patterns):**

```
For each symbol:
  1. Load ohlcv-1m from .dbn.zst files → Polars DataFrame
  2. Convert ts_event (nanosecond epoch) → UTC timestamp
  3. Scale prices (÷ 1e9 fixed-point to decimal)
  4. Filter weekend bars (Fri 22:00 UTC → Sun 23:00 UTC)
  5. Filter CME maintenance windows (if detectable from bar gaps)
  6. Group by 15m bucket (floor to 900-second boundary)
  7. Aggregate: first(open), max(high), min(low), last(close), sum(volume)
  8. Count constituent bars per bucket → constituent_1m_count
  9. Mark is_complete = (constituent_1m_count >= expected for that session period)
  10. Label timestamp as RIGHT-EDGE (bucket_start + 15 minutes = bar close)
  11. Upsert to local cross_asset_15m
```

**Source:** [Databento: OHLCV Resampling](https://databento.com/docs/examples/basics-historical/ohlcv-resampling) — official interpolation/resampling example using `groupby.resample.agg({open: first, high: max, low: min, close: last, volume: sum})`.

**Schema note:** The current `cross_asset_15m` schema is (ts, symbol_code, open, high, low, close, volume, created_at). The `constituent_1m_count` and `is_complete` fields do NOT exist yet. Options:
- (a) Add columns via migration
- (b) Store completeness metadata in a separate local-only table
- (c) Compute on read (count can be derived if 1m data is retained)

**Decision needed from user.**

**Also upsert to 1h and 1d?** Per Phase 0 results:
- If RR data passed audit → skip 1h/1d writes (already loaded from RR)
- If RR data failed audit → also aggregate 1m → 1h and 1m → 1d, overwrite local tables

**Checkpoint:**
- Row counts per symbol match expected (175,909 / 6 ≈ 29K per symbol, but will vary)
- Date range: 2020-01-01 → 2026-04-01 for all 6 symbols
- Spot-check: COVID crash, rate hike values match RR / known truth
- Zero NULL OHLCV, zero high < low
- Completeness: report % of 15m bars that are `is_complete = true`

### Phase 3: Options Data Migration

**Goal:** Pull options data from RR into local Supabase for future use.

**Source:** `mkt_options_ohlcv_1d` — 27,004 rows, 15 parent symbols (ES.OPT, NQ.OPT, LO.OPT, OG.OPT, etc.), 2020-01-01 → 2026-02-24.

**Target:** Need to determine. Options:
- (a) Create new local table `options_ohlcv_1d` (would need migration for local Supabase)
- (b) Load into existing table if one exists

**Quality audit required:**
- [ ] Check for NULLs
- [ ] Check date continuity
- [ ] Verify schema compatibility with local Supabase types
- [ ] Also check `mkt_options_statistics_1d` (56 rows — might not be worth it)

**Decision needed from user:** Table naming, schema, whether to also pull the 25GB options definitions from the batch download.

**Checkpoint:** Options data loaded, verified, counts match.

### Phase 4: Final Verification

**Goal:** Full data warehouse integrity check.

Using the QA Gatekeeper skill:
- [ ] All 6 symbols present in `cross_asset_15m` with 2020+ data
- [ ] No duplicates
- [ ] No NULLs in critical columns
- [ ] Date ranges complete
- [ ] Spot-checks against ground truth (COVID, rate hikes)
- [ ] Gap analysis: no active symbols with zero data
- [ ] Compare local totals vs source data (RR row counts, batch file record counts)
- [ ] Verify external drive archive is intact (file checksums or counts)

**Checkpoint:** Phase 4 verdict delivered per QA Gatekeeper skill protocol.

---

## Safety Rules

1. **NEVER truncate or delete data before verifying a copy exists**
2. **External drive archive is the ground truth** — `.dbn.zst` files persist on `/Volumes/Satechi Hub/Databento Data Dump/`
3. **Raccoon is READ-ONLY, DEAD** — only used as audit reference, never written to, never imported from into cloud
4. **Cloud Supabase is NOT touched** — all work targets local Supabase only
5. **Batch download first, process second** — raw data archived before any transformation
6. **Cost estimation before every Databento API call**

---

## Open Questions

1. **Completeness columns**: Add `constituent_1m_count` and `is_complete` to `cross_asset_15m` schema via migration, or store separately?
2. **Right-edge labeling**: The current HG data in `cross_asset_15m` uses LEFT-edge timestamps (bar start, matching Databento's `ts_event`). Switching to right-edge for the recovery would create inconsistency with HG. Should we re-process HG too?
3. **Options table**: What table name and schema for local options data?
4. **25GB options definitions batch**: The existing `GLBX-20260202-WH33638BK6.zip` contains instrument `definition` schema for 20 options parent symbols. Is this needed for anything, or just the OHLCV data from RR?
5. **1h/1d overwrite decision**: Pending Phase 0 RR audit results. If RR passes, keep as-is. If not, what's the threshold for "imperfect"?

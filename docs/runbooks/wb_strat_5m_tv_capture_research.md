# TV Chart Data Export — Research Note

> **Purpose:** Ground-truth the canonical procedure for capturing per-bar Pine plot values (specifically `nexus_*` plots from the Nexus indicator) into a CSV that becomes the footprint parquet. Triggered by V1's first-attempt FAILURE: Kirk's CSV had only OHLC + strategy's visible plots, no `nexus_*` columns. This note replaces my earlier inference-from-one-manifest with verified facts from official TradingView documentation.

**Status:** Research complete pending Kirk's review. Ledger NOT yet updated.

---

## §1 What I had wrong in the original V1 procedure

My V1 procedure said:
> "Edit lines 745–757 of the Nexus pine file. Change every `display = display.none` on those lines to `display = display.all`."

This was based on inference from the Nexus parquet manifest's one-line `notes` field: *"Converted from TradingView chart export containing nexus_fp_* columns after temporary display enablement for footprint export."*

**Two errors in that procedure:**

1. **Wrong `display` target.** Per TradingView's official Pine Script v6 FAQ on indicators: *"Plots with `display=display.none` will not appear in the exported CSV. However, you can work around this using `display=display.data_window` instead, which hides the plot from the chart visually while still including it in the export data."* The correct target is `display.data_window` — NOT `display.all`. Using `display.all` would have included the plots, but would have visually polluted the chart with extra panes/traces during the capture session.

2. **Missing the actual-likely-cause.** Kirk's CSV had `EMA 9, EMA 21, EMA 50, VWAP, VF Base` columns — those are plots from the **strategy**, not the Nexus indicator. The most likely root cause of V1's first-attempt FAILURE is one of:
   - The Nexus indicator was not loaded on the chart at the time of export.
   - The Nexus indicator was loaded but the export dialog "tab" selection picked only the chart/strategy, not Nexus. TV's "Download chart data" dialog presents data sources as tabs (chart symbol, each indicator). Each tab is downloaded separately.

---

## §2 Verified facts from official TradingView documentation

Sources used (cited in §6):

| Source | What it confirmed |
|---|---|
| TV Pine Script v6 FAQ — Indicators | `display.none` plots are NOT in CSV; `display.data_window` plots ARE in CSV |
| TV Pine Script v6 docs — Visuals/Plots | The `display` parameter controls "the locations where plot values appear, which include the script pane, status line, price scale, and Data Window. The default is `display.all`." |
| TV Pine Script v6 docs — Volume Footprints blog | `request.footprint()` requires **Premium or Ultimate** plan |
| TV Support — How can I export chart data | Menu path is *"Download chart data…"* in the dropdown menu on the upper toolbar; *"select the chart and click Download."* Plan tier: Pro+ or Premium. Export is *"limited to currently visible chart data"* — to get more history, scroll left first. |

### §2.1 The `display` parameter values that matter

| Value | Chart pane | Status line | Price scale | Data Window | CSV export |
|---|---|---|---|---|---|
| `display.all` (default) | ✓ | ✓ | ✓ | ✓ | ✓ |
| `display.none` | ✗ | ✗ | ✗ | ✗ | **✗ (NOT exported)** |
| `display.data_window` | ✗ | ✗ | ✗ | **✓** | **✓ (exported)** |
| `display.pane` | ✓ | ✗ | ✗ | ✗ | (likely yes — visible) |
| `display.status_line` | ✗ | ✓ | ✗ | ✗ | (likely yes) |
| `display.price_scale` | ✗ | ✗ | ✓ | ✗ | (likely yes) |
| Combinations like `display.status_line + display.data_window` | (per combination) | ✓ | ✗ | ✓ | ✓ |

**Implication for the Nexus capture:** the cleanest target is `display.data_window`. The chart stays visually unchanged (no extra panes or watermark drift), and the plot values appear in the CSV.

### §2.2 Plan tier and footprint history

- Kirk's plan: **TradingView Ultimate** (per memory `reference_tradingview_ultimate.md`, $239/month). This satisfies the `request.footprint()` Premium/Ultimate requirement AND the Pro+ CSV export requirement.
- `request.footprint()` history: returns `na` for bars where TV does not have footprint data. The existing Nexus parquet manifest shows TV footprint resolved from 2026-01-11 onward (at the time of that capture session). This is the data limit, not the procedure limit. **The V2 verification on history depth still stands.**
- Export window: limited to currently visible chart data. To capture a wider date range, the chart must be scrolled or set to a wider visible range BEFORE clicking export.

### §2.3 The "Download chart data" dialog

Per TV support docs: *"Information from each tab is exported individually. If you click on the export button, the information will be downloaded from the selected tab in the dropdown list."*

This means the dialog presents one "tab" per data source on the chart:
- Chart symbol tab — exports OHLCV + chart-overlay plots from indicators with `display.all` plots on the main pane (e.g., the strategy's EMA/VWAP).
- Each indicator tab — exports that indicator's plot values (visible OR hidden, per §2.1).

To get `nexus_*` columns, **the Nexus indicator's tab must be selected and downloaded separately.** It is not bundled with the chart symbol tab.

This explains Kirk's first-attempt CSV exactly: he downloaded the chart symbol tab. He did not download (or the procedure didn't expose) the Nexus indicator tab.

---

## §3 Corrected V1 procedure (proposed — for Kirk's review)

This is what V1 should have said. **I am NOT updating the ledger until Kirk approves this rewrite.**

### Pre-procedure checklist (Kirk-side, no Claude touches)

- TradingView Desktop running with the chart on **MES1! 5m** and the Nexus indicator (`Nexus ML Fast`) loaded on the chart. Strategy can also be loaded; doesn't matter for capture.
- Chart visible date range covers the IS window we want to capture (V2's open question — see V2 below).
- TV plan: Ultimate (verified via memory; Kirk to confirm if changed).

### Procedure

1. **Backup the Nexus pine file outside the repo** (paranoia — Claude will not touch it):
   ```
   cp "indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine" \
      ~/nexus-backup-2026-04-28.pine
   ```

2. **Edit Nexus pine — flip `display.none` → `display.data_window`** on lines 745–757 (the plots emitting `nexus_fp_available`, `nexus_fp_bar_delta`, `nexus_fp_total_volume`, `nexus_norm_cum_delta`, `nexus_delta_slope`, `nexus_bar_delta_ratio`, `nexus_delta_dir`, `nexus_gasout_bull`, `nexus_gasout_bear`, `nexus_mode_minutes`, `nexus_signal_tier`).

   **Why `display.data_window` and NOT `display.all`:**
   - `display.data_window` keeps the chart visually clean (no extra panes, no column-header watermark on the chart).
   - Both options export to CSV per §2.1.
   - `display.all` would clutter the chart and may shift indicator pane scales during the capture session.

3. **Save the Pine Editor** → indicator on chart re-renders. Visual chart should look identical to before (because data_window plots don't appear on chart). The indicator's Data Window should now show all the previously-hidden values when you hover over a bar — this is your verification that the flip took effect.

4. **TradingView upper toolbar → ⋮ (More) menu → Download chart data…** (or "Export chart data…" depending on TV UI version).

5. **In the dialog: select the Nexus indicator tab.** Critical step. The dialog presents one tab per data source. Selecting the chart symbol gives OHLCV + visible chart-overlay plots; selecting the Nexus tab gives Nexus's plot values (including the now-data_window-flipped plots). Click Download.

6. **Repeat for the chart symbol tab** if you want OHLCV in the same export run — or skip and use `data/mes_5m.parquet` for OHLCV, joining on `ts`.

7. **Save the CSV.** Paste the path here as your reply.

8. **Revert the Nexus pine file** — change `display = display.data_window` back to `display = display.none` on those same lines. Save.

### Acceptance check (Claude-run when CSV path lands)

- Inspect CSV header. PASS if these columns are present: `time, nexus_fp_available, nexus_fp_bar_delta, nexus_fp_total_volume, nexus_signal_tier`. (OHLCV may or may not be in this CSV — depends on which tab Kirk selected. If only Nexus tab was selected, OHLCV will come from the parquet join. That's fine.)
- Read first 5 data rows.
- Verify timestamp format and that `nexus_fp_available` is 1 on at least some bars.
- Update V1 STATUS to `VERIFIED` (or `FAILED` with specific findings).

---

## §4 Open uncertainties this research did NOT resolve

These should become future ledger rows, NOT folded into V1:

| ID | Uncertainty | Why it matters |
|---|---|---|
| U1 | TV UI menu name varies: "Export chart data…" vs "Download chart data…" depending on TV version. May also be hidden under a ⋮ menu vs a top-bar button. Kirk to confirm what HIS TV shows. | Procedure step 4 |
| U2 | The dialog's exact appearance and whether it's a tab UI vs a checkbox UI vs a single-select dropdown. The TV docs use the word "tab" but third-party tutorials describe checkboxes. | Procedure step 5 |
| U3 | Whether TV exports honor ALL bars currently in the chart's data buffer, or only bars currently visible in the viewport. Docs say "what your chart shows you" — ambiguous. | Determines whether scrolling/zooming is enough or whether the chart must be in Replay mode loaded back to a specific date. Tied to V2. |
| U4 | Whether `display.data_window` plots that return `na` are exported as empty cells, "NaN" string, or omitted from rows. Affects parquet load logic. | Parquet join semantics |
| U5 | Whether the CSV download dialog has a date-range selector or just downloads "everything currently on chart." | Tied to V2 footprint history depth |

These are DOCUMENTED here for tracking. They will be added as ledger rows V4–V7 (or similar) only after Kirk approves the V1 rewrite and we have empirical evidence from a successful V1 run that informs them.

---

## §5 Decision points for Kirk before V1 re-runs

Three things I need explicit GO on before touching the ledger:

1. **Approve the corrected V1 procedure in §3.** Specifically the `display.none → display.data_window` flip (NOT `display.all`) and the dialog tab-selection step.

2. **Approve writing the corrected procedure into the ledger.** I will replace the old V1 row content with the corrected version, mark the prior attempt as `FAILED → re-scoped` in V1's notes section (preserve the historical fail finding for future learning).

3. **Confirm one detail I need from you before re-running:** What does YOUR TV show when you click the upper-toolbar dropdown menu? Specifically:
   - Is the menu item called "Export chart data…" or "Download chart data…"?
   - When you click it, does a dialog open with tabs / a list of indicators? Describe what you see.
   - This grounds the procedure in your specific TV UI rather than guessing from docs.

If you give me what you see in the dialog (a screenshot or text description), I can write a procedure that uses your exact UI labels rather than the generic doc terms.

---

## §6 Sources

Documentation pages consulted:

- [How can I export chart data? — TradingView Support](https://www.tradingview.com/support/solutions/43000537255-how-can-i-export-chart-data/)
- [Pine Script v6 docs — Visuals / Plots](https://www.tradingview.com/pine-script-docs/visuals/plots/)
- [Pine Script v6 FAQ — Indicators](https://www.tradingview.com/pine-script-docs/faq/indicators/)
- [Volume footprints are now available in Pine scripts — TradingView Blog](https://www.tradingview.com/blog/en/volume-footprints-in-pine-scripts-56908/)
- [You can now export & download data into a CSV file — TradingView Blog](https://www.tradingview.com/blog/en/export-chart-data-in-csv-14395/)
- [How can I export trading data? — TradingView Support](https://www.tradingview.com/support/solutions/43000663814-how-can-i-export-trading-data/)
- TradingView Pine Script Language Reference Manual — referenced but page returned redirect-only content; primary findings came from FAQ and Visuals/Plots pages above.

Empirical evidence inspected:

- `scripts/optuna/workspaces/warbird_nexus_ml_rsi/tv_footprint_5m.manifest.json` — manifest from a prior successful Nexus capture; contains the one-line `notes` field that I had over-interpreted.
- `/Users/zincdigital/Downloads/CME_MINI_MES1!, 5_d8a2c.csv` — Kirk's first V1 attempt; provides the failure-mode evidence that drove this research.
- `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` lines 745–757 — the plot definitions that need to be flipped.
- TV MCP `tv_health_check`, `chart_get_state`, `data_get_study_values` — attempted; CDP not connected to TV right now (Kirk's normal state per memory `feedback_cdp_handshake_unreliable.md`); did NOT call `tv_launch` per memory rule.

---

## §7 What I'm NOT doing until Kirk approves §5

- Not editing the ledger.
- Not touching the Nexus pine file.
- Not running V2 prep (footprint history depth).
- Not calling `tv_launch` to bring CDP up.
- Not drafting V4–V17.
- Not designing Stage 1.

Reply pattern when ready:

```
APPROVE V1 REWRITE
[describe what your TV menu / dialog actually shows]
[any procedure refinements]
```

Or:

```
RESEARCH MORE
[specific gaps]
```

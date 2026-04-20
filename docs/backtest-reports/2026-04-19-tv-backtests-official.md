# Official TV Backtests (Deduped)

Date generated: 2026-04-19

## Scope

- Source folders scanned: `/Users/zincdigital/Downloads` (top-level only), `data/sats_ps_r0/`
- Dedup rule: exact file-content SHA-256 hash; prefer repo copy when duplicate exists, otherwise newest file
- Scope labels: `post_break_2025plus`, `recent_2024plus`, `full_2020plus`, `legacy_pre2020`, `unknown`

## Summary

- Total candidate files parsed: `57`
- Canonical deduped files: `51`
- Duplicate groups collapsed: `6`
- Canonical CSV: `docs/backtest-reports/2026-04-19-tv-backtests-official.csv`

Family counts:
- `Performance`: `1`
- `SATS-PS`: `6`
- `Supertrend`: `2`
- `WB7`: `42`

## Top 10 (Net P&L, trades >= 100)

| Rank | Family | File | Scope | Trades | Net P&L USD | Win Rate | Date Span |
|---|---|---|---|---:|---:|---:|---|
| 1 | Supertrend | Supertrend_Strategy_CME_MINI_MES1!_2026-04-14_78ef5.csv | full_2020plus | 617 | 30568.75 | 37.12% | 2022-04-12 16:00 -> 2026-04-14 04:48 |
| 2 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-13_3950e.csv | full_2020plus | 221 | 5508.00 | 46.61% | 2020-02-18 14:15 -> 2026-04-06 21:00 |
| 3 | SATS-PS | sats_ps_r0_trades_2y_2026-04-17.csv | recent_2024plus | 2360 | 5300.00 | 35.42% | 2024-04-02 03:30 -> 2026-04-17 13:45 |
| 4 | SATS-PS | sats_ps_r0_trades_2025fwd_2026-04-17.csv | post_break_2025plus | 1511 | 4233.00 | 35.67% | 2025-01-02 10:00 -> 2026-04-17 14:00 |
| 5 | Supertrend | Supertrend_Strategy_CME_MINI_MES1!_2026-04-14_9b6d2.csv | post_break_2025plus | 519 | 3530.00 | 36.61% | 2025-06-02 22:30 -> 2026-04-14 04:47 |
| 6 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-12_d7bd9.csv | legacy_pre2020 | 329 | 1905.75 | 44.38% | 2019-05-09 15:00 -> 2026-04-10 06:00 |
| 7 | SATS-PS | SATS-PS_CME_MINI_MES1!_2026-04-17_8d81a.csv | post_break_2025plus | 1633 | 1562.75 | 34.78% | 2025-01-02 10:00 -> 2026-04-17 15:30 |
| 8 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-09_6e97e.csv | legacy_pre2020 | 423 | 1409.23 | 66.19% | 2019-05-09 09:00 -> 2026-04-07 18:00 |
| 9 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-12_e6226.csv | full_2020plus | 1466 | 1340.50 | 31.24% | 2020-01-02 10:00 -> 2026-04-10 16:45 |
| 10 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-12_141de.csv | post_break_2025plus | 141 | 1270.50 | 46.10% | 2025-04-14 03:30 -> 2026-04-08 15:30 |

## Bottom 10 (Net P&L, trades >= 100)

| Rank | Family | File | Scope | Trades | Net P&L USD | Win Rate | Date Span |
|---|---|---|---|---:|---:|---:|---|
| 1 | SATS-PS | sats_ps_r0_trades_2026-04-17.csv | full_2020plus | 7925 | -25337.50 | 33.34% | 2020-01-02 08:15 -> 2026-04-17 13:30 |
| 2 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-10_76bb5.csv | legacy_pre2020 | 8120 | -19553.80 | 26.87% | 2019-05-06 03:15 -> 2025-05-26 23:00 |
| 3 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-10_7fcc8.csv | legacy_pre2020 | 2067 | -16099.33 | 30.33% | 2019-05-06 14:45 -> 2026-04-07 16:15 |
| 4 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-10_0e5e9.csv | legacy_pre2020 | 2595 | -15757.80 | 31.56% | 2019-05-06 11:15 -> 2026-04-10 12:45 |
| 5 | SATS-PS | SATS-PS_CME_MINI_MES1!_2026-04-17_99efd.csv | post_break_2025plus | 2583 | -14666.00 | 33.29% | 2025-01-02 09:30 -> 2026-04-17 15:30 |
| 6 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-10_08283.csv | legacy_pre2020 | 1998 | -9242.52 | 31.23% | 2019-05-06 14:45 -> 2026-04-10 14:15 |
| 7 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-09_bfc69.csv | legacy_pre2020 | 2308 | -8885.67 | 63.43% | 2019-05-08 20:30 -> 2026-04-09 19:00 |
| 8 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-10_593ad.csv | legacy_pre2020 | 3589 | -8720.36 | 58.82% | 2019-05-06 09:30 -> 2026-04-10 13:45 |
| 9 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-13_0f8bc.csv | full_2020plus | 462 | -8565.25 | 27.06% | 2020-01-07 08:30 -> 2026-04-10 12:00 |
| 10 | WB7 | WB7_Strat_CME_MINI_MES1!_2026-04-13_bda84.csv | full_2020plus | 492 | -7882.75 | 16.06% | 2020-01-06 07:30 -> 2026-04-10 12:30 |

## SATS-PS Canonical Runs

| File | Scope | Trades | Net P&L USD | Win Rate | Avg Trade USD | Date Span | Source |
|---|---|---:|---:|---:|---:|---|---|
| sats_ps_r0_trades_2y_2026-04-17.csv | recent_2024plus | 2360 | 5300.00 | 35.42% | 2.25 | 2024-04-02 03:30 -> 2026-04-17 13:45 | repo |
| sats_ps_r0_trades_2025fwd_2026-04-17.csv | post_break_2025plus | 1511 | 4233.00 | 35.67% | 2.80 | 2025-01-02 10:00 -> 2026-04-17 14:00 | repo |
| SATS-PS_CME_MINI_MES1!_2026-04-17_8d81a.csv | post_break_2025plus | 1633 | 1562.75 | 34.78% | 0.96 | 2025-01-02 10:00 -> 2026-04-17 15:30 | downloads |
| SATS-PS_CME_MINI_MES1!_2026-04-17_30afe.csv | post_break_2025plus | 1939 | -5709.25 | 33.83% | -2.94 | 2025-01-02 10:00 -> 2026-04-17 15:15 | downloads |
| SATS-PS_CME_MINI_MES1!_2026-04-17_99efd.csv | post_break_2025plus | 2583 | -14666.00 | 33.29% | -5.68 | 2025-01-02 09:30 -> 2026-04-17 15:30 | downloads |
| sats_ps_r0_trades_2026-04-17.csv | full_2020plus | 7925 | -25337.50 | 33.34% | -3.20 | 2020-01-02 08:15 -> 2026-04-17 13:30 | repo |

## Duplicate Map (Collapsed)

- Canonical: `WB7_Strat_CME_MINI_MES1!_2026-04-12_e6226.csv` (downloads)
  - Duplicate: `WB7_Strat_CME_MINI_MES1!_2026-04-12_acfd3.csv` (downloads)
- Canonical: `WB7_Strat_CME_MINI_MES1!_2026-04-13_16860.csv` (downloads)
  - Duplicate: `WB7_Strat_CME_MINI_MES1!_2026-04-13_c5673.csv` (downloads)
- Canonical: `WB7_Strat_CME_MINI_MES1!_2026-04-13_ec56b.csv` (downloads)
  - Duplicate: `WB7_Strat_CME_MINI_MES1!_2026-04-13_53fe3.csv` (downloads)
- Canonical: `sats_ps_r0_trades_2025fwd_2026-04-17.csv` (repo)
  - Duplicate: `SATS-PS_CME_MINI_MES1!_2026-04-17_e4bfe.csv` (downloads)
- Canonical: `sats_ps_r0_trades_2026-04-17.csv` (repo)
  - Duplicate: `SATS-PS_CME_MINI_MES1!_2026-04-17_864b8.csv` (downloads)
- Canonical: `sats_ps_r0_trades_2y_2026-04-17.csv` (repo)
  - Duplicate: `SATS-PS_CME_MINI_MES1!_2026-04-17_6af1f.csv` (downloads)

## Notes

- `Performance.csv` is included for completeness but uses a different schema (`performance_log`) than Strategy Tester trade exports.
- Rankings are by net P&L only; they do not normalize for different position sizing assumptions across runs.
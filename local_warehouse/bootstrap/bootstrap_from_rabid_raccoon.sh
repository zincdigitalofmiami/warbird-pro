#!/usr/bin/env bash
# Phase 2: One-Time Bootstrap — rabid_raccoon → warbird
# Run once only. After completion, rabid_raccoon is legacy reference only.
# Retention floor: 2020-01-01
#
# Usage:
#   bash local_warehouse/bootstrap/bootstrap_from_rabid_raccoon.sh
#
# Prerequisites:
#   - warbird migrations 001-006 applied and verified (all tables empty)
#   - rabid_raccoon reachable on 127.0.0.1:5432
#
# HG BLOCKER: HG is absent from rabid_raccoon.mkt_futures_1h.
#   After running this script, load HG separately from raw Databento files.

set -euo pipefail

PG_ARGS="-h 127.0.0.1 -p 5432"
RR="rabid_raccoon"
WB="warbird"

echo "[bootstrap] Starting Phase 2 bootstrap: rabid_raccoon → warbird"
echo "[bootstrap] Retention floor: 2020-01-01"
echo ""

# ── 1. MES 15m ──────────────────────────────────────────────────────────────
echo "[1/9] mes_15m..."
psql $PG_ARGS -d "$RR" -c "\copy (
  SELECT \"eventTime\", open::FLOAT8, high::FLOAT8, low::FLOAT8, close::FLOAT8, volume
  FROM mkt_futures_mes_15m
  WHERE \"eventTime\" >= '2020-01-01 00:00:00+00'
  ORDER BY \"eventTime\"
) TO STDOUT (FORMAT CSV)" \
| psql $PG_ARGS -d "$WB" -c "\copy mes_15m (ts, open, high, low, close, volume) FROM STDIN (FORMAT CSV)"
psql $PG_ARGS -d "$WB" -c "SELECT COUNT(*) AS mes_15m_rows, MIN(ts)::DATE AS min_date, MAX(ts)::DATE AS max_date FROM mes_15m;"

# ── 2. MES 1H ───────────────────────────────────────────────────────────────
echo "[2/9] mes_1h..."
psql $PG_ARGS -d "$RR" -c "\copy (
  SELECT \"eventTime\", open::FLOAT8, high::FLOAT8, low::FLOAT8, close::FLOAT8, volume
  FROM mkt_futures_mes_1h
  WHERE \"eventTime\" >= '2020-01-01 00:00:00+00'
  ORDER BY \"eventTime\"
) TO STDOUT (FORMAT CSV)" \
| psql $PG_ARGS -d "$WB" -c "\copy mes_1h (ts, open, high, low, close, volume) FROM STDIN (FORMAT CSV)"
psql $PG_ARGS -d "$WB" -c "SELECT COUNT(*) AS mes_1h_rows, MIN(ts)::DATE AS min_date, MAX(ts)::DATE AS max_date FROM mes_1h;"

# ── 3. MES 4H — derived from mes_1h (UTC-aligned 4H boundaries) ─────────────
echo "[3/9] mes_4h (derived from mes_1h)..."
psql $PG_ARGS -d "$WB" <<'SQL'
INSERT INTO mes_4h (ts, open, high, low, close, volume)
SELECT
  date_trunc('hour', ts) - INTERVAL '1 hour' * (EXTRACT(HOUR FROM ts)::INT % 4) AS ts_4h,
  (array_agg(open  ORDER BY ts))[1]      AS open,
  MAX(high)                              AS high,
  MIN(low)                               AS low,
  (array_agg(close ORDER BY ts DESC))[1] AS close,
  SUM(volume)                            AS volume
FROM mes_1h
GROUP BY ts_4h
ORDER BY ts_4h
ON CONFLICT (ts) DO NOTHING;
SQL
psql $PG_ARGS -d "$WB" -c "SELECT COUNT(*) AS mes_4h_rows, MIN(ts)::DATE AS min_date, MAX(ts)::DATE AS max_date FROM mes_4h;"

# ── 4. MES 1D ───────────────────────────────────────────────────────────────
echo "[4/9] mes_1d..."
psql $PG_ARGS -d "$RR" -c "\copy (
  SELECT \"eventDate\", open::FLOAT8, high::FLOAT8, low::FLOAT8, close::FLOAT8, volume
  FROM mkt_futures_mes_1d
  WHERE \"eventDate\" >= '2020-01-01'
  ORDER BY \"eventDate\"
) TO STDOUT (FORMAT CSV)" \
| psql $PG_ARGS -d "$WB" -c "\copy mes_1d (date, open, high, low, close, volume) FROM STDIN (FORMAT CSV)"
psql $PG_ARGS -d "$WB" -c "SELECT COUNT(*) AS mes_1d_rows, MIN(date) AS min_date, MAX(date) AS max_date FROM mes_1d;"

# ── 5. Cross-asset 1H (5 of 6 symbols — HG missing) ────────────────────────
echo "[5/9] cross_asset_1h (NQ, RTY, CL, 6E, 6J — HG missing, load separately)..."
psql $PG_ARGS -d "$RR" -c "\copy (
  SELECT \"symbolCode\", \"eventTime\", open::FLOAT8, high::FLOAT8, low::FLOAT8, close::FLOAT8, volume, \"openInterest\"
  FROM mkt_futures_1h
  WHERE \"symbolCode\" IN ('NQ', 'RTY', 'CL', '6E', '6J')
    AND \"eventTime\" >= '2020-01-01 00:00:00+00'
  ORDER BY \"symbolCode\", \"eventTime\"
) TO STDOUT (FORMAT CSV)" \
| psql $PG_ARGS -d "$WB" -c "\copy cross_asset_1h (symbol, ts, open, high, low, close, volume, open_interest) FROM STDIN (FORMAT CSV)"
psql $PG_ARGS -d "$WB" -c "SELECT symbol, COUNT(*) AS rows, MIN(ts)::DATE AS min_date, MAX(ts)::DATE AS max_date FROM cross_asset_1h GROUP BY symbol ORDER BY symbol;"

# ── 6. Economic series registry ──────────────────────────────────────────────
echo "[6/9] economic_series..."
psql $PG_ARGS -d "$RR" -c "\copy (
  SELECT \"seriesId\", \"displayName\", \"category\"::TEXT, \"source\"::TEXT,
         \"sourceSymbol\", frequency, units, \"isActive\"
  FROM economic_series
  ORDER BY \"seriesId\"
) TO STDOUT (FORMAT CSV)" \
| psql $PG_ARGS -d "$WB" -c "\copy economic_series (series_id, display_name, category, source, source_symbol, frequency, units, is_active) FROM STDIN (FORMAT CSV)"
psql $PG_ARGS -d "$WB" -c "SELECT COUNT(*) AS series_rows FROM economic_series;"

# ── 7. FRED families ─────────────────────────────────────────────────────────
echo "[7/9] FRED families (10 tables)..."

for tbl_rr in econ_rates_1d econ_yields_1d econ_fx_1d econ_inflation_1d econ_labor_1d econ_activity_1d econ_money_1d econ_commodities_1d econ_indexes_1d; do
  tbl_wb="$tbl_rr"
  echo "  → $tbl_rr..."
  psql $PG_ARGS -d "$RR" -c "\copy (
    SELECT \"seriesId\", \"eventDate\", value::FLOAT8
    FROM $tbl_rr
    WHERE \"eventDate\" >= '2020-01-01'
    ORDER BY \"seriesId\", \"eventDate\"
  ) TO STDOUT (FORMAT CSV)" \
  | psql $PG_ARGS -d "$WB" -c "\copy $tbl_wb (series_id, event_date, value) FROM STDIN (FORMAT CSV)"
done

# econ_vol_indices_1d in rr → econ_vol_1d in warbird (canonical rename)
echo "  → econ_vol_indices_1d → econ_vol_1d..."
psql $PG_ARGS -d "$RR" -c "\copy (
  SELECT \"seriesId\", \"eventDate\", value::FLOAT8
  FROM econ_vol_indices_1d
  WHERE \"eventDate\" >= '2020-01-01'
  ORDER BY \"seriesId\", \"eventDate\"
) TO STDOUT (FORMAT CSV)" \
| psql $PG_ARGS -d "$WB" -c "\copy econ_vol_1d (series_id, event_date, value) FROM STDIN (FORMAT CSV)"

psql $PG_ARGS -d "$WB" -c "
SELECT
  'econ_rates_1d'       AS tbl, COUNT(*) FROM econ_rates_1d       UNION ALL
  SELECT 'econ_yields_1d',       COUNT(*) FROM econ_yields_1d      UNION ALL
  SELECT 'econ_fx_1d',           COUNT(*) FROM econ_fx_1d          UNION ALL
  SELECT 'econ_vol_1d',          COUNT(*) FROM econ_vol_1d         UNION ALL
  SELECT 'econ_inflation_1d',    COUNT(*) FROM econ_inflation_1d   UNION ALL
  SELECT 'econ_labor_1d',        COUNT(*) FROM econ_labor_1d       UNION ALL
  SELECT 'econ_activity_1d',     COUNT(*) FROM econ_activity_1d    UNION ALL
  SELECT 'econ_money_1d',        COUNT(*) FROM econ_money_1d       UNION ALL
  SELECT 'econ_commodities_1d',  COUNT(*) FROM econ_commodities_1d UNION ALL
  SELECT 'econ_indexes_1d',      COUNT(*) FROM econ_indexes_1d
ORDER BY tbl;"

# ── 8. Economic calendar ─────────────────────────────────────────────────────
echo "[8/9] econ_calendar..."
psql $PG_ARGS -d "$RR" -c "\copy (
  SELECT \"eventDate\", \"eventTime\", \"eventName\", \"eventType\",
         \"fredReleaseId\", \"fredSeriesId\", frequency,
         forecast::FLOAT8, previous::FLOAT8, actual::FLOAT8, surprise::FLOAT8,
         \"impactRating\"
  FROM econ_calendar
  ORDER BY \"eventDate\", \"eventName\"
) TO STDOUT (FORMAT CSV)" \
| psql $PG_ARGS -d "$WB" -c "\copy econ_calendar (event_date, event_time, event_name, event_type, fred_release_id, fred_series_id, frequency, forecast, previous, actual, surprise, impact_rating) FROM STDIN (FORMAT CSV)"
psql $PG_ARGS -d "$WB" -c "SELECT COUNT(*) AS cal_rows, MIN(event_date) AS min_date, MAX(event_date) AS max_date FROM econ_calendar;"

# ── 9. Final validation summary ──────────────────────────────────────────────
echo "[9/9] Validation summary..."
psql $PG_ARGS -d "$WB" <<'SQL'
SELECT tbl, rows, min_date, max_date FROM (
  SELECT 'mes_15m'           AS tbl, COUNT(*) AS rows, MIN(ts)::DATE AS min_date, MAX(ts)::DATE AS max_date FROM mes_15m
  UNION ALL
  SELECT 'mes_1h',           COUNT(*), MIN(ts)::DATE, MAX(ts)::DATE FROM mes_1h
  UNION ALL
  SELECT 'mes_4h',           COUNT(*), MIN(ts)::DATE, MAX(ts)::DATE FROM mes_4h
  UNION ALL
  SELECT 'mes_1d',           COUNT(*), MIN(date), MAX(date) FROM mes_1d
  UNION ALL
  SELECT 'cross_asset_1h',   COUNT(*), MIN(ts)::DATE, MAX(ts)::DATE FROM cross_asset_1h
  UNION ALL
  SELECT 'economic_series',  COUNT(*), NULL, NULL FROM economic_series
  UNION ALL
  SELECT 'econ_calendar',    COUNT(*), MIN(event_date), MAX(event_date) FROM econ_calendar
) t ORDER BY tbl;
SQL

echo ""
echo "[bootstrap] COMPLETE. Review counts above."
echo "[bootstrap] HG BLOCKER: cross_asset_1h missing HG. Load from raw Databento files before Phase 2 signoff."
echo "[bootstrap] Next: Phase 3 — AG canonical schema (007_ag_schema.sql)"

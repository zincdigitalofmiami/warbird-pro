-- Migration 030: Backfill cross_asset_1d from cross_asset_1h
-- cross_asset_1d only has data from 2026-03-15 (163 rows).
-- cross_asset_1h has 131k+ rows going back further.
-- This rolls up 1h bars into daily OHLCV for the 2024-01-01+ retention window.

insert into cross_asset_1d (ts, symbol_code, open, high, low, close, volume)
select
  date_trunc('day', ts) as ts,
  symbol_code,
  (array_agg(open order by ts))[1] as open,
  max(high) as high,
  min(low) as low,
  (array_agg(close order by ts desc))[1] as close,
  sum(volume) as volume
from cross_asset_1h
where ts >= '2024-01-01'
group by date_trunc('day', ts), symbol_code
on conflict (ts, symbol_code) do update set
  open   = excluded.open,
  high   = excluded.high,
  low    = excluded.low,
  close  = excluded.close,
  volume = excluded.volume;

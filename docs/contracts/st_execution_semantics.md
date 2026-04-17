# ST Execution Semantics — Canonical Event Resolver

Authority: This spec governs both Pine v8 (Slice 9) and the Python pipeline (Slices 3/4).
Any discrepancy between Pine and Python behavior is a bug, not ambiguity.

## Scope Split

- Pine v8 skeleton is SATS-derived for live rendering and operator state.
- Python computes training-only features from OHLCV (`in_ote_zone`, `structure_event`) and labels outcomes.
- This resolver is the single execution-order contract both must follow.

## Per-Bar Event Order

On every confirmed bar (`barstate.isconfirmed` in Pine; bar-close timestamp in Python):

1. Load: `entry_price`, `current_sl`, `current_tp1`, `current_tp2`, `current_tp3`
2. SL check: if `low <= current_sl` (long) or `high >= current_sl` (short)
   - outcome = `STOPPED`
   - close at `current_sl`
   - stop processing
3. TP1 check: if `high >= current_tp1` (long) or `low <= current_tp1` (short)
   - ratchet: `current_sl = entry_price` (breakeven)
4. TP2 check: if `high >= current_tp2` (long) or `low <= current_tp2` (short)
   - ratchet: `current_sl = current_tp1`
5. TP3 check: if `high >= current_tp3` (long) or `low <= current_tp3` (short)
   - ratchet: `current_sl = current_tp2`

## Same-Bar Conflict Rule

If SL and any TP are both breached on the same bar:

- SL wins.
- Outcome = `STOPPED` at `current_sl`.
- TP is not credited.

## Trail Update Timing

Trail updates use the SL value as of bar open (pre-bar value).
Intra-bar ratchets do not apply until the next bar's SL check.

## Entry Timing

Entries are bar-close only. No mid-bar entries in Pine or Python.
Signal bar close = `entry_price`. Features freeze at signal bar close.

## SL Sizing

- `eff_atr = atr14 * (0.5 + 0.5 * er)`
- Candidate distance = `eff_atr * sl_atr_mult`
- Optimization floor: `sl_atr_mult >= 0.618`
- Live indicator enforcement remains: structural stop floor at `0.618 x ATR(14)` plus emergency `1.000 x ATR(14)`

Long:

- `entry_sl = entry_price - candidate_distance`

Short:

- `entry_sl = entry_price + candidate_distance`

## TP Sizing

- `tp1 = entry_price + (direction * eff_atr * tp1_r)`
- `tp2 = entry_price + (direction * eff_atr * tp2_r)`
- `tp3 = entry_price + (direction * eff_atr * tp3_r)`

`direction` is `+1` for long and `-1` for short.
`tp1_r`, `tp2_r`, and `tp3_r` come from the `st_tp_configs` row.

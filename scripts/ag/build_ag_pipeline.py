#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


CHICAGO_TZ = ZoneInfo("America/Chicago")
DEFAULT_DSN = os.environ.get("WARBIRD_PG_DSN", "host=127.0.0.1 port=5432 dbname=warbird")

FIB_236 = 0.236
FIB_382 = 0.382
FIB_500 = 0.5
FIB_618 = 0.618
FIB_786 = 0.786
FIB_100 = 1.0
FIB_T1 = 1.236
FIB_T2 = 1.618
FIB_T3 = 2.0
FIB_T4 = 2.236
FIB_T5 = 2.618

AG_TRAINING_VIEW_SQL = """
CREATE OR REPLACE VIEW ag_training AS
SELECT
  i.*,
  s.anchor_high, s.anchor_low, s.fib_range, s.fib_bull,
  s.anchor_swing_bars, s.anchor_swing_velocity, s.atr14,
  o.highest_tp_hit, o.hit_tp1, o.hit_tp2, o.hit_tp3, o.hit_tp4, o.hit_tp5,
  o.tp1_before_sl, o.mae_pts, o.mfe_pts, o.outcome_label,
  o.bars_to_tp1, o.bars_to_sl
FROM ag_fib_interactions i
JOIN ag_fib_snapshots s ON i.snapshot_ts = s.ts
JOIN ag_fib_outcomes o ON o.interaction_id = i.id
WHERE o.outcome_label != 'CENSORED'
"""


@dataclass
class MesBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class SnapshotState:
    ts: datetime
    anchor_high: float
    anchor_low: float
    anchor_high_ts: datetime
    anchor_low_ts: datetime
    fib_range: float
    fib_bull: bool
    zz_deviation: float
    zz_depth: int
    anchor_swing_bars: int
    anchor_swing_velocity: float
    time_since_anchor: int
    atr14: float
    atr_pct: float


@dataclass
class InteractionRow:
    ts: datetime
    snapshot_ts: datetime
    direction: int
    fib_level_touched: int
    fib_level_price: float
    touch_distance_pts: float
    touch_distance_norm: float
    interaction_state: int
    archetype: int
    entry_price: float
    sl_price: float
    tp1_price: float
    tp2_price: float
    tp3_price: float
    tp4_price: float
    tp5_price: float
    sl_dist_pts: float
    sl_dist_atr: float
    tp1_dist_pts: float
    rr_to_tp1: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    body_pct: float
    upper_wick_pct: float
    lower_wick_pct: float
    rvol: float
    rsi14: float
    ema9: float
    ema21: float
    ema50: float
    ema200: float
    ema_stacked_bull: bool
    ema_stacked_bear: bool
    ema9_dist_pct: float
    macd_hist: float
    adx: float
    energy: float
    confluence_quality: float
    ml_exec_tf_code: int
    ml_exec_direction_code: int
    ml_exec_state_code: int
    ml_exec_pattern_code: int
    ml_exec_pocket_code: int
    ml_exec_impulse_break_atr: float | None
    ml_exec_reclaim_dist_atr: float | None
    ml_exec_orderflow_bias: int
    ml_exec_delta_norm: float | None
    ml_exec_absorption: bool
    ml_exec_zero_print: bool
    ml_exec_same_dir_imbalance_ct: int
    ml_exec_opp_dir_imbalance_ct: int
    ml_exec_target_leg_code: int
    bar_index: int
    trade_dir: int


@dataclass
class MicroExecContext:
    tf_code: int = 0
    direction_code: int = 0
    state_code: int = 0
    pattern_code: int = 0
    pocket_code: int = 0
    impulse_break_atr: float | None = None
    reclaim_dist_atr: float | None = None
    orderflow_bias: int = 0
    delta_norm: float | None = None
    absorption: bool = False
    zero_print: bool = False
    same_dir_imbalance_ct: int = 0
    opp_dir_imbalance_ct: int = 0
    target_leg_code: int = 0


MICRO_EXEC_STATE_NONE = 0
MICRO_EXEC_STATE_WATCH = 1
MICRO_EXEC_STATE_ARMED = 2
MICRO_EXEC_STATE_GREEN = 3
MICRO_EXEC_STATE_INVALIDATED = 4
MICRO_EXEC_STATE_EXPIRED = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build canonical AG tables and walk-forward split structure from local warbird data."
    )
    parser.add_argument(
        "--dsn",
        default=DEFAULT_DSN,
        help="PostgreSQL DSN for local warbird warehouse (default: host=127.0.0.1 port=5432 dbname=warbird).",
    )
    parser.add_argument("--start-ts", default=None, help="Optional inclusive UTC lower bound (ISO-8601).")
    parser.add_argument("--end-ts", default=None, help="Optional inclusive UTC upper bound (ISO-8601).")
    parser.add_argument(
        "--observation-window",
        type=int,
        default=32,
        help="Forward bars used for outcome resolution and censoring.",
    )
    parser.add_argument(
        "--touch-tol-pts",
        type=float,
        default=2.0,
        help="Absolute close-to-level tolerance (points) when bar does not range-touch any fib levels.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append into canonical AG tables instead of truncating first.",
    )
    parser.add_argument(
        "--skip-populate",
        action="store_true",
        help="Skip table population and only build split structure from existing ag_training rows.",
    )
    parser.add_argument(
        "--splits-output",
        default="artifacts/ag_runs",
        help="Directory for split manifests and CSV exports.",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.70,
        help="Session-date ratio for train slice.",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.15,
        help="Session-date ratio for validation slice.",
    )
    parser.add_argument(
        "--session-embargo",
        type=int,
        default=1,
        help="Minimum number of full sessions between split boundaries.",
    )
    return parser.parse_args()


def to_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def fetch_mes_15m_rows(conn: psycopg2.extensions.connection, start_ts: str | None, end_ts: str | None) -> list[MesBar]:
    where = []
    params: list[Any] = []
    if start_ts:
        where.append("ts >= %s::timestamptz")
        params.append(start_ts)
    if end_ts:
        where.append("ts <= %s::timestamptz")
        params.append(end_ts)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    sql = f"""
        SELECT ts, open, high, low, close, volume
        FROM mes_15m
        {where_sql}
        ORDER BY ts ASC
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    bars = [
        MesBar(
            ts=row["ts"],
            open=to_float(row["open"]),
            high=to_float(row["high"]),
            low=to_float(row["low"]),
            close=to_float(row["close"]),
            volume=to_float(row["volume"]),
        )
        for row in rows
    ]
    return bars


def table_exists(conn: psycopg2.extensions.connection, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
        return cur.fetchone()[0] is not None


def fetch_mes_1m_rows(conn: psycopg2.extensions.connection, start_ts: str | None, end_ts: str | None) -> list[MesBar]:
    if not table_exists(conn, "mes_1m"):
        return []

    where = []
    params: list[Any] = []
    if start_ts:
        where.append("ts >= %s::timestamptz - interval '14 minutes'")
        params.append(start_ts)
    if end_ts:
        where.append("ts <= %s::timestamptz")
        params.append(end_ts)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    sql = f"""
        SELECT ts, open, high, low, close, volume
        FROM mes_1m
        {where_sql}
        ORDER BY ts ASC
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        MesBar(
            ts=row["ts"],
            open=to_float(row["open"]),
            high=to_float(row["high"]),
            low=to_float(row["low"]),
            close=to_float(row["close"]),
            volume=to_float(row["volume"]),
        )
        for row in rows
    ]


def ema(values: list[float], length: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (length + 1.0)
    out: list[float] = []
    prev = values[0]
    out.append(prev)
    for v in values[1:]:
        prev = alpha * v + (1.0 - alpha) * prev
        out.append(prev)
    return out


def rma(values: list[float], length: int) -> list[float]:
    if not values:
        return []
    out: list[float] = []
    prev = values[0]
    out.append(prev)
    alpha = 1.0 / float(length)
    for v in values[1:]:
        prev = alpha * v + (1.0 - alpha) * prev
        out.append(prev)
    return out


def sma(values: list[float], length: int) -> list[float]:
    out: list[float] = []
    window: list[float] = []
    running = 0.0
    for v in values:
        window.append(v)
        running += v
        if len(window) > length:
            running -= window.pop(0)
        out.append(running / len(window))
    return out


def rolling_max(values: list[float], length: int) -> list[float]:
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - length + 1)
        out.append(max(values[lo : i + 1]))
    return out


def rolling_min(values: list[float], length: int) -> list[float]:
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - length + 1)
        out.append(min(values[lo : i + 1]))
    return out


def true_range(bars: list[MesBar]) -> list[float]:
    out: list[float] = []
    prev_close = bars[0].close if bars else 0.0
    for idx, b in enumerate(bars):
        if idx == 0:
            tr = b.high - b.low
        else:
            tr = max(b.high - b.low, abs(b.high - prev_close), abs(b.low - prev_close))
        out.append(tr)
        prev_close = b.close
    return out


def calc_rsi(closes: list[float], length: int = 14) -> list[float]:
    if not closes:
        return []
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = rma(gains, length)
    avg_loss = rma(losses, length)
    out: list[float] = []
    for g, l in zip(avg_gain, avg_loss):
        if l == 0.0:
            out.append(100.0)
        else:
            rs = g / l
            out.append(100.0 - (100.0 / (1.0 + rs)))
    return out


def calc_adx(bars: list[MesBar], length: int = 14) -> list[float]:
    if not bars:
        return []
    plus_dm = [0.0]
    minus_dm = [0.0]
    tr = [bars[0].high - bars[0].low]
    for i in range(1, len(bars)):
        up_move = bars[i].high - bars[i - 1].high
        down_move = bars[i - 1].low - bars[i].low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        tr.append(max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low - bars[i - 1].close),
        ))

    tr_rma = rma(tr, length)
    plus_rma = rma(plus_dm, length)
    minus_rma = rma(minus_dm, length)
    dx: list[float] = []
    for t, p, m in zip(tr_rma, plus_rma, minus_rma):
        if t == 0.0:
            dx.append(0.0)
            continue
        plus_di = (100.0 * p) / t
        minus_di = (100.0 * m) / t
        denom = plus_di + minus_di
        if denom == 0.0:
            dx.append(0.0)
        else:
            dx.append((100.0 * abs(plus_di - minus_di)) / denom)
    return rma(dx, length)


def calc_indicators(bars: list[MesBar]) -> dict[str, list[float]]:
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    volumes = [b.volume for b in bars]

    tr = true_range(bars)
    atr14 = rma(tr, 14)
    atr10 = rma(tr, 10)
    atr_pct = [(a / c * 100.0) if c else 0.0 for a, c in zip(atr14, closes)]

    ema9 = ema(closes, 9)
    ema12 = ema(closes, 12)
    ema21 = ema(closes, 21)
    ema26 = ema(closes, 26)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    macd_line = [f - s for f, s in zip(ema12, ema26)]
    macd_signal = ema(macd_line, 9)
    macd_hist = [m - s for m, s in zip(macd_line, macd_signal)]

    rsi14 = calc_rsi(closes, 14)
    adx14 = calc_adx(bars, 14)
    rvol20 = [v / max(m, 1e-9) for v, m in zip(volumes, sma(volumes, 20))]
    high_8 = rolling_max(highs, 8)
    low_8 = rolling_min(lows, 8)
    high_13 = rolling_max(highs, 13)
    low_13 = rolling_min(lows, 13)
    high_21 = rolling_max(highs, 21)
    low_21 = rolling_min(lows, 21)
    high_34 = rolling_max(highs, 34)
    low_34 = rolling_min(lows, 34)
    high_55 = rolling_max(highs, 55)
    low_55 = rolling_min(lows, 55)

    return {
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": volumes,
        "atr14": atr14,
        "atr10": atr10,
        "atr_pct": atr_pct,
        "ema9": ema9,
        "ema21": ema21,
        "ema50": ema50,
        "ema200": ema200,
        "macd_hist": macd_hist,
        "rsi14": rsi14,
        "adx14": adx14,
        "rvol20": rvol20,
        "high_8": high_8,
        "low_8": low_8,
        "high_13": high_13,
        "low_13": low_13,
        "high_21": high_21,
        "low_21": low_21,
        "high_34": high_34,
        "low_34": low_34,
        "high_55": high_55,
        "low_55": low_55,
    }


def is_pivot_high(highs: list[float], idx: int, depth: int) -> bool:
    if idx - depth < 0 or idx + depth >= len(highs):
        return False
    pivot = highs[idx]
    for i in range(idx - depth, idx + depth + 1):
        if i == idx:
            continue
        if highs[i] >= pivot:
            return False
    return True


def is_pivot_low(lows: list[float], idx: int, depth: int) -> bool:
    if idx - depth < 0 or idx + depth >= len(lows):
        return False
    pivot = lows[idx]
    for i in range(idx - depth, idx + depth + 1):
        if i == idx:
            continue
        if lows[i] <= pivot:
            return False
    return True


def calc_confluence_quality(
    anchor_high: float,
    anchor_low: float,
    high_8: float,
    low_8: float,
    high_13: float,
    low_13: float,
    high_21: float,
    low_21: float,
    high_34: float,
    low_34: float,
    high_55: float,
    low_55: float,
    tol_pct: float = 0.05,
) -> float:
    anchor_range = anchor_high - anchor_low
    if anchor_range <= 0:
        return 0.0
    tol = anchor_range * tol_pct * 0.01
    conf_hits = 0
    pairs = [
        (high_8, low_8),
        (high_13, low_13),
        (high_21, low_21),
        (high_34, low_34),
        (high_55, low_55),
    ]
    for rolling_h, rolling_l in pairs:
        rolling_range = rolling_h - rolling_l
        if rolling_range <= 0:
            continue
        for ratio in (FIB_382, FIB_500, FIB_618):
            anchor_level = anchor_low + anchor_range * ratio
            rolling_level = rolling_l + rolling_range * ratio
            if abs(anchor_level - rolling_level) <= tol:
                conf_hits += 1
    return float(conf_hits) * anchor_range


def fib_price(fib_base: float, fib_dir: float, fib_range: float, ratio: float) -> float:
    if fib_range <= 0:
        return float("nan")
    return fib_base + fib_dir * fib_range * ratio


def nearest_fib_level(levels: list[tuple[int, float]], close_price: float) -> tuple[int, float, float]:
    level_code, level_price = min(levels, key=lambda item: abs(close_price - item[1]))
    return level_code, level_price, abs(close_price - level_price)


def build_snapshots_and_interactions(
    bars: list[MesBar],
    ind: dict[str, list[float]],
    micro_bars: list[MesBar],
    touch_tol_pts: float,
) -> tuple[list[SnapshotState], list[InteractionRow]]:
    snapshots: list[SnapshotState] = []
    interactions: list[InteractionRow] = []

    highs = ind["high"]
    lows = ind["low"]
    closes = ind["close"]

    fib_deviation = 3.0
    fib_depth = 15
    fib_threshold_floor_pct = 0.50
    min_fib_range_atr = 0.5
    retest_bars = 6

    last_pivot: tuple[str, int, float] | None = None
    current_snapshot: SnapshotState | None = None
    current_snapshot_idx: int | None = None
    last_break_bar: int | None = None
    micro_window_index = build_micro_window_index(bars, micro_bars)

    for i in range(len(bars)):
        pivot_idx = i - fib_depth
        if pivot_idx >= fib_depth:
            pivot_candidates: list[tuple[str, int, float]] = []
            if is_pivot_high(highs, pivot_idx, fib_depth):
                pivot_candidates.append(("H", pivot_idx, highs[pivot_idx]))
            if is_pivot_low(lows, pivot_idx, fib_depth):
                pivot_candidates.append(("L", pivot_idx, lows[pivot_idx]))

            for pivot_type, p_idx, p_price in pivot_candidates:
                if last_pivot is None:
                    last_pivot = (pivot_type, p_idx, p_price)
                    continue
                if pivot_type == last_pivot[0]:
                    if pivot_type == "H" and p_price > last_pivot[2]:
                        last_pivot = (pivot_type, p_idx, p_price)
                    elif pivot_type == "L" and p_price < last_pivot[2]:
                        last_pivot = (pivot_type, p_idx, p_price)
                    continue

                ref_price = max(abs(last_pivot[2]), 1e-9)
                move_pct = abs((p_price - last_pivot[2]) / ref_price) * 100.0
                dyn_thr = max((ind["atr10"][p_idx] / max(closes[p_idx], 1e-9)) * 100.0 * fib_deviation, fib_threshold_floor_pct)
                if move_pct < dyn_thr:
                    continue

                high_idx = p_idx if pivot_type == "H" else last_pivot[1]
                low_idx = p_idx if pivot_type == "L" else last_pivot[1]
                anchor_high = highs[high_idx]
                anchor_low = lows[low_idx]
                anchor_range = anchor_high - anchor_low
                atr14_now = ind["atr14"][i]
                min_range = min_fib_range_atr * atr14_now
                if anchor_range <= 0 or anchor_range < min_range:
                    last_pivot = (pivot_type, p_idx, p_price)
                    continue

                snapshot = SnapshotState(
                    ts=bars[i].ts,
                    anchor_high=anchor_high,
                    anchor_low=anchor_low,
                    anchor_high_ts=bars[high_idx].ts,
                    anchor_low_ts=bars[low_idx].ts,
                    fib_range=anchor_range,
                    fib_bull=high_idx > low_idx,
                    zz_deviation=fib_deviation,
                    zz_depth=fib_depth,
                    anchor_swing_bars=abs(high_idx - low_idx),
                    anchor_swing_velocity=anchor_range / max(abs(high_idx - low_idx), 1),
                    time_since_anchor=0,
                    atr14=atr14_now,
                    atr_pct=ind["atr_pct"][i],
                )
                snapshots.append(snapshot)
                current_snapshot = snapshot
                current_snapshot_idx = i
                last_break_bar = None
                last_pivot = (pivot_type, p_idx, p_price)

        if current_snapshot is None or current_snapshot_idx is None:
            continue

        fib_range = current_snapshot.anchor_high - current_snapshot.anchor_low
        atr14_now = ind["atr14"][i]
        min_range = min_fib_range_atr * atr14_now
        if fib_range < min_range or fib_range <= 0:
            continue

        fib_bull = current_snapshot.fib_bull
        fib_base = current_snapshot.anchor_low if fib_bull else current_snapshot.anchor_high
        fib_dir = 1.0 if fib_bull else -1.0
        direction = 1 if fib_bull else -1

        p236 = fib_price(fib_base, fib_dir, fib_range, FIB_236)
        p382 = fib_price(fib_base, fib_dir, fib_range, FIB_382)
        p500 = fib_price(fib_base, fib_dir, fib_range, FIB_500)
        p618 = fib_price(fib_base, fib_dir, fib_range, FIB_618)
        p786 = fib_price(fib_base, fib_dir, fib_range, FIB_786)
        p100 = fib_price(fib_base, fib_dir, fib_range, FIB_100)
        p_t1 = fib_price(fib_base, fib_dir, fib_range, FIB_T1)
        p_t2 = fib_price(fib_base, fib_dir, fib_range, FIB_T2)
        p_t3 = fib_price(fib_base, fib_dir, fib_range, FIB_T3)
        p_t4 = fib_price(fib_base, fib_dir, fib_range, FIB_T4)
        p_t5 = fib_price(fib_base, fib_dir, fib_range, FIB_T5)

        zone_upper = max(p618, p786)
        zone_lower = min(p618, p786)
        close_now = bars[i].close
        close_prev = bars[i - 1].close if i > 0 else close_now
        low_now = bars[i].low
        high_now = bars[i].high

        break_in_dir = (
            (direction == 1 and close_now > zone_upper and close_prev <= zone_upper)
            or (direction == -1 and close_now < zone_lower and close_prev >= zone_lower)
        )
        if break_in_dir:
            last_break_bar = i

        bars_since_break = (i - last_break_bar) if last_break_bar is not None else None
        accept_in_dir = bool(
            bars_since_break is not None
            and bars_since_break > 0
            and bars_since_break <= retest_bars
            and (
                (direction == 1 and low_now <= zone_upper and close_now > zone_upper)
                or (direction == -1 and high_now >= zone_lower and close_now < zone_lower)
            )
        )
        reject_at_zone = bool(
            (direction == 1 and high_now >= zone_lower and close_now < zone_lower)
            or (direction == -1 and low_now <= zone_upper and close_now > zone_upper)
        )
        break_against = bool(
            (direction == 1 and close_now < p500 and close_prev >= p500)
            or (direction == -1 and close_now > p500 and close_prev <= p500)
        )
        pivot_near_zone = close_now <= zone_upper and close_now >= zone_lower
        tag_t1 = (direction == 1 and high_now >= p_t1) or (direction == -1 and low_now <= p_t1)

        interaction_state = 4 if break_in_dir else 3 if reject_at_zone else 1 if accept_in_dir else 2 if break_against else 5 if pivot_near_zone else 0
        setup_reentry_after_tp1 = tag_t1 and accept_in_dir
        archetype = 1 if accept_in_dir else 2 if reject_at_zone else 3 if break_in_dir else 4 if break_against else 5 if setup_reentry_after_tp1 else 0

        level_pairs = [
            (236, p236),
            (382, p382),
            (500, p500),
            (618, p618),
            (786, p786),
            (1000, p100),
        ]
        touched_by_range = [pair for pair in level_pairs if low_now <= pair[1] <= high_now]
        if touched_by_range:
            level_code, level_price, distance = nearest_fib_level(touched_by_range, close_now)
        else:
            level_code, level_price, distance = nearest_fib_level(level_pairs, close_now)
            if distance > touch_tol_pts:
                continue

        entry_price = p618 if direction == 1 else p382
        sl_price = entry_price - 1.5 * atr14_now if direction == 1 else entry_price + 1.5 * atr14_now
        sl_dist_pts = abs(entry_price - sl_price)
        tp1_dist_pts = abs(p_t1 - entry_price)
        sl_dist_atr = sl_dist_pts / max(atr14_now, 1e-9)
        rr_to_tp1 = tp1_dist_pts / max(sl_dist_pts, 1e-9)

        bar_range = max(high_now - low_now, 1e-9)
        body_pct = abs(close_now - bars[i].open) / bar_range
        upper_wick = high_now - max(bars[i].open, close_now)
        lower_wick = min(bars[i].open, close_now) - low_now
        upper_wick_pct = max(0.0, upper_wick / bar_range)
        lower_wick_pct = max(0.0, lower_wick / bar_range)

        ema9 = ind["ema9"][i]
        ema21 = ind["ema21"][i]
        ema50 = ind["ema50"][i]
        ema200 = ind["ema200"][i]

        ema_stacked_bull = ema9 > ema21 > ema50 > ema200
        ema_stacked_bear = ema9 < ema21 < ema50 < ema200
        ema9_dist_pct = ((close_now - ema9) / ema9 * 100.0) if ema9 else 0.0
        energy = (abs(close_now - bars[i].open) / bar_range) * min(bar_range / max(atr14_now, 1e-9), 5.0)

        cq = calc_confluence_quality(
            current_snapshot.anchor_high,
            current_snapshot.anchor_low,
            ind["high_8"][i],
            ind["low_8"][i],
            ind["high_13"][i],
            ind["low_13"][i],
            ind["high_21"][i],
            ind["low_21"][i],
            ind["high_34"][i],
            ind["low_34"][i],
            ind["high_55"][i],
            ind["low_55"][i],
            tol_pct=0.05,
        )
        window_start_idx, window_end_idx = micro_window_index.get(bars[i].ts, (0, 0))
        micro_ctx = derive_micro_exec_context(
            window_bars=micro_bars[window_start_idx:window_end_idx],
            direction=direction,
            fib_level_touched=level_code,
            fib_level_price=level_price,
            close_now=close_now,
            high_now=high_now,
            low_now=low_now,
            atr14_now=atr14_now,
        )

        interactions.append(
            InteractionRow(
                ts=bars[i].ts,
                snapshot_ts=current_snapshot.ts,
                direction=direction,
                fib_level_touched=level_code,
                fib_level_price=level_price,
                touch_distance_pts=distance,
                touch_distance_norm=distance / max(atr14_now, 1e-9),
                interaction_state=interaction_state,
                archetype=archetype,
                entry_price=entry_price,
                sl_price=sl_price,
                tp1_price=p_t1,
                tp2_price=p_t2,
                tp3_price=p_t3,
                tp4_price=p_t4,
                tp5_price=p_t5,
                sl_dist_pts=sl_dist_pts,
                sl_dist_atr=sl_dist_atr,
                tp1_dist_pts=tp1_dist_pts,
                rr_to_tp1=rr_to_tp1,
                open=bars[i].open,
                high=high_now,
                low=low_now,
                close=close_now,
                volume=bars[i].volume,
                body_pct=body_pct,
                upper_wick_pct=upper_wick_pct,
                lower_wick_pct=lower_wick_pct,
                rvol=ind["rvol20"][i],
                rsi14=ind["rsi14"][i],
                ema9=ema9,
                ema21=ema21,
                ema50=ema50,
                ema200=ema200,
                ema_stacked_bull=ema_stacked_bull,
                ema_stacked_bear=ema_stacked_bear,
                ema9_dist_pct=ema9_dist_pct,
                macd_hist=ind["macd_hist"][i],
                adx=ind["adx14"][i],
                energy=energy,
                confluence_quality=cq,
                ml_exec_tf_code=micro_ctx.tf_code,
                ml_exec_direction_code=micro_ctx.direction_code,
                ml_exec_state_code=micro_ctx.state_code,
                ml_exec_pattern_code=micro_ctx.pattern_code,
                ml_exec_pocket_code=micro_ctx.pocket_code,
                ml_exec_impulse_break_atr=micro_ctx.impulse_break_atr,
                ml_exec_reclaim_dist_atr=micro_ctx.reclaim_dist_atr,
                ml_exec_orderflow_bias=micro_ctx.orderflow_bias,
                ml_exec_delta_norm=micro_ctx.delta_norm,
                ml_exec_absorption=micro_ctx.absorption,
                ml_exec_zero_print=micro_ctx.zero_print,
                ml_exec_same_dir_imbalance_ct=micro_ctx.same_dir_imbalance_ct,
                ml_exec_opp_dir_imbalance_ct=micro_ctx.opp_dir_imbalance_ct,
                ml_exec_target_leg_code=micro_ctx.target_leg_code,
                bar_index=i,
                trade_dir=direction,
            )
        )

    return snapshots, interactions


def build_micro_window_index(
    parent_bars: list[MesBar],
    micro_bars: list[MesBar],
) -> dict[datetime, tuple[int, int]]:
    if not parent_bars or not micro_bars:
        return {}

    index: dict[datetime, tuple[int, int]] = {}
    start_idx = 0
    end_idx = 0
    micro_len = len(micro_bars)

    for parent_bar in parent_bars:
        window_start = parent_bar.ts - timedelta(minutes=14)
        while start_idx < micro_len and micro_bars[start_idx].ts < window_start:
            start_idx += 1
        while end_idx < micro_len and micro_bars[end_idx].ts <= parent_bar.ts:
            end_idx += 1
        index[parent_bar.ts] = (start_idx, end_idx)
    return index


def micro_signed_flow(bar: MesBar) -> float:
    bar_range = max(bar.high - bar.low, 1e-9)
    clv = (bar.close - bar.low) / bar_range
    return bar.volume * (2.0 * clv - 1.0)


def rollup_micro_bars(window_bars: list[MesBar], bucket_size: int) -> list[MesBar]:
    if bucket_size <= 1:
        return window_bars
    usable = (len(window_bars) // bucket_size) * bucket_size
    if usable <= 0:
        return []
    start = len(window_bars) - usable
    rolled: list[MesBar] = []
    for idx in range(start, len(window_bars), bucket_size):
        chunk = window_bars[idx : idx + bucket_size]
        rolled.append(
            MesBar(
                ts=chunk[-1].ts,
                open=chunk[0].open,
                high=max(bar.high for bar in chunk),
                low=min(bar.low for bar in chunk),
                close=chunk[-1].close,
                volume=sum(bar.volume for bar in chunk),
            )
        )
    return rolled


def micro_target_leg_code(fib_level_touched: int, pattern_code: int) -> int:
    if pattern_code == 3:
        return 1
    if fib_level_touched >= 786:
        return 2
    if fib_level_touched in {236, 382, 500, 618}:
        return 3
    return 0


def micro_exec_expired(
    state_code: int,
    reclaim_dist_atr: float,
    impulse_break_atr: float,
) -> bool:
    if state_code not in {MICRO_EXEC_STATE_WATCH, MICRO_EXEC_STATE_ARMED}:
        return False
    return reclaim_dist_atr >= 1.5 and impulse_break_atr <= 0.15


def micro_tail_metrics(
    rolled: list[MesBar],
    flows: list[float],
    bucket_size: int,
    atr14_now: float,
) -> tuple[float, float]:
    tail_len = 5 if bucket_size == 1 else 3 if bucket_size == 3 else 2
    tail_len = min(tail_len, len(rolled))
    if tail_len <= 0:
        return 0.0, 0.0

    tail_rows = rolled[-tail_len:]
    tail_flows = flows[-tail_len:]
    tail_vol = sum(bar.volume for bar in tail_rows)
    tail_delta = sum(tail_flows) / max(tail_vol, 1.0)
    tail_move = (tail_rows[-1].close - tail_rows[0].open) / max(atr14_now, 1e-9)
    return tail_delta, tail_move


def micro_counter_target_leg_code(
    parent_direction: int,
    fib_level_touched: int,
    fib_level_price: float,
    close_now: float,
) -> int:
    if parent_direction == 1:
        return 1 if fib_level_touched in {618, 786} and close_now <= fib_level_price else 0
    return 1 if fib_level_touched in {236, 382} and close_now >= fib_level_price else 0


def derive_micro_exec_context(
    window_bars: list[MesBar],
    direction: int,
    fib_level_touched: int,
    fib_level_price: float,
    close_now: float,
    high_now: float,
    low_now: float,
    atr14_now: float,
) -> MicroExecContext:
    pocket_code = fib_level_touched if fib_level_touched in {236, 382, 500, 618, 786} else 0
    context = MicroExecContext(pocket_code=pocket_code)
    if len(window_bars) < 3 or atr14_now <= 0:
        context.target_leg_code = micro_target_leg_code(fib_level_touched, 0)
        return context

    scored_timeframes: list[dict[str, float | int]] = []
    for bucket_size in (1, 3, 5):
        rolled = rollup_micro_bars(window_bars, bucket_size)
        if not rolled:
            continue
        flows = [micro_signed_flow(bar) for bar in rolled]
        vol_sum = sum(bar.volume for bar in rolled)
        raw_delta = sum(flows) / max(vol_sum, 1.0)
        directional_pressure = direction * raw_delta
        same_dir_count = sum(
            1 for flow, bar in zip(flows, rolled, strict=False)
            if direction * flow > max(bar.volume * 0.15, 1.0)
        )
        opp_dir_count = sum(
            1 for flow, bar in zip(flows, rolled, strict=False)
            if direction * flow < -max(bar.volume * 0.15, 1.0)
        )
        raw_move_norm = (rolled[-1].close - rolled[0].open) / max(atr14_now, 1e-9)
        net_move_norm = direction * raw_move_norm
        tail_delta_raw, tail_move_raw = micro_tail_metrics(rolled, flows, bucket_size, atr14_now)
        counter_tail_pressure = (-direction) * tail_delta_raw
        counter_tail_move = (-direction) * tail_move_raw
        close_side_counter = (-direction) * ((close_now - fib_level_price) / max(atr14_now, 1e-9))
        level_failed_reclaim = bool(
            (direction == 1 and max(bar.high for bar in rolled) >= fib_level_price and close_now < fib_level_price)
            or (direction == -1 and min(bar.low for bar in rolled) <= fib_level_price and close_now > fib_level_price)
        )
        orderflow_bias = 0
        if directional_pressure >= 0.15:
            orderflow_bias = 1
        elif directional_pressure <= -0.15 or opp_dir_count > same_dir_count:
            orderflow_bias = -1
        score = directional_pressure + 0.25 * net_move_norm + 0.05 * (same_dir_count - opp_dir_count)
        scored_timeframes.append(
            {
                "bucket_size": bucket_size,
                "direction_code": direction,
                "state_code": MICRO_EXEC_STATE_WATCH,
                "pattern_code": 0,
                "directional_pressure": directional_pressure,
                "same_dir_count": same_dir_count,
                "opp_dir_count": opp_dir_count,
                "impulse_break_atr": abs(float(net_move_norm)),
                "reclaim_dist_atr": abs(close_now - fib_level_price) / max(atr14_now, 1e-9),
                "orderflow_bias": orderflow_bias,
                "score": score,
                "target_leg_code": 0,
            }
        )

        counter_score = (
            0.45 * counter_tail_pressure
            + 0.30 * counter_tail_move
            + 0.20 * close_side_counter
            + 0.05 * max(opp_dir_count - same_dir_count, 0)
            + (0.20 if level_failed_reclaim else 0.0)
        )
        if level_failed_reclaim:
            counter_state = (
                MICRO_EXEC_STATE_GREEN
                if counter_score >= 0.20 and counter_tail_pressure >= 0.05 and counter_tail_move >= 0.10
                else MICRO_EXEC_STATE_ARMED
                if counter_score >= 0.10
                else MICRO_EXEC_STATE_WATCH
            )
            scored_timeframes.append(
                {
                    "bucket_size": bucket_size,
                    "direction_code": -direction,
                    "state_code": counter_state,
                    "pattern_code": 2,
                    "directional_pressure": counter_tail_pressure,
                    "same_dir_count": same_dir_count,
                    "opp_dir_count": opp_dir_count,
                    "impulse_break_atr": abs(float(counter_tail_move)),
                    "reclaim_dist_atr": abs(close_now - fib_level_price) / max(atr14_now, 1e-9),
                    "orderflow_bias": -1,
                    "score": counter_score,
                    "target_leg_code": micro_counter_target_leg_code(direction, fib_level_touched, fib_level_price, close_now),
                }
            )

    if not scored_timeframes:
        context.target_leg_code = micro_target_leg_code(fib_level_touched, 0)
        return context

    best = max(scored_timeframes, key=lambda row: float(row["score"]))
    aligned_delta = float(best["directional_pressure"])
    same_dir_count = int(best["same_dir_count"])
    opp_dir_count = int(best["opp_dir_count"])
    impulse_break_atr = float(best["impulse_break_atr"])
    reclaim_dist_atr = float(best["reclaim_dist_atr"])
    direction_code = int(best["direction_code"])
    orderflow_bias = int(best["orderflow_bias"])

    state_code = int(best["state_code"])
    if direction_code == direction:
        state_code = MICRO_EXEC_STATE_WATCH
        if aligned_delta >= 0.35 and same_dir_count >= max(2, opp_dir_count + 1):
            state_code = MICRO_EXEC_STATE_GREEN
        elif orderflow_bias == 1:
            state_code = MICRO_EXEC_STATE_ARMED
        elif orderflow_bias == -1 and (opp_dir_count > same_dir_count or aligned_delta <= -0.20):
            state_code = MICRO_EXEC_STATE_INVALIDATED

    if micro_exec_expired(state_code, reclaim_dist_atr, impulse_break_atr):
        state_code = MICRO_EXEC_STATE_EXPIRED

    pattern_code = int(best["pattern_code"])
    if pattern_code == 0 and state_code == MICRO_EXEC_STATE_GREEN:
        if direction == 1 and pocket_code in {236, 382, 500, 618, 786} and low_now <= fib_level_price <= high_now and close_now >= fib_level_price:
            pattern_code = 1
        elif direction == -1 and pocket_code in {382, 500, 618, 786} and low_now <= fib_level_price <= high_now and close_now <= fib_level_price:
            pattern_code = 2
    elif pattern_code == 0 and state_code == MICRO_EXEC_STATE_INVALIDATED:
        if pocket_code in {236, 382, 500}:
            pattern_code = 3
        else:
            pattern_code = 4

    context.tf_code = int(best["bucket_size"])
    context.direction_code = direction_code
    context.state_code = state_code
    context.pattern_code = pattern_code
    context.impulse_break_atr = impulse_break_atr
    context.reclaim_dist_atr = reclaim_dist_atr
    context.orderflow_bias = orderflow_bias
    context.delta_norm = aligned_delta
    context.same_dir_imbalance_ct = same_dir_count
    context.opp_dir_imbalance_ct = opp_dir_count
    if direction_code != direction:
        context.target_leg_code = int(best["target_leg_code"])
    else:
        context.target_leg_code = (
            int(best["target_leg_code"])
            if int(best["target_leg_code"]) != 0
            else micro_target_leg_code(fib_level_touched, pattern_code)
        )
    return context


def outcome_label_for(highest_tp_hit: int, hit_sl: bool, resolved: bool) -> str:
    if not resolved:
        return "CENSORED"
    if highest_tp_hit >= 5:
        return "TP5_HIT"
    if highest_tp_hit == 4:
        return "TP4_HIT"
    if highest_tp_hit == 3:
        return "TP3_HIT"
    if highest_tp_hit == 2:
        return "TP2_HIT"
    if highest_tp_hit == 1:
        return "TP1_ONLY"
    if hit_sl:
        return "STOPPED"
    return "STOPPED"


def build_outcomes(
    interactions: list[InteractionRow],
    bars: list[MesBar],
    observation_window: int,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    if not interactions:
        return outcomes

    for row in interactions:
        i = row.bar_index
        max_idx = min(len(bars) - 1, i + observation_window)
        highest_tp_hit = 0
        bars_to_tp1: int | None = None
        bars_to_sl: int | None = None
        resolved = False
        resolution_idx = max_idx

        for k in range(i + 1, max_idx + 1):
            b = bars[k]
            if row.trade_dir == 1:
                target_hit_now = 5 if b.high >= row.tp5_price else 4 if b.high >= row.tp4_price else 3 if b.high >= row.tp3_price else 2 if b.high >= row.tp2_price else 1 if b.high >= row.tp1_price else 0
                stop_hit = b.low <= row.sl_price
            else:
                target_hit_now = 5 if b.low <= row.tp5_price else 4 if b.low <= row.tp4_price else 3 if b.low <= row.tp3_price else 2 if b.low <= row.tp2_price else 1 if b.low <= row.tp1_price else 0
                stop_hit = b.high >= row.sl_price

            if stop_hit:
                bars_to_sl = k - i
                resolved = True
                resolution_idx = k
                break

            if target_hit_now > highest_tp_hit:
                highest_tp_hit = target_hit_now
                if target_hit_now >= 1 and bars_to_tp1 is None:
                    bars_to_tp1 = k - i
                if target_hit_now == 5:
                    resolved = True
                    resolution_idx = k
                    break

        path_segment = bars[i + 1 : resolution_idx + 1] if i + 1 <= resolution_idx else []
        if not path_segment:
            mae_pts = 0.0
            mfe_pts = 0.0
        elif row.trade_dir == 1:
            mae_pts = max(0.0, row.entry_price - min(b.low for b in path_segment))
            mfe_pts = max(0.0, max(b.high for b in path_segment) - row.entry_price)
        else:
            mae_pts = max(0.0, max(b.high for b in path_segment) - row.entry_price)
            mfe_pts = max(0.0, row.entry_price - min(b.low for b in path_segment))

        hit_sl = bars_to_sl is not None
        tp1_before_sl = highest_tp_hit >= 1 and (bars_to_sl is None or (bars_to_tp1 is not None and bars_to_tp1 < bars_to_sl))
        bars_to_resolution = (resolution_idx - i) if resolved else observation_window

        outcomes.append(
            {
                "highest_tp_hit": highest_tp_hit,
                "hit_tp1": highest_tp_hit >= 1,
                "hit_tp2": highest_tp_hit >= 2,
                "hit_tp3": highest_tp_hit >= 3,
                "hit_tp4": highest_tp_hit >= 4,
                "hit_tp5": highest_tp_hit >= 5,
                "hit_sl": hit_sl,
                "tp1_before_sl": tp1_before_sl,
                "bars_to_tp1": bars_to_tp1,
                "bars_to_sl": bars_to_sl,
                "bars_to_resolution": bars_to_resolution,
                "mae_pts": mae_pts,
                "mfe_pts": mfe_pts,
                "outcome_label": outcome_label_for(highest_tp_hit, hit_sl, resolved),
                "observation_window": observation_window,
            }
        )
    return outcomes


def attach_interaction_ids(outcomes: list[dict[str, Any]], interaction_ids: list[int]) -> list[dict[str, Any]]:
    if len(outcomes) != len(interaction_ids):
        raise ValueError(
            f"Outcome row count ({len(outcomes)}) does not match inserted interaction ids ({len(interaction_ids)})."
        )

    for outcome, interaction_id in zip(outcomes, interaction_ids, strict=True):
        outcome["interaction_id"] = interaction_id
    return outcomes


def truncate_ag_tables(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE ag_fib_outcomes, ag_fib_interactions, ag_fib_snapshots RESTART IDENTITY CASCADE;")
    conn.commit()


def insert_snapshots(conn: psycopg2.extensions.connection, snapshots: list[SnapshotState]) -> None:
    if not snapshots:
        return
    # Multiple pivot confirmations can occur on the same bar-close in edge cases.
    # Keep the latest snapshot per ts to satisfy the PK contract.
    dedup: dict[datetime, SnapshotState] = {}
    for snap in snapshots:
        dedup[snap.ts] = snap
    snapshots = list(dedup.values())
    rows = [
        (
            s.ts,
            s.anchor_high,
            s.anchor_low,
            s.anchor_high_ts,
            s.anchor_low_ts,
            s.fib_range,
            s.fib_bull,
            s.zz_deviation,
            s.zz_depth,
            s.anchor_swing_bars,
            s.anchor_swing_velocity,
            s.time_since_anchor,
            s.atr14,
            s.atr_pct,
        )
        for s in snapshots
    ]
    sql = """
        INSERT INTO ag_fib_snapshots (
            ts, anchor_high, anchor_low, anchor_high_bar_ts, anchor_low_bar_ts,
            fib_range, fib_bull, zz_deviation, zz_depth, anchor_swing_bars,
            anchor_swing_velocity, time_since_anchor, atr14, atr_pct
        ) VALUES %s
        ON CONFLICT (ts) DO UPDATE SET
            anchor_high = EXCLUDED.anchor_high,
            anchor_low = EXCLUDED.anchor_low,
            anchor_high_bar_ts = EXCLUDED.anchor_high_bar_ts,
            anchor_low_bar_ts = EXCLUDED.anchor_low_bar_ts,
            fib_range = EXCLUDED.fib_range,
            fib_bull = EXCLUDED.fib_bull,
            zz_deviation = EXCLUDED.zz_deviation,
            zz_depth = EXCLUDED.zz_depth,
            anchor_swing_bars = EXCLUDED.anchor_swing_bars,
            anchor_swing_velocity = EXCLUDED.anchor_swing_velocity,
            time_since_anchor = EXCLUDED.time_since_anchor,
            atr14 = EXCLUDED.atr14,
            atr_pct = EXCLUDED.atr_pct
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=2000)
    conn.commit()


def insert_interactions(conn: psycopg2.extensions.connection, interactions: list[InteractionRow]) -> list[int]:
    if not interactions:
        return []
    rows = [
        (
            r.ts,
            r.snapshot_ts,
            r.direction,
            r.fib_level_touched,
            r.fib_level_price,
            r.touch_distance_pts,
            r.touch_distance_norm,
            r.interaction_state,
            r.archetype,
            r.entry_price,
            r.sl_price,
            r.tp1_price,
            r.tp2_price,
            r.tp3_price,
            r.tp4_price,
            r.tp5_price,
            r.sl_dist_pts,
            r.sl_dist_atr,
            r.tp1_dist_pts,
            r.rr_to_tp1,
            r.open,
            r.high,
            r.low,
            r.close,
            r.volume,
            r.body_pct,
            r.upper_wick_pct,
            r.lower_wick_pct,
            r.rvol,
            r.rsi14,
            r.ema9,
            r.ema21,
            r.ema50,
            r.ema200,
            r.ema_stacked_bull,
            r.ema_stacked_bear,
            r.ema9_dist_pct,
            r.macd_hist,
            r.adx,
            r.energy,
            r.confluence_quality,
            r.ml_exec_tf_code,
            r.ml_exec_direction_code,
            r.ml_exec_state_code,
            r.ml_exec_pattern_code,
            r.ml_exec_pocket_code,
            r.ml_exec_impulse_break_atr,
            r.ml_exec_reclaim_dist_atr,
            r.ml_exec_orderflow_bias,
            r.ml_exec_delta_norm,
            r.ml_exec_absorption,
            r.ml_exec_zero_print,
            r.ml_exec_same_dir_imbalance_ct,
            r.ml_exec_opp_dir_imbalance_ct,
            r.ml_exec_target_leg_code,
        )
        for r in interactions
    ]
    sql = """
        INSERT INTO ag_fib_interactions (
            ts, snapshot_ts, direction, fib_level_touched, fib_level_price,
            touch_distance_pts, touch_distance_norm, interaction_state, archetype,
            entry_price, sl_price, tp1_price, tp2_price, tp3_price, tp4_price, tp5_price,
            sl_dist_pts, sl_dist_atr, tp1_dist_pts, rr_to_tp1,
            open, high, low, close, volume, body_pct, upper_wick_pct, lower_wick_pct,
            rvol, rsi14, ema9, ema21, ema50, ema200, ema_stacked_bull, ema_stacked_bear,
            ema9_dist_pct, macd_hist, adx, energy, confluence_quality,
            ml_exec_tf_code, ml_exec_direction_code, ml_exec_state_code, ml_exec_pattern_code, ml_exec_pocket_code,
            ml_exec_impulse_break_atr, ml_exec_reclaim_dist_atr, ml_exec_orderflow_bias, ml_exec_delta_norm,
            ml_exec_absorption, ml_exec_zero_print, ml_exec_same_dir_imbalance_ct,
            ml_exec_opp_dir_imbalance_ct, ml_exec_target_leg_code
        ) VALUES %s
        RETURNING id
    """
    ids: list[int] = []
    with conn.cursor() as cur:
        for start in range(0, len(rows), 2000):
            batch = rows[start : start + 2000]
            execute_values(cur, sql, batch, page_size=2000)
            ids.extend([row[0] for row in cur.fetchall()])
    conn.commit()
    return ids


def insert_outcomes(conn: psycopg2.extensions.connection, outcomes: list[dict[str, Any]]) -> None:
    if not outcomes:
        return
    rows = [
        (
            o["interaction_id"],
            o["highest_tp_hit"],
            o["hit_tp1"],
            o["hit_tp2"],
            o["hit_tp3"],
            o["hit_tp4"],
            o["hit_tp5"],
            o["hit_sl"],
            o["tp1_before_sl"],
            o["bars_to_tp1"],
            o["bars_to_sl"],
            o["bars_to_resolution"],
            o["mae_pts"],
            o["mfe_pts"],
            o["outcome_label"],
            o["observation_window"],
        )
        for o in outcomes
    ]
    sql = """
        INSERT INTO ag_fib_outcomes (
            interaction_id, highest_tp_hit, hit_tp1, hit_tp2, hit_tp3, hit_tp4, hit_tp5,
            hit_sl, tp1_before_sl, bars_to_tp1, bars_to_sl, bars_to_resolution,
            mae_pts, mfe_pts, outcome_label, observation_window
        ) VALUES %s
        ON CONFLICT (interaction_id) DO UPDATE SET
            highest_tp_hit = EXCLUDED.highest_tp_hit,
            hit_tp1 = EXCLUDED.hit_tp1,
            hit_tp2 = EXCLUDED.hit_tp2,
            hit_tp3 = EXCLUDED.hit_tp3,
            hit_tp4 = EXCLUDED.hit_tp4,
            hit_tp5 = EXCLUDED.hit_tp5,
            hit_sl = EXCLUDED.hit_sl,
            tp1_before_sl = EXCLUDED.tp1_before_sl,
            bars_to_tp1 = EXCLUDED.bars_to_tp1,
            bars_to_sl = EXCLUDED.bars_to_sl,
            bars_to_resolution = EXCLUDED.bars_to_resolution,
            mae_pts = EXCLUDED.mae_pts,
            mfe_pts = EXCLUDED.mfe_pts,
            outcome_label = EXCLUDED.outcome_label,
            observation_window = EXCLUDED.observation_window
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=2000)
    conn.commit()


def refresh_ag_training_view(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute(AG_TRAINING_VIEW_SQL)
    conn.commit()


def session_date_chicago(ts: datetime) -> str:
    return ts.astimezone(CHICAGO_TZ).date().isoformat()


def fetch_ag_training_rows(conn: psycopg2.extensions.connection) -> list[dict[str, Any]]:
    sql = "SELECT * FROM ag_training ORDER BY ts ASC"
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_walk_forward_structure(
    conn: psycopg2.extensions.connection,
    output_root: Path,
    train_ratio: float,
    val_ratio: float,
    session_embargo: int,
) -> dict[str, Any]:
    rows = fetch_ag_training_rows(conn)
    if not rows:
        return {"status": "empty", "message": "ag_training has no rows"}

    for row in rows:
        row["session_date_ct"] = session_date_chicago(row["ts"])

    sessions = sorted({row["session_date_ct"] for row in rows})
    if len(sessions) < 10:
        return {
            "status": "insufficient_sessions",
            "message": f"Need >=10 sessions for stable split structure; found {len(sessions)}",
        }

    train_end_ix = max(1, int(len(sessions) * train_ratio) - 1)
    val_start_ix = min(len(sessions) - 1, train_end_ix + 1 + session_embargo)
    val_end_ix = max(val_start_ix, int(len(sessions) * (train_ratio + val_ratio)) - 1)
    test_start_ix = min(len(sessions) - 1, val_end_ix + 1 + session_embargo)

    train_sessions = set(sessions[: train_end_ix + 1])
    val_sessions = set(sessions[val_start_ix : val_end_ix + 1])
    test_sessions = set(sessions[test_start_ix:])

    train_rows = [row for row in rows if row["session_date_ct"] in train_sessions]
    val_rows = [row for row in rows if row["session_date_ct"] in val_sessions]
    test_rows = [row for row in rows if row["session_date_ct"] in test_sessions]

    run_id = datetime.now(UTC).strftime("agfit_%Y%m%dT%H%M%SZ")
    out_dir = output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    fieldnames = list(rows[0].keys())
    write_csv(out_dir / "train.csv", train_rows, fieldnames)
    write_csv(out_dir / "val.csv", val_rows, fieldnames)
    write_csv(out_dir / "test.csv", test_rows, fieldnames)

    label_counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get("outcome_label", "UNKNOWN"))
        label_counts[label] = label_counts.get(label, 0) + 1

    manifest = {
        "run_id": run_id,
        "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "rows_total": len(rows),
        "sessions_total": len(sessions),
        "split": {
            "train_rows": len(train_rows),
            "val_rows": len(val_rows),
            "test_rows": len(test_rows),
            "session_embargo": session_embargo,
            "train_session_start": sessions[0],
            "train_session_end": sessions[train_end_ix],
            "val_session_start": sessions[val_start_ix] if val_sessions else None,
            "val_session_end": sessions[val_end_ix] if val_sessions else None,
            "test_session_start": sessions[test_start_ix] if test_sessions else None,
            "test_session_end": sessions[-1] if test_sessions else None,
        },
        "label_distribution": label_counts,
        "files": {
            "train": str(out_dir / "train.csv"),
            "val": str(out_dir / "val.csv"),
            "test": str(out_dir / "test.csv"),
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def summarize_outcomes(outcomes: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in outcomes:
        label = row["outcome_label"]
        out[label] = out.get(label, 0) + 1
    return out


def main() -> None:
    args = parse_args()
    output_root = Path(args.splits_output)

    with psycopg2.connect(args.dsn) as conn:
        conn.autocommit = False

        if not args.skip_populate:
            bars = fetch_mes_15m_rows(conn, args.start_ts, args.end_ts)
            if not bars:
                raise SystemExit("No mes_15m rows found for the requested window.")
            micro_bars = fetch_mes_1m_rows(conn, args.start_ts, args.end_ts)

            indicators = calc_indicators(bars)
            snapshots, interactions = build_snapshots_and_interactions(
                bars=bars,
                ind=indicators,
                micro_bars=micro_bars,
                touch_tol_pts=args.touch_tol_pts,
            )
            outcomes = build_outcomes(
                interactions=interactions,
                bars=bars,
                observation_window=args.observation_window,
            )

            if not args.append:
                truncate_ag_tables(conn)
            insert_snapshots(conn, snapshots)
            interaction_ids = insert_interactions(conn, interactions)
            outcomes = attach_interaction_ids(outcomes, interaction_ids)
            insert_outcomes(conn, outcomes)
            refresh_ag_training_view(conn)

            print(
                json.dumps(
                    {
                        "populate": {
                            "bars_loaded": len(bars),
                            "micro_bars_loaded": len(micro_bars),
                            "snapshots_written": len(snapshots),
                            "interactions_written": len(interactions),
                            "outcomes_written": len(outcomes),
                            "outcome_labels": summarize_outcomes(outcomes),
                        }
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            refresh_ag_training_view(conn)

        manifest = build_walk_forward_structure(
            conn=conn,
            output_root=output_root,
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
            session_embargo=args.session_embargo,
        )
        print(json.dumps({"split_manifest": manifest}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

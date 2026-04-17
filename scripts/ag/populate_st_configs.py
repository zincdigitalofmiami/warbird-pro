#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from itertools import product
from typing import Sequence

import psycopg2
from psycopg2.extras import execute_values


DEFAULT_DSN = os.environ.get("WARBIRD_PG_DSN", "host=127.0.0.1 port=5432 dbname=warbird")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Populate v8 SuperTrend config grids (st_flip_configs, st_tp_configs).",
    )
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="Local PG17 DSN for warbird.")
    return parser.parse_args()


def build_flip_rows() -> list[tuple[int, float, str, str, float]]:
    atr_periods = [7, 10, 14, 21]
    atr_mults = [2.0, 2.5, 3.0, 3.5, 4.0]
    atr_methods = ["atr", "sma_tr"]
    source_ids = ["hl2", "close", "ohlc4"]
    sl_atr_mults = [0.62, 0.80, 1.00, 1.20]
    rows = list(product(atr_periods, atr_mults, atr_methods, source_ids, sl_atr_mults))
    assert len(rows) == 480, f"Expected 480 flip grid rows, got {len(rows)}"
    return rows


def build_tp_rows() -> list[tuple[str, float, float, float, float, float, float]]:
    tp_modes = ["fixed", "dynamic"]
    tqi_influences = [0.2, 0.4, 0.6, 0.8]
    vol_influences = [0.2, 0.4, 0.6, 0.8]
    min_tp_scales = [0.5, 0.7, 1.0]
    max_tp_scales = [1.5, 2.0, 3.0]
    tp1_floor_rs = [0.5, 0.75, 1.0]
    tp3_ceil_rs = [4.0, 6.0, 8.0]
    rows = list(
        product(
            tp_modes,
            tqi_influences,
            vol_influences,
            min_tp_scales,
            max_tp_scales,
            tp1_floor_rs,
            tp3_ceil_rs,
        )
    )
    assert len(rows) == 2592, f"Expected 2592 TP grid rows, got {len(rows)}"
    return rows


def insert_flip_rows(cur: psycopg2.extensions.cursor, rows: Sequence[tuple[int, float, str, str, float]]) -> None:
    execute_values(
        cur,
        """
        INSERT INTO st_flip_configs (
            atr_period,
            atr_mult,
            atr_method,
            source_id,
            sl_atr_mult
        ) VALUES %s
        ON CONFLICT (atr_period, atr_mult, atr_method, source_id, sl_atr_mult)
        DO NOTHING
        """,
        rows,
        template="(%s, %s, %s, %s, %s)",
        page_size=500,
    )


def insert_tp_rows(cur: psycopg2.extensions.cursor, rows: Sequence[tuple[str, float, float, float, float, float, float]]) -> None:
    execute_values(
        cur,
        """
        INSERT INTO st_tp_configs (
            tp_mode,
            tqi_influence,
            vol_influence,
            min_tp_scale,
            max_tp_scale,
            tp1_floor_r,
            tp3_ceil_r
        ) VALUES %s
        ON CONFLICT (tp_mode, tqi_influence, vol_influence, min_tp_scale, max_tp_scale, tp1_floor_r, tp3_ceil_r)
        DO NOTHING
        """,
        rows,
        template="(%s, %s, %s, %s, %s, %s, %s)",
        page_size=500,
    )


def fetch_scalar(cur: psycopg2.extensions.cursor, sql: str) -> int:
    cur.execute(sql)
    return int(cur.fetchone()[0])


def main() -> None:
    args = parse_args()
    flip_rows = build_flip_rows()
    tp_rows = build_tp_rows()

    with psycopg2.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            insert_flip_rows(cur, flip_rows)
            insert_tp_rows(cur, tp_rows)

            flip_count = fetch_scalar(cur, "SELECT COUNT(*) FROM st_flip_configs")
            tp_count = fetch_scalar(cur, "SELECT COUNT(*) FROM st_tp_configs")
            fib_0618_count = fetch_scalar(cur, "SELECT COUNT(*) FROM st_flip_configs WHERE source_id = 'fib_0618'")
            flip_dupes = fetch_scalar(
                cur,
                """
                SELECT COUNT(*) FROM (
                    SELECT 1
                    FROM st_flip_configs
                    GROUP BY atr_period, atr_mult, atr_method, source_id, sl_atr_mult
                    HAVING COUNT(*) > 1
                ) d
                """,
            )
            tp_dupes = fetch_scalar(
                cur,
                """
                SELECT COUNT(*) FROM (
                    SELECT 1
                    FROM st_tp_configs
                    GROUP BY tp_mode, tqi_influence, vol_influence, min_tp_scale, max_tp_scale, tp1_floor_r, tp3_ceil_r
                    HAVING COUNT(*) > 1
                ) d
                """,
            )

    assert flip_count == 480, f"Expected 480 flip configs, got {flip_count}"
    assert tp_count == 2592, f"Expected 2592 TP configs, got {tp_count}"
    assert fib_0618_count == 0, f"Expected source_id='fib_0618' to be absent, found {fib_0618_count}"
    assert flip_dupes == 0, f"Expected 0 duplicate flip rows, found {flip_dupes}"
    assert tp_dupes == 0, f"Expected 0 duplicate TP rows, found {tp_dupes}"

    print(f"flip_cfg count={flip_count}, tp_cfg count={tp_count}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Parse TradingView strategy-tester trade-list CSVs and compute PF / WR / DD metrics.

Usage:
    python scripts/sats/parse_trade_csv.py <csv_path> [csv_path2 ...]
    python scripts/sats/parse_trade_csv.py data/sats_ps_baselines/crypto.csv
"""

import sys
import csv
import json
from pathlib import Path
from collections import defaultdict


def parse_tv_trade_csv(path: str | Path) -> dict:
    """
    Parse a TradingView strategy-tester trade-list CSV (one row per entry or exit).
    TV exports paired rows: entry row then exit row (or vice-versa) for each trade.
    Each row contains a 'Net P&L USD' column on the EXIT row; entry rows have the
    same value mirrored. We identify the exit row by 'Type' starting with 'Exit'.
    """
    path = Path(path)
    trades = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trade_type = row.get("Type", "").strip()
            if not trade_type.lower().startswith("exit"):
                continue
            pnl_str = row.get("Net P&L USD", "").replace(",", "").strip()
            if not pnl_str:
                continue
            try:
                pnl = float(pnl_str)
            except ValueError:
                continue

            direction = "long" if "long" in trade_type.lower() else "short"
            date_str = row.get("Date and time", "").strip()
            month = date_str[:7] if date_str else "unknown"

            fav_str = row.get("Favorable excursion USD", "").replace(",", "").strip()
            adv_str = row.get("Adverse excursion USD", "").replace(",", "").strip()
            try:
                fav = float(fav_str)
            except ValueError:
                fav = float("nan")
            try:
                adv = float(adv_str)
            except ValueError:
                adv = float("nan")

            cum_str = row.get("Cumulative P&L USD", "").replace(",", "").strip()
            try:
                cum = float(cum_str)
            except ValueError:
                cum = float("nan")

            trades.append({
                "pnl": pnl,
                "direction": direction,
                "month": month,
                "fav": fav,
                "adv": adv,
                "cum": cum,
            })

    if not trades:
        return {"error": f"No exit-row trades found in {path}"}

    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net_pnl = gross_profit - gross_loss
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    win_rate = len(wins) / len(trades) * 100

    # Max drawdown from equity curve (cumulative P&L column)
    cum_values = [t["cum"] for t in trades if t["cum"] == t["cum"]]
    if cum_values:
        peak = cum_values[0]
        max_dd = 0.0
        for c in cum_values:
            if c > peak:
                peak = c
            dd = peak - c
            if dd > max_dd:
                max_dd = dd
    else:
        max_dd = float("nan")

    # By-month P&L
    monthly = defaultdict(float)
    for t in trades:
        monthly[t["month"]] += t["pnl"]
    monthly_sorted = dict(sorted(monthly.items()))

    longs = [t for t in trades if t["direction"] == "long"]
    shorts = [t for t in trades if t["direction"] == "short"]

    def side_pf(side_trades):
        g = sum(t["pnl"] for t in side_trades if t["pnl"] > 0)
        l = abs(sum(t["pnl"] for t in side_trades if t["pnl"] <= 0))
        return g / l if l > 0 else float("inf")

    return {
        "file": str(path),
        "trades": len(trades),
        "net_pnl": round(net_pnl, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(pf, 4),
        "win_rate_pct": round(win_rate, 2),
        "max_drawdown": round(max_dd, 2),
        "avg_win": round(gross_profit / len(wins), 2) if wins else 0,
        "avg_loss": round(gross_loss / len(losses), 2) if losses else 0,
        "long_trades": len(longs),
        "short_trades": len(shorts),
        "long_pf": round(side_pf(longs), 4),
        "short_pf": round(side_pf(shorts), 4),
        "monthly_pnl": monthly_sorted,
    }


def print_report(metrics: dict) -> None:
    if "error" in metrics:
        print(f"ERROR: {metrics['error']}")
        return
    m = metrics
    print(f"\n{'='*60}")
    print(f"File:          {m['file']}")
    print(f"Trades:        {m['trades']}")
    print(f"Net P&L:       ${m['net_pnl']:,.2f}")
    print(f"Gross Profit:  ${m['gross_profit']:,.2f}")
    print(f"Gross Loss:    ${m['gross_loss']:,.2f}")
    print(f"Profit Factor: {m['profit_factor']:.4f}  ← primary target")
    print(f"Win Rate:      {m['win_rate_pct']:.2f}%")
    print(f"Max Drawdown:  ${m['max_drawdown']:,.2f}")
    print(f"Avg Win:       ${m['avg_win']:,.2f}")
    print(f"Avg Loss:      ${m['avg_loss']:,.2f}")
    print(f"Longs:         {m['long_trades']} (PF {m['long_pf']:.4f})")
    print(f"Shorts:        {m['short_trades']} (PF {m['short_pf']:.4f})")
    if m.get("monthly_pnl"):
        print("\nMonthly P&L:")
        for mo, pnl in m["monthly_pnl"].items():
            bar = "+" if pnl >= 0 else ""
            print(f"  {mo}: {bar}${pnl:,.2f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    results = []
    for path in sys.argv[1:]:
        metrics = parse_tv_trade_csv(path)
        print_report(metrics)
        results.append(metrics)

    if len(results) > 1:
        print("\nSummary comparison:")
        header = f"{'File':<40} {'Trades':>7} {'Net P&L':>10} {'PF':>7} {'WR%':>6} {'Max DD':>9}"
        print(header)
        print("-" * len(header))
        for m in results:
            name = Path(m["file"]).stem[:40]
            print(f"{name:<40} {m['trades']:>7} ${m['net_pnl']:>9,.2f} {m['profit_factor']:>7.4f} {m['win_rate_pct']:>6.2f}% ${m['max_drawdown']:>8,.2f}")

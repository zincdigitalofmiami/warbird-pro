#!/usr/bin/env python3
"""
Backfill GPR (Geopolitical Risk) data from Caldara-Iacoviello XLS.
Writes two series to geopolitical_risk_1d: gpr_acts and gpr_threats.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import openpyxl
from supabase import create_client

def main() -> None:
    xls_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/gpr_web.xls")
    if not xls_path.exists():
        print(f"ERROR: {xls_path} not found. Download from matteoiacoviello.com/gpr.htm")
        sys.exit(1)

    sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    supabase = create_client(sb_url, sb_key)

    # openpyxl handles both .xls (via xlrd fallback) and .xlsx
    # If .xls format, use xlrd:
    try:
        import xlrd
        book = xlrd.open_workbook(str(xls_path))
        sheet = book.sheet_by_index(0)
        headers = [sheet.cell_value(0, c) for c in range(sheet.ncols)]
        rows_raw = [
            {headers[c]: sheet.cell_value(r, c) for c in range(sheet.ncols)}
            for r in range(1, sheet.nrows)
        ]
    except ImportError:
        wb = openpyxl.load_workbook(str(xls_path))
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        rows_raw = [
            {headers[i]: row[i].value for i in range(len(headers))}
            for row in ws.iter_rows(min_row=2)
        ]

    # Map column names (may vary by version): date, GPRACT, GPRTHREAT
    date_col = next((h for h in headers if h and "date" in str(h).lower()), None)
    acts_col = next((h for h in headers if h and "ACT" in str(h).upper()), None)
    threat_col = next((h for h in headers if h and "THREAT" in str(h).upper()), None)

    if not date_col:
        print(f"ERROR: can't find date column. Headers: {headers}")
        sys.exit(1)

    rows_acts = []
    rows_threats = []
    for raw in rows_raw:
        date_val = raw.get(date_col)
        if not date_val:
            continue
        # date may be a float (Excel serial) or string
        if isinstance(date_val, float):
            import datetime
            date_str = (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(date_val))).isoformat()
        else:
            date_str = str(date_val)[:10]

        ts = date_str + "T00:00:00Z"

        if acts_col and raw.get(acts_col) is not None:
            rows_acts.append({"ts": ts, "series_id": "gpr_acts", "value": float(raw[acts_col])})
        if threat_col and raw.get(threat_col) is not None:
            rows_threats.append({"ts": ts, "series_id": "gpr_threats", "value": float(raw[threat_col])})

    all_rows = rows_acts + rows_threats
    print(f"Upserting {len(all_rows)} GPR rows...")

    for i in range(0, len(all_rows), 500):
        chunk = all_rows[i:i + 500]
        supabase.table("geopolitical_risk_1d").upsert(chunk, on_conflict="ts,series_id").execute()

    print(f"Done. {len(rows_acts)} gpr_acts, {len(rows_threats)} gpr_threats.")

if __name__ == "__main__":
    main()

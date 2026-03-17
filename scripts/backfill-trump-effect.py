#!/usr/bin/env python3
"""
Backfill trump_effect_1d from Federal Register API (free, no key needed).
Fetches all executive orders and presidential memoranda from Jan 20, 2025 onward.
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta

import requests
from supabase import create_client

FR_API = "https://www.federalregister.gov/api/v1/documents.json"


def main() -> None:
    sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    supabase = create_client(sb_url, sb_key)

    start_date = date(2025, 1, 20)  # Trump 2 inauguration
    end_date = date.today()

    total_rows = 0

    # Chunk by month to avoid API limits
    chunk_start = start_date
    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=30), end_date)
        print(f"  {chunk_start} → {chunk_end}...", end=" ", flush=True)

        rows = []
        for doc_type in ["executive_order", "memorandum", "proclamation"]:
            params = {
                "per_page": 100,
                "order": "newest",
                "fields[]": ["title", "abstract", "publication_date", "html_url"],
                "conditions[publication_date][gte]": chunk_start.isoformat(),
                "conditions[publication_date][lte]": chunk_end.isoformat(),
                "conditions[presidential_document_type][]": doc_type,
            }

            try:
                resp = requests.get(FR_API, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])

                for doc in results:
                    if not doc.get("title") or not doc.get("publication_date"):
                        continue
                    rows.append({
                        "ts": f"{doc['publication_date']}T00:00:00Z",
                        "event_type": doc_type,
                        "title": doc["title"][:500],
                        "summary": (doc.get("abstract") or "")[:1000] or None,
                        "source": "federal_register",
                        "source_url": doc.get("html_url"),
                    })
            except Exception as exc:
                print(f"ERROR ({doc_type}): {exc}")

            time.sleep(0.5)  # Rate limit courtesy

        # Dedup by title + ts before insert
        inserted = 0
        for row in rows:
            existing = (
                supabase.table("trump_effect_1d")
                .select("id")
                .eq("ts", row["ts"])
                .eq("title", row["title"])
                .limit(1)
                .execute()
            )
            if not existing.data:
                supabase.table("trump_effect_1d").insert(row).execute()
                inserted += 1

        print(f"{inserted} new / {len(rows)} found")
        total_rows += inserted
        chunk_start = chunk_end + timedelta(days=1)

    print(f"Done. {total_rows} rows inserted to trump_effect_1d.")


if __name__ == "__main__":
    main()

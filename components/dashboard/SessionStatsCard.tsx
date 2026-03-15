"use client";

import { useEffect, useState } from "react";

interface SessionData {
  pivotPP: number | null;
  pivotR1: number | null;
  pivotS1: number | null;
  pivotR2: number | null;
  pivotS2: number | null;
}

export default function SessionStatsCard() {
  const [data, setData] = useState<SessionData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const res = await fetch("/api/pivots/mes");
        const json = await res.json();
        const pivots = json.pivots ?? [];

        const find = (label: string) => {
          const p = pivots.find((pv: { label: string }) => pv.label === label);
          return p ? p.price : null;
        };

        setData({
          pivotPP: find("D PP"),
          pivotR1: find("D R1"),
          pivotS1: find("D S1"),
          pivotR2: find("D R2"),
          pivotS2: find("D S2"),
        });
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  return (
    <div
      className="rounded-lg p-5"
      style={{
        background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <div className="text-white/40 text-xs font-medium mb-3 uppercase tracking-wider">
        Daily Pivots
      </div>
      {loading ? (
        <span className="text-white/20 text-xs">Loading...</span>
      ) : !data || !data.pivotPP ? (
        <span className="text-white/20 text-xs">No pivot data</span>
      ) : (
        <div className="grid grid-cols-5 gap-2 text-center">
          <PivotCell label="S2" value={data.pivotS2} color="#FF0000" />
          <PivotCell label="S1" value={data.pivotS1} color="#ef5350" />
          <PivotCell label="PP" value={data.pivotPP} color="#ffffff" />
          <PivotCell label="R1" value={data.pivotR1} color="#26C6DA" />
          <PivotCell label="R2" value={data.pivotR2} color="#4CAF50" />
        </div>
      )}
    </div>
  );
}

function PivotCell({ label, value, color }: { label: string; value: number | null; color: string }) {
  return (
    <div>
      <div className="text-xs mb-1" style={{ color, opacity: 0.6 }}>{label}</div>
      <div className="text-xs text-white/70 font-medium tabular-nums">
        {value ? value.toFixed(2) : "—"}
      </div>
    </div>
  );
}

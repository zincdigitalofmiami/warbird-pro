"use client";

import { useEffect, useState } from "react";

interface SetupCounts {
  touched: number;
  hooked: number;
  goFired: number;
  tp1Hit: number;
  stopped: number;
  expired: number;
  measuredMoves: number;
}

export default function ActiveSetupsCard() {
  const [counts, setCounts] = useState<SetupCounts | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const res = await fetch("/api/setups");
        const json = await res.json();

        const active = json.active ?? [];
        const recent = json.recent ?? [];
        const mm = json.measuredMoves ?? [];

        setCounts({
          touched: active.filter((s: { phase: string }) => s.phase === "TOUCHED").length,
          hooked: active.filter((s: { phase: string }) => s.phase === "HOOKED").length,
          goFired: active.filter((s: { phase: string }) => s.phase === "GO_FIRED").length,
          tp1Hit: [...active, ...recent].filter((s: { phase: string }) => s.phase === "TP1_HIT").length,
          stopped: recent.filter((s: { phase: string }) => s.phase === "STOPPED").length,
          expired: recent.filter((s: { phase: string }) => s.phase === "EXPIRED").length,
          measuredMoves: mm.length,
        });
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    }
    fetchData();
    const interval = setInterval(fetchData, 60_000);
    return () => clearInterval(interval);
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
        Active Setups
      </div>
      {loading ? (
        <span className="text-white/20 text-xs">Loading...</span>
      ) : !counts ? (
        <span className="text-white/20 text-xs">No data</span>
      ) : (
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <div className="flex gap-4">
              <PhaseTag label="Touch" count={counts.touched} color="#ffb464" />
              <PhaseTag label="Hook" count={counts.hooked} color="#26C6DA" />
              <PhaseTag label="Go" count={counts.goFired} color="#4CAF50" />
            </div>
          </div>
          <div className="flex gap-4 text-xs text-white/30 pt-2" style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
            <span>TP1 <span className="text-white/50">{counts.tp1Hit}</span></span>
            <span>Stopped <span className="text-white/50">{counts.stopped}</span></span>
            <span>Expired <span className="text-white/50">{counts.expired}</span></span>
            <span>MM <span className="text-white/50">{counts.measuredMoves}</span></span>
          </div>
        </div>
      )}
    </div>
  );
}

function PhaseTag({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-2 h-2 rounded-full" style={{ background: color, opacity: count > 0 ? 1 : 0.2 }} />
      <span className="text-xs text-white/50">{label}</span>
      <span className="text-xs font-medium text-white/80 tabular-nums">{count}</span>
    </div>
  );
}

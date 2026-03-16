"use client";

import { useEffect, useState } from "react";

interface SetupCounts {
  active: number;
  runners: number;
  counterTrend: number;
  tp1Hit: number;
  tp2Hit: number;
  stopped: number;
  expired: number;
  pullbackReversal: number;
}

export default function ActiveSetupsCard() {
  const [counts, setCounts] = useState<SetupCounts | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const historyRes = await fetch("/api/warbird/history?days=7&limit=100");
        const signalRes = await fetch("/api/warbird/signal");
        const history = await historyRes.json();
        const signal = await signalRes.json();
        const active = (history.setups ?? []).filter((s: { status: string }) =>
          ["ACTIVE", "RUNNER_ACTIVE", "TP1_HIT"].includes(s.status),
        );
        const recent = history.events ?? [];
        const currentSignalSetup = signal.setup;

        setCounts({
          active: active.filter((s: { status: string }) => s.status === "ACTIVE").length,
          runners: active.filter((s: { status: string }) => s.status === "RUNNER_ACTIVE").length,
          counterTrend: active.filter((s: { counter_trend: boolean }) => s.counter_trend).length,
          tp1Hit: recent.filter((e: { event_type: string }) => e.event_type === "TP1_HIT").length,
          tp2Hit: recent.filter((e: { event_type: string }) => e.event_type === "TP2_HIT").length,
          stopped: recent.filter((e: { event_type: string }) => e.event_type === "STOPPED").length,
          expired: recent.filter((e: { event_type: string }) => e.event_type === "EXPIRED").length,
          pullbackReversal:
            recent.filter((e: { event_type: string }) => e.event_type === "PULLBACK_REVERSAL").length +
            (currentSignalSetup?.status === "PULLBACK_REVERSAL" ? 1 : 0),
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
              <PhaseTag label="Active" count={counts.active} color="#4CAF50" />
              <PhaseTag label="Runner" count={counts.runners} color="#26C6DA" />
              <PhaseTag label="Counter" count={counts.counterTrend} color="#ffb464" />
            </div>
          </div>
          <div className="flex gap-4 text-xs text-white/30 pt-2" style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
            <span>TP1 <span className="text-white/50">{counts.tp1Hit}</span></span>
            <span>TP2 <span className="text-white/50">{counts.tp2Hit}</span></span>
            <span>Stopped <span className="text-white/50">{counts.stopped}</span></span>
            <span>Expired <span className="text-white/50">{counts.expired}</span></span>
            <span>Reversal <span className="text-white/50">{counts.pullbackReversal}</span></span>
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

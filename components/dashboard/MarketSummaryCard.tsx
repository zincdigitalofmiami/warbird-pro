"use client";

import { useEffect, useState } from "react";

interface MarketData {
  price: number;
  change: number;
  changePercent: number;
  high: number;
  low: number;
  ts: string;
}

export default function MarketSummaryCard() {
  const [data, setData] = useState<MarketData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const res = await fetch("/api/live/mes15m/summary", { cache: "no-store" });
        const json = await res.json();
        if (json.summary) {
          setData(json.summary);
        }
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

  if (loading) {
    return <CardShell title="MES Market"><span className="text-white/20 text-xs">Loading...</span></CardShell>;
  }

  if (!data) {
    return <CardShell title="MES Market"><span className="text-white/20 text-xs">No data</span></CardShell>;
  }

  const isPositive = data.change >= 0;
  const color = isPositive ? "#26C6DA" : "#FF0000";

  return (
    <CardShell title="MES Market">
      <div className="flex items-baseline gap-3 mb-3">
        <span className="text-white text-2xl font-semibold tabular-nums">
          {data.price.toFixed(2)}
        </span>
        <span className="text-sm font-medium tabular-nums" style={{ color }}>
          {isPositive ? "+" : ""}{data.change.toFixed(2)} ({isPositive ? "+" : ""}{data.changePercent.toFixed(2)}%)
        </span>
      </div>
      <div className="flex gap-6 text-xs text-white/30">
        <span>H <span className="text-white/60 tabular-nums">{data.high.toFixed(2)}</span></span>
        <span>L <span className="text-white/60 tabular-nums">{data.low.toFixed(2)}</span></span>
        <span>R <span className="text-white/60 tabular-nums">{(data.high - data.low).toFixed(2)}</span></span>
      </div>
    </CardShell>
  );
}

function CardShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="rounded-lg p-5"
      style={{
        background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <div className="text-white/40 text-xs font-medium mb-3 uppercase tracking-wider">{title}</div>
      {children}
    </div>
  );
}

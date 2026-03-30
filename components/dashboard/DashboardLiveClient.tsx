"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import CorrelationsRow from "@/components/dashboard/CorrelationsRow";
import DataTablesPanel from "@/components/dashboard/DataTablesPanel";
import { fromWarbirdSetup, type SetupCandidate } from "@/lib/setup-candidates";
import type { WarbirdSignal, WarbirdSetupEventRow, WarbirdSetupRow } from "@/lib/warbird/types";

// bundle-dynamic-imports: heavy chart component loaded client-side only
const LiveMesChart = dynamic(
  () => import("@/components/charts/LiveMesChart"),
  { ssr: false },
);

interface DashboardSetupCounts {
  active: number;
  counterTrend: number;
  tp1Hit: number;
  tp2Hit: number;
  stopped: number;
  open: number;
}

interface SignalEvent {
  signal_event_id: string;
  signal_id: string;
  ts: string;
  event_type: string;
  price: number | null;
  note: string | null;
}

interface DashboardPayload {
  signal: WarbirdSignal | null;
  setups: WarbirdSetupRow[];
  events: WarbirdSetupEventRow[];
  signalEvents: SignalEvent[];
  correlations: Record<string, { close: number; prevClose: number }>;
  counts: DashboardSetupCounts;
  generatedAt: string;
}

export default function DashboardLiveClient() {
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        // Cache busting: cacheComponents=true in next.config, so add cb param
        const response = await fetch(
          `/api/warbird/dashboard?days=7&limit=100&cb=${Date.now()}`,
          { cache: "no-store" },
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const json = (await response.json()) as DashboardPayload;
        if (!cancelled) {
          setData(json);
        }
      } catch {
        if (!cancelled) {
          setData(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void fetchData();
    const interval = setInterval(fetchData, 60_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const setups = useMemo<SetupCandidate[]>(() => {
    return (data?.setups ?? []).slice(0, 4).map((setup) => fromWarbirdSetup(setup));
  }, [data?.setups]);

  return (
    <div className="flex flex-col w-full h-full" style={{ background: "#131722" }}>
      {/* Top: Correlations Row */}
      <CorrelationsRow correlations={data?.correlations ?? null} />

      {/* Middle: Chart (full width) */}
      <div className="flex flex-1 min-h-0">
        <div className="flex-1 min-w-0 min-h-0">
          <LiveMesChart signal={data?.signal ?? null} setups={setups} />
        </div>
      </div>

      {/* Bottom: Data Tables */}
      <DataTablesPanel
        signal={data?.signal ?? null}
        setups={data?.setups ?? []}
      />
    </div>
  );
}

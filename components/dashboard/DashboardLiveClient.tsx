"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import CorrelationsRow from "@/components/dashboard/CorrelationsRow";
import DataTablesPanel from "@/components/dashboard/DataTablesPanel";
import { fromWarbirdSetup, type SetupCandidate } from "@/lib/setup-candidates";
import type {
  WarbirdRuntimeState,
  WarbirdSignal,
  WarbirdSetupEventRow,
  WarbirdSetupRow,
} from "@/lib/warbird/types";

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
  runtime: WarbirdRuntimeState;
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
      {data?.runtime.active ? (
        <div
          className="px-4 py-3 text-[11px] leading-5"
          style={{
            background: "rgba(242, 54, 69, 0.12)",
            borderBottom: "1px solid rgba(242, 54, 69, 0.28)",
            color: "rgba(255,255,255,0.82)",
          }}
        >
          <div className="font-semibold uppercase tracking-[0.18em] text-[10px] text-red-300">
            Warbird Runtime Degraded
          </div>
          <div className="mt-1 text-white/75">
            {data.runtime.reason ??
              "Legacy Warbird reader health could not be proven. The MES chart can still render, but Warbird setup state is intentionally withheld."}
          </div>
          <div className="mt-1 text-white/55">
            Checked{" "}
            {new Date(data.runtime.checkedAt).toLocaleString("en-US", {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
              hour12: true,
              timeZone: "America/Chicago",
            })}
            {" · "}
            Missing objects:{" "}
            {data.runtime.missingObjects.length > 0
              ? data.runtime.missingObjects.join(", ")
              : "none reported"}
          </div>
        </div>
      ) : null}

      {/* Top: Correlations Row */}
      <CorrelationsRow correlations={data?.correlations ?? null} />

      {/* Middle: Chart (full width) */}
      <div className="flex min-h-0" style={{ height: "80vh" }}>
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

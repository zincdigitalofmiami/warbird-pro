"use client";

import { useEffect, useMemo, useState } from "react";
import MesChartWrapper from "@/components/charts/MesChartWrapper";
import MarketSummaryCard from "@/components/dashboard/MarketSummaryCard";
import ActiveSetupsCard from "@/components/dashboard/ActiveSetupsCard";
import SessionStatsCard from "@/components/dashboard/SessionStatsCard";
import { fromWarbirdSetup, type SetupCandidate } from "@/lib/setup-candidates";
import type { WarbirdSignal, WarbirdSetupEventRow, WarbirdSetupRow } from "@/lib/warbird/types";

interface DashboardSetupCounts {
  active: number;
  counterTrend: number;
  tp1Hit: number;
  tp2Hit: number;
  stopped: number;
  expired: number;
}

interface DashboardPayload {
  signal: WarbirdSignal | null;
  setups: WarbirdSetupRow[];
  events: WarbirdSetupEventRow[];
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
        const response = await fetch("/api/warbird/dashboard?days=7&limit=100", {
          cache: "no-store",
        });

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
    <>
      <MesChartWrapper signal={data?.signal ?? null} setups={setups} />
      <div className="w-full px-4 pb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
        <MarketSummaryCard />
        <ActiveSetupsCard counts={data?.counts ?? null} loading={loading} />
        <SessionStatsCard />
      </div>
    </>
  );
}

"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { fromWarbirdSetup } from "@/lib/setup-candidates";
import type { SetupCandidate } from "@/lib/setup-candidates";
import type { WarbirdSignal, WarbirdSetupRow } from "@/lib/warbird/types";

const LiveMesChart = dynamic(
  () => import("@/components/charts/LiveMesChart"),
  { ssr: false },
);

export default function MesChartWrapper() {
  const [signal, setSignal] = useState<WarbirdSignal | null>(null);
  const [setups, setSetups] = useState<SetupCandidate[]>([]);

  useEffect(() => {
    let cancelled = false;

    async function loadWarbird() {
      try {
        const [signalRes, historyRes] = await Promise.all([
          fetch("/api/warbird/signal", { cache: "no-store" }),
          fetch("/api/warbird/history?days=7&limit=10", { cache: "no-store" }),
        ]);

        if (!signalRes.ok || !historyRes.ok) return;

        const signalJson = (await signalRes.json()) as {
          signal: WarbirdSignal | null;
          setup: WarbirdSetupRow | null;
        };
        const historyJson = (await historyRes.json()) as {
          setups: WarbirdSetupRow[];
        };

        if (cancelled) return;

        setSignal(signalJson.signal ?? null);

        const mapped = (historyJson.setups ?? [])
          .slice(0, 4)
          .map((setup) => fromWarbirdSetup(setup));
        setSetups(mapped);
      } catch {
        if (!cancelled) {
          setSignal(null);
          setSetups([]);
        }
      }
    }

    void loadWarbird();
    const interval = setInterval(loadWarbird, 60_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return <LiveMesChart signal={signal} setups={setups} />;
}

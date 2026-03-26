"use client";

import dynamic from "next/dynamic";
import type { SetupCandidate } from "@/lib/setup-candidates";
import type { WarbirdSignal } from "@/lib/warbird/types";

const LiveMesChart = dynamic(
  () => import("@/components/charts/LiveMesChart"),
  { ssr: false },
);

export default function MesChartWrapper({
  signal,
  setups,
}: {
  signal: WarbirdSignal | null;
  setups: SetupCandidate[];
}) {
  return <LiveMesChart signal={signal} setups={setups} />;
}

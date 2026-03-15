"use client";

import dynamic from "next/dynamic";

const LiveMesChart = dynamic(
  () => import("@/components/charts/LiveMesChart"),
  { ssr: false },
);

export default function MesChartWrapper() {
  return <LiveMesChart />;
}

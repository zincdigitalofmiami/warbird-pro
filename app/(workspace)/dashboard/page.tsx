import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import MesChartWrapper from "@/components/charts/MesChartWrapper";
import MarketSummaryCard from "@/components/dashboard/MarketSummaryCard";
import ActiveSetupsCard from "@/components/dashboard/ActiveSetupsCard";
import SessionStatsCard from "@/components/dashboard/SessionStatsCard";
import { Suspense } from "react";

async function AuthGate() {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getClaims();

  if (error || !data?.claims) {
    redirect("/auth/login");
  }

  return (
    <>
      <MesChartWrapper />
      <div className="w-full px-4 pb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
        <MarketSummaryCard />
        <ActiveSetupsCard />
        <SessionStatsCard />
      </div>
    </>
  );
}

export default function DashboardPage() {
  return (
    <div className="flex-1 w-full flex flex-col" style={{ background: "#131722" }}>
      <Suspense
        fallback={
          <div
            className="flex items-center justify-center w-full"
            style={{ height: "80vh", background: "#131722" }}
          >
            <span className="text-white/30 text-sm">Loading chart...</span>
          </div>
        }
      >
        <AuthGate />
      </Suspense>
    </div>
  );
}

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import DashboardLiveClient from "@/components/dashboard/DashboardLiveClient";
import { Suspense } from "react";

async function AuthGate() {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getClaims();

  if (error || !data?.claims) {
    redirect("/auth/login");
  }

  return (
    <DashboardLiveClient />
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

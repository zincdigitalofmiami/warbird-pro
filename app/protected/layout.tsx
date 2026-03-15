import { AuthButton } from "@/components/auth-button";
import { hasEnvVars } from "@/lib/utils";
import { EnvVarWarning } from "@/components/env-var-warning";
import Link from "next/link";
import { Suspense } from "react";

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <main className="min-h-screen flex flex-col" style={{ background: "#131722" }}>
      <nav className="w-full flex justify-center border-b border-white/5 h-14">
        <div className="w-full flex justify-between items-center px-6 text-sm">
          <div className="flex items-center gap-6">
            <Link
              href="/protected"
              className="font-bold text-white tracking-tight text-base"
            >
              Warbird Pro
            </Link>
          </div>
          <div className="flex items-center gap-4">
            {!hasEnvVars ? (
              <EnvVarWarning />
            ) : (
              <Suspense>
                <AuthButton />
              </Suspense>
            )}
          </div>
        </div>
      </nav>
      <div className="flex-1 w-full">{children}</div>
    </main>
  );
}

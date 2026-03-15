import { AuthButton } from "@/components/auth-button";
import { hasEnvVars } from "@/lib/utils";
import { EnvVarWarning } from "@/components/env-var-warning";
import Link from "next/link";
import Image from "next/image";
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
            <Link href="/protected" className="flex items-center">
              <Image
                src="/warbird-logo.svg"
                alt="Warbird Pro"
                width={180}
                height={36}
                priority
                className="h-8 w-auto"
              />
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

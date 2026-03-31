import Image from "next/image";
import Link from "next/link";

export default function Home() {
  return (
    <main
      className="min-h-screen flex flex-col"
      style={{ background: "linear-gradient(135deg, #000000 0%, #0a0a0a 50%, #111111 100%)" }}
    >
      {/* Nav */}
      <nav className="w-full flex justify-center h-20" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        <div className="w-full max-w-6xl flex justify-between items-center px-6">
          <Image src="/warbird-logo.svg" alt="Warbird Pro" className="h-10 w-auto" width={120} height={40} />
          <Link
            href="/auth/login"
            className="text-sm text-white/70 hover:text-white transition-colors duration-200"
          >
            Sign In
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative flex-1 flex items-center justify-center px-6" style={{ minHeight: "calc(100vh - 80px)" }}>
        {/* Warbird watermark overlay */}
        <div
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
          style={{ opacity: 0.5 }}
        >
          <Image src="/chart_watermark.svg" alt="" className="w-[600px] h-[600px]" width={600} height={600} />
        </div>
        <div className="relative z-10 w-full max-w-6xl grid grid-cols-1 lg:grid-cols-2 gap-16 items-center py-20">
          {/* Left — Text */}
          <div className="flex flex-col gap-8">
            <h1
              className="text-white font-bold"
              style={{ fontSize: "clamp(2.5rem, 5vw, 4rem)", letterSpacing: "-2px", lineHeight: 1.1 }}
            >
              S&amp;P 500 Futures
              <br />
              <span className="text-white/60">Intelligence</span>
            </h1>
            <p className="text-white/50 text-lg leading-relaxed max-w-lg" style={{ fontWeight: 300 }}>
              Fibonacci confluence engine for MES micro S&amp;P 500 futures.
              Backtested 15-minute setup detection with quantitative entry classification — built on real market data.
            </p>
            <p className="text-white/25 text-sm mt-2">
              Designed and architected by Kirk Musick, MS, MBA
            </p>
            <div className="flex gap-4 mt-2">
              <Link
                href="/auth/sign-up"
                className="px-6 py-3 text-sm font-medium rounded-lg transition-colors duration-200"
                style={{
                  background: "rgba(255,255,255,0.1)",
                  color: "white",
                  border: "1px solid rgba(255,255,255,0.15)",
                }}
              >
                Get Started
              </Link>
              <Link
                href="/auth/login"
                className="px-6 py-3 text-sm text-white/50 hover:text-white transition-colors duration-200"
              >
                Sign In &rarr;
              </Link>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-8 mt-8 pt-8" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              <StatBlock value="15m" label="Signal Resolution" />
              <StatBlock value="5" label="Fib Lookbacks" />
              <StatBlock value="24/5" label="Market Coverage" />
            </div>
          </div>

          {/* Right — Visual */}
          <div className="hidden lg:flex items-center justify-center">
            <div
              className="relative"
              style={{ width: 400, height: 400 }}
            >
              {/* Abstract grid visualization */}
              <svg viewBox="0 0 400 400" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
                {/* Horizontal lines */}
                {[80, 130, 180, 220, 260, 310].map((y) => (
                  <line key={`h-${y}`} x1="40" y1={y} x2="360" y2={y} stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
                ))}
                {/* Vertical lines */}
                {[80, 130, 180, 230, 280, 330].map((x) => (
                  <line key={`v-${x}`} x1={x} y1="60" x2={x} y2="340" stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
                ))}
                {/* Price action path */}
                <polyline
                  points="80,280 110,260 140,270 170,220 200,200 230,180 260,210 290,170 320,160 350,140"
                  stroke="rgba(38,198,218,0.5)"
                  strokeWidth="2"
                  fill="none"
                />
                {/* Fib levels */}
                <line x1="80" y1="160" x2="350" y2="160" stroke="rgba(38,198,218,0.15)" strokeWidth="1" strokeDasharray="4 4" />
                <line x1="80" y1="200" x2="350" y2="200" stroke="rgba(38,198,218,0.1)" strokeWidth="1" strokeDasharray="4 4" />
                <line x1="80" y1="240" x2="350" y2="240" stroke="rgba(38,198,218,0.1)" strokeWidth="1" strokeDasharray="4 4" />
                {/* Pivot dots */}
                <circle cx="170" cy="220" r="4" fill="rgba(38,198,218,0.6)" />
                <circle cx="290" cy="170" r="4" fill="rgba(38,198,218,0.6)" />
                <circle cx="350" cy="140" r="4" fill="rgba(38,198,218,0.8)" />
                {/* Labels */}
                <text x="354" y="162" fill="rgba(255,255,255,0.2)" fontSize="10">.618</text>
                <text x="354" y="203" fill="rgba(255,255,255,0.2)" fontSize="10">.500</text>
                <text x="354" y="243" fill="rgba(255,255,255,0.2)" fontSize="10">.382</text>
              </svg>
            </div>
          </div>
        </div>
      </section>

      {/* Intelligence Section */}
      <section className="w-full flex justify-center px-6 py-24" style={{ background: "#050505" }}>
        <div className="w-full max-w-6xl">
          <h2 className="text-white/80 text-2xl font-semibold mb-3 tracking-tight">Intelligence Layers</h2>
          <p className="text-white/30 text-sm mb-12 max-w-lg">
            Backtested and rule-driven. Every signal built on real market data.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <IntelCard
              title="Fibonacci Engine"
              description="Multi-period confluence with 5 lookback windows. Touch, Hook, Go state machine."
              accent={false}
            />
            <IntelCard
              title="Live MES Data"
              description="Sub-2-second Databento live feed. 1m and 15m bars with Supabase Realtime push."
              accent
            />
            <IntelCard
              title="Macro Context"
              description="31 FRED series, GPR index, economic calendar, Trump Effect tracker."
              accent={false}
            />
            <IntelCard
              title="Setup Classification"
              description="15-minute fib-outcome engine. TP1/TP2 measured-move targets with mechanical stop-loss."
              accent={false}
            />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="w-full flex justify-center px-6 py-20" style={{ background: "#000" }}>
        <div className="text-center max-w-xl">
          <h2 className="text-white text-3xl font-semibold mb-4 tracking-tight">
            Real data. Real signals.
          </h2>
          <p className="text-white/40 mb-8">
            Fibonacci confluence meets quantitative setup classification. Backtested on real MES futures data.
          </p>
          <Link
            href="/auth/sign-up"
            className="inline-block px-8 py-3 text-sm font-medium rounded-lg transition-colors duration-200"
            style={{
              background: "white",
              color: "black",
            }}
          >
            Get Started
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="w-full flex justify-center px-6 py-8" style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
        <p className="text-white/20 text-xs">
          &copy; 2026 Warbird Pro. All rights reserved.
        </p>
      </footer>
    </main>
  );
}

function StatBlock({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="text-white text-2xl font-semibold tracking-tight">{value}</div>
      <div className="text-white/30 text-xs mt-1">{label}</div>
    </div>
  );
}

function IntelCard({
  title,
  description,
  accent,
}: {
  title: string;
  description: string;
  accent: boolean;
}) {
  return (
    <div
      className="p-6 rounded-lg transition-transform duration-300 hover:-translate-y-1"
      style={{
        background: accent
          ? "rgba(38,198,218,0.04)"
          : "rgba(255,255,255,0.02)",
        border: accent
          ? "1px solid rgba(38,198,218,0.15)"
          : "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <h3 className="text-white/90 text-sm font-medium mb-2">{title}</h3>
      <p className="text-white/30 text-xs leading-relaxed">{description}</p>
    </div>
  );
}

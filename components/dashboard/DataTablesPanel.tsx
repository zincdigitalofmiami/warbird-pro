"use client";

import type { WarbirdSetupRow, WarbirdSignal } from "@/lib/warbird/types";

interface DataTablesPanelProps {
  signal: WarbirdSignal | null;
  setups: WarbirdSetupRow[];
}

export default function DataTablesPanel({ signal, setups }: DataTablesPanelProps) {
  return (
    <div
      className="w-full grid grid-cols-1 lg:grid-cols-3 gap-0"
      style={{
        background: "#131722",
        borderTop: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      {/* Fib State */}
      <FibStateTable signal={signal} />
      {/* Setup History */}
      <SetupHistoryTable setups={setups} />
      {/* Session Summary */}
      <SessionSummaryTable signal={signal} setups={setups} />
    </div>
  );
}

// ── Fib State Table ──────────────────────────────────────────────────────────

function FibStateTable({ signal }: { signal: WarbirdSignal | null }) {
  const setup = signal?.setup ?? null;
  const hasFib = setup?.fibLevel != null && setup?.fibRatio != null;

  return (
    <div
      className="px-5 py-4"
      style={{ borderRight: "1px solid rgba(255,255,255,0.04)" }}
    >
      <div className="text-[10px] font-semibold text-white/40 uppercase tracking-wider mb-3">
        Fib Structure
      </div>
      {!hasFib ? (
        <div className="text-[11px] text-white/20">No active fib state</div>
      ) : (
        <div className="grid grid-cols-2 gap-x-6 gap-y-2">
          <FibRow label="Direction" value={setup?.direction ?? "—"} color={setup?.direction === "LONG" ? "#26C6DA" : "#FF0000"} />
          <FibRow label="Status" value={setup?.status ?? "—"} />
          <FibRow label="Fib Level" value={setup?.fibLevel?.toFixed(2) ?? "—"} />
          <FibRow label="Fib Ratio" value={setup?.fibRatio?.toFixed(3) ?? "—"} />
          <FibRow label="Entry" value={setup?.entry?.toFixed(2) ?? "—"} color="#FF9800" />
          <FibRow label="Stop Loss" value={setup?.stopLoss?.toFixed(2) ?? "—"} color="#FF1744" />
          <FibRow label="TP1" value={setup?.tp1?.toFixed(2) ?? "—"} color="#00C853" />
          <FibRow label="TP2" value={setup?.tp2?.toFixed(2) ?? "—"} color="#69F0AE" />
        </div>
      )}
    </div>
  );
}

function FibRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] text-white/30">{label}</span>
      <span
        className="text-[11px] font-mono tabular-nums"
        style={{ color: color ?? "rgba(255,255,255,0.6)" }}
      >
        {value}
      </span>
    </div>
  );
}

// ── Setup History Table ──────────────────────────────────────────────────────

function SetupHistoryTable({ setups }: { setups: WarbirdSetupRow[] }) {
  const recent = setups.slice(0, 8);

  return (
    <div
      className="px-5 py-4"
      style={{ borderRight: "1px solid rgba(255,255,255,0.04)" }}
    >
      <div className="text-[10px] font-semibold text-white/40 uppercase tracking-wider mb-3">
        Recent Setups
      </div>
      {recent.length === 0 ? (
        <div className="text-[11px] text-white/20">No setup history</div>
      ) : (
        <div className="space-y-0">
          {/* Header */}
          <div className="grid grid-cols-5 gap-2 text-[9px] text-white/25 uppercase tracking-wider pb-1.5" style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
            <span>Time</span>
            <span>Dir</span>
            <span>Entry</span>
            <span>Status</span>
            <span className="text-right">R:R</span>
          </div>
          {recent.map((setup) => {
            const d = new Date(setup.bar_close_ts);
            const timeStr = d.toLocaleString("en-US", {
              month: "numeric",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
              hour12: false,
              timeZone: "America/Chicago",
            });
            const statusColor = STATUS_COLORS[setup.status] ?? "rgba(255,255,255,0.4)";
            const dirColor = setup.direction === "LONG" ? "#26C6DA" : "#FF0000";
            const rr = setup.stop_loss !== 0 && setup.entry_price !== 0
              ? Math.abs(setup.tp1 - setup.entry_price) / Math.abs(setup.entry_price - setup.stop_loss)
              : null;

            return (
              <div
                key={setup.id}
                className="grid grid-cols-5 gap-2 py-1.5 text-[10px]"
                style={{ borderBottom: "1px solid rgba(255,255,255,0.02)" }}
              >
                <span className="text-white/30 tabular-nums">{timeStr}</span>
                <span className="font-medium" style={{ color: dirColor }}>
                  {setup.direction}
                </span>
                <span className="text-white/50 font-mono tabular-nums">
                  {setup.entry_price.toFixed(2)}
                </span>
                <span className="font-medium" style={{ color: statusColor }}>
                  {setup.status}
                </span>
                <span className="text-white/40 tabular-nums text-right">
                  {rr != null ? `${rr.toFixed(1)}R` : "—"}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: "#FF9800",
  TP1_HIT: "#00C853",
  TP2_HIT: "#69F0AE",
  STOPPED: "#FF1744",
  EXPIRED: "#787b86",
};

// ── Session Summary Table ────────────────────────────────────────────────────

function SessionSummaryTable({
  signal,
  setups,
}: {
  signal: WarbirdSignal | null;
  setups: WarbirdSetupRow[];
}) {
  const totalSetups = setups.length;
  const activeCount = setups.filter((s) => s.status === "ACTIVE").length;
  const tp1Count = setups.filter((s) => s.status === "TP1_HIT" || s.status === "TP2_HIT").length;
  const stoppedCount = setups.filter((s) => s.status === "STOPPED").length;
  const winRate = totalSetups > 0 ? ((tp1Count / totalSetups) * 100) : null;

  const conviction = signal?.conviction ?? null;
  const risk = signal?.risk ?? null;
  const feedback = signal?.feedback ?? null;

  return (
    <div className="px-5 py-4">
      <div className="text-[10px] font-semibold text-white/40 uppercase tracking-wider mb-3">
        Session Summary
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2">
        <StatRow label="Total Setups" value={totalSetups.toString()} />
        <StatRow label="Active" value={activeCount.toString()} color="#FF9800" />
        <StatRow label="TP Hits" value={tp1Count.toString()} color="#00C853" />
        <StatRow label="Stopped" value={stoppedCount.toString()} color="#FF1744" />
        <StatRow label="Win Rate" value={winRate != null ? `${winRate.toFixed(0)}%` : "—"} />
        <StatRow label="Conviction" value={conviction?.level ?? "—"} color={convictionColor(conviction?.level ?? null)} />
        <StatRow label="Regime" value={risk?.regime ?? "—"} />
        <StatRow label="VIX" value={risk?.vix_level != null ? risk.vix_level.toFixed(1) : "—"} />
        <StatRow label="Win Rate 20" value={feedback?.win_rate_last20 != null ? `${(feedback.win_rate_last20 * 100).toFixed(0)}%` : "—"} />
        <StatRow label="Streak" value={feedback?.current_streak?.toString() ?? "—"} />
      </div>
    </div>
  );
}

function StatRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] text-white/30">{label}</span>
      <span
        className="text-[11px] font-mono tabular-nums"
        style={{ color: color ?? "rgba(255,255,255,0.6)" }}
      >
        {value}
      </span>
    </div>
  );
}

function convictionColor(level: string | null): string {
  switch (level) {
    case "MAXIMUM": return "#69F0AE";
    case "HIGH": return "#00C853";
    case "MODERATE": return "#FF9800";
    case "LOW": return "#FFB300";
    case "NO_TRADE": return "#FF1744";
    default: return "rgba(255,255,255,0.4)";
  }
}

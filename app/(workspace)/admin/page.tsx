"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// --- Types ---

interface TableCoverage {
  table: string;
  latestTs: string | null;
  rowCount: number;
  staleness: string;
}

interface JobLogEntry {
  id: number;
  job_name: string;
  status: string;
  rows_affected: number | null;
  error_message: string | null;
  duration_ms: number | null;
  created_at: string;
}

type TargetResult = "HIT" | "MISS" | "OPEN";
type OutcomeResult = "TP2_HIT" | "TP1_ONLY" | "STOPPED" | "REVERSAL" | "OPEN";

interface SetupEntry {
  id: number;
  ts: string;
  symbol_code: string;
  direction: string;
  status: string;
  entry_price: number | null;
  stop_loss: number | null;
  tp1: number | null;
  tp2: number | null;
  tp1_hit_at: string | null;
  tp2_hit_at: string | null;
  last_event_type: string | null;
  last_event_ts: string | null;
  pt1_result: TargetResult;
  pt2_result: TargetResult;
  outcome_result: OutcomeResult;
  conviction_level: string | null;
  fib_level: number | null;
  fib_ratio: number | null;
}

interface SymbolEntry {
  code: string;
  display_name: string;
  data_source: string;
  is_active: boolean;
}

interface TriggerEntry {
  id: number;
  ts: string;
  symbol_code: string;
  direction: string;
  decision: string;
  fib_level: number | null;
  entry_price: number | null;
  stop_loss: number | null;
  tp1: number | null;
  tp2: number | null;
  trigger_quality_ratio: number | null;
  no_trade_reason: string | null;
}

interface MeasuredMoveEntry {
  id: number;
  ts: string;
  symbol_code: string;
  direction: string;
  anchor_price: number | null;
  target_price: number | null;
  retracement_price: number | null;
  fib_level: number | null;
  status: string;
  target_result: TargetResult;
  outcome_result: OutcomeResult;
}

interface AdminData {
  coverage: TableCoverage[];
  jobLogs: JobLogEntry[];
  activeSetups: SetupEntry[];
  recentSetups: SetupEntry[];
  symbols: SymbolEntry[];
  triggers: TriggerEntry[];
  measuredMoves: MeasuredMoveEntry[];
  generatedAt: string;
}

// --- Status helpers ---

function coverageStatusColor(staleness: string): string {
  if (staleness === "empty" || staleness === "error") return "bg-red-500/20 text-red-400 border-red-500/30";
  if (staleness.endsWith("m ago")) {
    const mins = parseInt(staleness);
    if (mins < 30) return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
    if (mins < 60) return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
  }
  if (staleness.endsWith("h ago")) {
    const hrs = parseInt(staleness);
    if (hrs < 4) return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
  }
  return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
}

function statusColor(status: string): string {
  switch (status) {
    case "ACTIVE": return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
    case "TP1_HIT": return "bg-blue-500/20 text-blue-400 border-blue-500/30";
    case "TP2_HIT": return "bg-purple-500/20 text-purple-400 border-purple-500/30";
    case "STOPPED": return "bg-red-500/20 text-red-400 border-red-500/30";
    case "EXPIRED": return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
    default: return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
  }
}

function jobStatusColor(status: string): string {
  if (status === "OK" || status === "SUCCESS") return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
  if (status === "ERROR" || status === "FAILED") return "bg-red-500/20 text-red-400 border-red-500/30";
  if (status === "SKIPPED") return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
  return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
}

function directionColor(dir: string): string {
  if (dir === "LONG" || dir === "BULLISH") return "text-cyan-400";
  return "text-red-400";
}

function targetBadgeColor(state: TargetResult): string {
  if (state === "HIT") return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
  if (state === "MISS") return "bg-red-500/20 text-red-400 border-red-500/30";
  return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
}

function outcomeBadgeColor(state: OutcomeResult): string {
  if (state === "TP2_HIT") return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
  if (state === "TP1_ONLY") return "bg-blue-500/20 text-blue-300 border-blue-500/30";
  if (state === "STOPPED") return "bg-red-500/20 text-red-400 border-red-500/30";
  if (state === "REVERSAL") return "bg-amber-500/20 text-amber-300 border-amber-500/30";
  return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
}

function formatTs(ts: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
    timeZone: "America/Chicago",
  });
}

// --- Main Admin Page ---

export default function AdminPage() {
  const [data, setData] = useState<AdminData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 300_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[80vh]">
        <span className="text-white/30 text-sm">Loading admin data...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center min-h-[80vh]">
        <span className="text-red-400 text-sm">{error ?? "No data"}</span>
      </div>
    );
  }

  // Summary stats
  const totalRows = data.coverage.reduce((s, c) => s + c.rowCount, 0);
  const activeTables = data.coverage.filter((c) => c.rowCount > 0).length;
  const totalTables = data.coverage.length;
  const activeSymbols = data.symbols.filter((s) => s.is_active).length;
  const recentJobs = data.jobLogs.filter(
    (j) => Date.now() - new Date(j.created_at).getTime() < 3600_000,
  ).length;
  const errorJobs = data.jobLogs.filter(
    (j) => j.status === "ERROR" || j.status === "FAILED",
  ).length;

  return (
    <div className="w-full max-w-[1400px] mx-auto px-6 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white text-xl font-semibold tracking-tight">
            System Admin
          </h1>
          <p className="text-white/30 text-xs mt-1">
            Last refreshed: {formatTs(data.generatedAt)}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchData}
          className="text-xs border-white/10 text-white/50 hover:text-white hover:bg-white/5"
        >
          Refresh
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <SummaryCard label="Total Rows" value={totalRows.toLocaleString()} />
        <SummaryCard label="Tables" value={`${activeTables}/${totalTables} active`} />
        <SummaryCard label="Symbols" value={`${activeSymbols} active`} />
        <SummaryCard label="Active Setups" value={data.activeSetups.length.toString()} />
        <SummaryCard label="Jobs (1h)" value={recentJobs.toString()} />
        <SummaryCard label="Errors" value={errorJobs.toString()} alert={errorJobs > 0} />
      </div>

      {/* Tabs */}
      <Tabs defaultValue="coverage" className="w-full">
        <TabsList className="bg-white/5 border border-white/10">
          <TabsTrigger value="coverage" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/40">
            Data Coverage
          </TabsTrigger>
          <TabsTrigger value="setups" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/40">
            Setups
          </TabsTrigger>
          <TabsTrigger value="jobs" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/40">
            Job Log
          </TabsTrigger>
          <TabsTrigger value="triggers" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/40">
            Triggers
          </TabsTrigger>
          <TabsTrigger value="symbols" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/40">
            Symbols
          </TabsTrigger>
        </TabsList>

        {/* --- Data Coverage Tab --- */}
        <TabsContent value="coverage" className="mt-4">
          <Card className="bg-white/[0.02] border-white/[0.06]">
            <CardHeader className="pb-3">
              <CardTitle className="text-white text-sm">Data Coverage</CardTitle>
              <CardDescription className="text-white/30 text-xs">
                Row counts and freshness for all {totalTables} tables
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {data.coverage.map((c) => (
                  <div
                    key={c.table}
                    className="flex items-center justify-between px-3 py-2 rounded-md bg-white/[0.02] border border-white/[0.04]"
                  >
                    <div className="flex flex-col">
                      <span className="text-white/70 text-xs font-mono">
                        {c.table}
                      </span>
                      <span className="text-white/30 text-[10px]">
                        {c.rowCount.toLocaleString()} rows
                      </span>
                    </div>
                    <Badge
                      variant="outline"
                      className={`text-[10px] ${coverageStatusColor(c.staleness)}`}
                    >
                      {c.staleness}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* --- Setups Tab --- */}
        <TabsContent value="setups" className="mt-4 space-y-4">
          {/* Active */}
          <Card className="bg-white/[0.02] border-white/[0.06]">
            <CardHeader className="pb-3">
              <CardTitle className="text-white text-sm">
                Active Setups ({data.activeSetups.length})
              </CardTitle>
              <CardDescription className="text-white/30 text-xs">
                ACTIVE
              </CardDescription>
            </CardHeader>
            <CardContent>
              {data.activeSetups.length === 0 ? (
                <span className="text-white/20 text-xs">No active setups</span>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/5">
                        <TableHead className="text-white/30 text-[10px]">Time</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Status</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Dir</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Entry</TableHead>
                        <TableHead className="text-white/30 text-[10px]">SL</TableHead>
                        <TableHead className="text-white/30 text-[10px]">TP1 Px</TableHead>
                        <TableHead className="text-white/30 text-[10px]">PT1</TableHead>
                        <TableHead className="text-white/30 text-[10px]">TP2 Px</TableHead>
                        <TableHead className="text-white/30 text-[10px]">PT2</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Outcome</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Last Event</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Conviction</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.activeSetups.map((s) => {
                        return (
                          <TableRow key={s.id} className="border-white/5">
                            <TableCell className="text-white/50 text-xs font-mono">{formatTs(s.ts)}</TableCell>
                            <TableCell>
                              <Badge variant="outline" className={`text-[10px] ${statusColor(s.status)}`}>
                                {s.status}
                              </Badge>
                            </TableCell>
                            <TableCell className={`text-xs font-medium ${directionColor(s.direction)}`}>
                              {s.direction}
                            </TableCell>
                            <TableCell className="text-white/60 text-xs tabular-nums">
                              {s.entry_price?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell className="text-red-400/60 text-xs tabular-nums">
                              {s.stop_loss?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell className="text-emerald-400/60 text-xs tabular-nums">
                              {s.tp1?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={`text-[10px] ${targetBadgeColor(s.pt1_result)}`}
                              >
                                {s.pt1_result}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-emerald-400/60 text-xs tabular-nums">
                              {s.tp2?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={`text-[10px] ${targetBadgeColor(s.pt2_result)}`}
                              >
                                {s.pt2_result}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={`text-[10px] ${outcomeBadgeColor(s.outcome_result)}`}
                              >
                                {s.outcome_result}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <div className="flex flex-col gap-1">
                                <Badge
                                  variant="outline"
                                  className="text-[10px] bg-zinc-500/20 text-zinc-300 border-zinc-500/30 w-fit"
                                >
                                  {s.last_event_type ?? "—"}
                                </Badge>
                                <span className="text-white/30 text-[10px] font-mono">
                                  {formatTs(s.last_event_ts)}
                                </span>
                              </div>
                            </TableCell>
                            <TableCell className="text-white/40 text-xs tabular-nums">
                              {s.conviction_level ?? "—"}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Recent */}
          <Card className="bg-white/[0.02] border-white/[0.06]">
            <CardHeader className="pb-3">
              <CardTitle className="text-white text-sm">
                Recent Setups — 7 Days ({data.recentSetups.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {data.recentSetups.length === 0 ? (
                <span className="text-white/20 text-xs">No recent setups</span>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/5">
                        <TableHead className="text-white/30 text-[10px]">Time</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Status</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Dir</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Entry</TableHead>
                        <TableHead className="text-white/30 text-[10px]">SL</TableHead>
                        <TableHead className="text-white/30 text-[10px]">TP1 Px</TableHead>
                        <TableHead className="text-white/30 text-[10px]">PT1</TableHead>
                        <TableHead className="text-white/30 text-[10px]">TP2 Px</TableHead>
                        <TableHead className="text-white/30 text-[10px]">PT2</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Outcome</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Last Event</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Fib</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.recentSetups.map((s) => {
                        return (
                          <TableRow key={s.id} className="border-white/5">
                            <TableCell className="text-white/50 text-xs font-mono">{formatTs(s.ts)}</TableCell>
                            <TableCell>
                              <Badge variant="outline" className={`text-[10px] ${statusColor(s.status)}`}>
                                {s.status}
                              </Badge>
                            </TableCell>
                            <TableCell className={`text-xs font-medium ${directionColor(s.direction)}`}>
                              {s.direction}
                            </TableCell>
                            <TableCell className="text-white/60 text-xs tabular-nums">
                              {s.entry_price?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell className="text-red-400/60 text-xs tabular-nums">
                              {s.stop_loss?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell className="text-emerald-400/60 text-xs tabular-nums">
                              {s.tp1?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={`text-[10px] ${targetBadgeColor(s.pt1_result)}`}
                              >
                                {s.pt1_result}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-emerald-400/60 text-xs tabular-nums">
                              {s.tp2?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={`text-[10px] ${targetBadgeColor(s.pt2_result)}`}
                              >
                                {s.pt2_result}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={`text-[10px] ${outcomeBadgeColor(s.outcome_result)}`}
                              >
                                {s.outcome_result}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <div className="flex flex-col gap-1">
                                <Badge
                                  variant="outline"
                                  className="text-[10px] bg-zinc-500/20 text-zinc-300 border-zinc-500/30 w-fit"
                                >
                                  {s.last_event_type ?? "—"}
                                </Badge>
                                <span className="text-white/30 text-[10px] font-mono">
                                  {formatTs(s.last_event_ts)}
                                </span>
                              </div>
                            </TableCell>
                            <TableCell className="text-white/30 text-xs">
                              {s.fib_ratio != null ? s.fib_ratio.toFixed(3) : "—"}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Measured Moves */}
          <Card className="bg-white/[0.02] border-white/[0.06]">
            <CardHeader className="pb-3">
              <CardTitle className="text-white text-sm">
                Measured Moves ({data.measuredMoves.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {data.measuredMoves.length === 0 ? (
                <span className="text-white/20 text-xs">No measured moves</span>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/5">
                        <TableHead className="text-white/30 text-[10px]">Time</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Dir</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Anchor</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Target</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Retrace</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Fib</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Target Hit</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Outcome</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.measuredMoves.map((m) => {
                        return (
                          <TableRow key={m.id} className="border-white/5">
                            <TableCell className="text-white/50 text-xs font-mono">{formatTs(m.ts)}</TableCell>
                            <TableCell className={`text-xs font-medium ${directionColor(m.direction)}`}>
                              {m.direction}
                            </TableCell>
                            <TableCell className="text-white/60 text-xs tabular-nums">
                              {m.anchor_price?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell className="text-emerald-400/60 text-xs tabular-nums">
                              {m.target_price?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell className="text-white/40 text-xs tabular-nums">
                              {m.retracement_price?.toFixed(2) ?? "—"}
                            </TableCell>
                            <TableCell className="text-white/40 text-xs tabular-nums">
                              {m.fib_level?.toFixed(3) ?? "—"}
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={`text-[10px] ${targetBadgeColor(m.target_result)}`}
                              >
                                {m.target_result}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={`text-[10px] ${outcomeBadgeColor(m.outcome_result)}`}
                              >
                                {m.outcome_result}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={`text-[10px] ${
                                  m.status === "ACTIVE"
                                    ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                                    : "bg-zinc-500/20 text-zinc-400 border-zinc-500/30"
                                }`}
                              >
                                {m.status}
                              </Badge>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* --- Job Log Tab --- */}
        <TabsContent value="jobs" className="mt-4">
          <Card className="bg-white/[0.02] border-white/[0.06]">
            <CardHeader className="pb-3">
              <CardTitle className="text-white text-sm">
                Job Log — Last 50 Runs
              </CardTitle>
              <CardDescription className="text-white/30 text-xs">
                All cron job executions
              </CardDescription>
            </CardHeader>
            <CardContent>
              {data.jobLogs.length === 0 ? (
                <span className="text-white/20 text-xs">No job logs yet</span>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/5">
                        <TableHead className="text-white/30 text-[10px]">Time</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Job</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Status</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Rows</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Duration</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Error</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.jobLogs.map((j) => (
                        <TableRow key={j.id} className="border-white/5">
                          <TableCell className="text-white/50 text-xs font-mono">
                            {formatTs(j.created_at)}
                          </TableCell>
                          <TableCell className="text-white/70 text-xs font-mono">
                            {j.job_name}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className={`text-[10px] ${jobStatusColor(j.status)}`}>
                              {j.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-white/50 text-xs tabular-nums">
                            {j.rows_affected ?? "—"}
                          </TableCell>
                          <TableCell className="text-white/40 text-xs tabular-nums">
                            {j.duration_ms != null ? `${j.duration_ms}ms` : "—"}
                          </TableCell>
                          <TableCell className="text-red-400/60 text-xs max-w-[200px] truncate">
                            {j.error_message ?? "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* --- Triggers Tab --- */}
        <TabsContent value="triggers" className="mt-4">
          <Card className="bg-white/[0.02] border-white/[0.06]">
            <CardHeader className="pb-3">
              <CardTitle className="text-white text-sm">
                Triggers ({data.triggers.length})
              </CardTitle>
              <CardDescription className="text-white/30 text-xs">
                Latest MES 15m trigger evaluations
              </CardDescription>
            </CardHeader>
            <CardContent>
              {data.triggers.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 gap-2">
                  <span className="text-white/20 text-sm">No triggers yet</span>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/5">
                        <TableHead className="text-white/30 text-[10px]">Time</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Symbol</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Dir</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Decision</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Fib</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Entry</TableHead>
                        <TableHead className="text-white/30 text-[10px]">SL</TableHead>
                        <TableHead className="text-white/30 text-[10px]">TP1</TableHead>
                        <TableHead className="text-white/30 text-[10px]">TP2</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Score</TableHead>
                        <TableHead className="text-white/30 text-[10px]">No-Go Reason</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.triggers.map((trigger) => (
                        <TableRow key={trigger.id} className="border-white/5">
                          <TableCell className="text-white/50 text-xs font-mono">
                            {formatTs(trigger.ts)}
                          </TableCell>
                          <TableCell className="text-white/70 text-xs font-mono">
                            {trigger.symbol_code}
                          </TableCell>
                          <TableCell className={`text-xs font-medium ${directionColor(trigger.direction)}`}>
                            {trigger.direction}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="text-[10px] bg-zinc-500/20 text-zinc-300 border-zinc-500/30">
                              {trigger.decision}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-white/40 text-xs tabular-nums">
                            {trigger.fib_level?.toFixed(2) ?? "—"}
                          </TableCell>
                          <TableCell className="text-white/60 text-xs tabular-nums">
                            {trigger.entry_price?.toFixed(2) ?? "—"}
                          </TableCell>
                          <TableCell className="text-red-400/60 text-xs tabular-nums">
                            {trigger.stop_loss?.toFixed(2) ?? "—"}
                          </TableCell>
                          <TableCell className="text-emerald-400/60 text-xs tabular-nums">
                            {trigger.tp1?.toFixed(2) ?? "—"}
                          </TableCell>
                          <TableCell className="text-emerald-400/60 text-xs tabular-nums">
                            {trigger.tp2?.toFixed(2) ?? "—"}
                          </TableCell>
                          <TableCell className="text-white/50 text-xs tabular-nums">
                            {trigger.trigger_quality_ratio != null ? trigger.trigger_quality_ratio.toFixed(3) : "—"}
                          </TableCell>
                          <TableCell className="text-white/30 text-xs max-w-[220px] truncate">
                            {trigger.no_trade_reason ?? "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* --- Symbols Tab --- */}
        <TabsContent value="symbols" className="mt-4">
          <Card className="bg-white/[0.02] border-white/[0.06]">
            <CardHeader className="pb-3">
              <CardTitle className="text-white text-sm">
                Symbol Registry ({data.symbols.length} total, {activeSymbols} active)
              </CardTitle>
              <CardDescription className="text-white/30 text-xs">
                Databento + FRED + Manual sources
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                {data.symbols.map((s) => (
                  <div
                    key={s.code}
                    className={`flex items-center justify-between px-3 py-2 rounded-md border ${
                      s.is_active
                        ? "bg-white/[0.02] border-white/[0.06]"
                        : "bg-white/[0.01] border-white/[0.03] opacity-40"
                    }`}
                  >
                    <div className="flex flex-col">
                      <span className="text-white/70 text-xs font-mono font-medium">
                        {s.code}
                      </span>
                      <span className="text-white/30 text-[10px]">
                        {s.display_name}
                      </span>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <Badge
                        variant="outline"
                        className={`text-[10px] ${
                          s.is_active
                            ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                            : "bg-zinc-500/20 text-zinc-400 border-zinc-500/30"
                        }`}
                      >
                        {s.is_active ? "active" : "inactive"}
                      </Badge>
                      <span className="text-white/20 text-[10px]">{s.data_source}</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// --- Summary Card Component ---

function SummaryCard({
  label,
  value,
  alert,
}: {
  label: string;
  value: string;
  alert?: boolean;
}) {
  return (
    <Card className="bg-white/[0.02] border-white/[0.06]">
      <CardContent className="pt-4 pb-3 px-4">
        <div className="text-white/30 text-[10px] uppercase tracking-wider mb-1">
          {label}
        </div>
        <div
          className={`text-lg font-semibold tabular-nums ${
            alert ? "text-red-400" : "text-white/80"
          }`}
        >
          {value}
        </div>
      </CardContent>
    </Card>
  );
}

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

type TargetHitState = "HIT" | "MISS" | "OPEN";
type OutcomeState = "TP2_HIT" | "TP1_ONLY" | "STOPPED" | "REVERSAL" | "OPEN";

interface CandidateRow {
  candidate_id: number;
  signal_id: string | null;
  bar_close_ts: string;
  symbol_code: string;
  direction: string;
  anchor_price: number | null;
  target_price: number | null;
  entry_price: number | null;
  stop_loss: number | null;
  tp1_price: number | null;
  tp2_price: number | null;
  fib_level_touched: string | null;
  fib_ratio: number | null;
  setup_archetype: string | null;
  confidence_score: number | null;
  decision_code: string | null;
  tp1_probability: number | null;
  tp2_probability: number | null;
  reversal_risk: number | null;
  target_hit_state: TargetHitState;
  outcome_state: OutcomeState;
  status: string;
  emitted_at: string | null;
  packet_id: string | null;
}

interface SymbolEntry {
  code: string;
  display_name: string;
  data_source: string;
  is_active: boolean;
}

interface AdminData {
  coverage: TableCoverage[];
  jobLogs: JobLogEntry[];
  candidates: CandidateRow[];
  symbols: SymbolEntry[];
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

function targetBadgeColor(state: TargetHitState): string {
  if (state === "HIT") return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
  if (state === "MISS") return "bg-red-500/20 text-red-400 border-red-500/30";
  return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
}

function outcomeBadgeColor(state: OutcomeState): string {
  if (state === "TP2_HIT") return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
  if (state === "TP1_ONLY") return "bg-blue-500/20 text-blue-300 border-blue-500/30";
  if (state === "STOPPED") return "bg-red-500/20 text-red-400 border-red-500/30";
  if (state === "REVERSAL") return "bg-amber-500/20 text-amber-300 border-amber-500/30";
  return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
}

function decisionBadgeColor(code: string | null): string {
  if (code === "TAKE_TRADE") return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
  if (code === "WAIT") return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
  if (code === "PASS") return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
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

function formatPrice(v: number | null): string {
  return v != null ? v.toFixed(2) : "—";
}

function formatPct(v: number | null): string {
  return v != null ? `${(v * 100).toFixed(1)}%` : "—";
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
        <SummaryCard label="Candidates" value={data.candidates.length.toString()} />
        <SummaryCard label="Jobs (1h)" value={recentJobs.toString()} />
        <SummaryCard label="Errors" value={errorJobs.toString()} alert={errorJobs > 0} />
      </div>

      {/* Tabs */}
      <Tabs defaultValue="coverage" className="w-full">
        <TabsList className="bg-white/5 border border-white/10">
          <TabsTrigger value="coverage" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/40">
            Data Coverage
          </TabsTrigger>
          <TabsTrigger value="candidates" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/40">
            Candidates
          </TabsTrigger>
          <TabsTrigger value="jobs" className="text-xs data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/40">
            Job Log
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
                      <span className="text-white/70 text-xs font-mono">{c.table}</span>
                      <span className="text-white/30 text-[10px]">{c.rowCount.toLocaleString()} rows</span>
                    </div>
                    <Badge variant="outline" className={`text-[10px] ${coverageStatusColor(c.staleness)}`}>
                      {c.staleness}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* --- Candidates Tab --- */}
        <TabsContent value="candidates" className="mt-4">
          <Card className="bg-white/[0.02] border-white/[0.06]">
            <CardHeader className="pb-3">
              <CardTitle className="text-white text-sm">
                Fib Candidates ({data.candidates.length})
              </CardTitle>
              <CardDescription className="text-white/30 text-xs">
                From warbird_admin_candidate_rows_v — canonical fib engine output
              </CardDescription>
            </CardHeader>
            <CardContent>
              {data.candidates.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 gap-2">
                  <span className="text-white/20 text-sm">No candidates yet</span>
                  <span className="text-white/10 text-xs">Canonical writer not active — candidates appear when the fib engine writer is deployed</span>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/5">
                        <TableHead className="text-white/30 text-[10px]">Time</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Dir</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Anchor</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Entry</TableHead>
                        <TableHead className="text-white/30 text-[10px]">SL</TableHead>
                        <TableHead className="text-white/30 text-[10px]">TP1</TableHead>
                        <TableHead className="text-white/30 text-[10px]">TP2</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Fib</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Archetype</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Score</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Decision</TableHead>
                        <TableHead className="text-white/30 text-[10px]">TP1 Prob</TableHead>
                        <TableHead className="text-white/30 text-[10px]">TP2 Prob</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Rev Risk</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Target Hit</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Outcome</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Packet</TableHead>
                        <TableHead className="text-white/30 text-[10px]">Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.candidates.map((c) => (
                        <TableRow key={c.candidate_id} className="border-white/5">
                          <TableCell className="text-white/50 text-xs font-mono">{formatTs(c.bar_close_ts)}</TableCell>
                          <TableCell className={`text-xs font-medium ${directionColor(c.direction)}`}>{c.direction}</TableCell>
                          <TableCell className="text-white/60 text-xs tabular-nums">{formatPrice(c.anchor_price)}</TableCell>
                          <TableCell className="text-white/60 text-xs tabular-nums">{formatPrice(c.entry_price)}</TableCell>
                          <TableCell className="text-red-400/60 text-xs tabular-nums">{formatPrice(c.stop_loss)}</TableCell>
                          <TableCell className="text-emerald-400/60 text-xs tabular-nums">{formatPrice(c.tp1_price)}</TableCell>
                          <TableCell className="text-emerald-400/60 text-xs tabular-nums">{formatPrice(c.tp2_price)}</TableCell>
                          <TableCell className="text-white/40 text-xs">{c.fib_level_touched ?? "—"}</TableCell>
                          <TableCell className="text-white/40 text-xs">{c.setup_archetype ?? "—"}</TableCell>
                          <TableCell className="text-white/50 text-xs tabular-nums">{c.confidence_score != null ? c.confidence_score.toFixed(0) : "—"}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className={`text-[10px] ${decisionBadgeColor(c.decision_code)}`}>
                              {c.decision_code ?? "—"}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-white/50 text-xs tabular-nums">{formatPct(c.tp1_probability)}</TableCell>
                          <TableCell className="text-white/50 text-xs tabular-nums">{formatPct(c.tp2_probability)}</TableCell>
                          <TableCell className="text-white/50 text-xs tabular-nums">{formatPct(c.reversal_risk)}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className={`text-[10px] ${targetBadgeColor(c.target_hit_state)}`}>
                              {c.target_hit_state}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className={`text-[10px] ${outcomeBadgeColor(c.outcome_state)}`}>
                              {c.outcome_state}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-white/40 text-xs font-mono">{c.packet_id ? c.packet_id.slice(0, 8) : "—"}</TableCell>
                          <TableCell className="text-white/40 text-xs">{c.status}</TableCell>
                        </TableRow>
                      ))}
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
              <CardTitle className="text-white text-sm">Job Log — Last 50 Runs</CardTitle>
              <CardDescription className="text-white/30 text-xs">All cron job executions</CardDescription>
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
                          <TableCell className="text-white/50 text-xs font-mono">{formatTs(j.created_at)}</TableCell>
                          <TableCell className="text-white/70 text-xs font-mono">{j.job_name}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className={`text-[10px] ${jobStatusColor(j.status)}`}>{j.status}</Badge>
                          </TableCell>
                          <TableCell className="text-white/50 text-xs tabular-nums">{j.rows_affected ?? "—"}</TableCell>
                          <TableCell className="text-white/40 text-xs tabular-nums">{j.duration_ms != null ? `${j.duration_ms}ms` : "—"}</TableCell>
                          <TableCell className="text-red-400/60 text-xs max-w-[200px] truncate">{j.error_message ?? "—"}</TableCell>
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
              <CardTitle className="text-white text-sm">Symbols ({data.symbols.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {data.symbols.map((s) => (
                  <div
                    key={s.code}
                    className="flex items-center justify-between px-3 py-2 rounded-md bg-white/[0.02] border border-white/[0.04]"
                  >
                    <div className="flex flex-col">
                      <span className="text-white/70 text-xs font-mono">{s.code}</span>
                      <span className="text-white/30 text-[10px]">{s.display_name} — {s.data_source}</span>
                    </div>
                    <Badge variant="outline" className={`text-[10px] ${s.is_active ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" : "bg-zinc-500/20 text-zinc-400 border-zinc-500/30"}`}>
                      {s.is_active ? "ACTIVE" : "OFF"}
                    </Badge>
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

function SummaryCard({ label, value, alert }: { label: string; value: string; alert?: boolean }) {
  return (
    <Card className="bg-white/[0.02] border-white/[0.06]">
      <CardContent className="pt-4 pb-3 px-4">
        <div className={`text-lg font-semibold tracking-tight ${alert ? "text-red-400" : "text-white"}`}>{value}</div>
        <div className="text-white/30 text-[10px] mt-0.5">{label}</div>
      </CardContent>
    </Card>
  );
}

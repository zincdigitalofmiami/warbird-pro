"use client";

import {
  useEffect,
  useRef,
  useState,
  useMemo,
  forwardRef,
  useImperativeHandle,
} from "react";
import Image from "next/image";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  IChartApi,
  ISeriesApi,
  LineSeries,
  LineStyle,
  TickMarkType,
  Time,
  UTCTimestamp,
} from "lightweight-charts";
import { createClient } from "@/lib/supabase/client";
import type { CandleData, FibResult } from "@/lib/types";
import { ForecastTargetsPrimitive } from "@/lib/charts/ForecastTargetsPrimitive";
import { SetupMarkersPrimitive } from "@/lib/charts/SetupMarkersPrimitive";
import { FibLinesPrimitive } from "@/lib/charts/FibLinesPrimitive";
import { ensureFutureWhitespace } from "@/lib/charts/ensureFutureWhitespace";
import { calculateFibonacciMultiPeriod } from "@/lib/fibonacci";
import { getEventDisplayPhase } from "@/lib/event-display";
import type { SetupCandidate } from "@/lib/setup-candidates";
import { RegimeAnchorPrimitive } from "@/lib/charts/RegimeAnchorPrimitive";
import { REGIME_LABEL, REGIME_START_ISO } from "@/lib/warbird/constants";
import { warbirdSignalToTargets } from "@/lib/warbird/projection";
import type { WarbirdSignal } from "@/lib/warbird/types";
import TV from "@/lib/colors";

type MesPoint = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

type StreamStatus = "connecting" | "live" | "stale" | "error";

const BAR_INTERVAL_SEC = 900; // 15m
const GO_RECENT_BARS = 32; // ~8 hours of 15m bars
const INITIAL_VISIBLE_BARS = 120;
const RIGHT_PADDING_BARS = 16;
const DEFAULT_BAR_SPACING = 10;
const MIN_BAR_SPACING = 8;
const MAX_TOUCH_MARKERS = 1;
const MAX_HOOK_MARKERS = 1;

// ─── Gap-Free Time Mapping ──────────────────────────────────────────────────

interface TimeMap {
  realToGf: Map<number, number>;
  gfToReal: Map<number, number>;
  baseTime: number;
}

function buildGapFreeMapping(points: MesPoint[]): {
  gfPoints: MesPoint[];
  map: TimeMap;
} {
  if (points.length === 0) {
    return {
      gfPoints: [],
      map: { realToGf: new Map(), gfToReal: new Map(), baseTime: 0 },
    };
  }

  const baseTime = points[0].time;
  const realToGf = new Map<number, number>();
  const gfToReal = new Map<number, number>();

  const gfPoints = points.map((p, i) => {
    const gfTime = baseTime + i * BAR_INTERVAL_SEC;
    realToGf.set(p.time, gfTime);
    gfToReal.set(gfTime, p.time);
    return { ...p, time: gfTime };
  });

  return { gfPoints, map: { realToGf, gfToReal, baseTime } };
}

/** Format a real UTC timestamp for the time axis (Central Time) */
function formatRealTime(
  realTimeSec: number,
  tickMarkType: TickMarkType,
): string {
  const d = new Date(realTimeSec * 1000);
  switch (tickMarkType) {
    case TickMarkType.Year:
      return d.toLocaleDateString("en-US", {
        year: "numeric",
        timeZone: "America/Chicago",
      });
    case TickMarkType.Month:
      return d.toLocaleDateString("en-US", {
        month: "short",
        timeZone: "America/Chicago",
      });
    case TickMarkType.DayOfMonth:
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        timeZone: "America/Chicago",
      });
    case TickMarkType.Time:
    case TickMarkType.TimeWithSeconds:
    default:
      return d.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
        timeZone: "America/Chicago",
      });
  }
}

// ─── Chart Helpers ──────────────────────────────────────────────────────────

function toChartPoint(point: MesPoint) {
  return {
    time: point.time as UTCTimestamp,
    open: point.open,
    high: point.high,
    low: point.low,
    close: point.close,
  };
}

function toCandle(point: MesPoint): CandleData {
  return {
    time: point.time,
    open: point.open,
    high: point.high,
    low: point.low,
    close: point.close,
    volume: point.volume,
  };
}

function setupSortTime(setup: SetupCandidate): number {
  return setup.goTime ?? setup.hookTime ?? setup.touchTime ?? setup.createdAt;
}

function isRenderableGoSetup(setup: SetupCandidate): boolean {
  if (setup.phase !== "TRIGGERED") return false;
  if (
    setup.entry == null ||
    setup.stopLoss == null ||
    setup.tp1 == null ||
    setup.tp2 == null
  )
    return false;

  if (setup.direction === "BULLISH") {
    return (
      setup.stopLoss < setup.entry &&
      setup.tp1 > setup.entry &&
      setup.tp2 >= setup.tp1
    );
  }
  return (
    setup.tp2 <= setup.tp1 &&
    setup.tp1 < setup.entry &&
    setup.stopLoss > setup.entry
  );
}

function selectSetupsForChart(
  setups: SetupCandidate[],
  lastTimeSec: number | null,
): SetupCandidate[] {
  if (setups.length === 0) return [];

  const goCandidates = setups
    .filter(isRenderableGoSetup)
    .sort((a, b) => setupSortTime(b) - setupSortTime(a));

  const recentGoCandidates =
    lastTimeSec == null
      ? goCandidates
      : goCandidates.filter(
          (s) =>
            s.goTime != null &&
            lastTimeSec - s.goTime <= BAR_INTERVAL_SEC * GO_RECENT_BARS,
        );

  const sourceGo =
    recentGoCandidates.length > 0 ? recentGoCandidates : goCandidates;
  const selectedGo = sourceGo.slice(0, 1);

  const leadDirection = selectedGo[0]?.direction;
  const leadTime = selectedGo[0] ? setupSortTime(selectedGo[0]) : null;

  const selectedHooks = setups
    .filter((s) => s.phase === "CONFIRMED")
    .filter((s) => (leadDirection ? s.direction === leadDirection : true))
    .filter((s) => (leadTime != null ? setupSortTime(s) <= leadTime : true))
    .sort((a, b) => setupSortTime(b) - setupSortTime(a))
    .slice(0, MAX_HOOK_MARKERS);

  const selectedTouches = setups
    .filter((s) => s.phase === "CONTACT")
    .filter((s) => (leadDirection ? s.direction === leadDirection : true))
    .filter((s) => (leadTime != null ? setupSortTime(s) <= leadTime : true))
    .sort((a, b) => setupSortTime(b) - setupSortTime(a))
    .slice(0, MAX_TOUCH_MARKERS);

  return [...selectedGo, ...selectedHooks, ...selectedTouches];
}

export interface LiveMesChartHandle {
  captureScreenshot: () => string | null;
}

interface LiveMesChartProps {
  signal?: WarbirdSignal | null;
  setups?: SetupCandidate[];
  eventPhase?: string;
  eventLabel?: string;
}

const LiveMesChart = forwardRef<LiveMesChartHandle, LiveMesChartProps>(
  function LiveMesChart({ signal, setups, eventPhase, eventLabel }, ref) {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const seriesRef = useRef<ISeriesApi<"Candlestick", Time> | null>(null);
    const whitespaceSeriesRef = useRef<ISeriesApi<"Line", Time> | null>(null);
    const primitiveRef = useRef<ForecastTargetsPrimitive | null>(null);
    const setupPrimitiveRef = useRef<SetupMarkersPrimitive | null>(null);
    const fibPrimitiveRef = useRef<FibLinesPrimitive | null>(null);
    const regimePrimitiveRef = useRef<RegimeAnchorPrimitive | null>(null);
    // Structural break locking — persist fib anchor across ticks
    const lockedFibRef = useRef<FibResult | null>(null);
    const initialViewportAppliedRef = useRef(false);
    const displayEventPhase = getEventDisplayPhase(eventPhase);

    // Gap-free points (sequential times for chart rendering)
    const pointsRef = useRef<MesPoint[]>([]);
    // Original real-time points (for fib calc, session stats, setup time lookup)
    const realPointsRef = useRef<MesPoint[]>([]);
    // Bidirectional time mapping: real ↔ gap-free
    const timeMapRef = useRef<TimeMap>({
      realToGf: new Map(),
      gfToReal: new Map(),
      baseTime: 0,
    });

    const [status, setStatus] = useState<StreamStatus>("connecting");
    const [error, setError] = useState<string | null>(null);
    const [lastPrice, setLastPrice] = useState<number | null>(null);
    const [priceChange, setPriceChange] = useState<number>(0);
    const [sessionHigh, setSessionHigh] = useState<number | null>(null);
    const [sessionLow, setSessionLow] = useState<number | null>(null);

    /** Look up gap-free time for a real timestamp, snapping to nearest 15m bar */
    const realToGapFree = (
      realTime: number | null | undefined,
    ): number | undefined => {
      if (realTime == null) return undefined;
      const { realToGf } = timeMapRef.current;
      const exact = realToGf.get(realTime);
      if (exact != null) return exact;
      const snapped =
        Math.round(realTime / BAR_INTERVAL_SEC) * BAR_INTERVAL_SEC;
      return realToGf.get(snapped);
    };

    const chartSetups = useMemo(
      () =>
        selectSetupsForChart(
          setups ?? [],
          realPointsRef.current[realPointsRef.current.length - 1]?.time ?? null,
        ),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [setups, lastPrice],
    );

    useImperativeHandle(ref, () => ({
      captureScreenshot: () => {
        if (!chartRef.current) return null;
        try {
          const canvas = chartRef.current.takeScreenshot();
          return canvas.toDataURL("image/png");
        } catch {
          return null;
        }
      },
    }));

    // --- Chart setup ---
    useEffect(() => {
      if (!containerRef.current) return;

      const chart = createChart(containerRef.current, {
        autoSize: true,
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: "rgba(255,255,255,0.4)",
          fontFamily: "Inter, sans-serif",
          fontSize: 11,
          attributionLogo: false,
        },
        grid: {
          vertLines: { color: "rgba(255,255,255,0.04)" },
          horzLines: { color: "rgba(255,255,255,0.04)" },
        },
        rightPriceScale: {
          borderColor: "transparent",
          autoScale: true,
          scaleMargins: { top: 0.05, bottom: 0.05 },
        },
        timeScale: {
          borderColor: "transparent",
          timeVisible: true,
          fixLeftEdge: false,
          fixRightEdge: false,
          rightOffset: 16,
          barSpacing: DEFAULT_BAR_SPACING,
          minBarSpacing: MIN_BAR_SPACING,
          lockVisibleTimeRangeOnResize: true,
          tickMarkFormatter: (time: Time, tickMarkType: TickMarkType) => {
            const realTime = timeMapRef.current.gfToReal.get(time as number);
            if (realTime == null) return "";
            return formatRealTime(realTime, tickMarkType);
          },
        },
        localization: {
          timeFormatter: (time: Time) => {
            const realTime = timeMapRef.current.gfToReal.get(time as number);
            if (realTime == null) return "";
            const d = new Date(realTime * 1000);
            return d.toLocaleString("en-US", {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
              hour12: true,
              timeZone: "America/Chicago",
            });
          },
        },
        crosshair: {
          mode: CrosshairMode.Normal,
          vertLine: {
            color: "rgba(255,255,255,0.65)",
            width: 1,
            style: LineStyle.Solid,
            labelBackgroundColor: "rgba(42,46,57,0.95)",
          },
          horzLine: {
            color: "rgba(255,255,255,0.65)",
            width: 1,
            style: LineStyle.Solid,
            labelBackgroundColor: "rgba(42,46,57,0.95)",
          },
        },
        handleScroll: {
          mouseWheel: false,
          pressedMouseMove: false,
          horzTouchDrag: false,
          vertTouchDrag: false,
        },
        handleScale: {
          mouseWheel: false,
          pinch: false,
          axisPressedMouseMove: { time: true, price: true },
          axisDoubleClickReset: { time: true, price: true },
        },
      });

      const series = chart.addSeries(CandlestickSeries, {
        upColor: "#26C6DA",
        downColor: "#FF0000",
        borderUpColor: "transparent",
        borderDownColor: "transparent",
        wickUpColor: "#FFFFFF",
        wickDownColor: "rgba(178,181,190,0.83)",
        priceLineVisible: true,
        lastValueVisible: true,
        priceFormat: {
          type: "price",
          precision: 2,
          minMove: 0.25,
        },
      });

      const whitespaceSeries = chart.addSeries(LineSeries, {
        color: "rgba(255,255,255,0)",
        lineWidth: 1,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
      });

      const primitive = new ForecastTargetsPrimitive();
      series.attachPrimitive(primitive);

      const setupPrimitive = new SetupMarkersPrimitive();
      series.attachPrimitive(setupPrimitive);

      const fibPrimitive = new FibLinesPrimitive();
      series.attachPrimitive(fibPrimitive);

      const regimePrimitive = new RegimeAnchorPrimitive();
      series.attachPrimitive(regimePrimitive);

      chartRef.current = chart;
      seriesRef.current = series;
      whitespaceSeriesRef.current = whitespaceSeries;
      primitiveRef.current = primitive;
      setupPrimitiveRef.current = setupPrimitive;
      fibPrimitiveRef.current = fibPrimitive;
      regimePrimitiveRef.current = regimePrimitive;

      const resizeObserver = new ResizeObserver(() => {
        chart.applyOptions({ autoSize: true });
      });
      resizeObserver.observe(containerRef.current);

      return () => {
        resizeObserver.disconnect();
        series.detachPrimitive(primitive);
        series.detachPrimitive(setupPrimitive);
        series.detachPrimitive(fibPrimitive);
        series.detachPrimitive(regimePrimitive);
        chart.removeSeries(whitespaceSeries);
        chart.remove();
        chartRef.current = null;
        seriesRef.current = null;
        whitespaceSeriesRef.current = null;
        primitiveRef.current = null;
        setupPrimitiveRef.current = null;
        fibPrimitiveRef.current = null;
        regimePrimitiveRef.current = null;
      };
    }, []);

    // --- Live data: Supabase Realtime subscription ---
    useEffect(() => {
      const supabase = createClient();

      const updateSessionStats = (points: MesPoint[]) => {
        if (points.length === 0) return;
        const last = points[points.length - 1];
        setLastPrice(last.close);

        let high = -Infinity;
        let low = Infinity;
        for (const p of points) {
          if (p.high > high) high = p.high;
          if (p.low < low) low = p.low;
        }
        setSessionHigh(high);
        setSessionLow(low);

        const first = points[0];
        if (first.open > 0) {
          setPriceChange(((last.close - first.open) / first.open) * 100);
        }
      };

      const buildWhitespaceData = (
        lastGfTime: number,
        lastRealTime: number,
        map: TimeMap,
      ) => {
        const whitespace = ensureFutureWhitespace(
          lastGfTime,
          BAR_INTERVAL_SEC,
          RIGHT_PADDING_BARS,
        );
        for (let i = 0; i < whitespace.length; i += 1) {
          const wsGfTime = whitespace[i].time as number;
          const wsRealTime = lastRealTime + BAR_INTERVAL_SEC * (i + 1);
          map.gfToReal.set(wsGfTime, wsRealTime);
          map.realToGf.set(wsRealTime, wsGfTime);
        }
        return whitespace;
      };

      const rebuildAndRender = (rawPoints: MesPoint[]) => {
        if (!seriesRef.current || !whitespaceSeriesRef.current || rawPoints.length === 0) return;

        realPointsRef.current = rawPoints;
        const { gfPoints, map } = buildGapFreeMapping(rawPoints);
        timeMapRef.current = map;
        pointsRef.current = gfPoints;

        const lastGfTime = gfPoints[gfPoints.length - 1].time;
        const lastRealTime = rawPoints[rawPoints.length - 1].time;
        const whitespace = buildWhitespaceData(lastGfTime, lastRealTime, map);

        return { gfPoints, whitespace, map };
      };

      const applySnapshot = (rawPoints: MesPoint[]) => {
        try {
          const result = rebuildAndRender(rawPoints);
          if (!result || !seriesRef.current) return;

          seriesRef.current.setData(result.gfPoints.map(toChartPoint));
          whitespaceSeriesRef.current?.setData(result.whitespace);

          updateSessionStats(rawPoints);

          const timeScale = chartRef.current?.timeScale();
          timeScale?.applyOptions({
            barSpacing: DEFAULT_BAR_SPACING,
            minBarSpacing: MIN_BAR_SPACING,
          });

          if (timeScale && !initialViewportAppliedRef.current) {
            const totalBars = result.gfPoints.length;
            const visibleBars = Math.min(INITIAL_VISIBLE_BARS, totalBars);
            const from = Math.max(0, totalBars - visibleBars);
            const to = Math.max(0, totalBars - 1) + RIGHT_PADDING_BARS;
            timeScale.setVisibleLogicalRange({ from, to });
            initialViewportAppliedRef.current = true;
          } else {
            timeScale?.scrollToPosition(RIGHT_PADDING_BARS, false);
          }

          setStatus("live");
          setError(null);
        } catch (e) {
          setStatus("error");
          setError(e instanceof Error ? e.message : "Invalid snapshot");
        }
      };

      const applyRealtimeUpdate = (row: {
        ts: string;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
      }) => {
        try {
          if (!seriesRef.current) return;

          const realTime = Math.floor(new Date(row.ts).getTime() / 1000);
          const newPoint: MesPoint = {
            time: realTime,
            open: Number(row.open),
            high: Number(row.high),
            low: Number(row.low),
            close: Number(row.close),
            volume: Number(row.volume),
          };

          // Check if this is an intrabar update (same timestamp exists)
          const existingIdx = realPointsRef.current.findIndex(
            (p) => p.time === realTime,
          );

          if (existingIdx >= 0) {
            // Intrabar update — use series.update() for efficiency
            realPointsRef.current[existingIdx] = newPoint;
            const gfTime = timeMapRef.current.realToGf.get(realTime);
            if (gfTime != null) {
              seriesRef.current.update({
                time: gfTime as UTCTimestamp,
                open: newPoint.open,
                high: newPoint.high,
                low: newPoint.low,
                close: newPoint.close,
              });
            }
          } else if (
            realPointsRef.current.length === 0 ||
            realTime > realPointsRef.current[realPointsRef.current.length - 1].time
          ) {
            realPointsRef.current = [...realPointsRef.current, newPoint];
            const lastGfTime =
              pointsRef.current.length > 0
                ? pointsRef.current[pointsRef.current.length - 1].time
                : realTime;
            const nextGfTime =
              pointsRef.current.length > 0
                ? lastGfTime + BAR_INTERVAL_SEC
                : realTime;

            timeMapRef.current.realToGf.set(realTime, nextGfTime);
            timeMapRef.current.gfToReal.set(nextGfTime, realTime);

            const gfPoint = { ...newPoint, time: nextGfTime };
            pointsRef.current = [...pointsRef.current, gfPoint];
            seriesRef.current.update(toChartPoint(gfPoint));

            const whitespace = buildWhitespaceData(
              nextGfTime,
              realTime,
              timeMapRef.current,
            );
            whitespaceSeriesRef.current?.setData(whitespace);
          } else {
            // Out-of-order bar — merge and rebuild gap-free mapping
            const realByTime = new Map(
              realPointsRef.current.map((p) => [p.time, p] as const),
            );
            realByTime.set(realTime, newPoint);
            const newRealPoints = [...realByTime.values()].sort(
              (a, b) => a.time - b.time,
            );

            const result = rebuildAndRender(newRealPoints);
            if (!result) return;

            const range =
              chartRef.current?.timeScale().getVisibleLogicalRange();
            seriesRef.current.setData(result.gfPoints.map(toChartPoint));
            whitespaceSeriesRef.current?.setData(result.whitespace);
            if (range) {
              chartRef.current?.timeScale().setVisibleLogicalRange(range);
            }
          }

          updateSessionStats(realPointsRef.current);
          setStatus("live");
          setError(null);
        } catch (e) {
          setStatus("error");
          setError(e instanceof Error ? e.message : "Invalid update");
        }
      };

      let cancelled = false;

      async function startRealtimeFeed() {
        try {
          // Initial snapshot from API
          const snapshotRes = await fetch(
            "/api/live/mes15m?snapshot=1&backfill=1000",
            { cache: "no-store" },
          );
          const snapshotData = (await snapshotRes.json()) as
            | { points: MesPoint[]; live?: boolean }
            | { error: string };

          if (cancelled) return;
          if (!snapshotRes.ok || !("points" in snapshotData)) {
            throw new Error(
              "error" in snapshotData
                ? snapshotData.error
                : "Failed to load MES 15m snapshot",
            );
          }

          applySnapshot(snapshotData.points || []);
        } catch (e) {
          if (cancelled) return;
          setStatus("error");
          setError(
            e instanceof Error
              ? e.message
              : "Failed to load initial chart data.",
          );
        }
      }

      // Subscribe to Supabase Realtime for mes_15m updates
      const channel = supabase
        .channel("mes_15m_realtime")
        .on(
          "postgres_changes",
          {
            event: "*",
            schema: "public",
            table: "mes_15m",
          },
          (payload) => {
            if (cancelled) return;
            const row = payload.new as {
              ts: string;
              open: number;
              high: number;
              low: number;
              close: number;
              volume: number;
            };
            if (row?.ts) {
              applyRealtimeUpdate(row);
            }
          },
        )
        .subscribe((status) => {
          if (status === "SUBSCRIBED") {
            // Realtime channel active
          }
        });

      startRealtimeFeed();

      return () => {
        cancelled = true;
        supabase.removeChannel(channel);
      };
    }, []);

    // --- Wire Warbird forecast targets to primitive ---
    useEffect(() => {
      if (!primitiveRef.current) return;

      if (!signal || pointsRef.current.length === 0) {
        primitiveRef.current.setTargets([]);
        return;
      }

      const gfPoints = pointsRef.current;
      const lastGfTime = gfPoints[gfPoints.length - 1].time;
      const futureEnd = lastGfTime + BAR_INTERVAL_SEC * 16;

      const targets = warbirdSignalToTargets(
        signal,
        lastGfTime,
        futureEnd,
      );

      primitiveRef.current.setTargets(targets);
    }, [signal, lastPrice]);

    // --- Wire setup candidates to primitive ---
    useEffect(() => {
      if (!setupPrimitiveRef.current) return;

      if (
        !chartSetups ||
        chartSetups.length === 0 ||
        pointsRef.current.length === 0
      ) {
        setupPrimitiveRef.current.setMarkers(null);
        return;
      }

      const lastGfTime = pointsRef.current[pointsRef.current.length - 1].time;

      const mappedSetups = chartSetups.map((s) => ({
        ...s,
        touchTime:
          s.touchTime != null
            ? (realToGapFree(s.touchTime) ?? s.touchTime)
            : s.touchTime,
        hookTime:
          s.hookTime != null
            ? (realToGapFree(s.hookTime) ?? s.hookTime)
            : s.hookTime,
        goTime:
          s.goTime != null ? (realToGapFree(s.goTime) ?? s.goTime) : s.goTime,
      }));

      setupPrimitiveRef.current.setMarkers({
        setups: mappedSetups,
        lastTime: lastGfTime,
        futureBars: 16,
        barInterval: BAR_INTERVAL_SEC,
      });
    }, [chartSetups, lastPrice]);

    // --- Compute and wire fibonacci levels from candle data (with structural break locking) ---
    useEffect(() => {
      if (!fibPrimitiveRef.current) return;

      const realPoints = realPointsRef.current;
      if (realPoints.length < 55) {
        fibPrimitiveRef.current.setFibResult(null);
        lockedFibRef.current = null;
        return;
      }

      const currentPrice = realPoints[realPoints.length - 1].close;
      const locked = lockedFibRef.current;

      // Structural break locking: if current price is within the locked anchor
      // range, keep the existing fib (don't recompute to a narrower range)
      if (locked && currentPrice <= locked.anchorHigh && currentPrice >= locked.anchorLow) {
        const anchorIdx = Math.min(locked.anchorHighBarIndex, locked.anchorLowBarIndex);
        const anchorGfTime = pointsRef.current.length > anchorIdx
          ? pointsRef.current[anchorIdx].time
          : undefined;
        fibPrimitiveRef.current.setFibResult(locked, anchorGfTime);
        return;
      }

      // Structural break OR first computation — recompute
      const candles = realPoints.map(toCandle);
      const fibResult = calculateFibonacciMultiPeriod(candles);
      if (!fibResult) {
        fibPrimitiveRef.current.setFibResult(null);
        lockedFibRef.current = null;
        return;
      }

      // Lock the new anchor
      lockedFibRef.current = fibResult;

      const anchorIdx = Math.min(
        fibResult.anchorHighBarIndex,
        fibResult.anchorLowBarIndex,
      );
      const anchorGfTime =
        pointsRef.current.length > anchorIdx
          ? pointsRef.current[anchorIdx].time
          : undefined;

      fibPrimitiveRef.current.setFibResult(fibResult, anchorGfTime);
    }, [lastPrice]);

    useEffect(() => {
      if (!regimePrimitiveRef.current) return;
      const regimeTime = realToGapFree(
        Math.floor(new Date(REGIME_START_ISO).getTime() / 1000),
      );

      regimePrimitiveRef.current.setAnchor(
        regimeTime != null
          ? {
              time: regimeTime,
              label: `Regime ${REGIME_LABEL} · Jan 20 2025`,
              color: "rgba(255,152,0,0.8)",
            }
          : null,
      );
    }, [lastPrice]);

    const changeColor = priceChange >= 0 ? TV.bull.bright : TV.bear.bright;

    return (
      <div
        className="relative w-full rounded-xl overflow-hidden border border-white/5"
        style={{
          background: "linear-gradient(180deg, #131722 0%, #0d1117 100%)",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div
                className="w-2 h-2 rounded-full animate-pulse shadow-lg"
                style={{
                  backgroundColor:
                    status === "live"
                      ? "#26C6DA"
                      : status === "connecting"
                        ? "#F23645"
                        : "#FF0000",
                  boxShadow:
                    status === "live" ? "0 0 8px rgba(38,198,218,0.5)" : "none",
                }}
              />
              <span className="text-base font-semibold text-white tracking-tight">
                MES
              </span>
            </div>
            <span className="text-xs text-white/30 font-medium">
              Micro E-mini S&P 500 &bull; 15m
            </span>
            {eventPhase && eventPhase !== "CLEAR" && (
              <span
                title={eventLabel ?? undefined}
                className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border ${
                  displayEventPhase === "LOCKOUT"
                    ? "bg-red-500/10 text-red-400 border-red-500/20"
                    : displayEventPhase === "WATCH"
                      ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
                      : displayEventPhase === "REPRICE"
                          ? "bg-blue-500/10 text-blue-400 border-blue-500/20"
                          : "bg-white/5 text-white/40 border-white/10"
                }`}
              >
                {displayEventPhase}
              </span>
            )}
          </div>

          <div className="flex items-center gap-6">
            {sessionHigh != null && sessionLow != null && (
              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-1.5">
                  <span className="text-white/30">H</span>
                  <span className="text-white/60 font-mono tabular-nums">
                    {sessionHigh.toFixed(2)}
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-white/30">L</span>
                  <span className="text-white/60 font-mono tabular-nums">
                    {sessionLow.toFixed(2)}
                  </span>
                </div>
              </div>
            )}

            {sessionHigh != null && <div className="h-4 w-px bg-white/10" />}

            {lastPrice != null && (
              <div className="flex items-center gap-3">
                <span className="text-2xl font-semibold text-white tabular-nums">
                  {lastPrice.toFixed(2)}
                </span>
                <span
                  className="text-sm font-medium tabular-nums"
                  style={{ color: changeColor }}
                >
                  {priceChange >= 0 ? "+" : ""}
                  {priceChange.toFixed(2)}%
                </span>
              </div>
            )}

            <span
              className="text-[10px] font-bold uppercase tracking-wider"
              style={{
                color:
                  status === "live"
                    ? "#26C6DA"
                    : status === "connecting"
                      ? "#F23645"
                      : "#FF0000",
              }}
            >
              {status}
            </span>
          </div>
        </div>

        {/* Chart */}
        <div className="relative w-full" style={{ height: "80vh" }}>
          <div className="absolute bottom-12 left-3 z-20 rounded-md border border-orange-500/25 bg-black/35 px-3 py-1.5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-orange-300/80">
              Regime Anchor
            </div>
            <div className="text-[11px] text-white/70">
              {REGIME_LABEL} · Jan 20, 2025
            </div>
          </div>
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
            <Image
              src="/chart_watermark.svg"
              alt=""
              width={300}
              height={300}
              className="opacity-[0.25]"
              unoptimized
              priority
            />
          </div>
          <div ref={containerRef} className="absolute inset-0 z-10" />
        </div>

        {/* Legend Footer */}
        <div className="flex items-center justify-center gap-8 px-6 py-3 border-t border-white/5 bg-black/20">
          <div className="flex items-center gap-2">
            <div
              className="w-3 h-4 rounded-sm"
              style={{ backgroundColor: "#26C6DA" }}
            />
            <span className="text-[10px] text-white/40 uppercase tracking-wider">
              Bullish
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div
              className="w-3 h-4 rounded-sm"
              style={{ backgroundColor: "#FF0000" }}
            />
            <span className="text-[10px] text-white/40 uppercase tracking-wider">
              Bearish
            </span>
          </div>
          <div className="h-3 w-px bg-white/10" />
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-px" style={{ backgroundColor: "#FFFFFF" }} />
            <span className="text-[10px] text-white/40 uppercase tracking-wider">
              Anchor
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-px" style={{ backgroundColor: "#00BCD4" }} />
            <span className="text-[10px] text-white/40 uppercase tracking-wider">
              Fib
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-px" style={{ backgroundColor: "#FF9800" }} />
            <span className="text-[10px] text-white/40 uppercase tracking-wider">
              Pivot
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-px" style={{ backgroundColor: "#4CAF50" }} />
            <span className="text-[10px] text-white/40 uppercase tracking-wider">
              Target
            </span>
          </div>
          {setups && setups.length > 0 && (
            <>
              <div className="flex items-center gap-2">
                <div
                  className="w-2.5 h-2.5 rotate-45"
                  style={{ backgroundColor: "#26C6DA" }}
                />
                <span className="text-[10px] text-white/40 uppercase tracking-wider">
                  Setup
                </span>
              </div>
            </>
          )}
        </div>

        {/* Error banner */}
        {error && (
          <div className="px-6 py-2 border-t border-white/5">
            <p className="text-xs text-red-400">{error}</p>
          </div>
        )}
      </div>
    );
  },
);

export default LiveMesChart;

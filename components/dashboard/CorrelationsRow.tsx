"use client";

// Intermarket Full Agreement Panel
// 6 boxes: NQ, ZN, CL, SPX Vol, YM, NYSE — all from Supabase hourly bars.
// Each lane computes its directional MES impact (in bps) server-side:
//   mes_bps_i = weight_i * beta(MES|i) * ret_i * vol_weight_i * confidence_i
// IM Score is the sum of all weighted lane MES impacts in basis points.

interface TickerConfig {
  label: string;
  symbolCode: string;
  sublabel: string;
}

const TICKERS: TickerConfig[] = [
  { label: "NQ", symbolCode: "NQ", sublabel: "Nasdaq" },
  { label: "ZN", symbolCode: "ZN", sublabel: "10Y Treasury" },
  { label: "CL", symbolCode: "CL", sublabel: "Crude Oil" },
  { label: "SPXVOL", symbolCode: "SPXVOL", sublabel: "S&P Realized Vol" },
  { label: "YM", symbolCode: "YM", sublabel: "Dow Futures" },
  { label: "NYSE", symbolCode: "NYSE", sublabel: "NYSE Futures" },
];

const MES_BPS_NEUTRAL_THRESHOLD = 0.75;

interface CorrelationsRowProps {
  correlations: Record<
    string,
    {
      close: number;
      prevClose: number;
      changePct?: number;
      impact?: number;
      mesBps?: number;
      mesBpsRaw?: number;
      confidence?: number;
      rvol?: number | null;
    }
  > | null;
}

function computeImpactState(mesBps: number | null): -1 | 0 | 1 {
  if (mesBps == null || !Number.isFinite(mesBps)) return 0;
  if (mesBps > MES_BPS_NEUTRAL_THRESHOLD) return 1;
  if (mesBps < -MES_BPS_NEUTRAL_THRESHOLD) return -1;
  return 0;
}

function stateLabel(state: -1 | 0 | 1): string {
  if (state === 1) return "▲";
  if (state === -1) return "▼";
  return "—";
}

function stateColor(state: -1 | 0 | 1): string {
  if (state === 1) return "#26a65b";
  if (state === -1) return "#F23645";
  return "rgba(255,255,255,0.20)";
}

export default function CorrelationsRow({ correlations }: CorrelationsRowProps) {
  // Compute per-symbol data
  const tickerData = TICKERS.map((ticker) => {
    const data = correlations?.[ticker.symbolCode] ?? null;
    const close = data?.close ?? null;
    const prevClose = data?.prevClose ?? null;
    const changePct = data?.changePct ?? (
      close != null && prevClose != null && prevClose !== 0
        ? ((close - prevClose) / prevClose) * 100
        : null
    );
    const impact = Number.isFinite(data?.impact) ? Number(data?.impact) : 0;
    const mesBps = Number.isFinite(data?.mesBps)
      ? Number(data?.mesBps)
      : impact * 10;
    const confidence = Number.isFinite(data?.confidence) ? Number(data?.confidence) : 0;
    const rvol = data?.rvol ?? null;
    const atomicState = computeImpactState(mesBps);
    return { ticker, close, prevClose, changePct, impact, mesBps, confidence, rvol, atomicState };
  });

  const states = tickerData.map((d) => d.atomicState);

  // Strict consensus: all must agree for colored background
  const allLongAligned = states.every((v) => v === 1);
  const allShortAligned = states.every((v) => v === -1);
  const globalBg = allLongAligned
    ? "rgba(38, 166, 91, 0.15)"
    : allShortAligned
      ? "rgba(242, 54, 69, 0.15)"
      : "transparent";

  // Weighted IM score in MES bps (lane contributions are pre-weighted server-side)
  const imScore = tickerData.reduce(
    (sum, d) => sum + d.mesBps,
    0,
  );

  return (
    <div
      className="flex flex-col w-full flex-shrink-0"
      style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
    >
      {/* Symbol boxes */}
      <div className="flex items-center gap-0 w-full overflow-x-auto">
        {tickerData.map(({ ticker, close, changePct, mesBps, confidence, rvol, atomicState }) => {
          const changeColor =
            changePct == null
              ? "rgba(255,255,255,0.15)"
              : changePct >= 0
                ? "#26C6DA"
                : "#F23645";

          return (
            <div
              key={ticker.label}
              className="flex-1 min-w-[90px] px-3 py-1.5 flex flex-col gap-0"
              style={{
                background: globalBg,
                borderRight: "1px solid rgba(255,255,255,0.04)",
                transition: "background 0.3s ease",
                opacity: clamp(0.45 + confidence * 0.55, 0.45, 1),
              }}
            >
              <div className="flex items-center gap-1.5">
                <span
                  className="text-[11px] font-bold"
                  style={{ color: stateColor(atomicState) }}
                >
                  {stateLabel(atomicState)}
                </span>
                <span className="text-[11px] font-semibold text-white/80 tracking-wide">
                  {ticker.label}
                </span>
                <span className="text-[9px] text-white/25 uppercase tracking-wider">
                  {ticker.sublabel}
                </span>
              </div>
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="text-sm font-medium text-white/70 tabular-nums">
                  {close != null ? formatPrice(close, ticker.symbolCode) : "—"}
                </span>
                {changePct != null ? (
                  <span
                    className="text-[10px] font-medium tabular-nums"
                    style={{ color: changeColor }}
                  >
                    {changePct >= 0 ? "+" : ""}
                    {changePct.toFixed(2)}%
                  </span>
                ) : (
                  <span className="text-[10px] text-white/15">—</span>
                )}
                <span
                  className="text-[10px] font-medium tabular-nums"
                  style={{
                    color:
                      mesBps > MES_BPS_NEUTRAL_THRESHOLD
                        ? "#26C6DA"
                        : mesBps < -MES_BPS_NEUTRAL_THRESHOLD
                          ? "#F23645"
                          : "rgba(255,255,255,0.28)",
                  }}
                >
                  MES {mesBps >= 0 ? "+" : ""}
                  {mesBps.toFixed(1)}bp
                </span>
                {rvol != null && Number.isFinite(rvol) ? (
                  <span className="text-[9px] text-white/35 tabular-nums">
                    RV {rvol.toFixed(2)}x
                  </span>
                ) : null}
              </div>
            </div>
          );
        })}

        {/* IM Score badge */}
        <div
          className="flex-none min-w-[80px] px-3 py-1.5 flex flex-col items-center justify-center gap-0"
          style={{
            background: globalBg,
            borderLeft: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          <span className="text-[9px] text-white/30 uppercase tracking-wider font-medium">
            IM Score
          </span>
          <span
            className="text-sm font-bold tabular-nums"
            style={{
              color: imScore > 2.5
                ? "#26a65b"
                : imScore < -2.5
                  ? "#F23645"
                  : "rgba(255,255,255,0.40)",
            }}
          >
            {imScore >= 0 ? "+" : ""}
            {imScore.toFixed(1)}bp
          </span>
        </div>
      </div>
    </div>
  );
}

function formatPrice(price: number, symbolCode: string): string {
  if (symbolCode === "ZN") return price.toFixed(3);
  if (symbolCode === "SPXVOL") return price.toFixed(2);
  return price.toFixed(2);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

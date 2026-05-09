"use client";

// Intermarket Full Agreement Panel
// 6 boxes: NQ, ZN, CL, SPX Vol, YM, NYSE — all from Supabase hourly bars.
// Each lane computes its directional MES impact (in bps) server-side:
//   mes_bps_i = weight_i * beta(MES|i) * ret_i * vol_weight_i * confidence_i
// Pressure % splits total absolute pressure into UP vs DOWN buckets.

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
const PRESSURE_DOMINANCE_THRESHOLD_PCT = 55;

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

  const upPressureBps = tickerData.reduce((sum, d) => sum + Math.max(0, d.mesBps), 0);
  const downPressureBps = tickerData.reduce((sum, d) => sum + Math.max(0, -d.mesBps), 0);
  const totalAbsPressureBps = upPressureBps + downPressureBps;
  const upPressurePct = totalAbsPressureBps > 0 ? (upPressureBps / totalAbsPressureBps) * 100 : 50;
  const downPressurePct = 100 - upPressurePct;
  const confluencePct = Math.max(upPressurePct, downPressurePct);

  const netUpDominant = upPressurePct >= PRESSURE_DOMINANCE_THRESHOLD_PCT;
  const netDownDominant = downPressurePct >= PRESSURE_DOMINANCE_THRESHOLD_PCT;
  const globalBg = netUpDominant
    ? "rgba(38, 198, 218, 0.10)"
    : netDownDominant
      ? "rgba(242, 54, 69, 0.14)"
      : "transparent";

  return (
    <div
      className="flex flex-col w-full flex-shrink-0"
      style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
    >
      {/* Symbol boxes */}
      <div className="flex items-center gap-0 w-full overflow-x-auto">
        {tickerData.map(({ ticker, close, changePct, mesBps, confidence, rvol, atomicState }) => {
          const lanePressurePct = totalAbsPressureBps > 0
            ? (Math.abs(mesBps) / totalAbsPressureBps) * 100
            : 0;
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
                <span className="text-[9px] text-white/38 tabular-nums">
                  P {lanePressurePct.toFixed(0)}%
                </span>
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
            MES Pressure
          </span>
          <span
            className="text-2xl leading-none font-extrabold tabular-nums"
            style={{
              color: netUpDominant
                ? "#26C6DA"
                : netDownDominant
                  ? "#F23645"
                  : "rgba(255,255,255,0.40)",
            }}
          >
            {confluencePct.toFixed(0)}%
          </span>
          <span className="text-[9px] text-white/35 uppercase tracking-wide">Confluence</span>
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

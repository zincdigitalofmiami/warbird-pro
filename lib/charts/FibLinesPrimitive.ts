/**
 * Lightweight Charts Series Primitive: Auto Fib Retracement
 *
 * Matches Kirk's TradingView Auto Fib Retracement EXACTLY.
 * Settings: Depth=10, Deviation=3, Reverse=checked
 *
 * 10 levels total:
 *   ZERO (0)       — white, width 2
 *   .236           — cyan, width 1
 *   .382           — cyan, width 1
 *   Pivot (.5)     — orange, width 2, zone fill
 *   .618           — cyan, width 1
 *   .786           — cyan, width 1
 *   1              — white, width 2
 *   TARGET 1 (1.236) — green, width 1
 *   TARGET 2 (1.618) — green, width 1
 *   TARGET 3 (2.0)   — green, width 1
 *
 * Colors from Kirk's TradingView:
 *   Anchors (0, 1) = white
 *   Retracements (.236, .382, .618, .786) = cyan
 *   Pivot (.5) = orange
 *   Targets (1.236, 1.618, 2.0) = green
 */

import type {
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
  SeriesType,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  ISeriesPrimitiveAxisView,
  AutoscaleInfo,
  Coordinate,
} from "lightweight-charts";
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type { FibResult } from "@/lib/types";

// --- Colors matching Kirk's TradingView Auto Fib ---
const COLORS = {
  anchor: "#FFFFFF",      // white — 0 and 1 levels
  retracement: "#00BCD4", // cyan — .236, .382, .618, .786
  pivot: "#FF9800",       // orange — .5 level
  target: "#4CAF50",      // green — TARGET 1, 2, 3
} as const;

// --- All 10 fib ratios ---
const ALL_LEVELS: { ratio: number; label: string; color: string; width: number }[] = [
  { ratio: 0,     label: "ZERO",     color: COLORS.anchor,      width: 2 },
  { ratio: 0.236, label: ".236",     color: COLORS.retracement, width: 1 },
  { ratio: 0.382, label: ".382",     color: COLORS.retracement, width: 1 },
  { ratio: 0.5,   label: "Pivot",    color: COLORS.pivot,       width: 2 },
  { ratio: 0.618, label: ".618",     color: COLORS.retracement, width: 1 },
  { ratio: 0.786, label: ".786",     color: COLORS.retracement, width: 1 },
  { ratio: 1.0,   label: "1",        color: COLORS.anchor,      width: 2 },
  { ratio: 1.236, label: "TARGET 1", color: COLORS.target,      width: 1 },
  { ratio: 1.618, label: "TARGET 2", color: COLORS.target,      width: 1 },
  { ratio: 2.0,   label: "TARGET 3", color: COLORS.target,      width: 1 },
];

const PIVOT_FILL_OPACITY = 0.08; // Subtle orange zone around pivot

// --- Visual element for rendering ---

interface FibElement {
  price: number;
  label: string;
  color: string;
  lineWidth: number;
}

interface ZoneBand {
  topPrice: number;
  botPrice: number;
  color: string;
}

// --- Renderer ---

class FibRenderer implements IPrimitivePaneRenderer {
  private _elements: FibElement[] = [];
  private _zone: ZoneBand | null = null;
  private _priceToY: ((price: number) => Coordinate | null) | null = null;
  private _anchorStartX: number | null = null;

  update(
    elements: FibElement[],
    zone: ZoneBand | null,
    priceToY: (price: number) => Coordinate | null,
    anchorStartX: number | null,
  ) {
    this._elements = elements;
    this._zone = zone;
    this._priceToY = priceToY;
    this._anchorStartX = anchorStartX;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      if (!this._priceToY) return;

      const x0 = this._anchorStartX != null
        ? Math.max(0, this._anchorStartX)
        : 0;
      if (x0 >= mediaSize.width) return;

      // Draw zone fill first (behind everything)
      if (this._zone) {
        const topY = this._priceToY(this._zone.topPrice);
        const botY = this._priceToY(this._zone.botPrice);
        if (topY != null && botY != null) {
          const y0 = Math.min(topY, botY);
          const h = Math.abs(botY - topY);
          ctx.fillStyle = hexToRgba(this._zone.color, PIVOT_FILL_OPACITY);
          ctx.fillRect(x0, y0, mediaSize.width - x0, h);
        }
      }

      // Draw lines + labels
      for (const el of this._elements) {
        const y = this._priceToY(el.price);
        if (y == null) continue;
        if (y < -30 || y > mediaSize.height + 30) continue;

        // Solid horizontal line
        ctx.strokeStyle = hexToRgba(el.color, 0.85);
        ctx.lineWidth = el.lineWidth;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(mediaSize.width, y);
        ctx.stroke();

        // Label — right-aligned like TradingView
        ctx.font = '10px -apple-system, BlinkMacSystemFont, "Inter", sans-serif';
        ctx.fillStyle = hexToRgba(el.color, 0.9);
        ctx.textBaseline = "bottom";
        ctx.textAlign = "right";
        ctx.fillText(
          `${el.label}  ${el.price.toFixed(2)}`,
          mediaSize.width - 70,
          y - 3,
        );
      }
    });
  }
}

// --- Pane View ---

class FibPaneView implements IPrimitivePaneView {
  private _renderer = new FibRenderer();

  update(
    elements: FibElement[],
    zone: ZoneBand | null,
    priceToY: (price: number) => Coordinate | null,
    anchorStartX: number | null,
  ) {
    this._renderer.update(elements, zone, priceToY, anchorStartX);
  }

  zOrder(): "bottom" {
    return "bottom";
  }

  renderer(): IPrimitivePaneRenderer {
    return this._renderer;
  }
}

// --- Price Axis View ---

class FibAxisView implements ISeriesPrimitiveAxisView {
  private _label: string;
  private _coord: number;
  private _color: string;

  constructor(label: string, coord: number, color: string) {
    this._label = label;
    this._coord = coord;
    this._color = color;
  }

  coordinate(): number {
    return this._coord;
  }

  text(): string {
    return this._label;
  }

  textColor(): string {
    return "#ffffff";
  }

  backColor(): string {
    return this._color;
  }

  visible(): boolean {
    return true;
  }

  tickVisible(): boolean {
    return true;
  }
}

// --- Main Primitive ---

export class FibLinesPrimitive implements ISeriesPrimitive<Time> {
  private _fibResult: FibResult | null = null;
  private _anchorStartTime: number | null = null;
  private _paneView = new FibPaneView();
  private _axisViews: FibAxisView[] = [];
  private _attachedParams: SeriesAttachedParameter<Time, SeriesType> | null = null;

  setFibResult(result: FibResult | null, anchorStartTime?: number) {
    this._fibResult = result;
    this._anchorStartTime = anchorStartTime ?? null;
    if (this._attachedParams) {
      this._attachedParams.requestUpdate();
    }
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>) {
    this._attachedParams = param;
  }

  detached() {
    this._attachedParams = null;
  }

  updateAllViews() {
    if (!this._attachedParams || !this._fibResult) {
      this._paneView.update([], null, () => null, null);
      this._axisViews = [];
      return;
    }

    const { series, chart } = this._attachedParams;
    const priceToY = (price: number) => series.priceToCoordinate(price);
    const timeScale = chart.timeScale();

    let anchorStartX: number | null = null;
    if (this._anchorStartTime != null) {
      const x = timeScale.timeToCoordinate(this._anchorStartTime as unknown as Time);
      anchorStartX = x != null ? x : 0;
    }

    const fib = this._fibResult;
    const range = fib.anchorHigh - fib.anchorLow;
    if (range <= 0) {
      this._paneView.update([], null, priceToY, anchorStartX);
      this._axisViews = [];
      return;
    }

    // Direction-aware price computation
    const base = fib.isBullish ? fib.anchorLow : fib.anchorHigh;
    const dir = fib.isBullish ? 1 : -1;
    const priceAt = (ratio: number) => base + dir * range * ratio;

    // Build all 10 elements
    const elements: FibElement[] = [];
    for (const level of ALL_LEVELS) {
      const price = priceAt(level.ratio);
      elements.push({
        price,
        label: level.label,
        color: level.color,
        lineWidth: level.width,
      });
    }

    // Zone fill between .382 and .618 (around the pivot)
    const zoneBand: ZoneBand = {
      topPrice: Math.max(priceAt(0.382), priceAt(0.618)),
      botPrice: Math.min(priceAt(0.382), priceAt(0.618)),
      color: COLORS.pivot,
    };

    this._paneView.update(elements, zoneBand, priceToY, anchorStartX);

    // Axis views for key levels
    this._axisViews = [];
    const axisLevels = [
      { label: "Pivot", ratio: 0.5, color: COLORS.pivot },
      { label: "ZERO", ratio: 0, color: COLORS.anchor },
      { label: "1", ratio: 1.0, color: COLORS.anchor },
      { label: "T1", ratio: 1.236, color: COLORS.target },
      { label: "T2", ratio: 1.618, color: COLORS.target },
    ];
    for (const al of axisLevels) {
      const price = priceAt(al.ratio);
      const coord = series.priceToCoordinate(price);
      if (coord != null) {
        this._axisViews.push(
          new FibAxisView(`${al.label} ${price.toFixed(2)}`, coord, al.color),
        );
      }
    }
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this._paneView];
  }

  priceAxisViews(): readonly ISeriesPrimitiveAxisView[] {
    return this._axisViews;
  }

  autoscaleInfo(): AutoscaleInfo | null {
    return null;
  }
}

// --- Utility ---

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

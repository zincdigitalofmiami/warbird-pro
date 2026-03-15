/**
 * Lightweight Charts Series Primitive: Fibonacci Pivot/Zone/Targets/Magnet
 *
 * Matches Kirk's Rabid Raccoon Pine Script indicator exactly:
 *   - PIVOT: white solid line at .5 level (width 2)
 *   - ZONE: gold/orange shaded band between .382 and .618 (width 2 borders)
 *   - TARGET 1: green solid line at 0 level (bullish) or 1.0 (bearish)
 *   - TARGET 2: green solid line at 1.236 extension
 *   - DOWN MAGNET: red solid line at 1.0 level (bullish) or 0 (bearish)
 *
 * Colors from Kirk's settings:
 *   Pivot = white (#FFFFFF)
 *   Zone = gold (#D4A017)
 *   Target 1 = green (#4CAF50)
 *   Target 2 = green (#4CAF50)
 *   Down Magnet = red (#EF5350)
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

// --- Kirk's exact colors from Pine Script settings ---
const COLORS = {
  pivot: "#FFFFFF",       // White
  zone: "#D4A017",        // Gold/Orange
  target1: "#4CAF50",     // Green
  target2: "#4CAF50",     // Green (same)
  downMagnet: "#EF5350",  // Red
} as const;

const WIDTHS = {
  pivot: 2,
  zone: 2,
  target: 2,
  downMagnet: 1,
} as const;

// --- Resolved visual element ---

interface FibVisualElement {
  kind: "pivot" | "zone_top" | "zone_bot" | "target1" | "target2" | "magnet";
  price: number;
  label: string;
  color: string;
  lineWidth: number;
  dashed: boolean;
}

interface ZoneBand {
  topPrice: number;
  botPrice: number;
  color: string;
}

// --- Renderer ---

class FibRenderer implements IPrimitivePaneRenderer {
  private _elements: FibVisualElement[] = [];
  private _zone: ZoneBand | null = null;
  private _priceToY: ((price: number) => Coordinate | null) | null = null;
  private _anchorStartX: number | null = null;

  update(
    elements: FibVisualElement[],
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
          ctx.fillStyle = hexToRgba(this._zone.color, 0.15);
          ctx.fillRect(x0, y0, mediaSize.width - x0, h);
        }
      }

      // Draw lines + labels
      for (const el of this._elements) {
        const y = this._priceToY(el.price);
        if (y == null) continue;
        if (y < -30 || y > mediaSize.height + 30) continue;

        // Line
        ctx.strokeStyle = hexToRgba(el.color, 0.8);
        ctx.lineWidth = el.lineWidth;
        ctx.setLineDash(el.dashed ? [4, 4] : []);
        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(mediaSize.width, y);
        ctx.stroke();
        ctx.setLineDash([]);

        // Label
        ctx.font = '10px -apple-system, BlinkMacSystemFont, "Inter", sans-serif';
        ctx.fillStyle = hexToRgba(el.color, 0.9);
        ctx.textBaseline = "bottom";
        ctx.textAlign = "left";
        ctx.fillText(el.label, x0 + 8, y - 3);
      }
    });
  }
}

// --- Pane View ---

class FibPaneView implements IPrimitivePaneView {
  private _renderer = new FibRenderer();

  update(
    elements: FibVisualElement[],
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
    const base = fib.isBullish ? fib.anchorLow : fib.anchorHigh;
    const dir = fib.isBullish ? 1 : -1;

    const priceAt = (ratio: number) => base + dir * range * ratio;

    // Build visual elements matching Kirk's Pine indicator
    const elements: FibVisualElement[] = [];

    // PIVOT: .5 level — white, width 2
    const pivotPrice = priceAt(0.5);
    elements.push({
      kind: "pivot",
      price: pivotPrice,
      label: `Pivot ${pivotPrice.toFixed(2)}`,
      color: COLORS.pivot,
      lineWidth: WIDTHS.pivot,
      dashed: false,
    });

    // ZONE borders: .382 and .618 — gold, width 2
    const zoneTop = priceAt(0.618);
    const zoneBot = priceAt(0.382);
    elements.push({
      kind: "zone_top",
      price: zoneTop,
      label: `.618 ${zoneTop.toFixed(2)}`,
      color: COLORS.zone,
      lineWidth: WIDTHS.zone,
      dashed: false,
    });
    elements.push({
      kind: "zone_bot",
      price: zoneBot,
      label: `.382 ${zoneBot.toFixed(2)}`,
      color: COLORS.zone,
      lineWidth: WIDTHS.zone,
      dashed: false,
    });

    // Zone fill band
    const zoneBand: ZoneBand = {
      topPrice: Math.max(zoneTop, zoneBot),
      botPrice: Math.min(zoneTop, zoneBot),
      color: COLORS.zone,
    };

    // TARGET 1: full range end (1.0 for bullish → high, 0 for bullish → low? No...)
    // In Kirk's system: Target 1 = the .236 retracement area (near the top in bullish)
    // Actually from the Pine: these are standard levels. Let me use 0 and 1.0 as extremes.
    // Bullish: Target 1 = 1.0 (anchor high), Down Magnet = 0 (anchor low)
    // Bearish: Target 1 = 0 (anchor low side), Down Magnet = 1.0 (anchor high)
    const target1Price = priceAt(1.0);
    elements.push({
      kind: "target1",
      price: target1Price,
      label: `Target 1 ${target1Price.toFixed(2)}`,
      color: COLORS.target1,
      lineWidth: WIDTHS.target,
      dashed: false,
    });

    // TARGET 2: 1.236 extension
    const target2Price = priceAt(1.236);
    elements.push({
      kind: "target2",
      price: target2Price,
      label: `Target 2 ${target2Price.toFixed(2)}`,
      color: COLORS.target2,
      lineWidth: WIDTHS.target,
      dashed: false,
    });

    // DOWN MAGNET: 0 level (opposite extreme)
    const magnetPrice = priceAt(0);
    elements.push({
      kind: "magnet",
      price: magnetPrice,
      label: `Magnet ${magnetPrice.toFixed(2)}`,
      color: COLORS.downMagnet,
      lineWidth: WIDTHS.downMagnet,
      dashed: false,
    });

    this._paneView.update(elements, zoneBand, priceToY, anchorStartX);

    // Axis views for pivot + zone boundaries
    this._axisViews = [];
    for (const el of [elements[0], elements[1], elements[2]]) {
      const coord = series.priceToCoordinate(el.price);
      if (coord != null) {
        this._axisViews.push(new FibAxisView(
          el.label,
          coord,
          el.color,
        ));
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

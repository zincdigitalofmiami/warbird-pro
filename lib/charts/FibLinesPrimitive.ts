/**
 * Lightweight Charts Series Primitive: AutoFib Structure
 *
 * Matches Kirk's "AutoFib Structure + Intermarket Alerts" Pine Script v6 EXACTLY.
 *
 * From the Pine Script settings:
 *   pivotRatio     = 0.50   → PIVOT (white, width 2)
 *   zoneLoRatio    = 0.618  → Decision Zone low border (orange, width 2)
 *   zoneHiRatio    = 0.786  → Decision Zone high border (orange, width 2)
 *   target1Ratio   = 1.236  → Target 1 (aqua, width 1)
 *   target2Ratio   = 1.618  → Target 2 (blue, width 1)
 *   dnMagnet1Ratio = 0.382  → Down Magnet 1 (teal, width 1)
 *   dnMagnet2Ratio = 0.236  → Down Magnet 2 (teal, width 1)
 *
 * Zone fill between .618 and .786 with orange at zoneFillOpacity (88).
 *
 * Colors from Kirk's Pine settings:
 *   Pivot = white
 *   Zone = orange
 *   Target 1 = aqua
 *   Target 2 = blue
 *   Down Magnet = teal
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

// --- Kirk's EXACT colors from Pine Script groupStyle inputs ---
const COLORS = {
  pivot: "#FFFFFF",       // color.white
  zone: "#FF9800",        // color.orange
  target1: "#00BCD4",     // color.aqua
  target2: "#2196F3",     // color.blue
  downMagnet: "#009688",  // color.teal
} as const;

// --- Kirk's EXACT ratios from Pine Script groupStruct inputs ---
const RATIOS = {
  pivot: 0.5,
  zoneLo: 0.618,
  zoneHi: 0.786,
  target1: 1.236,
  target2: 1.618,
  dnMagnet1: 0.382,
  dnMagnet2: 0.236,
} as const;

// --- Kirk's EXACT widths from Pine Script groupStyle inputs ---
const WIDTHS = {
  pivot: 2,
  zone: 2,
  target: 1,
  downMagnet: 1,
} as const;

const ZONE_FILL_OPACITY = 0.12; // Pine: 88 transparency → 12% opacity

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
          ctx.fillStyle = hexToRgba(this._zone.color, ZONE_FILL_OPACITY);
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

    // Direction-aware price computation (matches Pine: fibBase + fibDir * fibRange * ratio)
    const base = fib.isBullish ? fib.anchorLow : fib.anchorHigh;
    const dir = fib.isBullish ? 1 : -1;
    const priceAt = (ratio: number) => base + dir * range * ratio;

    const elements: FibElement[] = [];

    // PIVOT: .5 — white, width 2
    const pivotPrice = priceAt(RATIOS.pivot);
    elements.push({
      price: pivotPrice,
      label: `Pivot ${pivotPrice.toFixed(2)}`,
      color: COLORS.pivot,
      lineWidth: WIDTHS.pivot,
    });

    // DECISION ZONE borders: .618 and .786 — orange, width 2
    const zoneLoPrice = priceAt(RATIOS.zoneLo);
    const zoneHiPrice = priceAt(RATIOS.zoneHi);
    elements.push({
      price: zoneLoPrice,
      label: `.618 ${zoneLoPrice.toFixed(2)}`,
      color: COLORS.zone,
      lineWidth: WIDTHS.zone,
    });
    elements.push({
      price: zoneHiPrice,
      label: `.786 ${zoneHiPrice.toFixed(2)}`,
      color: COLORS.zone,
      lineWidth: WIDTHS.zone,
    });

    // Zone fill between .618 and .786
    const zoneBand: ZoneBand = {
      topPrice: Math.max(zoneLoPrice, zoneHiPrice),
      botPrice: Math.min(zoneLoPrice, zoneHiPrice),
      color: COLORS.zone,
    };

    // TARGET 1: 1.236 — aqua, width 1
    const t1Price = priceAt(RATIOS.target1);
    elements.push({
      price: t1Price,
      label: `T1 ${t1Price.toFixed(2)}`,
      color: COLORS.target1,
      lineWidth: WIDTHS.target,
    });

    // TARGET 2: 1.618 — blue, width 1
    const t2Price = priceAt(RATIOS.target2);
    elements.push({
      price: t2Price,
      label: `T2 ${t2Price.toFixed(2)}`,
      color: COLORS.target2,
      lineWidth: WIDTHS.target,
    });

    // DOWN MAGNET 1: .382 — teal, width 1
    const dn1Price = priceAt(RATIOS.dnMagnet1);
    elements.push({
      price: dn1Price,
      label: `Mag .382 ${dn1Price.toFixed(2)}`,
      color: COLORS.downMagnet,
      lineWidth: WIDTHS.downMagnet,
    });

    // DOWN MAGNET 2: .236 — teal, width 1
    const dn2Price = priceAt(RATIOS.dnMagnet2);
    elements.push({
      price: dn2Price,
      label: `Mag .236 ${dn2Price.toFixed(2)}`,
      color: COLORS.downMagnet,
      lineWidth: WIDTHS.downMagnet,
    });

    this._paneView.update(elements, zoneBand, priceToY, anchorStartX);

    // Axis views for pivot + zone + targets
    this._axisViews = [];
    const axisElements = [
      { label: `Pivot ${pivotPrice.toFixed(2)}`, price: pivotPrice, color: COLORS.pivot },
      { label: `.618 ${zoneLoPrice.toFixed(2)}`, price: zoneLoPrice, color: COLORS.zone },
      { label: `.786 ${zoneHiPrice.toFixed(2)}`, price: zoneHiPrice, color: COLORS.zone },
    ];
    for (const ae of axisElements) {
      const coord = series.priceToCoordinate(ae.price);
      if (coord != null) {
        this._axisViews.push(new FibAxisView(ae.label, coord, ae.color));
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

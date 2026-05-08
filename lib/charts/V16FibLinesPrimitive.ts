/**
 * V16 Fib primitive port for Warbird dashboard chart.
 *
 * Draw behavior:
 * - 10 fib levels (0, .236, .382, .5, .618, .786, 1, 1.236, 1.618, 2.0)
 * - lines start at anchor and extend right
 * - pivot zone fill between .382 and .618
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
import type { FibResult } from "@/lib/charts/autofib-v16";

const COLORS = {
  anchor: "#F3F4F6",
  retracement: "#E5E7EB",
  pivot: "#E5E7EB",
  target: "#22D3EE",
  zone: "#9CA3AF",
} as const;

const ALL_LEVELS: { ratio: number; label: string; color: string; width: number; lineDash?: number[] }[] = [
  { ratio: 0, label: "ZERO", color: COLORS.anchor, width: 1.5 },
  { ratio: 0.236, label: ".236", color: COLORS.retracement, width: 1 },
  { ratio: 0.382, label: ".382", color: COLORS.retracement, width: 1 },
  { ratio: 0.5, label: "Pivot", color: COLORS.pivot, width: 1, lineDash: [5, 5] },
  { ratio: 0.618, label: ".618", color: COLORS.retracement, width: 1 },
  { ratio: 0.786, label: ".786", color: COLORS.target, width: 1.25 },
  { ratio: 1.0, label: "1", color: COLORS.target, width: 1.5 },
  { ratio: 1.236, label: "TARGET 1", color: COLORS.target, width: 1.25 },
  { ratio: 1.618, label: "TARGET 2", color: COLORS.target, width: 1.25 },
  { ratio: 2.0, label: "TARGET 3", color: COLORS.target, width: 1.25 },
];

const PIVOT_FILL_OPACITY = 0.22;

interface FibElement {
  price: number;
  label: string;
  color: string;
  lineWidth: number;
  lineDash: number[];
}

interface ZoneBand {
  topPrice: number;
  botPrice: number;
  color: string;
}

class PivotRenderer implements IPrimitivePaneRenderer {
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

      const x0 = this._anchorStartX != null ? Math.max(0, this._anchorStartX) : 0;
      if (x0 >= mediaSize.width) return;

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

      for (const el of this._elements) {
        const y = this._priceToY(el.price);
        if (y == null) continue;
        if (y < -30 || y > mediaSize.height + 30) continue;

        ctx.strokeStyle = hexToRgba(el.color, 0.9);
        ctx.lineWidth = el.lineWidth;
        ctx.setLineDash(el.lineDash);
        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(mediaSize.width, y);
        ctx.stroke();
      }
    });
  }
}

class PivotPaneView implements IPrimitivePaneView {
  private _renderer = new PivotRenderer();

  update(
    elements: FibElement[],
    zone: ZoneBand | null,
    priceToY: (price: number) => Coordinate | null,
    anchorStartX: number | null,
  ) {
    this._renderer.update(elements, zone, priceToY, anchorStartX);
  }

  zOrder(): "top" {
    return "top";
  }

  renderer(): IPrimitivePaneRenderer {
    return this._renderer;
  }
}

class PivotAxisView implements ISeriesPrimitiveAxisView {
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

export class V16FibLinesPrimitive implements ISeriesPrimitive<Time> {
  private _fibResult: FibResult | null = null;
  private _anchorStartTime: Time | null = null;
  private _paneView = new PivotPaneView();
  private _axisViews: PivotAxisView[] = [];
  private _attachedParams: SeriesAttachedParameter<Time, SeriesType> | null = null;

  setFibResult(result: FibResult | null, anchorStartTime?: Time) {
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
      const x = timeScale.timeToCoordinate(this._anchorStartTime);
      anchorStartX = x != null ? x : 0;
    }

    const fib = this._fibResult;
    const range = fib.anchorHigh - fib.anchorLow;
    if (range <= 0) {
      this._paneView.update([], null, priceToY, anchorStartX);
      this._axisViews = [];
      return;
    }

    const base = fib.isBullish ? fib.anchorLow : fib.anchorHigh;
    const dir = fib.isBullish ? 1 : -1;
    const priceAt = (ratio: number) => base + dir * range * ratio;

    const elements: FibElement[] = [];
    for (const level of ALL_LEVELS) {
      const price = priceAt(level.ratio);
      elements.push({
        price,
        label: level.label,
        color: level.color,
        lineWidth: level.width,
        lineDash: level.lineDash ?? [],
      });
    }

    const zoneBand: ZoneBand = {
      topPrice: Math.max(priceAt(0.382), priceAt(0.618)),
      botPrice: Math.min(priceAt(0.382), priceAt(0.618)),
      color: COLORS.zone,
    };

    this._paneView.update(elements, zoneBand, priceToY, anchorStartX);
    this._axisViews = [];
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

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

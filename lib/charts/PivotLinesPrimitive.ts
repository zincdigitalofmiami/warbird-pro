/**
 * Lightweight Charts Series Primitive: Pivot Lines
 *
 * Renders traditional pivot levels (P, R1-R5, S1-S5) as solid horizontal
 * lines with text labels at the left edge. NO axis boxes. NO dotted lines.
 *
 * Colors:
 *   D/M (primary): Bright White #FFFFFF
 *   W/Y (tier-two): Faint Gray #404040 (appears ~rgba(255,255,255,0.15) at alpha)
 *
 * Follows the same ISeriesPrimitive pattern as ForecastTargetsPrimitive.
 */

import type {
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
  SeriesType,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  AutoscaleInfo,
  Coordinate,
} from "lightweight-charts";
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type { PivotLine, PivotTimeframe } from "@/lib/pivots";

// --- Styling constants ---

const STYLES = {
  pivotLineWidth: 2, // P (pivot point) line — thicker
  levelLineWidth: 1, // R/S lines — thinner
  labelFont: '10px -apple-system, BlinkMacSystemFont, "Inter", sans-serif',
  labelPaddingX: 6,
  labelPaddingY: 3,
  lineAlpha: 0.6,
  pivotLineAlpha: 0.8,
} as const;

// --- Internal pivot item with resolved color ---

interface ResolvedPivot {
  price: number;
  label: string;
  level: string;
  startTime?: Time | number;
  color: string;
  isPivotPoint: boolean;
}

// --- Renderer: draws pivot lines + labels on the main pane ---

class PivotLinesRenderer implements IPrimitivePaneRenderer {
  private pivots: ResolvedPivot[] = [];
  private priceToY: ((price: number) => Coordinate | null) | null = null;
  private timeToX: ((time: Time) => Coordinate | null) | null = null;

  update(
    pivots: ResolvedPivot[],
    priceToY: (price: number) => Coordinate | null,
    timeToX: (time: Time) => Coordinate | null,
  ) {
    this.pivots = pivots;
    this.priceToY = priceToY;
    this.timeToX = timeToX;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      if (!this.priceToY || !this.timeToX) return;

      for (const pivot of this.pivots) {
        const y = this.priceToY(pivot.price);
        if (y == null) continue;

        // Skip lines outside the visible vertical range (with padding)
        if (y < -20 || y > mediaSize.height + 20) continue;

        const alpha = pivot.isPivotPoint
          ? STYLES.pivotLineAlpha
          : STYLES.lineAlpha;
        const lineWidth = pivot.isPivotPoint
          ? STYLES.pivotLineWidth
          : STYLES.levelLineWidth;

        const startXRaw =
          pivot.startTime != null ? this.timeToX(pivot.startTime as Time) : 0;
        const startX = startXRaw == null ? 0 : Math.max(0, startXRaw);
        if (startX >= mediaSize.width) continue;

        // --- Draw solid horizontal segment (timeframe start → right edge) ---
        context.strokeStyle = hexToRgba(pivot.color, alpha);
        context.lineWidth = lineWidth;
        context.setLineDash([]); // SOLID — no dashing ever
        context.beginPath();
        context.moveTo(startX, y);
        context.lineTo(mediaSize.width, y);
        context.stroke();

        // --- Draw text label near segment start ---
        context.font = STYLES.labelFont;
        context.fillStyle = hexToRgba(pivot.color, 0.9);
        context.textBaseline = "bottom";
        const labelY = y - STYLES.labelPaddingY + 1;
        if (startX > 56) {
          // Match TradingView pivot style: label just to the left of segment
          context.textAlign = "right";
          context.fillText(pivot.label, startX - 6, labelY);
        } else {
          // Fallback when segment starts near far-left boundary
          context.textAlign = "left";
          context.fillText(pivot.label, startX + STYLES.labelPaddingX, labelY);
        }
        context.textAlign = "left";
      }
    });
  }
}

// --- Pane View: bridges renderer to LC ---

class PivotLinesPaneView implements IPrimitivePaneView {
  private rendererInstance = new PivotLinesRenderer();

  update(
    pivots: ResolvedPivot[],
    priceToY: (price: number) => Coordinate | null,
    timeToX: (time: Time) => Coordinate | null,
  ) {
    this.rendererInstance.update(pivots, priceToY, timeToX);
  }

  zOrder(): "top" {
    return "top";
  }

  renderer(): IPrimitivePaneRenderer {
    return this.rendererInstance;
  }
}

// --- Main Primitive ---

export class PivotLinesPrimitive implements ISeriesPrimitive<Time> {
  private _pivots: PivotLine[] = [];
  private _colors: Record<PivotTimeframe, string> = {
    D: "#FFFFFF",   // Primary: Bright White
    M: "#FFFFFF",   // Primary: Bright White
    W: "#404040",   // Tier-two: Faint Gray
    Y: "#404040",   // Tier-two: Faint Gray
  };
  private paneView = new PivotLinesPaneView();
  private attachedParams: SeriesAttachedParameter<Time, SeriesType> | null =
    null;

  setPivots(pivots: PivotLine[], colors?: Record<PivotTimeframe, string>) {
    this._pivots = pivots;
    if (colors) this._colors = colors;
    this.attachedParams?.requestUpdate();
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>) {
    this.attachedParams = param;
  }

  detached() {
    this.attachedParams = null;
  }

  updateAllViews() {
    if (!this.attachedParams) return;

    const { chart, series } = this.attachedParams;
    const resolved = this._pivots.map((pivot) => ({
      ...pivot,
      color: this._colors[pivot.timeframe] ?? "#F23645",
      isPivotPoint: pivot.level === "P",
    }));

    this.paneView.update(
      resolved,
      (price: number) => series.priceToCoordinate(price),
      (time: Time) => chart.timeScale().timeToCoordinate(time),
    );
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.paneView];
  }

  // NO priceAxisViews — no colored boxes on the price axis
  priceAxisViews(): readonly [] {
    return [];
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

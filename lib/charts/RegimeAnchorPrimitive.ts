import type {
  AutoscaleInfo,
  Coordinate,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from "lightweight-charts";
import type { CanvasRenderingTarget2D } from "fancy-canvas";

export interface RegimeAnchor {
  time: number;
  label: string;
  color: string;
}

class RegimeAnchorRenderer implements IPrimitivePaneRenderer {
  private anchor: RegimeAnchor | null = null;
  private timeToX: ((time: Time) => Coordinate | null) | null = null;

  update(
    anchor: RegimeAnchor | null,
    timeToX: (time: Time) => Coordinate | null,
  ) {
    this.anchor = anchor;
    this.timeToX = timeToX;
  }

  draw(target: CanvasRenderingTarget2D): void {
    if (!this.anchor || !this.timeToX) return;

    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      const x = this.timeToX?.(this.anchor?.time as Time);
      if (x == null) return;

      context.save();
      context.strokeStyle = this.anchor?.color ?? "rgba(255,255,255,0.22)";
      context.lineWidth = 1;
      context.setLineDash([4, 6]);
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, mediaSize.height);
      context.stroke();
      context.setLineDash([]);

      context.font = "11px Georgia, serif";
      context.fillStyle = this.anchor?.color ?? "#ff9800";
      context.textAlign = "left";
      context.textBaseline = "bottom";
      context.fillText(this.anchor?.label ?? "", x + 6, mediaSize.height - 10);
      context.restore();
    });
  }
}

class RegimeAnchorPaneView implements IPrimitivePaneView {
  private readonly rendererImpl = new RegimeAnchorRenderer();

  update(anchor: RegimeAnchor | null, timeToX: (time: Time) => Coordinate | null) {
    this.rendererImpl.update(anchor, timeToX);
  }

  zOrder(): "bottom" {
    return "bottom";
  }

  renderer(): IPrimitivePaneRenderer {
    return this.rendererImpl;
  }
}

export class RegimeAnchorPrimitive implements ISeriesPrimitive<Time> {
  private anchor: RegimeAnchor | null = null;
  private paneView = new RegimeAnchorPaneView();
  private attachedParams: SeriesAttachedParameter<Time, SeriesType> | null = null;

  setAnchor(anchor: RegimeAnchor | null) {
    this.anchor = anchor;
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
    const timeScale = this.attachedParams.chart.timeScale();
    this.paneView.update(this.anchor, (time) => timeScale.timeToCoordinate(time));
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.paneView];
  }

  autoscaleInfo(): AutoscaleInfo | null {
    return null;
  }
}

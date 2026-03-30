"use client";

// Alert event types from warbird_signal_events table (migration 037)
interface SignalEvent {
  signal_event_id: string;
  signal_id: string;
  ts: string;
  event_type: string;
  price: number | null;
  note: string | null;
}

interface AlertFeedPanelProps {
  events: SignalEvent[];
}

const EVENT_COLORS: Record<string, string> = {
  SIGNAL_EMITTED: "#FF9800",
  TP1_HIT: "#00C853",
  TP2_HIT: "#69F0AE",
  STOPPED: "#FF1744",
  CANCELLED: "#FFB300",
  REVERSAL_DETECTED: "#FF0000",
};

const EVENT_LABELS: Record<string, string> = {
  SIGNAL_EMITTED: "SIGNAL",
  TP1_HIT: "TP1 HIT",
  TP2_HIT: "TP2 HIT",
  STOPPED: "STOPPED",
  CANCELLED: "CANCELLED",
  REVERSAL_DETECTED: "REVERSAL",
};

function formatEventTime(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
    timeZone: "America/Chicago",
  });
}

function formatEventDate(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "America/Chicago",
  });
}

export default function AlertFeedPanel({ events }: AlertFeedPanelProps) {
  return (
    <div
      className="flex flex-col h-full"
      style={{
        background: "#131722",
        borderLeft: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      {/* Header */}
      <div
        className="px-4 py-3 flex items-center gap-2"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <div
          className="w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: "#FF9800" }}
        />
        <span className="text-[11px] font-semibold text-white/60 uppercase tracking-wider">
          Signal Events
        </span>
        <span className="text-[10px] text-white/25 ml-auto tabular-nums">
          {events.length}
        </span>
      </div>

      {/* Feed */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {events.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <span className="text-[11px] text-white/20">
              No signal events
            </span>
          </div>
        ) : (
          <div className="flex flex-col">
            {events.map((event) => {
              const color = EVENT_COLORS[event.event_type] ?? "#787b86";
              const label = EVENT_LABELS[event.event_type] ?? event.event_type;

              return (
                <div
                  key={event.signal_event_id}
                  className="px-4 py-2.5 flex flex-col gap-1"
                  style={{
                    borderBottom: "1px solid rgba(255,255,255,0.03)",
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span
                      className="text-[10px] font-bold uppercase tracking-wider"
                      style={{ color }}
                    >
                      {label}
                    </span>
                    <span className="text-[9px] text-white/25 tabular-nums">
                      {formatEventTime(event.ts)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    {event.price != null ? (
                      <span className="text-[11px] text-white/50 font-mono tabular-nums">
                        {event.price.toFixed(2)}
                      </span>
                    ) : (
                      <span className="text-[11px] text-white/20">—</span>
                    )}
                    <span className="text-[9px] text-white/20">
                      {formatEventDate(event.ts)}
                    </span>
                  </div>
                  {event.note ? (
                    <span className="text-[9px] text-white/30 truncate">
                      {event.note}
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

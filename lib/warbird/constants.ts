export const REGIME_START_ISO = "2025-01-20T00:00:00Z";
export const REGIME_LABEL = "trump_2";

export const WARBIRD_SIGNAL_VERSION = "warbird-v1.0";

export const WARBIRD_TRIGGER_MIN_RATIO = 1.2;
export const WARBIRD_GO_RATIO = 1.5;
export const WARBIRD_RUNNER_HEADROOM_MULTIPLE = 1;
export const WARBIRD_RUNNER_VOLUME_RATIO = 1.05;

export const WARBIRD_DEFAULT_SYMBOL = "MES";

export const FIFTEEN_MINUTES_MS = 15 * 60 * 1000;
export const ONE_HOUR_MS = 60 * 60 * 1000;

export function getRegimeStartDate(): Date {
  return new Date(REGIME_START_ISO);
}

export function getDaysIntoRegime(at: Date | string): number {
  const current = typeof at === "string" ? new Date(at) : at;
  const diff = current.getTime() - getRegimeStartDate().getTime();
  return Math.max(0, Math.floor(diff / (24 * 60 * 60 * 1000)));
}

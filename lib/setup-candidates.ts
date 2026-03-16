/**
 * Setup Candidate Types & Utilities
 *
 * Engine-neutral setup candidate contract. In Warbird v1, candidates are
 * sourced from the canonical warbird_setups table and mapped to the chart's
 * trigger-focused marker contract.
 */

export type SetupDirection = 'BULLISH' | 'BEARISH'
export type SetupGoType = 'BREAK' | 'CLOSE'
export type SetupLifecyclePhase =
  | 'AWAITING_CONTACT'
  | 'CONTACT'
  | 'CONFIRMED'
  | 'TRIGGERED'
  | 'EXPIRED'
  | 'INVALIDATED'

export type SetupSourceFamily =
  | 'HOOK_REJECTION'
  | 'MEASURED_MOVE'
  | 'LIQUIDITY_SWEEP'
  | 'OPENING_DRIVE'

export type SetupType =
  | 'RETRACE_REJECTION'
  | 'MEASURED_MOVE_RETRACE'
  | 'LIQUIDITY_SWEEP_RECLAIM'
  | 'OPENING_DRIVE_CONTINUATION'

export type ImpulseContext =
  | 'RETRACE'
  | 'CONTINUATION'
  | 'REVERSAL'
  | 'UNSPECIFIED'

export type LiquidityContext =
  | 'UNSPECIFIED'
  | 'RESTING_LEVEL'
  | 'SWEEP_RECLAIM'
  | 'EXPANSION'

export type StructureContext =
  | 'FIB_REJECTION'
  | 'MEASURED_MOVE'
  | 'LIQUIDITY_RECLAIM'
  | 'OPENING_DRIVE'
  | 'UNSPECIFIED'

export interface SetupCandidate {
  id: string
  sourceFamily: SetupSourceFamily
  triggerType: SetupType
  direction: SetupDirection
  phase: SetupLifecyclePhase
  thesis: string
  structuralReason: string
  candidateTime: number
  referenceLevel: number
  entryZoneLow: number | null
  entryZoneHigh: number | null
  invalidationLevel: number | null
  impulseContext: ImpulseContext
  liquidityContext: LiquidityContext
  structureContext: StructureContext

  fibLevel: number
  fibRatio: number

  touchTime?: number
  touchBarIndex?: number
  touchPrice?: number

  hookTime?: number
  hookBarIndex?: number
  hookLow?: number
  hookHigh?: number
  hookClose?: number

  goTime?: number
  goBarIndex?: number
  goType?: SetupGoType

  entry?: number
  stopLoss?: number
  tp1?: number
  tp2?: number

  createdAt: number
  expiryBars: number
}

/**
 * Map a warbird_setups row from Supabase into a SetupCandidate.
 * This replaces the old fromBhgSetup() adapter.
 */
export function fromWarbirdSetup(row: {
  id: number
  ts: string
  direction: string
  status: string
  entry_price: number | null
  stop_loss: number | null
  tp1: number | null
  tp2: number | null
  fib_level: number | null
  fib_ratio: number | null
  conviction_level: string | null
  counter_trend?: boolean | null
  runner_eligible?: boolean | null
  notes?: string | null
  created_at: string
}): SetupCandidate {
  const ts = new Date(row.ts).getTime() / 1000

  return {
    id: String(row.id),
    sourceFamily: 'MEASURED_MOVE',
    triggerType: 'MEASURED_MOVE_RETRACE',
    direction: row.direction === 'LONG' ? 'BULLISH' : 'BEARISH',
    phase: mapStatus(row.status),
    thesis: row.notes ?? '',
    structuralReason: row.conviction_level ?? '',
    candidateTime: ts,
    referenceLevel: row.fib_level ?? row.entry_price ?? 0,
    entryZoneLow: row.entry_price,
    entryZoneHigh: row.entry_price,
    invalidationLevel: row.stop_loss,
    impulseContext: row.counter_trend ? 'REVERSAL' : 'CONTINUATION',
    liquidityContext: row.runner_eligible ? 'EXPANSION' : 'UNSPECIFIED',
    structureContext: 'MEASURED_MOVE',
    fibLevel: row.fib_level ?? row.entry_price ?? 0,
    fibRatio: row.fib_ratio ?? 0.5,
    goTime: ts,
    entry: row.entry_price ?? undefined,
    stopLoss: row.stop_loss ?? undefined,
    tp1: row.tp1 ?? undefined,
    tp2: row.tp2 ?? undefined,
    createdAt: new Date(row.created_at).getTime() / 1000,
    expiryBars: 16,
  }
}

function mapStatus(status: string): SetupLifecyclePhase {
  switch (status) {
    case 'ACTIVE':
    case 'TP1_HIT':
    case 'TP2_HIT':
    case 'RUNNER_ACTIVE':
      return 'TRIGGERED'
    case 'RUNNER_EXITED':
    case 'STOPPED':
    case 'EXPIRED':
    case 'PULLBACK_REVERSAL':
      return 'EXPIRED'
    default:
      return 'AWAITING_CONTACT'
  }
}

export function getTriggeredCandidates(
  candidates: SetupCandidate[],
): SetupCandidate[] {
  return candidates.filter((candidate) => candidate.phase === 'TRIGGERED')
}

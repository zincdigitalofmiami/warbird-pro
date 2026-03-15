/**
 * Setup Candidate Types & Utilities
 *
 * Engine-neutral setup candidate contract. In warbird-pro, candidates are
 * sourced from the warbird_setups Supabase table rather than a local engine.
 * The chart's SetupMarkersPrimitive depends on this contract.
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
  phase: string
  entry_price: number | null
  stop_loss: number | null
  tp1: number | null
  tp2: number | null
  confidence: number | null
  pivot_level: number | null
  pivot_type: string | null
  measured_move_target: number | null
  created_at: string
}): SetupCandidate {
  const ts = new Date(row.ts).getTime() / 1000

  return {
    id: String(row.id),
    sourceFamily: 'HOOK_REJECTION',
    triggerType: 'RETRACE_REJECTION',
    direction: row.direction as SetupDirection,
    phase: mapPhase(row.phase),
    thesis: '',
    structuralReason: '',
    candidateTime: ts,
    referenceLevel: row.pivot_level ?? row.entry_price ?? 0,
    entryZoneLow: row.entry_price,
    entryZoneHigh: row.entry_price,
    invalidationLevel: row.stop_loss,
    impulseContext: 'RETRACE',
    liquidityContext: 'RESTING_LEVEL',
    structureContext: 'FIB_REJECTION',
    fibLevel: row.pivot_level ?? 0,
    fibRatio: 0.618,
    touchTime: ts,
    touchPrice: row.pivot_level ?? undefined,
    goTime: row.phase === 'GO_FIRED' ? ts : undefined,
    entry: row.entry_price ?? undefined,
    stopLoss: row.stop_loss ?? undefined,
    tp1: row.tp1 ?? undefined,
    tp2: row.tp2 ?? undefined,
    createdAt: new Date(row.created_at).getTime() / 1000,
    expiryBars: 16,
  }
}

function mapPhase(dbPhase: string): SetupLifecyclePhase {
  switch (dbPhase) {
    case 'TOUCHED': return 'CONTACT'
    case 'HOOKED': return 'CONFIRMED'
    case 'GO_FIRED': return 'TRIGGERED'
    case 'TP1_HIT':
    case 'TP2_HIT':
    case 'STOPPED_OUT':
    case 'EXPIRED':
      return 'EXPIRED'
    default: return 'AWAITING_CONTACT'
  }
}

export function getTriggeredCandidates(
  candidates: SetupCandidate[],
): SetupCandidate[] {
  return candidates.filter((candidate) => candidate.phase === 'TRIGGERED')
}

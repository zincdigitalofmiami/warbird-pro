/**
 * Warbird Setup Engine — Touch → Hook → Go State Machine
 *
 * Pure functions. No DB, no API calls.
 * Takes candles + fib levels + measured moves, returns detected setups.
 *
 * Ported from rabid-raccoon bhg-engine.ts with clean naming.
 *
 * Touch: Price tags 0.5 or 0.618 fib level
 * Hook:  Wick rejection at fib level (wick >= body, close on approaching side)
 * Go:    Break or close past hook extreme (strict inequality, fire once, 20-bar expiry)
 */

import { CandleData, FibResult, MeasuredMove } from './types'
import { roundToTick } from './ta/fibonacci'

// ─── Types ────────────────────────────────────────────────────────────────────

export type GoType = 'BREAK' | 'CLOSE'
export type SetupPhase =
  | 'TOUCHED'
  | 'HOOKED'
  | 'GO_FIRED'
  | 'EXPIRED'
  | 'STOPPED'
  | 'TP1_HIT'
  | 'TP2_HIT'

export type SetupDirection = 'LONG' | 'SHORT'

export interface WarbirdSetup {
  id: string
  direction: SetupDirection
  phase: SetupPhase
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
  goType?: GoType

  entry?: number
  stopLoss?: number
  tp1?: number
  tp2?: number
  confidence?: number
  pivotLevel?: number
  pivotType?: string
  measuredMoveTarget?: number

  createdAt: number
  expiryBars: number
}

// ─── Constants ────────────────────────────────────────────────────────────────

const TOUCH_FIB_RATIOS = [0.5, 0.618] as const
const DEFAULT_EXPIRY_BARS = 20
const TOUCH_EXPIRY_BARS = 10
const MES_TICK_SIZE = 0.25
const PRICE_BUFFER_RATIO = 0.02

// ─── Helpers ──────────────────────────────────────────────────────────────────

function findFibLevelPrice(fibResult: FibResult, ratio: number): number | null {
  const level = fibResult.levels.find((l) => Math.abs(l.ratio - ratio) <= 0.002)
  return level ? level.price : null
}

export function findTouchableFibLevels(
  fibResult: FibResult
): { level: number; ratio: number }[] {
  const result: { level: number; ratio: number }[] = []
  for (const fl of fibResult.levels) {
    if (TOUCH_FIB_RATIOS.includes(fl.ratio as 0.5 | 0.618)) {
      result.push({ level: fl.price, ratio: fl.ratio })
    }
  }
  return result
}

// ─── Phase Detection ──────────────────────────────────────────────────────────

export function detectTouch(
  candle: CandleData,
  barIndex: number,
  fibLevel: number,
  fibRatio: number,
  isBullish: boolean
): WarbirdSetup | null {
  const isTagged = candle.low <= fibLevel && candle.high >= fibLevel
  if (!isTagged) return null

  const direction: SetupDirection = isBullish ? 'LONG' : 'SHORT'
  return {
    id: `${direction}-${fibRatio}-${barIndex}`,
    direction,
    phase: 'TOUCHED',
    fibLevel,
    fibRatio,
    touchTime: candle.time,
    touchBarIndex: barIndex,
    touchPrice: fibLevel,
    pivotLevel: fibLevel,
    pivotType: `fib_${fibRatio}`,
    createdAt: candle.time,
    expiryBars: DEFAULT_EXPIRY_BARS,
  }
}

export function detectHook(
  candle: CandleData,
  barIndex: number,
  setup: WarbirdSetup
): WarbirdSetup | null {
  if (setup.phase !== 'TOUCHED') return null

  const body = Math.abs(candle.close - candle.open)

  if (setup.direction === 'LONG') {
    const rejectionWick = candle.close - candle.low
    if (
      candle.low <= setup.fibLevel &&
      candle.close > setup.fibLevel &&
      rejectionWick >= body
    ) {
      return {
        ...setup,
        phase: 'HOOKED',
        hookTime: candle.time,
        hookBarIndex: barIndex,
        hookLow: candle.low,
        hookHigh: candle.high,
        hookClose: candle.close,
      }
    }
  }

  if (setup.direction === 'SHORT') {
    const rejectionWick = candle.high - candle.close
    if (
      candle.high >= setup.fibLevel &&
      candle.close < setup.fibLevel &&
      rejectionWick >= body
    ) {
      return {
        ...setup,
        phase: 'HOOKED',
        hookTime: candle.time,
        hookBarIndex: barIndex,
        hookLow: candle.low,
        hookHigh: candle.high,
        hookClose: candle.close,
      }
    }
  }

  return null
}

export function detectGo(
  candle: CandleData,
  barIndex: number,
  setup: WarbirdSetup
): WarbirdSetup | null {
  if (setup.phase !== 'HOOKED') return null

  if (barIndex - (setup.hookBarIndex ?? 0) > setup.expiryBars) {
    return { ...setup, phase: 'EXPIRED' }
  }

  if (setup.direction === 'LONG') {
    const hookHigh = setup.hookHigh!
    if (candle.high > hookHigh) {
      return {
        ...setup,
        phase: 'GO_FIRED',
        goTime: candle.time,
        goBarIndex: barIndex,
        goType: candle.close > hookHigh ? 'CLOSE' : 'BREAK',
      }
    }
    if (candle.close > hookHigh) {
      return {
        ...setup,
        phase: 'GO_FIRED',
        goTime: candle.time,
        goBarIndex: barIndex,
        goType: 'CLOSE',
      }
    }
  }

  if (setup.direction === 'SHORT') {
    const hookLow = setup.hookLow!
    if (candle.low < hookLow) {
      return {
        ...setup,
        phase: 'GO_FIRED',
        goTime: candle.time,
        goBarIndex: barIndex,
        goType: candle.close < hookLow ? 'CLOSE' : 'BREAK',
      }
    }
    if (candle.close < hookLow) {
      return {
        ...setup,
        phase: 'GO_FIRED',
        goTime: candle.time,
        goBarIndex: barIndex,
        goType: 'CLOSE',
      }
    }
  }

  return null
}

// ─── Target Computation ───────────────────────────────────────────────────────

export function computeTargets(
  setup: WarbirdSetup,
  fibResult: FibResult,
  measuredMoves: MeasuredMove[]
): WarbirdSetup {
  if (setup.phase !== 'GO_FIRED') return setup

  const range = fibResult.anchorHigh - fibResult.anchorLow
  if (range <= 0) return setup

  const entry = roundToTick(setup.hookClose ?? setup.fibLevel, MES_TICK_SIZE)
  const buffer = Math.max(MES_TICK_SIZE, range * PRICE_BUFFER_RATIO)
  const minDistance = Math.max(buffer * 1.5, MES_TICK_SIZE * 4)

  const stopRatio = setup.fibRatio === 0.5 ? 0.618 : 0.786
  const stopCandidate = findFibLevelPrice(fibResult, stopRatio)
  let stopLoss = 0

  if (setup.direction === 'LONG') {
    const belowEntry = [stopCandidate, setup.fibLevel, fibResult.anchorLow]
      .filter((v): v is number => v != null && Number.isFinite(v) && v < entry)
    const stopBase = belowEntry.length > 0 ? Math.max(...belowEntry) : entry - minDistance
    stopLoss = roundToTick(stopBase - buffer, MES_TICK_SIZE)
    if (stopLoss >= entry) stopLoss = roundToTick(entry - minDistance, MES_TICK_SIZE)
  } else {
    const aboveEntry = [stopCandidate, setup.fibLevel, fibResult.anchorHigh]
      .filter((v): v is number => v != null && Number.isFinite(v) && v > entry)
    const stopBase = aboveEntry.length > 0 ? Math.min(...aboveEntry) : entry + minDistance
    stopLoss = roundToTick(stopBase + buffer, MES_TICK_SIZE)
    if (stopLoss <= entry) stopLoss = roundToTick(entry + minDistance, MES_TICK_SIZE)
  }

  const ext1236 = findFibLevelPrice(fibResult, 1.236)
  const ext1618 = findFibLevelPrice(fibResult, 1.618)
  let tp1 = 0
  let tp2 = 0

  if (setup.direction === 'LONG') {
    const tp1Candidates = [ext1236, fibResult.anchorHigh + range * 0.236]
      .filter((v): v is number => v != null && Number.isFinite(v) && v > entry)
    tp1 = roundToTick(tp1Candidates.length > 0 ? Math.min(...tp1Candidates) : entry + minDistance, MES_TICK_SIZE)

    const tp2Candidates = [ext1618, fibResult.anchorHigh + range * 0.618]
      .filter((v): v is number => v != null && Number.isFinite(v) && v > tp1)
    tp2 = roundToTick(tp2Candidates.length > 0 ? Math.min(...tp2Candidates) : tp1 + minDistance, MES_TICK_SIZE)
    if (tp2 <= tp1) tp2 = roundToTick(tp1 + minDistance, MES_TICK_SIZE)
  } else {
    const tp1Candidates = [ext1236, fibResult.anchorLow - range * 0.236]
      .filter((v): v is number => v != null && Number.isFinite(v) && v < entry)
    tp1 = roundToTick(tp1Candidates.length > 0 ? Math.max(...tp1Candidates) : entry - minDistance, MES_TICK_SIZE)

    const tp2Candidates = [ext1618, fibResult.anchorLow - range * 0.618]
      .filter((v): v is number => v != null && Number.isFinite(v) && v < tp1)
    tp2 = roundToTick(tp2Candidates.length > 0 ? Math.max(...tp2Candidates) : tp1 - minDistance, MES_TICK_SIZE)
    if (tp2 >= tp1) tp2 = roundToTick(tp1 - minDistance, MES_TICK_SIZE)
  }

  // If aligned measured move exists, prefer its target for TP1
  const alignedMove = measuredMoves.find(
    (m) =>
      ((m.direction === 'BULLISH' && setup.direction === 'LONG') ||
       (m.direction === 'BEARISH' && setup.direction === 'SHORT')) &&
      (m.status === 'ACTIVE' || m.status === 'FORMING')
  )
  let measuredMoveTarget: number | undefined
  if (alignedMove) {
    const mmTarget = roundToTick(alignedMove.target, MES_TICK_SIZE)
    const valid =
      (setup.direction === 'LONG' && mmTarget > entry) ||
      (setup.direction === 'SHORT' && mmTarget < entry)
    if (valid) {
      tp1 = mmTarget
      measuredMoveTarget = mmTarget
      if (setup.direction === 'LONG' && tp2 <= tp1) tp2 = roundToTick(tp1 + minDistance, MES_TICK_SIZE)
      if (setup.direction === 'SHORT' && tp2 >= tp1) tp2 = roundToTick(tp1 - minDistance, MES_TICK_SIZE)
    }
  }

  return { ...setup, entry, stopLoss, tp1, tp2, measuredMoveTarget }
}

// ─── Main Entry Point ─────────────────────────────────────────────────────────

/**
 * Run the Warbird state machine over a candle array.
 *
 * Stateless: takes the full candle history and recomputes from scratch.
 * Returns all setups (active + terminal) for detection cron to persist.
 */
export function detectSetups(
  candles: CandleData[],
  fibResult: FibResult,
  measuredMoves: MeasuredMove[]
): WarbirdSetup[] {
  if (candles.length < 10 || !fibResult) return []

  const touchLevels = findTouchableFibLevels(fibResult)
  if (touchLevels.length === 0) return []

  const activeSetups: Map<string, WarbirdSetup> = new Map()
  const completedSetups: WarbirdSetup[] = []
  const firedGoKeys = new Set<string>()

  for (let i = 0; i < candles.length; i++) {
    const candle = candles[i]

    // 1. Check for new touches
    for (const { level, ratio } of touchLevels) {
      for (const isBullish of [true, false]) {
        const direction: SetupDirection = isBullish ? 'LONG' : 'SHORT'
        const dedupeKey = `${direction}-${ratio}`

        const hasActive = [...activeSetups.values()].some(
          (s) =>
            s.direction === direction &&
            s.fibRatio === ratio &&
            s.phase !== 'EXPIRED' &&
            s.phase !== 'GO_FIRED'
        )
        if (hasActive) continue

        if (firedGoKeys.has(dedupeKey)) {
          const lastGo = completedSetups.find(
            (s) => s.direction === direction && s.fibRatio === ratio && s.phase === 'GO_FIRED'
          )
          if (lastGo && i - (lastGo.goBarIndex ?? 0) < 40) continue
          firedGoKeys.delete(dedupeKey)
        }

        const touch = detectTouch(candle, i, level, ratio, isBullish)
        if (touch) {
          activeSetups.set(touch.id, touch)
        }
      }
    }

    // 2. Advance active setups
    for (const [id, setup] of activeSetups) {
      let updated: WarbirdSetup | null = null

      if (setup.phase === 'TOUCHED') {
        updated = detectHook(candle, i, setup)
      }

      if (!updated && setup.phase === 'HOOKED') {
        updated = detectGo(candle, i, setup)
      }

      if (updated) {
        if (updated.phase === 'GO_FIRED') {
          const withTargets = computeTargets(updated, fibResult, measuredMoves)
          completedSetups.push(withTargets)
          activeSetups.delete(id)
          firedGoKeys.add(`${updated.direction}-${updated.fibRatio}`)
        } else if (updated.phase === 'EXPIRED') {
          completedSetups.push(updated)
          activeSetups.delete(id)
        } else {
          activeSetups.set(id, updated)
        }
      } else if (setup.phase === 'TOUCHED') {
        if (i - (setup.touchBarIndex ?? 0) > TOUCH_EXPIRY_BARS) {
          activeSetups.delete(id)
          completedSetups.push({ ...setup, phase: 'EXPIRED' })
        }
      } else if (setup.phase === 'HOOKED') {
        if (i - (setup.hookBarIndex ?? 0) > setup.expiryBars) {
          activeSetups.delete(id)
          completedSetups.push({ ...setup, phase: 'EXPIRED' })
        }
      }
    }
  }

  return [
    ...activeSetups.values(),
    ...completedSetups.sort((a, b) => (b.goTime ?? b.createdAt) - (a.goTime ?? a.createdAt)),
  ]
}

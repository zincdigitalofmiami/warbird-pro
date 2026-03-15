/**
 * David Halsey Measured Move (AB=CD) Pattern Detection
 *
 * Uses swing points to find AB=CD patterns:
 * - A→B is the impulse leg
 * - B→C is a 38.2%–61.8% retracement of AB
 * - C→D projects the measured move where CD ≈ AB
 *
 * Entry at C (retrace pivot), stop beyond .618, target at 1:1 projection.
 */

import { SwingPoint, MeasuredMove } from './types'

export function detectMeasuredMoves(
  swingHighs: SwingPoint[],
  swingLows: SwingPoint[],
  currentPrice: number
): MeasuredMove[] {
  const moves: MeasuredMove[] = []

  const allSwings = [...swingHighs, ...swingLows].sort((a, b) => a.barIndex - b.barIndex)
  if (allSwings.length < 3) return moves

  for (let i = 0; i < allSwings.length - 2; i++) {
    const a = allSwings[i]
    const b = allSwings[i + 1]
    const c = allSwings[i + 2]

    if (a.isHigh === b.isHigh) continue
    if (b.isHigh === c.isHigh) continue

    const isBullish = !a.isHigh && b.isHigh && !c.isHigh
    const isBearish = a.isHigh && !b.isHigh && c.isHigh
    if (!isBullish && !isBearish) continue

    const abDistance = Math.abs(b.price - a.price)
    if (abDistance <= 0) continue

    const bcRetrace = Math.abs(c.price - b.price) / abDistance
    if (bcRetrace < 0.382 || bcRetrace > 0.618) continue

    let projectedD: number
    let entry: number
    let stop: number
    let target1236: number

    if (isBullish) {
      projectedD = c.price + abDistance
      entry = c.price
      stop = b.price - abDistance * 0.618 - abDistance * 0.02
      target1236 = c.price + abDistance * 1.236
    } else {
      projectedD = c.price - abDistance
      entry = c.price
      stop = b.price + abDistance * 0.618 + abDistance * 0.02
      target1236 = c.price - abDistance * 1.236
    }

    const idealDeviation = Math.abs(bcRetrace - 0.5)
    const quality = Math.round(100 - idealDeviation * 500)

    let status: MeasuredMove['status']
    if (isBullish) {
      if (currentPrice >= projectedD) status = 'TARGET_HIT'
      else if (currentPrice < stop) status = 'STOPPED_OUT'
      else if (currentPrice <= c.price) status = 'FORMING'
      else status = 'ACTIVE'
    } else {
      if (currentPrice <= projectedD) status = 'TARGET_HIT'
      else if (currentPrice > stop) status = 'STOPPED_OUT'
      else if (currentPrice >= c.price) status = 'FORMING'
      else status = 'ACTIVE'
    }

    moves.push({
      direction: isBullish ? 'BULLISH' : 'BEARISH',
      pointA: a,
      pointB: b,
      pointC: c,
      projectedD,
      retracementRatio: bcRetrace,
      entry,
      stop,
      target: projectedD,
      target1236,
      quality,
      status,
    })
  }

  return moves.sort((a, b) => b.quality - a.quality).slice(0, 5)
}

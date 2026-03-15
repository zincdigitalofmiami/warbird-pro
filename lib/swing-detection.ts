/**
 * Swing High/Low Detection
 *
 * Ported from Pine Script ta.pivothigh(high, leftBars, rightBars).
 * Confirms a pivot when the candidate bar's high/low is the extreme
 * in the window of leftBars + 1 + rightBars.
 */

import { CandleData, SwingPoint } from './types'

export function detectSwings(
  candles: CandleData[],
  leftBars: number = 5,
  rightBars: number = 5,
  maxHistory: number = 50
): { highs: SwingPoint[]; lows: SwingPoint[] } {
  const highs: SwingPoint[] = []
  const lows: SwingPoint[] = []

  if (candles.length < leftBars + rightBars + 1) {
    return { highs, lows }
  }

  for (let i = leftBars; i < candles.length - rightBars; i++) {
    let isPivotHigh = true
    for (let j = i - leftBars; j <= i + rightBars; j++) {
      if (j !== i && candles[j].high >= candles[i].high) {
        isPivotHigh = false
        break
      }
    }
    if (isPivotHigh) {
      highs.push({
        price: candles[i].high,
        barIndex: i,
        isHigh: true,
        time: candles[i].time,
      })
    }

    let isPivotLow = true
    for (let j = i - leftBars; j <= i + rightBars; j++) {
      if (j !== i && candles[j].low <= candles[i].low) {
        isPivotLow = false
        break
      }
    }
    if (isPivotLow) {
      lows.push({
        price: candles[i].low,
        barIndex: i,
        isHigh: false,
        time: candles[i].time,
      })
    }
  }

  return {
    highs: highs.reverse().slice(0, maxHistory),
    lows: lows.reverse().slice(0, maxHistory),
  }
}

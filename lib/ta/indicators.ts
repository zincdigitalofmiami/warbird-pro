/**
 * Technical Analysis Indicator Library
 *
 * Ported from battle-tested TradingView indicators:
 *   - LuxAlgo Market Sentiment Technicals (RSI, Stoch, StochRSI, CCI, BBP, MA, BB, Supertrend, LinReg, Market Structure)
 *   - LazyBear TTM Squeeze (Bollinger inside Keltner = squeeze)
 *   - Standard TA (EMA, SMA, ATR, StdDev)
 *
 * All oscillator outputs normalized to 0-100 matching LuxAlgo's scheme:
 *   >75 = overbought/strong bullish
 *   50  = neutral
 *   <25 = oversold/strong bearish
 *
 * These run on 1m bars for trigger-level precision.
 */

// ─── Base TA Functions ──────────────────────────────────────────────────────

export function sma(values: number[], length: number): number {
  if (values.length < length) return values[values.length - 1] ?? 0;
  const slice = values.slice(-length);
  return slice.reduce((s, v) => s + v, 0) / slice.length;
}

export function ema(values: number[], length: number): number {
  if (values.length === 0) return 0;
  const k = 2 / (length + 1);
  let result = values[0];
  for (let i = 1; i < values.length; i++) {
    result = values[i] * k + result * (1 - k);
  }
  return result;
}

export function rma(values: number[], length: number): number {
  if (values.length === 0) return 0;
  const alpha = 1 / length;
  let result = sma(values.slice(0, length), length);
  for (let i = length; i < values.length; i++) {
    result = alpha * values[i] + (1 - alpha) * result;
  }
  return result;
}

export function stdev(values: number[], length: number): number {
  if (values.length < length) return 0;
  const slice = values.slice(-length);
  const mean = slice.reduce((s, v) => s + v, 0) / slice.length;
  const variance = slice.reduce((s, v) => s + (v - mean) ** 2, 0) / slice.length;
  return Math.sqrt(variance);
}

export function trueRange(
  high: number[],
  low: number[],
  close: number[],
): number[] {
  const tr: number[] = [high[0] - low[0]];
  for (let i = 1; i < high.length; i++) {
    tr.push(Math.max(
      high[i] - low[i],
      Math.abs(high[i] - close[i - 1]),
      Math.abs(low[i] - close[i - 1]),
    ));
  }
  return tr;
}

export function atr(
  high: number[],
  low: number[],
  close: number[],
  length: number,
): number {
  const tr = trueRange(high, low, close);
  return rma(tr, length);
}

function interpolate(
  value: number,
  valueHigh: number,
  valueLow: number,
  rangeHigh: number,
  rangeLow: number,
): number {
  if (valueHigh === valueLow) return (rangeHigh + rangeLow) / 2;
  return rangeLow + (value - valueLow) * (rangeHigh - rangeLow) / (valueHigh - valueLow);
}

// ─── Oscillator Indicators (normalized 0-100) ───────────────────────────────

/**
 * RSI — Relative Strength Index
 * Normalized per LuxAlgo: >70 maps to 75-100, 50-70 maps to 50-75, etc.
 */
export function rsiNormalized(closes: number[], length: number = 14): number {
  if (closes.length < length + 1) return 50;

  let avgGain = 0;
  let avgLoss = 0;

  // Initial averages
  for (let i = 1; i <= length; i++) {
    const change = closes[i] - closes[i - 1];
    if (change > 0) avgGain += change;
    else avgLoss += Math.abs(change);
  }
  avgGain /= length;
  avgLoss /= length;

  // Smooth with RMA
  for (let i = length + 1; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1];
    avgGain = (avgGain * (length - 1) + (change > 0 ? change : 0)) / length;
    avgLoss = (avgLoss * (length - 1) + (change < 0 ? Math.abs(change) : 0)) / length;
  }

  const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
  const rsiVal = 100 - 100 / (1 + rs);

  // LuxAlgo normalization
  if (rsiVal > 70) return interpolate(rsiVal, 100, 70, 100, 75);
  if (rsiVal > 50) return interpolate(rsiVal, 70, 50, 75, 50);
  if (rsiVal > 30) return interpolate(rsiVal, 50, 30, 50, 25);
  return interpolate(rsiVal, 30, 0, 25, 0);
}

/**
 * Raw RSI value (0-100, no normalization)
 */
export function rsiRaw(closes: number[], length: number = 14): number {
  if (closes.length < length + 1) return 50;

  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 1; i <= length; i++) {
    const change = closes[i] - closes[i - 1];
    if (change > 0) avgGain += change;
    else avgLoss += Math.abs(change);
  }
  avgGain /= length;
  avgLoss /= length;

  for (let i = length + 1; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1];
    avgGain = (avgGain * (length - 1) + (change > 0 ? change : 0)) / length;
    avgLoss = (avgLoss * (length - 1) + (change < 0 ? Math.abs(change) : 0)) / length;
  }

  const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

/**
 * Stochastic %K — normalized per LuxAlgo
 */
export function stochasticNormalized(
  closes: number[],
  highs: number[],
  lows: number[],
  lengthK: number = 14,
  smoothK: number = 3,
): number {
  if (closes.length < lengthK) return 50;

  // Compute raw stochastic values
  const rawStoch: number[] = [];
  for (let i = lengthK - 1; i < closes.length; i++) {
    const hSlice = highs.slice(i - lengthK + 1, i + 1);
    const lSlice = lows.slice(i - lengthK + 1, i + 1);
    const hh = Math.max(...hSlice);
    const ll = Math.min(...lSlice);
    rawStoch.push(hh === ll ? 50 : ((closes[i] - ll) / (hh - ll)) * 100);
  }

  // Smooth with SMA
  const stochVal = sma(rawStoch, smoothK);

  // LuxAlgo normalization
  if (stochVal > 80) return interpolate(stochVal, 100, 80, 100, 75);
  if (stochVal > 50) return interpolate(stochVal, 80, 50, 75, 50);
  if (stochVal > 20) return interpolate(stochVal, 50, 20, 50, 25);
  return interpolate(stochVal, 20, 0, 25, 0);
}

/**
 * Stochastic RSI — normalized per LuxAlgo
 */
export function stochRsiNormalized(
  closes: number[],
  rsiLength: number = 14,
  stochLength: number = 14,
  smoothK: number = 3,
): number {
  if (closes.length < rsiLength + stochLength) return 50;

  // Compute RSI series
  const rsiSeries: number[] = [];
  for (let i = rsiLength; i <= closes.length; i++) {
    rsiSeries.push(rsiRaw(closes.slice(0, i), rsiLength));
  }

  if (rsiSeries.length < stochLength) return 50;

  // Stochastic on the RSI series
  const rawStoch: number[] = [];
  for (let i = stochLength - 1; i < rsiSeries.length; i++) {
    const slice = rsiSeries.slice(i - stochLength + 1, i + 1);
    const hh = Math.max(...slice);
    const ll = Math.min(...slice);
    rawStoch.push(hh === ll ? 50 : ((rsiSeries[i] - ll) / (hh - ll)) * 100);
  }

  const stochVal = sma(rawStoch, smoothK);

  if (stochVal > 80) return interpolate(stochVal, 100, 80, 100, 75);
  if (stochVal > 50) return interpolate(stochVal, 80, 50, 75, 50);
  if (stochVal > 20) return interpolate(stochVal, 50, 20, 50, 25);
  return interpolate(stochVal, 20, 0, 25, 0);
}

/**
 * CCI — Commodity Channel Index, normalized per LuxAlgo
 */
export function cciNormalized(
  closes: number[],
  highs: number[],
  lows: number[],
  length: number = 20,
): number {
  if (closes.length < length) return 50;

  // Typical price
  const tp: number[] = [];
  for (let i = 0; i < closes.length; i++) {
    tp.push((highs[i] + lows[i] + closes[i]) / 3);
  }

  const tpSlice = tp.slice(-length);
  const mean = tpSlice.reduce((s, v) => s + v, 0) / length;
  const meanDev = tpSlice.reduce((s, v) => s + Math.abs(v - mean), 0) / length;

  const cciVal = meanDev === 0 ? 0 : (tp[tp.length - 1] - mean) / (0.015 * meanDev);

  if (cciVal > 100) return cciVal > 300 ? 100 : interpolate(cciVal, 300, 100, 100, 75);
  if (cciVal >= 0) return interpolate(cciVal, 100, 0, 75, 50);
  if (cciVal < -100) return cciVal < -300 ? 0 : interpolate(cciVal, -100, -300, 25, 0);
  return interpolate(cciVal, 0, -100, 50, 25);
}

/**
 * Bull Bear Power — normalized per LuxAlgo
 */
export function bbpNormalized(
  closes: number[],
  highs: number[],
  lows: number[],
  length: number = 13,
): number {
  if (closes.length < length) return 50;

  const emaVal = ema(closes, length);
  const bbp = highs[highs.length - 1] + lows[lows.length - 1] - 2 * emaVal;

  // Compute Bollinger Bands on BBP series for dynamic normalization
  const bbpSeries: number[] = [];
  for (let i = Math.max(0, closes.length - 100); i < closes.length; i++) {
    const e = ema(closes.slice(0, i + 1), length);
    bbpSeries.push(highs[i] + lows[i] - 2 * e);
  }

  const bbpMean = sma(bbpSeries, Math.min(100, bbpSeries.length));
  const bbpStd = stdev(bbpSeries, Math.min(100, bbpSeries.length));
  const upper = bbpMean + 2 * bbpStd;
  const lower = bbpMean - 2 * bbpStd;

  if (bbp > upper) return bbp > 1.5 * upper ? 100 : interpolate(bbp, 1.5 * upper, upper, 100, 75);
  if (bbp > 0) return interpolate(bbp, upper, 0, 75, 50);
  if (bbp < lower) return bbp < 1.5 * lower ? 0 : interpolate(bbp, lower, 1.5 * lower, 25, 0);
  return interpolate(bbp, 0, lower, 50, 25);
}

// ─── Trend Indicators (normalized 0-100) ────────────────────────────────────

/**
 * Trend normalization — LuxAlgo's normalize() function
 * Tracks max/min within trend state, maps current price to 0-100
 */
function trendNormalize(
  closes: number[],
  buySignals: boolean[],
  sellSignals: boolean[],
  smooth: number = 3,
): number {
  if (closes.length === 0) return 50;

  let os = 0;
  let max = closes[0];
  let min = closes[0];
  const normalized: number[] = [];

  for (let i = 0; i < closes.length; i++) {
    const prevOs = os;
    if (buySignals[i]) os = 1;
    else if (sellSignals[i]) os = -1;

    if (os > prevOs) {
      // New uptrend: reset min
      max = closes[i];
      min = closes[i];
    } else if (os < prevOs) {
      // New downtrend: reset max
      max = closes[i];
      min = closes[i];
    } else {
      max = Math.max(closes[i], max);
      min = Math.min(closes[i], min);
    }

    const range = max - min;
    normalized.push(range > 0 ? ((closes[i] - min) / range) * 100 : 50);
  }

  return sma(normalized, smooth);
}

/**
 * Moving Average position — normalized per LuxAlgo
 */
export function maNormalized(
  closes: number[],
  length: number = 20,
  smooth: number = 3,
): number {
  if (closes.length < length) return 50;

  const maValues: number[] = [];
  for (let i = length - 1; i < closes.length; i++) {
    maValues.push(sma(closes.slice(0, i + 1), length));
  }

  const buySignals = maValues.map((ma, i) => {
    const ci = i + length - 1;
    return closes[ci] > ma;
  });
  const sellSignals = maValues.map((ma, i) => {
    const ci = i + length - 1;
    return closes[ci] < ma;
  });

  const relevantCloses = closes.slice(length - 1);
  return trendNormalize(relevantCloses, buySignals, sellSignals, smooth);
}

/**
 * Bollinger Band position — normalized per LuxAlgo
 */
export function bbNormalized(
  closes: number[],
  length: number = 20,
  mult: number = 2,
  smooth: number = 3,
): number {
  if (closes.length < length) return 50;

  const buySignals: boolean[] = [];
  const sellSignals: boolean[] = [];

  for (let i = length - 1; i < closes.length; i++) {
    const slice = closes.slice(i - length + 1, i + 1);
    const basis = sma(slice, length);
    const dev = stdev(slice, length) * mult;
    buySignals.push(closes[i] > basis + dev);
    sellSignals.push(closes[i] < basis - dev);
  }

  const relevantCloses = closes.slice(length - 1);
  return trendNormalize(relevantCloses, buySignals, sellSignals, smooth);
}

/**
 * Supertrend — normalized per LuxAlgo
 */
export function supertrendNormalized(
  closes: number[],
  highs: number[],
  lows: number[],
  factor: number = 3,
  period: number = 10,
  smooth: number = 3,
): number {
  if (closes.length < period + 1) return 50;

  const tr = trueRange(highs, lows, closes);
  let atrVal = sma(tr.slice(0, period), period);

  let upperBand = (highs[period - 1] + lows[period - 1]) / 2 + factor * atrVal;
  let lowerBand = (highs[period - 1] + lows[period - 1]) / 2 - factor * atrVal;
  let direction = closes[period - 1] > upperBand ? 1 : -1;

  const buySignals: boolean[] = new Array(period).fill(false);
  const sellSignals: boolean[] = new Array(period).fill(false);

  for (let i = period; i < closes.length; i++) {
    atrVal = (atrVal * (period - 1) + tr[i]) / period;
    const hl2 = (highs[i] + lows[i]) / 2;
    const newUpper = hl2 + factor * atrVal;
    const newLower = hl2 - factor * atrVal;

    if (newLower > lowerBand || closes[i - 1] < lowerBand) {
      lowerBand = newLower;
    }
    if (newUpper < upperBand || closes[i - 1] > upperBand) {
      upperBand = newUpper;
    }

    const prevDir = direction;
    if (closes[i] > upperBand) direction = 1;
    else if (closes[i] < lowerBand) direction = -1;

    buySignals.push(direction === 1 && prevDir !== 1);
    sellSignals.push(direction === -1 && prevDir !== -1);
  }

  return trendNormalize(closes, buySignals, sellSignals, smooth);
}

/**
 * Linear Regression — correlation-based, 0-100 per LuxAlgo
 */
export function linearRegressionNormalized(
  closes: number[],
  length: number = 25,
): number {
  if (closes.length < length) return 50;

  const slice = closes.slice(-length);
  const indices = Array.from({ length }, (_, i) => i);

  const meanX = indices.reduce((s, v) => s + v, 0) / length;
  const meanY = slice.reduce((s, v) => s + v, 0) / length;

  let numerator = 0;
  let denomX = 0;
  let denomY = 0;

  for (let i = 0; i < length; i++) {
    const dx = indices[i] - meanX;
    const dy = slice[i] - meanY;
    numerator += dx * dy;
    denomX += dx * dx;
    denomY += dy * dy;
  }

  const denom = Math.sqrt(denomX * denomY);
  const correlation = denom === 0 ? 0 : numerator / denom;

  // Map -1..1 correlation to 0..100
  return 50 * correlation + 50;
}

/**
 * Market Structure — pivot-based, normalized per LuxAlgo
 */
export function marketStructureNormalized(
  closes: number[],
  highs: number[],
  lows: number[],
  length: number = 5,
  smooth: number = 3,
): number {
  if (closes.length < length * 2 + 1) return 50;

  let phY = highs[0];
  let plY = lows[0];
  let phCross = false;
  let plCross = false;

  const buySignals: boolean[] = [];
  const sellSignals: boolean[] = [];

  for (let i = 0; i < closes.length; i++) {
    let buy = false;
    let sell = false;

    // Check for pivot high
    if (i >= length && i < closes.length - length) {
      let isPivotHigh = true;
      let isPivotLow = true;
      for (let j = 1; j <= length; j++) {
        if (highs[i - j] >= highs[i] || highs[i + j] >= highs[i]) isPivotHigh = false;
        if (lows[i - j] <= lows[i] || lows[i + j] <= lows[i]) isPivotLow = false;
      }
      if (isPivotHigh) {
        phY = highs[i];
        phCross = false;
      }
      if (isPivotLow) {
        plY = lows[i];
        plCross = false;
      }
    }

    if (closes[i] > phY && !phCross) {
      phCross = true;
      buy = true;
    }
    if (closes[i] < plY && !plCross) {
      plCross = true;
      sell = true;
    }

    buySignals.push(buy);
    sellSignals.push(sell);
  }

  return trendNormalize(closes, buySignals, sellSignals, smooth);
}

// ─── TTM Squeeze (LazyBear) ─────────────────────────────────────────────────

export interface SqueezeResult {
  /** Is the squeeze on? (BB inside KC) */
  squeezeOn: boolean;
  /** Momentum histogram value */
  momentum: number;
  /** Momentum direction: 1 = increasing, -1 = decreasing */
  momentumDirection: number;
}

/**
 * TTM Squeeze — Bollinger Bands inside Keltner Channels
 * When BB squeezes inside KC, a big move is coming.
 * Momentum = linear regression of (close - midline of KC/BB)
 */
export function ttmSqueeze(
  closes: number[],
  highs: number[],
  lows: number[],
  bbLength: number = 20,
  bbMult: number = 2.0,
  kcLength: number = 20,
  kcMult: number = 1.5,
  momentumLength: number = 12,
): SqueezeResult {
  if (closes.length < Math.max(bbLength, kcLength, momentumLength)) {
    return { squeezeOn: false, momentum: 0, momentumDirection: 0 };
  }

  // Bollinger Bands
  const bbBasis = sma(closes, bbLength);
  const bbDev = stdev(closes, bbLength) * bbMult;
  const bbUpper = bbBasis + bbDev;
  const bbLower = bbBasis - bbDev;

  // Keltner Channels
  const kcBasis = sma(closes, kcLength);
  const atrVal = atr(highs, lows, closes, kcLength);
  const kcUpper = kcBasis + kcMult * atrVal;
  const kcLower = kcBasis - kcMult * atrVal;

  // Squeeze = BB inside KC
  const squeezeOn = bbLower > kcLower && bbUpper < kcUpper;

  // Momentum = linear regression of (close - avg(avg(highest, lowest), basis))
  const recentHighs = highs.slice(-momentumLength);
  const recentLows = lows.slice(-momentumLength);
  const hh = Math.max(...recentHighs);
  const ll = Math.min(...recentLows);
  const midline = (sma(closes, momentumLength) + (hh + ll) / 2) / 2;
  const momentum = closes[closes.length - 1] - midline;

  // Direction
  const prevCloses = closes.slice(0, -1);
  let prevMomentum = 0;
  if (prevCloses.length >= momentumLength) {
    const prevHighs = highs.slice(-momentumLength - 1, -1);
    const prevLows = lows.slice(-momentumLength - 1, -1);
    const prevHH = Math.max(...prevHighs);
    const prevLL = Math.min(...prevLows);
    const prevMidline = (sma(prevCloses, momentumLength) + (prevHH + prevLL) / 2) / 2;
    prevMomentum = prevCloses[prevCloses.length - 1] - prevMidline;
  }

  const momentumDirection = momentum > prevMomentum ? 1 : -1;

  return { squeezeOn, momentum, momentumDirection };
}

// ─── Composite Sentiment Score ──────────────────────────────────────────────

export interface SentimentResult {
  /** Overall sentiment 0-100 (avg of all indicators) */
  sentiment: number;
  /** Individual indicator values */
  rsi: number;
  stochastic: number;
  stochRsi: number;
  cci: number;
  bbp: number;
  ma: number;
  bb: number;
  supertrend: number;
  linearRegression: number;
  marketStructure: number;
  /** TTM Squeeze state */
  squeeze: SqueezeResult;
}

/**
 * Compute the full LuxAlgo-style market sentiment from candle data.
 * Returns composite sentiment (0-100) plus all individual indicators.
 */
export function computeMarketSentiment(
  closes: number[],
  highs: number[],
  lows: number[],
): SentimentResult {
  const rsi = rsiNormalized(closes, 14);
  const stochastic = stochasticNormalized(closes, highs, lows, 14, 3);
  const stochRsi = stochRsiNormalized(closes, 14, 14, 3);
  const cci = cciNormalized(closes, highs, lows, 20);
  const bbp = bbpNormalized(closes, highs, lows, 13);
  const ma = maNormalized(closes, 20, 3);
  const bb = bbNormalized(closes, 20, 2, 3);
  const supertrend = supertrendNormalized(closes, highs, lows, 3, 10, 3);
  const linearRegression = linearRegressionNormalized(closes, 25);
  const marketStructure = marketStructureNormalized(closes, highs, lows, 5, 3);
  const squeeze = ttmSqueeze(closes, highs, lows);

  const sentiment = (rsi + stochastic + stochRsi + cci + bbp + ma + bb + supertrend + linearRegression + marketStructure) / 10;

  return {
    sentiment: Math.round(sentiment * 100) / 100,
    rsi: Math.round(rsi * 100) / 100,
    stochastic: Math.round(stochastic * 100) / 100,
    stochRsi: Math.round(stochRsi * 100) / 100,
    cci: Math.round(cci * 100) / 100,
    bbp: Math.round(bbp * 100) / 100,
    ma: Math.round(ma * 100) / 100,
    bb: Math.round(bb * 100) / 100,
    supertrend: Math.round(supertrend * 100) / 100,
    linearRegression: Math.round(linearRegression * 100) / 100,
    marketStructure: Math.round(marketStructure * 100) / 100,
    squeeze,
  };
}

/**
 * Technical Indicators Calculation Utilities
 * Provides comprehensive technical analysis indicators for financial charting
 */

/**
 * Simple Moving Average
 */
export const calculateSMA = (data, period, key = 'close') => {
  if (!data || data.length < period) return [];
  
  const result = [];
  
  for (let i = period - 1; i < data.length; i++) {
    const sum = data.slice(i - period + 1, i + 1)
      .reduce((acc, item) => acc + (item[key] || 0), 0);
    
    result.push({
      ...data[i],
      [`sma${period}`]: sum / period
    });
  }
  
  return result;
};

/**
 * Exponential Moving Average
 */
export const calculateEMA = (data, period, key = 'close') => {
  if (!data || data.length === 0) return [];
  
  const result = [...data];
  const multiplier = 2 / (period + 1);
  
  // Initialize with SMA for first value
  let ema = data.slice(0, period).reduce((acc, item) => acc + (item[key] || 0), 0) / period;
  
  for (let i = period - 1; i < data.length; i++) {
    if (i === period - 1) {
      result[i][`ema${period}`] = ema;
    } else {
      ema = (data[i][key] - ema) * multiplier + ema;
      result[i][`ema${period}`] = ema;
    }
  }
  
  return result;
};

/**
 * Relative Strength Index (RSI)
 */
export const calculateRSI = (data, period = 14, key = 'close') => {
  if (!data || data.length <= period) return [];
  
  const result = [...data];
  const gains = [];
  const losses = [];
  
  // Calculate price changes
  for (let i = 1; i < data.length; i++) {
    const change = data[i][key] - data[i - 1][key];
    gains.push(change > 0 ? change : 0);
    losses.push(change < 0 ? Math.abs(change) : 0);
  }
  
  // Calculate initial average gain and loss
  let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
  let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
  
  for (let i = period; i < data.length; i++) {
    // Smoothed averages
    avgGain = ((avgGain * (period - 1)) + gains[i - 1]) / period;
    avgLoss = ((avgLoss * (period - 1)) + losses[i - 1]) / period;
    
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    const rsi = 100 - (100 / (1 + rs));
    
    result[i].rsi = rsi;
  }
  
  return result;
};

/**
 * Moving Average Convergence Divergence (MACD)
 */
export const calculateMACD = (data, fastPeriod = 12, slowPeriod = 26, signalPeriod = 9, key = 'close') => {
  if (!data || data.length < slowPeriod) return [];
  
  // Calculate EMAs
  const fastEMA = calculateEMA(data, fastPeriod, key);
  const slowEMA = calculateEMA(data, slowPeriod, key);
  
  const result = [];
  
  for (let i = slowPeriod - 1; i < data.length; i++) {
    const macd = fastEMA[i][`ema${fastPeriod}`] - slowEMA[i][`ema${slowPeriod}`];
    
    result.push({
      ...data[i],
      macd,
      macdSignal: null,
      macdHistogram: null
    });
  }
  
  // Calculate MACD signal line (EMA of MACD)
  if (result.length >= signalPeriod) {
    const multiplier = 2 / (signalPeriod + 1);
    let signalEMA = result.slice(0, signalPeriod).reduce((acc, item) => acc + item.macd, 0) / signalPeriod;
    
    for (let i = signalPeriod - 1; i < result.length; i++) {
      if (i === signalPeriod - 1) {
        result[i].macdSignal = signalEMA;
      } else {
        signalEMA = (result[i].macd - signalEMA) * multiplier + signalEMA;
        result[i].macdSignal = signalEMA;
      }
      
      result[i].macdHistogram = result[i].macd - result[i].macdSignal;
    }
  }
  
  return result;
};

/**
 * Bollinger Bands
 */
export const calculateBollingerBands = (data, period = 20, stdDev = 2, key = 'close') => {
  if (!data || data.length < period) return [];
  
  const result = [];
  
  for (let i = period - 1; i < data.length; i++) {
    const slice = data.slice(i - period + 1, i + 1);
    const sum = slice.reduce((acc, item) => acc + (item[key] || 0), 0);
    const sma = sum / period;
    
    // Calculate standard deviation
    const variance = slice.reduce((acc, item) => {
      const diff = (item[key] || 0) - sma;
      return acc + (diff * diff);
    }, 0) / period;
    
    const standardDeviation = Math.sqrt(variance);
    
    result.push({
      ...data[i],
      bbMiddle: sma,
      bbUpper: sma + (standardDeviation * stdDev),
      bbLower: sma - (standardDeviation * stdDev),
      bbWidth: (standardDeviation * stdDev * 2),
      bbPercent: ((data[i][key] - (sma - standardDeviation * stdDev)) / (standardDeviation * stdDev * 2)) * 100
    });
  }
  
  return result;
};

/**
 * Stochastic Oscillator
 */
export const calculateStochastic = (data, kPeriod = 14, dPeriod = 3) => {
  if (!data || data.length < kPeriod) return [];
  
  const result = [];
  
  for (let i = kPeriod - 1; i < data.length; i++) {
    const slice = data.slice(i - kPeriod + 1, i + 1);
    const highestHigh = Math.max(...slice.map(item => item.high || 0));
    const lowestLow = Math.min(...slice.map(item => item.low || Number.MAX_VALUE));
    
    const currentClose = data[i].close || 0;
    const kPercent = ((currentClose - lowestLow) / (highestHigh - lowestLow)) * 100;
    
    result.push({
      ...data[i],
      stochK: kPercent
    });
  }
  
  // Calculate %D (SMA of %K)
  for (let i = dPeriod - 1; i < result.length; i++) {
    const dValue = result.slice(i - dPeriod + 1, i + 1)
      .reduce((acc, item) => acc + item.stochK, 0) / dPeriod;
    
    result[i].stochD = dValue;
  }
  
  return result;
};

/**
 * Average True Range (ATR)
 */
export const calculateATR = (data, period = 14) => {
  if (!data || data.length < 2) return [];
  
  const result = [...data];
  const trValues = [];
  
  // Calculate True Range for each period
  for (let i = 1; i < data.length; i++) {
    const high = data[i].high || 0;
    const low = data[i].low || 0;
    const prevClose = data[i - 1].close || 0;
    
    const tr = Math.max(
      high - low,
      Math.abs(high - prevClose),
      Math.abs(low - prevClose)
    );
    
    trValues.push(tr);
    result[i].tr = tr;
  }
  
  // Calculate ATR (smoothed average of TR)
  if (trValues.length >= period) {
    let atr = trValues.slice(0, period).reduce((a, b) => a + b, 0) / period;
    result[period].atr = atr;
    
    for (let i = period + 1; i < result.length; i++) {
      atr = ((atr * (period - 1)) + trValues[i - 1]) / period;
      result[i].atr = atr;
    }
  }
  
  return result;
};

/**
 * Williams %R
 */
export const calculateWilliamsR = (data, period = 14) => {
  if (!data || data.length < period) return [];
  
  const result = [];
  
  for (let i = period - 1; i < data.length; i++) {
    const slice = data.slice(i - period + 1, i + 1);
    const highestHigh = Math.max(...slice.map(item => item.high || 0));
    const lowestLow = Math.min(...slice.map(item => item.low || Number.MAX_VALUE));
    const currentClose = data[i].close || 0;
    
    const williamsR = ((highestHigh - currentClose) / (highestHigh - lowestLow)) * -100;
    
    result.push({
      ...data[i],
      williamsR
    });
  }
  
  return result;
};

/**
 * Commodity Channel Index (CCI)
 */
export const calculateCCI = (data, period = 20) => {
  if (!data || data.length < period) return [];
  
  const result = [];
  
  for (let i = period - 1; i < data.length; i++) {
    const slice = data.slice(i - period + 1, i + 1);
    
    // Calculate typical prices for the period
    const typicalPrices = slice.map(item => 
      ((item.high || 0) + (item.low || 0) + (item.close || 0)) / 3
    );
    
    const smaTP = typicalPrices.reduce((a, b) => a + b, 0) / period;
    const currentTP = typicalPrices[typicalPrices.length - 1];
    
    // Calculate mean deviation
    const meanDeviation = typicalPrices.reduce((acc, tp) => 
      acc + Math.abs(tp - smaTP), 0) / period;
    
    const cci = (currentTP - smaTP) / (0.015 * meanDeviation);
    
    result.push({
      ...data[i],
      cci
    });
  }
  
  return result;
};

/**
 * On-Balance Volume (OBV)
 */
export const calculateOBV = (data) => {
  if (!data || data.length < 2) return [];
  
  const result = [...data];
  let obv = 0;
  
  result[0].obv = 0;
  
  for (let i = 1; i < data.length; i++) {
    const currentClose = data[i].close || 0;
    const prevClose = data[i - 1].close || 0;
    const volume = data[i].volume || 0;
    
    if (currentClose > prevClose) {
      obv += volume;
    } else if (currentClose < prevClose) {
      obv -= volume;
    }
    
    result[i].obv = obv;
  }
  
  return result;
};

/**
 * Money Flow Index (MFI)
 */
export const calculateMFI = (data, period = 14) => {
  if (!data || data.length < period + 1) return [];
  
  const result = [];
  const moneyFlows = [];
  
  // Calculate raw money flow for each period
  for (let i = 1; i < data.length; i++) {
    const typical = ((data[i].high || 0) + (data[i].low || 0) + (data[i].close || 0)) / 3;
    const prevTypical = ((data[i-1].high || 0) + (data[i-1].low || 0) + (data[i-1].close || 0)) / 3;
    const volume = data[i].volume || 0;
    
    const rawMoneyFlow = typical * volume;
    const isPositive = typical > prevTypical;
    
    moneyFlows.push({
      positive: isPositive ? rawMoneyFlow : 0,
      negative: isPositive ? 0 : rawMoneyFlow
    });
  }
  
  // Calculate MFI for each period
  for (let i = period - 1; i < moneyFlows.length; i++) {
    const slice = moneyFlows.slice(i - period + 1, i + 1);
    const positiveFlow = slice.reduce((acc, mf) => acc + mf.positive, 0);
    const negativeFlow = slice.reduce((acc, mf) => acc + mf.negative, 0);
    
    const moneyRatio = negativeFlow === 0 ? 100 : positiveFlow / negativeFlow;
    const mfi = 100 - (100 / (1 + moneyRatio));
    
    result.push({
      ...data[i + 1],
      mfi
    });
  }
  
  return result;
};

/**
 * Volume Weighted Average Price (VWAP)
 */
export const calculateVWAP = (data) => {
  if (!data || data.length === 0) return [];
  
  const result = [...data];
  let cumulativeVolume = 0;
  let cumulativeVolumePrice = 0;
  
  for (let i = 0; i < data.length; i++) {
    const typical = ((data[i].high || 0) + (data[i].low || 0) + (data[i].close || 0)) / 3;
    const volume = data[i].volume || 0;
    
    cumulativeVolumePrice += typical * volume;
    cumulativeVolume += volume;
    
    result[i].vwap = cumulativeVolume > 0 ? cumulativeVolumePrice / cumulativeVolume : 0;
  }
  
  return result;
};

/**
 * Fibonacci Retracement Levels
 */
export const calculateFibonacci = (data, high = null, low = null) => {
  if (!data || data.length === 0) return { levels: [], high: 0, low: 0 };
  
  const dataHigh = high !== null ? high : Math.max(...data.map(item => item.high || 0));
  const dataLow = low !== null ? low : Math.min(...data.map(item => item.low || Number.MAX_VALUE));
  
  const diff = dataHigh - dataLow;
  
  const levels = [
    { level: 0, price: dataHigh, label: '0.0%' },
    { level: 23.6, price: dataHigh - (diff * 0.236), label: '23.6%' },
    { level: 38.2, price: dataHigh - (diff * 0.382), label: '38.2%' },
    { level: 50, price: dataHigh - (diff * 0.5), label: '50.0%' },
    { level: 61.8, price: dataHigh - (diff * 0.618), label: '61.8%' },
    { level: 78.6, price: dataHigh - (diff * 0.786), label: '78.6%' },
    { level: 100, price: dataLow, label: '100.0%' }
  ];
  
  return {
    levels,
    high: dataHigh,
    low: dataLow,
    range: diff
  };
};

/**
 * Pivot Points
 */
export const calculatePivotPoints = (high, low, close) => {
  const pivot = (high + low + close) / 3;
  
  return {
    pivot,
    r1: (2 * pivot) - low,
    r2: pivot + (high - low),
    r3: high + (2 * (pivot - low)),
    s1: (2 * pivot) - high,
    s2: pivot - (high - low),
    s3: low - (2 * (high - pivot))
  };
};

/**
 * Parabolic SAR
 */
export const calculateParabolicSAR = (data, step = 0.02, maxStep = 0.2) => {
  if (!data || data.length < 2) return [];
  
  const result = [...data];
  let isUptrend = true;
  let sar = data[0].low || 0;
  let ep = data[0].high || 0;
  let af = step;
  
  result[0].sar = sar;
  
  for (let i = 1; i < data.length; i++) {
    const high = data[i].high || 0;
    const low = data[i].low || 0;
    
    // Calculate new SAR
    sar = sar + af * (ep - sar);
    
    if (isUptrend) {
      // Uptrend logic
      if (low <= sar) {
        // Trend reversal
        isUptrend = false;
        sar = ep;
        ep = low;
        af = step;
      } else {
        if (high > ep) {
          ep = high;
          af = Math.min(af + step, maxStep);
        }
        // SAR should not exceed previous two period lows
        const prevLow = Math.min(data[i - 1].low || 0, i > 1 ? data[i - 2].low || 0 : data[i - 1].low || 0);
        sar = Math.min(sar, prevLow);
      }
    } else {
      // Downtrend logic
      if (high >= sar) {
        // Trend reversal
        isUptrend = true;
        sar = ep;
        ep = high;
        af = step;
      } else {
        if (low < ep) {
          ep = low;
          af = Math.min(af + step, maxStep);
        }
        // SAR should not exceed previous two period highs
        const prevHigh = Math.max(data[i - 1].high || 0, i > 1 ? data[i - 2].high || 0 : data[i - 1].high || 0);
        sar = Math.max(sar, prevHigh);
      }
    }
    
    result[i].sar = sar;
    result[i].sarTrend = isUptrend ? 'up' : 'down';
  }
  
  return result;
};

/**
 * Utility function to combine multiple indicators
 */
export const calculateAllIndicators = (data, options = {}) => {
  if (!data || data.length === 0) return [];
  
  const {
    sma = [20, 50, 200],
    ema = [12, 26],
    rsi = true,
    macd = true,
    bollinger = true,
    stochastic = true,
    atr = true,
    williamsR = true,
    cci = true,
    obv = true,
    mfi = true,
    vwap = true,
    sar = true
  } = options;
  
  let result = [...data];
  
  // Calculate SMAs
  sma.forEach(period => {
    result = calculateSMA(result, period);
  });
  
  // Calculate EMAs
  ema.forEach(period => {
    result = calculateEMA(result, period);
  });
  
  // Calculate other indicators
  if (rsi) result = calculateRSI(result);
  if (macd) result = calculateMACD(result);
  if (bollinger) result = calculateBollingerBands(result);
  if (stochastic) result = calculateStochastic(result);
  if (atr) result = calculateATR(result);
  if (williamsR) result = calculateWilliamsR(result);
  if (cci) result = calculateCCI(result);
  if (obv) result = calculateOBV(result);
  if (mfi) result = calculateMFI(result);
  if (vwap) result = calculateVWAP(result);
  if (sar) result = calculateParabolicSAR(result);
  
  return result;
};
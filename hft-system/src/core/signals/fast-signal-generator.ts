/**
 * Ultra-Fast Signal Generation Engine
 * 
 * Incremental technical indicator calculations with O(1) updates.
 * Optimized for sub-millisecond signal generation.
 */

import { TechnicalData, MicrostructureData } from '../timeseries/timeseries-engine';
import { Signal, SignalType, SignalSource } from '../../types';

/**
 * Incremental Exponential Moving Average - O(1) updates
 */
export class IncrementalEMA {
  private value: number = 0;
  private alpha: number;
  private initialized: boolean = false;
  
  constructor(period: number) {
    this.alpha = 2 / (period + 1);
  }
  
  update(price: number): number {
    if (!this.initialized) {
      this.value = price;
      this.initialized = true;
    } else {
      this.value = this.alpha * price + (1 - this.alpha) * this.value;
    }
    return this.value;
  }
  
  getValue(): number {
    return this.value;
  }
  
  reset(): void {
    this.value = 0;
    this.initialized = false;
  }
}

/**
 * Incremental RSI - O(1) updates using Wilder's smoothing
 */
export class IncrementalRSI {
  private period: number;
  private avgGain: number = 0;
  private avgLoss: number = 0;
  private lastPrice: number = 0;
  private initialized: boolean = false;
  private alpha: number;
  
  constructor(period: number = 14) {
    this.period = period;
    this.alpha = 1 / period;
  }
  
  update(price: number): number {
    if (!this.initialized) {
      this.lastPrice = price;
      this.initialized = true;
      return 50; // Neutral RSI
    }
    
    const change = price - this.lastPrice;
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? -change : 0;
    
    // Wilder's smoothing
    this.avgGain = this.avgGain === 0 ? gain : this.avgGain * (1 - this.alpha) + gain * this.alpha;
    this.avgLoss = this.avgLoss === 0 ? loss : this.avgLoss * (1 - this.alpha) + loss * this.alpha;
    
    this.lastPrice = price;
    
    if (this.avgLoss === 0) return 100;
    
    const rs = this.avgGain / this.avgLoss;
    return 100 - (100 / (1 + rs));
  }
  
  getValue(): number {
    if (this.avgLoss === 0) return 100;
    const rs = this.avgGain / this.avgLoss;
    return 100 - (100 / (1 + rs));
  }
}

/**
 * Incremental MACD - O(1) updates
 */
export class IncrementalMACD {
  private fastEMA: IncrementalEMA;
  private slowEMA: IncrementalEMA;
  private signalEMA: IncrementalEMA;
  
  constructor(fastPeriod: number = 12, slowPeriod: number = 26, signalPeriod: number = 9) {
    this.fastEMA = new IncrementalEMA(fastPeriod);
    this.slowEMA = new IncrementalEMA(slowPeriod);
    this.signalEMA = new IncrementalEMA(signalPeriod);
  }
  
  update(price: number): { macd: number; signal: number; histogram: number } {
    const fastValue = this.fastEMA.update(price);
    const slowValue = this.slowEMA.update(price);
    const macdValue = fastValue - slowValue;
    const signalValue = this.signalEMA.update(macdValue);
    const histogram = macdValue - signalValue;
    
    return {
      macd: macdValue,
      signal: signalValue,
      histogram
    };
  }
}

/**
 * Incremental Bollinger Bands - O(1) updates with rolling variance
 */
export class IncrementalBollingerBands {
  private period: number;
  private sma: number = 0;
  private variance: number = 0;
  private prices: number[] = [];
  private multiplier: number;
  
  constructor(period: number = 20, multiplier: number = 2) {
    this.period = period;
    this.multiplier = multiplier;
  }
  
  update(price: number): { upper: number; middle: number; lower: number; bandwidth: number } {
    this.prices.push(price);
    
    if (this.prices.length > this.period) {
      this.prices.shift();
    }
    
    // Calculate SMA
    this.sma = this.prices.reduce((sum, p) => sum + p, 0) / this.prices.length;
    
    // Calculate variance
    if (this.prices.length >= this.period) {
      this.variance = this.prices.reduce((sum, p) => sum + Math.pow(p - this.sma, 2), 0) / this.period;
    }
    
    const stdDev = Math.sqrt(this.variance);
    const upper = this.sma + (this.multiplier * stdDev);
    const lower = this.sma - (this.multiplier * stdDev);
    const bandwidth = upper - lower;
    
    return {
      upper,
      middle: this.sma,
      lower,
      bandwidth
    };
  }
}

/**
 * Volume-Weighted Average Price (VWAP) with session reset
 */
export class IncrementalVWAP {
  private cumulativePV: number = 0;
  private cumulativeVolume: number = 0;
  private sessionStart: bigint = 0n;
  
  constructor(sessionStart?: bigint) {
    this.sessionStart = sessionStart || BigInt(Date.now());
  }
  
  update(price: number, volume: number, timestamp: bigint): number {
    // Reset for new session
    if (timestamp > this.sessionStart + 24n * 60n * 60n * 1000n * 1000n) { // 24 hours in microseconds
      this.reset();
      this.sessionStart = timestamp;
    }
    
    this.cumulativePV += price * volume;
    this.cumulativeVolume += volume;
    
    return this.cumulativeVolume > 0 ? this.cumulativePV / this.cumulativeVolume : price;
  }
  
  getValue(): number {
    return this.cumulativeVolume > 0 ? this.cumulativePV / this.cumulativeVolume : 0;
  }
  
  reset(): void {
    this.cumulativePV = 0;
    this.cumulativeVolume = 0;
  }
}

/**
 * Fast Signal Generator with multiple indicators
 */
export class FastSignalGenerator {
  private readonly indicators: Map<string, SymbolIndicators> = new Map();
  
  /**
   * Initialize indicators for a symbol
   */
  initializeSymbol(symbol: string): void {
    if (this.indicators.has(symbol)) return;
    
    this.indicators.set(symbol, {
      ema12: new IncrementalEMA(12),
      ema26: new IncrementalEMA(26),
      ema50: new IncrementalEMA(50),
      ema200: new IncrementalEMA(200),
      rsi: new IncrementalRSI(14),
      macd: new IncrementalMACD(),
      bollinger: new IncrementalBollingerBands(20, 2),
      vwap: new IncrementalVWAP(),
      lastPrice: 0,
      priceChange: 0,
      volatility: 0,
      trend: 'neutral',
      momentum: 0
    });
  }
  
  /**
   * Generate signals from technical and microstructure data
   */
  generateSignals(
    symbol: string, 
    technicalData: TechnicalData, 
    microstructureData: MicrostructureData
  ): Signal[] {
    this.initializeSymbol(symbol);
    const indicators = this.indicators.get(symbol)!;
    const signals: Signal[] = [];
    
    const price = technicalData.currentPrice;
    const timestamp = Number(technicalData.timestamp);
    
    // Update all indicators
    const ema12 = indicators.ema12.update(price);
    const ema26 = indicators.ema26.update(price);
    const ema50 = indicators.ema50.update(price);
    const ema200 = indicators.ema200.update(price);
    const rsi = indicators.rsi.update(price);
    const macd = indicators.macd.update(price);
    const bollinger = indicators.bollinger.update(price);
    const vwap = indicators.vwap.update(price, technicalData.volume, technicalData.timestamp);
    
    // Calculate price change and momentum
    indicators.priceChange = indicators.lastPrice > 0 ? 
      (price - indicators.lastPrice) / indicators.lastPrice : 0;
    indicators.momentum = ema12 - ema26;
    indicators.lastPrice = price;
    
    // Determine trend
    if (ema12 > ema26 && ema26 > ema50) {
      indicators.trend = 'bullish';
    } else if (ema12 < ema26 && ema26 < ema50) {
      indicators.trend = 'bearish';
    } else {
      indicators.trend = 'neutral';
    }
    
    // Generate signals based on multiple conditions
    
    // 1. Mean Reversion Signal (primary scalping signal)
    if (this.shouldGenerateMeanReversionSignal(price, indicators, microstructureData)) {
      const signal = this.generateMeanReversionSignal(symbol, price, indicators, microstructureData, timestamp);
      if (signal) signals.push(signal);
    }
    
    // 2. Momentum Signal
    if (this.shouldGenerateMomentumSignal(indicators, microstructureData)) {
      const signal = this.generateMomentumSignal(symbol, price, indicators, microstructureData, timestamp);
      if (signal) signals.push(signal);
    }
    
    // 3. Breakout Signal
    if (this.shouldGenerateBreakoutSignal(price, indicators, microstructureData)) {
      const signal = this.generateBreakoutSignal(symbol, price, indicators, microstructureData, timestamp);
      if (signal) signals.push(signal);
    }
    
    // 4. Order Flow Signal
    if (this.shouldGenerateOrderFlowSignal(microstructureData)) {
      const signal = this.generateOrderFlowSignal(symbol, price, microstructureData, timestamp);
      if (signal) signals.push(signal);
    }
    
    return signals;
  }
    /**
   * Mean reversion signal generation (primary scalping strategy)
   */
  private shouldGenerateMeanReversionSignal(
    price: number, 
    indicators: SymbolIndicators, 
    microstructure: MicrostructureData
  ): boolean {
    const rsi = indicators.rsi.getValue();
    const { spread, imbalance } = microstructure;
    
    // Conditions for mean reversion:
    // 1. RSI oversold/overbought
    // 2. Tight spread (good liquidity)
    // 3. Price deviation from VWAP
    
    return (rsi < 30 || rsi > 70) && 
           spread < price * 0.001 && // Spread < 10 bps
           Math.abs(imbalance) < 0.6; // Reasonable order book balance
  }
  
  private generateMeanReversionSignal(
    symbol: string,
    price: number,
    indicators: SymbolIndicators,
    microstructure: MicrostructureData,
    timestamp: number
  ): Signal | null {
    const rsi = indicators.rsi.getValue();
    const vwap = indicators.vwap.getValue();
    const bollinger = indicators.bollinger.update(price);
    const { bid, ask, imbalance } = microstructure;
    
    let type: SignalType;
    let strength: number;
    let targetPrice: number;
    let stopLoss: number;
    
    if (rsi < 30 && price < bollinger.lower) {
      // Oversold condition - buy signal
      type = SignalType.BUY;
      strength = Math.min(0.9, (30 - rsi) / 30 + 0.3);
      targetPrice = Math.min(vwap, bollinger.middle);
      stopLoss = price * 0.995; // 0.5% stop loss
    } else if (rsi > 70 && price > bollinger.upper) {
      // Overbought condition - sell signal
      type = SignalType.SELL;
      strength = Math.min(0.9, (rsi - 70) / 30 + 0.3);
      targetPrice = Math.max(vwap, bollinger.middle);
      stopLoss = price * 1.005; // 0.5% stop loss
    } else {
      return null;
    }
    
    return {
      id: `${symbol}_${timestamp}_meanreversion`,
      symbol,
      type,
      source: SignalSource.TECHNICAL,
      strength,
      target_price: targetPrice,
      stop_loss: stopLoss,
      expected_holding_period: 300, // 5 minutes
      timestamp,
      metadata: {
        rsi,
        vwap,
        bollinger,
        imbalance,
        bid,
        ask,
        strategy: 'mean_reversion'
      }
    };
  }
  
  /**
   * Momentum signal generation
   */
  private shouldGenerateMomentumSignal(
    indicators: SymbolIndicators, 
    microstructure: MicrostructureData
  ): boolean {
    const { momentum, trend } = indicators;
    const { imbalance } = microstructure;
    
    // Strong momentum with order book support
    return Math.abs(momentum) > 0.01 && 
           trend !== 'neutral' &&
           Math.abs(imbalance) > 0.3; // Order book imbalance supporting direction
  }
    private generateMomentumSignal(
    symbol: string,
    _price: number, // Prefix with underscore to indicate intentionally unused
    indicators: SymbolIndicators,
    microstructure: MicrostructureData,
    timestamp: number
  ): Signal | null {
    const { momentum, trend, ema12, ema26 } = indicators;
    const { imbalance } = microstructure;
    
    let type: SignalType;
    let strength: number;
    
    if (trend === 'bullish' && momentum > 0 && imbalance > 0.3) {
      type = SignalType.BUY;
      strength = Math.min(0.8, Math.abs(momentum) * 10 + Math.abs(imbalance));
    } else if (trend === 'bearish' && momentum < 0 && imbalance < -0.3) {
      type = SignalType.SELL;
      strength = Math.min(0.8, Math.abs(momentum) * 10 + Math.abs(imbalance));
    } else {
      return null;
    }
    
    return {
      id: `${symbol}_${timestamp}_momentum`,
      symbol,
      type,
      source: SignalSource.TECHNICAL,
      strength,
      expected_holding_period: 180, // 3 minutes
      timestamp,
      metadata: {
        momentum,
        trend,
        ema12,
        ema26,
        imbalance,
        strategy: 'momentum'
      }
    };
  }
    /**
   * Breakout signal generation
   */
  private shouldGenerateBreakoutSignal(
    price: number,
    indicators: SymbolIndicators,
    microstructure: MicrostructureData
  ): boolean {
    const bollinger = indicators.bollinger.update(price);
    const { spread } = microstructure;
    
    // Price breaking out of Bollinger Bands with good liquidity
    return (price > bollinger.upper || price < bollinger.lower) &&
           spread < price * 0.0005; // Very tight spread for breakout
  }
    private generateBreakoutSignal(
    symbol: string,
    price: number,
    indicators: SymbolIndicators,
    _microstructure: MicrostructureData, // Prefix with underscore to indicate intentionally unused
    timestamp: number
  ): Signal | null {
    const bollinger = indicators.bollinger.update(price);
    const rsi = indicators.rsi.getValue();
    
    let type: SignalType;
    let strength: number;
    
    if (price > bollinger.upper && rsi < 80) {
      type = SignalType.BUY;
      strength = 0.7;
    } else if (price < bollinger.lower && rsi > 20) {
      type = SignalType.SELL;
      strength = 0.7;
    } else {
      return null;
    }
    
    return {
      id: `${symbol}_${timestamp}_breakout`,
      symbol,
      type,
      source: SignalSource.TECHNICAL,
      strength,
      expected_holding_period: 600, // 10 minutes
      timestamp,
      metadata: {
        bollinger,
        rsi,
        breakoutLevel: type === SignalType.BUY ? bollinger.upper : bollinger.lower,
        strategy: 'breakout'
      }
    };
  }
  
  /**
   * Order flow signal generation
   */
  private shouldGenerateOrderFlowSignal(microstructure: MicrostructureData): boolean {
    const { imbalance, spread } = microstructure;
    
    // Strong order book imbalance with reasonable spread
    return Math.abs(imbalance) > 0.5 && spread < microstructure.mid * 0.001;
  }
  
  private generateOrderFlowSignal(
    symbol: string,
    _price: number, // Prefix with underscore to indicate intentionally unused
    microstructure: MicrostructureData,
    timestamp: number
  ): Signal | null {
    const { imbalance, bid, ask } = microstructure;
    
    let type: SignalType;
    const strength = Math.min(0.6, Math.abs(imbalance));
    
    if (imbalance > 0.5) {
      type = SignalType.BUY;
    } else if (imbalance < -0.5) {
      type = SignalType.SELL;
    } else {
      return null;
    }
    
    return {
      id: `${symbol}_${timestamp}_orderflow`,
      symbol,
      type,
      source: SignalSource.TECHNICAL,
      strength,
      expected_holding_period: 60, // 1 minute
      timestamp,
      metadata: {
        imbalance,
        bid,
        ask,
        strategy: 'order_flow'
      }
    };
  }
  
  /**
   * Get current indicator values for a symbol
   */
  getIndicatorValues(symbol: string): SymbolIndicators | null {
    return this.indicators.get(symbol) || null;
  }
  
  /**
   * Reset indicators for a symbol
   */
  resetIndicators(symbol: string): void {
    this.indicators.delete(symbol);
  }
}

// Type definitions
interface SymbolIndicators {
  ema12: IncrementalEMA;
  ema26: IncrementalEMA;
  ema50: IncrementalEMA;
  ema200: IncrementalEMA;
  rsi: IncrementalRSI;
  macd: IncrementalMACD;
  bollinger: IncrementalBollingerBands;
  vwap: IncrementalVWAP;
  lastPrice: number;
  priceChange: number;
  volatility: number;
  trend: 'bullish' | 'bearish' | 'neutral';
  momentum: number;
}

// Export singleton instance
export const fastSignalGenerator = new FastSignalGenerator();

/**
 * Advanced Institutional-Grade Scalping Strategy
 * 
 * Features:
 * - Sub-second decision making
 * - Multi-timeframe technical analysis
 * - Dynamic position sizing
 * - Real-time risk management
 * - Market microstructure analysis
 * - Ultra-low latency execution
 * - Adaptive algorithms based on market conditions
 */

import { MarketTick, OHLCVBar, OrderSide, OrderType } from '../types';
import { CircularBuffer, NumericCircularBuffer } from '../utils/circular-buffer';
import { HighResTimer } from '../utils/high-res-timer';
import { PerformanceMonitor } from '../utils/performance-monitor';
import { createLogger } from '../utils/logger';

export interface ScalpingConfig {
  // Strategy parameters
  maxPositionSize: number;
  minProfitThreshold: number;  // Minimum profit in basis points
  maxLossThreshold: number;    // Maximum loss in basis points
  
  // Technical indicators
  emaFastPeriod: number;
  emaSlowPeriod: number;
  rsiPeriod: number;
  rsiOverbought: number;
  rsiOversold: number;
  
  // Market microstructure
  bidAskSpreadThreshold: number;  // Maximum spread to trade
  volumeThreshold: number;        // Minimum volume requirement
  liquidityThreshold: number;     // Minimum liquidity requirement
  
  // Risk management
  maxDrawdown: number;           // Maximum drawdown percentage
  maxDailyLoss: number;         // Maximum daily loss
  positionTimeout: number;       // Maximum time to hold position (ms)
  
  // Execution
  slippageTolerance: number;     // Maximum acceptable slippage
  partialFillTimeout: number;    // Timeout for partial fills
}

export interface ScalpingSignal {
  symbol: string;
  timestamp: number;
  signal: 'BUY' | 'SELL' | 'HOLD';
  strength: number;  // Signal strength 0-1
  price: number;
  indicators: {
    emaFast: number;
    emaSlow: number;
    rsi: number;
    volume: number;
    spread: number;
    momentum: number;
  };
  confidence: number;  // Strategy confidence 0-1
}

export interface Position {
  symbol: string;
  side: OrderSide;
  size: number;
  entryPrice: number;
  currentPrice: number;
  unrealizedPnL: number;
  entryTime: number;
  holdTime: number;
}

export class AdvancedScalpingStrategy {
  private logger = createLogger('ScalpingStrategy');
  private config: ScalpingConfig;
  private timer: HighResTimer = new HighResTimer();
  private performanceMonitor: PerformanceMonitor = new PerformanceMonitor();
  
  // Price and indicator buffers per symbol
  private priceBuffers: Map<string, CircularBuffer<MarketTick>> = new Map();
  private ohlcvBuffers: Map<string, CircularBuffer<OHLCVBar>> = new Map();
  private emaFastBuffers: Map<string, NumericCircularBuffer> = new Map();
  private emaSlowBuffers: Map<string, NumericCircularBuffer> = new Map();
  private rsiBuffers: Map<string, NumericCircularBuffer> = new Map();
  private volumeBuffers: Map<string, NumericCircularBuffer> = new Map();
  
  // Current positions and signals
  private positions: Map<string, Position> = new Map();
  private signals: Map<string, ScalpingSignal> = new Map();
  
  // Strategy state
  private isActive: boolean = false;
  private dailyPnL: number = 0;
  private maxDrawdown: number = 0;
  private tradingStart: number = Date.now();
  
  // Performance tracking
  private signalCount: number = 0;
  private tradeCount: number = 0;
  private winCount: number = 0;
  private lossCount: number = 0;
  
  constructor(config: ScalpingConfig, symbols: string[]) {
    this.config = config;
    this.initializeBuffers(symbols);
    this.performanceMonitor.start();
    
    this.logger.info('Advanced Scalping Strategy initialized', {
      symbols: symbols.length,
      config: this.config
    });
  }
  
  /**
   * Initialize price and indicator buffers for all symbols
   */
  private initializeBuffers(symbols: string[]): void {
    for (const symbol of symbols) {
      // Price data buffers (1 hour of second-level data)
      this.priceBuffers.set(symbol, new CircularBuffer<MarketTick>(3600));
      this.ohlcvBuffers.set(symbol, new CircularBuffer<OHLCVBar>(360)); // 6 hours of minute bars
      
      // Technical indicator buffers
      this.emaFastBuffers.set(symbol, new NumericCircularBuffer(Math.max(this.config.emaFastPeriod * 3, 100)));
      this.emaSlowBuffers.set(symbol, new NumericCircularBuffer(Math.max(this.config.emaSlowPeriod * 3, 200)));
      this.rsiBuffers.set(symbol, new NumericCircularBuffer(Math.max(this.config.rsiPeriod * 3, 100)));
      this.volumeBuffers.set(symbol, new NumericCircularBuffer(100));
    }
  }
  
  /**
   * Process new market tick
   */
  async processTick(tick: MarketTick): Promise<void> {
    const startTime = this.timer.now();
    
    try {
      // Store tick data
      const priceBuffer = this.priceBuffers.get(tick.symbol);
      if (!priceBuffer) return;
      
      priceBuffer.push(tick);
      
      // Update technical indicators
      await this.updateIndicators(tick);
      
      // Generate trading signal
      const signal = await this.generateSignal(tick);
      
      if (signal && signal.signal !== 'HOLD') {
        this.signals.set(tick.symbol, signal);
        
        // Execute trade if conditions are met
        if (this.shouldExecuteTrade(signal)) {
          await this.executeTrade(signal);
        }
      }
      
      // Update existing positions
      await this.updatePositions(tick);
      
      // Check risk limits
      await this.checkRiskLimits();
      
      this.signalCount++;
      
    } catch (error) {
      this.logger.error('Error processing tick:', error);
    } finally {
      // Record processing latency
      const latency = this.timer.elapsedMicros(startTime);
      this.performanceMonitor.recordLatency(latency);
      
      // Log slow processing
      if (latency > 1000) { // > 1ms
        this.logger.warn(`Slow tick processing: ${latency.toFixed(2)}μs for ${tick.symbol}`);
      }
    }
  }
  
  /**
   * Update technical indicators
   */
  private async updateIndicators(tick: MarketTick): Promise<void> {
    if (!tick.price) return;
    
    const symbol = tick.symbol;
    const price = tick.price;
    
    // Update EMA Fast
    const emaFastBuffer = this.emaFastBuffers.get(symbol);
    if (emaFastBuffer) {
      const emaFast = this.calculateEMA(price, emaFastBuffer, this.config.emaFastPeriod);
      emaFastBuffer.push(emaFast);
    }
    
    // Update EMA Slow
    const emaSlowBuffer = this.emaSlowBuffers.get(symbol);
    if (emaSlowBuffer) {
      const emaSlow = this.calculateEMA(price, emaSlowBuffer, this.config.emaSlowPeriod);
      emaSlowBuffer.push(emaSlow);
    }
    
    // Update RSI
    const rsiBuffer = this.rsiBuffers.get(symbol);
    if (rsiBuffer) {
      const rsi = this.calculateRSI(price, symbol);
      if (!isNaN(rsi)) {
        rsiBuffer.push(rsi);
      }
    }
    
    // Update Volume
    const volumeBuffer = this.volumeBuffers.get(symbol);
    if (volumeBuffer && tick.size) {
      volumeBuffer.push(tick.size);
    }
  }
  
  /**
   * Generate trading signal based on technical analysis
   */
  private async generateSignal(tick: MarketTick): Promise<ScalpingSignal | null> {
    const symbol = tick.symbol;
    const price = tick.price;
    
    if (!price) return null;
    
    // Get current indicator values
    const emaFast = this.emaFastBuffers.get(symbol)?.peek() ?? 0;
    const emaSlow = this.emaSlowBuffers.get(symbol)?.peek() ?? 0;
    const rsi = this.rsiBuffers.get(symbol)?.peek() ?? 50;
    const volume = this.volumeBuffers.get(symbol)?.peek() ?? 0;
    
    // Check market microstructure
    const spread = this.calculateSpread(tick);
    const momentum = this.calculateMomentum(symbol);
    
    // Signal generation logic
    let signal: 'BUY' | 'SELL' | 'HOLD' = 'HOLD';
    let strength = 0;
    let confidence = 0;
    
    // EMA Crossover Strategy
    if (emaFast > emaSlow && emaFast > 0 && emaSlow > 0) {
      // Bullish trend
      if (rsi < this.config.rsiOversold && momentum > 0) {
        signal = 'BUY';
        strength = Math.min(1, (this.config.rsiOversold - rsi) / 20 + momentum / 100);
        confidence = 0.8;
      }
    } else if (emaFast < emaSlow && emaFast > 0 && emaSlow > 0) {
      // Bearish trend
      if (rsi > this.config.rsiOverbought && momentum < 0) {
        signal = 'SELL';
        strength = Math.min(1, (rsi - this.config.rsiOverbought) / 20 + Math.abs(momentum) / 100);
        confidence = 0.8;
      }
    }
    
    // Market microstructure filters
    if (spread > this.config.bidAskSpreadThreshold) {
      signal = 'HOLD'; // Spread too wide
      confidence *= 0.5;
    }
    
    if (volume < this.config.volumeThreshold) {
      signal = 'HOLD'; // Insufficient volume
      confidence *= 0.7;
    }
    
    return {
      symbol,
      timestamp: this.timer.nowMicros(),
      signal,
      strength,
      price,
      indicators: {
        emaFast,
        emaSlow,
        rsi,
        volume,
        spread,
        momentum
      },
      confidence
    };
  }
  
  /**
   * Check if trade should be executed
   */
  private shouldExecuteTrade(signal: ScalpingSignal): boolean {
    // Don't trade if already have position in this symbol
    if (this.positions.has(signal.symbol)) {
      return false;
    }
    
    // Check signal strength and confidence
    if (signal.strength < 0.6 || signal.confidence < 0.7) {
      return false;
    }
    
    // Check daily loss limit
    if (this.dailyPnL < -this.config.maxDailyLoss) {
      this.logger.warn('Daily loss limit reached, stopping trading');
      return false;
    }
    
    // Check drawdown limit
    if (this.maxDrawdown > this.config.maxDrawdown) {
      this.logger.warn('Maximum drawdown reached, stopping trading');
      return false;
    }
    
    return true;
  }
  
  /**
   * Execute trade based on signal
   */
  private async executeTrade(signal: ScalpingSignal): Promise<void> {
    const executionStart = this.timer.now();
    
    try {
      const side: OrderSide = signal.signal === 'BUY' ? 'buy' : 'sell';
      const size = this.calculatePositionSize(signal);
      
      this.logger.info('Executing trade', {
        symbol: signal.symbol,
        side,
        size,
        price: signal.price,
        strength: signal.strength,
        confidence: signal.confidence
      });
      
      // Create position (in real implementation, this would place an order)
      const position: Position = {
        symbol: signal.symbol,
        side,
        size,
        entryPrice: signal.price,
        currentPrice: signal.price,
        unrealizedPnL: 0,
        entryTime: Date.now(),
        holdTime: 0
      };
      
      this.positions.set(signal.symbol, position);
      this.tradeCount++;
      
      // Record execution latency
      const executionLatency = this.timer.elapsedMicros(executionStart);
      this.performanceMonitor.recordLatency(executionLatency);
      
      this.logger.info(`Trade executed in ${executionLatency.toFixed(2)}μs`);
      
    } catch (error) {
      this.logger.error('Error executing trade:', error);
    }
  }
  
  /**
   * Update existing positions
   */
  private async updatePositions(tick: MarketTick): Promise<void> {
    const position = this.positions.get(tick.symbol);
    if (!position || !tick.price) return;
    
    // Update position metrics
    position.currentPrice = tick.price;
    position.holdTime = Date.now() - position.entryTime;
    
    // Calculate unrealized P&L
    const priceDiff = position.side === 'buy' 
      ? tick.price - position.entryPrice
      : position.entryPrice - tick.price;
    
    position.unrealizedPnL = priceDiff * position.size;
    
    // Check exit conditions
    const shouldExit = this.shouldExitPosition(position);
    
    if (shouldExit) {
      await this.exitPosition(position);
    }
  }
  
  /**
   * Check if position should be exited
   */
  private shouldExitPosition(position: Position): boolean {
    const pnlBasisPoints = (position.unrealizedPnL / (position.entryPrice * position.size)) * 10000;
    
    // Take profit
    if (pnlBasisPoints >= this.config.minProfitThreshold) {
      return true;
    }
    
    // Stop loss
    if (pnlBasisPoints <= -this.config.maxLossThreshold) {
      return true;
    }
    
    // Position timeout
    if (position.holdTime > this.config.positionTimeout) {
      return true;
    }
    
    return false;
  }
  
  /**
   * Exit position
   */
  private async exitPosition(position: Position): Promise<void> {
    const pnl = position.unrealizedPnL;
    this.dailyPnL += pnl;
    
    if (pnl > 0) {
      this.winCount++;
    } else {
      this.lossCount++;
    }
    
    // Update drawdown
    if (this.dailyPnL < 0 && Math.abs(this.dailyPnL) > this.maxDrawdown) {
      this.maxDrawdown = Math.abs(this.dailyPnL);
    }
    
    this.logger.info('Position closed', {
      symbol: position.symbol,
      side: position.side,
      size: position.size,
      entryPrice: position.entryPrice,
      exitPrice: position.currentPrice,
      pnl,
      holdTime: position.holdTime
    });
    
    this.positions.delete(position.symbol);
  }
  
  /**
   * Check risk limits
   */
  private async checkRiskLimits(): Promise<void> {
    // Check daily loss limit
    if (this.dailyPnL < -this.config.maxDailyLoss) {
      this.logger.error('Daily loss limit exceeded, stopping strategy');
      await this.stop();
    }
    
    // Check maximum drawdown
    if (this.maxDrawdown > this.config.maxDrawdown) {
      this.logger.error('Maximum drawdown exceeded, stopping strategy');
      await this.stop();
    }
  }
  
  /**
   * Calculate position size based on signal strength and risk management
   */
  private calculatePositionSize(signal: ScalpingSignal): number {
    const baseSize = this.config.maxPositionSize;
    const signalMultiplier = signal.strength * signal.confidence;
    
    return Math.floor(baseSize * signalMultiplier);
  }
  
  /**
   * Calculate bid-ask spread
   */
  private calculateSpread(tick: MarketTick): number {
    if (tick.bid && tick.ask) {
      return tick.ask - tick.bid;
    }
    return 0;
  }
  
  /**
   * Calculate momentum
   */
  private calculateMomentum(symbol: string): number {
    const priceBuffer = this.priceBuffers.get(symbol);
    if (!priceBuffer || priceBuffer.size() < 2) return 0;
    
    const current = priceBuffer.peek();
    const previous = priceBuffer.get(priceBuffer.size() - 2);
    
    if (!current || !previous || !current.price || !previous.price) return 0;
    
    return ((current.price - previous.price) / previous.price) * 100;
  }
  
  /**
   * Calculate EMA
   */
  private calculateEMA(price: number, buffer: NumericCircularBuffer, period: number): number {
    const prevEMA = buffer.peek();
    const multiplier = 2 / (period + 1);
    
    if (prevEMA === undefined || prevEMA === 0) {
      return price;
    }
    
    return (price * multiplier) + (prevEMA * (1 - multiplier));
  }
  
  /**
   * Calculate RSI
   */
  private calculateRSI(currentPrice: number, symbol: string): number {
    const priceBuffer = this.priceBuffers.get(symbol);
    if (!priceBuffer || priceBuffer.size() < this.config.rsiPeriod + 1) {
      return 50; // Neutral RSI
    }
    
    const prices = priceBuffer.last(this.config.rsiPeriod + 1).map(tick => tick.price || 0);
    
    let gains = 0;
    let losses = 0;
    
    for (let i = 1; i < prices.length; i++) {
      const change = prices[i] - prices[i - 1];
      if (change > 0) {
        gains += change;
      } else {
        losses -= change;
      }
    }
    
    const avgGain = gains / this.config.rsiPeriod;
    const avgLoss = losses / this.config.rsiPeriod;
    
    if (avgLoss === 0) return 100;
    
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }
  
  /**
   * Start strategy
   */
  async start(): Promise<void> {
    this.isActive = true;
    this.tradingStart = Date.now();
    this.logger.info('Advanced Scalping Strategy started');
  }
  
  /**
   * Stop strategy
   */
  async stop(): Promise<void> {
    this.isActive = false;
    
    // Close all positions
    for (const position of this.positions.values()) {
      await this.exitPosition(position);
    }
    
    this.performanceMonitor.stop();
    this.logger.info('Advanced Scalping Strategy stopped');
  }
  
  /**
   * Get strategy performance metrics
   */
  getPerformanceMetrics() {
    const uptime = Date.now() - this.tradingStart;
    const winRate = this.tradeCount > 0 ? (this.winCount / this.tradeCount) * 100 : 0;
    
    return {
      // Trading metrics
      signalCount: this.signalCount,
      tradeCount: this.tradeCount,
      winCount: this.winCount,
      lossCount: this.lossCount,
      winRate,
      
      // Financial metrics
      dailyPnL: this.dailyPnL,
      maxDrawdown: this.maxDrawdown,
      
      // Position metrics
      activePositions: this.positions.size,
      
      // System metrics
      uptime,
      isActive: this.isActive,
      
      // Performance metrics
      systemPerformance: this.performanceMonitor.getMetrics()
    };
  }
  
  /**
   * Get strategy summary
   */
  getSummary(): string {
    const metrics = this.getPerformanceMetrics();
    
    return `
Scalping Strategy Summary:
  Status: ${metrics.isActive ? 'ACTIVE' : 'STOPPED'}
  Signals: ${metrics.signalCount}
  Trades: ${metrics.tradeCount} (${metrics.winCount}W/${metrics.lossCount}L)
  Win Rate: ${metrics.winRate.toFixed(1)}%
  Daily P&L: $${metrics.dailyPnL.toFixed(2)}
  Max Drawdown: $${metrics.maxDrawdown.toFixed(2)}
  Active Positions: ${metrics.activePositions}
  
${this.performanceMonitor.getSummary()}
    `.trim();
  }
}

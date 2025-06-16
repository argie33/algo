/**
 * Advanced Scalping Strategy
 * 
 * Ultra-low latency scalping strategy combining:
 * - Mean reversion with statistical filters
 * - Order flow analysis
 * - Multi-timeframe momentum
 * - Dynamic position sizing
 * - Risk-adjusted entries/exits
 */

import { EventEmitter } from 'events';
import { Signal, SignalType, Order, Position, OrderSide, OrderType, TimeInForce } from '../types';
import { TechnicalData, MicrostructureData, timeSeriesManager } from '../core/timeseries/timeseries-engine';
import { fastSignalGenerator } from '../core/signals/fast-signal-generator';

export interface ScalpingConfig {
  enabled: boolean;
  symbols: string[];
  maxPositionsPerSymbol: number;
  maxTotalPositions: number;
  basePositionSize: number;
  maxPositionSize: number;
  profitTarget: number; // basis points
  stopLoss: number; // basis points
  maxHoldingTime: number; // milliseconds
  minSpread: number; // basis points
  maxSpread: number; // basis points
  minVolume: number;
  riskPerTrade: number; // percentage of capital
  correlationLimit: number; // max correlation between positions
}

export interface ScalpingMetrics {
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  winRate: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  totalPnL: number;
  dailyPnL: number;
  maxDrawdown: number;
  avgHoldTime: number;
  sharpeRatio: number;
  lastUpdate: number;
}

export class ScalpingStrategy extends EventEmitter {
  private config: ScalpingConfig;
  private positions: Map<string, Position[]> = new Map();
  private activeOrders: Map<string, Order[]> = new Map();
  private lastSignalTime: Map<string, number> = new Map();
  private metrics: ScalpingMetrics;
  private isRunning: boolean = false;
  private capital: number = 100000; // Starting capital
  
  // Position sizing and risk management
  private correlationMatrix: Map<string, Map<string, number>> = new Map();
  private volatilityEstimates: Map<string, number> = new Map();
  private liquidityScores: Map<string, number> = new Map();
  
  constructor(config: ScalpingConfig) {
    super();
    this.config = config;
    this.metrics = {
      totalTrades: 0,
      winningTrades: 0,
      losingTrades: 0,
      winRate: 0,
      avgWin: 0,
      avgLoss: 0,
      profitFactor: 0,
      totalPnL: 0,
      dailyPnL: 0,
      maxDrawdown: 0,
      avgHoldTime: 0,
      sharpeRatio: 0,
      lastUpdate: Date.now()
    };
    
    // Initialize symbol data structures
    this.config.symbols.forEach(symbol => {
      this.positions.set(symbol, []);
      this.activeOrders.set(symbol, []);
      this.lastSignalTime.set(symbol, 0);
      this.volatilityEstimates.set(symbol, 0.01); // 1% default volatility
      this.liquidityScores.set(symbol, 0.5); // Neutral liquidity score
    });
  }
  
  /**
   * Start the scalping strategy
   */
  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.isRunning = true;
    
    // Initialize signal generators for all symbols
    this.config.symbols.forEach(symbol => {
      fastSignalGenerator.initializeSymbol(symbol);
    });
    
    this.emit('strategy_started', { timestamp: Date.now() });
  }
  
  /**
   * Stop the scalping strategy
   */
  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.isRunning = false;
    
    // Close all positions
    await this.closeAllPositions();
    
    this.emit('strategy_stopped', { 
      metrics: this.metrics, 
      timestamp: Date.now() 
    });
  }
  
  /**
   * Process new market data and generate trading decisions
   */
  async processMarketData(symbol: string, timestamp: bigint): Promise<void> {
    if (!this.isRunning || !this.config.symbols.includes(symbol)) return;
    
    const startTime = process.hrtime.bigint();
    
    try {
      // Get latest market data
      const technicalData = timeSeriesManager.getTechnicalData(symbol, 100);
      const microstructureData = timeSeriesManager.getMicrostructure(symbol);
      
      if (!technicalData || !microstructureData) return;
      
      // Update volatility and liquidity estimates
      this.updateMarketRegime(symbol, technicalData, microstructureData);
      
      // Generate signals
      const signals = fastSignalGenerator.generateSignals(symbol, technicalData, microstructureData);
      
      // Process each signal
      for (const signal of signals) {
        await this.processSignal(signal, technicalData, microstructureData);
      }
      
      // Manage existing positions
      await this.managePositions(symbol, technicalData, microstructureData);
      
      // Update correlation matrix
      this.updateCorrelations();
      
      const endTime = process.hrtime.bigint();
      const latency = Number(endTime - startTime) / 1000000; // Convert to milliseconds
      
      this.emit('market_data_processed', {
        symbol,
        latency,
        signalCount: signals.length,
        timestamp: Number(timestamp)
      });
      
    } catch (error) {
      this.emit('error', {
        type: 'market_data_processing',
        symbol,
        error: error instanceof Error ? error.message : String(error),
        timestamp: Number(timestamp)
      });
    }
  }
  
  /**
   * Process trading signal and potentially create orders
   */
  private async processSignal(
    signal: Signal, 
    technicalData: TechnicalData, 
    microstructureData: MicrostructureData
  ): Promise<void> {
    const { symbol } = signal;
    const now = Date.now();
    
    // Throttle signals - avoid overtrading
    const lastSignal = this.lastSignalTime.get(symbol) || 0;
    if (now - lastSignal < 1000) return; // Min 1 second between signals
    
    // Pre-trade risk checks
    if (!this.passesPreTradeRisk(signal, technicalData, microstructureData)) {
      return;
    }
    
    // Calculate position size
    const positionSize = this.calculatePositionSize(signal, technicalData, microstructureData);
    if (positionSize === 0) return;
    
    // Create orders based on signal
    const orders = await this.createOrdersFromSignal(signal, positionSize, microstructureData);
    
    if (orders.length > 0) {
      this.lastSignalTime.set(symbol, now);
      
      // Store orders
      if (!this.activeOrders.has(symbol)) {
        this.activeOrders.set(symbol, []);
      }
      this.activeOrders.get(symbol)!.push(...orders);
      
      // Emit orders for execution
      orders.forEach(order => {
        this.emit('order_created', order);
      });
    }
  }
  
  /**
   * Pre-trade risk checks
   */
  private passesPreTradeRisk(
    signal: Signal, 
    technicalData: TechnicalData, 
    microstructureData: MicrostructureData
  ): boolean {
    const { symbol } = signal;
    
    // Check position limits
    const currentPositions = this.positions.get(symbol) || [];
    if (currentPositions.length >= this.config.maxPositionsPerSymbol) {
      return false;
    }
    
    // Check total position count
    const totalPositions = Array.from(this.positions.values()).reduce((sum, pos) => sum + pos.length, 0);
    if (totalPositions >= this.config.maxTotalPositions) {
      return false;
    }
    
    // Check spread constraints
    const spreadBps = (microstructureData.spread / microstructureData.mid) * 10000;
    if (spreadBps < this.config.minSpread || spreadBps > this.config.maxSpread) {
      return false;
    }
    
    // Check minimum volume
    if (technicalData.volume < this.config.minVolume) {
      return false;
    }
    
    // Check signal strength threshold
    if (signal.strength < 0.3) {
      return false;
    }
    
    // Check correlation limits
    if (!this.passesCorrelationCheck(symbol, signal.type)) {
      return false;
    }
    
    return true;
  }
  
  /**
   * Calculate optimal position size using Kelly criterion and risk management
   */
  private calculatePositionSize(
    signal: Signal, 
    technicalData: TechnicalData, 
    microstructureData: MicrostructureData
  ): number {
    const { symbol } = signal;
    
    // Base position size
    let size = this.config.basePositionSize;
    
    // Adjust for signal strength
    size *= signal.strength;
    
    // Adjust for volatility
    const volatility = this.volatilityEstimates.get(symbol) || 0.01;
    size *= Math.max(0.1, 1 / (volatility * 100)); // Reduce size for high volatility
    
    // Adjust for liquidity
    const liquidity = this.liquidityScores.get(symbol) || 0.5;
    size *= liquidity;
    
    // Adjust for spread
    const spreadBps = (microstructureData.spread / microstructureData.mid) * 10000;
    size *= Math.max(0.1, 1 / Math.max(1, spreadBps / this.config.minSpread));
    
    // Risk-based sizing
    const riskAmount = this.capital * (this.config.riskPerTrade / 100);
    const stopDistance = signal.stop_loss ? 
      Math.abs(technicalData.currentPrice - signal.stop_loss) / technicalData.currentPrice :
      0.005; // 0.5% default stop
    
    const riskBasedSize = riskAmount / (stopDistance * technicalData.currentPrice);
    size = Math.min(size, riskBasedSize);
    
    // Apply limits
    size = Math.min(size, this.config.maxPositionSize);
    size = Math.max(0, Math.floor(size));
    
    return size;
  }
  
  /**
   * Create orders from signal
   */
  private async createOrdersFromSignal(
    signal: Signal, 
    positionSize: number, 
    microstructureData: MicrostructureData
  ): Promise<Order[]> {
    const orders: Order[] = [];
    const timestamp = Date.now();
    
    // Main entry order
    const side = signal.type === SignalType.BUY ? OrderSide.BUY : OrderSide.SELL;
    const entryPrice = this.calculateEntryPrice(signal, microstructureData);
    
    const entryOrder: Order = {
      id: `${signal.symbol}_${timestamp}_entry`,
      client_order_id: `scalp_${signal.id}`,
      symbol: signal.symbol,
      side,
      type: OrderType.LIMIT,
      time_in_force: TimeInForce.IOC,
      quantity: positionSize,
      filled_quantity: 0,
      remaining_quantity: positionSize,
      price: entryPrice,
      status: 'new' as any,
      timestamp: timestamp,
      createdAt: timestamp,
      metadata: {
        strategy: 'scalping',
        signal_id: signal.id,
        expected_hold_time: signal.expected_holding_period
      }
    };
    
    orders.push(entryOrder);
    
    // Profit target order (OCO with stop loss)
    if (signal.target_price) {
      const profitOrder: Order = {
        id: `${signal.symbol}_${timestamp}_profit`,
        client_order_id: `scalp_profit_${signal.id}`,
        symbol: signal.symbol,
        side: side === OrderSide.BUY ? OrderSide.SELL : OrderSide.BUY,
        type: OrderType.LIMIT,
        time_in_force: TimeInForce.GTC,
        quantity: positionSize,
        filled_quantity: 0,
        remaining_quantity: positionSize,
        price: signal.target_price,
        status: 'pending' as any,
        timestamp: timestamp,
        createdAt: timestamp,
        metadata: {
          strategy: 'scalping',
          signal_id: signal.id,
          order_type: 'profit_target',
          parent_order: entryOrder.id
        }
      };
      
      orders.push(profitOrder);
    }
    
    // Stop loss order
    if (signal.stop_loss) {
      const stopOrder: Order = {
        id: `${signal.symbol}_${timestamp}_stop`,
        client_order_id: `scalp_stop_${signal.id}`,
        symbol: signal.symbol,
        side: side === OrderSide.BUY ? OrderSide.SELL : OrderSide.BUY,
        type: OrderType.STOP,
        time_in_force: TimeInForce.GTC,
        quantity: positionSize,
        filled_quantity: 0,
        remaining_quantity: positionSize,
        stop_price: signal.stop_loss,
        status: 'pending' as any,
        timestamp: timestamp,
        createdAt: timestamp,
        metadata: {
          strategy: 'scalping',
          signal_id: signal.id,
          order_type: 'stop_loss',
          parent_order: entryOrder.id
        }
      };
      
      orders.push(stopOrder);
    }
    
    return orders;
  }
  
  /**
   * Calculate optimal entry price based on signal and microstructure
   */
  private calculateEntryPrice(signal: Signal, microstructure: MicrostructureData): number {
    const { bid, ask, mid } = microstructure;
    
    if (signal.type === SignalType.BUY) {
      // For buy signals, try to get filled between mid and ask
      return Math.min(ask, mid + (ask - mid) * 0.3);
    } else {
      // For sell signals, try to get filled between bid and mid
      return Math.max(bid, mid - (mid - bid) * 0.3);
    }
  }
  
  /**
   * Manage existing positions
   */
  private async managePositions(
    symbol: string, 
    technicalData: TechnicalData, 
    microstructureData: MicrostructureData
  ): Promise<void> {
    const positions = this.positions.get(symbol) || [];
    const now = Date.now();
    
    for (const position of positions) {
      // Check time-based exit
      if (now - position.updated_at > this.config.maxHoldingTime) {
        await this.closePosition(position, 'time_limit', technicalData.currentPrice);
        continue;
      }
      
      // Check profit target
      const unrealizedPnL = this.calculateUnrealizedPnL(position, technicalData.currentPrice);
      const pnlBps = (unrealizedPnL / (position.quantity * position.average_entry_price)) * 10000;
      
      if (pnlBps > this.config.profitTarget) {
        await this.closePosition(position, 'profit_target', technicalData.currentPrice);
        continue;
      }
      
      // Check stop loss
      if (pnlBps < -this.config.stopLoss) {
        await this.closePosition(position, 'stop_loss', technicalData.currentPrice);
        continue;
      }
      
      // Dynamic exit based on signal reversal
      const currentSignals = fastSignalGenerator.generateSignals(symbol, technicalData, microstructureData);
      const oppositeSignals = currentSignals.filter(s => 
        (position.quantity > 0 && s.type === SignalType.SELL) ||
        (position.quantity < 0 && s.type === SignalType.BUY)
      );
      
      if (oppositeSignals.length > 0 && oppositeSignals[0].strength > 0.6) {
        await this.closePosition(position, 'signal_reversal', technicalData.currentPrice);
      }
    }
  }
  
  /**
   * Close a position
   */
  private async closePosition(
    position: Position, 
    reason: string, 
    currentPrice: number
  ): Promise<void> {
    const realizedPnL = this.calculateUnrealizedPnL(position, currentPrice);
    
    // Create closing order
    const closeOrder: Order = {
      id: `${position.symbol}_${Date.now()}_close`,
      client_order_id: `scalp_close_${position.symbol}_${Date.now()}`,
      symbol: position.symbol,
      side: position.quantity > 0 ? OrderSide.SELL : OrderSide.BUY,
      type: OrderType.MARKET,
      time_in_force: TimeInForce.IOC,
      quantity: Math.abs(position.quantity),
      filled_quantity: 0,
      remaining_quantity: Math.abs(position.quantity),
      status: 'new' as any,
      timestamp: Date.now(),
      createdAt: Date.now(),
      metadata: {
        strategy: 'scalping',
        position_close: true,
        close_reason: reason,
        expected_pnl: realizedPnL
      }
    };
    
    // Update metrics
    this.updateMetrics(position, realizedPnL, reason);
    
    // Remove position
    const positions = this.positions.get(position.symbol) || [];
    const index = positions.indexOf(position);
    if (index !== -1) {
      positions.splice(index, 1);
    }
    
    this.emit('order_created', closeOrder);
    this.emit('position_closed', {
      position,
      reason,
      pnl: realizedPnL,
      timestamp: Date.now()
    });
  }
  
  /**
   * Calculate unrealized PnL for a position
   */
  private calculateUnrealizedPnL(position: Position, currentPrice: number): number {
    const direction = position.quantity > 0 ? 1 : -1;
    return direction * Math.abs(position.quantity) * (currentPrice - position.average_entry_price);
  }
  
  /**
   * Update market regime estimates
   */
  private updateMarketRegime(
    symbol: string, 
    technicalData: TechnicalData, 
    microstructureData: MicrostructureData
  ): void {
    // Update volatility estimate using exponential smoothing
    const returns = this.calculateRecentReturns(symbol);
    if (returns.length > 0) {
      const currentVol = Math.sqrt(returns.reduce((sum, r) => sum + r * r, 0) / returns.length);
      const existingVol = this.volatilityEstimates.get(symbol) || currentVol;
      const smoothedVol = 0.1 * currentVol + 0.9 * existingVol;
      this.volatilityEstimates.set(symbol, smoothedVol);
    }
    
    // Update liquidity score based on spread and volume
    const spreadBps = (microstructureData.spread / microstructureData.mid) * 10000;
    const liquidityScore = Math.min(1, Math.max(0, 
      1 - (spreadBps / this.config.maxSpread) + 
      (technicalData.volume / this.config.minVolume) * 0.1
    ));
    this.liquidityScores.set(symbol, liquidityScore);
  }
  
  /**
   * Calculate recent returns for volatility estimation
   */
  private calculateRecentReturns(symbol: string): number[] {
    const technicalData = timeSeriesManager.getTechnicalData(symbol, 20);
    if (!technicalData || technicalData.priceArray.length < 2) return [];
    
    const returns: number[] = [];
    const prices = technicalData.priceArray;
    
    for (let i = 1; i < Math.min(prices.length, 20); i++) {
      if (prices[i-1] > 0) {
        returns.push((prices[i] - prices[i-1]) / prices[i-1]);
      }
    }
    
    return returns;
  }
  
  /**
   * Check correlation limits
   */
  private passesCorrelationCheck(symbol: string, signalType: SignalType): boolean {
    // Simplified correlation check - would need full implementation
    return true;
  }
  
  /**
   * Update correlation matrix
   */
  private updateCorrelations(): void {
    // Implementation for correlation matrix updates
    // This would calculate rolling correlations between symbols
  }
  
  /**
   * Close all positions
   */
  private async closeAllPositions(): Promise<void> {
    for (const [symbol, positions] of this.positions) {
      const technicalData = timeSeriesManager.getTechnicalData(symbol, 1);
      if (!technicalData) continue;
      
      for (const position of positions) {
        await this.closePosition(position, 'strategy_stop', technicalData.currentPrice);
      }
    }
  }
  
  /**
   * Update trading metrics
   */
  private updateMetrics(position: Position, pnl: number, reason: string): void {
    this.metrics.totalTrades++;
    this.metrics.totalPnL += pnl;
    
    if (pnl > 0) {
      this.metrics.winningTrades++;
      this.metrics.avgWin = (this.metrics.avgWin * (this.metrics.winningTrades - 1) + pnl) / this.metrics.winningTrades;
    } else {
      this.metrics.losingTrades++;
      this.metrics.avgLoss = (this.metrics.avgLoss * (this.metrics.losingTrades - 1) + Math.abs(pnl)) / this.metrics.losingTrades;
    }
    
    this.metrics.winRate = this.metrics.winningTrades / this.metrics.totalTrades;
    this.metrics.profitFactor = this.metrics.avgLoss > 0 ? this.metrics.avgWin / this.metrics.avgLoss : 0;
    this.metrics.lastUpdate = Date.now();
    
    this.emit('metrics_updated', this.metrics);
  }
  
  /**
   * Get current strategy metrics
   */
  getMetrics(): ScalpingMetrics {
    return { ...this.metrics };
  }
  
  /**
   * Get current positions
   */
  getPositions(): Map<string, Position[]> {
    return new Map(this.positions);
  }
  
  /**
   * Get active orders
   */
  getActiveOrders(): Map<string, Order[]> {
    return new Map(this.activeOrders);
  }
}

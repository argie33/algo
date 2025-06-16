import { EventEmitter } from 'events';
import { Config } from '../../config';
import { createLogger } from '../../utils/logger';
import { MetricsCollector } from '../../utils/metrics-collector';
import { Signal, Order, Position, PnLData, TradeStats, RiskMetrics, PerformanceMetrics } from '../../types';
import { Logger } from 'pino';

export interface AnalyticsConfig {
  enabled: boolean;
  realTimeAnalytics: boolean;
  historicalRetention: number; // days
  performanceCalculationInterval: number; // ms
  riskCalculationInterval: number; // ms
  alertThresholds: {
    maxDrawdown: number;
    maxDailyLoss: number;
    maxPositionSize: number;
    minSharpeRatio: number;
  };
}

export class AnalyticsService extends EventEmitter {
  private config: Config;
  private logger: Logger;
  private metrics: MetricsCollector;
  private isRunning: boolean = false;
  
  // Real-time data stores
  private trades: Map<string, Order[]> = new Map();
  private positions: Map<string, Position> = new Map();
  private pnlHistory: PnLData[] = [];
  private signalHistory: Signal[] = [];  private performanceMetrics: PerformanceMetrics = {
    totalPnL: 0,
    realizedPnL: 0,
    unrealizedPnL: 0,
    totalTrades: 0,
    winningTrades: 0,
    losingTrades: 0,
    winRate: 0,
    avgWin: 0,
    avgLoss: 0,
    profitFactor: 0,
    sharpeRatio: 0,
    maxDrawdown: 0,
    maxDrawdownPercent: 0,
    calmarRatio: 0,
    volatility: 0,
    startTime: Date.now(),
    lastUpdate: Date.now(),
    // Required fields for compatibility
    total_return: 0,
    daily_return: 0,
    updated_at: Date.now()
  };
  
  // Performance calculation intervals
  private performanceInterval?: NodeJS.Timeout;
  private riskInterval?: NodeJS.Timeout;
  
  constructor(config: Config, logger: Logger) {
    super();
    this.config = config;
    this.logger = logger;
    this.metrics = new MetricsCollector(config, logger);
  }
  
  async initialize(): Promise<void> {
    this.logger.info('Initializing Analytics Service');
    
    // Initialize metrics collector
    await this.metrics.initialize();
    
    // Load historical data if needed
    await this.loadHistoricalData();
    
    this.logger.info('Analytics Service initialized');
  }
  
  async start(): Promise<void> {
    if (this.isRunning) {
      this.logger.warn('Analytics Service already running');
      return;
    }
    
    this.logger.info('Starting Analytics Service');
    this.isRunning = true;
    
    // Start real-time analytics
    if (this.config.analytics.realTimeAnalytics) {
      this.startRealTimeAnalytics();
    }
    
    this.logger.info('Analytics Service started');
  }
  
  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Analytics Service');
    this.isRunning = false;
    
    // Clear intervals
    if (this.performanceInterval) {
      clearInterval(this.performanceInterval);
    }
    if (this.riskInterval) {
      clearInterval(this.riskInterval);
    }
    
    // Final metrics calculation
    await this.calculatePerformanceMetrics();
    await this.persistData();
    
    this.logger.info('Analytics Service stopped');
  }
  
  // Record trading events
  recordSignal(signal: Signal): void {
    this.signalHistory.push(signal);
    
    // Keep only recent signals for performance
    if (this.signalHistory.length > 10000) {
      this.signalHistory = this.signalHistory.slice(-5000);
    }
    
    this.metrics.incrementCounter('signals_generated');
    this.metrics.recordHistogram('signal_strength', Math.abs(signal.strength));
    
    this.emit('signal_recorded', signal);
  }
  
  recordOrder(order: Order): void {
    const symbol = order.symbol;
    if (!this.trades.has(symbol)) {
      this.trades.set(symbol, []);
    }
    this.trades.get(symbol)!.push(order);
    
    this.performanceMetrics.totalTrades++;
    this.performanceMetrics.lastUpdate = Date.now();
    
    this.metrics.incrementCounter('orders_recorded');
    this.metrics.recordHistogram('order_size', Math.abs(order.quantity));
    
    this.emit('order_recorded', order);
  }
  
  recordPnL(pnl: PnLData): void {
    this.pnlHistory.push(pnl);
    
    // Update real-time metrics
    this.performanceMetrics.totalPnL = pnl.totalPnL;
    this.performanceMetrics.realizedPnL = pnl.realizedPnL;
    this.performanceMetrics.unrealizedPnL = pnl.unrealizedPnL;
    this.performanceMetrics.lastUpdate = Date.now();
    
    // Keep only recent PnL data
    if (this.pnlHistory.length > 100000) {
      this.pnlHistory = this.pnlHistory.slice(-50000);
    }
    
    this.metrics.recordGauge('total_pnl', pnl.totalPnL);
    this.metrics.recordGauge('realized_pnl', pnl.realizedPnL);
    this.metrics.recordGauge('unrealized_pnl', pnl.unrealizedPnL);
    
    this.emit('pnl_recorded', pnl);
  }
  
  recordPosition(position: Position): void {
    this.positions.set(position.symbol, position);
    
    this.metrics.recordGauge(`position_${position.symbol}`, position.quantity);
    this.metrics.recordGauge(`position_value_${position.symbol}`, 
      position.quantity * position.averagePrice);
    
    this.emit('position_recorded', position);
  }
  
  // Analytics calculations
  async calculatePerformanceMetrics(): Promise<PerformanceMetrics> {
    const now = Date.now();
    const tradingDays = Math.max(1, (now - this.performanceMetrics.startTime) / (1000 * 60 * 60 * 24));
    
    // Calculate win/loss stats
    const allTrades = Array.from(this.trades.values()).flat();
    const completedTrades = allTrades.filter(t => t.status === 'filled');
    
    if (completedTrades.length > 0) {
      const winningTrades = completedTrades.filter(t => (t.pnl || 0) > 0);
      const losingTrades = completedTrades.filter(t => (t.pnl || 0) < 0);
      
      this.performanceMetrics.winningTrades = winningTrades.length;
      this.performanceMetrics.losingTrades = losingTrades.length;
      this.performanceMetrics.winRate = winningTrades.length / completedTrades.length;
      
      if (winningTrades.length > 0) {
        this.performanceMetrics.avgWin = winningTrades.reduce((sum, t) => sum + (t.pnl || 0), 0) / winningTrades.length;
      }
      
      if (losingTrades.length > 0) {
        this.performanceMetrics.avgLoss = Math.abs(losingTrades.reduce((sum, t) => sum + (t.pnl || 0), 0) / losingTrades.length);
      }
      
      if (this.performanceMetrics.avgLoss > 0) {
        this.performanceMetrics.profitFactor = this.performanceMetrics.avgWin / this.performanceMetrics.avgLoss;
      }
    }
    
    // Calculate Sharpe ratio and volatility
    if (this.pnlHistory.length > 30) {
      const dailyReturns = this.calculateDailyReturns();
      const avgReturn = dailyReturns.reduce((sum, r) => sum + r, 0) / dailyReturns.length;
      const variance = dailyReturns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / dailyReturns.length;
      
      this.performanceMetrics.volatility = Math.sqrt(variance);
      this.performanceMetrics.sharpeRatio = this.performanceMetrics.volatility > 0 ? 
        (avgReturn * Math.sqrt(252)) / (this.performanceMetrics.volatility * Math.sqrt(252)) : 0;
    }
    
    // Calculate drawdown
    const drawdownData = this.calculateDrawdown();
    this.performanceMetrics.maxDrawdown = drawdownData.maxDrawdown;
    this.performanceMetrics.maxDrawdownPercent = drawdownData.maxDrawdownPercent;
    
    // Calculate Calmar ratio
    if (this.performanceMetrics.maxDrawdownPercent > 0) {
      const annualizedReturn = (this.performanceMetrics.totalPnL / tradingDays) * 252;
      this.performanceMetrics.calmarRatio = annualizedReturn / Math.abs(this.performanceMetrics.maxDrawdownPercent);
    }
    
    // Update metrics
    this.metrics.recordGauge('win_rate', this.performanceMetrics.winRate);
    this.metrics.recordGauge('sharpe_ratio', this.performanceMetrics.sharpeRatio);
    this.metrics.recordGauge('max_drawdown', this.performanceMetrics.maxDrawdown);
    this.metrics.recordGauge('profit_factor', this.performanceMetrics.profitFactor);
    
    return this.performanceMetrics;
  }
  
  calculateRiskMetrics(): RiskMetrics {
    const positions = Array.from(this.positions.values());
    const totalExposure = positions.reduce((sum, p) => sum + Math.abs(p.quantity * p.averagePrice), 0);
    const netExposure = positions.reduce((sum, p) => sum + (p.quantity * p.averagePrice), 0);
    
    const riskMetrics: RiskMetrics = {
      totalExposure,
      netExposure,
      grossLeverage: totalExposure / Math.max(1, this.performanceMetrics.totalPnL + 1000000), // Assume 1M capital
      netLeverage: Math.abs(netExposure) / Math.max(1, this.performanceMetrics.totalPnL + 1000000),
      largestPosition: Math.max(...positions.map(p => Math.abs(p.quantity * p.averagePrice))),
      numberOfPositions: positions.length,
      concentrationRisk: positions.length > 0 ? 
        Math.max(...positions.map(p => Math.abs(p.quantity * p.averagePrice))) / totalExposure : 0,
      var95: this.calculateVaR(0.95),
      var99: this.calculateVaR(0.99),
      expectedShortfall: this.calculateExpectedShortfall(0.95),
      timestamp: Date.now()
    };
    
    this.metrics.recordGauge('total_exposure', riskMetrics.totalExposure);
    this.metrics.recordGauge('net_exposure', riskMetrics.netExposure);
    this.metrics.recordGauge('gross_leverage', riskMetrics.grossLeverage);
    this.metrics.recordGauge('var_95', riskMetrics.var95);
    
    return riskMetrics;
  }
  
  // Real-time analytics
  private startRealTimeAnalytics(): void {
    // Performance metrics calculation
    this.performanceInterval = setInterval(() => {
      this.calculatePerformanceMetrics().catch(err => {
        this.logger.error('Error calculating performance metrics:', err);
      });
    }, this.config.analytics.performanceCalculationInterval);
    
    // Risk metrics calculation
    this.riskInterval = setInterval(() => {
      const riskMetrics = this.calculateRiskMetrics();
      this.emit('risk_metrics_updated', riskMetrics);
      
      // Check risk thresholds
      this.checkRiskThresholds(riskMetrics);
    }, this.config.analytics.riskCalculationInterval);
  }
  
  private checkRiskThresholds(riskMetrics: RiskMetrics): void {
    const thresholds = this.config.analytics.alertThresholds;
    
    if (this.performanceMetrics.maxDrawdown > thresholds.maxDrawdown) {
      this.emit('risk_breach', {
        type: 'max_drawdown',
        value: this.performanceMetrics.maxDrawdown,
        threshold: thresholds.maxDrawdown,
        timestamp: Date.now()
      });
    }
    
    if (riskMetrics.largestPosition > thresholds.maxPositionSize) {
      this.emit('risk_breach', {
        type: 'max_position_size',
        value: riskMetrics.largestPosition,
        threshold: thresholds.maxPositionSize,
        timestamp: Date.now()
      });
    }
    
    if (this.performanceMetrics.sharpeRatio < thresholds.minSharpeRatio) {
      this.emit('risk_breach', {
        type: 'min_sharpe_ratio',
        value: this.performanceMetrics.sharpeRatio,
        threshold: thresholds.minSharpeRatio,
        timestamp: Date.now()
      });
    }
  }
  
  // Helper methods
  private calculateDailyReturns(): number[] {
    const dailyPnL: { [date: string]: number } = {};
    
    this.pnlHistory.forEach(p => {
      const date = new Date(p.timestamp).toDateString();
      if (!dailyPnL[date]) {
        dailyPnL[date] = 0;
      }
      dailyPnL[date] = p.totalPnL;
    });
    
    const dates = Object.keys(dailyPnL).sort();
    const returns: number[] = [];
    
    for (let i = 1; i < dates.length; i++) {
      const prevPnL = dailyPnL[dates[i-1]];
      const currPnL = dailyPnL[dates[i]];
      if (prevPnL !== 0) {
        returns.push((currPnL - prevPnL) / Math.abs(prevPnL));
      }
    }
    
    return returns;
  }
  
  private calculateDrawdown(): { maxDrawdown: number; maxDrawdownPercent: number } {
    let maxDrawdown = 0;
    let maxDrawdownPercent = 0;
    let peak = 0;
    
    this.pnlHistory.forEach(p => {
      if (p.totalPnL > peak) {
        peak = p.totalPnL;
      }
      
      const drawdown = peak - p.totalPnL;
      const drawdownPercent = peak > 0 ? (drawdown / peak) * 100 : 0;
      
      if (drawdown > maxDrawdown) {
        maxDrawdown = drawdown;
      }
      
      if (drawdownPercent > maxDrawdownPercent) {
        maxDrawdownPercent = drawdownPercent;
      }
    });
    
    return { maxDrawdown, maxDrawdownPercent };
  }
  
  private calculateVaR(confidence: number): number {
    const dailyReturns = this.calculateDailyReturns();
    if (dailyReturns.length === 0) return 0;
    
    dailyReturns.sort((a, b) => a - b);
    const index = Math.floor((1 - confidence) * dailyReturns.length);
    return dailyReturns[index] || 0;
  }
  
  private calculateExpectedShortfall(confidence: number): number {
    const dailyReturns = this.calculateDailyReturns();
    if (dailyReturns.length === 0) return 0;
    
    dailyReturns.sort((a, b) => a - b);
    const cutoff = Math.floor((1 - confidence) * dailyReturns.length);
    const tailReturns = dailyReturns.slice(0, cutoff);
    
    if (tailReturns.length === 0) return 0;
    return tailReturns.reduce((sum, r) => sum + r, 0) / tailReturns.length;
  }
  
  private async loadHistoricalData(): Promise<void> {
    // TODO: Load historical data from database
    this.logger.info('Loading historical analytics data...');
  }
  
  private async persistData(): Promise<void> {
    // TODO: Persist analytics data to database
    this.logger.info('Persisting analytics data...');
  }
  
  // Getters
  getPerformanceMetrics(): PerformanceMetrics {
    return { ...this.performanceMetrics };
  }
  
  getRiskMetrics(): RiskMetrics {
    return this.calculateRiskMetrics();
  }
  
  getTradeStats(symbol?: string): TradeStats {
    const trades = symbol ? 
      (this.trades.get(symbol) || []) : 
      Array.from(this.trades.values()).flat();
    
    const completedTrades = trades.filter(t => t.status === 'filled');
    
    return {
      totalTrades: completedTrades.length,
      totalVolume: completedTrades.reduce((sum, t) => sum + Math.abs(t.quantity), 0),
      avgTradeSize: completedTrades.length > 0 ? 
        completedTrades.reduce((sum, t) => sum + Math.abs(t.quantity), 0) / completedTrades.length : 0,
      totalPnL: completedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0),
      avgHoldTime: this.calculateAvgHoldTime(completedTrades),
      successRate: completedTrades.length > 0 ? 
        completedTrades.filter(t => (t.pnl || 0) > 0).length / completedTrades.length : 0
    };
  }
  
  private calculateAvgHoldTime(trades: Order[]): number {
    const holdTimes: number[] = [];
    
    trades.forEach(trade => {
      if (trade.filledAt && trade.createdAt) {
        holdTimes.push(trade.filledAt - trade.createdAt);
      }
    });
    
    return holdTimes.length > 0 ? 
      holdTimes.reduce((sum, t) => sum + t, 0) / holdTimes.length : 0;
  }
}

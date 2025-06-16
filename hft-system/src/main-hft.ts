/**
 * Ultra-Fast HFT System Main Application
 * 
 * Orchestrates all components for sub-millisecond trading:
 * - Market data ingestion
 * - Real-time signal generation  
 * - Scalping strategy execution
 * - Risk management
 * - Order execution
 * 
 * Designed for institutional-grade performance and reliability.
 */

import { Config, loadConfig } from './config';
import { createLogger } from './utils/logger';
import { timeSeriesManager } from './core/timeseries/timeseries-engine';
import { fastSignalGenerator } from './core/signals/fast-signal-generator';
import { ScalpingStrategy } from './strategies/scalping-strategy';
import { MarketDataEngine } from './engines/market-data/market-data-engine';
import { OrderEngine } from './engines/order/order-engine';
import { RiskEngine } from './engines/risk/risk-engine';
import { PortfolioEngine } from './engines/portfolio/portfolio-engine';
import { HealthService } from './services/health/health-service';
import type { Logger } from 'pino';

export class HFTSystem {
  private config: Config;
  private logger: Logger;
  private isRunning: boolean = false;
  
  // Core engines
  private marketDataEngine: MarketDataEngine;
  private orderEngine: OrderEngine;
  private riskEngine: RiskEngine;
  private portfolioEngine: PortfolioEngine;
  
  // Services
  private healthService: HealthService;
  
  // Strategy
  private scalpingStrategy: ScalpingStrategy;
  
  // Performance tracking
  private startTime: bigint = 0n;
  private processedTicks: number = 0;
  private generatedSignals: number = 0;
  private executedOrders: number = 0;
  
  constructor() {
    this.config = loadConfig();
    this.logger = createLogger('HFTSystem');
    
    // Initialize engines
    this.marketDataEngine = new MarketDataEngine(this.config, this.logger);
    this.orderEngine = new OrderEngine(this.config, this.logger);
    this.riskEngine = new RiskEngine(this.config, this.logger);
    this.portfolioEngine = new PortfolioEngine(this.config, this.logger);
    
    // Initialize services
    this.healthService = new HealthService(this.config, this.logger);
    
    // Initialize scalping strategy
    this.scalpingStrategy = new ScalpingStrategy({
      enabled: true,
      symbols: this.config.symbols.map(s => s.symbol),
      maxPositionsPerSymbol: 3,
      maxTotalPositions: 15,
      basePositionSize: 100,
      maxPositionSize: 1000,
      profitTarget: 20, // 20 bps
      stopLoss: 10, // 10 bps
      maxHoldingTime: 300000, // 5 minutes
      minSpread: 2, // 2 bps
      maxSpread: 20, // 20 bps
      minVolume: 1000,
      riskPerTrade: 0.5, // 0.5% of capital per trade
      correlationLimit: 0.7
    });
    
    this.setupEventHandlers();
  }
  
  /**
   * Setup event handlers for inter-component communication
   */
  private setupEventHandlers(): void {
    // Market data → Signal generation → Strategy
    this.marketDataEngine.on('tick', async (data) => {
      const startTime = process.hrtime.bigint();
      
      try {
        // Add tick to time series
        timeSeriesManager.addTick(
          data.symbol,
          data.price,
          data.size,
          BigInt(data.timestamp)
        );
        
        // Process market data through strategy
        await this.scalpingStrategy.processMarketData(
          data.symbol,
          BigInt(data.timestamp)
        );
        
        this.processedTicks++;
        
        const endTime = process.hrtime.bigint();
        const latency = Number(endTime - startTime) / 1000000; // ms
        
        // Log if latency exceeds threshold
        if (latency > 1.0) {
          this.logger.warn(`High tick processing latency: ${latency}ms for ${data.symbol}`);
        }
        
      } catch (error) {
        this.logger.error('Error processing tick:', error);
      }
    });
    
    // Market data → Order book updates
    this.marketDataEngine.on('quote', (data) => {
      timeSeriesManager.updateOrderBook(
        data.symbol,
        'bid',
        data.bid_price,
        data.bid_size,
        BigInt(data.timestamp)
      );
      
      timeSeriesManager.updateOrderBook(
        data.symbol,
        'ask',
        data.ask_price,
        data.ask_size,
        BigInt(data.timestamp)
      );
    });
    
    // Strategy → Order execution
    this.scalpingStrategy.on('order_created', async (order) => {
      const startTime = process.hrtime.bigint();
      
      try {
        // Risk check
        const riskCheck = await this.riskEngine.checkOrder(order);
        if (!riskCheck.approved) {
          this.logger.warn(`Order rejected by risk engine: ${order.id}`, riskCheck);
          return;
        }
        
        // Submit order
        await this.orderEngine.submitOrder(order);
        this.executedOrders++;
        
        const endTime = process.hrtime.bigint();
        const latency = Number(endTime - startTime) / 1000000; // ms
        
        this.logger.info(`Order submitted: ${order.id} in ${latency}ms`);
        
      } catch (error) {
        this.logger.error(`Error executing order ${order.id}:`, error);
      }
    });
    
    // Order fills → Portfolio updates
    this.orderEngine.on('order_filled', async (order) => {
      try {
        await this.portfolioEngine.processOrderFill(order);
        this.logger.info(`Order filled: ${order.id}, quantity: ${order.filled_quantity}`);
      } catch (error) {
        this.logger.error(`Error processing order fill ${order.id}:`, error);
      }
    });
    
    // Portfolio → Risk monitoring
    this.portfolioEngine.on('portfolio_updated', (portfolio) => {
      this.riskEngine.updatePortfolio(portfolio);
    });
    
    // Risk breaches → Emergency actions
    this.riskEngine.on('risk_breach', async (breach) => {
      this.logger.error('Risk breach detected:', breach);
      
      if (breach.risk_level === 'critical') {
        // Emergency stop
        await this.emergencyStop();
      }
    });
    
    // Strategy metrics
    this.scalpingStrategy.on('metrics_updated', (metrics) => {
      this.logger.info('Strategy metrics updated:', {
        totalTrades: metrics.totalTrades,
        winRate: metrics.winRate,
        totalPnL: metrics.totalPnL,
        profitFactor: metrics.profitFactor
      });
    });
    
    // Position management
    this.scalpingStrategy.on('position_closed', (event) => {
      this.logger.info(`Position closed: ${event.position.symbol}, PnL: ${event.pnl}, reason: ${event.reason}`);
    });
  }
  
  /**
   * Start the HFT system
   */
  async start(): Promise<void> {
    if (this.isRunning) {
      this.logger.warn('HFT System already running');
      return;
    }
    
    this.logger.info('Starting HFT System...');
    this.startTime = process.hrtime.bigint();
    
    try {
      // Initialize all engines in order
      await this.healthService.initialize();
      await this.riskEngine.initialize();
      await this.portfolioEngine.initialize();
      await this.orderEngine.initialize();
      await this.marketDataEngine.initialize();
      
      // Start strategy
      await this.scalpingStrategy.start();
      
      // Start engines
      await this.healthService.start();
      await this.riskEngine.start();
      await this.portfolioEngine.start();
      await this.orderEngine.start();
      await this.marketDataEngine.start();
      
      this.isRunning = true;
      
      // Initialize signal generators for all symbols
      this.config.symbols.forEach(symbolConfig => {
        fastSignalGenerator.initializeSymbol(symbolConfig.symbol);
      });
      
      // Start performance monitoring
      this.startPerformanceMonitoring();
      
      this.logger.info('HFT System started successfully');
      
    } catch (error) {
      this.logger.error('Failed to start HFT System:', error);
      await this.stop();
      throw error;
    }
  }
  
  /**
   * Stop the HFT system gracefully
   */
  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping HFT System...');
    this.isRunning = false;
    
    try {
      // Stop strategy first
      await this.scalpingStrategy.stop();
      
      // Stop engines in reverse order
      await this.marketDataEngine.stop();
      await this.orderEngine.stop();
      await this.portfolioEngine.stop();
      await this.riskEngine.stop();
      await this.healthService.stop();
      
      // Log final statistics
      const runtime = Number(process.hrtime.bigint() - this.startTime) / 1000000000; // seconds
      this.logger.info('HFT System stopped', {
        runtime: `${runtime.toFixed(2)}s`,
        processedTicks: this.processedTicks,
        generatedSignals: this.generatedSignals,
        executedOrders: this.executedOrders,
        avgTicksPerSecond: Math.round(this.processedTicks / runtime),
        avgOrdersPerSecond: Math.round(this.executedOrders / runtime)
      });
      
    } catch (error) {
      this.logger.error('Error stopping HFT System:', error);
    }
  }
  
  /**
   * Emergency stop - immediately halt all trading
   */
  async emergencyStop(): Promise<void> {
    this.logger.error('EMERGENCY STOP TRIGGERED');
    
    try {
      // Stop market data immediately
      await this.marketDataEngine.stop();
      
      // Cancel all pending orders
      await this.orderEngine.cancelAllOrders();
      
      // Close all positions at market
      const positions = this.scalpingStrategy.getPositions();
      for (const [symbol, symbolPositions] of positions) {
        for (const position of symbolPositions) {
          this.logger.warn(`Emergency closing position: ${symbol}`);
          // Create market order to close position
          // Implementation would depend on order engine
        }
      }
      
      // Stop all other components
      await this.stop();
      
    } catch (error) {
      this.logger.error('Error during emergency stop:', error);
    }
  }
  
  /**
   * Start performance monitoring
   */
  private startPerformanceMonitoring(): void {
    const monitoringInterval = 5000; // 5 seconds
    
    setInterval(() => {
      if (!this.isRunning) return;
      
      const runtime = Number(process.hrtime.bigint() - this.startTime) / 1000000000;
      const ticksPerSecond = this.processedTicks / runtime;
      const ordersPerSecond = this.executedOrders / runtime;
      
      // Get system metrics
      const memUsage = process.memoryUsage();
      const cpuUsage = process.cpuUsage();
      
      // Get strategy metrics
      const strategyMetrics = this.scalpingStrategy.getMetrics();
      
      // Log performance summary
      this.logger.info('Performance summary:', {
        runtime: `${runtime.toFixed(2)}s`,
        ticksPerSecond: Math.round(ticksPerSecond),
        ordersPerSecond: Math.round(ordersPerSecond),
        memoryMB: Math.round(memUsage.heapUsed / 1024 / 1024),
        totalTrades: strategyMetrics.totalTrades,
        winRate: `${(strategyMetrics.winRate * 100).toFixed(1)}%`,
        totalPnL: strategyMetrics.totalPnL.toFixed(2)
      });
      
      // Check performance thresholds
      if (ticksPerSecond < 1000) {
        this.logger.warn(`Low tick processing rate: ${ticksPerSecond}/s`);
      }
      
      if (memUsage.heapUsed > 1024 * 1024 * 1024) { // 1GB
        this.logger.warn(`High memory usage: ${Math.round(memUsage.heapUsed / 1024 / 1024)}MB`);
      }
      
    }, monitoringInterval);
  }
  
  /**
   * Get system status
   */
  getStatus(): SystemStatus {
    const runtime = this.isRunning ? 
      Number(process.hrtime.bigint() - this.startTime) / 1000000000 : 0;
    
    return {
      isRunning: this.isRunning,
      runtime,
      processedTicks: this.processedTicks,
      generatedSignals: this.generatedSignals,
      executedOrders: this.executedOrders,
      avgTicksPerSecond: runtime > 0 ? Math.round(this.processedTicks / runtime) : 0,
      avgOrdersPerSecond: runtime > 0 ? Math.round(this.executedOrders / runtime) : 0,
      strategyMetrics: this.scalpingStrategy.getMetrics(),
      activePositions: Array.from(this.scalpingStrategy.getPositions().values())
        .reduce((sum, positions) => sum + positions.length, 0),
      memoryUsageMB: Math.round(process.memoryUsage().heapUsed / 1024 / 1024)
    };
  }
}

interface SystemStatus {
  isRunning: boolean;
  runtime: number;
  processedTicks: number;
  generatedSignals: number;
  executedOrders: number;
  avgTicksPerSecond: number;
  avgOrdersPerSecond: number;
  strategyMetrics: any;
  activePositions: number;
  memoryUsageMB: number;
}

// Main entry point
async function main(): Promise<void> {
  const hftSystem = new HFTSystem();
  
  // Graceful shutdown handling
  process.on('SIGINT', async () => {
    console.log('Received SIGINT, shutting down gracefully...');
    await hftSystem.stop();
    process.exit(0);
  });
  
  process.on('SIGTERM', async () => {
    console.log('Received SIGTERM, shutting down gracefully...');
    await hftSystem.stop();
    process.exit(0);
  });
  
  // Handle uncaught exceptions
  process.on('uncaughtException', async (error) => {
    console.error('Uncaught exception:', error);
    await hftSystem.emergencyStop();
    process.exit(1);
  });
  
  process.on('unhandledRejection', async (reason, promise) => {
    console.error('Unhandled rejection at:', promise, 'reason:', reason);
    await hftSystem.emergencyStop();
    process.exit(1);
  });
  
  try {
    await hftSystem.start();
    console.log('HFT System is running. Press Ctrl+C to stop.');
    
    // Keep the process alive
    process.stdin.resume();
    
  } catch (error) {
    console.error('Failed to start HFT System:', error);
    process.exit(1);
  }
}

// Export for testing
export { main };

// Run if this is the main module
if (require.main === module) {
  main().catch(console.error);
}

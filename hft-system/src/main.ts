import { Logger } from 'pino';
import { createLogger } from './utils/logger';
import { Config } from './config';
import { MarketDataEngine } from './engines/market-data/market-data-engine';
import { SignalEngine } from './engines/signal/signal-engine';
import { RiskEngine } from './engines/risk/risk-engine';
import { OrderEngine } from './engines/order/order-engine';
import { PortfolioEngine } from './engines/portfolio/portfolio-engine';
import { ComplianceService } from './services/compliance/compliance-service';
import { AnalyticsService } from './services/analytics/analytics-service';
import { NotificationService } from './services/notification/notification-service';
import { DataIntegrationService } from './services/data-integration/data-integration-service';
import { HealthService } from './services/health/health-service';
import { MetricsCollector } from './utils/metrics-collector';
import { gracefulShutdown } from './utils/graceful-shutdown';

/**
 * Main HFT System Class
 * Orchestrates all engines and services for ultra-low latency trading
 */
export class HFTSystem {
  private logger: Logger;
  private config: Config;
  private metricsCollector: MetricsCollector;
  
  // Core engines
  private marketDataEngine: MarketDataEngine;
  private signalEngine: SignalEngine;
  private riskEngine: RiskEngine;
  private orderEngine: OrderEngine;
  private portfolioEngine: PortfolioEngine;
  
  // Services
  private complianceService: ComplianceService;
  private analyticsService: AnalyticsService;
  private notificationService: NotificationService;
  private dataIntegrationService: DataIntegrationService;
  private healthService: HealthService;
  
  private isRunning: boolean = false;
  private shutdownPromise: Promise<void> | null = null;

  constructor() {
    this.logger = createLogger('HFTSystem');
    this.config = new Config();
    this.metricsCollector = new MetricsCollector();
    
    // Initialize engines
    this.marketDataEngine = new MarketDataEngine(this.config, this.logger);
    this.signalEngine = new SignalEngine(this.config, this.logger);
    this.riskEngine = new RiskEngine(this.config, this.logger);
    this.orderEngine = new OrderEngine(this.config, this.logger);
    this.portfolioEngine = new PortfolioEngine(this.config, this.logger);
    
    // Initialize services
    this.complianceService = new ComplianceService(this.config, this.logger);
    this.analyticsService = new AnalyticsService(this.config, this.logger);
    this.notificationService = new NotificationService(this.config, this.logger);
    this.dataIntegrationService = new DataIntegrationService(this.config, this.logger);
    this.healthService = new HealthService(this.config, this.logger);
  }

  /**
   * Initialize and start the HFT system
   */
  async start(): Promise<void> {
    try {
      this.logger.info('Starting HFT System...');
      
      // Start metrics collection
      await this.metricsCollector.start();
      
      // Initialize data integration service first
      await this.dataIntegrationService.initialize();
      
      // Initialize services
      await this.complianceService.initialize();
      await this.analyticsService.initialize();
      await this.notificationService.initialize();
      await this.healthService.initialize();
      
      // Initialize engines in dependency order
      await this.portfolioEngine.initialize();
      await this.riskEngine.initialize();
      await this.orderEngine.initialize();
      await this.signalEngine.initialize();
      await this.marketDataEngine.initialize();
      
      // Wire up the data flow
      this.setupDataFlow();
      
      // Start engines
      await this.marketDataEngine.start();
      await this.signalEngine.start();
      await this.riskEngine.start();
      await this.orderEngine.start();
      await this.portfolioEngine.start();
      
      // Start services
      await this.complianceService.start();
      await this.analyticsService.start();
      await this.healthService.start();
      
      this.isRunning = true;
      
      this.logger.info('HFT System started successfully');
      
      // Setup graceful shutdown
      this.setupGracefulShutdown();
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to start HFT System');
      await this.shutdown();
      throw error;
    }
  }

  /**
   * Setup data flow between engines
   */
  private setupDataFlow(): void {
    // Market Data → Signal Engine
    this.marketDataEngine.on('tick', (tick) => {
      this.signalEngine.processTick(tick);
    });
    
    this.marketDataEngine.on('quote', (quote) => {
      this.signalEngine.processQuote(quote);
    });
    
    this.marketDataEngine.on('trade', (trade) => {
      this.signalEngine.processTrade(trade);
      this.portfolioEngine.processTrade(trade);
    });
    
    // Signal Engine → Risk Engine → Order Engine
    this.signalEngine.on('signal', async (signal) => {
      const riskCheck = await this.riskEngine.validateSignal(signal);
      if (riskCheck.approved) {
        await this.orderEngine.processSignal(signal);
      } else {
        this.logger.warn({ signal, riskCheck }, 'Signal rejected by risk engine');
      }
    });
    
    // Order Engine → Portfolio Engine
    this.orderEngine.on('orderFilled', (fill) => {
      this.portfolioEngine.processFill(fill);
    });
    
    // Portfolio Engine → Risk Engine
    this.portfolioEngine.on('positionUpdate', (position) => {
      this.riskEngine.updatePosition(position);
    });
    
    // Risk Engine → Notification Service
    this.riskEngine.on('riskBreach', (breach) => {
      this.notificationService.sendAlert(breach);
    });
    
    // Analytics collection
    this.signalEngine.on('signal', (signal) => {
      this.analyticsService.recordSignal(signal);
    });
    
    this.orderEngine.on('orderPlaced', (order) => {
      this.analyticsService.recordOrder(order);
    });
    
    this.portfolioEngine.on('pnlUpdate', (pnl) => {
      this.analyticsService.recordPnL(pnl);
    });
  }

  /**
   * Setup graceful shutdown handlers
   */
  private setupGracefulShutdown(): void {
    const signals = ['SIGTERM', 'SIGINT', 'SIGQUIT'];
    
    signals.forEach(signal => {
      process.on(signal, async () => {
        this.logger.info({ signal }, 'Received shutdown signal');
        await this.shutdown();
        process.exit(0);
      });
    });
    
    process.on('uncaughtException', async (error) => {
      this.logger.fatal({ error }, 'Uncaught exception');
      await this.shutdown();
      process.exit(1);
    });
    
    process.on('unhandledRejection', async (reason, promise) => {
      this.logger.fatal({ reason, promise }, 'Unhandled rejection');
      await this.shutdown();
      process.exit(1);
    });
  }

  /**
   * Gracefully shutdown the HFT system
   */
  async shutdown(): Promise<void> {
    if (this.shutdownPromise) {
      return this.shutdownPromise;
    }
    
    this.shutdownPromise = this._shutdown();
    return this.shutdownPromise;
  }

  private async _shutdown(): Promise<void> {
    if (!this.isRunning) {
      return;
    }
    
    this.logger.info('Shutting down HFT System...');
    this.isRunning = false;
    
    try {
      // Stop engines in reverse order
      await this.marketDataEngine.stop();
      await this.signalEngine.stop();
      await this.orderEngine.stop();
      await this.riskEngine.stop();
      await this.portfolioEngine.stop();
      
      // Stop services
      await this.complianceService.stop();
      await this.analyticsService.stop();
      await this.healthService.stop();
      await this.notificationService.stop();
      await this.dataIntegrationService.stop();
      
      // Stop metrics collection
      await this.metricsCollector.stop();
      
      this.logger.info('HFT System shutdown complete');
      
    } catch (error) {
      this.logger.error({ error }, 'Error during shutdown');
      throw error;
    }
  }

  /**
   * Get system health status
   */
  getHealth(): any {
    return this.healthService.getStatus();
  }

  /**
   * Get system metrics
   */
  getMetrics(): any {
    return this.metricsCollector.getMetrics();
  }
}

/**
 * Main application entry point
 */
async function main(): Promise<void> {
  const hftSystem = new HFTSystem();
  
  try {
    await hftSystem.start();
    
    // Keep the process running
    await new Promise(() => {});
    
  } catch (error) {
    console.error('Failed to start HFT System:', error);
    process.exit(1);
  }
}

// Start the application if this file is run directly
if (require.main === module) {
  main().catch(console.error);
}

export { main };

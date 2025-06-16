import { BaseEngine, Signal, RiskCheck, RiskLevel, Position, RiskMetrics, RiskViolationError } from '../../types';
import { Config } from '../../config';
import { Logger } from 'pino';

export interface RiskLimits {
  maxPositionSize: number;
  maxPortfolioValue: number;
  maxDailyLoss: number;
  maxDrawdown: number;
  concentrationLimit: number;
  leverageLimit: number;
  maxOrderSize: number;
  maxOrdersPerSecond: number;
  maxVaR: number;
}

export interface RiskBreach {
  type: string;
  severity: RiskLevel;
  symbol?: string;
  currentValue: number;
  limitValue: number;
  message: string;
  timestamp: number;
}

/**
 * Real-time risk management engine
 * Provides pre-trade and post-trade risk validation
 */
export class RiskEngine extends BaseEngine {
  private positions: Map<string, Position> = new Map();
  private dailyPnL: number = 0;
  private maxDrawdown: number = 0;
  private peakPortfolioValue: number = 0;
  private orderCounts: Map<string, number> = new Map();
  private riskMetrics: RiskMetrics;
  private riskLimits: RiskLimits;
  private circuitBreakerTriggered: boolean = false;

  constructor(config: Config, logger: Logger) {
    super('RiskEngine', config, logger);
    
    this.riskLimits = {
      maxPositionSize: config.riskLimits.maxPositionSize,
      maxPortfolioValue: config.riskLimits.maxPortfolioValue,
      maxDailyLoss: config.riskLimits.maxDailyLoss,
      maxDrawdown: config.riskLimits.maxDrawdown,
      concentrationLimit: config.riskLimits.concentrationLimit,
      leverageLimit: config.riskLimits.leverageLimit,
      maxOrderSize: config.riskLimits.maxOrderSize,
      maxOrdersPerSecond: 100,
      maxVaR: 50000 // $50k daily VaR limit
    };
    
    this.riskMetrics = {
      portfolio_value: 0,
      total_exposure: 0,
      net_exposure: 0,
      gross_exposure: 0,
      leverage: 0,
      var_1d: 0,
      var_5d: 0,
      max_drawdown: 0,
      sharpe_ratio: 0,
      beta: 0,
      concentration_risk: 0,
      updated_at: Date.now()
    };
  }

  async initialize(): Promise<void> {
    this.logger.info('Initializing Risk Engine...');
    
    try {
      // Initialize position tracking for enabled symbols
      const enabledSymbols = this.config.getEnabledSymbols();
      enabledSymbols.forEach((symbolConfig: any) => {
        this.positions.set(symbolConfig.symbol, {
          symbol: symbolConfig.symbol,
          quantity: 0,
          market_value: 0,
          cost_basis: 0,
          unrealized_pnl: 0,
          realized_pnl: 0,
          average_entry_price: 0,
          last_price: 0,
          updated_at: Date.now()
        });
      });
      
      // Start risk monitoring
      this.startRiskMonitoring();
      
      this.logger.info('Risk Engine initialized successfully');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to initialize Risk Engine');
      throw error;
    }
  }

  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.logger.info('Starting Risk Engine...');
    this.isRunning = true;
    
    this.logger.info('Risk Engine started successfully');
  }

  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Risk Engine...');
    this.isRunning = false;
    
    this.logger.info('Risk Engine stopped');
  }

  /**
   * Validate a signal against risk limits
   */
  async validateSignal(signal: Signal): Promise<RiskCheck> {
    if (!this.isRunning) {
      return {
        approved: false,
        risk_level: RiskLevel.CRITICAL,
        violations: ['Risk engine not running'],
        warnings: []
      };
    }

    const violations: string[] = [];
    const warnings: string[] = [];
    let riskLevel = RiskLevel.LOW;

    try {
      // Circuit breaker check
      if (this.circuitBreakerTriggered) {
        violations.push('Circuit breaker triggered - trading halted');
        riskLevel = RiskLevel.CRITICAL;
      }

      // Position size check
      const currentPosition = this.positions.get(signal.symbol);
      const symbolConfig = this.config.getSymbolConfig(signal.symbol);
      
      if (symbolConfig && currentPosition) {
        const proposedSize = this.estimateOrderSize(signal);
        const newPositionSize = Math.abs(currentPosition.quantity + proposedSize);
        
        if (newPositionSize > symbolConfig.maxPositionSize) {
          violations.push(`Position size limit exceeded for ${signal.symbol}`);
          riskLevel = RiskLevel.HIGH;
        }
        
        if (newPositionSize > this.riskLimits.maxPositionSize) {
          violations.push(`Global position size limit exceeded for ${signal.symbol}`);
          riskLevel = RiskLevel.CRITICAL;
        }
      }

      // Portfolio value check
      if (this.riskMetrics.portfolio_value > this.riskLimits.maxPortfolioValue) {
        violations.push('Portfolio value limit exceeded');
        riskLevel = RiskLevel.HIGH;
      }

      // Daily loss check
      if (this.dailyPnL < -this.riskLimits.maxDailyLoss) {
        violations.push('Daily loss limit exceeded');
        riskLevel = RiskLevel.CRITICAL;
      }

      // Drawdown check
      if (this.maxDrawdown > this.riskLimits.maxDrawdown) {
        violations.push('Maximum drawdown limit exceeded');
        riskLevel = RiskLevel.CRITICAL;
      }

      // Concentration risk check
      const concentrationRisk = this.calculateConcentrationRisk(signal.symbol);
      if (concentrationRisk > this.riskLimits.concentrationLimit) {
        violations.push(`Concentration limit exceeded for ${signal.symbol}`);
        riskLevel = RiskLevel.HIGH;
      }

      // Leverage check
      if (this.riskMetrics.leverage > this.riskLimits.leverageLimit) {
        violations.push('Leverage limit exceeded');
        riskLevel = RiskLevel.HIGH;
      }

      // Order rate limiting
      if (!this.checkOrderRateLimit(signal.symbol)) {
        violations.push('Order rate limit exceeded');
        riskLevel = RiskLevel.MEDIUM;
      }

      // VaR check
      if (this.riskMetrics.var_1d > this.riskLimits.maxVaR) {
        warnings.push('Value at Risk approaching limit');
        if (riskLevel === RiskLevel.LOW) riskLevel = RiskLevel.MEDIUM;
      }

      // Market hours check
      if (!this.config.isMarketOpen()) {
        violations.push('Market is closed');
        riskLevel = RiskLevel.HIGH;
      }

      // Signal strength check
      if (signal.strength < 0.5) {
        warnings.push('Low signal strength');
      }

      const approved = violations.length === 0;
      
      // Log risk check result
      this.logger.debug({
        signal: { id: signal.id, symbol: signal.symbol, type: signal.type },
        approved,
        riskLevel,
        violations,
        warnings
      }, 'Risk check completed');

      // Update metrics
      this.incrementMetric('risk_checks_performed');
      if (approved) {
        this.incrementMetric('risk_checks_approved');
      } else {
        this.incrementMetric('risk_checks_rejected');
      }

      return {
        approved,
        risk_level: riskLevel,
        violations,
        warnings,
        max_position_size: symbolConfig?.maxPositionSize,
        max_order_size: this.riskLimits.maxOrderSize
      };

    } catch (error) {
      this.logger.error({ error, signal }, 'Risk validation failed');
      
      return {
        approved: false,
        risk_level: RiskLevel.CRITICAL,
        violations: ['Risk validation system error'],
        warnings: []
      };
    }
  }

  /**
   * Update position after trade execution
   */
  updatePosition(position: Position): void {
    this.positions.set(position.symbol, position);
    
    // Recalculate risk metrics
    this.calculateRiskMetrics();
    
    // Check for risk breaches
    this.checkRiskBreaches();
    
    this.updateMetric(`${position.symbol}_position_size`, Math.abs(position.quantity));
    this.updateMetric(`${position.symbol}_unrealized_pnl`, position.unrealized_pnl);
  }

  /**
   * Calculate current risk metrics
   */
  private calculateRiskMetrics(): void {
    let totalValue = 0;
    let grossExposure = 0;
    let netExposure = 0;
    let totalUnrealizedPnL = 0;

    this.positions.forEach(position => {
      totalValue += position.market_value;
      grossExposure += Math.abs(position.market_value);
      netExposure += position.market_value;
      totalUnrealizedPnL += position.unrealized_pnl;
    });

    // Update drawdown
    if (totalValue > this.peakPortfolioValue) {
      this.peakPortfolioValue = totalValue;
    }
    
    const currentDrawdown = (this.peakPortfolioValue - totalValue) / this.peakPortfolioValue;
    if (currentDrawdown > this.maxDrawdown) {
      this.maxDrawdown = currentDrawdown;
    }

    this.riskMetrics = {
      portfolio_value: totalValue,
      total_exposure: grossExposure,
      net_exposure: netExposure,
      gross_exposure: grossExposure,
      leverage: grossExposure / Math.max(totalValue, 1),
      var_1d: this.calculateVaR(1),
      var_5d: this.calculateVaR(5),
      max_drawdown: this.maxDrawdown,
      sharpe_ratio: this.calculateSharpeRatio(),
      beta: this.calculateBeta(),
      concentration_risk: this.calculateMaxConcentrationRisk(),
      updated_at: Date.now()
    };

    // Update metrics
    this.updateMetric('portfolio_value', this.riskMetrics.portfolio_value);
    this.updateMetric('gross_exposure', this.riskMetrics.gross_exposure);
    this.updateMetric('leverage', this.riskMetrics.leverage);
    this.updateMetric('max_drawdown', this.riskMetrics.max_drawdown);
  }

  /**
   * Check for risk breaches and trigger alerts
   */
  private checkRiskBreaches(): void {
    const breaches: RiskBreach[] = [];

    // Check daily loss
    if (this.dailyPnL < -this.riskLimits.maxDailyLoss) {
      breaches.push({
        type: 'daily_loss',
        severity: RiskLevel.CRITICAL,
        currentValue: this.dailyPnL,
        limitValue: -this.riskLimits.maxDailyLoss,
        message: 'Daily loss limit exceeded',
        timestamp: Date.now()
      });
    }

    // Check drawdown
    if (this.maxDrawdown > this.riskLimits.maxDrawdown) {
      breaches.push({
        type: 'max_drawdown',
        severity: RiskLevel.CRITICAL,
        currentValue: this.maxDrawdown,
        limitValue: this.riskLimits.maxDrawdown,
        message: 'Maximum drawdown limit exceeded',
        timestamp: Date.now()
      });
    }

    // Check leverage
    if (this.riskMetrics.leverage > this.riskLimits.leverageLimit) {
      breaches.push({
        type: 'leverage',
        severity: RiskLevel.HIGH,
        currentValue: this.riskMetrics.leverage,
        limitValue: this.riskLimits.leverageLimit,
        message: 'Leverage limit exceeded',
        timestamp: Date.now()
      });
    }

    // Trigger circuit breaker for critical breaches
    const criticalBreaches = breaches.filter(b => b.severity === RiskLevel.CRITICAL);
    if (criticalBreaches.length > 0 && !this.circuitBreakerTriggered) {
      this.triggerCircuitBreaker();
    }

    // Emit risk breach events
    breaches.forEach(breach => {
      this.emit('riskBreach', breach);
      this.logger.warn({ breach }, 'Risk breach detected');
    });
  }

  /**
   * Trigger circuit breaker
   */
  private triggerCircuitBreaker(): void {
    this.circuitBreakerTriggered = true;
    this.logger.error('Circuit breaker triggered - all trading halted');
    
    const breach: RiskBreach = {
      type: 'circuit_breaker',
      severity: RiskLevel.CRITICAL,
      currentValue: 1,
      limitValue: 0,
      message: 'Circuit breaker triggered - trading halted',
      timestamp: Date.now()
    };
    
    this.emit('riskBreach', breach);
  }

  /**
   * Reset circuit breaker (manual intervention required)
   */
  resetCircuitBreaker(): void {
    this.circuitBreakerTriggered = false;
    this.logger.info('Circuit breaker reset - trading enabled');
  }

  /**
   * Start risk monitoring
   */
  private startRiskMonitoring(): void {
    setInterval(() => {
      this.calculateRiskMetrics();
      this.checkRiskBreaches();
    }, 5000); // Check every 5 seconds

    // Reset daily counters at market open
    setInterval(() => {
      if (this.shouldResetDailyCounters()) {
        this.resetDailyCounters();
      }
    }, 60000); // Check every minute
  }

  /**
   * Calculate concentration risk for a symbol
   */
  private calculateConcentrationRisk(symbol: string): number {
    const position = this.positions.get(symbol);
    if (!position) return 0;

    const positionValue = Math.abs(position.market_value);
    const totalValue = this.riskMetrics.portfolio_value;

    return totalValue > 0 ? positionValue / totalValue : 0;
  }

  /**
   * Calculate maximum concentration risk across all positions
   */
  private calculateMaxConcentrationRisk(): number {
    let maxConcentration = 0;

    this.positions.forEach((position, symbol) => {
      const concentration = this.calculateConcentrationRisk(symbol);
      if (concentration > maxConcentration) {
        maxConcentration = concentration;
      }
    });

    return maxConcentration;
  }

  /**
   * Check order rate limiting
   */
  private checkOrderRateLimit(symbol: string): boolean {
    const now = Date.now();
    const windowStart = now - 1000; // 1 second window
    
    // This would track order timestamps in a sliding window
    // For now, simplified implementation
    const recentOrders = this.orderCounts.get(symbol) || 0;
    
    if (recentOrders >= this.riskLimits.maxOrdersPerSecond) {
      return false;
    }
    
    this.orderCounts.set(symbol, recentOrders + 1);
    
    // Reset counters periodically
    setTimeout(() => {
      this.orderCounts.set(symbol, Math.max(0, (this.orderCounts.get(symbol) || 0) - 1));
    }, 1000);
    
    return true;
  }

  /**
   * Estimate order size from signal
   */
  private estimateOrderSize(signal: Signal): number {
    // This would use position sizing algorithms
    // For now, simplified implementation
    const symbolConfig = this.config.getSymbolConfig(signal.symbol);
    const maxSize = symbolConfig?.maxPositionSize || this.riskLimits.maxPositionSize;
    
    return maxSize * signal.strength * 0.1; // 10% of max position
  }

  /**
   * Calculate Value at Risk
   */
  private calculateVaR(days: number): number {
    // Simplified VaR calculation
    // In production, this would use proper risk models
    const portfolioValue = this.riskMetrics.portfolio_value;
    const volatility = 0.02; // 2% daily volatility assumption
    const confidence = 0.95; // 95% confidence level
    
    return portfolioValue * volatility * Math.sqrt(days) * 1.65; // 95% VaR
  }

  /**
   * Calculate Sharpe ratio
   */
  private calculateSharpeRatio(): number {
    // Simplified Sharpe ratio calculation
    return 0; // Would require return history
  }

  /**
   * Calculate portfolio beta
   */
  private calculateBeta(): number {
    // Simplified beta calculation
    return 1.0; // Would require benchmark correlation
  }

  /**
   * Check if daily counters should be reset
   */
  private shouldResetDailyCounters(): boolean {
    // Reset at market open
    const now = new Date();
    const hour = now.getHours();
    const minute = now.getMinutes();
    
    return hour === 9 && minute === 30; // 9:30 AM
  }

  /**
   * Reset daily risk counters
   */
  private resetDailyCounters(): void {
    this.dailyPnL = 0;
    this.maxDrawdown = 0;
    this.peakPortfolioValue = this.riskMetrics.portfolio_value;
    
    this.logger.info('Daily risk counters reset');
  }

  /**
   * Get current risk metrics
   */
  getRiskMetrics(): RiskMetrics {
    return { ...this.riskMetrics };
  }

  /**
   * Get current positions
   */
  getPositions(): Map<string, Position> {
    return new Map(this.positions);
  }

  /**
   * Get circuit breaker status
   */
  isCircuitBreakerTriggered(): boolean {
    return this.circuitBreakerTriggered;
  }
}

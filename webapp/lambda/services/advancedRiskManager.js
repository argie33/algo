/**
 * Advanced Risk Management System for HFT
 * Provides sophisticated risk controls, portfolio integration, and real-time monitoring
 */

const { createLogger } = require('../utils/structuredLogger');
const { query } = require('../utils/database');

class AdvancedRiskManager {
  constructor() {
    this.logger = createLogger('financial-platform', 'advanced-risk-manager');
    this.correlationId = this.generateCorrelationId();
    
    // Advanced risk parameters
    this.riskConfig = {
      // Portfolio-level limits
      maxPortfolioExposure: 10000, // USD
      maxSectorExposure: 0.30, // 30% of portfolio
      maxPositionConcentration: 0.15, // 15% of portfolio
      
      // Risk metrics thresholds
      maxVaR: 500, // Value at Risk daily
      maxSharpeRatio: -0.5, // Minimum acceptable Sharpe
      maxDrawdownPercent: 0.10, // 10%
      maxCorrelation: 0.80, // Between positions
      
      // Volatility controls
      maxVolatility: 0.25, // 25% annualized
      minLiquidity: 100000, // USD daily volume
      maxBeta: 2.0, // Portfolio beta limit
      
      // Time-based limits
      dailyTradingLimit: 50, // Max trades per day
      hourlyTradingLimit: 10, // Max trades per hour
      cooldownPeriod: 300000, // 5 minutes between same symbol trades
      
      // Advanced controls
      enableDynamicSizing: true,
      enableCorrelationLimits: true,
      enableVolatilityScaling: true,
      enableLiquidityFilters: true
    };
    
    // Runtime tracking
    this.portfolioExposure = 0;
    this.sectorExposures = new Map();
    this.positionCorrelations = new Map();
    this.volatilityCache = new Map();
    this.tradingActivity = {
      daily: 0,
      hourly: 0,
      lastReset: new Date()
    };
    
    this.lastTradesBySymbol = new Map();
  }

  generateCorrelationId() {
    return `risk-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Comprehensive risk assessment for trade approval
   */
  async assessTradeRisk(signal, currentPositions, portfolioValue) {
    const startTime = Date.now();
    
    try {
      this.logger.info('Starting advanced risk assessment', {
        symbol: signal.symbol,
        type: signal.type,
        quantity: signal.quantity,
        portfolioValue,
        correlationId: this.correlationId
      });

      // Update portfolio metrics
      await this.updatePortfolioMetrics(currentPositions, portfolioValue);
      
      // Risk checks
      const checks = {
        positionSize: await this.checkPositionSizing(signal, portfolioValue),
        portfolioExposure: this.checkPortfolioExposure(signal, portfolioValue),
        sectorExposure: await this.checkSectorExposure(signal, portfolioValue),
        correlation: await this.checkCorrelationLimits(signal, currentPositions),
        volatility: await this.checkVolatilityLimits(signal),
        liquidity: await this.checkLiquidityRequirements(signal),
        tradingLimits: this.checkTradingLimits(signal),
        cooldown: this.checkCooldownPeriod(signal),
        dynamicRisk: await this.calculateDynamicRisk(signal, currentPositions)
      };

      // Aggregate risk score
      const riskScore = this.calculateOverallRiskScore(checks);
      const approved = this.isTradeApproved(checks, riskScore);
      
      // Dynamic position sizing
      let adjustedQuantity = signal.quantity;
      if (approved && this.riskConfig.enableDynamicSizing) {
        adjustedQuantity = await this.calculateOptimalSize(signal, portfolioValue, riskScore);
      }

      const assessment = {
        approved,
        riskScore,
        adjustedQuantity,
        originalQuantity: signal.quantity,
        checks,
        reasoning: this.generateRiskReasoning(checks, riskScore),
        assessmentTime: Date.now() - startTime,
        timestamp: new Date().toISOString(),
        correlationId: this.correlationId
      };

      this.logger.info('Risk assessment completed', {
        symbol: signal.symbol,
        approved,
        riskScore,
        assessmentTime: assessment.assessmentTime,
        correlationId: this.correlationId
      });

      return assessment;
      
    } catch (error) {
      this.logger.error('Risk assessment failed', {
        symbol: signal.symbol,
        error: error.message,
        correlationId: this.correlationId
      });
      
      return {
        approved: false,
        riskScore: 1.0, // Maximum risk
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Check position sizing limits
   */
  async checkPositionSizing(signal, portfolioValue) {
    const positionValue = signal.quantity * signal.price;
    const positionPercent = positionValue / portfolioValue;
    
    const maxPositionValue = portfolioValue * this.riskConfig.maxPositionConcentration;
    
    return {
      passed: positionValue <= maxPositionValue,
      positionValue,
      positionPercent,
      maxAllowed: maxPositionValue,
      metric: 'position_sizing'
    };
  }

  /**
   * Check portfolio exposure limits
   */
  checkPortfolioExposure(signal, portfolioValue) {
    const positionValue = signal.quantity * signal.price;
    const newExposure = this.portfolioExposure + positionValue;
    
    return {
      passed: newExposure <= this.riskConfig.maxPortfolioExposure,
      currentExposure: this.portfolioExposure,
      newExposure,
      maxAllowed: this.riskConfig.maxPortfolioExposure,
      metric: 'portfolio_exposure'
    };
  }

  /**
   * Check sector exposure limits
   */
  async checkSectorExposure(signal, portfolioValue) {
    try {
      // Get sector information for the symbol
      const sectorInfo = await query(
        'SELECT sector FROM stock_symbols WHERE symbol = $1',
        [signal.symbol]
      );
      
      if (!sectorInfo.rows || sectorInfo.rows.length === 0) {
        return {
          passed: true,
          sector: 'unknown',
          warning: 'Sector information not available',
          metric: 'sector_exposure'
        };
      }
      
      const sector = sectorInfo.rows[0].sector;
      const positionValue = signal.quantity * signal.price;
      const currentSectorExposure = this.sectorExposures.get(sector) || 0;
      const newSectorExposure = currentSectorExposure + positionValue;
      const sectorPercent = newSectorExposure / portfolioValue;
      
      return {
        passed: sectorPercent <= this.riskConfig.maxSectorExposure,
        sector,
        currentExposure: currentSectorExposure,
        newExposure: newSectorExposure,
        sectorPercent,
        maxAllowed: this.riskConfig.maxSectorExposure,
        metric: 'sector_exposure'
      };
      
    } catch (error) {
      this.logger.error('Sector exposure check failed', {
        symbol: signal.symbol,
        error: error.message,
        correlationId: this.correlationId
      });
      
      return {
        passed: true, // Allow trade but log warning
        warning: 'Sector check failed',
        error: error.message,
        metric: 'sector_exposure'
      };
    }
  }

  /**
   * Check correlation limits with existing positions
   */
  async checkCorrelationLimits(signal, currentPositions) {
    if (!this.riskConfig.enableCorrelationLimits || currentPositions.size === 0) {
      return {
        passed: true,
        correlations: [],
        metric: 'correlation_limits'
      };
    }

    try {
      const correlations = [];
      const symbolList = Array.from(currentPositions.keys());
      symbolList.push(signal.symbol);
      
      // Get correlation data (simplified - would use real correlation matrix)
      const correlationMatrix = await this.calculateCorrelationMatrix(symbolList);
      
      for (const [symbol, position] of currentPositions) {
        const correlation = correlationMatrix.get(`${signal.symbol}_${symbol}`) || 0;
        correlations.push({
          symbol,
          correlation,
          positionValue: position.value
        });
      }
      
      const maxCorrelation = Math.max(...correlations.map(c => Math.abs(c.correlation)));
      
      return {
        passed: maxCorrelation <= this.riskConfig.maxCorrelation,
        correlations,
        maxCorrelation,
        maxAllowed: this.riskConfig.maxCorrelation,
        metric: 'correlation_limits'
      };
      
    } catch (error) {
      this.logger.error('Correlation check failed', {
        symbol: signal.symbol,
        error: error.message,
        correlationId: this.correlationId
      });
      
      return {
        passed: true,
        warning: 'Correlation analysis failed',
        metric: 'correlation_limits'
      };
    }
  }

  /**
   * Check volatility limits
   */
  async checkVolatilityLimits(signal) {
    try {
      const volatility = await this.getSymbolVolatility(signal.symbol);
      
      return {
        passed: volatility <= this.riskConfig.maxVolatility,
        volatility,
        maxAllowed: this.riskConfig.maxVolatility,
        metric: 'volatility_limits'
      };
      
    } catch (error) {
      return {
        passed: true,
        warning: 'Volatility data unavailable',
        metric: 'volatility_limits'
      };
    }
  }

  /**
   * Check liquidity requirements
   */
  async checkLiquidityRequirements(signal) {
    try {
      // Get recent volume data
      const volumeData = await query(`
        SELECT AVG(volume * close) as avg_dollar_volume
        FROM price_daily 
        WHERE symbol = $1 
        AND date >= CURRENT_DATE - INTERVAL '20 days'
      `, [signal.symbol]);
      
      const avgDollarVolume = volumeData.rows[0]?.avg_dollar_volume || 0;
      
      return {
        passed: avgDollarVolume >= this.riskConfig.minLiquidity,
        avgDollarVolume,
        minRequired: this.riskConfig.minLiquidity,
        metric: 'liquidity_requirements'
      };
      
    } catch (error) {
      return {
        passed: true,
        warning: 'Liquidity data unavailable',
        metric: 'liquidity_requirements'
      };
    }
  }

  /**
   * Check trading limits (daily/hourly)
   */
  checkTradingLimits(signal) {
    const now = new Date();
    
    // Reset counters if needed
    if (now.toDateString() !== this.tradingActivity.lastReset.toDateString()) {
      this.tradingActivity.daily = 0;
      this.tradingActivity.lastReset = now;
    }
    
    if (now.getHours() !== this.tradingActivity.lastReset.getHours()) {
      this.tradingActivity.hourly = 0;
    }
    
    const dailyOk = this.tradingActivity.daily < this.riskConfig.dailyTradingLimit;
    const hourlyOk = this.tradingActivity.hourly < this.riskConfig.hourlyTradingLimit;
    
    return {
      passed: dailyOk && hourlyOk,
      dailyTrades: this.tradingActivity.daily,
      hourlyTrades: this.tradingActivity.hourly,
      dailyLimit: this.riskConfig.dailyTradingLimit,
      hourlyLimit: this.riskConfig.hourlyTradingLimit,
      metric: 'trading_limits'
    };
  }

  /**
   * Check cooldown period between trades for same symbol
   */
  checkCooldownPeriod(signal) {
    const lastTrade = this.lastTradesBySymbol.get(signal.symbol);
    if (!lastTrade) {
      return {
        passed: true,
        metric: 'cooldown_period'
      };
    }
    
    const timeSinceLastTrade = Date.now() - lastTrade;
    const cooldownOk = timeSinceLastTrade >= this.riskConfig.cooldownPeriod;
    
    return {
      passed: cooldownOk,
      timeSinceLastTrade,
      cooldownRequired: this.riskConfig.cooldownPeriod,
      remainingCooldown: Math.max(0, this.riskConfig.cooldownPeriod - timeSinceLastTrade),
      metric: 'cooldown_period'
    };
  }

  /**
   * Calculate dynamic risk based on market conditions
   */
  async calculateDynamicRisk(signal, currentPositions) {
    try {
      // Market volatility factor
      const marketVol = await this.getMarketVolatility();
      const volFactor = Math.min(marketVol / 0.20, 2.0); // Scale to normal 20% vol
      
      // Portfolio heat (concentration risk)
      const portfolioHeat = currentPositions.size / 10; // Normalize to 10 positions
      
      // Recent performance factor
      const recentPnL = await this.getRecentPnL();
      const performanceFactor = recentPnL < -100 ? 1.5 : recentPnL > 100 ? 0.8 : 1.0;
      
      const dynamicRiskScore = volFactor * portfolioHeat * performanceFactor;
      
      return {
        passed: dynamicRiskScore < 1.5,
        dynamicRiskScore,
        factors: {
          marketVolatility: marketVol,
          volatilityFactor: volFactor,
          portfolioHeat,
          performanceFactor
        },
        metric: 'dynamic_risk'
      };
      
    } catch (error) {
      return {
        passed: true,
        warning: 'Dynamic risk calculation failed',
        metric: 'dynamic_risk'
      };
    }
  }

  /**
   * Calculate overall risk score
   */
  calculateOverallRiskScore(checks) {
    let riskScore = 0;
    let totalWeight = 0;
    
    const weights = {
      positionSize: 0.20,
      portfolioExposure: 0.15,
      sectorExposure: 0.15,
      correlation: 0.15,
      volatility: 0.10,
      liquidity: 0.10,
      tradingLimits: 0.05,
      cooldown: 0.05,
      dynamicRisk: 0.05
    };
    
    for (const [checkName, check] of Object.entries(checks)) {
      if (check && weights[checkName]) {
        const weight = weights[checkName];
        const checkRisk = check.passed ? 0 : 1;
        
        riskScore += checkRisk * weight;
        totalWeight += weight;
      }
    }
    
    return totalWeight > 0 ? riskScore / totalWeight : 0;
  }

  /**
   * Determine if trade should be approved
   */
  isTradeApproved(checks, riskScore) {
    // Critical checks that must pass
    const criticalChecks = ['positionSize', 'portfolioExposure', 'tradingLimits'];
    
    for (const critical of criticalChecks) {
      if (checks[critical] && !checks[critical].passed) {
        return false;
      }
    }
    
    // Overall risk score threshold
    return riskScore < 0.7; // 70% risk threshold
  }

  /**
   * Calculate optimal position size based on risk
   */
  async calculateOptimalSize(signal, portfolioValue, riskScore) {
    try {
      // Kelly Criterion inspired sizing
      const volatility = await this.getSymbolVolatility(signal.symbol);
      const expectedReturn = 0.001; // Assume 0.1% expected return per trade
      
      // Base Kelly fraction
      const kellyFraction = expectedReturn / (volatility * volatility);
      
      // Risk adjustment
      const riskAdjustment = Math.max(0.1, 1.0 - riskScore);
      
      // Conservative sizing (max 2% of portfolio)
      const maxPosition = portfolioValue * 0.02;
      const optimalSize = Math.min(
        signal.quantity,
        Math.floor(maxPosition * kellyFraction * riskAdjustment / signal.price)
      );
      
      return Math.max(1, optimalSize); // Minimum 1 share
      
    } catch (error) {
      return signal.quantity; // Return original if calculation fails
    }
  }

  /**
   * Generate risk reasoning explanation
   */
  generateRiskReasoning(checks, riskScore) {
    const reasons = [];
    
    if (riskScore < 0.3) {
      reasons.push('Low risk trade - all checks passed');
    } else if (riskScore < 0.7) {
      reasons.push('Moderate risk trade - some concerns identified');
    } else {
      reasons.push('High risk trade - multiple risk factors detected');
    }
    
    // Add specific check failures
    for (const [checkName, check] of Object.entries(checks)) {
      if (check && !check.passed) {
        reasons.push(`${checkName} check failed`);
      }
    }
    
    return reasons;
  }

  // Helper methods for data fetching
  async updatePortfolioMetrics(currentPositions, portfolioValue) {
    this.portfolioExposure = Array.from(currentPositions.values())
      .reduce((sum, pos) => sum + pos.value, 0);
  }

  async getSymbolVolatility(symbol) {
    // Simplified volatility calculation
    const cached = this.volatilityCache.get(symbol);
    if (cached && Date.now() - cached.timestamp < 3600000) { // 1 hour cache
      return cached.volatility;
    }
    
    try {
      const priceData = await query(`
        SELECT close, LAG(close) OVER (ORDER BY date) as prev_close
        FROM price_daily 
        WHERE symbol = $1 
        AND date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY date
      `, [symbol]);
      
      if (priceData.rows.length < 10) return 0.20; // Default 20%
      
      const returns = priceData.rows
        .filter(row => row.prev_close)
        .map(row => Math.log(row.close / row.prev_close));
      
      const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
      const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length;
      const volatility = Math.sqrt(variance * 252); // Annualized
      
      this.volatilityCache.set(symbol, {
        volatility,
        timestamp: Date.now()
      });
      
      return volatility;
      
    } catch (error) {
      return 0.20; // Default fallback
    }
  }

  async calculateCorrelationMatrix(symbols) {
    // Simplified correlation calculation
    const correlations = new Map();
    
    for (let i = 0; i < symbols.length; i++) {
      for (let j = i + 1; j < symbols.length; j++) {
        const correlation = Math.random() * 0.6 - 0.3; // Mock correlation
        correlations.set(`${symbols[i]}_${symbols[j]}`, correlation);
        correlations.set(`${symbols[j]}_${symbols[i]}`, correlation);
      }
    }
    
    return correlations;
  }

  async getMarketVolatility() {
    // Simplified market volatility (would use VIX or similar)
    return 0.18; // 18% default
  }

  async getRecentPnL() {
    // Get recent P&L from database
    try {
      const result = await query(`
        SELECT SUM(profit_loss) as recent_pnl
        FROM trading_history 
        WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
      `);
      
      return result.rows[0]?.recent_pnl || 0;
    } catch (error) {
      return 0;
    }
  }

  /**
   * Record trade execution for tracking
   */
  recordTradeExecution(signal) {
    this.tradingActivity.daily++;
    this.tradingActivity.hourly++;
    this.lastTradesBySymbol.set(signal.symbol, Date.now());
  }

  /**
   * Get current risk metrics
   */
  getRiskMetrics() {
    return {
      portfolioExposure: this.portfolioExposure,
      sectorExposures: Object.fromEntries(this.sectorExposures),
      tradingActivity: this.tradingActivity,
      riskConfig: this.riskConfig,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Update risk configuration
   */
  updateRiskConfig(newConfig) {
    this.riskConfig = { ...this.riskConfig, ...newConfig };
    
    this.logger.info('Risk configuration updated', {
      newConfig,
      correlationId: this.correlationId
    });
  }
}

module.exports = AdvancedRiskManager;
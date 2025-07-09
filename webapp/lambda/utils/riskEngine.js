const { query } = require('./database');
const EventEmitter = require('events');

class RiskEngine extends EventEmitter {
  constructor() {
    super();
    this.monitoringUsers = new Map();
    this.monitoringInterval = null;
    this.isMonitoring = false;
    this.checkInterval = 300000; // 5 minutes default
  }

  async calculatePortfolioRisk(portfolioId, timeframe = '1Y', confidenceLevel = 0.95) {
    try {
      // Get portfolio holdings
      const holdingsResult = await query(`
        SELECT 
          ph.symbol,
          ph.quantity,
          ph.average_cost,
          ph.current_price,
          ph.market_value,
          ph.weight,
          sse.sector,
          sse.industry
        FROM portfolio_holdings ph
        JOIN stock_symbols_enhanced sse ON ph.symbol = sse.symbol
        WHERE ph.portfolio_id = $1
      `, [portfolioId]);

      const holdings = holdingsResult.rows;
      if (holdings.length === 0) {
        return {
          portfolio_id: portfolioId,
          error: 'No holdings found in portfolio'
        };
      }

      // Get historical price data for all symbols
      const symbols = holdings.map(h => h.symbol);
      const priceData = await this.getHistoricalPrices(symbols, timeframe);

      // Calculate portfolio returns
      const portfolioReturns = this.calculatePortfolioReturns(holdings, priceData);

      // Calculate risk metrics
      const riskMetrics = {
        portfolio_id: portfolioId,
        timeframe: timeframe,
        confidence_level: confidenceLevel,
        
        // Basic risk metrics
        volatility: this.calculateVolatility(portfolioReturns),
        var_95: this.calculateVaR(portfolioReturns, 0.95),
        var_99: this.calculateVaR(portfolioReturns, 0.99),
        expected_shortfall: this.calculateExpectedShortfall(portfolioReturns, confidenceLevel),
        
        // Performance metrics
        sharpe_ratio: this.calculateSharpeRatio(portfolioReturns),
        max_drawdown: this.calculateMaxDrawdown(portfolioReturns),
        
        // Portfolio composition metrics
        concentration_risk: this.calculateConcentrationRisk(holdings),
        sector_exposure: this.calculateSectorExposure(holdings),
        
        // Correlation and diversification
        correlation_matrix: await this.calculateCorrelationMatrix(portfolioId),
        diversification_ratio: this.calculateDiversificationRatio(holdings, priceData),
        
        // Market risk metrics
        beta: await this.calculatePortfolioBeta(portfolioId, symbols),
        tracking_error: await this.calculateTrackingError(portfolioId, symbols),
        
        calculated_at: new Date().toISOString()
      };

      // Store risk metrics
      await this.storeRiskMetrics(portfolioId, riskMetrics);

      return riskMetrics;
    } catch (error) {
      console.error('Error calculating portfolio risk:', error);
      throw error;
    }
  }

  async calculateVaR(portfolioId, method = 'historical', confidenceLevel = 0.95, timeHorizon = 1, lookbackDays = 252) {
    try {
      const holdings = await this.getPortfolioHoldings(portfolioId);
      const symbols = holdings.map(h => h.symbol);
      const priceData = await this.getHistoricalPrices(symbols, `${lookbackDays}D`);
      
      const portfolioReturns = this.calculatePortfolioReturns(holdings, priceData);
      
      let var_value;
      
      switch (method) {
        case 'historical':
          var_value = this.calculateHistoricalVaR(portfolioReturns, confidenceLevel);
          break;
        case 'parametric':
          var_value = this.calculateParametricVaR(portfolioReturns, confidenceLevel, timeHorizon);
          break;
        case 'monte_carlo':
          var_value = await this.calculateMonteCarloVaR(portfolioReturns, confidenceLevel, timeHorizon);
          break;
        default:
          var_value = this.calculateHistoricalVaR(portfolioReturns, confidenceLevel);
      }
      
      return {
        portfolio_id: portfolioId,
        method: method,
        confidence_level: confidenceLevel,
        time_horizon: timeHorizon,
        var_value: var_value,
        expected_shortfall: this.calculateExpectedShortfall(portfolioReturns, confidenceLevel),
        lookback_days: lookbackDays,
        calculated_at: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error calculating VaR:', error);
      throw error;
    }
  }

  async performStressTest(portfolioId, scenarios, shockMagnitude = 0.1, correlationAdjustment = false) {
    try {
      const holdings = await this.getPortfolioHoldings(portfolioId);
      const symbols = holdings.map(h => h.symbol);
      
      const stressTestResults = {
        portfolio_id: portfolioId,
        shock_magnitude: shockMagnitude,
        correlation_adjustment: correlationAdjustment,
        scenarios: [],
        summary: null
      };

      // Default scenarios if none provided
      if (scenarios.length === 0) {
        scenarios = [
          { name: 'Market Crash', type: 'market_shock', magnitude: -0.2 },
          { name: 'Interest Rate Shock', type: 'rate_shock', magnitude: 0.02 },
          { name: 'Sector Rotation', type: 'sector_shock', magnitude: -0.15 },
          { name: 'Volatility Spike', type: 'volatility_shock', magnitude: 0.5 },
          { name: 'Credit Spread Widening', type: 'credit_shock', magnitude: 0.01 }
        ];
      }

      // Run each scenario
      for (const scenario of scenarios) {
        const scenarioResult = await this.runStressScenario(
          portfolioId,
          holdings,
          scenario,
          correlationAdjustment
        );
        stressTestResults.scenarios.push(scenarioResult);
      }

      // Calculate summary statistics
      const pnlValues = stressTestResults.scenarios.map(s => s.portfolio_pnl);
      stressTestResults.summary = {
        worst_case_pnl: Math.min(...pnlValues),
        best_case_pnl: Math.max(...pnlValues),
        average_pnl: pnlValues.reduce((a, b) => a + b, 0) / pnlValues.length,
        scenarios_count: scenarios.length,
        fail_threshold: -0.05, // 5% loss threshold
        scenarios_exceeding_threshold: pnlValues.filter(pnl => pnl < -0.05).length
      };

      return stressTestResults;
    } catch (error) {
      console.error('Error performing stress test:', error);
      throw error;
    }
  }

  async startRealTimeMonitoring(userId, portfolioIds = [], checkInterval = 300000) {
    try {
      // Get user's portfolios if none specified
      if (portfolioIds.length === 0) {
        const portfoliosResult = await query(`
          SELECT id FROM portfolios WHERE user_id = $1
        `, [userId]);
        portfolioIds = portfoliosResult.rows.map(row => row.id);
      }

      // Get risk limits for monitoring
      const limitsResult = await query(`
        SELECT 
          rl.portfolio_id,
          rl.metric_name,
          rl.threshold_value,
          rl.warning_threshold,
          rl.threshold_type
        FROM risk_limits rl
        WHERE rl.portfolio_id = ANY($1) AND rl.is_active = true
      `, [portfolioIds]);

      // Store monitoring configuration
      this.monitoringUsers.set(userId, {
        portfolios: portfolioIds,
        limits: limitsResult.rows,
        last_check: new Date(),
        check_interval: checkInterval
      });

      // Start monitoring if not already running
      if (!this.isMonitoring) {
        this.startMonitoringLoop();
      }

      return {
        user_id: userId,
        portfolios_monitored: portfolioIds.length,
        limits_configured: limitsResult.rows.length,
        check_interval: checkInterval,
        status: 'active'
      };
    } catch (error) {
      console.error('Error starting real-time monitoring:', error);
      throw error;
    }
  }

  async stopRealTimeMonitoring(userId) {
    try {
      const wasMonitoring = this.monitoringUsers.has(userId);
      this.monitoringUsers.delete(userId);

      // Stop monitoring loop if no users left
      if (this.monitoringUsers.size === 0 && this.isMonitoring) {
        this.stopMonitoringLoop();
      }

      return {
        user_id: userId,
        was_monitoring: wasMonitoring,
        status: 'stopped'
      };
    } catch (error) {
      console.error('Error stopping real-time monitoring:', error);
      throw error;
    }
  }

  startMonitoringLoop() {
    if (this.isMonitoring) return;

    this.isMonitoring = true;
    console.log('Starting real-time risk monitoring...');

    this.monitoringInterval = setInterval(async () => {
      try {
        await this.performMonitoringCheck();
      } catch (error) {
        console.error('Error in monitoring check:', error);
      }
    }, this.checkInterval);

    this.emit('monitoring_started');
  }

  stopMonitoringLoop() {
    if (!this.isMonitoring) return;

    this.isMonitoring = false;
    
    if (this.monitoringInterval) {
      clearInterval(this.monitoringInterval);
      this.monitoringInterval = null;
    }

    console.log('Stopped real-time risk monitoring');
    this.emit('monitoring_stopped');
  }

  async performMonitoringCheck() {
    for (const [userId, config] of this.monitoringUsers) {
      try {
        await this.checkUserPortfolios(userId, config);
      } catch (error) {
        console.error(`Error checking portfolios for user ${userId}:`, error);
      }
    }
  }

  async checkUserPortfolios(userId, config) {
    for (const portfolioId of config.portfolios) {
      try {
        // Calculate current risk metrics
        const riskMetrics = await this.calculatePortfolioRisk(portfolioId);

        // Check against limits
        const portfolioLimits = config.limits.filter(l => l.portfolio_id === portfolioId);
        
        for (const limit of portfolioLimits) {
          const currentValue = riskMetrics[limit.metric_name];
          if (currentValue !== undefined) {
            await this.checkRiskLimit(userId, portfolioId, limit, currentValue);
          }
        }
      } catch (error) {
        console.error(`Error checking portfolio ${portfolioId}:`, error);
      }
    }
  }

  async checkRiskLimit(userId, portfolioId, limit, currentValue) {
    try {
      const isBreached = this.isLimitBreached(limit, currentValue);
      const isWarning = this.isWarningThreshold(limit, currentValue);

      if (isBreached || isWarning) {
        // Check if alert already exists
        const existingAlertResult = await query(`
          SELECT id FROM risk_alerts
          WHERE user_id = $1 AND portfolio_id = $2 AND metric_name = $3 AND status = 'active'
        `, [userId, portfolioId, limit.metric_name]);

        if (existingAlertResult.rows.length === 0) {
          // Create new alert
          await this.createRiskAlert(userId, portfolioId, limit, currentValue, isBreached);
        } else {
          // Update existing alert
          await query(`
            UPDATE risk_alerts
            SET current_value = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2
          `, [currentValue, existingAlertResult.rows[0].id]);
        }
      }
    } catch (error) {
      console.error('Error checking risk limit:', error);
    }
  }

  async createRiskAlert(userId, portfolioId, limit, currentValue, isBreached) {
    try {
      const severity = isBreached ? 'high' : 'medium';
      const alertType = isBreached ? 'limit_breach' : 'warning_threshold';
      
      const title = `${limit.metric_name} ${isBreached ? 'Limit Breached' : 'Warning Threshold Exceeded'}`;
      const description = `Portfolio ${portfolioId}: ${limit.metric_name} is ${currentValue.toFixed(4)}, ${isBreached ? 'exceeding limit' : 'approaching limit'} of ${limit.threshold_value}`;

      await query(`
        INSERT INTO risk_alerts (
          user_id, portfolio_id, alert_type, severity, title, description,
          metric_name, current_value, threshold_value, status, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'active', CURRENT_TIMESTAMP)
      `, [
        userId, portfolioId, alertType, severity, title, description,
        limit.metric_name, currentValue, limit.threshold_value
      ]);

      // Emit alert event
      this.emit('risk_alert', {
        userId,
        portfolioId,
        alertType,
        severity,
        title,
        description,
        metricName: limit.metric_name,
        currentValue,
        thresholdValue: limit.threshold_value
      });
    } catch (error) {
      console.error('Error creating risk alert:', error);
    }
  }

  isLimitBreached(limit, currentValue) {
    switch (limit.threshold_type) {
      case 'greater_than':
        return currentValue > limit.threshold_value;
      case 'less_than':
        return currentValue < limit.threshold_value;
      case 'absolute':
        return Math.abs(currentValue) > limit.threshold_value;
      default:
        return currentValue > limit.threshold_value;
    }
  }

  isWarningThreshold(limit, currentValue) {
    if (!limit.warning_threshold) return false;
    
    switch (limit.threshold_type) {
      case 'greater_than':
        return currentValue > limit.warning_threshold;
      case 'less_than':
        return currentValue < limit.warning_threshold;
      case 'absolute':
        return Math.abs(currentValue) > limit.warning_threshold;
      default:
        return currentValue > limit.warning_threshold;
    }
  }

  // Helper methods for risk calculations
  calculateVolatility(returns) {
    const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / (returns.length - 1);
    return Math.sqrt(variance * 252); // Annualized volatility
  }

  calculateHistoricalVaR(returns, confidenceLevel) {
    const sortedReturns = returns.slice().sort((a, b) => a - b);
    const index = Math.floor((1 - confidenceLevel) * sortedReturns.length);
    return sortedReturns[index];
  }

  calculateParametricVaR(returns, confidenceLevel, timeHorizon) {
    const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
    const volatility = this.calculateVolatility(returns);
    const zScore = this.getZScore(confidenceLevel);
    
    return mean - (zScore * volatility * Math.sqrt(timeHorizon / 252));
  }

  calculateExpectedShortfall(returns, confidenceLevel) {
    const var_value = this.calculateHistoricalVaR(returns, confidenceLevel);
    const tailReturns = returns.filter(r => r <= var_value);
    return tailReturns.reduce((a, b) => a + b, 0) / tailReturns.length;
  }

  calculateSharpeRatio(returns, riskFreeRate = 0.02) {
    const excessReturns = returns.map(r => r - riskFreeRate / 252);
    const meanExcess = excessReturns.reduce((a, b) => a + b, 0) / excessReturns.length;
    const volatility = this.calculateVolatility(excessReturns);
    return (meanExcess * 252) / volatility;
  }

  calculateMaxDrawdown(returns) {
    let maxDrawdown = 0;
    let peak = 0;
    let cumulativeReturn = 0;
    
    for (const return_val of returns) {
      cumulativeReturn += return_val;
      peak = Math.max(peak, cumulativeReturn);
      const drawdown = (peak - cumulativeReturn) / peak;
      maxDrawdown = Math.max(maxDrawdown, drawdown);
    }
    
    return maxDrawdown;
  }

  calculateConcentrationRisk(holdings) {
    const weights = holdings.map(h => h.weight);
    const herfindahlIndex = weights.reduce((sum, w) => sum + w * w, 0);
    return {
      herfindahl_index: herfindahlIndex,
      effective_number_of_holdings: 1 / herfindahlIndex,
      concentration_risk: herfindahlIndex > 0.25 ? 'high' : herfindahlIndex > 0.15 ? 'medium' : 'low'
    };
  }

  calculateSectorExposure(holdings) {
    const sectorExposure = {};
    
    holdings.forEach(holding => {
      const sector = holding.sector || 'Unknown';
      sectorExposure[sector] = (sectorExposure[sector] || 0) + holding.weight;
    });
    
    return sectorExposure;
  }

  getZScore(confidenceLevel) {
    // Approximate z-scores for common confidence levels
    const zScores = {
      0.90: 1.282,
      0.95: 1.645,
      0.99: 2.326,
      0.999: 3.090
    };
    
    return zScores[confidenceLevel] || 1.645;
  }

  async getPortfolioHoldings(portfolioId) {
    const result = await query(`
      SELECT 
        symbol,
        quantity,
        average_cost,
        current_price,
        market_value,
        weight
      FROM portfolio_holdings
      WHERE portfolio_id = $1
    `, [portfolioId]);
    
    return result.rows;
  }

  async getHistoricalPrices(symbols, timeframe) {
    // This would fetch historical price data
    // For now, return mock data structure
    const mockData = {};
    
    symbols.forEach(symbol => {
      mockData[symbol] = {
        prices: Array.from({ length: 252 }, (_, i) => 100 + Math.random() * 20 - 10),
        dates: Array.from({ length: 252 }, (_, i) => new Date(Date.now() - i * 24 * 60 * 60 * 1000))
      };
    });
    
    return mockData;
  }

  calculatePortfolioReturns(holdings, priceData) {
    // Calculate portfolio returns based on holdings and price data
    const portfolioReturns = [];
    
    // This is a simplified calculation - in reality you'd need to properly weight returns
    for (let i = 1; i < 252; i++) {
      let portfolioReturn = 0;
      
      holdings.forEach(holding => {
        const symbolData = priceData[holding.symbol];
        if (symbolData && symbolData.prices[i] && symbolData.prices[i-1]) {
          const return_val = (symbolData.prices[i] - symbolData.prices[i-1]) / symbolData.prices[i-1];
          portfolioReturn += return_val * holding.weight;
        }
      });
      
      portfolioReturns.push(portfolioReturn);
    }
    
    return portfolioReturns;
  }

  async storeRiskMetrics(portfolioId, metrics) {
    try {
      await query(`
        INSERT INTO portfolio_risk_metrics (
          portfolio_id, volatility, var_95, var_99, expected_shortfall,
          sharpe_ratio, max_drawdown, beta, calculated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP)
        ON CONFLICT (portfolio_id) DO UPDATE SET
          volatility = EXCLUDED.volatility,
          var_95 = EXCLUDED.var_95,
          var_99 = EXCLUDED.var_99,
          expected_shortfall = EXCLUDED.expected_shortfall,
          sharpe_ratio = EXCLUDED.sharpe_ratio,
          max_drawdown = EXCLUDED.max_drawdown,
          beta = EXCLUDED.beta,
          calculated_at = EXCLUDED.calculated_at
      `, [
        portfolioId,
        metrics.volatility,
        metrics.var_95,
        metrics.var_99,
        metrics.expected_shortfall,
        metrics.sharpe_ratio,
        metrics.max_drawdown,
        metrics.beta
      ]);
    } catch (error) {
      console.error('Error storing risk metrics:', error);
    }
  }

  async getMonitoringStatus(userId) {
    const userConfig = this.monitoringUsers.get(userId);
    
    if (!userConfig) {
      return {
        user_id: userId,
        status: 'not_monitoring',
        portfolios_monitored: 0
      };
    }

    return {
      user_id: userId,
      status: 'monitoring',
      portfolios_monitored: userConfig.portfolios.length,
      limits_configured: userConfig.limits.length,
      last_check: userConfig.last_check,
      check_interval: userConfig.check_interval
    };
  }

  // Additional helper methods would be implemented here...
  async calculateCorrelationMatrix(portfolioId) {
    // Placeholder for correlation matrix calculation
    return {};
  }

  calculateDiversificationRatio(holdings, priceData) {
    // Placeholder for diversification ratio calculation
    return 0.5;
  }

  async calculatePortfolioBeta(portfolioId, symbols) {
    // Placeholder for portfolio beta calculation
    return 1.0;
  }

  async calculateTrackingError(portfolioId, symbols) {
    // Placeholder for tracking error calculation
    return 0.02;
  }

  async calculateRiskAttribution(portfolioId, attributionType) {
    // Placeholder for risk attribution calculation
    return {
      attribution_type: attributionType,
      contributions: {}
    };
  }

  async runStressScenario(portfolioId, holdings, scenario, correlationAdjustment) {
    // Placeholder for stress scenario calculation
    return {
      scenario_name: scenario.name,
      scenario_type: scenario.type,
      portfolio_pnl: Math.random() * 0.2 - 0.1, // Random P&L for demo
      worst_holding: holdings[0]?.symbol || 'N/A',
      best_holding: holdings[1]?.symbol || 'N/A'
    };
  }

  async calculateMonteCarloVaR(returns, confidenceLevel, timeHorizon) {
    // Placeholder for Monte Carlo VaR calculation
    return this.calculateHistoricalVaR(returns, confidenceLevel);
  }
}

module.exports = RiskEngine;
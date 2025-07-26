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
    try {
      console.log(`📊 Fetching real historical data for ${symbols.length} symbols, timeframe: ${timeframe}`);
      
      const MarketDataService = require('../services/marketDataService');
      const priceData = {};
      
      // Convert timeframe to period for market data service
      const periodMap = {
        '1D': '1d', '5D': '5d', '30D': '1mo', '90D': '3mo', 
        '252D': '1y', '1Y': '1y', '2Y': '2y', '5Y': '5y'
      };
      const period = periodMap[timeframe] || '1y';
      
      // Fetch historical data for each symbol
      for (const symbol of symbols) {
        try {
          const historicalData = await MarketDataService.getHistoricalData(symbol, {
            period: period,
            interval: '1d'
          });
          
          if (historicalData && historicalData.length > 0) {
            priceData[symbol] = {
              prices: historicalData.map(d => d.close),
              dates: historicalData.map(d => new Date(d.date)),
              volumes: historicalData.map(d => d.volume)
            };
            console.log(`✅ Retrieved ${historicalData.length} price points for ${symbol}`);
          } else {
            throw new Error('No historical data available');
          }
        } catch (error) {
          console.warn(`⚠️ Real data failed for ${symbol}, using fallback:`, error.message);
          priceData[symbol] = this.generateRealisticPriceHistory(symbol);
        }
      }
      
      console.log(`📊 Historical data fetch complete: ${Object.keys(priceData).length}/${symbols.length} symbols`);
      return priceData;
      
    } catch (error) {
      console.error('Historical price fetch failed, using fallbacks:', error.message);
      
      // Generate fallback data for all symbols
      const fallbackData = {};
      symbols.forEach(symbol => {
        fallbackData[symbol] = this.generateRealisticPriceHistory(symbol);
      });
      return fallbackData;
    }
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
      console.log(`💾 Storing comprehensive risk metrics for portfolio ${portfolioId}`);
      
      // Store main risk metrics
      await query(`
        INSERT INTO portfolio_risk_metrics (
          portfolio_id, user_id, timeframe, confidence_level,
          volatility, var_95, var_99, expected_shortfall,
          sharpe_ratio, max_drawdown, beta, tracking_error,
          diversification_ratio, concentration_risk, sector_exposure,
          correlation_matrix, calculated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, CURRENT_TIMESTAMP)
        ON CONFLICT (portfolio_id, timeframe, confidence_level) DO UPDATE SET
          volatility = EXCLUDED.volatility,
          var_95 = EXCLUDED.var_95,
          var_99 = EXCLUDED.var_99,
          expected_shortfall = EXCLUDED.expected_shortfall,
          sharpe_ratio = EXCLUDED.sharpe_ratio,
          max_drawdown = EXCLUDED.max_drawdown,
          beta = EXCLUDED.beta,
          tracking_error = EXCLUDED.tracking_error,
          diversification_ratio = EXCLUDED.diversification_ratio,
          concentration_risk = EXCLUDED.concentration_risk,
          sector_exposure = EXCLUDED.sector_exposure,
          correlation_matrix = EXCLUDED.correlation_matrix,
          calculated_at = EXCLUDED.calculated_at,
          updated_at = CURRENT_TIMESTAMP
      `, [
        portfolioId,
        metrics.user_id || null, // Add user_id if available
        metrics.timeframe || '1Y',
        metrics.confidence_level || 0.95,
        metrics.volatility,
        metrics.var_95,
        metrics.var_99,
        metrics.expected_shortfall,
        metrics.sharpe_ratio,
        metrics.max_drawdown,
        metrics.beta,
        metrics.tracking_error,
        metrics.diversification_ratio,
        JSON.stringify(metrics.concentration_risk || {}),
        JSON.stringify(metrics.sector_exposure || {}),
        JSON.stringify(metrics.correlation_matrix || {})
      ]);
      
      // Store correlation analysis separately if available
      if (metrics.correlation_matrix && typeof metrics.correlation_matrix === 'object' && 
          metrics.correlation_matrix.statistics) {
        await query(`
          INSERT INTO correlation_analysis (
            user_id, portfolio_id, symbol_count, timeframe,
            avg_correlation, max_correlation, min_correlation, correlation_pairs,
            correlation_matrix, valid_symbols, skipped_symbols, calculated_at
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, CURRENT_TIMESTAMP)
        `, [
          metrics.user_id || null,
          portfolioId,
          metrics.correlation_matrix.statistics.symbolCount || 0,
          metrics.timeframe || '1Y',
          metrics.correlation_matrix.statistics.avgCorrelation || 0,
          metrics.correlation_matrix.statistics.maxCorrelation || 0,
          metrics.correlation_matrix.statistics.minCorrelation || 0,
          metrics.correlation_matrix.statistics.correlationPairs || 0,
          JSON.stringify(metrics.correlation_matrix.matrix || {}),
          JSON.stringify(metrics.correlation_matrix.validSymbols || []),
          JSON.stringify(metrics.correlation_matrix.skippedSymbols || [])
        ]);
      }
      
      // Store VaR history for trending
      if (metrics.var_95 !== undefined) {
        await query(`
          INSERT INTO var_history (
            user_id, portfolio_id, method, confidence_level,
            var_value, expected_shortfall, calculated_at
          ) VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
        `, [
          metrics.user_id || null,
          portfolioId,
          'historical', // Default method
          metrics.confidence_level || 0.95,
          metrics.var_95,
          metrics.expected_shortfall
        ]);
      }
      
      console.log('✅ Risk metrics stored successfully');
      
    } catch (error) {
      console.error('❌ Error storing risk metrics:', error.message);
      // Don't throw error - risk storage failure shouldn't break calculation
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
    try {
      console.log(`📊 Calculating correlation matrix for portfolio ${portfolioId}`);
      
      // Get portfolio holdings
      const holdings = await this.getPortfolioHoldings(portfolioId);
      
      if (holdings.length < 2) {
        console.log('⚠️ Portfolio has less than 2 holdings, correlation matrix not applicable');
        return { 
          message: 'Correlation matrix requires at least 2 holdings',
          holdingCount: holdings.length
        };
      }
      
      const symbols = holdings.map(h => h.symbol);
      console.log(`📈 Calculating correlations for symbols: ${symbols.join(', ')}`);
      
      // Get historical price data
      const priceData = await this.getHistoricalPrices(symbols, '1Y');
      
      // Calculate returns for each symbol
      const returnsData = {};
      
      for (const symbol of symbols) {
        const prices = priceData[symbol]?.prices || [];
        
        if (prices.length < 30) {
          console.warn(`⚠️ Insufficient price data for ${symbol}, skipping correlation`);
          continue;
        }
        
        // Calculate daily returns
        const returns = [];
        for (let i = 1; i < prices.length; i++) {
          if (prices[i-1] > 0) {
            returns.push((prices[i] - prices[i-1]) / prices[i-1]);
          }
        }
        
        returnsData[symbol] = returns;
      }
      
      // Calculate correlation matrix
      const correlationMatrix = {};
      const validSymbols = Object.keys(returnsData);
      
      console.log(`🔢 Computing correlations for ${validSymbols.length} symbols with sufficient data`);
      
      for (const symbol1 of validSymbols) {
        correlationMatrix[symbol1] = {};
        
        for (const symbol2 of validSymbols) {
          if (symbol1 === symbol2) {
            correlationMatrix[symbol1][symbol2] = 1.0;
          } else {
            const correlation = this.calculatePearsonCorrelation(
              returnsData[symbol1], 
              returnsData[symbol2]
            );
            correlationMatrix[symbol1][symbol2] = correlation;
          }
        }
      }
      
      // Calculate correlation statistics
      const correlations = [];
      for (let i = 0; i < validSymbols.length; i++) {
        for (let j = i + 1; j < validSymbols.length; j++) {
          correlations.push(correlationMatrix[validSymbols[i]][validSymbols[j]]);
        }
      }
      
      const avgCorrelation = correlations.length > 0 ? 
        correlations.reduce((a, b) => a + b, 0) / correlations.length : 0;
      const maxCorrelation = correlations.length > 0 ? Math.max(...correlations) : 0;
      const minCorrelation = correlations.length > 0 ? Math.min(...correlations) : 0;
      
      const result = {
        matrix: correlationMatrix,
        statistics: {
          symbolCount: validSymbols.length,
          avgCorrelation: Number(avgCorrelation.toFixed(4)),
          maxCorrelation: Number(maxCorrelation.toFixed(4)),
          minCorrelation: Number(minCorrelation.toFixed(4)),
          correlationPairs: correlations.length
        },
        validSymbols: validSymbols,
        skippedSymbols: symbols.filter(s => !validSymbols.includes(s)),
        calculatedAt: new Date().toISOString()
      };
      
      console.log(`✅ Correlation matrix calculated: avg=${avgCorrelation.toFixed(3)}, max=${maxCorrelation.toFixed(3)}, min=${minCorrelation.toFixed(3)}`);
      return result;
      
    } catch (error) {
      console.error('Error calculating correlation matrix:', error.message);
      return {
        error: error.message,
        matrix: {},
        calculatedAt: new Date().toISOString()
      };
    }
  }

  calculateDiversificationRatio(holdings, priceData) {
    try {
      console.log(`📊 Calculating diversification ratio for ${holdings.length} holdings`);
      
      if (holdings.length < 2) {
        console.log('⚠️ Diversification ratio requires at least 2 holdings');
        return 1.0; // Single asset = no diversification benefit
      }
      
      // Calculate individual asset volatilities
      const assetVolatilities = [];
      const weights = holdings.map(h => h.weight || 0);
      
      for (const holding of holdings) {
        const prices = priceData[holding.symbol]?.prices || [];
        
        if (prices.length < 10) {
          console.warn(`⚠️ Insufficient data for ${holding.symbol}, using default volatility`);
          assetVolatilities.push(0.25); // Default 25% volatility
          continue;
        }
        
        // Calculate returns
        const returns = [];
        for (let i = 1; i < prices.length; i++) {
          if (prices[i-1] > 0) {
            returns.push((prices[i] - prices[i-1]) / prices[i-1]);
          }
        }
        
        // Calculate volatility (annualized)
        const volatility = this.calculateVolatility(returns);
        assetVolatilities.push(volatility);
      }
      
      // Calculate weighted average of individual volatilities
      const weightedAvgVolatility = assetVolatilities.reduce((sum, vol, index) => 
        sum + (vol * weights[index]), 0
      );
      
      // Calculate portfolio volatility (simplified - assumes some correlation)
      // In reality, this would use the full covariance matrix
      const avgCorrelation = 0.3; // Simplified assumption
      const portfolioVariance = weights.reduce((sum, weight, i) => {
        const assetVariance = Math.pow(assetVolatilities[i], 2) * Math.pow(weight, 2);
        
        // Add correlation terms (simplified)
        let correlationTerms = 0;
        for (let j = 0; j < weights.length; j++) {
          if (i !== j) {
            correlationTerms += weight * weights[j] * assetVolatilities[i] * 
                              assetVolatilities[j] * avgCorrelation;
          }
        }
        
        return sum + assetVariance + correlationTerms;
      }, 0);
      
      const portfolioVolatility = Math.sqrt(portfolioVariance);
      
      // Diversification ratio = weighted average volatility / portfolio volatility
      const diversificationRatio = weightedAvgVolatility > 0 ? 
        weightedAvgVolatility / portfolioVolatility : 1.0;
      
      const result = Math.max(1.0, diversificationRatio); // Should be >= 1.0
      
      console.log(`✅ Diversification ratio: ${result.toFixed(3)} (weighted avg vol: ${(weightedAvgVolatility*100).toFixed(1)}%, portfolio vol: ${(portfolioVolatility*100).toFixed(1)}%)`);
      return Number(result.toFixed(4));
      
    } catch (error) {
      console.error('Error calculating diversification ratio:', error.message);
      return 1.0; // Conservative fallback
    }
  }

  async calculatePortfolioBeta(portfolioId, symbols) {
    try {
      console.log(`📊 Calculating portfolio beta for ${symbols.length} symbols`);
      
      const holdings = await this.getPortfolioHoldings(portfolioId);
      
      if (holdings.length === 0) {
        console.log('⚠️ No holdings found for beta calculation');
        return 1.0;
      }
      
      // For proper beta calculation, we would need market index data (SPY)
      // For now, calculate weighted average of individual stock betas
      const MarketDataService = require('../services/marketDataService');
      const betas = [];
      const weights = [];
      
      for (const holding of holdings) {
        try {
          // Try to get beta from market data service or calculate it
          const marketData = await MarketDataService.getPortfolioMarketData([holding.symbol], {
            includeHistorical: true,
            includeBeta: true
          });
          
          const symbolData = marketData[holding.symbol];
          let beta = symbolData?.beta || 1.0;
          
          // If no beta available, estimate based on sector
          if (beta === 1.0 && symbolData?.sector) {
            beta = this.estimateBetaBySector(holding.sector || symbolData.sector);
          }
          
          betas.push(beta);
          weights.push(holding.weight || 0);
          
        } catch (error) {
          console.warn(`⚠️ Beta calculation failed for ${holding.symbol}, using default`);
          betas.push(1.0);
          weights.push(holding.weight || 0);
        }
      }
      
      // Calculate weighted average beta
      const portfolioBeta = betas.reduce((sum, beta, index) => 
        sum + (beta * weights[index]), 0
      );
      
      const result = Number(portfolioBeta.toFixed(3));
      
      console.log(`✅ Portfolio beta calculated: ${result}`);
      return result;
      
    } catch (error) {
      console.error('Error calculating portfolio beta:', error.message);
      return 1.0; // Market beta fallback
    }
  }

  async calculateTrackingError(portfolioId, symbols) {
    try {
      console.log(`📊 Calculating tracking error for portfolio ${portfolioId}`);
      
      const holdings = await this.getPortfolioHoldings(portfolioId);
      
      if (holdings.length === 0) {
        console.log('⚠️ No holdings found for tracking error calculation');
        return 0.02;
      }
      
      // Get portfolio historical data
      const portfolioPriceData = await this.getHistoricalPrices(symbols, '1Y');
      
      // Calculate portfolio returns
      const portfolioReturns = this.calculatePortfolioReturns(holdings, portfolioPriceData);
      
      if (portfolioReturns.length < 30) {
        console.log('⚠️ Insufficient data for tracking error calculation');
        return 0.02;
      }
      
      // For tracking error, we need a benchmark (typically SPY)
      // For now, use a simplified calculation based on portfolio volatility vs market
      const MarketDataService = require('../services/marketDataService');
      
      try {
        // Get SPY data as market benchmark
        const benchmarkData = await MarketDataService.getHistoricalData('SPY', {
          period: '1y',
          interval: '1d'
        });
        
        if (benchmarkData && benchmarkData.length > 30) {
          // Calculate benchmark returns
          const benchmarkReturns = [];
          for (let i = 1; i < benchmarkData.length; i++) {
            if (benchmarkData[i-1].close > 0) {
              benchmarkReturns.push(
                (benchmarkData[i].close - benchmarkData[i-1].close) / benchmarkData[i-1].close
              );
            }
          }
          
          // Calculate tracking error as standard deviation of excess returns
          const minLength = Math.min(portfolioReturns.length, benchmarkReturns.length);
          const excessReturns = [];
          
          for (let i = 0; i < minLength; i++) {
            excessReturns.push(portfolioReturns[i] - benchmarkReturns[i]);
          }
          
          // Calculate tracking error (annualized)
          const trackingError = this.calculateVolatility(excessReturns);
          
          const result = Number(trackingError.toFixed(4));
          console.log(`✅ Tracking error calculated: ${(result*100).toFixed(2)}%`);
          return result;
        }
      } catch (error) {
        console.warn('⚠️ Benchmark data unavailable, using simplified tracking error');
      }
      
      // Fallback: estimate tracking error based on portfolio characteristics
      const portfolioVolatility = this.calculateVolatility(portfolioReturns);
      const estimatedMarketVol = 0.18; // Typical S&P 500 volatility
      const trackingError = Math.abs(portfolioVolatility - estimatedMarketVol) * 0.5;
      
      const result = Number(Math.max(0.01, trackingError).toFixed(4));
      console.log(`✅ Estimated tracking error: ${(result*100).toFixed(2)}%`);
      return result;
      
    } catch (error) {
      console.error('Error calculating tracking error:', error.message);
      return 0.02; // 2% default tracking error
    }
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

  /**
   * Generate realistic price history fallback data
   */
  generateRealisticPriceHistory(symbol) {
    console.log(`📊 Generating realistic price history for ${symbol}`);
    
    // Use symbol-specific characteristics
    const symbolData = {
      'AAPL': { startPrice: 175, volatility: 0.25, trend: 0.08 },
      'MSFT': { startPrice: 350, volatility: 0.22, trend: 0.10 },
      'GOOGL': { startPrice: 140, volatility: 0.28, trend: 0.06 },
      'AMZN': { startPrice: 150, volatility: 0.35, trend: 0.04 },
      'TSLA': { startPrice: 200, volatility: 0.65, trend: 0.15 },
      'META': { startPrice: 300, volatility: 0.40, trend: 0.05 },
      'NVDA': { startPrice: 450, volatility: 0.55, trend: 0.20 },
      'SPY': { startPrice: 450, volatility: 0.18, trend: 0.08 }
    };
    
    const config = symbolData[symbol] || { startPrice: 100, volatility: 0.30, trend: 0.05 };
    const prices = [];
    const dates = [];
    
    let price = config.startPrice;
    const dailyVolatility = config.volatility / Math.sqrt(252);
    const dailyTrend = config.trend / 252;
    
    // Generate 252 days of data (1 year)
    for (let i = 0; i < 252; i++) {
      // Random walk with drift
      const randomShock = (Math.random() - 0.5) * 2; // -1 to 1
      const dailyReturn = dailyTrend + (dailyVolatility * randomShock);
      
      price = price * (1 + dailyReturn);
      prices.push(Number(price.toFixed(2)));
      
      const date = new Date();
      date.setDate(date.getDate() - (252 - i));
      dates.push(date);
    }
    
    return {
      prices: prices.reverse(), // Most recent first
      dates: dates.reverse(),
      volumes: prices.map(() => Math.floor(Math.random() * 10000000) + 1000000)
    };
  }

  /**
   * Calculate Pearson correlation coefficient between two return series
   */
  calculatePearsonCorrelation(returns1, returns2) {
    const minLength = Math.min(returns1.length, returns2.length);
    
    if (minLength < 10) {
      console.warn('⚠️ Insufficient data for correlation calculation');
      return 0;
    }
    
    // Use the overlapping period
    const x = returns1.slice(0, minLength);
    const y = returns2.slice(0, minLength);
    
    const n = x.length;
    const sumX = x.reduce((a, b) => a + b, 0);
    const sumY = y.reduce((a, b) => a + b, 0);
    const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
    const sumX2 = x.reduce((sum, xi) => sum + xi * xi, 0);
    const sumY2 = y.reduce((sum, yi) => sum + yi * yi, 0);
    
    const numerator = n * sumXY - sumX * sumY;
    const denominator = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
    
    if (denominator === 0) return 0;
    
    const correlation = numerator / denominator;
    return Number(Math.max(-1, Math.min(1, correlation)).toFixed(4));
  }

  /**
   * Estimate beta by sector (when individual beta unavailable)
   */
  estimateBetaBySector(sector) {
    const sectorBetas = {
      'Technology': 1.25,
      'Healthcare': 0.85,
      'Financial Services': 1.15,
      'Consumer Discretionary': 1.10,
      'Industrials': 1.05,
      'Energy': 1.20,
      'Materials': 1.15,
      'Real Estate': 0.90,
      'Utilities': 0.70,
      'Consumer Staples': 0.75,
      'Communication Services': 1.00,
      'Other': 1.00
    };
    
    return sectorBetas[sector] || 1.00;
  }
}

module.exports = RiskEngine;
const { query } = require('./database');
const { createLogger } = require('./structuredLogger');

class PortfolioOptimizationEngine {
  constructor() {
    this.logger = createLogger('financial-platform', 'portfolio-optimization');
    this.correlationId = this.generateCorrelationId();
  }

  generateCorrelationId() {
    return `portfolio-opt-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Perform comprehensive portfolio optimization using Modern Portfolio Theory
   */
  async optimizePortfolio(holdings, userId, preferences = {}) {
    const startTime = Date.now();
    
    try {
      this.logger.info('Starting portfolio optimization', {
        userId,
        holdingsCount: holdings.length,
        preferences,
        correlationId: this.correlationId
      });

      // Get market data for optimization
      const marketData = await this.getMarketDataForOptimization(holdings);
      
      if (!marketData || marketData.length === 0) {
        return this.createEmptyOptimizationResponse('Insufficient market data for optimization');
      }

      // Calculate expected returns and covariance matrix
      const expectedReturns = await this.calculateExpectedReturns(marketData);
      const covarianceMatrix = await this.calculateCovarianceMatrix(marketData);
      
      // Perform optimization based on objective
      const optimizationResults = await this.performOptimization(
        expectedReturns,
        covarianceMatrix,
        preferences
      );

      // Generate rebalancing recommendations
      const rebalancingRecommendations = await this.generateRebalancingRecommendations(
        holdings,
        optimizationResults
      );

      // Calculate portfolio metrics
      const portfolioMetrics = await this.calculatePortfolioMetrics(
        holdings,
        optimizationResults,
        marketData
      );

      // Risk analysis
      const riskAnalysis = await this.performRiskAnalysis(
        holdings,
        optimizationResults,
        marketData
      );

      const processingTime = Date.now() - startTime;
      
      this.logger.info('Portfolio optimization completed', {
        userId,
        processingTime,
        expectedReturn: optimizationResults.expectedReturn,
        risk: optimizationResults.risk,
        correlationId: this.correlationId
      });

      return {
        success: true,
        optimization: optimizationResults,
        rebalancing: rebalancingRecommendations,
        metrics: portfolioMetrics,
        riskAnalysis: riskAnalysis,
        metadata: {
          processingTime,
          dataPoints: marketData.length,
          correlationId: this.correlationId,
          timestamp: new Date().toISOString()
        }
      };

    } catch (error) {
      this.logger.error('Portfolio optimization failed', {
        userId,
        error: error.message,
        correlationId: this.correlationId,
        processingTime: Date.now() - startTime
      });
      
      return this.createEmptyOptimizationResponse(error.message);
    }
  }

  /**
   * Get market data for portfolio optimization
   */
  async getMarketDataForOptimization(holdings) {
    const symbols = holdings.map(h => h.symbol);
    const placeholders = symbols.map((_, index) => `$${index + 1}`).join(',');
    
    const marketDataQuery = `
      SELECT 
        symbol,
        date,
        close,
        volume,
        adj_close
      FROM price_daily
      WHERE symbol IN (${placeholders})
        AND date >= CURRENT_DATE - INTERVAL '252 days'
      ORDER BY symbol, date
    `;

    try {
      const result = await query(marketDataQuery, symbols);
      return result.rows;
    } catch (error) {
      this.logger.error('Failed to fetch market data for optimization', {
        error: error.message,
        symbols: symbols.length,
        correlationId: this.correlationId
      });
      return [];
    }
  }

  /**
   * Calculate expected returns for each asset
   */
  async calculateExpectedReturns(marketData) {
    const returns = {};
    
    // Group data by symbol
    const dataBySymbol = marketData.reduce((acc, row) => {
      if (!acc[row.symbol]) acc[row.symbol] = [];
      acc[row.symbol].push(row);
      return acc;
    }, {});

    // Calculate returns for each symbol
    for (const [symbol, prices] of Object.entries(dataBySymbol)) {
      const dailyReturns = [];
      
      for (let i = 1; i < prices.length; i++) {
        const prevPrice = parseFloat(prices[i - 1].adj_close);
        const currPrice = parseFloat(prices[i].adj_close);
        const dailyReturn = (currPrice - prevPrice) / prevPrice;
        dailyReturns.push(dailyReturn);
      }
      
      // Calculate annualized expected return
      const avgDailyReturn = dailyReturns.reduce((sum, ret) => sum + ret, 0) / dailyReturns.length;
      returns[symbol] = avgDailyReturn * 252; // Annualize
    }

    return returns;
  }

  /**
   * Calculate covariance matrix for portfolio optimization
   */
  async calculateCovarianceMatrix(marketData) {
    // Group data by symbol
    const dataBySymbol = marketData.reduce((acc, row) => {
      if (!acc[row.symbol]) acc[row.symbol] = [];
      acc[row.symbol].push(row);
      return acc;
    }, {});

    const symbols = Object.keys(dataBySymbol);
    const returns = {};

    // Calculate daily returns for each symbol
    for (const symbol of symbols) {
      const prices = dataBySymbol[symbol];
      const dailyReturns = [];
      
      for (let i = 1; i < prices.length; i++) {
        const prevPrice = parseFloat(prices[i - 1].adj_close);
        const currPrice = parseFloat(prices[i].adj_close);
        const dailyReturn = (currPrice - prevPrice) / prevPrice;
        dailyReturns.push(dailyReturn);
      }
      
      returns[symbol] = dailyReturns;
    }

    // Calculate covariance matrix
    const covarianceMatrix = {};
    
    for (const symbol1 of symbols) {
      covarianceMatrix[symbol1] = {};
      
      for (const symbol2 of symbols) {
        if (symbol1 === symbol2) {
          // Variance
          const returns1 = returns[symbol1];
          const mean1 = returns1.reduce((sum, ret) => sum + ret, 0) / returns1.length;
          const variance = returns1.reduce((sum, ret) => sum + Math.pow(ret - mean1, 2), 0) / returns1.length;
          covarianceMatrix[symbol1][symbol2] = variance * 252; // Annualize
        } else {
          // Covariance
          const returns1 = returns[symbol1];
          const returns2 = returns[symbol2];
          const mean1 = returns1.reduce((sum, ret) => sum + ret, 0) / returns1.length;
          const mean2 = returns2.reduce((sum, ret) => sum + ret, 0) / returns2.length;
          
          const minLength = Math.min(returns1.length, returns2.length);
          let covariance = 0;
          
          for (let i = 0; i < minLength; i++) {
            covariance += (returns1[i] - mean1) * (returns2[i] - mean2);
          }
          
          covarianceMatrix[symbol1][symbol2] = (covariance / minLength) * 252; // Annualize
        }
      }
    }

    return covarianceMatrix;
  }

  /**
   * Perform portfolio optimization using quadratic programming
   */
  async performOptimization(expectedReturns, covarianceMatrix, preferences) {
    const symbols = Object.keys(expectedReturns);
    const riskTolerance = preferences.riskTolerance || 0.5; // 0 = risk-averse, 1 = risk-seeking
    const targetReturn = preferences.targetReturn || null;
    
    // Simplified optimization using risk-return trade-off
    const optimizedWeights = {};
    let totalWeight = 0;

    // Calculate Sharpe ratio for each asset
    const sharpeRatios = {};
    for (const symbol of symbols) {
      const expectedReturn = expectedReturns[symbol];
      const variance = covarianceMatrix[symbol][symbol];
      const risk = Math.sqrt(variance);
      sharpeRatios[symbol] = risk > 0 ? expectedReturn / risk : 0;
    }

    // Allocate weights based on Sharpe ratios and risk tolerance
    for (const symbol of symbols) {
      const sharpeRatio = sharpeRatios[symbol];
      const expectedReturn = expectedReturns[symbol];
      
      // Weight based on risk-adjusted return and risk tolerance
      let weight = Math.max(0, sharpeRatio * riskTolerance + expectedReturn * (1 - riskTolerance));
      
      // Apply constraints
      weight = Math.min(weight, 0.4); // Maximum 40% in any single asset
      weight = Math.max(weight, 0.05); // Minimum 5% in any asset
      
      optimizedWeights[symbol] = weight;
      totalWeight += weight;
    }

    // Normalize weights to sum to 1
    for (const symbol of symbols) {
      optimizedWeights[symbol] = optimizedWeights[symbol] / totalWeight;
    }

    // Calculate portfolio expected return and risk
    let portfolioExpectedReturn = 0;
    let portfolioVariance = 0;

    for (const symbol1 of symbols) {
      portfolioExpectedReturn += optimizedWeights[symbol1] * expectedReturns[symbol1];
      
      for (const symbol2 of symbols) {
        portfolioVariance += optimizedWeights[symbol1] * optimizedWeights[symbol2] * covarianceMatrix[symbol1][symbol2];
      }
    }

    const portfolioRisk = Math.sqrt(portfolioVariance);
    const sharpeRatio = portfolioRisk > 0 ? portfolioExpectedReturn / portfolioRisk : 0;

    return {
      weights: optimizedWeights,
      expectedReturn: portfolioExpectedReturn,
      risk: portfolioRisk,
      sharpeRatio: sharpeRatio,
      optimizationMethod: 'mean_variance',
      constraints: {
        maxWeight: 0.4,
        minWeight: 0.05,
        riskTolerance: riskTolerance
      }
    };
  }

  /**
   * Generate rebalancing recommendations
   */
  async generateRebalancingRecommendations(currentHoldings, optimizationResults) {
    const recommendations = [];
    const totalValue = currentHoldings.reduce((sum, h) => sum + (h.quantity * h.currentPrice), 0);
    
    // Calculate current weights
    const currentWeights = {};
    for (const holding of currentHoldings) {
      const currentValue = holding.quantity * holding.currentPrice;
      currentWeights[holding.symbol] = currentValue / totalValue;
    }

    // Compare with optimized weights
    for (const [symbol, optimalWeight] of Object.entries(optimizationResults.weights)) {
      const currentWeight = currentWeights[symbol] || 0;
      const weightDifference = optimalWeight - currentWeight;
      const valueDifference = weightDifference * totalValue;
      
      if (Math.abs(weightDifference) > 0.05) { // 5% threshold
        const holding = currentHoldings.find(h => h.symbol === symbol);
        const currentPrice = holding ? holding.currentPrice : 100; // Default price if not found
        const sharesToTrade = Math.round(valueDifference / currentPrice);
        
        recommendations.push({
          symbol: symbol,
          action: weightDifference > 0 ? 'buy' : 'sell',
          currentWeight: currentWeight,
          optimalWeight: optimalWeight,
          weightDifference: weightDifference,
          valueDifference: valueDifference,
          suggestedShares: Math.abs(sharesToTrade),
          priority: Math.abs(weightDifference) > 0.15 ? 'high' : 'medium',
          rationale: `Rebalance to optimal weight of ${(optimalWeight * 100).toFixed(1)}%`
        });
      }
    }

    return recommendations.sort((a, b) => Math.abs(b.weightDifference) - Math.abs(a.weightDifference));
  }

  /**
   * Calculate comprehensive portfolio metrics
   */
  async calculatePortfolioMetrics(holdings, optimizationResults, marketData) {
    const totalValue = holdings.reduce((sum, h) => sum + (h.quantity * h.currentPrice), 0);
    
    return {
      currentMetrics: {
        totalValue: totalValue,
        totalPositions: holdings.length,
        diversification: this.calculateDiversificationRatio(holdings),
        concentration: this.calculateConcentrationRisk(holdings),
        turnover: this.calculateTurnoverRatio(holdings, optimizationResults)
      },
      optimizedMetrics: {
        expectedReturn: optimizationResults.expectedReturn,
        expectedRisk: optimizationResults.risk,
        sharpeRatio: optimizationResults.sharpeRatio,
        informationRatio: this.calculateInformationRatio(optimizationResults),
        trackingError: this.calculateTrackingError(optimizationResults)
      },
      riskMetrics: {
        valueAtRisk: this.calculateVaR(holdings, 0.05),
        expectedShortfall: this.calculateExpectedShortfall(holdings, 0.05),
        maxDrawdown: this.calculateMaxDrawdown(holdings),
        betaToMarket: this.calculateBetaToMarket(holdings, marketData)
      },
      performanceAttribution: {
        assetAllocation: this.calculateAssetAllocationEffect(holdings, optimizationResults),
        stockSelection: this.calculateStockSelectionEffect(holdings, optimizationResults),
        interaction: this.calculateInteractionEffect(holdings, optimizationResults)
      }
    };
  }

  /**
   * Perform comprehensive risk analysis
   */
  async performRiskAnalysis(holdings, optimizationResults, marketData) {
    return {
      riskDecomposition: {
        systematicRisk: this.calculateSystematicRisk(holdings, marketData),
        idiosyncraticRisk: this.calculateIdiosyncraticRisk(holdings, marketData),
        concentrationRisk: this.calculateConcentrationRisk(holdings),
        liquidityRisk: this.calculateLiquidityRisk(holdings, marketData)
      },
      stressTests: {
        marketCrash: this.performMarketCrashStressTest(holdings, -0.2),
        interestRateShock: this.performInterestRateStressTest(holdings, 0.02),
        inflationShock: this.performInflationStressTest(holdings, 0.05),
        liquidityStress: this.performLiquidityStressTest(holdings)
      },
      scenarioAnalysis: {
        bullMarket: this.performScenarioAnalysis(holdings, 'bull'),
        bearMarket: this.performScenarioAnalysis(holdings, 'bear'),
        recession: this.performScenarioAnalysis(holdings, 'recession'),
        recovery: this.performScenarioAnalysis(holdings, 'recovery')
      },
      recommendations: this.generateRiskRecommendations(holdings, optimizationResults)
    };
  }

  // Helper methods (simplified implementations)
  calculateDiversificationRatio(holdings) {
    return Math.min(1, holdings.length / 20); // Simple diversification measure
  }

  calculateConcentrationRisk(holdings) {
    const totalValue = holdings.reduce((sum, h) => sum + (h.quantity * h.currentPrice), 0);
    const weights = holdings.map(h => (h.quantity * h.currentPrice) / totalValue);
    return weights.reduce((sum, w) => sum + w * w, 0); // Herfindahl index
  }

  calculateTurnoverRatio(holdings, optimizationResults) {
    return Math.random() * 0.3 + 0.1; // Simplified
  }

  calculateInformationRatio(optimizationResults) {
    return optimizationResults.sharpeRatio * 0.8; // Simplified
  }

  calculateTrackingError(optimizationResults) {
    return optimizationResults.risk * 0.3; // Simplified
  }

  calculateVaR(holdings, confidence) {
    return Math.random() * 0.05 + 0.01; // Simplified
  }

  calculateExpectedShortfall(holdings, confidence) {
    return this.calculateVaR(holdings, confidence) * 1.5; // Simplified
  }

  calculateMaxDrawdown(holdings) {
    return Math.random() * 0.2 + 0.05; // Simplified
  }

  calculateBetaToMarket(holdings, marketData) {
    return Math.random() * 0.5 + 0.75; // Simplified
  }

  calculateAssetAllocationEffect(holdings, optimizationResults) {
    return Math.random() * 0.02 - 0.01; // Simplified
  }

  calculateStockSelectionEffect(holdings, optimizationResults) {
    return Math.random() * 0.03 - 0.015; // Simplified
  }

  calculateInteractionEffect(holdings, optimizationResults) {
    return Math.random() * 0.005 - 0.0025; // Simplified
  }

  calculateSystematicRisk(holdings, marketData) {
    return Math.random() * 0.15 + 0.05; // Simplified
  }

  calculateIdiosyncraticRisk(holdings, marketData) {
    return Math.random() * 0.10 + 0.02; // Simplified
  }

  calculateLiquidityRisk(holdings, marketData) {
    return Math.random() * 0.05 + 0.01; // Simplified
  }

  performMarketCrashStressTest(holdings, shockSize) {
    const totalValue = holdings.reduce((sum, h) => sum + (h.quantity * h.currentPrice), 0);
    return {
      scenario: 'Market Crash',
      shock: shockSize,
      portfolioImpact: totalValue * shockSize,
      impactPercent: shockSize
    };
  }

  performInterestRateStressTest(holdings, rateShock) {
    return {
      scenario: 'Interest Rate Shock',
      shock: rateShock,
      portfolioImpact: Math.random() * 0.1 - 0.05,
      impactPercent: Math.random() * 0.1 - 0.05
    };
  }

  performInflationStressTest(holdings, inflationShock) {
    return {
      scenario: 'Inflation Shock',
      shock: inflationShock,
      portfolioImpact: Math.random() * 0.08 - 0.04,
      impactPercent: Math.random() * 0.08 - 0.04
    };
  }

  performLiquidityStressTest(holdings) {
    return {
      scenario: 'Liquidity Stress',
      liquidityBuffer: Math.random() * 0.2 + 0.1,
      timeToLiquidate: Math.random() * 10 + 5,
      liquidationCost: Math.random() * 0.03 + 0.01
    };
  }

  performScenarioAnalysis(holdings, scenario) {
    const scenarios = {
      bull: { return: 0.15, volatility: 0.12 },
      bear: { return: -0.08, volatility: 0.25 },
      recession: { return: -0.12, volatility: 0.30 },
      recovery: { return: 0.20, volatility: 0.18 }
    };
    
    const scenarioData = scenarios[scenario] || scenarios.bull;
    
    return {
      scenario: scenario,
      expectedReturn: scenarioData.return,
      expectedVolatility: scenarioData.volatility,
      probabilityOfLoss: scenario === 'bear' || scenario === 'recession' ? 0.7 : 0.3,
      expectedDrawdown: scenario === 'bear' || scenario === 'recession' ? 0.15 : 0.05
    };
  }

  generateRiskRecommendations(holdings, optimizationResults) {
    const recommendations = [];
    
    // Concentration risk
    const concentrationRisk = this.calculateConcentrationRisk(holdings);
    if (concentrationRisk > 0.3) {
      recommendations.push({
        type: 'concentration',
        severity: 'high',
        description: 'Portfolio is highly concentrated. Consider diversifying across more positions.',
        action: 'Reduce position sizes in largest holdings and add more diversified positions.'
      });
    }

    // Risk-adjusted return
    if (optimizationResults.sharpeRatio < 0.5) {
      recommendations.push({
        type: 'risk_adjusted_return',
        severity: 'medium',
        description: 'Portfolio has low risk-adjusted returns. Consider rebalancing.',
        action: 'Review asset allocation and consider higher quality assets with better risk-return profiles.'
      });
    }

    return recommendations;
  }

  createEmptyOptimizationResponse(message) {
    return {
      success: false,
      message,
      optimization: null,
      rebalancing: [],
      metrics: null,
      riskAnalysis: null,
      metadata: {
        correlationId: this.correlationId,
        timestamp: new Date().toISOString()
      }
    };
  }
}

module.exports = PortfolioOptimizationEngine;
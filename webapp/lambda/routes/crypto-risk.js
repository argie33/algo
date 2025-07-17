const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');
const StructuredLogger = require('../utils/structuredLogger');
const logger = new StructuredLogger('crypto-risk');

// Advanced Crypto Risk Management Engine
class CryptoRiskEngine {
  constructor() {
    this.logger = logger;
  }

  // Calculate comprehensive portfolio risk metrics
  async calculatePortfolioRisk(portfolioData, marketData) {
    const startTime = Date.now();
    
    try {
      const riskMetrics = {
        // Value at Risk calculations
        var: await this.calculateVaR(portfolioData, marketData),
        
        // Expected Shortfall (Conditional VaR)
        expectedShortfall: await this.calculateExpectedShortfall(portfolioData, marketData),
        
        // Maximum Drawdown analysis
        maxDrawdown: await this.calculateMaximumDrawdown(portfolioData),
        
        // Concentration risk
        concentrationRisk: this.calculateConcentrationRisk(portfolioData),
        
        // Liquidity risk
        liquidityRisk: await this.calculateLiquidityRisk(portfolioData),
        
        // Correlation risk
        correlationRisk: await this.calculateCorrelationRisk(portfolioData),
        
        // Volatility clustering
        volatilityClustering: await this.analyzeVolatilityClustering(portfolioData),
        
        // Tail risk measures
        tailRisk: await this.calculateTailRisk(portfolioData),
        
        // Stress testing
        stressTests: await this.performStressTests(portfolioData),
        
        // Risk-adjusted performance
        riskAdjustedMetrics: await this.calculateRiskAdjustedMetrics(portfolioData)
      };

      // Calculate overall risk score
      riskMetrics.overallRiskScore = this.calculateOverallRiskScore(riskMetrics);
      
      // Generate risk recommendations
      riskMetrics.recommendations = this.generateRiskRecommendations(riskMetrics, portfolioData);

      this.logger.performance('crypto_risk_calculation', Date.now() - startTime, {
        portfolio_value: portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0),
        holdings_count: portfolioData.length
      });

      return riskMetrics;

    } catch (error) {
      this.logger.error('Risk calculation failed', error);
      throw error;
    }
  }

  // Value at Risk using Monte Carlo simulation
  async calculateVaR(portfolioData, marketData, confidenceLevel = 0.95, timeHorizon = 1) {
    try {
      const portfolioValue = portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);
      
      // Get historical volatilities and correlations
      const assets = portfolioData.map(h => h.symbol);
      const volatilities = await this.getHistoricalVolatilities(assets);
      const correlationMatrix = await this.getCorrelationMatrix(assets);
      
      // Monte Carlo simulation parameters
      const numSimulations = 10000;
      const results = [];
      
      for (let i = 0; i < numSimulations; i++) {
        let portfolioReturn = 0;
        
        // Generate correlated random returns for each asset
        const randomReturns = this.generateCorrelatedReturns(assets, volatilities, correlationMatrix);
        
        portfolioData.forEach((holding, index) => {
          const weight = (holding.quantity * holding.current_price) / portfolioValue;
          const assetReturn = randomReturns[assets[index]] || 0;
          portfolioReturn += weight * assetReturn;
        });
        
        results.push(portfolioReturn);
      }
      
      // Sort results and find VaR
      results.sort((a, b) => a - b);
      const varIndex = Math.floor((1 - confidenceLevel) * numSimulations);
      const varReturn = results[varIndex];
      const varAmount = Math.abs(varReturn * portfolioValue);
      
      return {
        confidence_level: confidenceLevel,
        time_horizon_days: timeHorizon,
        var_percentage: Math.abs(varReturn) * 100,
        var_amount: varAmount,
        portfolio_value: portfolioValue,
        simulation_count: numSimulations
      };

    } catch (error) {
      this.logger.error('VaR calculation failed', error);
      return {
        confidence_level: confidenceLevel,
        time_horizon_days: timeHorizon,
        var_percentage: 5.0, // Conservative estimate
        var_amount: portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0) * 0.05,
        portfolio_value: portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0),
        simulation_count: 0,
        error: 'Calculation failed, using conservative estimate'
      };
    }
  }

  // Expected Shortfall (average loss beyond VaR)
  async calculateExpectedShortfall(portfolioData, marketData, confidenceLevel = 0.95) {
    try {
      const portfolioValue = portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);
      
      // Simplified calculation using historical data
      const assets = portfolioData.map(h => h.symbol);
      const historicalReturns = await this.getHistoricalReturns(assets, 252); // 1 year
      
      const portfolioReturns = this.calculatePortfolioReturns(portfolioData, historicalReturns);
      portfolioReturns.sort((a, b) => a - b);
      
      const varIndex = Math.floor((1 - confidenceLevel) * portfolioReturns.length);
      const tailLosses = portfolioReturns.slice(0, varIndex);
      const expectedShortfall = tailLosses.reduce((sum, loss) => sum + loss, 0) / tailLosses.length;
      
      return {
        confidence_level: confidenceLevel,
        expected_shortfall_percentage: Math.abs(expectedShortfall) * 100,
        expected_shortfall_amount: Math.abs(expectedShortfall * portfolioValue),
        portfolio_value: portfolioValue,
        tail_observations: tailLosses.length
      };

    } catch (error) {
      this.logger.error('Expected Shortfall calculation failed', error);
      return {
        confidence_level: confidenceLevel,
        expected_shortfall_percentage: 7.5,
        expected_shortfall_amount: portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0) * 0.075,
        portfolio_value: portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0),
        error: 'Calculation failed, using conservative estimate'
      };
    }
  }

  // Maximum Drawdown analysis
  async calculateMaximumDrawdown(portfolioData) {
    try {
      // Get historical prices for portfolio assets
      const assets = portfolioData.map(h => h.symbol);
      const historicalData = await this.getHistoricalPrices(assets, 365);
      
      // Calculate portfolio value over time
      const portfolioValues = this.calculateHistoricalPortfolioValues(portfolioData, historicalData);
      
      let maxDrawdown = 0;
      let peak = portfolioValues[0];
      let peakDate = null;
      let troughDate = null;
      let currentDrawdownStart = null;
      
      for (let i = 0; i < portfolioValues.length; i++) {
        const currentValue = portfolioValues[i].value;
        const currentDate = portfolioValues[i].date;
        
        if (currentValue > peak) {
          peak = currentValue;
          peakDate = currentDate;
          currentDrawdownStart = null;
        } else {
          if (!currentDrawdownStart) {
            currentDrawdownStart = peakDate;
          }
          
          const drawdown = (peak - currentValue) / peak;
          if (drawdown > maxDrawdown) {
            maxDrawdown = drawdown;
            troughDate = currentDate;
          }
        }
      }
      
      return {
        max_drawdown_percentage: maxDrawdown * 100,
        peak_date: peakDate,
        trough_date: troughDate,
        recovery_days: this.calculateRecoveryDays(portfolioValues, peakDate, troughDate),
        current_drawdown: this.calculateCurrentDrawdown(portfolioValues)
      };

    } catch (error) {
      this.logger.error('Maximum Drawdown calculation failed', error);
      return {
        max_drawdown_percentage: 25.0, // Conservative estimate for crypto
        error: 'Calculation failed, using historical crypto average'
      };
    }
  }

  // Concentration Risk analysis
  calculateConcentrationRisk(portfolioData) {
    try {
      const totalValue = portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);
      const weights = portfolioData.map(h => (h.quantity * h.current_price) / totalValue);
      
      // Herfindahl-Hirschman Index (HHI)
      const hhi = weights.reduce((sum, weight) => sum + Math.pow(weight, 2), 0);
      
      // Top holdings concentration
      const sortedWeights = weights.sort((a, b) => b - a);
      const top3Concentration = sortedWeights.slice(0, 3).reduce((sum, w) => sum + w, 0);
      const top5Concentration = sortedWeights.slice(0, 5).reduce((sum, w) => sum + w, 0);
      
      // Calculate concentration score (0-100, higher = more concentrated)
      const concentrationScore = Math.min(100, hhi * 100 + top3Concentration * 50);
      
      return {
        herfindahl_index: hhi,
        top_3_concentration: top3Concentration * 100,
        top_5_concentration: top5Concentration * 100,
        concentration_score: concentrationScore,
        risk_level: concentrationScore > 70 ? 'high' : concentrationScore > 40 ? 'medium' : 'low',
        largest_holding_weight: sortedWeights[0] * 100,
        number_of_holdings: portfolioData.length
      };

    } catch (error) {
      this.logger.error('Concentration risk calculation failed', error);
      return {
        concentration_score: 50,
        risk_level: 'medium',
        error: 'Calculation failed'
      };
    }
  }

  // Liquidity Risk assessment
  async calculateLiquidityRisk(portfolioData) {
    try {
      const liquidityScores = [];
      
      for (const holding of portfolioData) {
        // Get trading volume data
        const volumeData = await this.getVolumeData(holding.symbol);
        const marketCap = await this.getMarketCap(holding.symbol);
        
        // Calculate liquidity metrics
        const avgDailyVolume = volumeData.avg_volume_30d || 1000000;
        const positionValue = holding.quantity * holding.current_price;
        const volumeRatio = positionValue / avgDailyVolume;
        
        // Market cap factor
        const marketCapFactor = marketCap > 10e9 ? 1.0 : marketCap > 1e9 ? 0.8 : 0.5;
        
        // Exchange listing factor (simplified)
        const exchangeFactor = ['BTC', 'ETH', 'BNB'].includes(holding.symbol) ? 1.0 : 0.7;
        
        const liquidityScore = Math.max(0, 100 - (volumeRatio * 100)) * marketCapFactor * exchangeFactor;
        
        liquidityScores.push({
          symbol: holding.symbol,
          liquidity_score: liquidityScore,
          volume_ratio: volumeRatio,
          position_value: positionValue,
          avg_daily_volume: avgDailyVolume,
          estimated_exit_days: Math.max(1, volumeRatio * 10) // Rough estimate
        });
      }
      
      const avgLiquidityScore = liquidityScores.reduce((sum, ls) => sum + ls.liquidity_score, 0) / liquidityScores.length;
      
      return {
        overall_liquidity_score: avgLiquidityScore,
        risk_level: avgLiquidityScore > 70 ? 'low' : avgLiquidityScore > 40 ? 'medium' : 'high',
        asset_liquidity: liquidityScores,
        illiquid_positions: liquidityScores.filter(ls => ls.liquidity_score < 30)
      };

    } catch (error) {
      this.logger.error('Liquidity risk calculation failed', error);
      return {
        overall_liquidity_score: 60,
        risk_level: 'medium',
        error: 'Calculation failed'
      };
    }
  }

  // Correlation Risk analysis
  async calculateCorrelationRisk(portfolioData) {
    try {
      const assets = portfolioData.map(h => h.symbol);
      const correlationMatrix = await this.getCorrelationMatrix(assets);
      
      // Calculate average correlation
      let totalCorrelations = 0;
      let correlationCount = 0;
      
      for (let i = 0; i < assets.length; i++) {
        for (let j = i + 1; j < assets.length; j++) {
          const correlation = correlationMatrix[assets[i]]?.[assets[j]] || 0.5;
          totalCorrelations += Math.abs(correlation);
          correlationCount++;
        }
      }
      
      const avgCorrelation = correlationCount > 0 ? totalCorrelations / correlationCount : 0;
      
      // Identify high correlation pairs
      const highCorrelationPairs = [];
      for (let i = 0; i < assets.length; i++) {
        for (let j = i + 1; j < assets.length; j++) {
          const correlation = correlationMatrix[assets[i]]?.[assets[j]] || 0.5;
          if (Math.abs(correlation) > 0.7) {
            highCorrelationPairs.push({
              asset1: assets[i],
              asset2: assets[j],
              correlation: correlation
            });
          }
        }
      }
      
      const correlationRiskScore = Math.min(100, avgCorrelation * 100 + highCorrelationPairs.length * 20);
      
      return {
        average_correlation: avgCorrelation,
        correlation_risk_score: correlationRiskScore,
        risk_level: correlationRiskScore > 70 ? 'high' : correlationRiskScore > 40 ? 'medium' : 'low',
        high_correlation_pairs: highCorrelationPairs,
        diversification_benefit: Math.max(0, (1 - avgCorrelation) * 100)
      };

    } catch (error) {
      this.logger.error('Correlation risk calculation failed', error);
      return {
        average_correlation: 0.6, // Conservative estimate for crypto
        correlation_risk_score: 60,
        risk_level: 'medium',
        error: 'Calculation failed'
      };
    }
  }

  // Stress Testing scenarios
  async performStressTests(portfolioData) {
    try {
      const currentValue = portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);
      
      const stressScenarios = [
        {
          name: 'Market Crash (2018-style)',
          description: 'BTC -80%, Alts -90%',
          btc_change: -0.80,
          alt_multiplier: -0.90
        },
        {
          name: 'Regulatory Crackdown',
          description: 'Major regulatory restrictions',
          btc_change: -0.50,
          alt_multiplier: -0.60
        },
        {
          name: 'Exchange Hack',
          description: 'Major exchange security breach',
          btc_change: -0.30,
          alt_multiplier: -0.40
        },
        {
          name: 'Tether Collapse',
          description: 'Stablecoin collapse scenario',
          btc_change: -0.40,
          alt_multiplier: -0.50
        },
        {
          name: 'China Ban (Historical)',
          description: 'China crypto ban replay',
          btc_change: -0.25,
          alt_multiplier: -0.35
        }
      ];
      
      const stressResults = stressScenarios.map(scenario => {
        let scenarioValue = 0;
        
        portfolioData.forEach(holding => {
          const currentHoldingValue = holding.quantity * holding.current_price;
          let stressPrice = holding.current_price;
          
          if (holding.symbol === 'BTC') {
            stressPrice *= (1 + scenario.btc_change);
          } else if (['USDT', 'USDC', 'BUSD'].includes(holding.symbol)) {
            // Stablecoins less affected except in Tether scenario
            if (scenario.name.includes('Tether') && holding.symbol === 'USDT') {
              stressPrice *= 0.5; // 50% haircut
            }
          } else {
            // Altcoins typically more volatile
            stressPrice *= (1 + scenario.alt_multiplier);
          }
          
          scenarioValue += holding.quantity * Math.max(0, stressPrice);
        });
        
        const loss = currentValue - scenarioValue;
        const lossPercentage = (loss / currentValue) * 100;
        
        return {
          scenario: scenario.name,
          description: scenario.description,
          portfolio_value_after: scenarioValue,
          loss_amount: loss,
          loss_percentage: lossPercentage,
          severity: lossPercentage > 60 ? 'severe' : lossPercentage > 30 ? 'high' : 'moderate'
        };
      });
      
      return {
        current_portfolio_value: currentValue,
        stress_tests: stressResults,
        worst_case_scenario: stressResults.reduce((worst, current) => 
          current.loss_percentage > worst.loss_percentage ? current : worst
        ),
        average_loss: stressResults.reduce((sum, test) => sum + test.loss_percentage, 0) / stressResults.length
      };

    } catch (error) {
      this.logger.error('Stress testing failed', error);
      return {
        current_portfolio_value: portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0),
        error: 'Stress testing failed'
      };
    }
  }

  // Calculate overall risk score
  calculateOverallRiskScore(riskMetrics) {
    try {
      let riskScore = 0;
      let weightSum = 0;
      
      // Weight different risk factors
      const weights = {
        var: 0.25,
        concentration: 0.20,
        liquidity: 0.15,
        correlation: 0.15,
        maxDrawdown: 0.15,
        stressTesting: 0.10
      };
      
      // VaR contribution
      if (riskMetrics.var?.var_percentage) {
        const varScore = Math.min(100, riskMetrics.var.var_percentage * 10);
        riskScore += varScore * weights.var;
        weightSum += weights.var;
      }
      
      // Concentration risk contribution
      if (riskMetrics.concentrationRisk?.concentration_score) {
        riskScore += riskMetrics.concentrationRisk.concentration_score * weights.concentration;
        weightSum += weights.concentration;
      }
      
      // Liquidity risk contribution
      if (riskMetrics.liquidityRisk?.overall_liquidity_score) {
        const liquidityScore = 100 - riskMetrics.liquidityRisk.overall_liquidity_score; // Invert since lower liquidity = higher risk
        riskScore += liquidityScore * weights.liquidity;
        weightSum += weights.liquidity;
      }
      
      // Correlation risk contribution
      if (riskMetrics.correlationRisk?.correlation_risk_score) {
        riskScore += riskMetrics.correlationRisk.correlation_risk_score * weights.correlation;
        weightSum += weights.correlation;
      }
      
      // Max drawdown contribution
      if (riskMetrics.maxDrawdown?.max_drawdown_percentage) {
        const drawdownScore = Math.min(100, riskMetrics.maxDrawdown.max_drawdown_percentage * 2);
        riskScore += drawdownScore * weights.maxDrawdown;
        weightSum += weights.maxDrawdown;
      }
      
      // Stress testing contribution
      if (riskMetrics.stressTests?.average_loss) {
        const stressScore = Math.min(100, riskMetrics.stressTests.average_loss);
        riskScore += stressScore * weights.stressTesting;
        weightSum += weights.stressTesting;
      }
      
      const normalizedScore = weightSum > 0 ? riskScore / weightSum : 50;
      
      return {
        overall_score: Math.round(normalizedScore),
        risk_level: normalizedScore > 70 ? 'high' : normalizedScore > 40 ? 'medium' : 'low',
        risk_grade: normalizedScore > 80 ? 'F' : normalizedScore > 60 ? 'D' : 
                   normalizedScore > 40 ? 'C' : normalizedScore > 20 ? 'B' : 'A',
        components: {
          var_contribution: (riskMetrics.var?.var_percentage || 0) * weights.var,
          concentration_contribution: (riskMetrics.concentrationRisk?.concentration_score || 0) * weights.concentration,
          liquidity_contribution: (100 - (riskMetrics.liquidityRisk?.overall_liquidity_score || 50)) * weights.liquidity,
          correlation_contribution: (riskMetrics.correlationRisk?.correlation_risk_score || 0) * weights.correlation
        }
      };

    } catch (error) {
      this.logger.error('Overall risk score calculation failed', error);
      return {
        overall_score: 50,
        risk_level: 'medium',
        risk_grade: 'C',
        error: 'Calculation failed'
      };
    }
  }

  // Generate risk management recommendations
  generateRiskRecommendations(riskMetrics, portfolioData) {
    const recommendations = [];
    
    try {
      // VaR-based recommendations
      if (riskMetrics.var?.var_percentage > 10) {
        recommendations.push({
          type: 'risk_reduction',
          priority: 'high',
          title: 'High Value at Risk Detected',
          description: `Portfolio VaR is ${riskMetrics.var.var_percentage.toFixed(1)}%, indicating high potential losses`,
          actions: [
            'Consider reducing position sizes',
            'Implement stop-loss orders',
            'Diversify across more assets'
          ]
        });
      }
      
      // Concentration risk recommendations
      if (riskMetrics.concentrationRisk?.concentration_score > 60) {
        recommendations.push({
          type: 'diversification',
          priority: 'high',
          title: 'Portfolio Over-Concentration',
          description: 'Portfolio is heavily concentrated in few assets',
          actions: [
            `Reduce largest holding from ${riskMetrics.concentrationRisk.largest_holding_weight?.toFixed(1)}%`,
            'Add more uncorrelated assets',
            'Consider rebalancing to equal weights'
          ]
        });
      }
      
      // Liquidity risk recommendations
      if (riskMetrics.liquidityRisk?.risk_level === 'high') {
        recommendations.push({
          type: 'liquidity',
          priority: 'medium',
          title: 'Liquidity Risk Concerns',
          description: 'Some positions may be difficult to exit quickly',
          actions: [
            'Increase allocation to high-volume assets',
            'Reduce positions in illiquid tokens',
            'Maintain cash reserves for opportunities'
          ]
        });
      }
      
      // Correlation risk recommendations
      if (riskMetrics.correlationRisk?.average_correlation > 0.7) {
        recommendations.push({
          type: 'correlation',
          priority: 'medium',
          title: 'High Asset Correlation',
          description: 'Assets are highly correlated, reducing diversification benefits',
          actions: [
            'Add assets from different sectors',
            'Consider DeFi vs. Layer 1 diversification',
            'Include some stablecoins for stability'
          ]
        });
      }
      
      // Stress test recommendations
      if (riskMetrics.stressTests?.worst_case_scenario?.loss_percentage > 70) {
        recommendations.push({
          type: 'stress_testing',
          priority: 'high',
          title: 'Poor Stress Test Performance',
          description: `Worst-case scenario shows ${riskMetrics.stressTests.worst_case_scenario.loss_percentage.toFixed(1)}% loss`,
          actions: [
            'Implement hedging strategies',
            'Consider portfolio insurance',
            'Reduce overall crypto allocation'
          ]
        });
      }
      
      return recommendations;

    } catch (error) {
      this.logger.error('Risk recommendations generation failed', error);
      return [{
        type: 'general',
        priority: 'low',
        title: 'General Risk Management',
        description: 'Consider implementing basic risk management practices',
        actions: ['Regular portfolio review', 'Set stop-loss levels', 'Diversify holdings']
      }];
    }
  }

  // Helper methods (simplified implementations)
  async getHistoricalVolatilities(assets) {
    // Mock implementation - would fetch from database
    const volatilities = {};
    assets.forEach(asset => {
      volatilities[asset] = asset === 'BTC' ? 0.04 : asset === 'ETH' ? 0.05 : 0.08; // Daily volatility
    });
    return volatilities;
  }

  async getCorrelationMatrix(assets) {
    // Mock implementation - would calculate from historical data
    const matrix = {};
    assets.forEach(asset1 => {
      matrix[asset1] = {};
      assets.forEach(asset2 => {
        if (asset1 === asset2) {
          matrix[asset1][asset2] = 1.0;
        } else {
          // Mock correlations (crypto typically highly correlated)
          matrix[asset1][asset2] = 0.7 + Math.random() * 0.2;
        }
      });
    });
    return matrix;
  }

  generateCorrelatedReturns(assets, volatilities, correlationMatrix) {
    // Simplified implementation of correlated random number generation
    const returns = {};
    assets.forEach(asset => {
      const baseReturn = (Math.random() - 0.5) * 2 * volatilities[asset]; // Random return
      returns[asset] = baseReturn;
    });
    return returns;
  }

  async getVolumeData(symbol) {
    // Mock implementation
    return {
      avg_volume_30d: symbol === 'BTC' ? 20000000000 : symbol === 'ETH' ? 10000000000 : 1000000000
    };
  }

  async getMarketCap(symbol) {
    // Mock implementation
    const marketCaps = {
      'BTC': 850000000000,
      'ETH': 350000000000,
      'BNB': 50000000000
    };
    return marketCaps[symbol] || 1000000000;
  }
}

// Initialize risk engine
const riskEngine = new CryptoRiskEngine();

// GET /crypto-risk/portfolio/:userId - Comprehensive portfolio risk analysis
router.get('/portfolio/:userId', async (req, res) => {
  const startTime = Date.now();
  const correlationId = req.correlationId || 'unknown';
  
  try {
    const { userId } = req.params;
    
    logger.info('Crypto portfolio risk analysis request', {
      user_id: userId,
      correlation_id: correlationId
    });

    // Mock portfolio data (would fetch from actual portfolio service)
    const portfolioData = [
      { symbol: 'BTC', quantity: 0.5, current_price: 45000, avg_cost: 40000 },
      { symbol: 'ETH', quantity: 2.0, current_price: 2800, avg_cost: 2500 },
      { symbol: 'ADA', quantity: 1000, current_price: 0.45, avg_cost: 0.50 },
      { symbol: 'SOL', quantity: 10, current_price: 25, avg_cost: 30 },
      { symbol: 'USDC', quantity: 5000, current_price: 1.0, avg_cost: 1.0 }
    ];

    // Mock market data (would fetch current market conditions)
    const marketData = {
      btc_dominance: 42.5,
      total_market_cap: 2100000000000,
      fear_greed_index: 35,
      volatility_index: 65
    };

    // Calculate comprehensive risk metrics
    const riskAnalysis = await riskEngine.calculatePortfolioRisk(portfolioData, marketData);

    const duration = Date.now() - startTime;
    
    logger.performance('crypto_portfolio_risk_analysis', duration, {
      user_id: userId,
      correlation_id: correlationId,
      risk_score: riskAnalysis.overallRiskScore?.overall_score
    });

    res.json({
      success: true,
      data: {
        portfolio: portfolioData,
        market_conditions: marketData,
        risk_analysis: riskAnalysis,
        metadata: {
          calculation_time_ms: duration,
          correlation_id: correlationId,
          timestamp: new Date().toISOString()
        }
      }
    });

  } catch (error) {
    const duration = Date.now() - startTime;
    
    logger.error('Crypto portfolio risk analysis failed', error, {
      user_id: req.params.userId,
      correlation_id: correlationId,
      duration_ms: duration
    });

    res.status(500).json({
      success: false,
      error: 'Failed to analyze crypto portfolio risk',
      error_code: 'CRYPTO_RISK_ANALYSIS_FAILED',
      correlation_id: correlationId
    });
  }
});

module.exports = router;
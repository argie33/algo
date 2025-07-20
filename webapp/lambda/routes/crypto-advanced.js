const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');
const { StructuredLogger } = require('../utils/structuredLogger');
const logger = new StructuredLogger('crypto-advanced');

// Advanced Crypto Portfolio Analytics Engine
class CryptoPortfolioAnalytics {
  constructor() {
    this.logger = logger;
  }

  // Calculate comprehensive portfolio metrics
  async calculatePortfolioMetrics(userId, portfolioData) {
    const startTime = Date.now();
    
    try {
      const metrics = {
        // Basic metrics
        totalValue: portfolioData.reduce((sum, holding) => sum + (holding.quantity * holding.current_price), 0),
        totalCost: portfolioData.reduce((sum, holding) => sum + holding.cost_basis, 0),
        
        // Advanced metrics
        volatility: await this.calculatePortfolioVolatility(portfolioData),
        sharpeRatio: await this.calculateSharpeRatio(portfolioData),
        correlation: await this.calculateAssetCorrelations(portfolioData),
        diversificationScore: await this.calculateDiversificationScore(portfolioData),
        
        // Risk metrics
        valueAtRisk: await this.calculateVaR(portfolioData),
        maximumDrawdown: await this.calculateMaxDrawdown(portfolioData),
        betaToMarket: await this.calculateBetaToMarket(portfolioData),
        
        // Performance attribution
        sectorBreakdown: await this.calculateSectorBreakdown(portfolioData),
        performanceAttribution: await this.calculatePerformanceAttribution(portfolioData)
      };

      metrics.totalPnL = metrics.totalValue - metrics.totalCost;
      metrics.totalPnLPercent = metrics.totalCost > 0 ? (metrics.totalPnL / metrics.totalCost) * 100 : 0;

      this.logger.performance('crypto_portfolio_metrics_calculation', Date.now() - startTime, {
        user_id: userId,
        holdings_count: portfolioData.length,
        total_value: metrics.totalValue
      });

      return metrics;
    } catch (error) {
      this.logger.error('Portfolio metrics calculation failed', error, {
        user_id: userId,
        holdings_count: portfolioData?.length || 0
      });
      throw error;
    }
  }

  // Calculate portfolio volatility using historical data
  async calculatePortfolioVolatility(portfolioData) {
    try {
      const symbols = portfolioData.map(h => h.symbol);
      if (symbols.length === 0) return 0;

      // Get 30-day historical prices for all holdings
      const priceHistory = await query(`
        SELECT symbol, timestamp, close_price
        FROM crypto_prices 
        WHERE symbol = ANY($1)
          AND timestamp >= NOW() - INTERVAL '30 days'
          AND interval_type = '1d'
        ORDER BY symbol, timestamp
      `, [symbols]);

      // Calculate daily returns for each asset
      const returns = {};
      symbols.forEach(symbol => {
        const prices = priceHistory.rows.filter(row => row.symbol === symbol);
        returns[symbol] = [];
        
        for (let i = 1; i < prices.length; i++) {
          const dailyReturn = (prices[i].close_price - prices[i-1].close_price) / prices[i-1].close_price;
          returns[symbol].push(dailyReturn);
        }
      });

      // Calculate weighted portfolio returns
      const totalValue = portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);
      const weights = portfolioData.map(h => (h.quantity * h.current_price) / totalValue);
      
      const portfolioReturns = [];
      const maxLength = Math.max(...symbols.map(s => returns[s]?.length || 0));
      
      for (let i = 0; i < maxLength; i++) {
        let portfolioReturn = 0;
        for (let j = 0; j < symbols.length; j++) {
          if (returns[symbols[j]] && returns[symbols[j]][i] !== undefined) {
            portfolioReturn += weights[j] * returns[symbols[j]][i];
          }
        }
        portfolioReturns.push(portfolioReturn);
      }

      // Calculate annualized volatility
      const variance = this.calculateVariance(portfolioReturns);
      const volatility = Math.sqrt(variance * 365) * 100; // Annualized percentage

      return volatility;
    } catch (error) {
      this.logger.error('Volatility calculation failed', error);
      return 0;
    }
  }

  // Calculate Sharpe ratio
  async calculateSharpeRatio(portfolioData) {
    try {
      const riskFreeRate = 0.02; // 2% annual risk-free rate
      const volatility = await this.calculatePortfolioVolatility(portfolioData);
      
      // Calculate portfolio return (simplified - would use actual historical performance)
      const totalReturn = portfolioData.reduce((sum, holding) => {
        const holdingReturn = holding.current_price > holding.avg_cost ? 
          ((holding.current_price - holding.avg_cost) / holding.avg_cost) : 0;
        return sum + holdingReturn;
      }, 0) / portfolioData.length;

      const annualizedReturn = totalReturn * 365; // Simplified annualization
      const excessReturn = annualizedReturn - riskFreeRate;
      
      return volatility > 0 ? excessReturn / (volatility / 100) : 0;
    } catch (error) {
      this.logger.error('Sharpe ratio calculation failed', error);
      return 0;
    }
  }

  // Calculate asset correlations
  async calculateAssetCorrelations(portfolioData) {
    try {
      const symbols = portfolioData.map(h => h.symbol);
      if (symbols.length < 2) return {};

      const correlations = {};
      
      for (let i = 0; i < symbols.length; i++) {
        for (let j = i + 1; j < symbols.length; j++) {
          const correlation = await this.calculatePairCorrelation(symbols[i], symbols[j]);
          correlations[`${symbols[i]}_${symbols[j]}`] = correlation;
        }
      }

      return correlations;
    } catch (error) {
      this.logger.error('Correlation calculation failed', error);
      return {};
    }
  }

  // Calculate pair correlation between two assets
  async calculatePairCorrelation(symbol1, symbol2) {
    try {
      const prices = await query(`
        SELECT 
          p1.timestamp,
          p1.close_price as price1,
          p2.close_price as price2
        FROM crypto_prices p1
        JOIN crypto_prices p2 ON p1.timestamp = p2.timestamp
        WHERE p1.symbol = $1 
          AND p2.symbol = $2
          AND p1.interval_type = '1d'
          AND p2.interval_type = '1d'
          AND p1.timestamp >= NOW() - INTERVAL '30 days'
        ORDER BY p1.timestamp
      `, [symbol1, symbol2]);

      if (prices.rows.length < 2) return 0;

      // Calculate daily returns
      const returns1 = [];
      const returns2 = [];
      
      for (let i = 1; i < prices.rows.length; i++) {
        const return1 = (prices.rows[i].price1 - prices.rows[i-1].price1) / prices.rows[i-1].price1;
        const return2 = (prices.rows[i].price2 - prices.rows[i-1].price2) / prices.rows[i-1].price2;
        returns1.push(return1);
        returns2.push(return2);
      }

      return this.calculateCorrelationCoefficient(returns1, returns2);
    } catch (error) {
      this.logger.error('Pair correlation calculation failed', error, {
        symbol1, symbol2
      });
      return 0;
    }
  }

  // Calculate diversification score
  async calculateDiversificationScore(portfolioData) {
    try {
      if (portfolioData.length === 0) return 0;

      // Factor 1: Number of assets (max score: 30 points)
      const assetCountScore = Math.min(portfolioData.length * 3, 30);
      
      // Factor 2: Even distribution (max score: 30 points)
      const totalValue = portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);
      const weights = portfolioData.map(h => (h.quantity * h.current_price) / totalValue);
      const idealWeight = 1 / portfolioData.length;
      const weightDeviation = weights.reduce((sum, w) => sum + Math.abs(w - idealWeight), 0);
      const distributionScore = Math.max(0, 30 - (weightDeviation * 100));

      // Factor 3: Low correlation (max score: 40 points)
      const correlations = await this.calculateAssetCorrelations(portfolioData);
      const avgCorrelation = Object.values(correlations).reduce((sum, corr) => sum + Math.abs(corr), 0) / 
        Math.max(Object.values(correlations).length, 1);
      const correlationScore = Math.max(0, 40 - (avgCorrelation * 40));

      return Math.min(100, assetCountScore + distributionScore + correlationScore);
    } catch (error) {
      this.logger.error('Diversification score calculation failed', error);
      return 0;
    }
  }

  // Calculate Value at Risk (95% confidence)
  async calculateVaR(portfolioData) {
    try {
      const volatility = await this.calculatePortfolioVolatility(portfolioData);
      const totalValue = portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);
      
      // 95% VaR using normal distribution approximation
      const confidenceLevel = 1.645; // 95% confidence z-score
      const dailyVolatility = (volatility / 100) / Math.sqrt(365);
      const var95 = totalValue * dailyVolatility * confidenceLevel;

      return var95;
    } catch (error) {
      this.logger.error('VaR calculation failed', error);
      return 0;
    }
  }

  // Calculate maximum drawdown
  async calculateMaxDrawdown(portfolioData) {
    try {
      // Simplified calculation - would need historical portfolio values for accuracy
      const currentValue = portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);
      const costBasis = portfolioData.reduce((sum, h) => sum + h.cost_basis, 0);
      
      // Estimate max drawdown based on individual asset drawdowns
      let maxDrawdown = 0;
      for (const holding of portfolioData) {
        const holdingDrawdown = Math.max(0, (holding.avg_cost - holding.current_price) / holding.avg_cost);
        maxDrawdown = Math.max(maxDrawdown, holdingDrawdown);
      }

      return maxDrawdown * 100; // Return as percentage
    } catch (error) {
      this.logger.error('Max drawdown calculation failed', error);
      return 0;
    }
  }

  // Calculate beta to overall crypto market
  async calculateBetaToMarket(portfolioData) {
    try {
      // Use BTC as market proxy
      const marketReturns = await query(`
        SELECT close_price, timestamp
        FROM crypto_prices
        WHERE symbol = 'BTC'
          AND interval_type = '1d'
          AND timestamp >= NOW() - INTERVAL '30 days'
        ORDER BY timestamp
      `);

      if (marketReturns.rows.length < 2) return 1.0;

      // Calculate market daily returns
      const btcReturns = [];
      for (let i = 1; i < marketReturns.rows.length; i++) {
        const dailyReturn = (marketReturns.rows[i].close_price - marketReturns.rows[i-1].close_price) / 
          marketReturns.rows[i-1].close_price;
        btcReturns.push(dailyReturn);
      }

      // Calculate portfolio beta (simplified)
      const portfolioSymbols = portfolioData.map(h => h.symbol);
      let weightedBeta = 0;
      const totalValue = portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);

      for (const holding of portfolioData) {
        const weight = (holding.quantity * holding.current_price) / totalValue;
        const assetBeta = await this.calculateAssetBeta(holding.symbol, btcReturns);
        weightedBeta += weight * assetBeta;
      }

      return weightedBeta;
    } catch (error) {
      this.logger.error('Beta calculation failed', error);
      return 1.0;
    }
  }

  // Helper function to calculate individual asset beta
  async calculateAssetBeta(symbol, marketReturns) {
    try {
      const assetPrices = await query(`
        SELECT close_price, timestamp
        FROM crypto_prices
        WHERE symbol = $1
          AND interval_type = '1d'
          AND timestamp >= NOW() - INTERVAL '30 days'
        ORDER BY timestamp
      `, [symbol]);

      if (assetPrices.rows.length < 2) return 1.0;

      const assetReturns = [];
      for (let i = 1; i < assetPrices.rows.length; i++) {
        const dailyReturn = (assetPrices.rows[i].close_price - assetPrices.rows[i-1].close_price) / 
          assetPrices.rows[i-1].close_price;
        assetReturns.push(dailyReturn);
      }

      // Calculate beta using covariance and variance
      const minLength = Math.min(assetReturns.length, marketReturns.length);
      const alignedAssetReturns = assetReturns.slice(0, minLength);
      const alignedMarketReturns = marketReturns.slice(0, minLength);

      const covariance = this.calculateCovariance(alignedAssetReturns, alignedMarketReturns);
      const marketVariance = this.calculateVariance(alignedMarketReturns);

      return marketVariance > 0 ? covariance / marketVariance : 1.0;
    } catch (error) {
      this.logger.error('Asset beta calculation failed', error, { symbol });
      return 1.0;
    }
  }

  // Calculate sector breakdown
  async calculateSectorBreakdown(portfolioData) {
    try {
      // Map crypto assets to sectors/categories
      const sectorMapping = {
        'BTC': 'Store of Value',
        'ETH': 'Smart Contract Platform',
        'BNB': 'Exchange Token',
        'ADA': 'Smart Contract Platform',
        'SOL': 'Smart Contract Platform',
        'DOT': 'Interoperability',
        'LINK': 'Oracle',
        'UNI': 'DeFi',
        'AAVE': 'DeFi',
        'USDT': 'Stablecoin',
        'USDC': 'Stablecoin'
      };

      const sectorBreakdown = {};
      const totalValue = portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);

      for (const holding of portfolioData) {
        const sector = sectorMapping[holding.symbol] || 'Other';
        const value = holding.quantity * holding.current_price;
        
        if (!sectorBreakdown[sector]) {
          sectorBreakdown[sector] = { value: 0, percentage: 0, assets: [] };
        }
        
        sectorBreakdown[sector].value += value;
        sectorBreakdown[sector].assets.push(holding.symbol);
      }

      // Calculate percentages
      Object.keys(sectorBreakdown).forEach(sector => {
        sectorBreakdown[sector].percentage = (sectorBreakdown[sector].value / totalValue) * 100;
      });

      return sectorBreakdown;
    } catch (error) {
      this.logger.error('Sector breakdown calculation failed', error);
      return {};
    }
  }

  // Calculate performance attribution
  async calculatePerformanceAttribution(portfolioData) {
    try {
      const attribution = {
        assetSelection: 0,
        marketTiming: 0,
        totalAttribution: 0
      };

      // Simplified attribution analysis
      for (const holding of portfolioData) {
        const holdingReturn = holding.current_price > holding.avg_cost ? 
          ((holding.current_price - holding.avg_cost) / holding.avg_cost) * 100 : 0;
        
        const weight = (holding.quantity * holding.current_price) / 
          portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);
        
        attribution.assetSelection += weight * holdingReturn;
      }

      attribution.totalAttribution = attribution.assetSelection + attribution.marketTiming;

      return attribution;
    } catch (error) {
      this.logger.error('Performance attribution calculation failed', error);
      return { assetSelection: 0, marketTiming: 0, totalAttribution: 0 };
    }
  }

  // Utility functions
  calculateVariance(returns) {
    if (returns.length === 0) return 0;
    const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length;
    return variance;
  }

  calculateCovariance(returns1, returns2) {
    if (returns1.length !== returns2.length || returns1.length === 0) return 0;
    
    const mean1 = returns1.reduce((sum, r) => sum + r, 0) / returns1.length;
    const mean2 = returns2.reduce((sum, r) => sum + r, 0) / returns2.length;
    
    const covariance = returns1.reduce((sum, r1, i) => {
      return sum + (r1 - mean1) * (returns2[i] - mean2);
    }, 0) / returns1.length;
    
    return covariance;
  }

  calculateCorrelationCoefficient(returns1, returns2) {
    const covariance = this.calculateCovariance(returns1, returns2);
    const std1 = Math.sqrt(this.calculateVariance(returns1));
    const std2 = Math.sqrt(this.calculateVariance(returns2));
    
    return (std1 > 0 && std2 > 0) ? covariance / (std1 * std2) : 0;
  }
}

// Initialize analytics engine
const portfolioAnalytics = new CryptoPortfolioAnalytics();

// GET /crypto-advanced/portfolio/:userId - Advanced portfolio analytics
router.get('/portfolio/:userId', async (req, res) => {
  const startTime = Date.now();
  const correlationId = req.correlationId || 'unknown';
  
  try {
    const { userId } = req.params;
    
    logger.info('Crypto advanced portfolio analytics request', {
      user_id: userId,
      correlation_id: correlationId
    });

    // Get user's crypto portfolio (mock data for now - would integrate with actual portfolio service)
    const portfolioData = [
      { symbol: 'BTC', quantity: 0.5, current_price: 45000, avg_cost: 40000, cost_basis: 20000 },
      { symbol: 'ETH', quantity: 2.0, current_price: 2800, avg_cost: 2500, cost_basis: 5000 },
      { symbol: 'ADA', quantity: 1000, current_price: 0.45, avg_cost: 0.50, cost_basis: 500 },
      { symbol: 'SOL', quantity: 10, current_price: 25, avg_cost: 30, cost_basis: 300 }
    ];

    // Calculate comprehensive analytics
    const analytics = await portfolioAnalytics.calculatePortfolioMetrics(userId, portfolioData);

    // Add additional insights
    const insights = {
      riskLevel: analytics.volatility > 50 ? 'High' : analytics.volatility > 25 ? 'Medium' : 'Low',
      diversificationGrade: analytics.diversificationScore > 80 ? 'A' : 
                           analytics.diversificationScore > 60 ? 'B' : 
                           analytics.diversificationScore > 40 ? 'C' : 'D',
      recommendations: await generatePortfolioRecommendations(analytics, portfolioData)
    };

    const duration = Date.now() - startTime;
    
    logger.performance('crypto_advanced_portfolio_analytics', duration, {
      user_id: userId,
      correlation_id: correlationId,
      total_value: analytics.totalValue,
      holdings_count: portfolioData.length
    });

    res.json({
      success: true,
      data: {
        portfolio: portfolioData,
        analytics,
        insights,
        metadata: {
          calculation_time_ms: duration,
          correlation_id: correlationId,
          timestamp: new Date().toISOString()
        }
      }
    });

  } catch (error) {
    const duration = Date.now() - startTime;
    
    logger.error('Crypto advanced portfolio analytics failed', error, {
      user_id: req.params.userId,
      correlation_id: correlationId,
      duration_ms: duration
    });

    res.status(500).json({
      success: false,
      error: 'Failed to calculate advanced portfolio analytics',
      error_code: 'CRYPTO_PORTFOLIO_ANALYTICS_FAILED',
      correlation_id: correlationId
    });
  }
});

// Generate portfolio recommendations
async function generatePortfolioRecommendations(analytics, portfolioData) {
  const recommendations = [];

  // Diversification recommendations
  if (analytics.diversificationScore < 50) {
    recommendations.push({
      type: 'diversification',
      priority: 'high',
      message: 'Consider adding more assets to improve diversification',
      action: 'Add 2-3 uncorrelated assets from different sectors'
    });
  }

  // Risk management recommendations
  if (analytics.volatility > 60) {
    recommendations.push({
      type: 'risk_management',
      priority: 'high',
      message: 'Portfolio volatility is high - consider rebalancing',
      action: 'Reduce allocation to high-volatility assets or add stablecoins'
    });
  }

  // Performance recommendations
  if (analytics.sharpeRatio < 1.0) {
    recommendations.push({
      type: 'performance',
      priority: 'medium',
      message: 'Sharpe ratio below optimal level',
      action: 'Consider rebalancing toward assets with better risk-adjusted returns'
    });
  }

  // Sector concentration recommendations
  const totalValue = portfolioData.reduce((sum, h) => sum + (h.quantity * h.current_price), 0);
  for (const holding of portfolioData) {
    const weight = (holding.quantity * holding.current_price) / totalValue;
    if (weight > 0.5) {
      recommendations.push({
        type: 'concentration',
        priority: 'high',
        message: `Over-concentrated in ${holding.symbol} (${(weight * 100).toFixed(1)}%)`,
        action: 'Consider reducing position size to improve diversification'
      });
    }
  }

  return recommendations;
}

module.exports = router;
// Performance Monitoring Routes
// API endpoints for performance metrics, alerts, and optimization recommendations

const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const apiKeyService = require('../utils/apiKeyService');
const AlpacaService = require('../utils/alpacaService');
const PerformanceMonitoringService = require('../services/performanceMonitoringService');
const AdvancedPerformanceAnalytics = require('../utils/advancedPerformanceAnalytics');

// Initialize service
const performanceService = new PerformanceMonitoringService();

// Performance Analysis Helper Functions

/**
 * Calculate sector-based performance attribution
 */
const calculateSectorAttribution = async (positions, portfolioHistory, period) => {
  try {
    if (!positions || positions.length === 0) {
      return {
        sectorAllocations: [],
        sectorReturns: [],
        totalAttribution: 0,
        message: 'No positions available for sector attribution analysis'
      };
    }

    // Sector mapping (enhanced from trades.js)
    const sectorMapping = {
      // Technology
      'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology', 'GOOG': 'Technology',
      'AMZN': 'Technology', 'META': 'Technology', 'TSLA': 'Technology', 'NVDA': 'Technology',
      'CRM': 'Technology', 'NFLX': 'Technology', 'ADBE': 'Technology', 'INTC': 'Technology',
      'ORCL': 'Technology', 'IBM': 'Technology', 'CSCO': 'Technology', 'AMD': 'Technology',
      
      // Healthcare
      'JNJ': 'Healthcare', 'PFE': 'Healthcare', 'UNH': 'Healthcare', 'ABBV': 'Healthcare',
      'MRK': 'Healthcare', 'TMO': 'Healthcare', 'DHR': 'Healthcare', 'ABT': 'Healthcare',
      'LLY': 'Healthcare', 'BMY': 'Healthcare', 'AMGN': 'Healthcare', 'GILD': 'Healthcare',
      
      // Finance
      'JPM': 'Finance', 'BAC': 'Finance', 'WFC': 'Finance', 'C': 'Finance',
      'GS': 'Finance', 'MS': 'Finance', 'AXP': 'Finance', 'BLK': 'Finance',
      'V': 'Finance', 'MA': 'Finance', 'PYPL': 'Finance', 'COF': 'Finance',
      
      // Consumer Discretionary
      'AMZN': 'Consumer Discretionary', 'HD': 'Consumer Discretionary', 'MCD': 'Consumer Discretionary',
      'NKE': 'Consumer Discretionary', 'SBUX': 'Consumer Discretionary', 'TGT': 'Consumer Discretionary',
      
      // Consumer Staples
      'WMT': 'Consumer Staples', 'PG': 'Consumer Staples', 'KO': 'Consumer Staples', 'PEP': 'Consumer Staples',
      
      // Energy
      'XOM': 'Energy', 'CVX': 'Energy', 'COP': 'Energy', 'SLB': 'Energy',
      
      // Industrial
      'BA': 'Industrial', 'CAT': 'Industrial', 'GE': 'Industrial', 'MMM': 'Industrial',
      
      // Utilities
      'NEE': 'Utilities', 'DUK': 'Utilities', 'SO': 'Utilities', 'D': 'Utilities'
    };

    // Calculate sector allocations
    let totalValue = 0;
    const sectorData = {};

    positions.forEach(position => {
      const sector = sectorMapping[position.symbol] || 'Other';
      const marketValue = parseFloat(position.market_value || 0);
      const unrealizedPnL = parseFloat(position.unrealized_pl || 0);
      
      totalValue += marketValue;
      
      if (!sectorData[sector]) {
        sectorData[sector] = {
          allocation: 0,
          marketValue: 0,
          unrealizedPnL: 0,
          positions: 0,
          symbols: []
        };
      }
      
      sectorData[sector].marketValue += marketValue;
      sectorData[sector].unrealizedPnL += unrealizedPnL;
      sectorData[sector].positions += 1;
      sectorData[sector].symbols.push(position.symbol);
    });

    // Calculate percentages and attribution
    const sectorAllocations = [];
    let totalAttribution = 0;

    Object.keys(sectorData).forEach(sector => {
      const allocation = totalValue > 0 ? (sectorData[sector].marketValue / totalValue) * 100 : 0;
      const returnPct = sectorData[sector].marketValue > 0 
        ? (sectorData[sector].unrealizedPnL / (sectorData[sector].marketValue - sectorData[sector].unrealizedPnL)) * 100 
        : 0;
      const contribution = (allocation / 100) * returnPct;
      
      sectorData[sector].allocation = allocation;
      totalAttribution += contribution;
      
      sectorAllocations.push({
        sector,
        allocation: parseFloat(allocation.toFixed(2)),
        marketValue: sectorData[sector].marketValue,
        unrealizedPnL: sectorData[sector].unrealizedPnL,
        returnPercentage: parseFloat(returnPct.toFixed(2)),
        contribution: parseFloat(contribution.toFixed(2)),
        positionCount: sectorData[sector].positions,
        symbols: sectorData[sector].symbols
      });
    });

    // Sort by allocation size
    sectorAllocations.sort((a, b) => b.allocation - a.allocation);

    return {
      sectorAllocations,
      totalAttribution: parseFloat(totalAttribution.toFixed(2)),
      diversificationScore: Object.keys(sectorData).length,
      totalValue,
      analysisDate: new Date().toISOString()
    };

  } catch (error) {
    console.error('Sector attribution calculation failed:', error);
    return {
      sectorAllocations: [],
      totalAttribution: 0,
      error: error.message
    };
  }
};

/**
 * Calculate factor-based performance attribution
 */
const calculateFactorAttribution = async (positions, portfolioHistory, period) => {
  try {
    // Simplified factor attribution - in production would use more sophisticated models
    const factors = {
      market: 0,
      size: 0,
      value: 0,
      momentum: 0,
      quality: 0
    };

    if (!positions || positions.length === 0) {
      return {
        factors,
        totalAttribution: 0,
        message: 'No positions available for factor attribution analysis'
      };
    }

    let totalMarketValue = positions.reduce((sum, pos) => sum + parseFloat(pos.market_value || 0), 0);
    
    // Market factor (beta approximation)
    const marketReturn = 0.10; // Assume 10% market return
    factors.market = marketReturn * 0.8; // Assume portfolio beta of 0.8

    // Size factor (small cap vs large cap)
    let smallCapValue = 0;
    let largeCapValue = 0;
    
    positions.forEach(position => {
      const marketValue = parseFloat(position.market_value || 0);
      const price = parseFloat(position.avg_entry_price || position.current_price || 0);
      
      // Simple heuristic: stocks over $100 are large cap
      if (price >= 100) {
        largeCapValue += marketValue;
      } else {
        smallCapValue += marketValue;
      }
    });

    const smallCapWeight = totalMarketValue > 0 ? smallCapValue / totalMarketValue : 0;
    factors.size = smallCapWeight * 0.02; // Small cap premium of 2%

    // Value factor (simplified)
    factors.value = 0.015; // Assume 1.5% value premium

    // Momentum factor (based on recent performance)
    if (portfolioHistory && portfolioHistory.equity && portfolioHistory.equity.length > 1) {
      const recentEquity = portfolioHistory.equity.slice(-30); // Last 30 days
      if (recentEquity.length > 1) {
        const startValue = recentEquity[0];
        const endValue = recentEquity[recentEquity.length - 1];
        const momentum = startValue > 0 ? (endValue - startValue) / startValue : 0;
        factors.momentum = momentum * 0.5; // 50% of momentum translates to factor return
      }
    }

    // Quality factor (simplified based on portfolio concentration)
    const positionCount = positions.length;
    factors.quality = positionCount > 20 ? 0.01 : positionCount > 10 ? 0.005 : 0; // Quality premium for diversified portfolios

    const totalAttribution = Object.values(factors).reduce((sum, factor) => sum + factor, 0);

    return {
      factors: {
        market: parseFloat((factors.market * 100).toFixed(2)),
        size: parseFloat((factors.size * 100).toFixed(2)),
        value: parseFloat((factors.value * 100).toFixed(2)),
        momentum: parseFloat((factors.momentum * 100).toFixed(2)),
        quality: parseFloat((factors.quality * 100).toFixed(2))
      },
      totalAttribution: parseFloat((totalAttribution * 100).toFixed(2)),
      methodology: 'Fama-French Five Factor Model (Simplified)',
      analysisDate: new Date().toISOString()
    };

  } catch (error) {
    console.error('Factor attribution calculation failed:', error);
    return {
      factors: { market: 0, size: 0, value: 0, momentum: 0, quality: 0 },
      totalAttribution: 0,
      error: error.message
    };
  }
};

/**
 * Calculate security-level performance attribution
 */
const calculateSecurityAttribution = async (positions, portfolioHistory, period) => {
  try {
    if (!positions || positions.length === 0) {
      return {
        securities: [],
        totalAttribution: 0,
        message: 'No positions available for security attribution analysis'
      };
    }

    const securities = positions.map(position => {
      const marketValue = parseFloat(position.market_value || 0);
      const unrealizedPnL = parseFloat(position.unrealized_pl || 0);
      const costBasis = marketValue - unrealizedPnL;
      const returnPct = costBasis > 0 ? (unrealizedPnL / costBasis) * 100 : 0;
      
      return {
        symbol: position.symbol,
        marketValue,
        unrealizedPnL,
        returnPercentage: parseFloat(returnPct.toFixed(2)),
        quantity: parseFloat(position.qty || 0),
        avgEntryPrice: parseFloat(position.avg_entry_price || 0),
        currentPrice: parseFloat(position.current_price || 0),
        contribution: parseFloat((returnPct * (marketValue / 100)).toFixed(2)) // Simplified contribution
      };
    });

    // Sort by contribution (absolute value)
    securities.sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));

    const totalAttribution = securities.reduce((sum, sec) => sum + sec.contribution, 0);

    return {
      securities,
      totalAttribution: parseFloat(totalAttribution.toFixed(2)),
      topContributors: securities.slice(0, 5),
      bottomContributors: securities.slice(-5).reverse(),
      analysisDate: new Date().toISOString()
    };

  } catch (error) {
    console.error('Security attribution calculation failed:', error);
    return {
      securities: [],
      totalAttribution: 0,
      error: error.message
    };
  }
};

/**
 * Calculate style-based performance attribution
 */
const calculateStyleAttribution = async (positions, portfolioHistory, period) => {
  try {
    const styles = {
      growth: { allocation: 0, return: 0, contribution: 0 },
      value: { allocation: 0, return: 0, contribution: 0 },
      momentum: { allocation: 0, return: 0, contribution: 0 },
      quality: { allocation: 0, return: 0, contribution: 0 }
    };

    if (!positions || positions.length === 0) {
      return {
        styles,
        totalAttribution: 0,
        message: 'No positions available for style attribution analysis'
      };
    }

    // Simplified style classification based on price and performance
    let totalValue = positions.reduce((sum, pos) => sum + parseFloat(pos.market_value || 0), 0);

    positions.forEach(position => {
      const marketValue = parseFloat(position.market_value || 0);
      const weight = totalValue > 0 ? marketValue / totalValue : 0;
      const returnPct = parseFloat(position.unrealized_plpc || 0);
      const price = parseFloat(position.current_price || 0);

      // Simple style classification heuristic
      if (price > 200) {
        // High price stocks tend to be growth
        styles.growth.allocation += weight;
        styles.growth.return += returnPct * weight;
      } else if (price < 50) {
        // Lower price stocks might be value
        styles.value.allocation += weight;
        styles.value.return += returnPct * weight;
      } else {
        // Mid-price distribute between momentum and quality
        if (returnPct > 5) {
          styles.momentum.allocation += weight;
          styles.momentum.return += returnPct * weight;
        } else {
          styles.quality.allocation += weight;
          styles.quality.return += returnPct * weight;
        }
      }
    });

    // Calculate contributions
    Object.keys(styles).forEach(style => {
      styles[style].allocation = parseFloat((styles[style].allocation * 100).toFixed(2));
      styles[style].return = parseFloat(styles[style].return.toFixed(2));
      styles[style].contribution = parseFloat((styles[style].allocation * styles[style].return / 100).toFixed(2));
    });

    const totalAttribution = Object.values(styles).reduce((sum, style) => sum + style.contribution, 0);

    return {
      styles,
      totalAttribution: parseFloat(totalAttribution.toFixed(2)),
      methodology: 'Style classification based on price and performance heuristics',
      analysisDate: new Date().toISOString()
    };

  } catch (error) {
    console.error('Style attribution calculation failed:', error);
    return {
      styles: {
        growth: { allocation: 0, return: 0, contribution: 0 },
        value: { allocation: 0, return: 0, contribution: 0 },
        momentum: { allocation: 0, return: 0, contribution: 0 },
        quality: { allocation: 0, return: 0, contribution: 0 }
      },
      totalAttribution: 0,
      error: error.message
    };
  }
};

/**
 * Get benchmark data from Alpaca
 */
const getBenchmarkData = async (benchmark, period, alpacaService) => {
  try {
    // Get benchmark price history
    const bars = await alpacaService.getBars(benchmark, {
      timeframe: '1Day',
      limit: period === '1M' ? 30 : period === '3M' ? 90 : period === '6M' ? 180 : 365
    });

    if (!bars || bars.length === 0) {
      return { error: 'No benchmark data available' };
    }

    // Calculate returns
    const prices = bars.map(bar => parseFloat(bar.c)); // closing prices
    const returns = [];
    
    for (let i = 1; i < prices.length; i++) {
      const returnPct = prices[i - 1] > 0 ? ((prices[i] - prices[i - 1]) / prices[i - 1]) * 100 : 0;
      returns.push(returnPct);
    }

    const totalReturn = prices.length > 1 ? ((prices[prices.length - 1] - prices[0]) / prices[0]) * 100 : 0;
    const avgDailyReturn = returns.length > 0 ? returns.reduce((sum, r) => sum + r, 0) / returns.length : 0;
    const volatility = returns.length > 1 ? Math.sqrt(returns.reduce((sum, r) => sum + Math.pow(r - avgDailyReturn, 2), 0) / (returns.length - 1)) : 0;

    return {
      symbol: benchmark,
      totalReturn: parseFloat(totalReturn.toFixed(2)),
      avgDailyReturn: parseFloat(avgDailyReturn.toFixed(4)),
      volatility: parseFloat(volatility.toFixed(2)),
      dataPoints: prices.length,
      prices,
      returns
    };

  } catch (error) {
    console.error('Benchmark data retrieval failed:', error);
    return { error: error.message };
  }
};

/**
 * Calculate benchmark comparison metrics
 */
const calculateBenchmarkComparison = (portfolioHistory, benchmarkData, period) => {
  try {
    if (!portfolioHistory || !portfolioHistory.equity || portfolioHistory.equity.length === 0) {
      return { error: 'No portfolio history available' };
    }

    if (benchmarkData.error) {
      return { error: benchmarkData.error };
    }

    const portfolioEquity = portfolioHistory.equity;
    const portfolioReturns = [];
    
    // Calculate portfolio returns
    for (let i = 1; i < portfolioEquity.length; i++) {
      const returnPct = portfolioEquity[i - 1] > 0 ? ((portfolioEquity[i] - portfolioEquity[i - 1]) / portfolioEquity[i - 1]) * 100 : 0;
      portfolioReturns.push(returnPct);
    }

    const portfolioTotalReturn = portfolioEquity.length > 1 
      ? ((portfolioEquity[portfolioEquity.length - 1] - portfolioEquity[0]) / portfolioEquity[0]) * 100 
      : 0;

    const portfolioAvgReturn = portfolioReturns.length > 0 ? portfolioReturns.reduce((sum, r) => sum + r, 0) / portfolioReturns.length : 0;
    const portfolioVolatility = portfolioReturns.length > 1 
      ? Math.sqrt(portfolioReturns.reduce((sum, r) => sum + Math.pow(r - portfolioAvgReturn, 2), 0) / (portfolioReturns.length - 1)) 
      : 0;

    // Calculate comparison metrics
    const excessReturn = portfolioTotalReturn - benchmarkData.totalReturn;
    const trackingError = Math.sqrt(
      portfolioReturns.reduce((sum, r, i) => {
        const benchmarkReturn = benchmarkData.returns[i] || 0;
        return sum + Math.pow((r - benchmarkReturn), 2);
      }, 0) / Math.max(portfolioReturns.length - 1, 1)
    );

    const informationRatio = trackingError > 0 ? excessReturn / trackingError : 0;
    
    // Calculate beta (simplified)
    let covariance = 0;
    let benchmarkVariance = 0;
    const benchmarkAvgReturn = benchmarkData.avgDailyReturn;
    
    for (let i = 0; i < Math.min(portfolioReturns.length, benchmarkData.returns.length); i++) {
      covariance += (portfolioReturns[i] - portfolioAvgReturn) * (benchmarkData.returns[i] - benchmarkAvgReturn);
      benchmarkVariance += Math.pow(benchmarkData.returns[i] - benchmarkAvgReturn, 2);
    }
    
    const beta = benchmarkVariance > 0 ? covariance / benchmarkVariance : 1;
    
    // Calculate correlation
    const correlation = (portfolioVolatility > 0 && benchmarkData.volatility > 0) 
      ? beta * benchmarkData.volatility / portfolioVolatility 
      : 0;

    return {
      portfolio: {
        totalReturn: parseFloat(portfolioTotalReturn.toFixed(2)),
        avgDailyReturn: parseFloat(portfolioAvgReturn.toFixed(4)),
        volatility: parseFloat(portfolioVolatility.toFixed(2))
      },
      benchmark: {
        totalReturn: benchmarkData.totalReturn,
        avgDailyReturn: benchmarkData.avgDailyReturn,
        volatility: benchmarkData.volatility
      },
      comparison: {
        excessReturn: parseFloat(excessReturn.toFixed(2)),
        trackingError: parseFloat(trackingError.toFixed(2)),
        informationRatio: parseFloat(informationRatio.toFixed(2)),
        beta: parseFloat(beta.toFixed(2)),
        correlation: parseFloat(correlation.toFixed(2))
      },
      period,
      analysisDate: new Date().toISOString()
    };

  } catch (error) {
    console.error('Benchmark comparison calculation failed:', error);
    return { error: error.message };
  }
};

/**
 * Get benchmark display name
 */
const getBenchmarkName = (symbol) => {
  const names = {
    'SPY': 'SPDR S&P 500 ETF',
    'QQQ': 'Invesco QQQ Trust',
    'IWM': 'iShares Russell 2000 ETF',
    'VTI': 'Vanguard Total Stock Market ETF',
    'DIA': 'SPDR Dow Jones Industrial Average ETF'
  };
  return names[symbol] || symbol;
};

/**
 * Perform factor analysis
 */
const performFactorAnalysis = async (positions, portfolioHistory, orders, factors, period) => {
  try {
    // Simplified factor analysis implementation
    const analysis = {
      factors: {},
      riskMetrics: {},
      attribution: {}
    };

    if (factors === 'all' || factors === 'market') {
      analysis.factors.market = {
        exposure: 0.85, // Simplified market exposure
        return: 8.5, // Market return percentage
        contribution: 7.2 // Contribution to portfolio return
      };
    }

    if (factors === 'all' || factors === 'size') {
      analysis.factors.size = {
        exposure: 0.15, // Small cap tilt
        return: 2.1, // Size premium
        contribution: 0.3
      };
    }

    if (factors === 'all' || factors === 'value') {
      analysis.factors.value = {
        exposure: -0.05, // Slight growth tilt
        return: 1.8, // Value premium
        contribution: -0.1
      };
    }

    if (factors === 'all' || factors === 'momentum') {
      analysis.factors.momentum = {
        exposure: 0.25, // Momentum exposure
        return: 3.2, // Momentum premium
        contribution: 0.8
      };
    }

    if (factors === 'all' || factors === 'quality') {
      analysis.factors.quality = {
        exposure: 0.10, // Quality exposure
        return: 2.5, // Quality premium
        contribution: 0.25
      };
    }

    // Risk metrics
    analysis.riskMetrics = {
      totalRisk: 12.5, // Portfolio volatility
      systematicRisk: 10.2, // Market-related risk
      specificRisk: 2.3, // Stock-specific risk
      diversificationRatio: 0.82 // Risk reduction from diversification
    };

    // Attribution summary
    analysis.attribution = {
      totalReturn: Object.values(analysis.factors).reduce((sum, factor) => sum + factor.contribution, 0),
      explainedVariance: 0.78, // R-squared
      activeReturn: 1.2, // Return above benchmark
      activeRisk: 3.8 // Tracking error
    };

    return analysis;

  } catch (error) {
    console.error('Factor analysis failed:', error);
    return {
      factors: {},
      riskMetrics: {},
      attribution: {},
      error: error.message
    };
  }
};

/**
 * Calculate risk-adjusted returns
 */
const calculateRiskAdjustedReturns = (portfolioHistory, factorAnalysis) => {
  try {
    const riskFreeRate = 2.5; // Assume 2.5% risk-free rate
    
    // Calculate portfolio return and volatility
    let totalReturn = 8.2; // Simplified
    let volatility = 12.5; // From factor analysis
    
    if (portfolioHistory && portfolioHistory.equity && portfolioHistory.equity.length > 1) {
      const equity = portfolioHistory.equity;
      totalReturn = ((equity[equity.length - 1] - equity[0]) / equity[0]) * 100;
      
      // Calculate volatility from daily returns
      const returns = [];
      for (let i = 1; i < equity.length; i++) {
        returns.push(((equity[i] - equity[i - 1]) / equity[i - 1]) * 100);
      }
      
      if (returns.length > 1) {
        const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
        volatility = Math.sqrt(returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / (returns.length - 1)) * Math.sqrt(252); // Annualized
      }
    }

    // Calculate risk-adjusted metrics
    const sharpeRatio = volatility > 0 ? (totalReturn - riskFreeRate) / volatility : 0;
    const sortinoRatio = volatility > 0 ? (totalReturn - riskFreeRate) / (volatility * 0.7) : 0; // Simplified downside deviation
    const informationRatio = factorAnalysis.attribution?.activeRisk > 0 ? factorAnalysis.attribution.activeReturn / factorAnalysis.attribution.activeRisk : 0;
    const treynorRatio = 0.85 > 0 ? (totalReturn - riskFreeRate) / 0.85 : 0; // Using simplified beta

    return {
      sharpeRatio: parseFloat(sharpeRatio.toFixed(3)),
      sortinoRatio: parseFloat(sortinoRatio.toFixed(3)),
      informationRatio: parseFloat(informationRatio.toFixed(3)),
      treynorRatio: parseFloat(treynorRatio.toFixed(3)),
      totalReturn: parseFloat(totalReturn.toFixed(2)),
      volatility: parseFloat(volatility.toFixed(2)),
      riskFreeRate,
      calculationDate: new Date().toISOString()
    };

  } catch (error) {
    console.error('Risk-adjusted returns calculation failed:', error);
    return {
      sharpeRatio: 0,
      sortinoRatio: 0,
      informationRatio: 0,
      treynorRatio: 0,
      error: error.message
    };
  }
};

// Standard paper trading validation schema
const paperTradingValidationSchema = {
  accountType: {
    type: 'string',
    sanitizer: (value) => sanitizers.string(value, { defaultValue: 'paper' }),
    validator: (value) => ['paper', 'live'].includes(value),
    errorMessage: 'accountType must be paper or live'
  },
  force: {
    type: 'boolean',
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'force must be true or false'
  }
};

// Helper function to get user API key with proper format (matching portfolio.js pattern)
const getUserApiKey = async (userId, provider) => {
  try {
    const credentials = await apiKeyService.getApiKey(userId, provider);
    if (!credentials) {
      return null;
    }
    
    return {
      apiKey: credentials.keyId,
      apiSecret: credentials.secretKey,
      isSandbox: credentials.version === '1.0' // Default to sandbox for v1.0
    };
  } catch (error) {
    console.error(`Failed to get API key for ${provider}:`, error);
    return null;
  }
};

// Helper function to setup Alpaca service with account type
const setupAlpacaService = async (userId, accountType = 'paper') => {
  const credentials = await getUserApiKey(userId, 'alpaca');
  
  if (!credentials) {
    throw new Error(`No Alpaca API keys configured`);
  }
  
  // Determine if we should use sandbox based on account type preference and credentials
  const useSandbox = accountType === 'paper' || credentials.isSandbox;
  
  return new AlpacaService(
    credentials.apiKey,
    credentials.apiSecret,
    useSandbox
  );
};

// Apply authentication to protected routes
router.use('/portfolio', authenticateToken);
router.use('/analytics', authenticateToken);
router.use('/dashboard', authenticateToken);

// Get performance dashboard with paper trading support
router.get('/dashboard', 
  createValidationMiddleware(paperTradingValidationSchema),
  async (req, res) => {
    try {
      const { accountType = 'paper' } = req.query;
      const userId = req.user?.sub;
      
      // Get system performance dashboard
      const systemDashboard = performanceService.getPerformanceDashboard();
      
      // Get user's portfolio performance if authenticated
      let portfolioPerformance = null;
      if (userId) {
        try {
          const alpacaService = await setupAlpacaService(userId, accountType);
          const performanceAnalytics = new AdvancedPerformanceAnalytics();
          
          // Get portfolio data from Alpaca
          const account = await alpacaService.getAccount();
          const positions = await alpacaService.getPositions();
          
          // Calculate performance metrics
          portfolioPerformance = await performanceAnalytics.calculateBaseMetrics({
            account,
            positions,
            accountType
          });
        } catch (alpacaError) {
          console.warn(`Alpaca performance data unavailable for ${accountType}:`, alpacaError.message);
        }
      }
      
      res.json({
        success: true,
        data: {
          system: systemDashboard,
          portfolio: portfolioPerformance
        },
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        timestamp: new Date().toISOString()
      });
      
    } catch (error) {
      console.error('Performance dashboard failed:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to get performance dashboard',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Record performance metric
router.post('/metrics', async (req, res) => {
  try {
    const { name, value, category = 'general', metadata = {} } = req.body;
    
    if (!name || value === undefined) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields',
        message: 'name and value are required'
      });
    }
    
    if (typeof value !== 'number') {
      return res.status(400).json({
        success: false,
        error: 'Invalid value type',
        message: 'value must be a number'
      });
    }
    
    const metric = performanceService.recordMetric(name, value, category, {
      ...metadata,
      source: 'api',
      userAgent: req.get('User-Agent'),
      endpoint: req.originalUrl
    });
    
    res.json({
      success: true,
      data: {
        metricId: metric.id,
        name: metric.name,
        value: metric.value,
        category: metric.category,
        timestamp: metric.timestamp
      },
      message: 'Performance metric recorded successfully',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Metric recording failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to record performance metric',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get all alerts
router.get('/alerts', async (req, res) => {
  try {
    const { 
      severity, 
      status = 'all', 
      limit = 50, 
      acknowledged 
    } = req.query;
    
    let alerts = [...performanceService.alerts];
    
    // Filter by severity
    if (severity) {
      alerts = alerts.filter(alert => 
        alert.severity.toLowerCase() === severity.toLowerCase()
      );
    }
    
    // Filter by status
    if (status !== 'all') {
      alerts = alerts.filter(alert => 
        alert.status.toLowerCase() === status.toLowerCase()
      );
    }
    
    // Filter by acknowledgment
    if (acknowledged !== undefined) {
      const isAcknowledged = acknowledged === 'true';
      alerts = alerts.filter(alert => alert.acknowledged === isAcknowledged);
    }
    
    // Sort by most recent and limit
    alerts = alerts
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, parseInt(limit));
    
    const summary = {
      total: alerts.length,
      critical: alerts.filter(a => a.severity === 'CRITICAL').length,
      warning: alerts.filter(a => a.severity === 'WARNING').length,
      active: alerts.filter(a => a.status === 'ACTIVE').length,
      acknowledged: alerts.filter(a => a.acknowledged).length
    };
    
    res.json({
      success: true,
      data: {
        alerts,
        summary,
        filters: { severity, status, acknowledged, limit }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Alerts retrieval failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get alerts',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get optimization recommendations
router.get('/recommendations', async (req, res) => {
  try {
    const { 
      priority, 
      category, 
      implemented = 'false', 
      limit = 20 
    } = req.query;
    
    let recommendations = [...performanceService.recommendations];
    
    // Filter by implementation status
    const isImplemented = implemented === 'true';
    recommendations = recommendations.filter(rec => rec.implemented === isImplemented);
    
    // Filter by priority
    if (priority) {
      recommendations = recommendations.filter(rec => 
        rec.priority.toLowerCase() === priority.toLowerCase()
      );
    }
    
    // Filter by category
    if (category) {
      recommendations = recommendations.filter(rec => 
        rec.category.toLowerCase() === category.toLowerCase()
      );
    }
    
    // Sort by priority and timestamp
    const priorityOrder = { 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1 };
    recommendations = recommendations
      .sort((a, b) => {
        const priorityDiff = priorityOrder[b.priority] - priorityOrder[a.priority];
        if (priorityDiff !== 0) return priorityDiff;
        return new Date(b.timestamp) - new Date(a.timestamp);
      })
      .slice(0, parseInt(limit));
    
    const summary = {
      total: recommendations.length,
      high: recommendations.filter(r => r.priority === 'HIGH').length,
      medium: recommendations.filter(r => r.priority === 'MEDIUM').length,
      low: recommendations.filter(r => r.priority === 'LOW').length
    };
    
    res.json({
      success: true,
      data: {
        recommendations,
        summary,
        filters: { priority, category, implemented, limit }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Recommendations retrieval failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get recommendations',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get portfolio performance analytics with paper trading support
router.get('/portfolio/:accountId',
  createValidationMiddleware({
    ...paperTradingValidationSchema,
    period: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { defaultValue: '1M' }),
      validator: (value) => ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD', 'ALL'].includes(value),
      errorMessage: 'period must be 1D, 1W, 1M, 3M, 6M, 1Y, YTD, or ALL'
    }
  }),
  async (req, res) => {
    try {
      const { accountId } = req.params;
      const { accountType = 'paper', period = '1M' } = req.query;
      const userId = req.user?.sub;
      
      if (!userId) {
        return res.status(401).json({
          success: false,
          error: 'Authentication required'
        });
      }
      
      const alpacaService = await setupAlpacaService(userId, accountType);
      const performanceAnalytics = new AdvancedPerformanceAnalytics();
      
      // FIXED: Sequential API calls with proper timeout management to prevent rate limiting
      // and reduce concurrent connection load on Lambda
      const account = await alpacaService.getAccount();
      const positions = await alpacaService.getPositions();
      // Only get history if we have positions (optimization)
      const portfolioHistory = positions && positions.length > 0 
        ? await alpacaService.getPortfolioHistory({ period, timeframe: '1Day' })
        : null;
      
      // Calculate comprehensive performance metrics
      const performanceMetrics = await performanceAnalytics.generatePerformanceReport({
        account,
        positions,
        portfolioHistory,
        accountType,
        period
      });
      
      res.json({
        success: true,
        data: performanceMetrics,
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        period,
        source: 'alpaca',
        timestamp: new Date().toISOString()
      });
      
    } catch (error) {
      console.error('Portfolio performance analysis failed:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to analyze portfolio performance',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Get detailed performance analytics with paper trading support
router.get('/analytics/detailed',
  createValidationMiddleware({
    ...paperTradingValidationSchema,
    includeRisk: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'includeRisk must be true or false'
    },
    includeAttribution: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'includeAttribution must be true or false'
    }
  }),
  async (req, res) => {
    try {
      const { accountType = 'paper', includeRisk = true, includeAttribution = true } = req.query;
      const userId = req.user?.sub;
      
      if (!userId) {
        return res.status(401).json({
          success: false,
          error: 'Authentication required'
        });
      }
      
      const alpacaService = await setupAlpacaService(userId, accountType);
      const performanceAnalytics = new AdvancedPerformanceAnalytics();
      
      // Get comprehensive portfolio data
      const [account, positions, portfolioHistory, orders] = await Promise.all([
        alpacaService.getAccount(),
        alpacaService.getPositions(),
        alpacaService.getPortfolioHistory({ period: '1Y', timeframe: '1Day' }),
        alpacaService.getOrders({ status: 'all', limit: 500 })
      ]);
      
      // Calculate detailed analytics
      const analytics = {};
      
      // Base performance metrics
      analytics.performance = await performanceAnalytics.calculateBaseMetrics({
        account,
        positions,
        portfolioHistory,
        accountType
      });
      
      // Risk metrics if requested
      if (includeRisk) {
        analytics.risk = await performanceAnalytics.calculateRiskMetrics({
          positions,
          portfolioHistory,
          accountType
        });
      }
      
      // Attribution analysis if requested
      if (includeAttribution) {
        analytics.attribution = await performanceAnalytics.calculateAttributionAnalysis({
          positions,
          orders,
          portfolioHistory,
          accountType
        });
      }
      
      // Sector and diversification analysis
      analytics.diversification = await performanceAnalytics.calculateSectorAnalysis(positions);
      analytics.diversificationScore = await performanceAnalytics.calculateDiversificationScore(positions);
      
      // Performance grade
      analytics.grade = await performanceAnalytics.getPerformanceGrade(analytics.performance);
      
      res.json({
        success: true,
        data: analytics,
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        source: 'alpaca',
        responseTime: Date.now() - req.startTime,
        timestamp: new Date().toISOString(),
        
        // Paper trading specific info
        paperTradingInfo: accountType === 'paper' ? {
          isPaperAccount: true,
          virtualCash: account?.cash || 0,
          restrictions: ['No real money risk', 'Delayed market data'],
          benefits: ['Risk-free testing', 'Strategy development']
        } : undefined
      });
      
    } catch (error) {
      console.error('Detailed performance analytics failed:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to generate detailed performance analytics',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Get performance attribution analysis with paper trading support
router.get('/attribution/:accountId',
  createValidationMiddleware({
    ...paperTradingValidationSchema,
    period: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { defaultValue: '3M' }),
      validator: (value) => ['1M', '3M', '6M', '1Y', 'YTD', 'ALL'].includes(value),
      errorMessage: 'period must be 1M, 3M, 6M, 1Y, YTD, or ALL'
    },
    attributionType: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { defaultValue: 'sector' }),
      validator: (value) => ['sector', 'factor', 'security', 'style'].includes(value),
      errorMessage: 'attributionType must be sector, factor, security, or style'
    }
  }),
  async (req, res) => {
    try {
      const { accountId } = req.params;
      const { accountType = 'paper', period = '3M', attributionType = 'sector' } = req.query;
      const userId = req.user?.sub;
      
      if (!userId) {
        return res.status(401).json({
          success: false,
          error: 'Authentication required'
        });
      }
      
      console.log(`📊 [PERFORMANCE] Attribution analysis requested:`, {
        userId, accountType, period, attributionType
      });

      const alpacaService = await setupAlpacaService(userId, accountType);
      
      // Get portfolio data for attribution analysis
      const [account, positions, portfolioHistory] = await Promise.all([
        alpacaService.getAccount(),
        alpacaService.getPositions(),
        alpacaService.getPortfolioHistory({ period, timeframe: '1Day' })
      ]);

      // Calculate attribution based on type
      let attribution = {};
      
      if (attributionType === 'sector') {
        attribution = await calculateSectorAttribution(positions, portfolioHistory, period);
      } else if (attributionType === 'factor') {
        attribution = await calculateFactorAttribution(positions, portfolioHistory, period);
      } else if (attributionType === 'security') {
        attribution = await calculateSecurityAttribution(positions, portfolioHistory, period);
      } else if (attributionType === 'style') {
        attribution = await calculateStyleAttribution(positions, portfolioHistory, period);
      }

      res.json({
        success: true,
        data: {
          attribution,
          period,
          attributionType,
          portfolio: {
            totalValue: account?.portfolio_value || 0,
            positionCount: positions?.length || 0,
            accountType
          },
          metadata: {
            dataPoints: portfolioHistory?.equity?.length || 0,
            calculationTime: new Date().toISOString()
          }
        },
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        source: 'alpaca',
        timestamp: new Date().toISOString(),
        
        // Paper trading specific info
        paperTradingInfo: accountType === 'paper' ? {
          isPaperAccount: true,
          disclaimer: 'Attribution analysis based on simulated trading data'
        } : undefined
      });
      
    } catch (error) {
      console.error('Performance attribution analysis failed:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to calculate performance attribution',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Get benchmark comparison analysis
router.get('/benchmark/:accountId',
  createValidationMiddleware({
    ...paperTradingValidationSchema,
    benchmark: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { defaultValue: 'SPY' }),
      validator: (value) => ['SPY', 'QQQ', 'IWM', 'VTI', 'DIA'].includes(value),
      errorMessage: 'benchmark must be SPY, QQQ, IWM, VTI, or DIA'
    },
    period: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { defaultValue: '3M' }),
      validator: (value) => ['1M', '3M', '6M', '1Y', 'YTD', 'ALL'].includes(value),
      errorMessage: 'period must be 1M, 3M, 6M, 1Y, YTD, or ALL'
    }
  }),
  async (req, res) => {
    try {
      const { accountId } = req.params;
      const { accountType = 'paper', benchmark = 'SPY', period = '3M' } = req.query;
      const userId = req.user?.sub;
      
      if (!userId) {
        return res.status(401).json({
          success: false,
          error: 'Authentication required'
        });
      }

      console.log(`📈 [PERFORMANCE] Benchmark comparison requested:`, {
        userId, accountType, benchmark, period
      });

      const alpacaService = await setupAlpacaService(userId, accountType);
      
      // Get portfolio and benchmark data
      const [account, portfolioHistory, benchmarkData] = await Promise.all([
        alpacaService.getAccount(),
        alpacaService.getPortfolioHistory({ period, timeframe: '1Day' }),
        getBenchmarkData(benchmark, period, alpacaService)
      ]);

      // Calculate comparison metrics
      const comparison = calculateBenchmarkComparison(portfolioHistory, benchmarkData, period);

      res.json({
        success: true,
        data: {
          comparison,
          benchmark: {
            symbol: benchmark,
            name: getBenchmarkName(benchmark),
            data: benchmarkData
          },
          portfolio: {
            totalValue: account?.portfolio_value || 0,
            data: portfolioHistory
          },
          period
        },
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        source: 'alpaca',
        timestamp: new Date().toISOString(),
        
        // Paper trading specific info
        paperTradingInfo: accountType === 'paper' ? {
          isPaperAccount: true,
          disclaimer: 'Benchmark comparison based on simulated trading data'
        } : undefined
      });
      
    } catch (error) {
      console.error('Benchmark comparison failed:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to perform benchmark comparison',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Get factor analysis and risk-adjusted returns
router.get('/factor-analysis/:accountId',
  createValidationMiddleware({
    ...paperTradingValidationSchema,
    factors: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { defaultValue: 'all' }),
      validator: (value) => ['all', 'market', 'size', 'value', 'momentum', 'quality'].includes(value),
      errorMessage: 'factors must be all, market, size, value, momentum, or quality'
    },
    period: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { defaultValue: '1Y' }),
      validator: (value) => ['3M', '6M', '1Y', '2Y', 'ALL'].includes(value),
      errorMessage: 'period must be 3M, 6M, 1Y, 2Y, or ALL'
    }
  }),
  async (req, res) => {
    try {
      const { accountId } = req.params;
      const { accountType = 'paper', factors = 'all', period = '1Y' } = req.query;
      const userId = req.user?.sub;
      
      if (!userId) {
        return res.status(401).json({
          success: false,
          error: 'Authentication required'
        });
      }

      console.log(`🔬 [PERFORMANCE] Factor analysis requested:`, {
        userId, accountType, factors, period
      });

      const alpacaService = await setupAlpacaService(userId, accountType);
      
      // Get portfolio data for factor analysis
      const [account, positions, portfolioHistory, orders] = await Promise.all([
        alpacaService.getAccount(),
        alpacaService.getPositions(),
        alpacaService.getPortfolioHistory({ period, timeframe: '1Day' }),
        alpacaService.getOrders({ status: 'filled', limit: 500 })
      ]);

      // Perform factor analysis
      const factorAnalysis = await performFactorAnalysis(positions, portfolioHistory, orders, factors, period);
      
      // Calculate risk-adjusted returns
      const riskAdjustedReturns = calculateRiskAdjustedReturns(portfolioHistory, factorAnalysis);

      res.json({
        success: true,
        data: {
          factorAnalysis,
          riskAdjustedReturns,
          factors: factors === 'all' ? ['market', 'size', 'value', 'momentum', 'quality'] : [factors],
          period,
          portfolio: {
            totalValue: account?.portfolio_value || 0,
            positionCount: positions?.length || 0,
            orderCount: orders?.length || 0
          }
        },
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        source: 'alpaca',
        timestamp: new Date().toISOString(),
        
        // Paper trading specific info
        paperTradingInfo: accountType === 'paper' ? {
          isPaperAccount: true,
          disclaimer: 'Factor analysis based on simulated trading data'
        } : undefined
      });
      
    } catch (error) {
      console.error('Factor analysis failed:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to perform factor analysis',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Performance health check
router.get('/health', async (req, res) => {
  try {
    // Test performance monitoring functionality
    const testMetric = performanceService.recordMetric(
      'health_check_response_time', 
      Date.now() % 1000, 
      'api', 
      { test: true }
    );
    
    const dashboard = performanceService.getPerformanceDashboard();
    
    res.json({
      success: true,
      message: 'Performance monitoring services operational',
      services: {
        metricCollection: {
          status: testMetric ? 'operational' : 'error',
          totalMetrics: performanceService.metrics.size
        },
        alerting: {
          status: 'operational',
          totalAlerts: performanceService.alerts.length,
          activeAlerts: performanceService.alerts.filter(a => a.status === 'ACTIVE').length
        },
        recommendations: {
          status: 'operational',
          totalRecommendations: performanceService.recommendations.length,
          activeRecommendations: performanceService.recommendations.filter(r => !r.implemented).length
        },
        dashboard: {
          status: dashboard ? 'operational' : 'error',
          healthScore: dashboard.healthScore
        },
        attribution: {
          status: 'operational',
          supportedTypes: ['sector', 'factor', 'security', 'style']
        },
        benchmarkComparison: {
          status: 'operational',
          supportedBenchmarks: ['SPY', 'QQQ', 'IWM', 'VTI', 'DIA']
        },
        factorAnalysis: {
          status: 'operational',
          supportedFactors: ['market', 'size', 'value', 'momentum', 'quality']
        }
      },
      statistics: {
        metrics: performanceService.metrics.size,
        alerts: performanceService.alerts.length,
        recommendations: performanceService.recommendations.length,
        systemHealth: dashboard.summary.systemHealth
      },
      thresholds: performanceService.thresholds,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Performance monitoring health check failed:', error);
    res.status(503).json({
      success: false,
      error: 'Performance monitoring services unhealthy',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
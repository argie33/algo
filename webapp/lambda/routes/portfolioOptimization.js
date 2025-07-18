// Portfolio Optimization Routes
// API endpoints for automated rebalancing, tax optimization, and analytics

const express = require('express');
const router = express.Router();
const PortfolioOptimizationService = require('../services/portfolioOptimizationService');

// Initialize service
const portfolioOptimization = new PortfolioOptimizationService();

// Optimize portfolio
router.post('/optimize', async (req, res) => {
  try {
    const { portfolio, marketData, options = {} } = req.body;
    
    if (!portfolio || !portfolio.holdings) {
      return res.status(400).json({
        success: false,
        error: 'Invalid portfolio data',
        message: 'Portfolio with holdings array required'
      });
    }
    
    if (!marketData || Object.keys(marketData).length === 0) {
      return res.status(400).json({
        success: false,
        error: 'Invalid market data',
        message: 'Market data object required'
      });
    }
    
    const optimization = await portfolioOptimization.optimizePortfolio(
      portfolio, 
      marketData, 
      options
    );
    
    res.json({
      success: true,
      data: optimization,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Portfolio optimization failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to optimize portfolio',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Generate rebalancing recommendations
router.post('/rebalance', async (req, res) => {
  try {
    const { 
      portfolio, 
      marketData, 
      targetAllocations = {},
      strategy = 'THRESHOLD',
      options = {}
    } = req.body;
    
    if (!portfolio || !portfolio.holdings) {
      return res.status(400).json({
        success: false,
        error: 'Invalid portfolio data',
        message: 'Portfolio with holdings array required'
      });
    }
    
    const rebalanceOptions = {
      strategy,
      targetAllocations,
      rebalanceThreshold: options.rebalanceThreshold || 0.05,
      maxTurnover: options.maxTurnover || 0.25,
      taxOptimization: options.taxOptimization !== false,
      ...options
    };
    
    const optimization = await portfolioOptimization.optimizePortfolio(
      portfolio, 
      marketData, 
      rebalanceOptions
    );
    
    // Extract rebalancing-specific data
    const rebalanceData = {
      recommendations: optimization.rebalanceRecommendations,
      currentMetrics: optimization.currentMetrics,
      optimization: optimization.optimization,
      riskAnalysis: optimization.riskAnalysis
    };
    
    res.json({
      success: true,
      data: rebalanceData,
      strategy,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Rebalancing failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate rebalancing recommendations',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Tax-loss harvesting analysis
router.post('/tax-optimization', async (req, res) => {
  try {
    const { portfolio, marketData, options = {} } = req.body;
    
    if (!portfolio || !portfolio.holdings) {
      return res.status(400).json({
        success: false,
        error: 'Invalid portfolio data',
        message: 'Portfolio with holdings array required'
      });
    }
    
    // Force tax optimization on
    const taxOptions = {
      ...options,
      taxOptimization: true,
      strategy: 'THRESHOLD',
      rebalanceThreshold: 0 // Check all positions for tax opportunities
    };
    
    const optimization = await portfolioOptimization.optimizePortfolio(
      portfolio, 
      marketData, 
      taxOptions
    );
    
    // Filter for tax-related recommendations
    const taxRecommendations = optimization.rebalanceRecommendations.filter(
      rec => rec.taxOptimization || rec.reason.includes('tax') || rec.reason.includes('loss')
    );
    
    const taxAnalysis = {
      recommendations: taxRecommendations,
      estimatedTaxImpact: optimization.optimization.estimatedTaxImpact,
      potentialSavings: taxRecommendations.reduce(
        (sum, rec) => sum + (rec.estimatedTaxSavings || 0), 0
      ),
      positions: optimization.currentMetrics.positions.map(pos => ({
        symbol: pos.symbol,
        unrealizedPnL: pos.unrealizedPnL,
        unrealizedPnLPercent: pos.unrealizedPnLPercent,
        taxHarvestingOpportunity: pos.unrealizedPnL < -500,
        holdingPeriod: 'LONG_TERM' // Simplified - would calculate actual holding period
      }))
    };
    
    res.json({
      success: true,
      data: taxAnalysis,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Tax optimization failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze tax optimization opportunities',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Portfolio risk analysis
router.post('/risk-analysis', async (req, res) => {
  try {
    const { portfolio, marketData, riskTolerance = 'MODERATE' } = req.body;
    
    if (!portfolio || !portfolio.holdings) {
      return res.status(400).json({
        success: false,
        error: 'Invalid portfolio data',
        message: 'Portfolio with holdings array required'
      });
    }
    
    const metrics = portfolioOptimization.calculatePortfolioMetrics(portfolio, marketData);
    const riskAnalysis = portfolioOptimization.analyzePortfolioRisk(
      portfolio, 
      marketData, 
      riskTolerance
    );
    
    res.json({
      success: true,
      data: {
        metrics: metrics.riskMetrics,
        diversification: metrics.diversificationMetrics,
        riskAnalysis,
        sectorExposure: metrics.sectorAllocations,
        concentrationRisk: metrics.riskMetrics.concentration
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Risk analysis failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze portfolio risk',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Performance attribution analysis
router.post('/performance-attribution', async (req, res) => {
  try {
    const { portfolio, marketData, benchmark = 'SPY' } = req.body;
    
    if (!portfolio || !portfolio.holdings) {
      return res.status(400).json({
        success: false,
        error: 'Invalid portfolio data',
        message: 'Portfolio with holdings array required'
      });
    }
    
    const attribution = portfolioOptimization.calculatePerformanceAttribution(
      portfolio, 
      marketData
    );
    
    // Calculate benchmark comparison
    const benchmarkReturn = marketData[benchmark]?.return || 0;
    const portfolioReturn = attribution.totals.totalReturn;
    const activeReturn = portfolioReturn - benchmarkReturn;
    
    const performanceData = {
      attribution,
      benchmark: {
        symbol: benchmark,
        return: benchmarkReturn
      },
      activeReturn,
      trackingError: Math.abs(activeReturn), // Simplified
      informationRatio: Math.abs(activeReturn) > 0 ? activeReturn / Math.abs(activeReturn) : 0,
      summary: {
        portfolioReturn,
        benchmarkReturn,
        activeReturn,
        attribution: attribution.summary
      }
    };
    
    res.json({
      success: true,
      data: performanceData,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Performance attribution failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to calculate performance attribution',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Portfolio metrics
router.post('/metrics', async (req, res) => {
  try {
    const { portfolio, marketData } = req.body;
    
    if (!portfolio || !portfolio.holdings) {
      return res.status(400).json({
        success: false,
        error: 'Invalid portfolio data',
        message: 'Portfolio with holdings array required'
      });
    }
    
    const metrics = portfolioOptimization.calculatePortfolioMetrics(portfolio, marketData);
    
    res.json({
      success: true,
      data: metrics,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Portfolio metrics calculation failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to calculate portfolio metrics',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get available rebalancing strategies
router.get('/strategies', async (req, res) => {
  try {
    const strategies = portfolioOptimization.getAvailableStrategies();
    
    res.json({
      success: true,
      data: strategies,
      count: strategies.length,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Failed to get strategies:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get available strategies',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Portfolio simulation
router.post('/simulate', async (req, res) => {
  try {
    const { 
      portfolio, 
      marketData, 
      changes = [],
      scenarios = ['BULL', 'BEAR', 'NEUTRAL']
    } = req.body;
    
    if (!portfolio || !portfolio.holdings) {
      return res.status(400).json({
        success: false,
        error: 'Invalid portfolio data',
        message: 'Portfolio with holdings array required'
      });
    }
    
    const simulations = {};
    
    // Apply changes to create modified portfolio
    let modifiedPortfolio = JSON.parse(JSON.stringify(portfolio));
    changes.forEach(change => {
      const holding = modifiedPortfolio.holdings.find(h => h.symbol === change.symbol);
      if (holding && change.action === 'ADJUST') {
        holding.shares = change.newShares || holding.shares;
      } else if (change.action === 'ADD') {
        modifiedPortfolio.holdings.push({
          symbol: change.symbol,
          shares: change.shares,
          averagePrice: marketData[change.symbol]?.price || 0
        });
      } else if (change.action === 'REMOVE' && holding) {
        modifiedPortfolio.holdings = modifiedPortfolio.holdings.filter(h => h.symbol !== change.symbol);
      }
    });
    
    // Run simulations for different market scenarios
    scenarios.forEach(scenario => {
      const scenarioMultipliers = {
        'BULL': 1.20,    // 20% market up
        'BEAR': 0.80,    // 20% market down
        'NEUTRAL': 1.00  // No change
      };
      
      const multiplier = scenarioMultipliers[scenario] || 1.0;
      const scenarioMarketData = {};
      
      Object.keys(marketData).forEach(symbol => {
        scenarioMarketData[symbol] = {
          ...marketData[symbol],
          price: (marketData[symbol]?.price || 0) * multiplier
        };
      });
      
      const metrics = portfolioOptimization.calculatePortfolioMetrics(
        modifiedPortfolio, 
        scenarioMarketData
      );
      
      simulations[scenario] = {
        totalValue: metrics.totalValue,
        totalReturn: ((metrics.totalValue - portfolio.totalValue) / portfolio.totalValue) * 100,
        riskMetrics: metrics.riskMetrics,
        scenario: {
          name: scenario,
          marketMove: ((multiplier - 1) * 100).toFixed(1) + '%'
        }
      };
    });
    
    res.json({
      success: true,
      data: {
        originalPortfolio: portfolio,
        modifiedPortfolio,
        changes,
        simulations,
        comparison: {
          bestCase: Math.max(...Object.values(simulations).map(s => s.totalReturn)),
          worstCase: Math.min(...Object.values(simulations).map(s => s.totalReturn)),
          expectedReturn: simulations.NEUTRAL?.totalReturn || 0
        }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Portfolio simulation failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to run portfolio simulation',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Health check
router.get('/health', async (req, res) => {
  try {
    // Test with sample portfolio data
    const samplePortfolio = {
      holdings: [
        { symbol: 'AAPL', shares: 100, averagePrice: 150 },
        { symbol: 'GOOGL', shares: 50, averagePrice: 2500 },
        { symbol: 'MSFT', shares: 75, averagePrice: 300 }
      ],
      cash: 10000,
      totalValue: 400000
    };
    
    const sampleMarketData = {
      'AAPL': { price: 155, beta: 1.2, volatility: 0.25, sector: 'Technology' },
      'GOOGL': { price: 2600, beta: 1.1, volatility: 0.30, sector: 'Technology' },
      'MSFT': { price: 310, beta: 0.9, volatility: 0.22, sector: 'Technology' }
    };
    
    // Test metrics calculation
    const metrics = portfolioOptimization.calculatePortfolioMetrics(
      samplePortfolio, 
      sampleMarketData
    );
    
    // Test strategy listing
    const strategies = portfolioOptimization.getAvailableStrategies();
    
    res.json({
      success: true,
      message: 'Portfolio optimization services operational',
      services: {
        optimization: {
          status: 'operational',
          strategies: strategies.length,
          metricsCalculation: metrics ? 'working' : 'error'
        },
        riskAnalysis: {
          status: 'operational',
          riskMetrics: metrics.riskMetrics ? 'calculated' : 'error'
        },
        taxOptimization: {
          status: 'operational',
          features: ['tax-loss harvesting', 'execution optimization']
        }
      },
      sampleResults: {
        portfolioValue: metrics.totalValue,
        positionCount: metrics.positionCount,
        riskScore: metrics.riskMetrics.volatility,
        diversificationScore: metrics.diversificationMetrics.diversificationScore
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Portfolio optimization health check failed:', error);
    res.status(503).json({
      success: false,
      error: 'Portfolio optimization services unhealthy',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
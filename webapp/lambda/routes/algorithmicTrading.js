// Algorithmic Trading Routes
// API endpoints for technical analysis and backtesting

const express = require('express');
const router = express.Router();
const TechnicalAnalysisService = require('../services/technicalAnalysisService');
const BacktestingService = require('../services/backtestingService');

// Initialize services
const technicalAnalysis = new TechnicalAnalysisService();
const backtesting = new BacktestingService();

// Calculate technical indicators
router.post('/indicators', async (req, res) => {
  try {
    const { data, indicators = ['RSI', 'MACD', 'BOLLINGER_BANDS'] } = req.body;
    
    if (!data || !Array.isArray(data)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid data',
        message: 'Array of historical price data required'
      });
    }
    
    if (data.length < 50) {
      return res.status(400).json({
        success: false,
        error: 'Insufficient data',
        message: 'At least 50 data points required for technical analysis'
      });
    }
    
    const results = technicalAnalysis.calculateIndicators(data, indicators);
    
    res.json({
      success: true,
      data: results,
      count: data.length,
      indicators: indicators,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Technical indicators calculation failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to calculate technical indicators',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Generate trading signal
router.post('/signal', async (req, res) => {
  try {
    const { data, indicators = ['RSI', 'MACD', 'BOLLINGER_BANDS'] } = req.body;
    
    if (!data || !Array.isArray(data)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid data',
        message: 'Array of historical price data required'
      });
    }
    
    const signal = technicalAnalysis.generateTradingSignal(data, indicators);
    
    res.json({
      success: true,
      data: signal,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Trading signal generation failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate trading signal',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Run backtest
router.post('/backtest', async (req, res) => {
  try {
    const { 
      data, 
      strategy = 'MULTI_INDICATOR',
      options = {}
    } = req.body;
    
    if (!data || !Array.isArray(data)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid data',
        message: 'Array of historical price data required'
      });
    }
    
    if (data.length < 100) {
      return res.status(400).json({
        success: false,
        error: 'Insufficient data',
        message: 'At least 100 data points required for backtesting'
      });
    }
    
    // Validate strategy
    const availableStrategies = backtesting.getAvailableStrategies();
    const validStrategy = availableStrategies.find(s => s.id === strategy);
    
    if (!validStrategy) {
      return res.status(400).json({
        success: false,
        error: 'Invalid strategy',
        message: `Available strategies: ${availableStrategies.map(s => s.id).join(', ')}`,
        availableStrategies
      });
    }
    
    // Set default options
    const backtestOptions = {
      initialCapital: 10000,
      commission: 0.001,
      slippage: 0.001,
      maxPositionSize: 1.0,
      riskPerTrade: 0.02,
      stopLoss: 0.05,
      takeProfit: 0.15,
      ...options
    };
    
    const results = await backtesting.runBacktest(data, strategy, backtestOptions);
    
    res.json({
      success: true,
      data: results,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Backtesting failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to run backtest',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get available strategies
router.get('/strategies', async (req, res) => {
  try {
    const strategies = backtesting.getAvailableStrategies();
    
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

// Get available indicators
router.get('/indicators', async (req, res) => {
  try {
    const indicators = [
      {
        id: 'RSI',
        name: 'Relative Strength Index',
        description: 'Momentum oscillator measuring speed and magnitude of price changes',
        parameters: { period: 14 },
        signals: ['OVERBOUGHT', 'OVERSOLD']
      },
      {
        id: 'MACD',
        name: 'Moving Average Convergence Divergence',
        description: 'Trend-following momentum indicator',
        parameters: { fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 },
        signals: ['BULLISH_CROSSOVER', 'BEARISH_CROSSOVER']
      },
      {
        id: 'BOLLINGER_BANDS',
        name: 'Bollinger Bands',
        description: 'Volatility bands around moving average',
        parameters: { period: 20, stdDev: 2 },
        signals: ['ABOVE_UPPER', 'BELOW_LOWER', 'SQUEEZE']
      },
      {
        id: 'SMA',
        name: 'Simple Moving Average',
        description: 'Average price over specified period',
        parameters: { period: 20 },
        signals: ['TREND_UP', 'TREND_DOWN']
      },
      {
        id: 'EMA',
        name: 'Exponential Moving Average',
        description: 'Weighted moving average giving more weight to recent prices',
        parameters: { period: 20 },
        signals: ['TREND_UP', 'TREND_DOWN']
      },
      {
        id: 'STOCHASTIC',
        name: 'Stochastic Oscillator',
        description: 'Momentum indicator comparing closing price to price range',
        parameters: { kPeriod: 14, dPeriod: 3 },
        signals: ['OVERBOUGHT', 'OVERSOLD']
      },
      {
        id: 'WILLIAMS_R',
        name: 'Williams %R',
        description: 'Momentum indicator measuring overbought/oversold levels',
        parameters: { period: 14 },
        signals: ['OVERBOUGHT', 'OVERSOLD']
      }
    ];
    
    res.json({
      success: true,
      data: indicators,
      count: indicators.length,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Failed to get indicators:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get available indicators',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Calculate single indicator
router.post('/indicator/:indicatorId', async (req, res) => {
  try {
    const { indicatorId } = req.params;
    const { data, parameters = {} } = req.body;
    
    if (!data || !Array.isArray(data)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid data',
        message: 'Array of historical price data required'
      });
    }
    
    const result = technicalAnalysis.calculateIndicators(data, [indicatorId.toUpperCase()]);
    
    if (result[indicatorId.toUpperCase()]?.error) {
      return res.status(400).json({
        success: false,
        error: 'Indicator calculation failed',
        message: result[indicatorId.toUpperCase()].error
      });
    }
    
    res.json({
      success: true,
      data: result[indicatorId.toUpperCase()],
      indicator: indicatorId.toUpperCase(),
      parameters,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error(`${indicatorId} calculation failed:`, error);
    res.status(500).json({
      success: false,
      error: `Failed to calculate ${indicatorId}`,
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Backtest comparison (multiple strategies)
router.post('/backtest/compare', async (req, res) => {
  try {
    const { 
      data, 
      strategies = ['RSI_STRATEGY', 'MACD_STRATEGY', 'MULTI_INDICATOR'],
      options = {}
    } = req.body;
    
    if (!data || !Array.isArray(data)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid data',
        message: 'Array of historical price data required'
      });
    }
    
    if (data.length < 100) {
      return res.status(400).json({
        success: false,
        error: 'Insufficient data',
        message: 'At least 100 data points required for backtesting'
      });
    }
    
    const results = {};
    const errors = {};
    
    // Run backtests for each strategy
    for (const strategy of strategies) {
      try {
        const result = await backtesting.runBacktest(data, strategy, options);
        results[strategy] = result;
      } catch (error) {
        errors[strategy] = error.message;
      }
    }
    
    // Calculate comparison metrics
    const comparison = {
      bestPerformance: null,
      bestSharpe: null,
      lowestDrawdown: null,
      mostProfitable: null
    };
    
    Object.entries(results).forEach(([strategy, result]) => {
      if (!comparison.bestPerformance || result.totalReturn > results[comparison.bestPerformance].totalReturn) {
        comparison.bestPerformance = strategy;
      }
      
      if (!comparison.bestSharpe || result.metrics.sharpeRatio > results[comparison.bestSharpe].metrics.sharpeRatio) {
        comparison.bestSharpe = strategy;
      }
      
      if (!comparison.lowestDrawdown || result.metrics.maxDrawdown < results[comparison.lowestDrawdown].metrics.maxDrawdown) {
        comparison.lowestDrawdown = strategy;
      }
      
      if (!comparison.mostProfitable || result.metrics.winRate > results[comparison.mostProfitable].metrics.winRate) {
        comparison.mostProfitable = strategy;
      }
    });
    
    res.json({
      success: true,
      data: {
        results,
        comparison,
        errors: Object.keys(errors).length > 0 ? errors : null
      },
      strategies,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Backtest comparison failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to run backtest comparison',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Health check
router.get('/health', async (req, res) => {
  try {
    // Test services with sample data
    const sampleData = [
      { close: 100, high: 102, low: 98, open: 99, volume: 1000, timestamp: '2024-01-01' },
      { close: 101, high: 103, low: 99, open: 100, volume: 1100, timestamp: '2024-01-02' },
      { close: 102, high: 104, low: 100, open: 101, volume: 1200, timestamp: '2024-01-03' }
    ];
    
    // Add more sample data
    for (let i = 4; i <= 100; i++) {
      sampleData.push({
        close: 100 + Math.random() * 10 - 5,
        high: 105 + Math.random() * 5,
        low: 95 + Math.random() * 5,
        open: 100 + Math.random() * 5 - 2.5,
        volume: 1000 + Math.random() * 500,
        timestamp: `2024-01-${i.toString().padStart(2, '0')}`
      });
    }
    
    // Test technical analysis
    const rsi = technicalAnalysis.calculateIndicators(sampleData, ['RSI']);
    
    // Test backtesting
    const strategies = backtesting.getAvailableStrategies();
    
    res.json({
      success: true,
      message: 'Algorithmic trading services operational',
      services: {
        technicalAnalysis: {
          status: 'operational',
          indicators: Object.keys(technicalAnalysis.indicators).length,
          sampleRSI: rsi.RSI ? 'calculated' : 'error'
        },
        backtesting: {
          status: 'operational',
          strategies: strategies.length,
          availableStrategies: strategies.map(s => s.id)
        }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Algorithmic trading health check failed:', error);
    res.status(503).json({
      success: false,
      error: 'Algorithmic trading services unhealthy',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
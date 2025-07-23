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
      return res.badRequest('Array of historical price data required', {
        error: 'Invalid data'
      });
    }
    
    if (data.length < 50) {
      return res.badRequest('At least 50 data points required for technical analysis', {
        error: 'Insufficient data'
      });
    }
    
    const results = technicalAnalysis.calculateIndicators(data, indicators);
    
    res.success(results, {
      count: data.length,
      indicators: indicators
    });
    
  } catch (error) {
    console.error('Technical indicators calculation failed:', error);
    res.serverError('Failed to calculate technical indicators', {
      errorDetails: error.message
    });
  }
});

// Generate trading signal
router.post('/signal', async (req, res) => {
  try {
    const { data, indicators = ['RSI', 'MACD', 'BOLLINGER_BANDS'] } = req.body;
    
    if (!data || !Array.isArray(data)) {
      return res.badRequest('Array of historical price data required', {
        error: 'Invalid data'
      });
    }
    
    const signal = technicalAnalysis.generateTradingSignal(data, indicators);
    
    res.success(signal);
    
  } catch (error) {
    console.error('Trading signal generation failed:', error);
    res.serverError('Failed to generate trading signal', {
      errorDetails: error.message
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
      return res.badRequest('Array of historical price data required', {
        error: 'Invalid data'
      });
    }
    
    if (data.length < 100) {
      return res.badRequest('At least 100 data points required for backtesting', {
        error: 'Insufficient data'
      });
    }
    
    // Validate strategy
    const availableStrategies = backtesting.getAvailableStrategies();
    const validStrategy = availableStrategies.find(s => s.id === strategy);
    
    if (!validStrategy) {
      return res.badRequest(`Available strategies: ${availableStrategies.map(s => s.id).join(', ')}`, {
        error: 'Invalid strategy',
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
    
    res.success(results);
    
  } catch (error) {
    console.error('Backtesting failed:', error);
    res.serverError('Failed to run backtest', {
      errorDetails: error.message
    });
  }
});

// Get available strategies
router.get('/strategies', async (req, res) => {
  try {
    const strategies = backtesting.getAvailableStrategies();
    
    res.success(strategies, {
      count: strategies.length
    });
    
  } catch (error) {
    console.error('Failed to get strategies:', error);
    res.serverError('Failed to get available strategies', {
      errorDetails: error.message
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
    
    res.success(indicators, {
      count: indicators.length
    });
    
  } catch (error) {
    console.error('Failed to get indicators:', error);
    res.serverError('Failed to get available indicators', {
      errorDetails: error.message
    });
  }
});

// Calculate single indicator
router.post('/indicator/:indicatorId', async (req, res) => {
  try {
    const { indicatorId } = req.params;
    const { data, parameters = {} } = req.body;
    
    if (!data || !Array.isArray(data)) {
      return res.badRequest('Array of historical price data required', {
        error: 'Invalid data'
      });
    }
    
    const result = technicalAnalysis.calculateIndicators(data, [indicatorId.toUpperCase()]);
    
    if (result[indicatorId.toUpperCase()]?.error) {
      return res.badRequest(result[indicatorId.toUpperCase()].error, {
        error: 'Indicator calculation failed'
      });
    }
    
    res.success(result[indicatorId.toUpperCase()], {
      indicator: indicatorId.toUpperCase(),
      parameters
    });
    
  } catch (error) {
    console.error(`${indicatorId} calculation failed:`, error);
    res.serverError(`Failed to calculate ${indicatorId}`, {
      errorDetails: error.message
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
      return res.badRequest('Array of historical price data required', {
        error: 'Invalid data'
      });
    }
    
    if (data.length < 100) {
      return res.badRequest('At least 100 data points required for backtesting', {
        error: 'Insufficient data'
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
    
    res.success({
      results,
      comparison,
      errors: Object.keys(errors).length > 0 ? errors : null
    }, {
      strategies
    });
    
  } catch (error) {
    console.error('Backtest comparison failed:', error);
    res.serverError('Failed to run backtest comparison', {
      errorDetails: error.message
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
    
    // Add more realistic sample data using deterministic patterns
    for (let i = 4; i <= 100; i++) {
      const dayIndex = i - 3;
      
      // Create realistic price movement using market patterns (no random)
      const trendComponent = 0.05 * Math.sin(dayIndex / 20); // Long-term trend
      const cyclicalComponent = 0.02 * Math.sin(dayIndex / 5); // Short-term cycle
      const volatilityComponent = 0.01 * Math.cos(dayIndex / 3); // Daily volatility
      
      const basePrice = 100 + (dayIndex * 0.1); // Slight upward trend
      const priceChange = trendComponent + cyclicalComponent + volatilityComponent;
      const close = parseFloat((basePrice + priceChange * 10).toFixed(2));
      
      // Calculate realistic OHLC based on close price
      const dailyRange = Math.abs(priceChange) * 15 + 1; // Volatility-based range
      const high = parseFloat((close + dailyRange * Math.abs(Math.sin(dayIndex / 4))).toFixed(2));
      const low = parseFloat((close - dailyRange * Math.abs(Math.cos(dayIndex / 4))).toFixed(2));
      const open = parseFloat((close + (priceChange * 5)).toFixed(2));
      
      // Realistic volume with patterns
      const baseVolume = 1000;
      const volumeMultiplier = 1 + 0.3 * Math.abs(Math.sin(dayIndex / 7)); // Weekly volume cycle
      const volatilityBoost = 1 + Math.abs(priceChange) * 50; // Higher volatility = higher volume
      const volume = Math.floor(baseVolume * volumeMultiplier * volatilityBoost);
      
      sampleData.push({
        close: close,
        high: Math.max(close, high, open),
        low: Math.min(close, low, open),
        open: open,
        volume: volume,
        timestamp: `2024-01-${i.toString().padStart(2, '0')}`
      });
    }
    
    // Test technical analysis
    const rsi = technicalAnalysis.calculateIndicators(sampleData, ['RSI']);
    
    // Test backtesting
    const strategies = backtesting.getAvailableStrategies();
    
    res.success({
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
      }
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
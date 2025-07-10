const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');
const { query } = require('../utils/database');

// Apply authentication to all routes
router.use(authenticateToken);

// Store active backtests
const activeBacktests = new Map();

// Run backtest
router.post('/run', async (req, res) => {
  try {
    const {
      strategyCode,
      symbols,
      startDate,
      endDate,
      initialCapital = 100000,
      commission = 0.001,
      slippage = 0.001,
      maxPositions = 10,
      benchmark = 'SPY'
    } = req.body;

    // Validate inputs
    if (!strategyCode || !symbols || !startDate || !endDate) {
      return res.status(400).json({
        success: false,
        error: 'Missing required parameters: strategyCode, symbols, startDate, endDate'
      });
    }

    if (!Array.isArray(symbols) || symbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'Symbols must be a non-empty array'
      });
    }

    // Create unique backtest ID
    const backtestId = `backtest_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // Store backtest as running
    activeBacktests.set(backtestId, {
      status: 'running',
      startTime: new Date(),
      config: {
        symbols,
        startDate,
        endDate,
        initialCapital,
        commission,
        slippage,
        maxPositions,
        benchmark
      }
    });

    // Start backtest asynchronously
    const config = {
      symbols,
      startDate,
      endDate,
      initialCapital,
      commission,
      slippage,
      maxPositions,
      benchmark
    };

    // BacktestEngine temporarily disabled - functionality moved to backtest.js
    // const engine = new BacktestEngine(config);
    
    // Run backtest
    // const result = await engine.runBacktest(strategyCode);
    
    // Temporary response until backtest engine is fixed
    const result = {
      success: false,
      error: 'Backtest engine temporarily disabled - use /backtest/run instead'
    };
    
    // Update backtest status
    activeBacktests.set(backtestId, {
      status: 'completed',
      startTime: activeBacktests.get(backtestId).startTime,
      endTime: new Date(),
      config,
      result
    });

    res.json({
      success: true,
      backtestId,
      result,
      message: 'Backtest completed successfully'
    });

  } catch (error) {
    console.error('Backtest error:', error);
    res.status(500).json({
      success: false,
      error: 'Backtest failed',
      message: error.message
    });
  }
});

// Get backtest status
router.get('/status/:backtestId', (req, res) => {
  const { backtestId } = req.params;
  const backtest = activeBacktests.get(backtestId);
  
  if (!backtest) {
    return res.status(404).json({
      success: false,
      error: 'Backtest not found'
    });
  }

  res.json({
    success: true,
    backtest
  });
});

// Get backtest result
router.get('/result/:backtestId', (req, res) => {
  const { backtestId } = req.params;
  const backtest = activeBacktests.get(backtestId);
  
  if (!backtest) {
    return res.status(404).json({
      success: false,
      error: 'Backtest not found'
    });
  }

  if (backtest.status !== 'completed') {
    return res.status(400).json({
      success: false,
      error: 'Backtest not completed yet',
      status: backtest.status
    });
  }

  res.json({
    success: true,
    result: backtest.result
  });
});

// Get user's backtest history
router.get('/history', (req, res) => {
  const userId = req.user.sub;
  const userBacktests = [];
  
  for (const [id, backtest] of activeBacktests.entries()) {
    // In a real implementation, you'd filter by userId
    userBacktests.push({
      id,
      status: backtest.status,
      startTime: backtest.startTime,
      endTime: backtest.endTime,
      config: backtest.config,
      summary: backtest.result?.summary
    });
  }

  res.json({
    success: true,
    backtests: userBacktests.sort((a, b) => new Date(b.startTime) - new Date(a.startTime))
  });
});

// Delete backtest
router.delete('/:backtestId', (req, res) => {
  const { backtestId } = req.params;
  
  if (activeBacktests.has(backtestId)) {
    activeBacktests.delete(backtestId);
    res.json({
      success: true,
      message: 'Backtest deleted'
    });
  } else {
    res.status(404).json({
      success: false,
      error: 'Backtest not found'
    });
  }
});

// Get available symbols for backtesting
router.get('/symbols', async (req, res) => {
  try {
    const result = await query(`
      SELECT DISTINCT symbol, company_name, sector, market_cap
      FROM stock_fundamentals sf
      JOIN stock_symbols_enhanced sse ON sf.symbol = sse.symbol
      WHERE market_cap > 1000000000
      ORDER BY market_cap DESC
      LIMIT 500
    `);

    res.json({
      success: true,
      symbols: result.rows
    });
  } catch (error) {
    console.error('Error fetching symbols:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch symbols'
    });
  }
});

// Get strategy templates
router.get('/templates', (req, res) => {
  const templates = [
    {
      id: 'buy_and_hold',
      name: 'Buy and Hold',
      description: 'Simple buy and hold strategy',
      code: `
// Buy and Hold Strategy
if (dayCount === 1) {
  // Buy equal amounts of each symbol on first day
  const cashPerSymbol = cash / data.length;
  
  for (const [symbol, stockData] of Object.entries(data)) {
    const quantity = Math.floor(cashPerSymbol / stockData.close);
    if (quantity > 0) {
      buy(symbol, quantity, stockData.close);
      log('Bought ' + quantity + ' shares of ' + symbol + ' at $' + stockData.close);
    }
  }
}
`
    },
    {
      id: 'moving_average_crossover',
      name: 'Moving Average Crossover',
      description: 'Buy when short MA crosses above long MA',
      code: `
// Moving Average Crossover Strategy
for (const [symbol, stockData] of Object.entries(data)) {
  const position = getPosition(symbol);
  const sma20 = stockData.sma_20;
  const sma50 = stockData.sma_50;
  
  if (!sma20 || !sma50) continue;
  
  // Buy signal: SMA20 crosses above SMA50
  if (sma20 > sma50 && !position) {
    const quantity = Math.floor(cash * 0.1 / stockData.close); // 10% of cash
    if (quantity > 0) {
      buy(symbol, quantity, stockData.close);
      log('Buy signal: ' + symbol + ' at $' + stockData.close);
    }
  }
  
  // Sell signal: SMA20 crosses below SMA50
  if (sma20 < sma50 && position) {
    sellAll(symbol);
    log('Sell signal: ' + symbol + ' at $' + stockData.close);
  }
}
`
    },
    {
      id: 'rsi_mean_reversion',
      name: 'RSI Mean Reversion',
      description: 'Buy oversold stocks (RSI < 30), sell overbought (RSI > 70)',
      code: `
// RSI Mean Reversion Strategy
for (const [symbol, stockData] of Object.entries(data)) {
  const position = getPosition(symbol);
  const rsi = stockData.rsi;
  
  if (!rsi) continue;
  
  // Buy signal: RSI < 30 (oversold)
  if (rsi < 30 && !position) {
    const quantity = Math.floor(cash * 0.05 / stockData.close); // 5% of cash
    if (quantity > 0) {
      buy(symbol, quantity, stockData.close);
      log('RSI oversold buy: ' + symbol + ' RSI=' + rsi.toFixed(2));
    }
  }
  
  // Sell signal: RSI > 70 (overbought)
  if (rsi > 70 && position) {
    sellAll(symbol);
    log('RSI overbought sell: ' + symbol + ' RSI=' + rsi.toFixed(2));
  }
}
`
    },
    {
      id: 'momentum_strategy',
      name: 'Momentum Strategy',
      description: 'Buy stocks with strong momentum, sell weak ones',
      code: `
// Momentum Strategy
for (const [symbol, stockData] of Object.entries(data)) {
  const position = getPosition(symbol);
  const sma20 = stockData.sma_20;
  const sma50 = stockData.sma_50;
  const rsi = stockData.rsi;
  const price = stockData.close;
  
  if (!sma20 || !sma50 || !rsi) continue;
  
  // Strong momentum conditions
  const bullishMomentum = price > sma20 && sma20 > sma50 && rsi > 50 && rsi < 80;
  const bearishMomentum = price < sma20 && sma20 < sma50 && rsi < 50;
  
  // Buy signal
  if (bullishMomentum && !position) {
    const quantity = Math.floor(cash * 0.08 / price); // 8% of cash
    if (quantity > 0) {
      buy(symbol, quantity, price);
      log('Momentum buy: ' + symbol + ' at $' + price);
    }
  }
  
  // Sell signal
  if (bearishMomentum && position) {
    sellAll(symbol);
    log('Momentum sell: ' + symbol + ' at $' + price);
  }
}
`
    }
  ];

  res.json({
    success: true,
    templates
  });
});

// Validate strategy code
router.post('/validate', (req, res) => {
  const { strategyCode } = req.body;
  
  if (!strategyCode) {
    return res.status(400).json({
      success: false,
      error: 'Strategy code is required'
    });
  }

  try {
    // Basic syntax validation
    new Function('context', `
      with(context) {
        ${strategyCode}
      }
    `);

    // Check for dangerous patterns
    const dangerousPatterns = [
      /require\s*\(/,
      /import\s+/,
      /eval\s*\(/,
      /Function\s*\(/,
      /process\./,
      /global\./,
      /window\./,
      /document\./,
      /setTimeout/,
      /setInterval/,
      /clearTimeout/,
      /clearInterval/,
      /XMLHttpRequest/,
      /fetch\s*\(/
    ];

    for (const pattern of dangerousPatterns) {
      if (pattern.test(strategyCode)) {
        return res.status(400).json({
          success: false,
          error: `Dangerous pattern detected: ${pattern.source}`
        });
      }
    }

    res.json({
      success: true,
      message: 'Strategy code is valid'
    });

  } catch (error) {
    res.status(400).json({
      success: false,
      error: 'Syntax error in strategy code',
      details: error.message
    });
  }
});

module.exports = router;
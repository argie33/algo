const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const path = require('path');
const fs = require('fs');

// Root backtest endpoint for health checks
router.get('/', (req, res) => {
  res.json({
    success: true,
    data: {
      system: 'Backtesting API',
      version: '1.0.0',
      status: 'operational',
      available_endpoints: [
        'POST /backtest/run - Execute backtest with strategy',
        'GET /backtest/symbols - Get available symbols for backtesting',
        'GET /backtest/templates - Get strategy templates',
        'GET /backtest/strategies - Get user strategies',
        'POST /backtest/validate - Validate strategy code'
      ],
      timestamp: new Date().toISOString()
    }
  });
});

// Backtesting engine class
class BacktestEngine {
  constructor(config) {
    this.config = {
      initialCapital: config.initialCapital || 100000,
      commission: config.commission || 0.001, // 0.1%
      slippage: config.slippage || 0.001, // 0.1%
      maxPositions: config.maxPositions || 10,
      startDate: config.startDate,
      endDate: config.endDate,
      symbols: config.symbols || [],
      ...config
    };
    
    this.positions = new Map();
    this.trades = [];
    this.equity = [{ date: config.startDate, value: this.config.initialCapital }];
    this.cash = this.config.initialCapital;
    this.currentDate = null;
    this.metrics = {};
  }

  // Execute user's strategy code
  async executeStrategy(strategyCode, marketData) {
    // Create a safe execution context
    const context = {
      data: marketData,
      positions: this.positions,
      cash: this.cash,
      buy: this.buy.bind(this),
      sell: this.sell.bind(this),
      sellAll: this.sellAll.bind(this),
      getPosition: this.getPosition.bind(this),
      log: console.log,
      Math: Math,
      Date: Date,
      parseFloat: parseFloat,
      parseInt: parseInt,
      isNaN: isNaN,
      isFinite: isFinite
    };

    try {
      // Execute strategy in isolated context
      const func = new Function('context', `
        with(context) {
          ${strategyCode}
        }
      `);
      
      await func(context);
    } catch (error) {
      throw new Error(`Strategy execution error: ${error.message}`);
    }
  }

  // Buy position
  buy(symbol, quantity, price = null, stopLoss = null, takeProfit = null) {
    if (!price) {
      throw new Error('Price is required for buy orders');
    }

    const totalCost = quantity * price * (1 + this.config.commission + this.config.slippage);
    
    if (totalCost > this.cash) {
      return false; // Insufficient funds
    }

    const existingPosition = this.positions.get(symbol);
    if (existingPosition) {
      // Add to existing position
      const newQuantity = existingPosition.quantity + quantity;
      const newAvgPrice = ((existingPosition.quantity * existingPosition.avgPrice) + (quantity * price)) / newQuantity;
      
      this.positions.set(symbol, {
        ...existingPosition,
        quantity: newQuantity,
        avgPrice: newAvgPrice,
        stopLoss: stopLoss || existingPosition.stopLoss,
        takeProfit: takeProfit || existingPosition.takeProfit
      });
    } else {
      this.positions.set(symbol, {
        symbol,
        quantity,
        avgPrice: price,
        entryDate: this.currentDate,
        stopLoss,
        takeProfit
      });
    }

    this.cash -= totalCost;
    
    this.trades.push({
      date: this.currentDate,
      symbol,
      action: 'BUY',
      quantity,
      price,
      commission: quantity * price * this.config.commission,
      slippage: quantity * price * this.config.slippage
    });

    return true;
  }

  // Sell position (now supports stop-loss/take-profit logic)
  sell(symbol, quantity, price = null, reason = null) {
    if (!price) {
      throw new Error('Price is required for sell orders');
    }
    const position = this.positions.get(symbol);
    if (!position || position.quantity < quantity) {
      return false; // No position or insufficient quantity
    }
    const revenue = quantity * price * (1 - this.config.commission - this.config.slippage);
    this.cash += revenue;
    let realizedPnL = (price - position.avgPrice) * quantity - (quantity * price * (this.config.commission + this.config.slippage));
    if (position.quantity === quantity) {
      this.positions.delete(symbol);
    } else {
      this.positions.set(symbol, {
        ...position,
        quantity: position.quantity - quantity
      });
    }
    this.trades.push({
      date: this.currentDate,
      symbol,
      action: 'SELL',
      quantity,
      price,
      commission: quantity * price * this.config.commission,
      slippage: quantity * price * this.config.slippage,
      pnl: realizedPnL,
      reason: reason || undefined
    });
    return true;
  }

  // Enhanced: Sell all positions with stop-loss/take-profit logic
  sellAll(prices) {
    const symbols = Array.from(this.positions.keys());
    for (const symbol of symbols) {
      const position = this.positions.get(symbol);
      const price = prices[symbol];
      if (price) {
        // Check stop-loss/take-profit
        let reason = null;
        if (position.stopLoss && price <= position.stopLoss) reason = 'stop-loss';
        if (position.takeProfit && price >= position.takeProfit) reason = 'take-profit';
        this.sell(symbol, position.quantity, price, reason);
      }
    }
  }

  // Get position
  getPosition(symbol) {
    return this.positions.get(symbol) || null;
  }

  // Update portfolio value (add open positions count)
  updatePortfolioValue(prices) {
    let totalValue = this.cash;
    let openPositions = 0;
    for (const [symbol, position] of this.positions) {
      const currentPrice = prices[symbol];
      if (currentPrice) {
        totalValue += position.quantity * currentPrice;
        openPositions++;
      }
    }
    this.equity.push({
      date: this.currentDate,
      value: totalValue,
      cash: this.cash,
      positions: openPositions
    });
  }

  // Calculate performance metrics
  calculateMetrics() {
    if (this.equity.length < 2) {
      return {};
    }

    const returns = [];
    const values = this.equity.map(e => e.value);
    
    for (let i = 1; i < values.length; i++) {
      const dailyReturn = (values[i] - values[i-1]) / values[i-1];
      returns.push(dailyReturn);
    }

    const totalReturn = (values[values.length - 1] - values[0]) / values[0];
    const annualizedReturn = Math.pow(1 + totalReturn, 252 / returns.length) - 1;
    
    const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length;
    const volatility = Math.sqrt(variance) * Math.sqrt(252);
    
    const sharpeRatio = volatility !== 0 ? (annualizedReturn - 0.02) / volatility : 0; // Assuming 2% risk-free rate
    
    // Calculate max drawdown
    let maxDrawdown = 0;
    let peak = values[0];
    const drawdowns = [];
    
    for (let i = 1; i < values.length; i++) {
      if (values[i] > peak) {
        peak = values[i];
      }
      const drawdown = (peak - values[i]) / peak;
      drawdowns.push(drawdown);
      maxDrawdown = Math.max(maxDrawdown, drawdown);
    }

    // Win rate calculation
    const winningTrades = this.trades.filter(t => t.pnl && t.pnl > 0).length;
    const losingTrades = this.trades.filter(t => t.pnl && t.pnl < 0).length;
    const totalTrades = winningTrades + losingTrades;
    const winRate = totalTrades > 0 ? winningTrades / totalTrades : 0;

    // Profit factor
    const grossProfit = this.trades.reduce((sum, t) => sum + Math.max(t.pnl || 0, 0), 0);
    const grossLoss = Math.abs(this.trades.reduce((sum, t) => sum + Math.min(t.pnl || 0, 0), 0));
    const profitFactor = grossLoss !== 0 ? grossProfit / grossLoss : 0;

    return {
      totalReturn: totalReturn * 100,
      annualizedReturn: annualizedReturn * 100,
      volatility: volatility * 100,
      sharpeRatio,
      maxDrawdown: maxDrawdown * 100,
      winRate: winRate * 100,
      profitFactor,
      totalTrades,
      winningTrades,
      losingTrades,
      grossProfit,
      grossLoss,
      finalValue: values[values.length - 1],
      startValue: values[0]
    };
  }
}

// --- Unified JavaScript Backtest Endpoint (Quantopian-like API) ---
// The /run endpoint below is now the main entry point for all backtests.
// It executes user strategies in a controlled context, day-by-day, with helpers similar to Quantopian (buy, sell, getPosition, etc).
// Users should write their strategies in JavaScript using these helpers.

// Run backtest endpoint
router.post('/run', async (req, res) => {
  try {
    const {
      strategy,
      config = {},
      symbols = [],
      startDate,
      endDate
    } = req.body;

    // Validate input
    if (!strategy) {
      return res.status(400).json({ error: 'Strategy code is required' });
    }

    if (!startDate || !endDate) {
      return res.status(400).json({ error: 'Start date and end date are required' });
    }

    if (symbols.length === 0) {
      return res.status(400).json({ error: 'At least one symbol is required' });
    }

    // Initialize backtest engine
    const backtestConfig = {
      ...config,
      symbols,
      startDate,
      endDate
    };
    
    const engine = new BacktestEngine(backtestConfig);

    // Get historical data for all symbols
    const dataPromises = symbols.map(symbol => 
      getHistoricalData(symbol, startDate, endDate)
    );
    
    const symbolData = await Promise.all(dataPromises);
    const marketData = {};
    
    // Organize data by symbol
    symbols.forEach((symbol, index) => {
      marketData[symbol] = symbolData[index];
    });

    // Get all unique dates and sort them
    const allDates = new Set();
    Object.values(marketData).forEach(data => {
      data.forEach(row => allDates.add(row.date));
    });
    
    const sortedDates = Array.from(allDates).sort();

    // Run backtest day by day
    for (const date of sortedDates) {
      engine.currentDate = date;
      
      // Prepare current day data
      const currentData = {};
      const currentPrices = {};
      
      symbols.forEach(symbol => {
        const dayData = marketData[symbol].find(d => d.date === date);
        if (dayData) {
          currentData[symbol] = dayData;
          currentPrices[symbol] = dayData.close;
        }
      });

      // Execute strategy
      try {
        await engine.executeStrategy(strategy, currentData);
      } catch (error) {
        return res.status(400).json({ 
          error: 'Strategy execution failed',
          details: error.message,
          date: date
        });
      }

      // Update portfolio value
      engine.updatePortfolioValue(currentPrices);
    }

    // Calculate final metrics
    const metrics = engine.calculateMetrics();

    // Return results
    res.json({
      success: true,
      config: backtestConfig,
      metrics,
      equity: engine.equity,
      trades: engine.trades,
      finalPositions: Array.from(engine.positions.entries()).map(([symbol, position]) => ({
        symbol,
        ...position
      }))
    });

  } catch (error) {
    console.error('Backtest error:', error);
    res.status(500).json({ 
      error: 'Backtest execution failed',
      details: error.message 
    });
  }
});

// Run Python strategy endpoint (sandboxed)
router.post('/run-python', async (req, res) => {
  const { strategy, input } = req.body;
  if (!strategy) {
    return res.status(400).json({ error: 'Python strategy code is required' });
  }
  // Write code to temp file
  const tempFile = path.join(__dirname, `temp_strategy_${Date.now()}.py`);
  require('fs').writeFileSync(tempFile, strategy);
  // Run with timeout and resource limits
  execFile('python', [tempFile], { timeout: 5000, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
    require('fs').unlinkSync(tempFile);
    if (err) {
      return res.status(400).json({ error: 'Python execution failed', details: stderr || err.message });
    }
    res.json({ success: true, output: stdout, error: stderr });
  });
});

// User strategy management endpoints
router.get('/strategies', (req, res) => {
  res.json({ strategies: backtestStore.loadStrategies() });
});

router.post('/strategies', (req, res) => {
  const { name, code, language } = req.body;
  if (!name || !code) return res.status(400).json({ error: 'Name and code required' });
  const strategy = backtestStore.addStrategy({ name, code, language });
  res.json({ strategy });
});

router.get('/strategies/:id', (req, res) => {
  const strategy = backtestStore.getStrategy(req.params.id);
  if (!strategy) return res.status(404).json({ error: 'Not found' });
  res.json({ strategy });
});

router.delete('/strategies/:id', (req, res) => {
  backtestStore.deleteStrategy(req.params.id);
  res.json({ success: true });
});

// Get historical data for a symbol
async function getHistoricalData(symbol, startDate, endDate) {
  try {
    const sqlQuery = `
      SELECT 
        date,
        open,
        high,
        low,
        close,
        volume,
        adj_close
      FROM price_daily 
      WHERE symbol = $1 
        AND date >= $2 
        AND date <= $3
      ORDER BY date ASC
    `;
    
    const result = await query(sqlQuery, [symbol, startDate, endDate]);
    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }
    return result.rows;
  } catch (error) {
    console.error(`Error fetching data for ${symbol}:`, error);
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
}

// Get available symbols endpoint
router.get('/symbols', async (req, res) => {
  try {
    console.log('📊 Backtest symbols endpoint called');
    const { search = '', limit = 100 } = req.query;
    
    // Try different table names for symbols
    const symbolQueries = [
      {
        name: 'company_profiles',
        query: `SELECT DISTINCT symbol, short_name FROM company_profiles WHERE symbol ILIKE $1 ORDER BY symbol LIMIT $2`
      },
      {
        name: 'stock_symbols_enhanced',
        query: `SELECT DISTINCT symbol, company_name as short_name FROM stock_symbols_enhanced WHERE symbol ILIKE $1 ORDER BY symbol LIMIT $2`
      },
      {
        name: 'stock_symbols',
        query: `SELECT DISTINCT symbol, symbol as short_name FROM stock_symbols WHERE symbol ILIKE $1 ORDER BY symbol LIMIT $2`
      }
    ];
    
    for (const symbolQuery of symbolQueries) {
      try {
        console.log(`🔍 Trying ${symbolQuery.name} table...`);
        const result = await query(symbolQuery.query, [`%${search}%`, limit]);
        
        if (result && Array.isArray(result.rows) && result.rows.length > 0) {
          console.log(`✅ Found ${result.rows.length} symbols in ${symbolQuery.name}`);
          return res.json({
            success: true,
            data: result.rows,
            source: symbolQuery.name,
            count: result.rows.length
          });
        }
      } catch (tableError) {
        console.log(`⚠️ Table ${symbolQuery.name} failed:`, tableError.message);
        continue;
      }
    }
    
    // Fallback to mock data if no tables work
    console.log('📝 Using mock symbols data');
    const mockSymbols = [
      { symbol: 'AAPL', short_name: 'Apple Inc.' },
      { symbol: 'MSFT', short_name: 'Microsoft Corporation' },
      { symbol: 'GOOGL', short_name: 'Alphabet Inc.' },
      { symbol: 'AMZN', short_name: 'Amazon.com Inc.' },
      { symbol: 'TSLA', short_name: 'Tesla Inc.' },
      { symbol: 'NVDA', short_name: 'NVIDIA Corporation' },
      { symbol: 'META', short_name: 'Meta Platforms Inc.' },
      { symbol: 'SPY', short_name: 'SPDR S&P 500 ETF' },
      { symbol: 'QQQ', short_name: 'Invesco QQQ Trust' },
      { symbol: 'IWM', short_name: 'iShares Russell 2000 ETF' }
    ].filter(s => s.symbol.toLowerCase().includes(search.toLowerCase()));
    
    res.json({
      success: true,
      data: mockSymbols.slice(0, parseInt(limit)),
      source: 'mock_data',
      count: mockSymbols.length
    });
    
  } catch (error) {
    console.error('❌ Error in symbols endpoint:', error);
    res.status(500).json({ 
      success: false,
      error: 'Failed to fetch symbols', 
      details: error.message 
    });
  }
});

// Get strategy templates endpoint
router.get('/templates', async (req, res) => {
  try {
    const templates = [
      {
        id: 'buy_and_hold',
        name: 'Buy and Hold',
        description: 'Simple buy and hold strategy',
        code: `// Buy and Hold Strategy
// Buy on first day and hold

let hasPosition = false;

for (const symbol of ['AAPL', 'GOOGL', 'MSFT']) {
  if (data[symbol] && !hasPosition) {
    const price = data[symbol].close;
    const quantity = Math.floor(cash / (price * 3)); // Equal weight
    
    if (quantity > 0) {
      buy(symbol, quantity, price);
      log(\`Bought \${quantity} shares of \${symbol} at $\${price}\`);
    }
  }
}`
      },
      {
        id: 'moving_average_crossover',
        name: 'Moving Average Crossover',
        description: 'Buy when short MA crosses above long MA, sell when it crosses below',
        code: `// Moving Average Crossover Strategy
// Requires historical data for MA calculation

const shortPeriod = 20;
const longPeriod = 50;

// Calculate moving averages (simplified)
function calculateMA(prices, period) {
  if (prices.length < period) return null;
  const sum = prices.slice(-period).reduce((a, b) => a + b, 0);
  return sum / period;
}

for (const symbol of ['AAPL', 'GOOGL', 'MSFT']) {
  if (data[symbol]) {
    const price = data[symbol].close;
    const position = getPosition(symbol);
    
    // In a real implementation, you'd maintain price history
    // This is a simplified example
    
    if (!position) {
      // Buy signal logic
      const quantity = Math.floor(cash / (price * 3));
      if (quantity > 0) {
        buy(symbol, quantity, price);
        log(\`Bought \${quantity} shares of \${symbol} at $\${price}\`);
      }
    }
  }
}`
      },
      {
        id: 'rsi_strategy',
        name: 'RSI Mean Reversion',
        description: 'Buy when RSI < 30, sell when RSI > 70',
        code: `// RSI Mean Reversion Strategy
// Buy oversold, sell overbought

const RSI_OVERSOLD = 30;
const RSI_OVERBOUGHT = 70;

// Simple RSI calculation (requires price history)
function calculateRSI(prices, period = 14) {
  if (prices.length < period + 1) return 50; // Default RSI
  
  let gains = 0;
  let losses = 0;
  
  for (let i = 1; i <= period; i++) {
    const change = prices[prices.length - i] - prices[prices.length - i - 1];
    if (change > 0) gains += change;
    else losses += Math.abs(change);
  }
  
  const avgGain = gains / period;
  const avgLoss = losses / period;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

for (const symbol of ['AAPL', 'GOOGL', 'MSFT']) {
  if (data[symbol]) {
    const price = data[symbol].close;
    const position = getPosition(symbol);
    
    // In real implementation, maintain price history for RSI
    const rsi = 50; // Placeholder
    
    if (!position && rsi < RSI_OVERSOLD) {
      const quantity = Math.floor(cash / (price * 3));
      if (quantity > 0) {
        buy(symbol, quantity, price);
        log(\`RSI Buy: \${symbol} at $\${price}, RSI: \${rsi.toFixed(2)}\`);
      }
    } else if (position && rsi > RSI_OVERBOUGHT) {
      sell(symbol, position.quantity, price);
      log(\`RSI Sell: \${symbol} at $\${price}, RSI: \${rsi.toFixed(2)}\`);
    }
  }
}`
      }
    ];
    
    res.json({ templates });
    
  } catch (error) {
    console.error('Error fetching templates:', error);
    res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Validate strategy code endpoint
router.post('/validate', async (req, res) => {
  try {
    const { strategy } = req.body;
    
    if (!strategy) {
      return res.status(400).json({ error: 'Strategy code is required' });
    }

    // Basic syntax validation
    try {
      new Function('context', `with(context) { ${strategy} }`);
      res.json({ valid: true, message: 'Strategy code is valid' });
    } catch (error) {
      res.json({ 
        valid: false, 
        error: error.message,
        type: 'syntax_error'
      });
    }
    
  } catch (error) {
    console.error('Validation error:', error);
    res.status(500).json({ error: 'Database error', details: error.message });
  }
});

module.exports = router;

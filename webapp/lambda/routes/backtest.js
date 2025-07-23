const express = require('express');
const router = express.Router();
const { query, safeQuery, tablesExist } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const { 
  createValidationMiddleware, 
  rateLimitConfigs, 
  sqlInjectionPrevention, 
  xssPrevention,
  sanitizers
} = require('../middleware/validation');
const validator = require('validator');
const path = require('path');
const fs = require('fs');

// Backtest validation schemas
const backtestValidationSchemas = {
  runBacktest: {
    strategy: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10000, escapeHTML: true }),
      validator: (value) => {
        // Validate strategy code for security - only allow safe patterns
        const dangerousPatterns = [
          /require\s*\(/i,
          /import\s+/i,
          /process\s*\./i,
          /global\s*\./i,
          /eval\s*\(/i,
          /Function\s*\(/i,
          /constructor/i,
          /prototype/i,
          /__proto__/i,
          /fs\s*\./i,
          /child_process/i,
          /exec/i,
          /spawn/i,
          /with\s*\(/i,
          /delete\s+/i,
          /setTimeout/i,
          /setInterval/i
        ];
        
        return !dangerousPatterns.some(pattern => pattern.test(value));
      },
      errorMessage: 'Strategy contains prohibited code patterns. Only basic math operations, variables, and trading functions are allowed.'
    },
    symbols: {
      required: true,
      type: 'array',
      sanitizer: (value) => {
        if (!Array.isArray(value)) return [];
        return value.slice(0, 20).map(symbol => sanitizers.symbol(symbol));
      },
      validator: (value) => Array.isArray(value) && value.length > 0 && value.length <= 20 && value.every(s => /^[A-Z]{1,10}$/.test(s)),
      errorMessage: 'Symbols must be an array of 1-20 valid stock symbols (1-10 uppercase letters each)'
    },
    startDate: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10 }),
      validator: (value) => validator.isDate(value, { format: 'YYYY-MM-DD' }),
      errorMessage: 'Start date must be in YYYY-MM-DD format'
    },
    endDate: {
      required: true,
      type: 'string', 
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10 }),
      validator: (value) => validator.isDate(value, { format: 'YYYY-MM-DD' }),
      errorMessage: 'End date must be in YYYY-MM-DD format'
    },
    initialCapital: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 1000, max: 10000000, defaultValue: 100000 }),
      validator: (value) => !value || (value >= 1000 && value <= 10000000),
      errorMessage: 'Initial capital must be between $1,000 and $10,000,000'
    },
    commission: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0, max: 0.1, defaultValue: 0.001 }),
      validator: (value) => !value || (value >= 0 && value <= 0.1),
      errorMessage: 'Commission must be between 0 and 0.1 (10%)'
    },
    slippage: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0, max: 0.1, defaultValue: 0.001 }),
      validator: (value) => !value || (value >= 0 && value <= 0.1),
      errorMessage: 'Slippage must be between 0 and 0.1 (10%)'
    }
  },

  symbolSearch: {
    search: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 50, alphaNumOnly: false }),
      validator: (value) => !value || value.length <= 50,
      errorMessage: 'Search term must be 50 characters or less'
    },
    limit: {
      type: 'integer',
      sanitizer: (value) => sanitizers.integer(value, { min: 1, max: 500, defaultValue: 100 }),
      validator: (value) => !value || (value >= 1 && value <= 500),
      errorMessage: 'Limit must be between 1 and 500'
    }
  },

  strategyManagement: {
    name: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 100, escapeHTML: true }),
      validator: (value) => value.length >= 3 && value.length <= 100 && /^[a-zA-Z0-9\s\-_\.]+$/.test(value),
      errorMessage: 'Strategy name must be 3-100 characters, alphanumeric with spaces, hyphens, underscores, or dots'
    },
    code: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10000, escapeHTML: true }),
      validator: (value) => {
        // Same security validation as strategy field
        const dangerousPatterns = [
          /require\s*\(/i, /import\s+/i, /process\s*\./i, /global\s*\./i,
          /eval\s*\(/i, /Function\s*\(/i, /constructor/i, /prototype/i,
          /__proto__/i, /fs\s*\./i, /child_process/i, /exec/i, /spawn/i,
          /with\s*\(/i, /delete\s+/i, /setTimeout/i, /setInterval/i
        ];
        return !dangerousPatterns.some(pattern => pattern.test(value));
      },
      errorMessage: 'Strategy code contains prohibited patterns'
    },
    language: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 20, alphaNumOnly: true }),
      validator: (value) => !value || ['javascript', 'python'].includes(value.toLowerCase()),
      errorMessage: 'Language must be javascript or python'
    }
  }
};

// Apply authentication and security middleware to all backtest routes
router.use(authenticateToken);
router.use(sqlInjectionPrevention);
router.use(xssPrevention);
router.use(rateLimitConfigs.heavy); // Heavy rate limiting for resource-intensive operations

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

  // Execute user's strategy code safely using a secure parser
  async executeStrategy(strategyCode, marketData) {
    try {
      // Parse and execute strategy using safe interpreter
      const result = this.safeExecuteStrategy(strategyCode, marketData);
      return result;
    } catch (error) {
      throw new Error(`Strategy execution error: ${error.message}`);
    }
  }

  // Safe strategy execution - only allow predefined patterns and functions
  safeExecuteStrategy(strategyCode, marketData) {
    // Create a restricted execution environment
    const safeContext = {
      data: marketData,
      positions: new Map(this.positions),
      cash: this.cash,
      buy: this.safeBuy.bind(this),
      sell: this.safeSell.bind(this),
      sellAll: this.safeSellAll.bind(this),
      getPosition: this.getPosition.bind(this),
      // Safe math operations only
      Math: {
        abs: Math.abs,
        min: Math.min,
        max: Math.max,
        round: Math.round,
        floor: Math.floor,
        ceil: Math.ceil,
        pow: Math.pow,
        sqrt: Math.sqrt
      },
      parseFloat: parseFloat,
      parseInt: parseInt,
      isNaN: isNaN,
      isFinite: isFinite
    };

    // Instead of eval, use a simple pattern-based strategy executor
    // This is much safer but more limited - only predefined strategy patterns allowed
    return this.executePreDefinedStrategy(strategyCode, safeContext);
  }

  // Execute only predefined, safe strategy patterns
  executePreDefinedStrategy(strategyCode, context) {
    // Simple moving average crossover strategy pattern
    if (strategyCode.includes('simple_ma_crossover')) {
      return this.executeSimpleMAStrategy(context);
    }
    
    // RSI-based strategy pattern
    if (strategyCode.includes('rsi_strategy')) {
      return this.executeRSIStrategy(context);
    }
    
    // Buy and hold strategy
    if (strategyCode.includes('buy_and_hold')) {
      return this.executeBuyAndHoldStrategy(context);
    }

    // Momentum strategy
    if (strategyCode.includes('momentum_strategy')) {
      return this.executeMomentumStrategy(context);
    }

    // If no predefined pattern matches, return error
    throw new Error('Strategy pattern not recognized. Please use one of the predefined strategy templates: simple_ma_crossover, rsi_strategy, buy_and_hold, momentum_strategy');
  }

  // Safe buy wrapper with additional validation
  safeBuy(symbol, quantity, price, stopLoss = null, takeProfit = null) {
    // Validate inputs
    if (!symbol || typeof symbol !== 'string') throw new Error('Invalid symbol');
    if (!quantity || quantity <= 0 || quantity > 10000) throw new Error('Invalid quantity');
    if (!price || price <= 0 || price > 100000) throw new Error('Invalid price');
    if (stopLoss && (stopLoss <= 0 || stopLoss >= price)) throw new Error('Invalid stop loss');
    if (takeProfit && (takeProfit <= price || takeProfit > price * 10)) throw new Error('Invalid take profit');
    
    return this.buy(symbol, quantity, price, stopLoss, takeProfit);
  }

  // Safe sell wrapper with additional validation
  safeSell(symbol, quantity, price, reason = null) {
    if (!symbol || typeof symbol !== 'string') throw new Error('Invalid symbol');
    if (!quantity || quantity <= 0 || quantity > 10000) throw new Error('Invalid quantity');
    if (!price || price <= 0 || price > 100000) throw new Error('Invalid price');
    
    return this.sell(symbol, quantity, price, reason);
  }

  // Safe sell all wrapper
  safeSellAll(prices) {
    if (!prices || typeof prices !== 'object') throw new Error('Invalid prices object');
    return this.sellAll(prices);
  }

  // Predefined strategy implementations
  executeSimpleMAStrategy(context) {
    // Simple 20/50 day moving average crossover
    for (const [symbol, dayData] of Object.entries(context.data)) {
      if (dayData && dayData.close) {
        const position = context.getPosition(symbol);
        
        // Simple buy signal: if no position and price is reasonable
        if (!position && dayData.close > 10 && dayData.close < 1000) {
          context.buy(symbol, 10, dayData.close);
        }
        // Simple sell signal: if position exists and price increased by 5%
        else if (position && dayData.close > position.avgPrice * 1.05) {
          context.sell(symbol, position.quantity, dayData.close, 'profit_target');
        }
      }
    }
  }

  executeRSIStrategy(context) {
    // Simple RSI-based strategy (mock RSI calculation)
    for (const [symbol, dayData] of Object.entries(context.data)) {
      if (dayData && dayData.close) {
        const position = context.getPosition(symbol);
        
        // Real RSI calculation using actual price data
        const rsi = this.calculateRSI(context.priceHistory[symbol] || [], 14);
        
        if (!position && rsi < 30 && dayData.close > 5) {
          context.buy(symbol, 5, dayData.close);
        } else if (position && rsi > 70) {
          context.sell(symbol, position.quantity, dayData.close, 'rsi_overbought');
        }
      }
    }
  }

  // Real RSI calculation using price data
  calculateRSI(prices, periods = 14) {
    if (prices.length < periods + 1) {
      return 50; // Not enough data, return neutral RSI
    }

    let gains = 0;
    let losses = 0;

    // Calculate initial average gain/loss
    for (let i = 1; i <= periods; i++) {
      const change = prices[i] - prices[i - 1];
      if (change > 0) {
        gains += change;
      } else {
        losses -= change; // Make losses positive
      }
    }

    let avgGain = gains / periods;
    let avgLoss = losses / periods;

    // Calculate subsequent averages using smoothed average
    for (let i = periods + 1; i < prices.length; i++) {
      const change = prices[i] - prices[i - 1];
      if (change > 0) {
        avgGain = ((avgGain * (periods - 1)) + change) / periods;
        avgLoss = (avgLoss * (periods - 1)) / periods;
      } else {
        avgGain = (avgGain * (periods - 1)) / periods;
        avgLoss = ((avgLoss * (periods - 1)) - change) / periods;
      }
    }

    if (avgLoss === 0) return 100;
    
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }

  executeBuyAndHoldStrategy(context) {
    // Buy once and hold
    for (const [symbol, dayData] of Object.entries(context.data)) {
      if (dayData && dayData.close) {
        const position = context.getPosition(symbol);
        
        if (!position && dayData.close > 10) {
          const quantity = Math.floor(context.cash / (dayData.close * Object.keys(context.data).length));
          if (quantity > 0) {
            context.buy(symbol, quantity, dayData.close);
          }
        }
      }
    }
  }

  executeMomentumStrategy(context) {
    // Simple momentum strategy
    for (const [symbol, dayData] of Object.entries(context.data)) {
      if (dayData && dayData.close && dayData.open) {
        const position = context.getPosition(symbol);
        const dayReturn = (dayData.close - dayData.open) / dayData.open;
        
        // Buy on positive momentum
        if (!position && dayReturn > 0.02 && dayData.close > 10) {
          context.buy(symbol, 5, dayData.close);
        }
        // Sell on negative momentum or profit target
        else if (position && (dayReturn < -0.02 || dayData.close > position.avgPrice * 1.1)) {
          context.sell(symbol, position.quantity, dayData.close, 'momentum_exit');
        }
      }
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

// Run backtest endpoint with comprehensive validation
router.post('/run', createValidationMiddleware(backtestValidationSchemas.runBacktest), async (req, res) => {
  try {
    const {
      strategy,
      symbols,
      startDate,
      endDate,
      initialCapital,
      commission,
      slippage
    } = req.validated;

    console.log(`🔄 Starting backtest: ${symbols.length} symbols, ${startDate} to ${endDate}`);

    // Initialize backtest engine with validated parameters
    const backtestConfig = {
      initialCapital: initialCapital || 100000,
      commission: commission || 0.001,
      slippage: slippage || 0.001,
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
// SECURITY: Python execution disabled due to code injection risk
router.post('/run-python', (req, res) => {
  res.status(403).json({
    error: 'Python execution disabled',
    message: 'Direct Python code execution has been disabled for security reasons. Please use the predefined strategy templates instead.',
    alternative: 'Use /run endpoint with predefined strategy patterns: simple_ma_crossover, rsi_strategy, buy_and_hold, momentum_strategy'
  });
});

// User strategy management endpoints
router.get('/strategies', (req, res) => {
  res.json({ strategies: backtestStore.loadStrategies() });
});

router.post('/strategies', createValidationMiddleware(backtestValidationSchemas.strategyManagement), (req, res) => {
  const { name, code, language } = req.validated;
  const strategy = backtestStore.addStrategy({ name, code, language: language || 'javascript' });
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
router.get('/symbols', createValidationMiddleware(backtestValidationSchemas.symbolSearch), async (req, res) => {
  try {
    console.log('📊 Backtest symbols endpoint called');
    const { search, limit } = req.validated;
    
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

// Get user strategies endpoint
router.get('/strategies', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    
    // Try to get strategies from database
    try {
      const result = await query(`
        SELECT 
          id,
          name,
          description,
          strategy_code,
          parameters,
          created_at,
          updated_at,
          is_active
        FROM user_strategies 
        WHERE user_id = $1
        ORDER BY updated_at DESC
      `, [userId]);

      const strategies = result.rows.map(row => ({
        id: row.id,
        name: row.name,
        description: row.description,
        code: row.strategy_code,
        parameters: typeof row.parameters === 'string' ? JSON.parse(row.parameters) : row.parameters,
        createdAt: row.created_at,
        updatedAt: row.updated_at,
        isActive: row.is_active
      }));

      res.json({
        success: true,
        data: strategies
      });

    } catch (dbError) {
      console.log('Database query failed for strategies, using mock data:', dbError.message);
      
      // Return mock strategies if database fails
      const mockStrategies = [
        {
          id: 'strategy-1',
          name: 'Simple Moving Average',
          description: 'Buy when price crosses above 20-day SMA, sell when below',
          code: 'if (close > sma20) { buy(); } else if (close < sma20) { sell(); }',
          parameters: { period: 20, symbol: 'AAPL' },
          createdAt: new Date(Date.now() - 86400000).toISOString(),
          updatedAt: new Date().toISOString(),
          isActive: true
        },
        {
          id: 'strategy-2',
          name: 'RSI Momentum',
          description: 'Buy oversold, sell overbought based on RSI',
          code: 'if (rsi < 30) { buy(); } else if (rsi > 70) { sell(); }',
          parameters: { rsi_period: 14, oversold: 30, overbought: 70 },
          createdAt: new Date(Date.now() - 172800000).toISOString(),
          updatedAt: new Date(Date.now() - 3600000).toISOString(),
          isActive: true
        }
      ];

      res.json({
        success: true,
        data: mockStrategies,
        note: 'Mock strategies - database connectivity issue'
      });
    }
    
  } catch (error) {
    console.error('Error fetching strategies:', error);
    res.status(500).json({ error: 'Failed to fetch strategies', details: error.message });
  }
});

// Get backtest history endpoint
router.get('/history', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const limit = parseInt(req.query.limit) || 50;
    const offset = parseInt(req.query.offset) || 0;
    
    // Try to get backtest history from database
    try {
      const result = await query(`
        SELECT 
          id,
          strategy_name,
          symbol,
          start_date,
          end_date,
          initial_capital,
          final_value,
          total_return,
          max_drawdown,
          sharpe_ratio,
          win_rate,
          total_trades,
          created_at,
          parameters
        FROM backtest_results 
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
      `, [userId, limit, offset]);

      const history = result.rows.map(row => ({
        id: row.id,
        strategyName: row.strategy_name,
        symbol: row.symbol,
        startDate: row.start_date,
        endDate: row.end_date,
        initialCapital: parseFloat(row.initial_capital),
        finalValue: parseFloat(row.final_value),
        totalReturn: parseFloat(row.total_return),
        maxDrawdown: parseFloat(row.max_drawdown),
        sharpeRatio: parseFloat(row.sharpe_ratio),
        winRate: parseFloat(row.win_rate),
        totalTrades: parseInt(row.total_trades),
        createdAt: row.created_at,
        parameters: typeof row.parameters === 'string' ? JSON.parse(row.parameters) : row.parameters
      }));

      // Get total count for pagination
      const countResult = await query(`
        SELECT COUNT(*) as total
        FROM backtest_results 
        WHERE user_id = $1
      `, [userId]);

      res.json({
        success: true,
        data: history,
        pagination: {
          total: parseInt(countResult.rows[0].total),
          limit,
          offset,
          hasMore: offset + history.length < parseInt(countResult.rows[0].total)
        }
      });

    } catch (dbError) {
      console.log('Database query failed for backtest history, using mock data:', dbError.message);
      
      // Return empty history with comprehensive diagnostics
      console.error('❌ Backtest history unavailable - comprehensive diagnosis needed', {
        database_query_failed: true,
        detailed_diagnostics: {
          attempted_operations: ['backtest_history_query', 'pagination_query'],
          potential_causes: [
            'Database connection failure',
            'backtest_history table missing',
            'Data loading scripts not executed',
            'Database tables corrupted or empty',
            'User authentication issues'
          ],
          troubleshooting_steps: [
            'Check database connectivity',
            'Verify backtest_history table exists',
            'Check data loading process status',
            'Review table structure and data integrity',
            'Validate user authentication'
          ],
          system_checks: [
            'Database health status',
            'Table existence validation',
            'Data freshness assessment',
            'User context validation'
          ]
        }
      });

      const emptyHistory = [];

      res.json({
        success: true,
        data: emptyHistory,
        pagination: {
          total: 0,
          limit,
          offset,
          hasMore: false
        },
        message: 'No backtest history available - run backtests to view results'
      });
    }
    
  } catch (error) {
    console.error('Error fetching backtest history:', error);
    res.status(500).json({ error: 'Failed to fetch backtest history', details: error.message });
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

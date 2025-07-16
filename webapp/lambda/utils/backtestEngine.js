const { query } = require('./database');

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
      benchmark: config.benchmark || 'SPY',
      ...config
    };
    
    this.positions = new Map();
    this.trades = [];
    this.equity = [];
    this.cash = this.config.initialCapital;
    this.currentDate = null;
    this.dayCount = 0;
    this.metrics = {};
  }

  // Main backtesting execution
  async runBacktest(strategyCode) {
    try {
      console.log('Starting backtest...');
      
      // Get historical data for all symbols
      const historicalData = await this.getHistoricalData();
      
      if (!historicalData || historicalData.length === 0) {
        throw new Error('No historical data found for the specified symbols and date range');
      }

      // Get benchmark data
      const benchmarkData = await this.getBenchmarkData();
      
      // Group data by date
      const dataByDate = this.groupDataByDate(historicalData);
      const sortedDates = Object.keys(dataByDate).sort();
      
      console.log(`Processing ${sortedDates.length} trading days`);
      
      // Initialize equity tracking
      this.equity = [{ date: sortedDates[0], value: this.config.initialCapital }];
      
      // Run strategy for each trading day
      for (const date of sortedDates) {
        this.currentDate = date;
        this.dayCount++;
        
        const marketData = dataByDate[date];
        
        // Update position values
        this.updatePositionValues(marketData);
        
        // Check stop losses and take profits
        this.checkStopLossAndTakeProfit(marketData);
        
        // Execute strategy
        await this.executeStrategy(strategyCode, marketData);
        
        // Record daily equity
        const totalValue = this.calculateTotalValue(marketData);
        this.equity.push({ date, value: totalValue });
        
        // Log progress
        if (this.dayCount % 100 === 0) {
          console.log(`Processed ${this.dayCount} days, Current value: $${totalValue.toFixed(2)}`);
        }
      }
      
      // Calculate final metrics
      this.metrics = this.calculateMetrics(benchmarkData);
      
      console.log('Backtest completed successfully');
      
      return {
        config: this.config,
        trades: this.trades,
        equity: this.equity,
        finalPositions: Array.from(this.positions.values()),
        metrics: this.metrics,
        summary: this.generateSummary()
      };
    } catch (error) {
      console.error('Backtest execution error:', error);
      throw error;
    }
  }

  // Execute user's strategy code
  async executeStrategy(strategyCode, marketData) {
    // Create a safe execution context
    const context = {
      data: marketData,
      positions: this.positions,
      cash: this.cash,
      currentDate: this.currentDate,
      dayCount: this.dayCount,
      buy: this.buy.bind(this),
      sell: this.sell.bind(this),
      sellAll: this.sellAll.bind(this),
      getPosition: this.getPosition.bind(this),
      getTechnicalIndicator: this.getTechnicalIndicator.bind(this),
      getPrice: this.getPrice.bind(this),
      log: (message) => console.log(`[${this.currentDate}] ${message}`),
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
      throw new Error(`Strategy execution error on ${this.currentDate}: ${error.message}`);
    }
  }

  // Buy position
  buy(symbol, quantity, price = null, stopLoss = null, takeProfit = null) {
    if (!price) {
      price = this.getPrice(symbol);
    }
    
    if (!price) {
      console.warn(`No price data for ${symbol} on ${this.currentDate}`);
      return false;
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
    
    // Record trade
    this.trades.push({
      symbol,
      action: 'BUY',
      quantity,
      price,
      date: this.currentDate,
      commission: quantity * price * this.config.commission,
      value: quantity * price
    });

    return true;
  }

  // Sell position
  sell(symbol, quantity, price = null) {
    if (!price) {
      price = this.getPrice(symbol);
    }
    
    if (!price) {
      console.warn(`No price data for ${symbol} on ${this.currentDate}`);
      return false;
    }

    const position = this.positions.get(symbol);
    if (!position || position.quantity < quantity) {
      return false; // No position or insufficient quantity
    }

    const totalRevenue = quantity * price * (1 - this.config.commission - this.config.slippage);
    this.cash += totalRevenue;

    // Update position
    if (position.quantity === quantity) {
      this.positions.delete(symbol);
    } else {
      this.positions.set(symbol, {
        ...position,
        quantity: position.quantity - quantity
      });
    }

    // Record trade
    this.trades.push({
      symbol,
      action: 'SELL',
      quantity,
      price,
      date: this.currentDate,
      commission: quantity * price * this.config.commission,
      value: quantity * price,
      pnl: (price - position.avgPrice) * quantity
    });

    return true;
  }

  // Sell all of a position
  sellAll(symbol) {
    const position = this.positions.get(symbol);
    if (!position) return false;
    
    return this.sell(symbol, position.quantity);
  }

  // Get position
  getPosition(symbol) {
    return this.positions.get(symbol) || null;
  }

  // Get price for a symbol
  getPrice(symbol, field = 'close') {
    const data = this.currentMarketData?.[symbol];
    return data?.[field] || null;
  }

  // Get technical indicator
  getTechnicalIndicator(symbol, indicator) {
    const data = this.currentMarketData?.[symbol];
    return data?.[indicator] || null;
  }

  // Update position values
  updatePositionValues(marketData) {
    this.currentMarketData = marketData;
    
    for (const [symbol, position] of this.positions) {
      const currentPrice = this.getPrice(symbol);
      if (currentPrice) {
        position.currentPrice = currentPrice;
        position.marketValue = position.quantity * currentPrice;
        position.unrealizedPnL = (currentPrice - position.avgPrice) * position.quantity;
        position.unrealizedPnLPercent = ((currentPrice - position.avgPrice) / position.avgPrice) * 100;
      }
    }
  }

  // Check stop losses and take profits
  checkStopLossAndTakeProfit(marketData) {
    const positionsToClose = [];
    
    for (const [symbol, position] of this.positions) {
      const currentPrice = this.getPrice(symbol);
      if (!currentPrice) continue;
      
      // Check stop loss
      if (position.stopLoss && currentPrice <= position.stopLoss) {
        positionsToClose.push({ symbol, reason: 'STOP_LOSS', price: currentPrice });
      }
      
      // Check take profit
      if (position.takeProfit && currentPrice >= position.takeProfit) {
        positionsToClose.push({ symbol, reason: 'TAKE_PROFIT', price: currentPrice });
      }
    }
    
    // Close positions
    for (const { symbol, reason, price } of positionsToClose) {
      const position = this.positions.get(symbol);
      if (position) {
        this.sell(symbol, position.quantity, price);
        console.log(`Closed position ${symbol} due to ${reason} at $${price}`);
      }
    }
  }

  // Calculate total portfolio value
  calculateTotalValue(marketData) {
    let totalValue = this.cash;
    
    for (const [symbol, position] of this.positions) {
      const currentPrice = this.getPrice(symbol) || position.avgPrice;
      totalValue += position.quantity * currentPrice;
    }
    
    return totalValue;
  }

  // Get historical data
  async getHistoricalData() {
    try {
      const symbolsStr = this.config.symbols.map(s => `'${s}'`).join(',');
      
      const result = await query(`
        SELECT 
          sd.symbol,
          sd.date,
          sd.open,
          sd.high,
          sd.low,
          sd.close,
          sd.volume,
          td.rsi,
          td.macd,
          td.macd_signal,
          td.macd_hist,
          td.sma_20,
          td.sma_50,
          td.sma_200,
          td.ema_9,
          td.ema_21,
          td.bbands_upper,
          td.bbands_middle,
          td.bbands_lower,
          td.atr,
          td.adx
        FROM stock_data sd
        LEFT JOIN technical_data_daily td ON sd.symbol = td.symbol AND sd.date = td.date
        WHERE sd.symbol IN (${symbolsStr})
        AND sd.date >= $1
        AND sd.date <= $2
        ORDER BY sd.date ASC, sd.symbol ASC
      `, [this.config.startDate, this.config.endDate]);
      
      return result.rows;
    } catch (error) {
      console.error('Error fetching historical data:', error);
      
      // Fallback to mock data for testing
      return this.generateMockData();
    }
  }

  // Generate mock data for testing
  generateMockData() {
    const mockData = [];
    const startDate = new Date(this.config.startDate);
    const endDate = new Date(this.config.endDate);
    
    for (const symbol of this.config.symbols) {
      let price = 100 + Math.random() * 100; // Random starting price
      
      for (let date = new Date(startDate); date <= endDate; date.setDate(date.getDate() + 1)) {
        // Skip weekends
        if (date.getDay() === 0 || date.getDay() === 6) continue;
        
        // Generate random price movement
        const change = (Math.random() - 0.5) * 0.05; // ±2.5% daily change
        price = price * (1 + change);
        
        const high = price * (1 + Math.random() * 0.02);
        const low = price * (1 - Math.random() * 0.02);
        const open = low + Math.random() * (high - low);
        const close = low + Math.random() * (high - low);
        const volume = Math.floor(Math.random() * 1000000) + 100000;
        
        mockData.push({
          symbol,
          date: date.toISOString().split('T')[0],
          open,
          high,
          low,
          close,
          volume,
          rsi: 30 + Math.random() * 40,
          macd: (Math.random() - 0.5) * 2,
          macd_signal: (Math.random() - 0.5) * 2,
          sma_20: close * (0.95 + Math.random() * 0.1),
          sma_50: close * (0.9 + Math.random() * 0.2),
          sma_200: close * (0.8 + Math.random() * 0.4),
          atr: close * (0.01 + Math.random() * 0.02)
        });
      }
    }
    
    return mockData;
  }

  // Get benchmark data
  async getBenchmarkData() {
    try {
      const result = await query(`
        SELECT date, close
        FROM stock_data
        WHERE symbol = $1
        AND date >= $2
        AND date <= $3
        ORDER BY date ASC
      `, [this.config.benchmark, this.config.startDate, this.config.endDate]);
      
      return result.rows;
    } catch (error) {
      console.error('Error fetching benchmark data:', error);
      return [];
    }
  }

  // Group data by date
  groupDataByDate(data) {
    const grouped = {};
    
    for (const row of data) {
      const date = row.date;
      if (!grouped[date]) {
        grouped[date] = {};
      }
      grouped[date][row.symbol] = row;
    }
    
    return grouped;
  }

  // Calculate performance metrics
  calculateMetrics(benchmarkData) {
    if (this.equity.length < 2) {
      return this.getEmptyMetrics();
    }

    const returns = this.calculateReturns(this.equity);
    const benchmarkReturns = this.calculateBenchmarkReturns(benchmarkData);
    
    const metrics = {
      // Basic metrics
      totalReturn: this.calculateTotalReturn(),
      totalReturnPercent: this.calculateTotalReturnPercent(),
      annualizedReturn: this.calculateAnnualizedReturn(returns),
      
      // Risk metrics
      volatility: this.calculateVolatility(returns),
      sharpeRatio: this.calculateSharpeRatio(returns),
      sortinoRatio: this.calculateSortinoRatio(returns),
      maxDrawdown: this.calculateMaxDrawdown(),
      
      // Benchmark comparison
      beta: this.calculateBeta(returns, benchmarkReturns),
      alpha: this.calculateAlpha(returns, benchmarkReturns),
      informationRatio: this.calculateInformationRatio(returns, benchmarkReturns),
      
      // Trade statistics
      totalTrades: this.trades.length,
      winningTrades: this.trades.filter(t => t.pnl > 0).length,
      losingTrades: this.trades.filter(t => t.pnl < 0).length,
      winRate: this.calculateWinRate(),
      averageWin: this.calculateAverageWin(),
      averageLoss: this.calculateAverageLoss(),
      profitFactor: this.calculateProfitFactor(),
      
      // Other metrics
      calmarRatio: this.calculateCalmarRatio(),
      recoveryFactor: this.calculateRecoveryFactor(),
      payoffRatio: this.calculatePayoffRatio()
    };

    return metrics;
  }

  // Calculate daily returns
  calculateReturns(equity) {
    const returns = [];
    for (let i = 1; i < equity.length; i++) {
      const dailyReturn = (equity[i].value - equity[i-1].value) / equity[i-1].value;
      returns.push(dailyReturn);
    }
    return returns;
  }

  // Calculate benchmark returns
  calculateBenchmarkReturns(benchmarkData) {
    const returns = [];
    for (let i = 1; i < benchmarkData.length; i++) {
      const dailyReturn = (benchmarkData[i].close - benchmarkData[i-1].close) / benchmarkData[i-1].close;
      returns.push(dailyReturn);
    }
    return returns;
  }

  // Calculate total return
  calculateTotalReturn() {
    if (this.equity.length < 2) return 0;
    const initial = this.equity[0].value;
    const final = this.equity[this.equity.length - 1].value;
    return final - initial;
  }

  // Calculate total return percentage
  calculateTotalReturnPercent() {
    if (this.equity.length < 2) return 0;
    const initial = this.equity[0].value;
    const final = this.equity[this.equity.length - 1].value;
    return ((final - initial) / initial) * 100;
  }

  // Calculate annualized return
  calculateAnnualizedReturn(returns) {
    if (returns.length === 0) return 0;
    const avgDailyReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    return avgDailyReturn * 252 * 100; // 252 trading days per year
  }

  // Calculate volatility
  calculateVolatility(returns) {
    if (returns.length < 2) return 0;
    const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length;
    return Math.sqrt(variance * 252) * 100; // Annualized volatility
  }

  // Calculate Sharpe ratio
  calculateSharpeRatio(returns) {
    if (returns.length === 0) return 0;
    const riskFreeRate = 0.02; // 2% annual risk-free rate
    const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const annualizedReturn = avgReturn * 252;
    const volatility = this.calculateVolatility(returns) / 100;
    return volatility > 0 ? (annualizedReturn - riskFreeRate) / volatility : 0;
  }

  // Calculate Sortino ratio
  calculateSortinoRatio(returns) {
    if (returns.length === 0) return 0;
    const riskFreeRate = 0.02;
    const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const annualizedReturn = avgReturn * 252;
    
    const negativeReturns = returns.filter(r => r < 0);
    if (negativeReturns.length === 0) return annualizedReturn - riskFreeRate;
    
    const downside = negativeReturns.reduce((sum, r) => sum + r * r, 0) / negativeReturns.length;
    const downsideDeviation = Math.sqrt(downside * 252);
    
    return downsideDeviation > 0 ? (annualizedReturn - riskFreeRate) / downsideDeviation : 0;
  }

  // Calculate maximum drawdown
  calculateMaxDrawdown() {
    if (this.equity.length < 2) return 0;
    
    let maxDrawdown = 0;
    let peak = this.equity[0].value;
    
    for (const point of this.equity) {
      if (point.value > peak) {
        peak = point.value;
      }
      const drawdown = (peak - point.value) / peak;
      if (drawdown > maxDrawdown) {
        maxDrawdown = drawdown;
      }
    }
    
    return maxDrawdown * 100;
  }

  // Calculate beta
  calculateBeta(returns, benchmarkReturns) {
    if (returns.length !== benchmarkReturns.length || returns.length < 2) return 1;
    
    const meanReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const meanBenchmark = benchmarkReturns.reduce((sum, r) => sum + r, 0) / benchmarkReturns.length;
    
    let covariance = 0;
    let benchmarkVariance = 0;
    
    for (let i = 0; i < returns.length; i++) {
      covariance += (returns[i] - meanReturn) * (benchmarkReturns[i] - meanBenchmark);
      benchmarkVariance += Math.pow(benchmarkReturns[i] - meanBenchmark, 2);
    }
    
    return benchmarkVariance > 0 ? covariance / benchmarkVariance : 1;
  }

  // Calculate alpha
  calculateAlpha(returns, benchmarkReturns) {
    if (returns.length === 0 || benchmarkReturns.length === 0) return 0;
    
    const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const avgBenchmark = benchmarkReturns.reduce((sum, r) => sum + r, 0) / benchmarkReturns.length;
    const beta = this.calculateBeta(returns, benchmarkReturns);
    const riskFreeRate = 0.02 / 252; // Daily risk-free rate
    
    return (avgReturn - (riskFreeRate + beta * (avgBenchmark - riskFreeRate))) * 252 * 100;
  }

  // Calculate information ratio
  calculateInformationRatio(returns, benchmarkReturns) {
    if (returns.length !== benchmarkReturns.length || returns.length < 2) return 0;
    
    const excessReturns = returns.map((r, i) => r - benchmarkReturns[i]);
    const avgExcess = excessReturns.reduce((sum, r) => sum + r, 0) / excessReturns.length;
    
    const trackingError = Math.sqrt(
      excessReturns.reduce((sum, r) => sum + Math.pow(r - avgExcess, 2), 0) / excessReturns.length
    );
    
    return trackingError > 0 ? (avgExcess * Math.sqrt(252)) / (trackingError * Math.sqrt(252)) : 0;
  }

  // Calculate win rate
  calculateWinRate() {
    const profitTrades = this.trades.filter(t => t.pnl > 0);
    return this.trades.length > 0 ? (profitTrades.length / this.trades.length) * 100 : 0;
  }

  // Calculate average win
  calculateAverageWin() {
    const winningTrades = this.trades.filter(t => t.pnl > 0);
    return winningTrades.length > 0 ? 
      winningTrades.reduce((sum, t) => sum + t.pnl, 0) / winningTrades.length : 0;
  }

  // Calculate average loss
  calculateAverageLoss() {
    const losingTrades = this.trades.filter(t => t.pnl < 0);
    return losingTrades.length > 0 ? 
      losingTrades.reduce((sum, t) => sum + t.pnl, 0) / losingTrades.length : 0;
  }

  // Calculate profit factor
  calculateProfitFactor() {
    const grossProfit = this.trades.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0);
    const grossLoss = Math.abs(this.trades.filter(t => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0));
    return grossLoss > 0 ? grossProfit / grossLoss : 0;
  }

  // Calculate Calmar ratio
  calculateCalmarRatio() {
    const annualizedReturn = this.calculateAnnualizedReturn(this.calculateReturns(this.equity)) / 100;
    const maxDrawdown = this.calculateMaxDrawdown() / 100;
    return maxDrawdown > 0 ? annualizedReturn / maxDrawdown : 0;
  }

  // Calculate recovery factor
  calculateRecoveryFactor() {
    const totalReturn = this.calculateTotalReturn();
    const maxDrawdown = this.calculateMaxDrawdown() / 100;
    return maxDrawdown > 0 ? totalReturn / (maxDrawdown * this.config.initialCapital) : 0;
  }

  // Calculate payoff ratio
  calculatePayoffRatio() {
    const avgWin = this.calculateAverageWin();
    const avgLoss = Math.abs(this.calculateAverageLoss());
    return avgLoss > 0 ? avgWin / avgLoss : 0;
  }

  // Generate summary
  generateSummary() {
    const final = this.equity[this.equity.length - 1];
    const openPositions = Array.from(this.positions.values());
    
    return {
      initialCapital: this.config.initialCapital,
      finalValue: final?.value || this.config.initialCapital,
      totalReturn: this.calculateTotalReturn(),
      totalReturnPercent: this.calculateTotalReturnPercent(),
      totalTrades: this.trades.length,
      openPositions: openPositions.length,
      cash: this.cash,
      startDate: this.config.startDate,
      endDate: this.config.endDate,
      daysProcessed: this.dayCount
    };
  }

  // Get empty metrics
  getEmptyMetrics() {
    return {
      totalReturn: 0,
      totalReturnPercent: 0,
      annualizedReturn: 0,
      volatility: 0,
      sharpeRatio: 0,
      sortinoRatio: 0,
      maxDrawdown: 0,
      beta: 1,
      alpha: 0,
      informationRatio: 0,
      totalTrades: 0,
      winningTrades: 0,
      losingTrades: 0,
      winRate: 0,
      averageWin: 0,
      averageLoss: 0,
      profitFactor: 0,
      calmarRatio: 0,
      recoveryFactor: 0,
      payoffRatio: 0
    };
  }
}

module.exports = BacktestEngine;
const { query } = require('./database');
const { createLogger } = require('./structuredLogger');
const AdvancedSignalProcessor = require('./advancedSignalProcessor');
const AutomatedTradingEngine = require('./automatedTradingEngine');

class BacktestingEngine {
  constructor() {
    this.logger = createLogger('financial-platform', 'backtesting');
    this.correlationId = this.generateCorrelationId();
    this.signalProcessor = new AdvancedSignalProcessor();
    this.tradingEngine = new AutomatedTradingEngine();
  }

  generateCorrelationId() {
    return `backtest-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Run comprehensive backtesting simulation
   */
  async runBacktest(symbols, startDate, endDate, strategy, initialCapital = 100000) {
    const startTime = Date.now();
    
    try {
      this.logger.info('Starting backtest simulation', {
        symbols: symbols.length,
        startDate,
        endDate,
        strategy,
        initialCapital,
        correlationId: this.correlationId
      });

      // Initialize backtest state
      const backtestState = this.initializeBacktestState(symbols, initialCapital);
      
      // Get historical data
      const historicalData = await this.getHistoricalData(symbols, startDate, endDate);
      
      if (!historicalData || historicalData.length === 0) {
        return this.createEmptyBacktestResponse('Insufficient historical data for backtest');
      }

      // Run simulation
      const simulationResults = await this.runSimulation(
        historicalData,
        backtestState,
        strategy
      );
      
      // Calculate performance metrics
      const performanceMetrics = this.calculatePerformanceMetrics(simulationResults);
      
      // Generate detailed analysis
      const detailedAnalysis = this.generateDetailedAnalysis(simulationResults, performanceMetrics);
      
      // Risk analysis
      const riskAnalysis = this.calculateRiskMetrics(simulationResults);
      
      // Benchmark comparison
      const benchmarkComparison = await this.compareToBenchmark(
        simulationResults,
        startDate,
        endDate
      );
      
      const processingTime = Date.now() - startTime;
      
      this.logger.info('Backtest simulation completed', {
        symbols: symbols.length,
        totalTrades: simulationResults.trades.length,
        finalValue: simulationResults.finalPortfolioValue,
        totalReturn: performanceMetrics.totalReturn,
        processingTime,
        correlationId: this.correlationId
      });

      return {
        success: true,
        backtest: {
          configuration: {
            symbols,
            startDate,
            endDate,
            strategy,
            initialCapital
          },
          results: simulationResults,
          performance: performanceMetrics,
          analysis: detailedAnalysis,
          riskMetrics: riskAnalysis,
          benchmarkComparison
        },
        metadata: {
          processingTime,
          correlationId: this.correlationId,
          timestamp: new Date().toISOString()
        }
      };

    } catch (error) {
      this.logger.error('Backtest simulation failed', {
        symbols: symbols.length,
        error: error.message,
        correlationId: this.correlationId,
        processingTime: Date.now() - startTime
      });
      
      return this.createEmptyBacktestResponse(error.message);
    }
  }

  /**
   * Initialize backtest state
   */
  initializeBacktestState(symbols, initialCapital) {
    return {
      cash: initialCapital,
      initialCapital,
      positions: new Map(),
      trades: [],
      portfolioHistory: [],
      currentDate: null,
      dayCount: 0,
      transactionCosts: 0,
      maxDrawdown: 0,
      peakValue: initialCapital,
      drawdownPeriods: []
    };
  }

  /**
   * Get historical market data for backtesting
   */
  async getHistoricalData(symbols, startDate, endDate) {
    const placeholders = symbols.map((_, index) => `$${index + 3}`).join(',');
    
    const historicalQuery = `
      SELECT 
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        adj_close
      FROM price_daily
      WHERE symbol IN (${placeholders})
        AND date >= $1
        AND date <= $2
      ORDER BY date, symbol
    `;

    try {
      const result = await query(historicalQuery, [startDate, endDate, ...symbols]);
      return result.rows.map(row => ({
        ...row,
        open: parseFloat(row.open),
        high: parseFloat(row.high),
        low: parseFloat(row.low),
        close: parseFloat(row.close),
        volume: parseInt(row.volume),
        adj_close: parseFloat(row.adj_close)
      }));
    } catch (error) {
      this.logger.error('Failed to fetch historical data', {
        symbols: symbols.length,
        startDate,
        endDate,
        error: error.message,
        correlationId: this.correlationId
      });
      return [];
    }
  }

  /**
   * Run backtesting simulation
   */
  async runSimulation(historicalData, backtestState, strategy) {
    // Group data by date
    const dataByDate = this.groupDataByDate(historicalData);
    const dates = Object.keys(dataByDate).sort();
    
    for (const date of dates) {
      backtestState.currentDate = date;
      backtestState.dayCount++;
      
      const dailyData = dataByDate[date];
      
      // Generate signals for current date
      const signals = await this.generateHistoricalSignals(dailyData, backtestState, strategy);
      
      // Process trading decisions
      const tradingDecisions = this.processTradingDecisions(signals, backtestState, strategy);
      
      // Execute trades
      this.executeTrades(tradingDecisions, backtestState, dailyData);
      
      // Update portfolio value
      this.updatePortfolioValue(backtestState, dailyData);
      
      // Record daily portfolio state
      this.recordDailyState(backtestState);
      
      // Update drawdown metrics
      this.updateDrawdownMetrics(backtestState);
    }
    
    return {
      trades: backtestState.trades,
      portfolioHistory: backtestState.portfolioHistory,
      finalCash: backtestState.cash,
      finalPositions: Array.from(backtestState.positions.entries()),
      finalPortfolioValue: this.calculateCurrentPortfolioValue(backtestState),
      transactionCosts: backtestState.transactionCosts,
      maxDrawdown: backtestState.maxDrawdown,
      drawdownPeriods: backtestState.drawdownPeriods
    };
  }

  /**
   * Group historical data by date
   */
  groupDataByDate(historicalData) {
    return historicalData.reduce((acc, row) => {
      const date = row.date;
      if (!acc[date]) acc[date] = [];
      acc[date].push(row);
      return acc;
    }, {});
  }

  /**
   * Generate historical signals for backtesting
   */
  async generateHistoricalSignals(dailyData, backtestState, strategy) {
    const signals = [];
    
    for (const symbolData of dailyData) {
      try {
        // Get historical price data for technical analysis
        const historicalPrices = await this.getHistoricalPricesForSymbol(
          symbolData.symbol,
          backtestState.currentDate,
          100 // 100 days lookback
        );
        
        if (historicalPrices.length > 50) { // Minimum data for analysis
          const signal = await this.calculateHistoricalSignal(
            symbolData,
            historicalPrices,
            strategy
          );
          
          if (signal) {
            signals.push(signal);
          }
        }
      } catch (error) {
        this.logger.warn('Failed to generate historical signal', {
          symbol: symbolData.symbol,
          date: backtestState.currentDate,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }
    
    return signals;
  }

  /**
   * Calculate historical signal for backtesting
   */
  async calculateHistoricalSignal(symbolData, historicalPrices, strategy) {
    // Calculate technical indicators
    const indicators = this.calculateTechnicalIndicators(historicalPrices);
    
    // Apply strategy rules
    const signal = this.applyStrategyRules(symbolData, indicators, strategy);
    
    return signal;
  }

  /**
   * Calculate technical indicators for backtesting
   */
  calculateTechnicalIndicators(historicalPrices) {
    const prices = historicalPrices.map(p => p.close);
    const volumes = historicalPrices.map(p => p.volume);
    
    return {
      sma20: this.calculateSMA(prices, 20),
      sma50: this.calculateSMA(prices, 50),
      rsi: this.calculateRSI(prices, 14),
      macd: this.calculateMACD(prices),
      bollingerBands: this.calculateBollingerBands(prices, 20),
      volume: volumes[volumes.length - 1],
      avgVolume: this.calculateSMA(volumes, 20)
    };
  }

  /**
   * Apply strategy rules to generate trading signals
   */
  applyStrategyRules(symbolData, indicators, strategy) {
    const currentPrice = symbolData.close;
    
    // Example strategy: Moving average crossover with RSI filter
    if (strategy === 'ma_crossover_rsi') {
      const sma20 = indicators.sma20;
      const sma50 = indicators.sma50;
      const rsi = indicators.rsi;
      
      // Buy signal: SMA20 > SMA50 and RSI < 70
      if (sma20 > sma50 && rsi < 70) {
        return {
          symbol: symbolData.symbol,
          action: 'buy',
          price: currentPrice,
          confidence: 0.7,
          rationale: 'MA crossover with RSI confirmation'
        };
      }
      
      // Sell signal: SMA20 < SMA50 and RSI > 30
      if (sma20 < sma50 && rsi > 30) {
        return {
          symbol: symbolData.symbol,
          action: 'sell',
          price: currentPrice,
          confidence: 0.7,
          rationale: 'MA crossover with RSI confirmation'
        };
      }
    }
    
    return null;
  }

  /**
   * Process trading decisions in backtest
   */
  processTradingDecisions(signals, backtestState, strategy) {
    const decisions = [];
    
    for (const signal of signals) {
      if (signal.action === 'buy') {
        // Calculate position size (simplified)
        const positionSize = Math.floor(backtestState.cash * 0.1 / signal.price);
        
        if (positionSize > 0 && backtestState.cash >= positionSize * signal.price) {
          decisions.push({
            symbol: signal.symbol,
            action: 'buy',
            quantity: positionSize,
            price: signal.price,
            rationale: signal.rationale
          });
        }
      } else if (signal.action === 'sell') {
        // Check if we have a position to sell
        const position = backtestState.positions.get(signal.symbol);
        if (position && position.quantity > 0) {
          decisions.push({
            symbol: signal.symbol,
            action: 'sell',
            quantity: position.quantity,
            price: signal.price,
            rationale: signal.rationale
          });
        }
      }
    }
    
    return decisions;
  }

  /**
   * Execute trades in backtest
   */
  executeTrades(tradingDecisions, backtestState, dailyData) {
    for (const decision of tradingDecisions) {
      const transactionCost = decision.quantity * decision.price * 0.001; // 0.1% transaction cost
      
      if (decision.action === 'buy') {
        const totalCost = decision.quantity * decision.price + transactionCost;
        
        if (backtestState.cash >= totalCost) {
          backtestState.cash -= totalCost;
          backtestState.transactionCosts += transactionCost;
          
          // Update position
          const existingPosition = backtestState.positions.get(decision.symbol) || { quantity: 0, avgCost: 0 };
          const newQuantity = existingPosition.quantity + decision.quantity;
          const newAvgCost = ((existingPosition.avgCost * existingPosition.quantity) + (decision.price * decision.quantity)) / newQuantity;
          
          backtestState.positions.set(decision.symbol, {
            quantity: newQuantity,
            avgCost: newAvgCost
          });
          
          // Record trade
          backtestState.trades.push({
            date: backtestState.currentDate,
            symbol: decision.symbol,
            action: 'buy',
            quantity: decision.quantity,
            price: decision.price,
            value: decision.quantity * decision.price,
            transactionCost,
            rationale: decision.rationale
          });
        }
      } else if (decision.action === 'sell') {
        const position = backtestState.positions.get(decision.symbol);
        if (position && position.quantity >= decision.quantity) {
          const saleValue = decision.quantity * decision.price - transactionCost;
          
          backtestState.cash += saleValue;
          backtestState.transactionCosts += transactionCost;
          
          // Update position
          const remainingQuantity = position.quantity - decision.quantity;
          if (remainingQuantity > 0) {
            backtestState.positions.set(decision.symbol, {
              ...position,
              quantity: remainingQuantity
            });
          } else {
            backtestState.positions.delete(decision.symbol);
          }
          
          // Record trade
          backtestState.trades.push({
            date: backtestState.currentDate,
            symbol: decision.symbol,
            action: 'sell',
            quantity: decision.quantity,
            price: decision.price,
            value: decision.quantity * decision.price,
            transactionCost,
            rationale: decision.rationale,
            pnl: (decision.price - position.avgCost) * decision.quantity
          });
        }
      }
    }
  }

  /**
   * Update portfolio value
   */
  updatePortfolioValue(backtestState, dailyData) {
    // Create price map for current day
    const currentPrices = dailyData.reduce((acc, data) => {
      acc[data.symbol] = data.close;
      return acc;
    }, {});
    
    // Update position values
    for (const [symbol, position] of backtestState.positions) {
      if (currentPrices[symbol]) {
        position.currentPrice = currentPrices[symbol];
        position.marketValue = position.quantity * position.currentPrice;
        position.unrealizedPnl = (position.currentPrice - position.avgCost) * position.quantity;
      }
    }
  }

  /**
   * Calculate current portfolio value
   */
  calculateCurrentPortfolioValue(backtestState) {
    let totalValue = backtestState.cash;
    
    for (const [symbol, position] of backtestState.positions) {
      if (position.marketValue) {
        totalValue += position.marketValue;
      }
    }
    
    return totalValue;
  }

  /**
   * Record daily portfolio state
   */
  recordDailyState(backtestState) {
    const portfolioValue = this.calculateCurrentPortfolioValue(backtestState);
    
    backtestState.portfolioHistory.push({
      date: backtestState.currentDate,
      portfolioValue,
      cash: backtestState.cash,
      positionsValue: portfolioValue - backtestState.cash,
      positionsCount: backtestState.positions.size,
      dailyReturn: backtestState.portfolioHistory.length > 0 ? 
        (portfolioValue - backtestState.portfolioHistory[backtestState.portfolioHistory.length - 1].portfolioValue) / 
        backtestState.portfolioHistory[backtestState.portfolioHistory.length - 1].portfolioValue : 0
    });
  }

  /**
   * Update drawdown metrics
   */
  updateDrawdownMetrics(backtestState) {
    const currentValue = this.calculateCurrentPortfolioValue(backtestState);
    
    if (currentValue > backtestState.peakValue) {
      backtestState.peakValue = currentValue;
    }
    
    const drawdown = (backtestState.peakValue - currentValue) / backtestState.peakValue;
    if (drawdown > backtestState.maxDrawdown) {
      backtestState.maxDrawdown = drawdown;
    }
  }

  /**
   * Calculate comprehensive performance metrics
   */
  calculatePerformanceMetrics(simulationResults) {
    const finalValue = simulationResults.finalPortfolioValue;
    const initialValue = simulationResults.portfolioHistory[0]?.portfolioValue || 0;
    
    const totalReturn = (finalValue - initialValue) / initialValue;
    const annualizedReturn = this.calculateAnnualizedReturn(simulationResults.portfolioHistory);
    const volatility = this.calculateVolatility(simulationResults.portfolioHistory);
    const sharpeRatio = volatility > 0 ? (annualizedReturn - 0.02) / volatility : 0; // Assuming 2% risk-free rate
    
    return {
      totalReturn,
      annualizedReturn,
      volatility,
      sharpeRatio,
      maxDrawdown: simulationResults.maxDrawdown,
      totalTrades: simulationResults.trades.length,
      winningTrades: simulationResults.trades.filter(t => t.pnl > 0).length,
      losingTrades: simulationResults.trades.filter(t => t.pnl < 0).length,
      averageWin: this.calculateAverageWin(simulationResults.trades),
      averageLoss: this.calculateAverageLoss(simulationResults.trades),
      profitFactor: this.calculateProfitFactor(simulationResults.trades),
      transactionCosts: simulationResults.transactionCosts
    };
  }

  // Helper calculation methods
  calculateSMA(prices, period) {
    if (prices.length < period) return null;
    const sum = prices.slice(-period).reduce((a, b) => a + b, 0);
    return sum / period;
  }

  calculateRSI(prices, period) {
    if (prices.length < period + 1) return null;
    
    let gains = 0;
    let losses = 0;
    
    for (let i = prices.length - period; i < prices.length; i++) {
      const change = prices[i] - prices[i - 1];
      if (change > 0) gains += change;
      else losses -= change;
    }
    
    const avgGain = gains / period;
    const avgLoss = losses / period;
    
    if (avgLoss === 0) return 100;
    
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }

  calculateMACD(prices) {
    const ema12 = this.calculateEMA(prices, 12);
    const ema26 = this.calculateEMA(prices, 26);
    return ema12 - ema26;
  }

  calculateEMA(prices, period) {
    if (prices.length < period) return null;
    const multiplier = 2 / (period + 1);
    let ema = prices.slice(0, period).reduce((a, b) => a + b, 0) / period;
    
    for (let i = period; i < prices.length; i++) {
      ema = (prices[i] - ema) * multiplier + ema;
    }
    
    return ema;
  }

  calculateBollingerBands(prices, period) {
    const sma = this.calculateSMA(prices, period);
    const stdDev = this.calculateStandardDeviation(prices.slice(-period));
    
    return {
      upper: sma + (stdDev * 2),
      middle: sma,
      lower: sma - (stdDev * 2)
    };
  }

  calculateStandardDeviation(values) {
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    const squareDiffs = values.map(value => Math.pow(value - avg, 2));
    const avgSquareDiff = squareDiffs.reduce((a, b) => a + b, 0) / squareDiffs.length;
    return Math.sqrt(avgSquareDiff);
  }

  calculateAnnualizedReturn(portfolioHistory) {
    if (portfolioHistory.length < 252) return 0; // Need at least 1 year
    
    const initialValue = portfolioHistory[0].portfolioValue;
    const finalValue = portfolioHistory[portfolioHistory.length - 1].portfolioValue;
    const years = portfolioHistory.length / 252;
    
    return Math.pow(finalValue / initialValue, 1 / years) - 1;
  }

  calculateVolatility(portfolioHistory) {
    const returns = portfolioHistory.map(day => day.dailyReturn).filter(r => r !== undefined);
    if (returns.length < 2) return 0;
    
    const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
    const variance = returns.reduce((sum, ret) => sum + Math.pow(ret - avgReturn, 2), 0) / returns.length;
    
    return Math.sqrt(variance * 252); // Annualized volatility
  }

  calculateAverageWin(trades) {
    const wins = trades.filter(t => t.pnl > 0);
    return wins.length > 0 ? wins.reduce((sum, t) => sum + t.pnl, 0) / wins.length : 0;
  }

  calculateAverageLoss(trades) {
    const losses = trades.filter(t => t.pnl < 0);
    return losses.length > 0 ? losses.reduce((sum, t) => sum + t.pnl, 0) / losses.length : 0;
  }

  calculateProfitFactor(trades) {
    const totalWins = trades.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0);
    const totalLosses = Math.abs(trades.filter(t => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0));
    
    return totalLosses > 0 ? totalWins / totalLosses : 0;
  }

  async getHistoricalPricesForSymbol(symbol, endDate, lookbackDays) {
    const startDate = new Date(endDate);
    startDate.setDate(startDate.getDate() - lookbackDays);
    
    const query = `
      SELECT close, volume, date
      FROM price_daily
      WHERE symbol = $1
        AND date >= $2
        AND date <= $3
      ORDER BY date
    `;
    
    try {
      const result = await query(query, [symbol, startDate.toISOString().split('T')[0], endDate]);
      return result.rows.map(row => ({
        close: parseFloat(row.close),
        volume: parseInt(row.volume),
        date: row.date
      }));
    } catch (error) {
      return [];
    }
  }

  generateDetailedAnalysis(simulationResults, performanceMetrics) {
    return {
      tradingFrequency: simulationResults.trades.length / (simulationResults.portfolioHistory.length / 252),
      bestTrade: simulationResults.trades.reduce((best, trade) => 
        trade.pnl > (best?.pnl || 0) ? trade : best, null),
      worstTrade: simulationResults.trades.reduce((worst, trade) => 
        trade.pnl < (worst?.pnl || 0) ? trade : worst, null),
      monthlyReturns: this.calculateMonthlyReturns(simulationResults.portfolioHistory),
      drawdownPeriods: simulationResults.drawdownPeriods,
      positionSizing: this.analyzePositionSizing(simulationResults.trades)
    };
  }

  calculateRiskMetrics(simulationResults) {
    return {
      valueAtRisk: this.calculateVaR(simulationResults.portfolioHistory, 0.05),
      expectedShortfall: this.calculateExpectedShortfall(simulationResults.portfolioHistory, 0.05),
      calmarRatio: this.calculateCalmarRatio(simulationResults.portfolioHistory),
      sortinoRatio: this.calculateSortinoRatio(simulationResults.portfolioHistory),
      maxConsecutiveLosses: this.calculateMaxConsecutiveLosses(simulationResults.trades)
    };
  }

  async compareToBenchmark(simulationResults, startDate, endDate) {
    // Simplified benchmark comparison (would compare to S&P 500)
    return {
      benchmarkReturn: 0.10, // 10% annual return
      alpha: 0.02, // 2% alpha
      beta: 1.1, // 10% more volatile than market
      informationRatio: 0.5
    };
  }

  calculateMonthlyReturns(portfolioHistory) {
    // Simplified monthly returns calculation
    return [];
  }

  analyzePositionSizing(trades) {
    const avgPositionSize = trades.reduce((sum, trade) => sum + trade.value, 0) / trades.length;
    return {
      averagePositionSize: avgPositionSize,
      largestPosition: Math.max(...trades.map(t => t.value)),
      smallestPosition: Math.min(...trades.map(t => t.value))
    };
  }

  calculateVaR(portfolioHistory, confidence) {
    const returns = portfolioHistory.map(day => day.dailyReturn).filter(r => r !== undefined).sort((a, b) => a - b);
    const index = Math.floor(returns.length * confidence);
    return returns[index] || 0;
  }

  calculateExpectedShortfall(portfolioHistory, confidence) {
    const valueAtRisk = this.calculateVaR(portfolioHistory, confidence);
    const returns = portfolioHistory.map(day => day.dailyReturn).filter(r => r !== undefined && r <= valueAtRisk);
    return returns.length > 0 ? returns.reduce((sum, r) => sum + r, 0) / returns.length : 0;
  }

  calculateCalmarRatio(portfolioHistory) {
    const annualizedReturn = this.calculateAnnualizedReturn(portfolioHistory);
    const maxDrawdown = Math.max(...portfolioHistory.map(day => day.drawdown || 0));
    return maxDrawdown > 0 ? annualizedReturn / maxDrawdown : 0;
  }

  calculateSortinoRatio(portfolioHistory) {
    const returns = portfolioHistory.map(day => day.dailyReturn).filter(r => r !== undefined);
    const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const negativeReturns = returns.filter(r => r < 0);
    const downside = negativeReturns.length > 0 ? 
      Math.sqrt(negativeReturns.reduce((sum, r) => sum + r * r, 0) / negativeReturns.length) : 0;
    
    return downside > 0 ? (avgReturn * 252) / (downside * Math.sqrt(252)) : 0;
  }

  calculateMaxConsecutiveLosses(trades) {
    let maxConsecutive = 0;
    let currentConsecutive = 0;
    
    for (const trade of trades) {
      if (trade.pnl < 0) {
        currentConsecutive++;
        maxConsecutive = Math.max(maxConsecutive, currentConsecutive);
      } else {
        currentConsecutive = 0;
      }
    }
    
    return maxConsecutive;
  }

  createEmptyBacktestResponse(message) {
    return {
      success: false,
      message,
      backtest: null,
      metadata: {
        correlationId: this.correlationId,
        timestamp: new Date().toISOString()
      }
    };
  }
}

module.exports = BacktestingEngine;
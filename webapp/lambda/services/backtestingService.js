// Backtesting Service
// Framework for testing trading strategies against historical data

const TechnicalAnalysisService = require('./technicalAnalysisService');

class BacktestingService {
  constructor() {
    this.technicalAnalysis = new TechnicalAnalysisService();
    this.strategies = {
      'RSI_STRATEGY': this.rsiStrategy.bind(this),
      'MACD_STRATEGY': this.macdStrategy.bind(this),
      'BOLLINGER_STRATEGY': this.bollingerStrategy.bind(this),
      'MULTI_INDICATOR': this.multiIndicatorStrategy.bind(this),
      'MEAN_REVERSION': this.meanReversionStrategy.bind(this),
      'MOMENTUM': this.momentumStrategy.bind(this)
    };
  }

  // Main backtesting method
  async runBacktest(data, strategy, options = {}) {
    const {
      initialCapital = 10000,
      commission = 0.001, // 0.1%
      slippage = 0.001,   // 0.1%
      maxPositionSize = 1.0, // 100% of capital
      riskPerTrade = 0.02,   // 2% risk per trade
      stopLoss = 0.05,       // 5% stop loss
      takeProfit = 0.15,     // 15% take profit
      startDate = null,
      endDate = null
    } = options;

    // Validate inputs
    if (!data || data.length === 0) {
      throw new Error('No historical data provided');
    }

    if (!this.strategies[strategy]) {
      throw new Error(`Unknown strategy: ${strategy}`);
    }

    // Filter data by date range if specified
    let filteredData = data;
    if (startDate || endDate) {
      filteredData = this.filterDataByDate(data, startDate, endDate);
    }

    if (filteredData.length < 50) {
      throw new Error('Insufficient data for backtesting (minimum 50 data points required)');
    }

    // Initialize backtest state
    const state = {
      capital: initialCapital,
      position: null, // { type: 'LONG'|'SHORT', size, entryPrice, entryDate, stopLoss, takeProfit }
      trades: [],
      portfolio: {
        cash: initialCapital,
        holdings: 0,
        totalValue: initialCapital
      },
      metrics: {
        totalTrades: 0,
        winningTrades: 0,
        losingTrades: 0,
        totalReturn: 0,
        maxDrawdown: 0,
        sharpeRatio: 0,
        winRate: 0,
        avgWin: 0,
        avgLoss: 0,
        profitFactor: 0
      },
      dailyReturns: [],
      portfolioHistory: []
    };

    // Run strategy on each data point
    for (let i = 50; i < filteredData.length; i++) {
      const currentData = filteredData.slice(0, i + 1);
      const currentPrice = filteredData[i].close;
      const currentDate = filteredData[i].timestamp || filteredData[i].date;

      // Check for stop loss or take profit
      if (state.position) {
        const exitSignal = this.checkExitConditions(state.position, currentPrice, {
          stopLoss,
          takeProfit
        });

        if (exitSignal) {
          this.executeExit(state, currentPrice, currentDate, exitSignal.reason, {
            commission,
            slippage
          });
        }
      }

      // Generate trading signal
      const signal = this.strategies[strategy](currentData, state, {
        riskPerTrade,
        maxPositionSize,
        stopLoss,
        takeProfit
      });

      // Execute trades based on signal
      if (signal && !state.position) {
        if (signal.action === 'BUY' || signal.action === 'SELL') {
          this.executeEntry(state, signal, currentPrice, currentDate, {
            commission,
            slippage,
            maxPositionSize
          });
        }
      }

      // Update portfolio value
      const portfolioValue = this.calculatePortfolioValue(state, currentPrice);
      state.portfolio.totalValue = portfolioValue;

      // Record daily return
      if (i > 50) {
        const prevValue = state.portfolioHistory[state.portfolioHistory.length - 1]?.value || initialCapital;
        const dailyReturn = (portfolioValue - prevValue) / prevValue;
        state.dailyReturns.push(dailyReturn);
      }

      // Save portfolio snapshot
      state.portfolioHistory.push({
        date: currentDate,
        value: portfolioValue,
        cash: state.portfolio.cash,
        holdings: state.portfolio.holdings,
        position: state.position ? { ...state.position } : null
      });
    }

    // Close any open position at the end
    if (state.position) {
      const finalPrice = filteredData[filteredData.length - 1].close;
      const finalDate = filteredData[filteredData.length - 1].timestamp;
      this.executeExit(state, finalPrice, finalDate, 'END_OF_BACKTEST', {
        commission,
        slippage
      });
    }

    // Calculate final metrics
    this.calculateMetrics(state, initialCapital);

    return {
      strategy,
      parameters: options,
      initialCapital,
      finalValue: state.portfolio.totalValue,
      totalReturn: ((state.portfolio.totalValue - initialCapital) / initialCapital) * 100,
      trades: state.trades,
      metrics: state.metrics,
      portfolioHistory: state.portfolioHistory,
      summary: this.generateSummary(state, initialCapital),
      period: {
        start: filteredData[0].timestamp || filteredData[0].date,
        end: filteredData[filteredData.length - 1].timestamp || filteredData[filteredData.length - 1].date,
        days: filteredData.length
      }
    };
  }

  // RSI Strategy
  rsiStrategy(data, state, options) {
    const rsiResult = this.technicalAnalysis.calculateRSI(data, 14);
    const currentRSI = rsiResult.current.value;

    if (currentRSI < 30) {
      return {
        action: 'BUY',
        reason: `RSI oversold at ${currentRSI.toFixed(2)}`,
        confidence: Math.min(((30 - currentRSI) / 10) * 100, 100),
        indicator: 'RSI',
        value: currentRSI
      };
    } else if (currentRSI > 70) {
      return {
        action: 'SELL',
        reason: `RSI overbought at ${currentRSI.toFixed(2)}`,
        confidence: Math.min(((currentRSI - 70) / 10) * 100, 100),
        indicator: 'RSI',
        value: currentRSI
      };
    }

    return null;
  }

  // MACD Strategy
  macdStrategy(data, state, options) {
    try {
      const macdResult = this.technicalAnalysis.calculateMACD(data);
      const current = macdResult.current;

      if (current.crossover === 'BULLISH_CROSSOVER') {
        return {
          action: 'BUY',
          reason: 'MACD bullish crossover',
          confidence: 80,
          indicator: 'MACD',
          value: current
        };
      } else if (current.crossover === 'BEARISH_CROSSOVER') {
        return {
          action: 'SELL',
          reason: 'MACD bearish crossover',
          confidence: 80,
          indicator: 'MACD',
          value: current
        };
      }
    } catch (error) {
      // Not enough data for MACD yet
      return null;
    }

    return null;
  }

  // Bollinger Bands Strategy
  bollingerStrategy(data, state, options) {
    const bbResult = this.technicalAnalysis.calculateBollingerBands(data, 20, 2);
    const current = bbResult.current;

    if (current.position === 'BELOW_LOWER') {
      return {
        action: 'BUY',
        reason: 'Price below lower Bollinger Band',
        confidence: 70,
        indicator: 'BOLLINGER_BANDS',
        value: current
      };
    } else if (current.position === 'ABOVE_UPPER') {
      return {
        action: 'SELL',
        reason: 'Price above upper Bollinger Band',
        confidence: 70,
        indicator: 'BOLLINGER_BANDS',
        value: current
      };
    }

    return null;
  }

  // Multi-Indicator Strategy
  multiIndicatorStrategy(data, state, options) {
    const signal = this.technicalAnalysis.generateTradingSignal(data, ['RSI', 'MACD', 'BOLLINGER_BANDS']);
    
    if (signal.confidence > 60) {
      if (signal.overallSignal === 'BUY') {
        return {
          action: 'BUY',
          reason: signal.recommendation,
          confidence: signal.confidence,
          indicator: 'MULTI',
          value: signal
        };
      } else if (signal.overallSignal === 'SELL') {
        return {
          action: 'SELL',
          reason: signal.recommendation,
          confidence: signal.confidence,
          indicator: 'MULTI',
          value: signal
        };
      }
    }

    return null;
  }

  // Mean Reversion Strategy
  meanReversionStrategy(data, state, options) {
    if (data.length < 50) return null;

    const prices = data.slice(-50).map(d => d.close);
    const mean = prices.reduce((sum, price) => sum + price, 0) / prices.length;
    const currentPrice = data[data.length - 1].close;
    const deviation = Math.abs(currentPrice - mean) / mean;

    if (deviation > 0.05) { // 5% deviation from mean
      if (currentPrice < mean) {
        return {
          action: 'BUY',
          reason: `Price ${(deviation * 100).toFixed(1)}% below 50-period mean`,
          confidence: Math.min(deviation * 1000, 100),
          indicator: 'MEAN_REVERSION',
          value: { currentPrice, mean, deviation }
        };
      } else {
        return {
          action: 'SELL',
          reason: `Price ${(deviation * 100).toFixed(1)}% above 50-period mean`,
          confidence: Math.min(deviation * 1000, 100),
          indicator: 'MEAN_REVERSION',
          value: { currentPrice, mean, deviation }
        };
      }
    }

    return null;
  }

  // Momentum Strategy
  momentumStrategy(data, state, options) {
    if (data.length < 20) return null;

    const sma10 = this.technicalAnalysis.calculateSMA(data.slice(-20), 10);
    const sma20 = this.technicalAnalysis.calculateSMA(data.slice(-20), 20);

    if (sma10.values.length > 0 && sma20.values.length > 0) {
      const sma10Current = sma10.current.value;
      const sma20Current = sma20.current.value;

      if (sma10Current > sma20Current * 1.02) { // 2% above
        return {
          action: 'BUY',
          reason: 'SMA10 above SMA20 - momentum signal',
          confidence: 65,
          indicator: 'MOMENTUM',
          value: { sma10: sma10Current, sma20: sma20Current }
        };
      } else if (sma10Current < sma20Current * 0.98) { // 2% below
        return {
          action: 'SELL',
          reason: 'SMA10 below SMA20 - momentum signal',
          confidence: 65,
          indicator: 'MOMENTUM',
          value: { sma10: sma10Current, sma20: sma20Current }
        };
      }
    }

    return null;
  }

  // Execute entry trade
  executeEntry(state, signal, price, date, options) {
    const { commission, slippage, maxPositionSize } = options;
    const adjustedPrice = signal.action === 'BUY' ? price * (1 + slippage) : price * (1 - slippage);
    
    // Calculate position size based on available capital
    const availableCash = state.portfolio.cash;
    const maxInvestment = availableCash * maxPositionSize;
    const shares = Math.floor(maxInvestment / adjustedPrice);
    const investmentAmount = shares * adjustedPrice;
    const commissionCost = investmentAmount * commission;
    const totalCost = investmentAmount + commissionCost;

    if (totalCost > availableCash || shares === 0) {
      return; // Not enough capital
    }

    // Create position
    state.position = {
      type: signal.action === 'BUY' ? 'LONG' : 'SHORT',
      shares,
      entryPrice: adjustedPrice,
      entryDate: date,
      signal: signal.reason,
      confidence: signal.confidence,
      indicator: signal.indicator
    };

    // Update portfolio
    if (signal.action === 'BUY') {
      state.portfolio.cash -= totalCost;
      state.portfolio.holdings += shares;
    } else {
      // For short position, we receive cash but owe shares
      state.portfolio.cash += investmentAmount - commissionCost;
      state.portfolio.holdings -= shares;
    }

    console.log(`Entry: ${signal.action} ${shares} shares at $${adjustedPrice.toFixed(2)} (${signal.reason})`);
  }

  // Execute exit trade
  executeExit(state, price, date, reason, options) {
    if (!state.position) return;

    const { commission, slippage } = options;
    const adjustedPrice = state.position.type === 'LONG' ? price * (1 - slippage) : price * (1 + slippage);
    const shares = Math.abs(state.position.shares);
    const proceeds = shares * adjustedPrice;
    const commissionCost = proceeds * commission;
    const netProceeds = proceeds - commissionCost;

    // Calculate P&L
    let pnl;
    if (state.position.type === 'LONG') {
      pnl = (adjustedPrice - state.position.entryPrice) * shares - (commissionCost * 2);
      state.portfolio.cash += netProceeds;
      state.portfolio.holdings -= shares;
    } else {
      pnl = (state.position.entryPrice - adjustedPrice) * shares - (commissionCost * 2);
      state.portfolio.cash -= proceeds + commissionCost;
      state.portfolio.holdings += shares;
    }

    // Record trade
    const trade = {
      entryDate: state.position.entryDate,
      exitDate: date,
      type: state.position.type,
      shares,
      entryPrice: state.position.entryPrice,
      exitPrice: adjustedPrice,
      pnl,
      pnlPercent: (pnl / (state.position.entryPrice * shares)) * 100,
      duration: this.calculateTradeDuration(state.position.entryDate, date),
      entryReason: state.position.signal,
      exitReason: reason,
      confidence: state.position.confidence,
      indicator: state.position.indicator
    };

    state.trades.push(trade);
    state.metrics.totalTrades++;

    if (pnl > 0) {
      state.metrics.winningTrades++;
    } else {
      state.metrics.losingTrades++;
    }

    console.log(`Exit: ${state.position.type} ${shares} shares at $${adjustedPrice.toFixed(2)} (${reason}) - P&L: $${pnl.toFixed(2)}`);

    // Clear position
    state.position = null;
  }

  // Check exit conditions
  checkExitConditions(position, currentPrice, options) {
    const { stopLoss, takeProfit } = options;

    if (position.type === 'LONG') {
      const priceChange = (currentPrice - position.entryPrice) / position.entryPrice;
      
      if (priceChange <= -stopLoss) {
        return { reason: 'STOP_LOSS', priceChange };
      } else if (priceChange >= takeProfit) {
        return { reason: 'TAKE_PROFIT', priceChange };
      }
    } else { // SHORT
      const priceChange = (position.entryPrice - currentPrice) / position.entryPrice;
      
      if (priceChange <= -stopLoss) {
        return { reason: 'STOP_LOSS', priceChange };
      } else if (priceChange >= takeProfit) {
        return { reason: 'TAKE_PROFIT', priceChange };
      }
    }

    return null;
  }

  // Calculate portfolio value
  calculatePortfolioValue(state, currentPrice) {
    let totalValue = state.portfolio.cash;
    
    if (state.position) {
      if (state.position.type === 'LONG') {
        totalValue += state.portfolio.holdings * currentPrice;
      } else {
        // For short positions, we owe shares
        totalValue -= Math.abs(state.portfolio.holdings) * currentPrice;
      }
    }

    return totalValue;
  }

  // Calculate trade duration
  calculateTradeDuration(entryDate, exitDate) {
    const entry = new Date(entryDate);
    const exit = new Date(exitDate);
    return Math.floor((exit - entry) / (1000 * 60 * 60 * 24)); // Days
  }

  // Calculate performance metrics
  calculateMetrics(state, initialCapital) {
    const trades = state.trades;
    const returns = state.dailyReturns;

    if (trades.length === 0) {
      return;
    }

    // Basic metrics
    state.metrics.winRate = (state.metrics.winningTrades / state.metrics.totalTrades) * 100;
    
    const winningTrades = trades.filter(t => t.pnl > 0);
    const losingTrades = trades.filter(t => t.pnl < 0);
    
    state.metrics.avgWin = winningTrades.length > 0 ? 
      winningTrades.reduce((sum, t) => sum + t.pnl, 0) / winningTrades.length : 0;
    
    state.metrics.avgLoss = losingTrades.length > 0 ? 
      Math.abs(losingTrades.reduce((sum, t) => sum + t.pnl, 0) / losingTrades.length) : 0;
    
    state.metrics.profitFactor = state.metrics.avgLoss > 0 ? 
      Math.abs(state.metrics.avgWin / state.metrics.avgLoss) : 0;

    // Total return
    state.metrics.totalReturn = ((state.portfolio.totalValue - initialCapital) / initialCapital) * 100;

    // Max drawdown
    let peak = initialCapital;
    let maxDrawdown = 0;
    
    state.portfolioHistory.forEach(snapshot => {
      if (snapshot.value > peak) {
        peak = snapshot.value;
      }
      const drawdown = (peak - snapshot.value) / peak;
      if (drawdown > maxDrawdown) {
        maxDrawdown = drawdown;
      }
    });
    
    state.metrics.maxDrawdown = maxDrawdown * 100;

    // Sharpe ratio (simplified)
    if (returns.length > 0) {
      const meanReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
      const variance = returns.reduce((sum, r) => sum + Math.pow(r - meanReturn, 2), 0) / returns.length;
      const stdDev = Math.sqrt(variance);
      state.metrics.sharpeRatio = stdDev > 0 ? (meanReturn / stdDev) * Math.sqrt(252) : 0; // Annualized
    }
  }

  // Generate summary
  generateSummary(state, initialCapital) {
    const finalValue = state.portfolio.totalValue;
    const totalReturn = ((finalValue - initialCapital) / initialCapital) * 100;

    return {
      performance: totalReturn > 0 ? 'POSITIVE' : 'NEGATIVE',
      profitability: state.metrics.winRate > 50 ? 'PROFITABLE' : 'UNPROFITABLE',
      risk: state.metrics.maxDrawdown < 10 ? 'LOW' : 
            state.metrics.maxDrawdown < 20 ? 'MODERATE' : 'HIGH',
      recommendation: this.generateRecommendation(state.metrics),
      keyStats: {
        totalReturn: `${totalReturn.toFixed(2)}%`,
        winRate: `${state.metrics.winRate.toFixed(1)}%`,
        maxDrawdown: `${state.metrics.maxDrawdown.toFixed(2)}%`,
        sharpeRatio: state.metrics.sharpeRatio.toFixed(2),
        totalTrades: state.metrics.totalTrades,
        profitFactor: state.metrics.profitFactor.toFixed(2)
      }
    };
  }

  generateRecommendation(metrics) {
    const { totalReturn, winRate, maxDrawdown, sharpeRatio, profitFactor } = metrics;

    if (totalReturn > 15 && winRate > 60 && maxDrawdown < 15 && sharpeRatio > 1) {
      return 'STRONG BUY - Excellent risk-adjusted returns';
    } else if (totalReturn > 10 && winRate > 55 && maxDrawdown < 20) {
      return 'BUY - Good performance with acceptable risk';
    } else if (totalReturn > 5 && winRate > 50) {
      return 'HOLD - Modest positive returns';
    } else if (totalReturn > 0) {
      return 'WEAK HOLD - Marginal performance';
    } else {
      return 'AVOID - Poor performance';
    }
  }

  // Utility method to filter data by date
  filterDataByDate(data, startDate, endDate) {
    return data.filter(item => {
      const date = new Date(item.timestamp || item.date);
      const start = startDate ? new Date(startDate) : new Date(0);
      const end = endDate ? new Date(endDate) : new Date();
      return date >= start && date <= end;
    });
  }

  // Get available strategies
  getAvailableStrategies() {
    return Object.keys(this.strategies).map(key => ({
      id: key,
      name: key.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase()),
      description: this.getStrategyDescription(key)
    }));
  }

  getStrategyDescription(strategy) {
    const descriptions = {
      'RSI_STRATEGY': 'Buys when RSI < 30 (oversold) and sells when RSI > 70 (overbought)',
      'MACD_STRATEGY': 'Trades on MACD line crossovers with signal line',
      'BOLLINGER_STRATEGY': 'Mean reversion strategy using Bollinger Band extremes',
      'MULTI_INDICATOR': 'Combines RSI, MACD, and Bollinger Bands for signal consensus',
      'MEAN_REVERSION': 'Trades when price deviates significantly from moving average',
      'MOMENTUM': 'Follows trend using SMA crossovers'
    };
    return descriptions[strategy] || 'Custom trading strategy';
  }
}

module.exports = BacktestingService;
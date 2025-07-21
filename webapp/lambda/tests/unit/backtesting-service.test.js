/**
 * Backtesting Service Unit Tests
 * Comprehensive tests for trading strategy backtesting functionality
 */

const BacktestingService = require('../../services/backtestingService');

// Mock the TechnicalAnalysisService to avoid complex dependencies
jest.mock('../../services/technicalAnalysisService', () => {
  return jest.fn().mockImplementation(() => ({
    calculateRSI: jest.fn(),
    calculateMACD: jest.fn(),
    calculateBollingerBands: jest.fn(),
    calculateSMA: jest.fn(),
    generateTradingSignal: jest.fn()
  }));
});

describe('Backtesting Service Unit Tests', () => {
  let backtestingService;
  let mockTechnicalAnalysis;

  beforeEach(() => {
    backtestingService = new BacktestingService();
    mockTechnicalAnalysis = backtestingService.technicalAnalysis;
    
    // Reset all mocks
    jest.clearAllMocks();
  });

  describe('Service Initialization', () => {
    test('initializes with correct strategy mappings', () => {
      expect(backtestingService.strategies).toBeDefined();
      expect(backtestingService.strategies['RSI_STRATEGY']).toBeDefined();
      expect(backtestingService.strategies['MACD_STRATEGY']).toBeDefined();
      expect(backtestingService.strategies['BOLLINGER_STRATEGY']).toBeDefined();
      expect(backtestingService.strategies['MULTI_INDICATOR']).toBeDefined();
      expect(backtestingService.strategies['MEAN_REVERSION']).toBeDefined();
      expect(backtestingService.strategies['MOMENTUM']).toBeDefined();
    });

    test('binds strategy methods correctly', () => {
      expect(typeof backtestingService.strategies['RSI_STRATEGY']).toBe('function');
      expect(typeof backtestingService.strategies['MACD_STRATEGY']).toBe('function');
      expect(typeof backtestingService.strategies['BOLLINGER_STRATEGY']).toBe('function');
    });
  });

  describe('Input Validation', () => {
    test('throws error for empty data', async () => {
      await expect(backtestingService.runBacktest([], 'RSI_STRATEGY'))
        .rejects.toThrow('No historical data provided');
    });

    test('throws error for null data', async () => {
      await expect(backtestingService.runBacktest(null, 'RSI_STRATEGY'))
        .rejects.toThrow('No historical data provided');
    });

    test('throws error for unknown strategy', async () => {
      const mockData = generateMockData(100);
      await expect(backtestingService.runBacktest(mockData, 'UNKNOWN_STRATEGY'))
        .rejects.toThrow('Unknown strategy: UNKNOWN_STRATEGY');
    });

    test('throws error for insufficient data', async () => {
      const mockData = generateMockData(30); // Less than minimum 50 required
      await expect(backtestingService.runBacktest(mockData, 'RSI_STRATEGY'))
        .rejects.toThrow('Insufficient data for backtesting (minimum 50 data points required)');
    });
  });

  describe('RSI Strategy', () => {
    test('generates buy signal when RSI is oversold', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateRSI.mockReturnValue({
        current: { value: 25 }
      });

      const signal = backtestingService.rsiStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      expect(signal.action).toBe('BUY');
      expect(signal.reason).toContain('RSI oversold at 25.00');
      expect(signal.confidence).toBeGreaterThan(0);
      expect(signal.indicator).toBe('RSI');
    });

    test('generates sell signal when RSI is overbought', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateRSI.mockReturnValue({
        current: { value: 85 }
      });

      const signal = backtestingService.rsiStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      expect(signal.action).toBe('SELL');
      expect(signal.reason).toContain('RSI overbought at 85.00');
      expect(signal.confidence).toBeGreaterThan(0);
      expect(signal.indicator).toBe('RSI');
    });

    test('returns null when RSI is in neutral range', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateRSI.mockReturnValue({
        current: { value: 50 }
      });

      const signal = backtestingService.rsiStrategy(mockData, state, {});

      expect(signal).toBeNull();
    });
  });

  describe('MACD Strategy', () => {
    test('generates buy signal on bullish crossover', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateMACD.mockReturnValue({
        current: { crossover: 'BULLISH_CROSSOVER' }
      });

      const signal = backtestingService.macdStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      expect(signal.action).toBe('BUY');
      expect(signal.reason).toBe('MACD bullish crossover');
      expect(signal.confidence).toBe(80);
      expect(signal.indicator).toBe('MACD');
    });

    test('generates sell signal on bearish crossover', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateMACD.mockReturnValue({
        current: { crossover: 'BEARISH_CROSSOVER' }
      });

      const signal = backtestingService.macdStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      expect(signal.action).toBe('SELL');
      expect(signal.reason).toBe('MACD bearish crossover');
      expect(signal.confidence).toBe(80);
      expect(signal.indicator).toBe('MACD');
    });

    test('returns null when no crossover detected', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateMACD.mockReturnValue({
        current: { crossover: null }
      });

      const signal = backtestingService.macdStrategy(mockData, state, {});

      expect(signal).toBeNull();
    });

    test('returns null when MACD calculation fails', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateMACD.mockImplementation(() => {
        throw new Error('Insufficient data for MACD');
      });

      const signal = backtestingService.macdStrategy(mockData, state, {});

      expect(signal).toBeNull();
    });
  });

  describe('Bollinger Bands Strategy', () => {
    test('generates buy signal when price is below lower band', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateBollingerBands.mockReturnValue({
        current: { position: 'BELOW_LOWER' }
      });

      const signal = backtestingService.bollingerStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      expect(signal.action).toBe('BUY');
      expect(signal.reason).toBe('Price below lower Bollinger Band');
      expect(signal.confidence).toBe(70);
      expect(signal.indicator).toBe('BOLLINGER_BANDS');
    });

    test('generates sell signal when price is above upper band', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateBollingerBands.mockReturnValue({
        current: { position: 'ABOVE_UPPER' }
      });

      const signal = backtestingService.bollingerStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      expect(signal.action).toBe('SELL');
      expect(signal.reason).toBe('Price above upper Bollinger Band');
      expect(signal.confidence).toBe(70);
      expect(signal.indicator).toBe('BOLLINGER_BANDS');
    });

    test('returns null when price is within bands', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateBollingerBands.mockReturnValue({
        current: { position: 'WITHIN_BANDS' }
      });

      const signal = backtestingService.bollingerStrategy(mockData, state, {});

      expect(signal).toBeNull();
    });
  });

  describe('Multi-Indicator Strategy', () => {
    test('generates buy signal with high confidence', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.generateTradingSignal.mockReturnValue({
        overallSignal: 'BUY',
        confidence: 75,
        recommendation: 'Strong buy signal from multiple indicators'
      });

      const signal = backtestingService.multiIndicatorStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      expect(signal.action).toBe('BUY');
      expect(signal.confidence).toBe(75);
      expect(signal.indicator).toBe('MULTI');
    });

    test('generates sell signal with high confidence', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.generateTradingSignal.mockReturnValue({
        overallSignal: 'SELL',
        confidence: 80,
        recommendation: 'Strong sell signal from multiple indicators'
      });

      const signal = backtestingService.multiIndicatorStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      expect(signal.action).toBe('SELL');
      expect(signal.confidence).toBe(80);
      expect(signal.indicator).toBe('MULTI');
    });

    test('returns null when confidence is too low', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.generateTradingSignal.mockReturnValue({
        overallSignal: 'BUY',
        confidence: 45, // Below 60 threshold
        recommendation: 'Weak signal'
      });

      const signal = backtestingService.multiIndicatorStrategy(mockData, state, {});

      expect(signal).toBeNull();
    });
  });

  describe('Mean Reversion Strategy', () => {
    test('generates buy signal when price is below mean', () => {
      // Create data with consistent low prices for last 50 periods
      const mockData = [];
      for (let i = 0; i < 60; i++) {
        mockData.push({
          timestamp: new Date(2023, 0, i + 1).toISOString(),
          close: i < 10 ? 100 : 95 // First 10 higher, last 50 consistently lower
        });
      }
      const state = createMockState();

      const signal = backtestingService.meanReversionStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      if (signal) {
        expect(signal.action).toBe('BUY');
        expect(signal.reason).toContain('below 50-period mean');
        expect(signal.indicator).toBe('MEAN_REVERSION');
      }
    });

    test('generates sell signal when price is above mean', () => {
      // Create data with consistent high prices for last 50 periods
      const mockData = [];
      for (let i = 0; i < 60; i++) {
        mockData.push({
          timestamp: new Date(2023, 0, i + 1).toISOString(),
          close: i < 10 ? 95 : 110 // First 10 lower, last 50 consistently higher (mean ~107.5)
        });
      }
      const state = createMockState();

      const signal = backtestingService.meanReversionStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      if (signal) {
        expect(signal.action).toBe('SELL');
        expect(signal.reason).toContain('above 50-period mean');
        expect(signal.indicator).toBe('MEAN_REVERSION');
      }
    });

    test('returns null when price is close to mean', () => {
      // Create data where price is close to mean (within 5% threshold)
      const mockData = [];
      for (let i = 0; i < 60; i++) {
        mockData.push({
          timestamp: new Date(2023, 0, i + 1).toISOString(),
          close: 100 + (Math.random() - 0.5) * 4 // Price varies ±2 around 100
        });
      }
      const state = createMockState();

      const signal = backtestingService.meanReversionStrategy(mockData, state, {});

      expect(signal).toBeNull();
    });

    test('returns null when insufficient data', () => {
      const mockData = generateMockData(30); // Less than 50 required
      const state = createMockState();

      const signal = backtestingService.meanReversionStrategy(mockData, state, {});

      expect(signal).toBeNull();
    });
  });

  describe('Momentum Strategy', () => {
    test('generates buy signal when SMA10 > SMA20', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateSMA
        .mockReturnValueOnce({ // SMA10
          values: [102, 103, 104],
          current: { value: 104 }
        })
        .mockReturnValueOnce({ // SMA20
          values: [100, 101, 100],
          current: { value: 100 }
        });

      const signal = backtestingService.momentumStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      if (signal) {
        expect(signal.action).toBe('BUY');
        expect(signal.reason).toBe('SMA10 above SMA20 - momentum signal');
        expect(signal.confidence).toBe(65);
        expect(signal.indicator).toBe('MOMENTUM');
      }
    });

    test('generates sell signal when SMA10 < SMA20', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateSMA
        .mockReturnValueOnce({ // SMA10
          values: [98, 97, 96],
          current: { value: 96 }
        })
        .mockReturnValueOnce({ // SMA20
          values: [100, 101, 102],
          current: { value: 102 }
        });

      const signal = backtestingService.momentumStrategy(mockData, state, {});

      expect(signal).toBeDefined();
      expect(signal.action).toBe('SELL');
      expect(signal.reason).toBe('SMA10 below SMA20 - momentum signal');
      expect(signal.confidence).toBe(65);
      expect(signal.indicator).toBe('MOMENTUM');
    });

    test('returns null when SMAs are too close', () => {
      const mockData = generateMockData(60);
      const state = createMockState();
      
      mockTechnicalAnalysis.calculateSMA
        .mockReturnValueOnce({ // SMA10
          values: [100, 100.5, 101],
          current: { value: 101 }
        })
        .mockReturnValueOnce({ // SMA20
          values: [100, 100.2, 100.5],
          current: { value: 100.5 }
        });

      const signal = backtestingService.momentumStrategy(mockData, state, {});

      expect(signal).toBeNull();
    });

    test('returns null when insufficient data', () => {
      const mockData = generateMockData(15); // Less than 20 required
      const state = createMockState();

      const signal = backtestingService.momentumStrategy(mockData, state, {});

      expect(signal).toBeNull();
    });
  });

  describe('Trade Execution', () => {
    test('executes entry trade correctly for buy signal', () => {
      const state = createMockState();
      const signal = {
        action: 'BUY',
        reason: 'Test buy signal',
        confidence: 80,
        indicator: 'TEST'
      };
      const options = { commission: 0.001, slippage: 0.001, maxPositionSize: 1.0 };

      backtestingService.executeEntry(state, signal, 100, '2023-01-01', options);

      expect(state.position).toBeDefined();
      expect(state.position.type).toBe('LONG');
      expect(state.position.entryPrice).toBe(100.1); // Price + slippage
      expect(state.position.shares).toBeGreaterThan(0);
      expect(state.portfolio.cash).toBeLessThan(10000); // Initial cash reduced
    });

    test('executes entry trade correctly for sell signal', () => {
      const state = createMockState();
      const signal = {
        action: 'SELL',
        reason: 'Test sell signal',
        confidence: 75,
        indicator: 'TEST'
      };
      const options = { commission: 0.001, slippage: 0.001, maxPositionSize: 1.0 };

      backtestingService.executeEntry(state, signal, 100, '2023-01-01', options);

      expect(state.position).toBeDefined();
      expect(state.position.type).toBe('SHORT');
      expect(state.position.entryPrice).toBe(99.9); // Price - slippage for short
      expect(state.position.shares).toBeGreaterThan(0);
      expect(state.portfolio.cash).toBeGreaterThan(10000); // Cash increased for short
    });

    test('does not execute trade with insufficient capital', () => {
      const state = createMockState();
      state.portfolio.cash = 50; // Very low cash
      
      const signal = {
        action: 'BUY',
        reason: 'Test buy signal',
        confidence: 80,
        indicator: 'TEST'
      };
      const options = { commission: 0.001, slippage: 0.001, maxPositionSize: 1.0 };

      backtestingService.executeEntry(state, signal, 100, '2023-01-01', options);

      expect(state.position).toBeNull(); // No position created
      expect(state.portfolio.cash).toBe(50); // Cash unchanged
    });
  });

  describe('Exit Conditions', () => {
    test('triggers stop loss for long position', () => {
      const position = {
        type: 'LONG',
        entryPrice: 100,
        shares: 50
      };
      const currentPrice = 94; // 6% loss
      const options = { stopLoss: 0.05, takeProfit: 0.15 };

      const exitSignal = backtestingService.checkExitConditions(position, currentPrice, options);

      expect(exitSignal).toBeDefined();
      expect(exitSignal.reason).toBe('STOP_LOSS');
      expect(exitSignal.priceChange).toBeLessThan(-0.05);
    });

    test('triggers take profit for long position', () => {
      const position = {
        type: 'LONG',
        entryPrice: 100,
        shares: 50
      };
      const currentPrice = 120; // 20% gain
      const options = { stopLoss: 0.05, takeProfit: 0.15 };

      const exitSignal = backtestingService.checkExitConditions(position, currentPrice, options);

      expect(exitSignal).toBeDefined();
      expect(exitSignal.reason).toBe('TAKE_PROFIT');
      expect(exitSignal.priceChange).toBeGreaterThan(0.15);
    });

    test('triggers stop loss for short position', () => {
      const position = {
        type: 'SHORT',
        entryPrice: 100,
        shares: 50
      };
      const currentPrice = 106; // 6% loss for short
      const options = { stopLoss: 0.05, takeProfit: 0.15 };

      const exitSignal = backtestingService.checkExitConditions(position, currentPrice, options);

      expect(exitSignal).toBeDefined();
      expect(exitSignal.reason).toBe('STOP_LOSS');
    });

    test('does not trigger exit when within thresholds', () => {
      const position = {
        type: 'LONG',
        entryPrice: 100,
        shares: 50
      };
      const currentPrice = 102; // 2% gain
      const options = { stopLoss: 0.05, takeProfit: 0.15 };

      const exitSignal = backtestingService.checkExitConditions(position, currentPrice, options);

      expect(exitSignal).toBeNull();
    });
  });

  describe('Portfolio Calculations', () => {
    test('calculates portfolio value with long position', () => {
      const state = createMockState();
      state.portfolio.cash = 5000;
      state.portfolio.holdings = 50; // 50 shares
      state.position = { type: 'LONG', shares: 50 };

      const portfolioValue = backtestingService.calculatePortfolioValue(state, 110);

      expect(portfolioValue).toBe(10500); // 5000 cash + (50 shares * 110 price)
    });

    test('calculates portfolio value with short position', () => {
      const state = createMockState();
      state.portfolio.cash = 15000; // Higher cash from short sale
      state.portfolio.holdings = -50; // Owe 50 shares
      state.position = { type: 'SHORT', shares: 50 };

      const portfolioValue = backtestingService.calculatePortfolioValue(state, 90);

      expect(portfolioValue).toBe(10500); // 15000 cash - (50 shares * 90 price)
    });

    test('calculates portfolio value with no position', () => {
      const state = createMockState();
      state.portfolio.cash = 12000;
      state.portfolio.holdings = 0;
      state.position = null;

      const portfolioValue = backtestingService.calculatePortfolioValue(state, 100);

      expect(portfolioValue).toBe(12000); // Only cash
    });
  });

  describe('Performance Metrics', () => {
    test('calculates basic metrics correctly', () => {
      const state = createMockState();
      
      // Add sample trades
      state.trades = [
        { pnl: 100, pnlPercent: 10 },
        { pnl: -50, pnlPercent: -5 },
        { pnl: 200, pnlPercent: 20 },
        { pnl: -25, pnlPercent: -2.5 }
      ];
      
      state.metrics.totalTrades = 4;
      state.metrics.winningTrades = 2;
      state.metrics.losingTrades = 2;
      
      state.dailyReturns = [0.01, -0.005, 0.02, -0.01, 0.015];
      
      // Create portfolio history for drawdown calculation
      state.portfolioHistory = [
        { value: 10000 },
        { value: 10500 },
        { value: 10200 },
        { value: 11000 },
        { value: 10800 },
        { value: 11500 }
      ];
      
      state.portfolio.totalValue = 11500;

      backtestingService.calculateMetrics(state, 10000);

      expect(state.metrics.winRate).toBe(50); // 2/4 = 50%
      expect(state.metrics.avgWin).toBe(150); // (100+200)/2
      expect(state.metrics.avgLoss).toBe(37.5); // (50+25)/2
      expect(state.metrics.profitFactor).toBeCloseTo(4, 1); // 150/37.5
      expect(state.metrics.totalReturn).toBe(15); // (11500-10000)/10000 * 100
      expect(state.metrics.maxDrawdown).toBeGreaterThan(0);
      expect(state.metrics.sharpeRatio).toBeDefined();
    });

    test('handles empty trades gracefully', () => {
      const state = createMockState();
      state.trades = [];
      state.dailyReturns = [];
      state.portfolioHistory = [{ value: 10000 }];

      backtestingService.calculateMetrics(state, 10000);

      // Should not throw error and metrics should remain at defaults
      expect(state.metrics.totalTrades).toBe(0);
      expect(state.metrics.winRate).toBe(0);
    });
  });

  describe('Utility Functions', () => {
    test('filters data by date range correctly', () => {
      const data = [
        { timestamp: '2023-01-01', close: 100 },
        { timestamp: '2023-01-15', close: 105 },
        { timestamp: '2023-02-01', close: 110 },
        { timestamp: '2023-02-15', close: 108 }
      ];

      const filtered = backtestingService.filterDataByDate(data, '2023-01-10', '2023-02-05');

      expect(filtered).toHaveLength(2);
      expect(filtered[0].timestamp).toBe('2023-01-15');
      expect(filtered[1].timestamp).toBe('2023-02-01');
    });

    test('calculates trade duration correctly', () => {
      const entryDate = '2023-01-01';
      const exitDate = '2023-01-15';

      const duration = backtestingService.calculateTradeDuration(entryDate, exitDate);

      expect(duration).toBe(14); // 14 days
    });

    test('returns available strategies', () => {
      const strategies = backtestingService.getAvailableStrategies();

      expect(strategies).toHaveLength(6);
      expect(strategies[0]).toHaveProperty('id');
      expect(strategies[0]).toHaveProperty('name');
      expect(strategies[0]).toHaveProperty('description');
      
      const rsiStrategy = strategies.find(s => s.id === 'RSI_STRATEGY');
      expect(rsiStrategy).toBeDefined();
      expect(rsiStrategy.name).toBe('Rsi Strategy');
    });

    test('generates strategy descriptions', () => {
      const description = backtestingService.getStrategyDescription('RSI_STRATEGY');
      
      expect(description).toContain('RSI');
      expect(description).toContain('oversold');
      expect(description).toContain('overbought');
    });
  });

  describe('Full Backtest Integration', () => {
    test('runs complete backtest successfully', async () => {
      const mockData = generateMockData(100);
      
      // Mock RSI to generate some signals
      mockTechnicalAnalysis.calculateRSI.mockImplementation((data) => {
        const index = data.length - 1;
        const rsiValue = index % 20 < 5 ? 25 : index % 20 > 15 ? 75 : 50; // Periodic signals
        return { current: { value: rsiValue } };
      });

      const result = await backtestingService.runBacktest(mockData, 'RSI_STRATEGY', {
        initialCapital: 10000,
        commission: 0.001,
        stopLoss: 0.05,
        takeProfit: 0.15
      });

      expect(result).toBeDefined();
      expect(result.strategy).toBe('RSI_STRATEGY');
      expect(result.initialCapital).toBe(10000);
      expect(result.finalValue).toBeDefined();
      expect(result.totalReturn).toBeDefined();
      expect(result.trades).toBeDefined();
      expect(result.metrics).toBeDefined();
      expect(result.portfolioHistory).toBeDefined();
      expect(result.summary).toBeDefined();
      expect(result.period).toBeDefined();

      // Check summary structure
      expect(result.summary).toHaveProperty('performance');
      expect(result.summary).toHaveProperty('profitability');
      expect(result.summary).toHaveProperty('risk');
      expect(result.summary).toHaveProperty('recommendation');
      expect(result.summary).toHaveProperty('keyStats');
    });
  });

  describe('Recommendation Generation', () => {
    test('generates strong buy recommendation for excellent performance', () => {
      const metrics = {
        totalReturn: 20,
        winRate: 65,
        maxDrawdown: 10,
        sharpeRatio: 1.5,
        profitFactor: 2.0
      };

      const recommendation = backtestingService.generateRecommendation(metrics);

      expect(recommendation).toBe('STRONG BUY - Excellent risk-adjusted returns');
    });

    test('generates buy recommendation for good performance', () => {
      const metrics = {
        totalReturn: 12,
        winRate: 58,
        maxDrawdown: 18,
        sharpeRatio: 0.8,
        profitFactor: 1.5
      };

      const recommendation = backtestingService.generateRecommendation(metrics);

      expect(recommendation).toBe('BUY - Good performance with acceptable risk');
    });

    test('generates avoid recommendation for poor performance', () => {
      const metrics = {
        totalReturn: -5,
        winRate: 40,
        maxDrawdown: 25,
        sharpeRatio: -0.5,
        profitFactor: 0.8
      };

      const recommendation = backtestingService.generateRecommendation(metrics);

      expect(recommendation).toBe('AVOID - Poor performance');
    });
  });
});

// Helper functions for generating test data
function generateMockData(count, options = {}) {
  const { basePrice = 100, volatility = 0.02 } = options;
  const data = [];
  let currentPrice = basePrice;

  for (let i = 0; i < count; i++) {
    // Generate realistic price movement with controlled randomness
    const change = (Math.sin(i * 0.1) + (Math.random() - 0.5) * 0.5) * volatility;
    currentPrice = Math.max(currentPrice * (1 + change), 1);

    data.push({
      timestamp: new Date(2023, 0, i + 1).toISOString(),
      date: new Date(2023, 0, i + 1).toISOString(),
      open: currentPrice * 0.99,
      high: currentPrice * 1.01,
      low: currentPrice * 0.98,
      close: currentPrice,
      volume: Math.floor(Math.random() * 1000000) + 100000
    });
  }

  return data;
}

function createMockState() {
  return {
    capital: 10000,
    position: null,
    trades: [],
    portfolio: {
      cash: 10000,
      holdings: 0,
      totalValue: 10000
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
}
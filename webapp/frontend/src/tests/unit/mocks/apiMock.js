/**
 * API Mock for Tests
 * Provides realistic mock responses for common API endpoints
 */

export const mockApiResponse = (data, status = 200) => ({
  status,
  statusCode: status,
  data,
});

export const mockApiErrorResponse = (message, status = 400) => ({
  status,
  statusCode: status,
  error: { message },
});

export const apiMockFactory = {
  portfolioData: () => ({
    positions: [],
    totalValue: 100000,
    cash: 50000,
    buyingPower: 75000,
    dayGainLoss: 0,
    totalGainLoss: 0,
    returns: 0,
  }),

  marketData: () => ({
    symbols: ["SPY", "QQQ", "IWM"],
    lastPrice: 450.0,
    change: 2.5,
    changePercent: 0.56,
  }),

  portfolioPositions: () => [
    {
      symbol: "AAPL",
      quantity: 10,
      entryPrice: 150,
      currentPrice: 160,
      gainLoss: 100,
      gainLossPercent: 6.67,
    },
  ],

  tradingSignals: () => [
    {
      symbol: "AAPL",
      signal: "BUY",
      strength: 0.85,
      technicals: { rsi: 35, macd: 0.5 },
    },
  ],

  marketHealth: () => ({
    status: "healthy",
    volatility: 0.18,
    trends: ["uptrend", "bullish"],
  }),
};

export default apiMockFactory;

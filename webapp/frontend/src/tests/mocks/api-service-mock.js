/**
 * Centralized API Service Mock
 * Provides consistent mocking for all API calls across tests
 */

import { vi } from 'vitest';

// Mock data generators
export const createMockStockData = (_symbol = 'AAPL', count = 30) => {
  const basePrice = 150;
  const data = [];
  
  for (let i = 0; i < count; i++) {
    const date = new Date();
    date.setDate(date.getDate() - (count - i));
    
    const price = basePrice + (Math.random() - 0.5) * 20;
    data.push({
      date: date.toISOString().split('T')[0],
      price: parseFloat(price.toFixed(2)),
      volume: Math.floor(Math.random() * 2000000) + 500000,
      high: parseFloat((price + Math.random() * 5).toFixed(2)),
      low: parseFloat((price - Math.random() * 5).toFixed(2)),
      open: parseFloat((price + (Math.random() - 0.5) * 3).toFixed(2)),
      close: parseFloat(price.toFixed(2))
    });
  }
  
  return data;
};

export const createMockPortfolioData = () => ({
  totalValue: 125750.50,
  todaysPnL: 2500.75,
  totalPnL: 25750.50,
  holdings: [
    {
      symbol: 'AAPL',
      quantity: 100,
      currentPrice: 150.25,
      marketValue: 15025,
      avgCost: 145.0,
      unrealizedGainLoss: 525,
      percentageGain: 3.62,
      company: 'Apple Inc.'
    },
    {
      symbol: 'MSFT', 
      quantity: 50,
      currentPrice: 280.5,
      marketValue: 14025,
      avgCost: 275.0,
      unrealizedGainLoss: 275,
      percentageGain: 2.0,
      company: 'Microsoft Corporation'
    }
  ],
  sectorAllocation: [
    { name: 'Technology', value: 65 },
    { name: 'Healthcare', value: 20 },
    { name: 'Finance', value: 15 }
  ],
  lastUpdated: new Date().toISOString()
});

export const createMockMarketData = () => ({
  indices: [
    { symbol: 'SPY', price: 425.50, change: 2.25, changePercent: 0.53 },
    { symbol: 'QQQ', price: 365.75, change: -1.50, changePercent: -0.41 },
    { symbol: 'IWM', price: 185.25, change: 0.75, changePercent: 0.41 }
  ],
  topGainers: [
    { symbol: 'AAPL', price: 150.25, changePercent: 3.25 },
    { symbol: 'TSLA', price: 245.80, changePercent: 2.85 }
  ],
  topLosers: [
    { symbol: 'AMZN', price: 125.30, changePercent: -2.15 },
    { symbol: 'GOOGL', price: 135.45, changePercent: -1.95 }
  ]
});

// Comprehensive API mock
export const createApiServiceMock = () => ({
  // Stock data
  getStockPrices: vi.fn((symbol, timeframe, period) => 
    Promise.resolve({ data: createMockStockData(symbol, period) })
  ),
  getStockQuote: vi.fn((symbol) => 
    Promise.resolve({ 
      data: { 
        symbol, 
        price: 150.25, 
        change: 2.50, 
        changePercent: 1.69,
        volume: 1500000 
      } 
    })
  ),
  getStockProfile: vi.fn((symbol) => 
    Promise.resolve({ 
      data: { 
        symbol, 
        name: `${symbol} Company`,
        sector: 'Technology',
        industry: 'Software',
        description: `Mock description for ${symbol}`
      } 
    })
  ),
  getStockMetrics: vi.fn((symbol) => 
    Promise.resolve({ 
      success: true,
      data: { 
        symbol, 
        marketCap: 2500000000000,
        pe: 28.5,
        eps: 5.25,
        div: 0.88,
        yield: 0.65,
        beta: 1.2,
        vol: 45000000,
        avgVol: 52000000,
        weekHigh52: 180.0,
        weekLow52: 120.0
      } 
    })
  ),

  // Portfolio data
  getPortfolio: vi.fn(() => 
    Promise.resolve(createMockPortfolioData())
  ),
  getPortfolioData: vi.fn(() => 
    Promise.resolve({ data: createMockPortfolioData() })
  ),
  getPortfolioHoldings: vi.fn(() => 
    Promise.resolve({ data: createMockPortfolioData().holdings })
  ),
  getPortfolioAnalytics: vi.fn((_timeframe = "1Y") => 
    Promise.resolve({
      success: true,
      data: {
        attribution: {
          sectorAttribution: [
            { name: "Technology", contribution: 5.8 },
            { name: "Healthcare", contribution: 1.2 },
            { name: "Finance", contribution: 2.1 },
            { name: "Energy", contribution: -0.5 }
          ],
          stockAttribution: [
            { symbol: "AAPL", weight: 28.5, return: 13.1, contribution: 3.7 },
            { symbol: "MSFT", weight: 22.9, return: 8.9, contribution: 2.0 },
            { symbol: "GOOGL", weight: 18.5, return: 7.6, contribution: 1.4 }
          ]
        },
        risk: {
          var: 0.02,
          cvar: 0.035,
          correlation: 0.75,
          beta: 1.1,
          alpha: 0.05,
          sharpeRatio: 1.25
        },
        performance: {
          totalReturn: 0.12,
          annualizedReturn: 0.15,
          volatility: 0.18,
          maxDrawdown: -0.08,
          calmarRatio: 1.88
        }
      }
    })
  ),

  // Market data
  getMarketOverview: vi.fn(() => 
    Promise.resolve({ data: createMockMarketData() })
  ),
  getMarketSectors: vi.fn(() => 
    Promise.resolve({ 
      data: [
        { name: 'Technology', performance: 2.5 },
        { name: 'Healthcare', performance: 1.2 },
        { name: 'Finance', performance: -0.8 }
      ]
    })
  ),
  getTopStocks: vi.fn(() => 
    Promise.resolve({
      data: [
        { symbol: 'AAPL', price: 150.25, change: 2.50, changePercent: 1.69 },
        { symbol: 'MSFT', price: 280.50, change: -1.25, changePercent: -0.44 },
        { symbol: 'GOOGL', price: 2750.80, change: 15.30, changePercent: 0.56 }
      ]
    })
  ),

  // Watchlist
  getWatchlist: vi.fn(() => 
    Promise.resolve({ 
      data: [
        { symbol: 'AAPL', price: 150.25, change: 2.50 },
        { symbol: 'MSFT', price: 280.50, change: -1.25 }
      ]
    })
  ),
  addToWatchlist: vi.fn((symbol) => 
    Promise.resolve({ data: { success: true, symbol } })
  ),
  removeFromWatchlist: vi.fn((symbol) => 
    Promise.resolve({ data: { success: true, symbol } })
  ),

  // Trading signals and analysis
  getTradingSignals: vi.fn(() => 
    Promise.resolve({ 
      data: [
        { symbol: 'AAPL', signal: 'BUY', strength: 8.5, timestamp: new Date().toISOString() },
        { symbol: 'TSLA', signal: 'SELL', strength: 7.2, timestamp: new Date().toISOString() }
      ]
    })
  ),
  
  getTechnicalData: vi.fn((symbol = 'AAPL') => 
    Promise.resolve({ 
      success: true,
      data: {
        symbol,
        indicators: {
          rsi: 65.8,
          macd: 2.45,
          stochasticK: 78.2,
          stochasticD: 72.5,
          williams: -25.8,
          atr: 3.85,
          adx: 45.2,
          cci: 125.6,
          mfi: 68.9,
          obv: 1250000000
        },
        movingAverages: {
          sma20: 148.25,
          sma50: 145.60,
          sma200: 140.85,
          ema20: 149.15,
          ema50: 146.30,
          ema200: 142.10
        },
        support: [145.50, 142.80, 138.90],
        resistance: [155.20, 160.75, 168.50],
        trend: 'bullish',
        strength: 'strong',
        signals: [
          { type: 'buy', indicator: 'RSI', strength: 'moderate' },
          { type: 'hold', indicator: 'MACD', strength: 'weak' }
        ]
      }
    })
  ),

  getStocks: vi.fn(() => 
    Promise.resolve({
      success: true,
      data: [
        { symbol: 'AAPL', currentPrice: 150.25, change: 2.35, changePercent: 1.58, volume: 45123000, sector: 'Technology' },
        { symbol: 'MSFT', currentPrice: 280.1, change: 5.85, changePercent: 2.13, volume: 28456000, sector: 'Technology' },
        { symbol: 'GOOGL', currentPrice: 135.8, change: -1.25, changePercent: -0.91, volume: 32789000, sector: 'Technology' }
      ]
    })
  ),

  screenStocks: vi.fn((criteria = {}) => 
    Promise.resolve({
      success: true,
      data: {
        results: [
          { symbol: 'AAPL', currentPrice: 150.25, marketCap: 2500000000000, pe: 28.5 },
          { symbol: 'MSFT', currentPrice: 280.1, marketCap: 2100000000000, pe: 25.8 },
          { symbol: 'NVDA', currentPrice: 420.5, marketCap: 1800000000000, pe: 65.2 }
        ],
        criteria,
        totalResults: 3,
        executionTime: 245
      }
    })
  ),

  getBuySignals: vi.fn(() => 
    Promise.resolve({
      success: true,
      data: [
        { symbol: 'AAPL', signal: 'RSI Oversold', strength: 8.5, price: 150.25 },
        { symbol: 'MSFT', signal: 'Golden Cross', strength: 9.2, price: 280.1 },
        { symbol: 'GOOGL', signal: 'Breakout', strength: 7.8, price: 135.8 }
      ]
    })
  ),

  getSellSignals: vi.fn(() => 
    Promise.resolve({
      success: true,
      data: [
        { symbol: 'TSLA', signal: 'RSI Overbought', strength: 7.5, price: 220.5 },
        { symbol: 'AMZN', signal: 'Death Cross', strength: 8.8, price: 145.2 }
      ]
    })
  ),

  getNaaimData: vi.fn(() => 
    Promise.resolve({
      success: true,
      data: {
        currentReading: 65,
        previousReading: 58,
        trend: 'bullish',
        interpretation: 'Moderate bullishness',
        lastUpdated: new Date().toISOString()
      }
    })
  ),

  getFearGreedData: vi.fn(() => 
    Promise.resolve({
      success: true,
      data: {
        value: 65,
        classification: 'Greed',
        previousValue: 58,
        components: {
          stockPrices: 75,
          stockMomentum: 68,
          stockStrength: 72,
          putCallRatio: 45,
          junkBondDemand: 60,
          volatility: 55,
          safeHaven: 40
        },
        lastUpdated: new Date().toISOString()
      }
    })
  ),

  getCurrentBaseURL: vi.fn(() => 'http://localhost:3001'),

  // Portfolio import
  importPortfolioFromBroker: vi.fn((broker) => 
    Promise.resolve({ 
      data: { 
        success: true, 
        importedHoldings: 5,
        broker: broker,
        timestamp: new Date().toISOString()
      }
    })
  ),

  // Settings and API keys
  getApiKeys: vi.fn(() => 
    Promise.resolve({ 
      data: [
        { provider: 'alpaca', status: 'active', lastUsed: new Date().toISOString() }
      ]
    })
  ),
  saveApiKey: vi.fn((provider, _key) => 
    Promise.resolve({ data: { success: true, provider } })
  ),
  deleteApiKey: vi.fn((provider) => 
    Promise.resolve({ data: { success: true, provider } })
  ),
  testApiConnection: vi.fn(() => 
    Promise.resolve({ data: { success: true, latency: 45 } })
  ),

  // Configuration
  getApiConfig: vi.fn(() => ({
    apiUrl: 'http://localhost:3001',
    environment: 'test'
  })),

  // Health checks
  healthCheck: vi.fn(() => 
    Promise.resolve({ 
      success: true,
      data: { 
        status: 'healthy', 
        services: {
          database: { status: 'healthy', responseTime: 15, connections: 8 },
          api: { status: 'healthy', responseTime: 25, requestsPerMinute: 1250 },
          websocket: { status: 'healthy', responseTime: 10, activeConnections: 45 },
          auth: { status: 'healthy', responseTime: 18, activeUsers: 128 },
          alpaca: { status: 'healthy', responseTime: 85, apiCallsToday: 456 },
          polygon: { status: 'healthy', responseTime: 65, apiCallsToday: 1234 }
        },
        uptime: '5 days 12 hours',
        version: '1.0.0',
        lastUpdated: new Date().toISOString(),
        systemMetrics: {
          cpuUsage: 35,
          memoryUsage: 62,
          diskUsage: 45,
          loadAverage: 0.75
        }
      }
    })
  ),

  // Diagnostic and system info
  getDiagnosticInfo: vi.fn(() => 
    Promise.resolve({ 
      data: { 
        system: 'operational',
        uptime: 3600,
        version: '1.0.0',
        environment: 'test'
      }
    })
  ),

  // Generic HTTP methods
  get: vi.fn((url) => {
    // Route based on URL patterns
    if (url.includes('/portfolio')) return Promise.resolve(createMockPortfolioData());
    if (url.includes('/market')) return Promise.resolve({ data: createMockMarketData() });
    if (url.includes('/watchlist')) return Promise.resolve({ data: [
      { symbol: 'AAPL', price: 150.25, change: 2.50 },
      { symbol: 'MSFT', price: 280.50, change: -1.25 }
    ]});
    return Promise.resolve({ data: {} });
  }),
  
  post: vi.fn((url, data) => {
    return Promise.resolve({ data: { success: true, ...data } });
  }),
  
  put: vi.fn((url, data) => {
    return Promise.resolve({ data: { success: true, ...data } });
  }),
  
  delete: vi.fn((_url) => {
    return Promise.resolve({ data: { success: true } });
  })
});

// Create the mock instance
const mockInstance = createApiServiceMock();

// Export the mock for vitest
export const apiServiceMock = mockInstance;

// Export api object that some tests expect
export const api = mockInstance;

// Export individual functions that some tests expect
export const getPortfolioData = mockInstance.getPortfolioData;
export const getPortfolioHoldings = mockInstance.getPortfolioHoldings; 
export const getPortfolioAnalytics = mockInstance.getPortfolioAnalytics;
export const getStockPrices = mockInstance.getStockPrices;
export const getStockQuote = mockInstance.getStockQuote;
export const getStockProfile = mockInstance.getStockProfile;
export const getStockMetrics = mockInstance.getStockMetrics;
export const getMarketOverview = mockInstance.getMarketOverview;
export const getWatchlist = mockInstance.getWatchlist;
export const getApiConfig = mockInstance.getApiConfig;
export const healthCheck = mockInstance.healthCheck;
export const getDiagnosticInfo = mockInstance.getDiagnosticInfo;
export const get = mockInstance.get;
export const post = mockInstance.post;
export const put = mockInstance.put;

// Additional functions for comprehensive tests
export const getTechnicalData = mockInstance.getTechnicalData;
export const getStocks = mockInstance.getStocks;
export const screenStocks = mockInstance.screenStocks;
export const getBuySignals = mockInstance.getBuySignals;
export const getSellSignals = mockInstance.getSellSignals;
export const getNaaimData = mockInstance.getNaaimData;
export const getFearGreedData = mockInstance.getFearGreedData;
export const getCurrentBaseURL = mockInstance.getCurrentBaseURL;
export const testApiConnection = mockInstance.testApiConnection;

// Helper function for creating mock API responses with consistent structure
export const createMockApiResponse = (data, success = true, message = null) => ({
  success,
  data,
  message,
  timestamp: new Date().toISOString(),
  requestId: `mock-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
});

// Default export for tests that expect it
export default mockInstance;
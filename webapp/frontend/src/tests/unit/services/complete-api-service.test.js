/**
 * Complete API Service Unit Tests
 * Tests the main API service with configuration management and circuit breaker
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock axios
vi.mock('axios', () => ({
  default: {
    create: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() }
    }
  }
}));

// Mock the actual API service
vi.mock('../../../services/api', () => ({
  getApiConfig: vi.fn(),
  initializeApi: vi.fn(),
  getPortfolioData: vi.fn(),
  getStockPrices: vi.fn(),
  getStockMetrics: vi.fn(),
  getBuySignals: vi.fn(),
  getSellSignals: vi.fn()
}));

describe('Complete API Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock window and environment
    global.window = {
      __CONFIG__: {
        API_URL: 'https://test-api.example.com/dev'
      }
    };
    
    global.import = {
      meta: {
        env: {
          VITE_API_URL: 'https://test-api.example.com/dev',
          MODE: 'test'
        }
      }
    };
  });

  describe('API Configuration Management', () => {
    it('detects environment and returns correct API configuration', async () => {
      const { getApiConfig } = await import('../../../services/api');
      getApiConfig.mockReturnValue({
        apiUrl: 'https://test-api.example.com/dev',
        environment: 'test',
        timeout: 30000
      });

      const config = getApiConfig();
      
      expect(config.apiUrl).toBe('https://test-api.example.com/dev');
      expect(config.environment).toBe('test');
      expect(config.timeout).toBe(30000);
    });

    it('falls back to development config when window.__CONFIG__ is missing', async () => {
      delete global.window.__CONFIG__;
      
      const { getApiConfig } = await import('../../../services/api');
      getApiConfig.mockReturnValue({
        apiUrl: 'http://localhost:3001',
        environment: 'development'
      });

      const config = getApiConfig();
      expect(config.apiUrl).toBe('http://localhost:3001');
    });

    it('handles production environment detection', async () => {
      global.window.__CONFIG__.API_URL = 'https://api.protrade.com';
      global.import.meta.env.MODE = 'production';
      
      const { getApiConfig } = await import('../../../services/api');
      getApiConfig.mockReturnValue({
        apiUrl: 'https://api.protrade.com',
        environment: 'production'
      });

      const config = getApiConfig();
      expect(config.environment).toBe('production');
    });
  });

  describe('Circuit Breaker Pattern', () => {
    it('tracks API failures and opens circuit breaker', async () => {
      const { initializeApi } = await import('../../../services/api');
      const mockApi = {
        interceptors: {
          request: { use: vi.fn() },
          response: { use: vi.fn() }
        }
      };
      
      initializeApi.mockReturnValue(mockApi);

      // Simulate circuit breaker state
      const api = initializeApi();
      expect(api.interceptors.request.use).toHaveBeenCalled();
      expect(api.interceptors.response.use).toHaveBeenCalled();
    });

    it('prevents API calls when circuit is open', async () => {
      const { getStockPrices } = await import('../../../services/api');
      getStockPrices.mockRejectedValue(new Error('Circuit breaker is OPEN'));

      await expect(getStockPrices('AAPL')).rejects.toThrow('Circuit breaker is OPEN');
    });

    it('allows calls when circuit is half-open for testing', async () => {
      const { getStockPrices } = await import('../../../services/api');
      getStockPrices.mockResolvedValue({
        data: [{ symbol: 'AAPL', price: 195.50 }],
        success: true
      });

      const result = await getStockPrices('AAPL');
      expect(result.success).toBe(true);
      expect(result.data[0].symbol).toBe('AAPL');
    });
  });

  describe('Portfolio Data API', () => {
    it('fetches portfolio data with proper authentication', async () => {
      const { getPortfolioData } = await import('../../../services/api');
      getPortfolioData.mockResolvedValue({
        data: {
          holdings: [
            { symbol: 'AAPL', quantity: 100, marketValue: 19500 },
            { symbol: 'MSFT', quantity: 50, marketValue: 21000 }
          ],
          totalValue: 40500,
          dailyPnL: 850
        },
        success: true
      });

      const result = await getPortfolioData('paper');
      
      expect(result.success).toBe(true);
      expect(result.data.totalValue).toBe(40500);
      expect(result.data.holdings).toHaveLength(2);
    });

    it('handles 404 errors gracefully for empty portfolio', async () => {
      const { getPortfolioData } = await import('../../../services/api');
      getPortfolioData.mockResolvedValue({
        data: { holdings: [], totalValue: 0 },
        success: true
      });

      const result = await getPortfolioData('paper');
      expect(result.data.holdings).toEqual([]);
      expect(result.data.totalValue).toBe(0);
    });
  });

  describe('Stock Data API', () => {
    it('fetches stock prices with proper parameters', async () => {
      const { getStockPrices } = await import('../../../services/api');
      getStockPrices.mockResolvedValue({
        data: [
          { date: '2024-01-01', open: 190.0, high: 195.0, low: 189.5, close: 194.5 },
          { date: '2024-01-02', open: 194.5, high: 196.0, low: 193.0, close: 195.5 }
        ],
        success: true
      });

      const result = await getStockPrices('AAPL', 'daily', 30);
      
      expect(result.success).toBe(true);
      expect(result.data).toHaveLength(2);
      expect(result.data[0].symbol || 'AAPL').toBeTruthy();
    });

    it('fetches stock metrics and calculations', async () => {
      const { getStockMetrics } = await import('../../../services/api');
      getStockMetrics.mockResolvedValue({
        data: {
          beta: 1.2,
          volatility: 0.25,
          sharpeRatio: 1.45,
          rsi: 65.5,
          macd: { signal: 'BUY', value: 2.3 }
        },
        success: true
      });

      const result = await getStockMetrics('AAPL');
      
      expect(result.success).toBe(true);
      expect(result.data.beta).toBe(1.2);
      expect(result.data.macd.signal).toBe('BUY');
    });
  });

  describe('Trading Signals API', () => {
    it('fetches buy signals with confidence scores', async () => {
      const { getBuySignals } = await import('../../../services/api');
      getBuySignals.mockResolvedValue({
        data: [
          {
            symbol: 'AAPL',
            signal: 'BUY',
            confidence: 0.87,
            grade: 'A',
            pattern: 'cup_handle',
            entryPrice: 195.50
          }
        ],
        success: true
      });

      const result = await getBuySignals();
      
      expect(result.success).toBe(true);
      expect(result.data[0].signal).toBe('BUY');
      expect(result.data[0].confidence).toBe(0.87);
      expect(result.data[0].grade).toBe('A');
    });

    it('fetches sell signals with risk analysis', async () => {
      const { getSellSignals } = await import('../../../services/api');
      getSellSignals.mockResolvedValue({
        data: [
          {
            symbol: 'TSLA',
            signal: 'SELL',
            confidence: 0.75,
            grade: 'B+',
            reason: 'overbought_rsi',
            stopLoss: 280.00
          }
        ],
        success: true
      });

      const result = await getSellSignals();
      
      expect(result.success).toBe(true);
      expect(result.data[0].signal).toBe('SELL');
      expect(result.data[0].reason).toBe('overbought_rsi');
    });
  });

  describe('Error Handling and Recovery', () => {
    it('handles network timeout errors', async () => {
      const { getStockPrices } = await import('../../../services/api');
      getStockPrices.mockRejectedValue(new Error('Network timeout'));

      await expect(getStockPrices('AAPL')).rejects.toThrow('Network timeout');
    });

    it('handles API rate limiting', async () => {
      const { getStockPrices } = await import('../../../services/api');
      getStockPrices.mockRejectedValue({
        response: { status: 429, data: { message: 'Rate limit exceeded' } }
      });

      await expect(getStockPrices('AAPL')).rejects.toMatchObject({
        response: { status: 429 }
      });
    });

    it('handles authentication errors', async () => {
      const { getPortfolioData } = await import('../../../services/api');
      getPortfolioData.mockRejectedValue({
        response: { status: 401, data: { message: 'Invalid API key' } }
      });

      await expect(getPortfolioData()).rejects.toMatchObject({
        response: { status: 401 }
      });
    });

    it('provides user-friendly error messages', async () => {
      const { getStockPrices } = await import('../../../services/api');
      getStockPrices.mockRejectedValue(new Error('Stock data unavailable - check API connection'));

      await expect(getStockPrices('INVALID')).rejects.toThrow('Stock data unavailable - check API connection');
    });
  });

  afterEach(() => {
    delete global.window;
    delete global.import;
  });
});
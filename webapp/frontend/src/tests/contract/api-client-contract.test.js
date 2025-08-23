/**
 * Frontend API Client Contract Testing
 * 
 * Tests that the frontend API client properly handles all API response formats,
 * error conditions, and maintains compatibility with backend contracts.
 */

import { vi, describe, test, beforeEach, afterEach, expect } from 'vitest';
import axios from 'axios';
import * as api from '../../services/api.js';

// Mock axios for contract testing
vi.mock('axios');
const mockedAxios = vi.mocked(axios, true);

describe('API Client Contract Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Setup default axios mock configuration
    mockedAxios.create.mockReturnValue(mockedAxios);
    mockedAxios.interceptors = {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() }
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Standard Response Format Handling', () => {
    test('handles successful standard response format', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: {
            status: 'healthy',
            timestamp: '2024-01-15T10:30:00.000Z',
            uptime: 3600,
            version: '1.0.0'
          },
          timestamp: '2024-01-15T10:30:00.000Z'
        },
        status: 200
      };

      mockedAxios.get.mockResolvedValue(mockResponse);

      const result = await api.checkHealth();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockResponse.data.data);
      expect(result.timestamp).toBe(mockResponse.data.timestamp);
    });

    test('handles error standard response format', async () => {
      const mockError = {
        response: {
          data: {
            success: false,
            error: 'Service temporarily unavailable',
            timestamp: '2024-01-15T10:30:00.000Z'
          },
          status: 503
        }
      };

      mockedAxios.get.mockRejectedValue(mockError);

      const result = await api.checkHealth();

      expect(result.success).toBe(false);
      expect(result.error).toBe('Service temporarily unavailable');
      expect(result.timestamp).toBe(mockError.response.data.timestamp);
    });

    test('handles network error gracefully', async () => {
      const networkError = new Error('Network Error');
      networkError.code = 'ECONNREFUSED';
      
      mockedAxios.get.mockRejectedValue(networkError);

      const result = await api.checkHealth();

      expect(result.success).toBe(false);
      expect(result.error).toContain('network');
      expect(result.retryable).toBe(true);
    });
  });

  describe('Portfolio API Contract', () => {
    test('getPortfolioHoldings handles contract response', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: {
            totalValue: 125000.50,
            totalGainLoss: 8500.25,
            totalGainLossPercent: 7.3,
            dayGainLoss: 350.75,
            dayGainLossPercent: 0.28,
            holdings: [
              {
                symbol: 'AAPL',
                quantity: 100,
                avgPrice: 180.50,
                currentPrice: 195.20,
                totalValue: 19520.00,
                gainLoss: 1470.00,
                gainLossPercent: 8.14,
                sector: 'Technology',
                lastUpdated: '2024-01-15T10:30:00.000Z'
              }
            ]
          },
          timestamp: '2024-01-15T10:30:00.000Z'
        }
      };

      mockedAxios.get.mockResolvedValue(mockResponse);

      const result = await api.getPortfolioHoldings();

      expect(result.success).toBe(true);
      expect(result.data.totalValue).toBe(125000.50);
      expect(result.data.holdings).toHaveLength(1);
      expect(result.data.holdings[0]).toMatchObject({
        symbol: 'AAPL',
        quantity: 100,
        avgPrice: 180.50,
        currentPrice: 195.20,
        totalValue: 19520.00,
        gainLoss: 1470.00,
        gainLossPercent: 8.14
      });

      // Verify API called with correct parameters
      expect(mockedAxios.get).toHaveBeenCalledWith('/portfolio/holdings');
    });

    test('getPortfolioSummary handles missing data gracefully', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: {
            totalValue: 0,
            totalGainLoss: 0,
            totalGainLossPercent: 0,
            topPerformers: [],
            sectorAllocation: []
          },
          timestamp: '2024-01-15T10:30:00.000Z'
        }
      };

      mockedAxios.get.mockResolvedValue(mockResponse);

      const result = await api.getPortfolioSummary();

      expect(result.success).toBe(true);
      expect(result.data.totalValue).toBe(0);
      expect(result.data.topPerformers).toEqual([]);
      expect(result.data.sectorAllocation).toEqual([]);
    });

    test('handles portfolio calculation validation', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: {
            totalValue: 125000.50,
            totalGainLoss: 8500.25,
            totalGainLossPercent: 7.3,
            holdings: [
              {
                symbol: 'AAPL',
                quantity: 100,
                avgPrice: 180.50,
                currentPrice: 195.20,
                totalValue: 19520.00, // 100 * 195.20
                gainLoss: 1470.00, // 19520 - (100 * 180.50)
                gainLossPercent: 8.14 // (1470 / 18050) * 100
              }
            ]
          }
        }
      };

      mockedAxios.get.mockResolvedValue(mockResponse);

      const result = await api.getPortfolioHoldings();
      const holding = result.data.holdings[0];

      // Verify financial calculations are correct
      const expectedTotalValue = holding.quantity * holding.currentPrice;
      expect(Math.abs(holding.totalValue - expectedTotalValue)).toBeLessThan(0.01);

      const expectedGainLoss = holding.totalValue - (holding.quantity * holding.avgPrice);
      expect(Math.abs(holding.gainLoss - expectedGainLoss)).toBeLessThan(0.01);

      const costBasis = holding.quantity * holding.avgPrice;
      const expectedGainLossPercent = (holding.gainLoss / costBasis) * 100;
      expect(Math.abs(holding.gainLossPercent - expectedGainLossPercent)).toBeLessThan(0.01);
    });
  });

  describe('Market Data API Contract', () => {
    test('getMarketOverview handles contract response', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: {
            indices: {
              SPY: { price: 445.32, change: 2.15, changePercent: 0.48, volume: 45000000 },
              QQQ: { price: 375.68, change: -1.23, changePercent: -0.33, volume: 28000000 }
            },
            sectors: [
              { name: 'Technology', performance: 1.85, trend: 'up', volume: 850000000 },
              { name: 'Healthcare', performance: 0.75, trend: 'up', volume: 620000000 }
            ],
            marketSentiment: 'bullish',
            vixLevel: 18.5,
            lastUpdated: '2024-01-15T10:30:00.000Z'
          }
        }
      };

      mockedAxios.get.mockResolvedValue(mockResponse);

      const result = await api.getMarketOverview();

      expect(result.success).toBe(true);
      expect(result.data.indices).toHaveProperty('SPY');
      expect(result.data.indices).toHaveProperty('QQQ');
      expect(result.data.sectors).toHaveLength(2);
      expect(['bullish', 'bearish', 'neutral']).toContain(result.data.marketSentiment);
      expect(typeof result.data.vixLevel).toBe('number');
    });

    test('getStockPrice handles contract response', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: {
            symbol: 'AAPL',
            price: 195.20,
            change: 2.15,
            changePercent: 1.11,
            volume: 25000000,
            high: 197.50,
            low: 192.80,
            open: 193.40,
            previousClose: 193.05,
            marketCap: 3000000000000,
            peRatio: 28.5,
            dividendYield: 0.52,
            lastUpdated: '2024-01-15T10:30:00.000Z'
          }
        }
      };

      mockedAxios.get.mockResolvedValue(mockResponse);

      const result = await api.getStockPrice('AAPL');

      expect(result.success).toBe(true);
      expect(result.data.symbol).toBe('AAPL');
      expect(result.data.price).toBe(195.20);

      // Validate price relationships
      expect(result.data.high).toBeGreaterThanOrEqual(result.data.low);
      expect(result.data.price).toBeGreaterThanOrEqual(result.data.low);
      expect(result.data.price).toBeLessThanOrEqual(result.data.high);

      // Validate change calculations
      const expectedChange = result.data.price - result.data.previousClose;
      expect(Math.abs(result.data.change - expectedChange)).toBeLessThan(0.01);

      // Verify API called with correct symbol
      expect(mockedAxios.get).toHaveBeenCalledWith('/stocks/AAPL/price');
    });
  });

  describe('Settings API Contract', () => {
    test('getApiKeys handles contract response', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: {
            configured: ['alpaca', 'polygon', 'finnhub'],
            valid: ['alpaca', 'polygon'],
            lastValidated: '2024-01-15T10:30:00.000Z'
          }
        }
      };

      mockedAxios.get.mockResolvedValue(mockResponse);

      const result = await api.getApiKeys();

      expect(result.success).toBe(true);
      expect(Array.isArray(result.data.configured)).toBe(true);
      expect(Array.isArray(result.data.valid)).toBe(true);
      
      // Valid keys should be subset of configured
      result.data.valid.forEach(provider => {
        expect(result.data.configured).toContain(provider);
      });

      // Providers should be valid values
      const validProviders = ['alpaca', 'polygon', 'finnhub', 'alpha_vantage', 'iex'];
      result.data.configured.forEach(provider => {
        expect(validProviders).toContain(provider);
      });
    });

    test('saveApiKey handles validation errors', async () => {
      const mockError = {
        response: {
          data: {
            success: false,
            error: 'Invalid API key format',
            details: {
              field: 'credentials.keyId',
              message: 'Key ID must be alphanumeric',
              value: 'invalid-key!'
            },
            timestamp: '2024-01-15T10:30:00.000Z'
          },
          status: 400
        }
      };

      mockedAxios.post.mockRejectedValue(mockError);

      const result = await api.saveApiKey('alpaca', {
        keyId: 'invalid-key!',
        secret: 'test-secret'
      });

      expect(result.success).toBe(false);
      expect(result.error).toBe('Invalid API key format');
      expect(result.details).toMatchObject({
        field: 'credentials.keyId',
        message: 'Key ID must be alphanumeric',
        value: 'invalid-key!'
      });
    });
  });

  describe('Authentication Handling', () => {
    test('automatically includes auth token', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: { test: 'data' }
        }
      };

      // Mock localStorage for auth token
      const mockToken = 'mock-jwt-token';
      vi.stubGlobal('localStorage', {
        getItem: vi.fn().mockReturnValue(mockToken)
      });

      mockedAxios.get.mockResolvedValue(mockResponse);

      await api.getPortfolioHoldings();

      // Verify auth header was included
      expect(mockedAxios.get).toHaveBeenCalledWith('/portfolio/holdings', {
        headers: {
          'Authorization': `Bearer ${mockToken}`
        }
      });

      vi.unstubAllGlobals();
    });

    test('handles 401 authentication errors', async () => {
      const mockError = {
        response: {
          data: {
            success: false,
            error: 'Invalid token',
            code: 'INVALID_TOKEN',
            timestamp: '2024-01-15T10:30:00.000Z'
          },
          status: 401
        }
      };

      mockedAxios.get.mockRejectedValue(mockError);

      const result = await api.getPortfolioHoldings();

      expect(result.success).toBe(false);
      expect(result.error).toBe('Invalid token');
      expect(result.code).toBe('INVALID_TOKEN');
      expect(result.requiresAuth).toBe(true);
    });

    test('handles token refresh on 401', async () => {
      const mockError = {
        response: {
          data: {
            success: false,
            error: 'Token expired',
            code: 'EXPIRED_TOKEN'
          },
          status: 401
        }
      };

      const mockSuccessResponse = {
        data: {
          success: true,
          data: { test: 'data' }
        }
      };

      // Mock token refresh
      mockedAxios.get
        .mockRejectedValueOnce(mockError)
        .mockResolvedValueOnce(mockSuccessResponse);

      const result = await api.getPortfolioHoldings();

      // Should succeed after token refresh
      expect(result.success).toBe(true);
      expect(mockedAxios.get).toHaveBeenCalledTimes(2);
    });
  });

  describe('Error Handling Contract', () => {
    test('handles rate limiting errors', async () => {
      const mockError = {
        response: {
          data: {
            success: false,
            error: 'Rate limit exceeded',
            retryAfter: 60,
            limit: 100,
            remaining: 0,
            reset: '2024-01-15T10:31:00.000Z',
            timestamp: '2024-01-15T10:30:00.000Z'
          },
          status: 429
        }
      };

      mockedAxios.get.mockRejectedValue(mockError);

      const result = await api.getPortfolioHoldings();

      expect(result.success).toBe(false);
      expect(result.error).toBe('Rate limit exceeded');
      expect(result.retryAfter).toBe(60);
      expect(result.rateLimited).toBe(true);
      expect(typeof result.reset).toBe('string');
    });

    test('handles server errors gracefully', async () => {
      const mockError = {
        response: {
          data: {
            success: false,
            error: 'Internal server error',
            correlationId: 'req-12345',
            timestamp: '2024-01-15T10:30:00.000Z'
          },
          status: 500
        }
      };

      mockedAxios.get.mockRejectedValue(mockError);

      const result = await api.getPortfolioHoldings();

      expect(result.success).toBe(false);
      expect(result.error).toBe('Internal server error');
      expect(result.correlationId).toBe('req-12345');
      expect(result.serverError).toBe(true);
    });

    test('handles malformed response gracefully', async () => {
      const mockResponse = {
        data: 'Invalid JSON response',
        status: 200
      };

      mockedAxios.get.mockResolvedValue(mockResponse);

      const result = await api.getPortfolioHoldings();

      expect(result.success).toBe(false);
      expect(result.error).toContain('Invalid response format');
      expect(result.parseError).toBe(true);
    });
  });

  describe('Pagination Contract', () => {
    test('handles paginated responses correctly', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: {
            transactions: [
              { id: 1, symbol: 'AAPL', type: 'buy', quantity: 10 },
              { id: 2, symbol: 'MSFT', type: 'sell', quantity: 5 }
            ],
            pagination: {
              page: 1,
              limit: 10,
              total: 25,
              pages: 3,
              hasNext: true,
              hasPrev: false
            }
          }
        }
      };

      mockedAxios.get.mockResolvedValue(mockResponse);

      const result = await api.getPortfolioTransactions({ page: 1, limit: 10 });

      expect(result.success).toBe(true);
      expect(result.data.transactions).toHaveLength(2);
      expect(result.data.pagination).toMatchObject({
        page: 1,
        limit: 10,
        total: 25,
        pages: 3,
        hasNext: true,
        hasPrev: false
      });

      // Verify pagination math
      const { pagination } = result.data;
      expect(pagination.pages).toBe(Math.ceil(pagination.total / pagination.limit));
      expect(pagination.hasNext).toBe(pagination.page < pagination.pages);
      expect(pagination.hasPrev).toBe(pagination.page > 1);
    });

    test('validates pagination parameters', async () => {
      await api.getPortfolioTransactions({ page: 1, limit: 50 });

      expect(mockedAxios.get).toHaveBeenCalledWith('/portfolio/transactions', {
        params: { page: 1, limit: 50 }
      });
    });
  });

  describe('Response Time Validation', () => {
    test('handles slow responses with timeout', async () => {
      const slowResponse = new Promise(resolve => {
        setTimeout(() => resolve({ data: { success: true, data: {} } }), 10000);
      });

      mockedAxios.get.mockReturnValue(slowResponse);

      const startTime = Date.now();
      const result = await api.getPortfolioHoldings();
      const responseTime = Date.now() - startTime;

      // Should timeout or resolve quickly
      expect(responseTime).toBeLessThan(8000);
    });
  });
});
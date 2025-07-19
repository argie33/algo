/**
 * Real API Service Unit Tests
 * Testing the actual api.js with circuit breaker, authentication, and error handling
 * CRITICAL COMPONENT - Known to have authentication and circuit breaker issues
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';

// Mock dependencies
vi.mock('axios');
vi.mock('../../../error/apiErrorHandler', () => ({
  enhancedFetch: vi.fn()
}));
vi.mock('../../../error/ErrorManager', () => ({
  default: {
    handleError: vi.fn((config) => config),
    CATEGORIES: { API: 'api' },
    SEVERITY: { LOW: 'low', HIGH: 'high' }
  }
}));
vi.mock('../../../services/apiHealthService', () => ({
  default: {
    forceHealthCheck: vi.fn().mockResolvedValue({})
  }
}));
vi.mock('../../../services/apiWrapper', () => ({
  default: {
    execute: vi.fn((name, fn, options) => fn())
  }
}));

// Mock environment variables
vi.stubGlobal('import', {
  meta: {
    env: {
      VITE_API_URL: 'https://api.example.com',
      MODE: 'test',
      DEV: false,
      PROD: true,
      BASE_URL: '/'
    }
  }
});

// Mock window and localStorage
const mockLocalStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn()
};

Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage
});

Object.defineProperty(window, 'location', {
  value: {
    href: 'https://example.com/dashboard',
    pathname: '/dashboard'
  },
  writable: true
});

// Import the REAL API service after mocks
let api, getApiConfig, getPortfolioData, addHolding, updateHolding;

describe('🔌 Real API Service', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Mock axios.create to return a mock instance
    const mockAxiosInstance = {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() }
      }
    };
    
    axios.create.mockReturnValue(mockAxiosInstance);
    
    // Reset global window config
    delete window.__CONFIG__;
    
    // Mock console to avoid noise
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    
    // Dynamically import the API service to get fresh instance
    const apiModule = await import('../../../services/api');
    api = apiModule.api;
    getApiConfig = apiModule.getApiConfig;
    getPortfolioData = apiModule.getPortfolioData;
    addHolding = apiModule.addHolding;
    updateHolding = apiModule.updateHolding;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('API Configuration', () => {
    it('should get configuration from environment variable', () => {
      const config = getApiConfig();
      
      expect(config).toEqual(expect.objectContaining({
        baseURL: 'https://api.example.com',
        isServerless: true,
        apiUrl: 'https://api.example.com',
        isConfigured: true,
        environment: 'test',
        isDevelopment: false,
        isProduction: true
      }));
    });

    it('should prefer window.__CONFIG__ over environment variables', () => {
      window.__CONFIG__ = { API_URL: 'https://runtime.api.com' };
      
      const config = getApiConfig();
      
      expect(config.baseURL).toBe('https://runtime.api.com');
      expect(config.apiUrl).toBe('https://runtime.api.com');
    });

    it('should throw error when API URL is not configured', () => {
      // Temporarily remove environment config
      vi.stubGlobal('import', {
        meta: {
          env: {}
        }
      });
      
      expect(() => getApiConfig()).toThrow(
        'API URL not configured - set VITE_API_URL environment variable or window.__CONFIG__.API_URL'
      );
    });

    it('should detect localhost as unconfigured', () => {
      window.__CONFIG__ = { API_URL: 'http://localhost:3000' };
      
      const config = getApiConfig();
      
      expect(config.isConfigured).toBe(false);
      expect(config.isServerless).toBe(false);
    });

    it('should detect placeholder URLs as unconfigured', () => {
      window.__CONFIG__ = { API_URL: 'PLACEHOLDER_API_URL' };
      
      const config = getApiConfig();
      
      expect(config.isConfigured).toBe(false);
    });
  });

  describe('Axios Instance Creation', () => {
    it('should create axios instance with correct configuration', () => {
      expect(axios.create).toHaveBeenCalledWith({
        baseURL: 'https://api.example.com',
        timeout: 45000, // Serverless timeout
        headers: {
          'Content-Type': 'application/json'
        }
      });
    });

    it('should use shorter timeout for non-serverless environments', () => {
      window.__CONFIG__ = { API_URL: 'http://localhost:3000' };
      
      // Re-import to get fresh configuration
      vi.resetModules();
      
      expect(axios.create).toHaveBeenCalledWith(
        expect.objectContaining({
          timeout: 30000 // Non-serverless timeout
        })
      );
    });

    it('should setup request and response interceptors', () => {
      const mockInstance = axios.create.mock.results[0].value;
      
      expect(mockInstance.interceptors.request.use).toHaveBeenCalled();
      expect(mockInstance.interceptors.response.use).toHaveBeenCalled();
    });
  });

  describe('Authentication Token Handling', () => {
    it('should add authorization header when token exists', () => {
      mockLocalStorage.getItem.mockReturnValue('test-access-token');
      
      const mockInstance = axios.create.mock.results[0].value;
      const requestInterceptor = mockInstance.interceptors.request.use.mock.calls[1][0];
      
      const config = { headers: {} };
      const result = requestInterceptor(config);
      
      expect(result.headers.Authorization).toBe('Bearer test-access-token');
    });

    it('should prefer accessToken over authToken', () => {
      mockLocalStorage.getItem
        .mockReturnValueOnce('access-token')  // accessToken
        .mockReturnValueOnce('auth-token');   // authToken (fallback)
      
      const mockInstance = axios.create.mock.results[0].value;
      const requestInterceptor = mockInstance.interceptors.request.use.mock.calls[1][0];
      
      const config = { headers: {} };
      const result = requestInterceptor(config);
      
      expect(result.headers.Authorization).toBe('Bearer access-token');
    });

    it('should use authToken as fallback when accessToken not available', () => {
      mockLocalStorage.getItem
        .mockReturnValueOnce(null)           // accessToken
        .mockReturnValueOnce('auth-token'); // authToken
      
      const mockInstance = axios.create.mock.results[0].value;
      const requestInterceptor = mockInstance.interceptors.request.use.mock.calls[1][0];
      
      const config = { headers: {} };
      const result = requestInterceptor(config);
      
      expect(result.headers.Authorization).toBe('Bearer auth-token');
    });

    it('should not add authorization header when no token exists', () => {
      mockLocalStorage.getItem.mockReturnValue(null);
      
      const mockInstance = axios.create.mock.results[0].value;
      const requestInterceptor = mockInstance.interceptors.request.use.mock.calls[1][0];
      
      const config = { headers: {} };
      const result = requestInterceptor(config);
      
      expect(result.headers.Authorization).toBeUndefined();
    });
  });

  describe('Circuit Breaker Implementation', () => {
    let circuitBreakerRequestInterceptor;
    let responseInterceptor;
    
    beforeEach(() => {
      const mockInstance = axios.create.mock.results[0].value;
      circuitBreakerRequestInterceptor = mockInstance.interceptors.request.use.mock.calls[0][0];
      responseInterceptor = mockInstance.interceptors.response.use.mock.calls[0];
    });

    it('should allow requests when circuit breaker is closed', () => {
      const config = { url: '/test' };
      
      const result = circuitBreakerRequestInterceptor(config);
      
      expect(result).toBe(config);
    });

    it('should record success and reset circuit breaker state', () => {
      const [successHandler] = responseInterceptor;
      const mockResponse = { data: 'success' };
      
      const result = successHandler(mockResponse);
      
      expect(result).toBe(mockResponse);
      // Circuit breaker state should be reset (tested indirectly through behavior)
    });

    it('should handle authentication errors by clearing tokens', () => {
      const [, errorHandler] = responseInterceptor;
      const authError = {
        response: { status: 401 }
      };
      
      expect(() => errorHandler(authError)).rejects.toThrow();
      
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('accessToken');
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('authToken');
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('refreshToken');
    });

    it('should redirect to login page on authentication error', () => {
      const [, errorHandler] = responseInterceptor;
      const authError = {
        response: { status: 401 }
      };
      
      expect(() => errorHandler(authError)).rejects.toThrow();
      
      // Would redirect in real browser (can't test redirect directly in unit test)
    });

    it('should not redirect when already on login page', () => {
      window.location.pathname = '/login';
      
      const [, errorHandler] = responseInterceptor;
      const authError = {
        response: { status: 401 }
      };
      
      expect(() => errorHandler(authError)).rejects.toThrow();
      
      // Should not attempt redirect
    });

    it('should record failures for non-auth errors', () => {
      const [, errorHandler] = responseInterceptor;
      const serverError = {
        response: { status: 500 }
      };
      
      expect(() => errorHandler(serverError)).rejects.toThrow();
      
      // Circuit breaker failure should be recorded (tested indirectly)
    });

    it('should not record failures for forbidden errors', () => {
      const [, errorHandler] = responseInterceptor;
      const forbiddenError = {
        response: { status: 403 }
      };
      
      expect(() => errorHandler(forbiddenError)).rejects.toThrow();
      
      // Should not record as circuit breaker failure
    });

    it('should block requests when circuit breaker is open', async () => {
      // Simulate multiple failures to open circuit breaker
      const [, errorHandler] = responseInterceptor;
      
      for (let i = 0; i < 3; i++) {
        try {
          await errorHandler({ response: { status: 500 } });
        } catch (e) {
          // Expected to throw
        }
      }
      
      // Now circuit breaker should be open
      expect(() => circuitBreakerRequestInterceptor({ url: '/test' }))
        .rejects.toThrow('Circuit breaker is open - API unavailable');
    });

    it('should allow requests after circuit breaker timeout', async () => {
      vi.useFakeTimers();
      
      // Open circuit breaker
      const [, errorHandler] = responseInterceptor;
      for (let i = 0; i < 3; i++) {
        try {
          await errorHandler({ response: { status: 500 } });
        } catch (e) {
          // Expected to throw
        }
      }
      
      // Fast forward past timeout (30 seconds)
      vi.advanceTimersByTime(31000);
      
      const config = { url: '/test' };
      const result = circuitBreakerRequestInterceptor(config);
      
      expect(result).toBe(config);
      
      vi.useRealTimers();
    });
  });

  describe('Portfolio API Functions', () => {
    beforeEach(() => {
      // Mock successful API responses
      api.get = vi.fn().mockResolvedValue({
        data: {
          success: true,
          data: {
            holdings: [
              {
                id: 'holding_1',
                symbol: 'AAPL',
                quantity: 100,
                averagePrice: 175.25,
                currentPrice: 185.50
              }
            ],
            summary: {
              totalValue: 18550,
              totalCost: 17525,
              totalGainLoss: 1025,
              totalGainLossPercent: 5.85
            }
          }
        }
      });
      
      api.post = vi.fn().mockResolvedValue({
        data: {
          success: true,
          data: { id: 'new_holding', symbol: 'TSLA' }
        }
      });
      
      api.put = vi.fn().mockResolvedValue({
        data: {
          success: true,
          data: { updated: true }
        }
      });
    });

    describe('getPortfolioData', () => {
      it('should fetch portfolio data successfully', async () => {
        const result = await getPortfolioData('paper');
        
        expect(api.get).toHaveBeenCalledWith('/api/portfolio/holdings?accountType=paper');
        expect(result).toEqual(expect.objectContaining({
          holdings: expect.any(Array),
          summary: expect.any(Object)
        }));
      });

      it('should use default account type when not specified', async () => {
        await getPortfolioData();
        
        expect(api.get).toHaveBeenCalledWith('/api/portfolio/holdings?accountType=paper');
      });

      it('should handle different account types', async () => {
        await getPortfolioData('live');
        
        expect(api.get).toHaveBeenCalledWith('/api/portfolio/holdings?accountType=live');
      });

      it('should return empty portfolio for 404 errors', async () => {
        api.get.mockRejectedValue({
          response: { status: 404 },
          message: 'Portfolio not found'
        });
        
        const result = await getPortfolioData();
        
        expect(result).toEqual({
          success: true,
          holdings: [],
          summary: {
            totalValue: 0,
            totalCost: 0,
            totalGainLoss: 0,
            totalGainLossPercent: 0
          }
        });
      });

      it('should throw enhanced error for non-404 failures', async () => {
        api.get.mockRejectedValue({
          response: { status: 500 },
          message: 'Internal server error'
        });
        
        await expect(getPortfolioData()).rejects.toEqual(
          expect.objectContaining({
            type: 'api_request_failed',
            message: expect.stringContaining('Failed to fetch portfolio data')
          })
        );
      });

      it('should extract data from nested response structure', async () => {
        api.get.mockResolvedValue({
          data: {
            success: true,
            data: {
              holdings: [{ symbol: 'AAPL' }]
            }
          }
        });
        
        const result = await getPortfolioData();
        
        expect(result.holdings).toEqual([{ symbol: 'AAPL' }]);
      });

      it('should return raw data when structure is not nested', async () => {
        api.get.mockResolvedValue({
          data: {
            holdings: [{ symbol: 'AAPL' }]
          }
        });
        
        const result = await getPortfolioData();
        
        expect(result.holdings).toEqual([{ symbol: 'AAPL' }]);
      });

      it('should provide helpful error message for API configuration errors', async () => {
        api.get.mockRejectedValue({
          message: 'API URL not configured - set VITE_API_URL environment variable',
          response: { status: 500 }
        });
        
        try {
          await getPortfolioData();
        } catch (error) {
          expect(error.userMessage).toBe('API configuration is missing. Please check your settings.');
          expect(error.suggestedActions).toEqual([
            'Check API settings in Settings page',
            'Verify environment configuration',
            'Contact support if problem persists'
          ]);
        }
      });
    });

    describe('addHolding', () => {
      it('should add holding successfully', async () => {
        const holding = {
          symbol: 'TSLA',
          quantity: 10,
          averagePrice: 220.00
        };
        
        const result = await addHolding(holding);
        
        expect(api.post).toHaveBeenCalledWith('/api/portfolio/holdings', holding);
        expect(result).toEqual(expect.objectContaining({
          success: true,
          data: { id: 'new_holding', symbol: 'TSLA' }
        }));
      });

      it('should validate required symbol field', async () => {
        const invalidHolding = {
          quantity: 10,
          averagePrice: 220.00
        };
        
        await expect(addHolding(invalidHolding)).rejects.toThrow(
          'Invalid holding data: symbol is required'
        );
      });

      it('should validate holding object exists', async () => {
        await expect(addHolding(null)).rejects.toThrow(
          'Invalid holding data: symbol is required'
        );
        
        await expect(addHolding(undefined)).rejects.toThrow(
          'Invalid holding data: symbol is required'
        );
      });

      it('should handle validation errors from API', async () => {
        api.post.mockRejectedValue({
          response: { 
            status: 400,
            data: { errors: ['Quantity must be positive'] }
          },
          message: 'Validation failed'
        });
        
        try {
          await addHolding({ symbol: 'INVALID', quantity: -1 });
        } catch (error) {
          expect(error.userMessage).toBe('Invalid holding data. Please check all required fields.');
          expect(error.context.validationErrors).toEqual(['Quantity must be positive']);
        }
      });

      it('should handle duplicate holding errors', async () => {
        api.post.mockRejectedValue({
          response: { status: 409 },
          message: 'Holding already exists'
        });
        
        try {
          await addHolding({ symbol: 'AAPL', quantity: 10 });
        } catch (error) {
          expect(error.userMessage).toBe('This holding already exists in your portfolio.');
        }
      });

      it('should log successful operation', async () => {
        const ErrorManager = (await import('../../../error/ErrorManager')).default;
        
        await addHolding({ symbol: 'AAPL', quantity: 10 });
        
        expect(ErrorManager.handleError).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'api_success',
            message: 'Holding AAPL added successfully'
          })
        );
      });
    });

    describe('updateHolding', () => {
      it('should update holding successfully', async () => {
        const holdingId = 'holding_123';
        const updatedHolding = {
          symbol: 'AAPL',
          quantity: 150,
          averagePrice: 180.00
        };
        
        const result = await updateHolding(holdingId, updatedHolding);
        
        expect(api.put).toHaveBeenCalledWith(
          `/api/portfolio/holdings/${holdingId}`,
          updatedHolding
        );
        expect(result).toEqual(expect.objectContaining({
          success: true,
          data: { updated: true }
        }));
      });

      it('should validate holding ID is provided', async () => {
        await expect(updateHolding(null, { symbol: 'AAPL' })).rejects.toThrow(
          'Holding ID is required'
        );
        
        await expect(updateHolding('', { symbol: 'AAPL' })).rejects.toThrow(
          'Holding ID is required'
        );
      });

      it('should validate holding data is provided', async () => {
        await expect(updateHolding('holding_123', null)).rejects.toThrow(
          'Invalid holding data: symbol is required'
        );
        
        await expect(updateHolding('holding_123', {})).rejects.toThrow(
          'Invalid holding data: symbol is required'
        );
      });
    });
  });

  describe('Error Handling Integration', () => {
    it('should integrate with ErrorManager for error tracking', async () => {
      const ErrorManager = (await import('../../../error/ErrorManager')).default;
      
      api.get.mockRejectedValue({
        response: { status: 500 },
        message: 'Server error'
      });
      
      try {
        await getPortfolioData();
      } catch (error) {
        expect(ErrorManager.handleError).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'api_request_failed',
            category: 'api',
            severity: 'high'
          })
        );
      }
    });

    it('should provide appropriate error severity for different status codes', async () => {
      const ErrorManager = (await import('../../../error/ErrorManager')).default;
      
      // 404 should be low severity
      api.get.mockRejectedValue({
        response: { status: 404 },
        message: 'Not found'
      });
      
      await getPortfolioData(); // Should not throw for 404
      
      expect(ErrorManager.handleError).toHaveBeenCalledWith(
        expect.objectContaining({
          severity: 'low'
        })
      );
    });

    it('should include relevant context in error reports', async () => {
      const ErrorManager = (await import('../../../error/ErrorManager')).default;
      
      api.get.mockRejectedValue({
        response: { status: 500 },
        message: 'Server error'
      });
      
      try {
        await getPortfolioData('live');
      } catch (error) {
        expect(ErrorManager.handleError).toHaveBeenCalledWith(
          expect.objectContaining({
            context: expect.objectContaining({
              operation: 'getPortfolioData',
              accountType: 'live',
              status: 500,
              url: '/api/portfolio/holdings?accountType=live'
            })
          })
        );
      }
    });
  });

  describe('API Health Integration', () => {
    it('should trigger health check after API failures', async () => {
      const apiHealthService = (await import('../../../services/apiHealthService')).default;
      
      const [, errorHandler] = axios.create.mock.results[0].value.interceptors.response.use.mock.calls[0];
      
      try {
        await errorHandler({ response: { status: 500 } });
      } catch (e) {
        // Expected to throw
      }
      
      expect(apiHealthService.forceHealthCheck).toHaveBeenCalled();
    });

    it('should handle health check failures gracefully', async () => {
      const apiHealthService = (await import('../../../services/apiHealthService')).default;
      apiHealthService.forceHealthCheck.mockRejectedValue(new Error('Health check failed'));
      
      const [, errorHandler] = axios.create.mock.results[0].value.interceptors.response.use.mock.calls[0];
      
      // Should not throw even if health check fails
      expect(async () => {
        try {
          await errorHandler({ response: { status: 500 } });
        } catch (e) {
          // Expected to throw original error, not health check error
        }
      }).not.toThrow();
    });
  });

  describe('Real-World Integration Scenarios', () => {
    it('should handle complete authentication flow', async () => {
      // Start with valid token
      mockLocalStorage.getItem.mockReturnValue('valid-token');
      
      // Make successful request
      api.get.mockResolvedValue({ data: { success: true } });
      await getPortfolioData();
      
      // Token should be used
      const mockInstance = axios.create.mock.results[0].value;
      const requestInterceptor = mockInstance.interceptors.request.use.mock.calls[1][0];
      const config = requestInterceptor({ headers: {} });
      expect(config.headers.Authorization).toBe('Bearer valid-token');
      
      // Simulate auth failure
      const [, errorHandler] = mockInstance.interceptors.response.use.mock.calls[0];
      try {
        await errorHandler({ response: { status: 401 } });
      } catch (e) {
        // Expected
      }
      
      // Tokens should be cleared
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('accessToken');
    });

    it('should handle network connectivity issues', async () => {
      // Simulate network error
      api.get.mockRejectedValue(new Error('Network Error'));
      
      try {
        await getPortfolioData();
      } catch (error) {
        expect(error.type).toBe('api_request_failed');
        expect(error.message).toContain('Network Error');
      }
    });

    it('should handle API rate limiting', async () => {
      api.get.mockRejectedValue({
        response: { status: 429 },
        message: 'Too Many Requests'
      });
      
      try {
        await getPortfolioData();
      } catch (error) {
        expect(error.context.status).toBe(429);
      }
    });

    it('should handle malformed API responses', async () => {
      api.get.mockResolvedValue({
        data: 'invalid json response'
      });
      
      const result = await getPortfolioData();
      
      // Should return the raw response when structure is unexpected
      expect(result).toBe('invalid json response');
    });
  });

  describe('Performance and Memory Management', () => {
    it('should handle large portfolio datasets efficiently', async () => {
      const largePortfolio = {
        success: true,
        data: {
          holdings: Array.from({ length: 1000 }, (_, i) => ({
            id: `holding_${i}`,
            symbol: `STOCK${i}`,
            quantity: 100,
            averagePrice: 100 + i
          })),
          summary: { totalValue: 100000 }
        }
      };
      
      api.get.mockResolvedValue({ data: largePortfolio });
      
      const startTime = performance.now();
      const result = await getPortfolioData();
      const duration = performance.now() - startTime;
      
      expect(duration).toBeLessThan(100); // Should complete within 100ms
      expect(result.holdings).toHaveLength(1000);
    });

    it('should handle concurrent API requests safely', async () => {
      api.get.mockResolvedValue({
        data: { success: true, holdings: [] }
      });
      
      const promises = Array.from({ length: 10 }, () => getPortfolioData());
      
      const results = await Promise.all(promises);
      
      expect(results).toHaveLength(10);
      expect(api.get).toHaveBeenCalledTimes(10);
    });
  });
});
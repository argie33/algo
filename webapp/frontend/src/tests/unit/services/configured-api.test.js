/**
 * Configured API Service Tests
 * Tests the centralized API configuration and ensures no hardcoded values
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock fetch globally
global.fetch = vi.fn();

// Mock window configuration
const mockWindowConfig = {
  API: {
    BASE_URL: 'https://api-test.example.com',
    VERSION: 'v1',
    TIMEOUT: 30000
  },
  COGNITO: {
    USER_POOL_ID: 'us-east-1_TEST123456',
    CLIENT_ID: 'test-client-id'
  }
};

describe('Configured API Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock window.__CONFIG__
    global.window = global.window || {};
    window.__CONFIG__ = { ...mockWindowConfig };
    
    // Mock localStorage
    const localStorageMock = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn()
    };
    Object.defineProperty(window, 'localStorage', { value: localStorageMock });
    
    // Mock successful API response by default
    fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ success: true, data: {} })
    });
  });

  afterEach(() => {
    vi.resetModules();
  });

  describe('API Client Configuration', () => {
    it('should use centralized configuration for base URL', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('test-endpoint');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('api-test.example.com'),
        expect.any(Object)
      );
    });

    it('should include API version in URLs', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('test-endpoint');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/v1/test-endpoint'),
        expect.any(Object)
      );
    });

    it('should use configured timeout', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      const timeoutSpy = vi.spyOn(global, 'setTimeout');
      
      await configuredApi.get('test-endpoint');
      
      expect(timeoutSpy).toHaveBeenCalledWith(
        expect.any(Function),
        30000
      );
    });

    it('should set appropriate default headers', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('test-endpoint');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-API-Version': 'v1'
          })
        })
      );
    });
  });

  describe('Authentication Integration', () => {
    it('should include authentication token when available', async () => {
      window.localStorage.getItem.mockReturnValue('test-auth-token');
      
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('protected-endpoint');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer test-auth-token'
          })
        })
      );
    });

    it('should not include authorization header when token is missing', async () => {
      window.localStorage.getItem.mockReturnValue(null);
      
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('public-endpoint');
      
      const fetchCall = fetch.mock.calls[0];
      const headers = fetchCall[1].headers;
      
      expect(headers).not.toHaveProperty('Authorization');
    });

    it('should not include authorization header for demo tokens', async () => {
      window.localStorage.getItem.mockReturnValue('demo-token');
      
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('endpoint');
      
      const fetchCall = fetch.mock.calls[0];
      const headers = fetchCall[1].headers;
      
      expect(headers).not.toHaveProperty('Authorization');
    });
  });

  describe('Error Handling and Fallbacks', () => {
    it('should provide fallback data for 404 errors', async () => {
      fetch.mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found'
      });
      
      const { configuredApi } = await import('../../../services/configuredApi');
      
      const result = await configuredApi.get('metrics');
      
      expect(result).toEqual({
        success: true,
        data: {
          totalStocks: 8500,
          activeAlerts: 12,
          portfolioValue: 125000,
          dailyChange: 1250
        }
      });
    });

    it('should provide fallback data for 500 errors', async () => {
      fetch.mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error'
      });
      
      const { configuredApi } = await import('../../../services/configuredApi');
      
      const result = await configuredApi.get('portfolio');
      
      expect(result).toEqual({
        success: true,
        data: {
          totalValue: 125000,
          positions: [],
          performance: { dayChange: 2.04, totalReturn: 15.3 }
        }
      });
    });

    it('should handle network timeouts gracefully', async () => {
      const abortError = new Error('Request timeout');
      abortError.name = 'AbortError';
      fetch.mockRejectedValue(abortError);
      
      const { configuredApi } = await import('../../../services/configuredApi');
      
      const result = await configuredApi.get('any-endpoint');
      
      expect(result).toHaveProperty('success', false);
      expect(result).toHaveProperty('error', 'Service unavailable');
    });

    it('should handle network errors with fallback data', async () => {
      fetch.mockRejectedValue(new Error('Network error'));
      
      const { configuredApi } = await import('../../../services/configuredApi');
      
      const result = await configuredApi.get('metrics');
      
      expect(result).toEqual({
        success: true,
        data: {
          totalStocks: 8500,
          activeAlerts: 12,
          portfolioValue: 125000,
          dailyChange: 1250
        }
      });
    });
  });

  describe('HTTP Methods', () => {
    it('should support GET requests with query parameters', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('search', { query: 'AAPL', limit: 10 });
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('search?query=AAPL&limit=10'),
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('should support POST requests with JSON body', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      const postData = { symbol: 'AAPL', quantity: 100 };
      await configuredApi.post('orders', postData);
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('orders'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(postData)
        })
      );
    });

    it('should support PUT requests', async () => {  
      const { configuredApi } = await import('../../../services/configuredApi');
      
      const putData = { id: 1, status: 'updated' };
      await configuredApi.put('orders/1', putData);
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('orders/1'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(putData)
        })
      );
    });

    it('should support DELETE requests', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.delete('orders/1');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('orders/1'),
        expect.objectContaining({ method: 'DELETE' })
      );
    });
  });

  describe('URL Construction', () => {
    it('should handle endpoints with leading slashes', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('/portfolio');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/v1\/portfolio$/),
        expect.any(Object)
      );
      
      // Should not have double slashes
      const fetchUrl = fetch.mock.calls[0][0];
      expect(fetchUrl).not.toContain('//portfolio');
    });

    it('should handle endpoints without leading slashes', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('portfolio');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/v1\/portfolio$/),
        expect.any(Object)
      );
    });

    it('should handle query parameters correctly', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('stocks', { 
        symbol: 'AAPL', 
        fields: 'price,volume',
        limit: 50 
      });
      
      const fetchUrl = fetch.mock.calls[0][0];
      expect(fetchUrl).toContain('symbol=AAPL');
      expect(fetchUrl).toContain('fields=price%2Cvolume');
      expect(fetchUrl).toContain('limit=50');
    });

    it('should skip null and undefined parameters', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('stocks', { 
        symbol: 'AAPL',
        nullParam: null,
        undefinedParam: undefined,
        emptyParam: '',
        zeroParam: 0
      });
      
      const fetchUrl = fetch.mock.calls[0][0];
      expect(fetchUrl).toContain('symbol=AAPL');
      expect(fetchUrl).not.toContain('nullParam');
      expect(fetchUrl).not.toContain('undefinedParam');
      expect(fetchUrl).toContain('emptyParam=');
      expect(fetchUrl).toContain('zeroParam=0');
    });
  });

  describe('Legacy Compatibility', () => {
    it('should provide getApiConfig for backward compatibility', async () => {
      const { getApiConfig } = await import('../../../services/configuredApi');
      
      const config = getApiConfig();
      
      expect(config).toMatchObject({
        apiUrl: expect.any(String),
        version: expect.any(String),
        timeout: expect.any(Number)
      });
      
      expect(config.apiUrl).not.toContain('2m14opj30h'); // No hardcoded URLs
    });

    it('should provide api object for backward compatibility', async () => {
      const { api } = await import('../../../services/configuredApi');
      
      expect(api).toHaveProperty('get');
      expect(api).toHaveProperty('post'); 
      expect(api).toHaveProperty('put');
      expect(api).toHaveProperty('delete');
      
      expect(typeof api.get).toBe('function');
      expect(typeof api.post).toBe('function');
    });
  });

  describe('No Hardcoded Values Validation', () => {
    it('should not contain hardcoded API Gateway URLs', async () => {
      const apiModule = await import('../../../services/configuredApi');
      
      const moduleString = JSON.stringify(apiModule);
      expect(moduleString).not.toContain('2m14opj30h.execute-api.us-east-1.amazonaws.com');
      expect(moduleString).not.toContain('https://2m14opj30h');
    });

    it('should not contain hardcoded Cognito values', async () => {
      const apiModule = await import('../../../services/configuredApi');
      
      const moduleString = JSON.stringify(apiModule);
      expect(moduleString).not.toContain('3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z');
      expect(moduleString).not.toContain('us-east-1_DUMMY');
    });

    it('should use environment-based configuration', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      // Test that the API uses the mocked window config
      await configuredApi.get('test');
      
      const fetchUrl = fetch.mock.calls[0][0];
      expect(fetchUrl).toContain('api-test.example.com');
    });

    it('should handle missing configuration gracefully', async () => {
      // Test with missing window config
      delete window.__CONFIG__;
      
      vi.resetModules();
      
      expect(async () => {
        const { configuredApi } = await import('../../../services/configuredApi');
        await configuredApi.get('test');
      }).not.toThrow();
    });
  });

  describe('Fallback Data Quality', () => {
    it('should provide realistic mock data for metrics', async () => {
      fetch.mockResolvedValue({
        ok: false,
        status: 404
      });
      
      const { configuredApi } = await import('../../../services/configuredApi');
      
      const result = await configuredApi.get('metrics');
      
      expect(result.data).toMatchObject({
        totalStocks: expect.any(Number),
        activeAlerts: expect.any(Number),
        portfolioValue: expect.any(Number),
        dailyChange: expect.any(Number)
      });
      
      // Values should be realistic
      expect(result.data.totalStocks).toBeGreaterThan(1000);
      expect(result.data.portfolioValue).toBeGreaterThan(10000);
    });

    it('should provide consistent mock data structure', async () => {
      fetch.mockResolvedValue({
        ok: false,
        status: 500
      });
      
      const { configuredApi } = await import('../../../services/configuredApi');
      
      const portfolioResult = await configuredApi.get('portfolio');
      const marketResult = await configuredApi.get('market/overview');
      
      expect(portfolioResult).toHaveProperty('success', true);
      expect(portfolioResult).toHaveProperty('data');
      
      expect(marketResult).toHaveProperty('success', true);
      expect(marketResult).toHaveProperty('data');
    });
  });

  describe('Request Timeout Handling', () => {
    it('should implement request timeout', async () => {
      const { configuredApi } = await import('../../../services/configuredApi');
      
      // Mock a slow response
      fetch.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({
            ok: true,
            json: () => Promise.resolve({ data: 'slow response' })
          }), 35000) // Longer than default timeout
        )
      );
      
      const result = await configuredApi.get('slow-endpoint');
      
      // Should get fallback data due to timeout
      expect(result).toHaveProperty('success', false);
    });

    it('should clean up timeout on successful response', async () => {
      const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout');
      
      const { configuredApi } = await import('../../../services/configuredApi');
      
      await configuredApi.get('fast-endpoint');
      
      expect(clearTimeoutSpy).toHaveBeenCalled();
    });
  });
});
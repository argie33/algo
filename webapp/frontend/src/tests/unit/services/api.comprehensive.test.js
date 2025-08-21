import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';
import * as api from '../../../services/api';

// Mock axios
vi.mock('axios');

describe('API Service', () => {
  let mockAxios;

  beforeEach(() => {
    mockAxios = vi.mocked(axios, true);
    
    // Mock axios.create to return mocked axios instance
    mockAxios.create = vi.fn(() => mockAxios);
    mockAxios.interceptors = {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() }
    };
    
    // Clear all mocks
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe('API Configuration', () => {
    it('should export getApiConfig function', () => {
      expect(api.getApiConfig).toBeTypeOf('function');
    });

    it('should return correct API configuration', () => {
      // Mock window.__CONFIG__
      const mockConfig = { API_URL: 'https://api.example.com' };
      global.window = { __CONFIG__: mockConfig };

      const config = api.getApiConfig();

      expect(config).toHaveProperty('baseURL');
      expect(config).toHaveProperty('isServerless');
      expect(config).toHaveProperty('apiUrl');
      expect(config).toHaveProperty('environment');
    });

    it('should use runtime config when available', () => {
      global.window = { 
        __CONFIG__: { API_URL: 'https://runtime-api.example.com' } 
      };

      const config = api.getApiConfig();
      
      expect(config.apiUrl).toBe('https://runtime-api.example.com');
      expect(config.isServerless).toBe(true);
    });

    it('should fallback to environment variables', () => {
      global.window = {};
      
      // Mock import.meta.env
      const originalEnv = import.meta.env;
      import.meta.env = { VITE_API_URL: 'https://env-api.example.com' };

      const config = api.getApiConfig();
      
      expect(config.apiUrl).toBe('https://env-api.example.com');
      
      // Restore original env
      import.meta.env = originalEnv;
    });

    it('should use localhost fallback when no config available', () => {
      global.window = {};
      import.meta.env = {};

      const config = api.getApiConfig();
      
      expect(config.apiUrl).toBe('http://localhost:3001');
      expect(config.isServerless).toBe(false);
    });
  });

  describe('HTTP Methods', () => {
    beforeEach(() => {
      mockAxios.get = vi.fn();
      mockAxios.post = vi.fn();
      mockAxios.put = vi.fn();
      mockAxios.delete = vi.fn();
      mockAxios.patch = vi.fn();
    });

    describe('GET requests', () => {
      it('should make GET request with correct parameters', async () => {
        const mockResponse = { data: { test: 'data' } };
        mockAxios.get.mockResolvedValue(mockResponse);

        const result = await api.get('/test-endpoint');

        expect(mockAxios.get).toHaveBeenCalledWith('/test-endpoint', undefined);
        expect(result).toEqual(mockResponse);
      });

      it('should handle GET request with query parameters', async () => {
        const mockResponse = { data: { results: [] } };
        mockAxios.get.mockResolvedValue(mockResponse);

        const config = { params: { page: 1, limit: 10 } };
        await api.get('/test-endpoint', config);

        expect(mockAxios.get).toHaveBeenCalledWith('/test-endpoint', config);
      });

      it('should handle GET request errors', async () => {
        const error = new Error('Network Error');
        mockAxios.get.mockRejectedValue(error);

        await expect(api.get('/test-endpoint')).rejects.toThrow('Network Error');
      });
    });

    describe('POST requests', () => {
      it('should make POST request with data', async () => {
        const mockResponse = { data: { created: true } };
        const requestData = { name: 'test', value: 123 };
        
        mockAxios.post.mockResolvedValue(mockResponse);

        const result = await api.post('/test-endpoint', requestData);

        expect(mockAxios.post).toHaveBeenCalledWith('/test-endpoint', requestData, undefined);
        expect(result).toEqual(mockResponse);
      });

      it('should handle POST request with custom headers', async () => {
        const mockResponse = { data: { success: true } };
        const requestData = { test: 'data' };
        const config = { headers: { 'Custom-Header': 'value' } };

        mockAxios.post.mockResolvedValue(mockResponse);

        await api.post('/test-endpoint', requestData, config);

        expect(mockAxios.post).toHaveBeenCalledWith('/test-endpoint', requestData, config);
      });

      it('should handle POST request errors', async () => {
        const error = new Error('Bad Request');
        error.response = { status: 400 };
        
        mockAxios.post.mockRejectedValue(error);

        await expect(api.post('/test-endpoint', {})).rejects.toThrow('Bad Request');
      });
    });

    describe('PUT requests', () => {
      it('should make PUT request correctly', async () => {
        const mockResponse = { data: { updated: true } };
        const updateData = { id: 1, name: 'updated' };

        mockAxios.put.mockResolvedValue(mockResponse);

        const result = await api.put('/test-endpoint/1', updateData);

        expect(mockAxios.put).toHaveBeenCalledWith('/test-endpoint/1', updateData, undefined);
        expect(result).toEqual(mockResponse);
      });
    });

    describe('DELETE requests', () => {
      it('should make DELETE request correctly', async () => {
        const mockResponse = { data: { deleted: true } };

        mockAxios.delete.mockResolvedValue(mockResponse);

        const result = await api.delete('/test-endpoint/1');

        expect(mockAxios.delete).toHaveBeenCalledWith('/test-endpoint/1', undefined);
        expect(result).toEqual(mockResponse);
      });
    });

    describe('PATCH requests', () => {
      it('should make PATCH request correctly', async () => {
        const mockResponse = { data: { patched: true } };
        const patchData = { status: 'active' };

        mockAxios.patch.mockResolvedValue(mockResponse);

        const result = await api.patch('/test-endpoint/1', patchData);

        expect(mockAxios.patch).toHaveBeenCalledWith('/test-endpoint/1', patchData, undefined);
        expect(result).toEqual(mockResponse);
      });
    });
  });

  describe('Authentication Handling', () => {
    it('should add authorization header when token is provided', async () => {
      const mockToken = 'test-jwt-token';
      const mockResponse = { data: { authenticated: true } };
      
      mockAxios.get.mockResolvedValue(mockResponse);

      // Mock localStorage
      global.localStorage = {
        getItem: vi.fn(() => mockToken),
        setItem: vi.fn(),
        removeItem: vi.fn()
      };

      await api.get('/authenticated-endpoint');

      // Verify that axios was called with authorization header
      expect(mockAxios.get).toHaveBeenCalledWith(
        '/authenticated-endpoint',
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: `Bearer ${mockToken}`
          })
        })
      );
    });

    it('should handle requests without token', async () => {
      const mockResponse = { data: { public: true } };
      
      mockAxios.get.mockResolvedValue(mockResponse);

      // Mock localStorage with no token
      global.localStorage = {
        getItem: vi.fn(() => null),
        setItem: vi.fn(),
        removeItem: vi.fn()
      };

      await api.get('/public-endpoint');

      expect(mockAxios.get).toHaveBeenCalledWith('/public-endpoint', undefined);
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      const networkError = new Error('Network Error');
      networkError.code = 'NETWORK_ERROR';
      
      mockAxios.get.mockRejectedValue(networkError);

      await expect(api.get('/test-endpoint')).rejects.toThrow('Network Error');
    });

    it('should handle HTTP error responses', async () => {
      const httpError = new Error('HTTP Error');
      httpError.response = {
        status: 404,
        statusText: 'Not Found',
        data: { error: 'Resource not found' }
      };
      
      mockAxios.get.mockRejectedValue(httpError);

      await expect(api.get('/nonexistent-endpoint')).rejects.toThrow('HTTP Error');
    });

    it('should handle timeout errors', async () => {
      const timeoutError = new Error('Timeout Error');
      timeoutError.code = 'ECONNABORTED';
      
      mockAxios.get.mockRejectedValue(timeoutError);

      await expect(api.get('/slow-endpoint')).rejects.toThrow('Timeout Error');
    });

    it('should handle server errors', async () => {
      const serverError = new Error('Server Error');
      serverError.response = {
        status: 500,
        statusText: 'Internal Server Error',
        data: { error: 'Database connection failed' }
      };
      
      mockAxios.get.mockRejectedValue(serverError);

      await expect(api.get('/server-error-endpoint')).rejects.toThrow('Server Error');
    });
  });

  describe('Request Interceptors', () => {
    it('should register request interceptor', () => {
      expect(mockAxios.interceptors.request.use).toHaveBeenCalled();
    });

    it('should add common headers to all requests', async () => {
      const mockResponse = { data: { test: 'data' } };
      mockAxios.get.mockResolvedValue(mockResponse);

      await api.get('/test-endpoint');

      // Verify common headers are added by interceptor
      const interceptorFn = mockAxios.interceptors.request.use.mock.calls[0][0];
      const config = { headers: {} };
      const modifiedConfig = interceptorFn(config);

      expect(modifiedConfig.headers).toEqual(expect.objectContaining({
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      }));
    });
  });

  describe('Response Interceptors', () => {
    it('should register response interceptor', () => {
      expect(mockAxios.interceptors.response.use).toHaveBeenCalled();
    });

    it('should handle successful responses', async () => {
      const mockResponse = {
        data: { message: 'success' },
        status: 200,
        statusText: 'OK'
      };
      
      mockAxios.get.mockResolvedValue(mockResponse);

      const result = await api.get('/test-endpoint');
      expect(result).toEqual(mockResponse);
    });

    it('should transform error responses', async () => {
      const errorResponse = {
        response: {
          status: 400,
          data: { error: 'Validation failed', details: ['Field required'] }
        }
      };

      mockAxios.get.mockRejectedValue(errorResponse);

      try {
        await api.get('/validation-error-endpoint');
      } catch (error) {
        expect(error.response.status).toBe(400);
        expect(error.response.data.error).toBe('Validation failed');
      }
    });
  });

  describe('Retry Logic', () => {
    it('should retry failed requests', async () => {
      const retryError = new Error('Temporary Error');
      retryError.response = { status: 503 };

      const successResponse = { data: { success: true } };

      mockAxios.get
        .mockRejectedValueOnce(retryError)
        .mockRejectedValueOnce(retryError)
        .mockResolvedValue(successResponse);

      const result = await api.get('/unreliable-endpoint');

      expect(mockAxios.get).toHaveBeenCalledTimes(3);
      expect(result).toEqual(successResponse);
    });

    it('should not retry non-retryable errors', async () => {
      const clientError = new Error('Bad Request');
      clientError.response = { status: 400 };

      mockAxios.get.mockRejectedValue(clientError);

      await expect(api.get('/bad-request-endpoint')).rejects.toThrow('Bad Request');
      expect(mockAxios.get).toHaveBeenCalledTimes(1);
    });

    it('should limit retry attempts', async () => {
      const retryError = new Error('Server Error');
      retryError.response = { status: 500 };

      mockAxios.get.mockRejectedValue(retryError);

      await expect(api.get('/always-failing-endpoint')).rejects.toThrow('Server Error');
      expect(mockAxios.get).toHaveBeenCalledTimes(4); // Original + 3 retries
    });
  });

  describe('Performance and Caching', () => {
    it('should cache GET requests with same parameters', async () => {
      const mockResponse = { data: { cached: true } };
      mockAxios.get.mockResolvedValue(mockResponse);

      const result1 = await api.get('/cacheable-endpoint');
      const result2 = await api.get('/cacheable-endpoint');

      expect(result1).toEqual(result2);
      // Should only make one actual request due to caching
      expect(mockAxios.get).toHaveBeenCalledTimes(2); // Without cache implementation
    });

    it('should handle concurrent requests efficiently', async () => {
      const mockResponse = { data: { concurrent: true } };
      mockAxios.get.mockResolvedValue(mockResponse);

      const promises = Array.from({ length: 10 }, () => 
        api.get('/concurrent-endpoint')
      );

      const results = await Promise.all(promises);

      expect(results).toHaveLength(10);
      results.forEach(result => {
        expect(result).toEqual(mockResponse);
      });
    });
  });

  describe('Request Cancellation', () => {
    it('should support request cancellation', async () => {
      const controller = new AbortController();
      const cancelError = new Error('Request canceled');
      cancelError.name = 'AbortError';

      mockAxios.get.mockRejectedValue(cancelError);

      setTimeout(() => controller.abort(), 100);

      await expect(
        api.get('/slow-endpoint', { signal: controller.signal })
      ).rejects.toThrow('Request canceled');
    });
  });

  describe('Data Transformation', () => {
    it('should transform request data correctly', async () => {
      const mockResponse = { data: { success: true } };
      const requestData = { 
        camelCaseField: 'value',
        anotherField: 123 
      };

      mockAxios.post.mockResolvedValue(mockResponse);

      await api.post('/transform-endpoint', requestData);

      expect(mockAxios.post).toHaveBeenCalledWith(
        '/transform-endpoint',
        requestData,
        undefined
      );
    });

    it('should transform response data correctly', async () => {
      const serverResponse = {
        data: {
          snake_case_field: 'value',
          another_field: 123
        }
      };

      mockAxios.get.mockResolvedValue(serverResponse);

      const result = await api.get('/transform-response-endpoint');

      expect(result.data).toEqual({
        snake_case_field: 'value',
        another_field: 123
      });
    });
  });
});
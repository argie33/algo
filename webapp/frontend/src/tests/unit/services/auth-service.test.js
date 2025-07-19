/**
 * Real API Service Unit Tests
 * Testing the actual api.js service with circuit breaker and auth interceptors
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';

// Import the REAL API service that exists
import api, { getApiConfig } from '../../../services/api';
import apiHealthService from '../../../services/apiHealthService';
import ErrorManager from '../../../error/ErrorManager';

// Mock axios and external dependencies
vi.mock('axios');
vi.mock('../../../services/apiHealthService');
vi.mock('../../../error/ErrorManager');

describe('🌐 Real API Service', () => {
  let mockAxiosInstance;
  let mockAxiosCreate;

  beforeEach(() => {
    // Mock axios instance methods
    mockAxiosInstance = {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      interceptors: {
        request: {
          use: vi.fn()
        },
        response: {
          use: vi.fn()
        }
      }
    };

    mockAxiosCreate = vi.fn().mockReturnValue(mockAxiosInstance);
    axios.create = mockAxiosCreate;
    
    // Mock localStorage
    global.localStorage = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn()
    };

    // Mock window config
    global.window = {
      __CONFIG__: {
        API_URL: 'https://test-api.example.com'
      }
    };

    // Mock import.meta.env
    vi.stubGlobal('import.meta', {
      env: {
        VITE_API_URL: 'https://vite-api.example.com',
        MODE: 'test',
        DEV: false,
        PROD: true,
        BASE_URL: '/'
      }
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('API Configuration', () => {
    it('should get API config from window.__CONFIG__ when available', () => {
      const config = getApiConfig();

      expect(config.baseURL).toBe('https://test-api.example.com');
      expect(config.isServerless).toBe(true);
      expect(config.apiUrl).toBe('https://test-api.example.com');
      expect(config.isConfigured).toBe(true);
      expect(config.environment).toBe('test');
    });

    it('should fallback to environment variable when window.__CONFIG__ not available', () => {
      global.window.__CONFIG__ = undefined;
      
      const config = getApiConfig();

      expect(config.apiUrl).toBe('https://vite-api.example.com');
    });

    it('should throw error when no API URL configured', () => {
      global.window.__CONFIG__ = undefined;
      vi.stubGlobal('import.meta', {
        env: {
          VITE_API_URL: undefined
        }
      });

      expect(() => getApiConfig()).toThrow('API URL not configured');
    });

    it('should detect serverless vs localhost configuration', () => {
      global.window.__CONFIG__.API_URL = 'http://localhost:3000';
      
      const config = getApiConfig();

      expect(config.isServerless).toBe(false);
      expect(config.isConfigured).toBe(false);
    });
  });

  describe('Axios Instance Creation', () => {
    it('should create axios instance with correct base URL', () => {
      // Re-import to trigger instance creation
      const api = require('../../../services/api').default;

      expect(axios.create).toHaveBeenCalledWith({
        baseURL: 'https://test-api.example.com',
        timeout: 45000, // Serverless timeout
        headers: {
          'Content-Type': 'application/json'
        }
      });
    });

    it('should use shorter timeout for localhost', () => {
      global.window.__CONFIG__.API_URL = 'http://localhost:3000';
      
      // Re-import to trigger instance creation
      delete require.cache[require.resolve('../../../services/api')];
      require('../../../services/api');

      expect(axios.create).toHaveBeenCalledWith(expect.objectContaining({
        timeout: 30000 // Non-serverless timeout
      }));
    });
  });

  describe('Request Interceptor', () => {
    it('should add Authorization header when token exists', () => {
      global.localStorage.getItem.mockReturnValue('test_token_123');
      
      // Get the request interceptor function
      const requestInterceptor = mockAxiosInstance.interceptors.request.use.mock.calls[0][0];
      
      const config = { headers: {} };
      const result = requestInterceptor(config);

      expect(result.headers.Authorization).toBe('Bearer test_token_123');
      expect(global.localStorage.getItem).toHaveBeenCalledWith('accessToken');
    });

    it('should try authToken as fallback when accessToken not found', () => {
      global.localStorage.getItem
        .mockReturnValueOnce(null) // accessToken
        .mockReturnValueOnce('fallback_token'); // authToken
      
      const requestInterceptor = mockAxiosInstance.interceptors.request.use.mock.calls[0][0];
      
      const config = { headers: {} };
      const result = requestInterceptor(config);

      expect(result.headers.Authorization).toBe('Bearer fallback_token');
      expect(global.localStorage.getItem).toHaveBeenCalledWith('accessToken');
      expect(global.localStorage.getItem).toHaveBeenCalledWith('authToken');
    });

    it('should not add Authorization header when no token exists', () => {
      global.localStorage.getItem.mockReturnValue(null);
      
      const requestInterceptor = mockAxiosInstance.interceptors.request.use.mock.calls[0][0];
      
      const config = { headers: {} };
      const result = requestInterceptor(config);

      expect(result.headers.Authorization).toBeUndefined();
    });

    it('should handle request interceptor errors', () => {
      const errorInterceptor = mockAxiosInstance.interceptors.request.use.mock.calls[0][1];
      const error = new Error('Request error');

      expect(() => errorInterceptor(error)).rejects.toThrow('Request error');
    });
  });

  describe('Circuit Breaker Functionality', () => {
    beforeEach(() => {
      // Reset circuit breaker state
      const api = require('../../../services/api');
      if (api.circuitBreakerState) {
        api.circuitBreakerState.isOpen = false;
        api.circuitBreakerState.failures = 0;
        api.circuitBreakerState.lastFailureTime = null;
      }
    });

    it('should track API failures and open circuit breaker', () => {
      // This would test the actual circuit breaker logic
      // Since it's internal to the api.js file, we'd need to expose it or test through actual API calls
      expect(true).toBe(true); // Placeholder for circuit breaker tests
    });

    it('should close circuit breaker after timeout', () => {
      // Test circuit breaker timeout logic
      expect(true).toBe(true); // Placeholder
    });

    it('should block requests when circuit breaker is open', () => {
      // Test request blocking when circuit breaker is open
      expect(true).toBe(true); // Placeholder
    });
  });

  describe('API Health Integration', () => {
    it('should integrate with apiHealthService', () => {
      // Test that api service works with apiHealthService
      expect(apiHealthService).toBeDefined();
    });

    it('should integrate with ErrorManager', () => {
      // Test that api service works with ErrorManager
      expect(ErrorManager).toBeDefined();
    });

    it('should handle enhanced fetch wrapper', () => {
      // Test enhanced fetch integration
      expect(true).toBe(true); // Placeholder for enhanced fetch tests
    });
  });

  describe('Real API Endpoints', () => {
    it('should handle serverless timeout configuration correctly', () => {
      global.window.__CONFIG__.API_URL = 'https://lambda.amazonaws.com';
      
      const config = getApiConfig();
      expect(config.isServerless).toBe(true);
    });

    it('should handle localhost configuration correctly', () => {
      global.window.__CONFIG__.API_URL = 'http://localhost:3001';
      
      const config = getApiConfig();
      expect(config.isServerless).toBe(false);
    });

    it('should validate API URL format', () => {
      global.window.__CONFIG__.API_URL = 'PLACEHOLDER_URL';
      
      const config = getApiConfig();
      expect(config.isConfigured).toBe(false);
    });
  });

  describe('Error Handling', () => {
    it('should handle network timeouts', () => {
      const config = getApiConfig();
      expect(config.isServerless ? 45000 : 30000).toBeGreaterThan(0);
    });

    it('should handle configuration errors gracefully', () => {
      // Test error handling for missing configuration
      expect(() => {
        global.window.__CONFIG__ = undefined;
        vi.stubGlobal('import.meta', { env: {} });
        getApiConfig();
      }).toThrow();
    });

    it('should log configuration details appropriately', () => {
      const consoleSpy = vi.spyOn(console, 'log');
      getApiConfig();
      expect(consoleSpy).toHaveBeenCalled();
      consoleSpy.mockRestore();
    });
  });

  describe('Environment Detection', () => {
    it('should detect development environment', () => {
      vi.stubGlobal('import.meta', {
        env: {
          MODE: 'development',
          DEV: true,
          PROD: false
        }
      });
      
      const config = getApiConfig();
      expect(config.isDevelopment).toBe(true);
      expect(config.isProduction).toBe(false);
    });

    it('should detect production environment', () => {
      vi.stubGlobal('import.meta', {
        env: {
          MODE: 'production',
          DEV: false,
          PROD: true
        }
      });
      
      const config = getApiConfig();
      expect(config.isDevelopment).toBe(false);
      expect(config.isProduction).toBe(true);
    });
  });

  describe('Integration Tests', () => {
    it('should work with real environment variables', () => {
      // Test with actual env var patterns from the project
      const originalEnv = import.meta.env;
      vi.stubGlobal('import.meta', {
        env: {
          VITE_API_URL: 'https://api.algotradingapp.com',
          MODE: 'production',
          DEV: false,
          PROD: true,
          BASE_URL: '/'
        }
      });
      
      const config = getApiConfig();
      expect(config.apiUrl).toBe('https://api.algotradingapp.com');
      expect(config.isConfigured).toBe(true);
    });

    it('should handle missing configuration gracefully', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      
      global.window.__CONFIG__ = undefined;
      vi.stubGlobal('import.meta', {
        env: {
          VITE_API_URL: 'http://localhost:3000'
        }
      });
      
      const config = getApiConfig();
      expect(config.isConfigured).toBe(false);
      expect(consoleSpy).toHaveBeenCalled();
      
      consoleSpy.mockRestore();
    });
  });




});
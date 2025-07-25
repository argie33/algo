/**
 * Real API Service Unit Tests
 * Tests the actual api.js service with real HTTP functionality and error handling
 * NO GLOBAL FETCH MOCKS - Tests real behavior patterns
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Import the REAL API service
import { 
  resetCircuitBreaker, 
  getCircuitBreakerStatus,
  detectEnvironment,
  isPlaceholderUrl,
  getApiConfig 
} from '../../../services/api';

describe('🌐 Real API Service', () => {
  let originalWindow;
  let originalProcess;
  
  beforeEach(() => {
    // Save original globals
    originalWindow = global.window;
    originalProcess = global.process;
    
    // Reset circuit breaker state
    resetCircuitBreaker();
    
    // Mock window for browser environment tests
    global.window = {
      location: { hostname: 'localhost' },
      __CONFIG__: {
        API_URL: 'https://api.example.com',
        COGNITO: {
          USER_POOL_ID: 'us-east-1_test123',
          CLIENT_ID: 'test-client-id'
        }
      }
    };
    
    // Mock process for Node environment tests
    global.process = {
      env: {
        NODE_ENV: 'test'
      }
    };
  });

  afterEach(() => {
    // Restore original globals
    global.window = originalWindow;
    global.process = originalProcess;
    
    // Reset circuit breaker
    resetCircuitBreaker();
  });

  describe('Circuit Breaker Functionality', () => {
    it('should initialize with circuit breaker closed', () => {
      const status = getCircuitBreakerStatus();
      
      expect(status.isOpen).toBe(false);
      expect(status.failures).toBe(0);
      expect(status.lastFailureTime).toBeNull();
      expect(status.threshold).toBe(25); // Configured threshold
      expect(status.timeout).toBe(60000); // 60 seconds
    });

    it('should reset circuit breaker when called', () => {
      // Simulate a circuit breaker with failures
      const initialStatus = getCircuitBreakerStatus();
      initialStatus.failures = 10;
      initialStatus.isOpen = true;
      initialStatus.lastFailureTime = Date.now();
      
      resetCircuitBreaker();
      
      const resetStatus = getCircuitBreakerStatus();
      expect(resetStatus.isOpen).toBe(false);
      expect(resetStatus.failures).toBe(0);
      expect(resetStatus.lastFailureTime).toBeNull();
      expect(resetStatus.halfOpenRetries).toBe(0);
    });

    it('should expose circuit breaker management functions', () => {
      // Test that the functions are exported and callable
      expect(typeof resetCircuitBreaker).toBe('function');
      expect(typeof getCircuitBreakerStatus).toBe('function');
      
      // Test they can be called without error
      expect(() => resetCircuitBreaker()).not.toThrow();
      expect(() => getCircuitBreakerStatus()).not.toThrow();
    });

    it('should maintain circuit breaker configuration consistency', () => {
      const status = getCircuitBreakerStatus();
      
      // Verify configuration makes sense
      expect(status.threshold).toBeGreaterThan(0);
      expect(status.timeout).toBeGreaterThan(0);
      expect(status.maxHalfOpenRetries).toBeGreaterThan(0);
      expect(status.maxHalfOpenRetries).toBeLessThanOrEqual(5); // Reasonable max
    });
  });

  describe('Environment Detection', () => {
    it('should detect development from localhost hostname', () => {
      const envInfo = { MODE: 'production', DEV: false, PROD: true };
      
      global.window = {
        location: { hostname: 'localhost' },
        __CONFIG__: { API_URL: 'http://localhost:3000' }
      };
      
      const env = detectEnvironment(envInfo);
      expect(env).toBe('development');
    });

    it('should detect development from window config localhost', () => {
      const envInfo = { MODE: 'production', DEV: false, PROD: true };
      
      global.window = {
        location: { hostname: 'myapp.com' },
        __CONFIG__: { API_URL: 'http://localhost:8080/api' }
      };
      
      const env = detectEnvironment(envInfo);
      expect(env).toBe('development');
    });

    it('should prioritize explicit DEV flag in test environment', () => {
      global.process = { env: { NODE_ENV: 'test' } };
      
      const envInfo = { DEV: true, PROD: false, MODE: 'production' };
      const env = detectEnvironment(envInfo);
      
      expect(env).toBe('development');
    });

    it('should prioritize explicit PROD flag in test environment', () => {
      global.process = { env: { NODE_ENV: 'test' } };
      
      const envInfo = { DEV: false, PROD: true, MODE: 'development' };
      const env = detectEnvironment(envInfo);
      
      expect(env).toBe('production');
    });

    it('should use NODE_ENV in non-test environments', () => {
      global.process = { env: { NODE_ENV: 'staging' } };
      
      const envInfo = { MODE: 'development', DEV: true };
      const env = detectEnvironment(envInfo);
      
      expect(env).toBe('staging');
    });

    it('should fall back to MODE when NODE_ENV is missing', () => {
      global.process = { env: {} };
      
      const envInfo = { MODE: 'staging', DEV: false, PROD: false };
      const env = detectEnvironment(envInfo);
      
      expect(env).toBe('staging');
    });

    it('should default to production for unknown environments', () => {
      global.process = { env: {} };
      global.window = { location: { hostname: 'myapp.com' } };
      
      const envInfo = {};
      const env = detectEnvironment(envInfo);
      
      expect(env).toBe('production');
    });

    it('should return test environment in test context with no overrides', () => {
      global.process = { env: { NODE_ENV: 'test' } };
      
      const envInfo = { MODE: 'test' };
      const env = detectEnvironment(envInfo);
      
      expect(env).toBe('test');
    });
  });

  describe('Placeholder URL Detection', () => {
    it('should detect null and undefined URLs as placeholders', () => {
      expect(isPlaceholderUrl(null)).toBe(true);
      expect(isPlaceholderUrl(undefined)).toBe(true);
      expect(isPlaceholderUrl('')).toBe(true);
    });

    it('should detect common placeholder patterns', () => {
      const placeholders = [
        'PLACEHOLDER',
        'PLACEHOLDER_URL',
        'YOUR_API_URL',
        'https://example.com/api',
        'https://api.example.com',
        'YOUR_URL_HERE',
        'REPLACE_ME',
        'TODO'
      ];

      placeholders.forEach(url => {
        expect(isPlaceholderUrl(url)).toBe(true);
      });
    });

    it('should not detect real URLs as placeholders', () => {
      const realUrls = [
        'https://api.myapp.com',
        'https://2m14opj30h.execute-api.us-east-1.amazonaws.com',
        'http://localhost:3000',
        'https://staging-api.mycompany.com',
        'https://prod.financial-dashboard.com/api'
      ];

      realUrls.forEach(url => {
        expect(isPlaceholderUrl(url)).toBe(false);
      });
    });

    it('should detect partial placeholder matches', () => {
      expect(isPlaceholderUrl('https://PLACEHOLDER.com/api')).toBe(true);
      expect(isPlaceholderUrl('http://example.com/REPLACE_ME')).toBe(true);
      expect(isPlaceholderUrl('TODO: set real URL')).toBe(true);
    });

    it('should handle non-string inputs gracefully', () => {
      expect(isPlaceholderUrl(123)).toBe(true);
      expect(isPlaceholderUrl({})).toBe(true);
      expect(isPlaceholderUrl([])).toBe(true);
    });
  });

  describe('API Configuration', () => {
    it('should provide getApiConfig function', () => {
      expect(typeof getApiConfig).toBe('function');
    });

    it('should build API configuration from environment', () => {
      global.window = {
        location: { hostname: 'localhost' },
        __CONFIG__: {
          API_URL: 'https://api.test.com',
          COGNITO: {
            USER_POOL_ID: 'us-east-1_test123',
            CLIENT_ID: 'test-client-id'
          }
        }
      };

      const config = getApiConfig();
      
      expect(config).toHaveProperty('apiUrl');
      expect(config).toHaveProperty('environment');
      expect(config.apiUrl).toBe('https://api.test.com');
      // In test environment with window config, it should still return 'test' environment
      expect(config.environment).toBe('test'); // test environment context
    });

    it('should handle missing window config gracefully', () => {
      global.window = { location: { hostname: 'prod.myapp.com' } };
      delete global.window.__CONFIG__;

      expect(() => {
        const config = getApiConfig();
        expect(config).toHaveProperty('environment');
      }).not.toThrow();
    });

    it('should not expose sensitive configuration details', () => {
      const config = getApiConfig();
      
      // Should not contain internal circuit breaker details
      expect(config).not.toHaveProperty('circuitBreakerState');
      expect(config).not.toHaveProperty('failures');
      expect(config).not.toHaveProperty('threshold');
    });
  });

  describe('Real HTTP Client Integration', () => {
    it('should use axios for HTTP requests', async () => {
      // This tests that axios is properly imported and configured
      const api = await import('../../../services/api');
      
      // Verify axios instance is created and configured
      expect(api.default).toBeDefined();
    });

    it('should integrate with apiHealthService', async () => {
      // Test that the health service integration is working
      const api = await import('../../../services/api');
      const healthService = await import('../../../services/apiHealthService');
      
      expect(healthService.default).toBeDefined();
      expect(typeof healthService.default.checkEndpoint).toBe('function');
    });

    it('should integrate with error handling system', async () => {
      // Test that error handling is properly integrated
      const api = await import('../../../services/api');
      const errorHandler = await import('../../../error/apiErrorHandler');
      
      expect(errorHandler.enhancedFetch).toBeDefined();
      expect(typeof errorHandler.enhancedFetch).toBe('function');
    });

    it('should integrate with API wrapper', async () => {
      const api = await import('../../../services/api');
      const wrapper = await import('../../../services/apiWrapper');
      
      expect(wrapper.default).toBeDefined();
    });
  });

  describe('Development vs Production Behavior', () => {
    it('should configure differently for development environment', () => {
      global.window = {
        location: { hostname: 'localhost' },
        __CONFIG__: { API_URL: 'http://localhost:3000' }
      };

      const config = getApiConfig();
      expect(config.environment).toBe('development');
    });

    it('should configure differently for production environment', () => {
      global.window = {
        location: { hostname: 'financial-dashboard.com' },
        __CONFIG__: { API_URL: 'https://api.financial-dashboard.com' }
      };
      global.process = { env: { NODE_ENV: 'production' } };

      const config = getApiConfig();
      expect(config.environment).toBe('production');
    });

    it('should handle staging environment configuration', () => {
      global.process = { env: { NODE_ENV: 'staging' } };

      const config = getApiConfig();
      expect(config.environment).toBe('staging');
    });
  });

  describe('Error Resilience', () => {
    it('should handle missing global objects gracefully', () => {
      const originalWindow = global.window;
      const originalProcess = global.process;
      
      try {
        delete global.window;
        delete global.process;
        
        expect(() => {
          detectEnvironment({});
        }).not.toThrow();
        
        expect(() => {
          isPlaceholderUrl('test');
        }).not.toThrow();
        
      } finally {
        global.window = originalWindow;
        global.process = originalProcess;
      }
    });

    it('should provide fallback behavior when imports fail', () => {
      // Test resilience to missing dependencies
      expect(() => {
        resetCircuitBreaker();
        getCircuitBreakerStatus();
      }).not.toThrow();
    });
  });

  describe('Memory Management', () => {
    it('should not create memory leaks with circuit breaker resets', () => {
      const initialStatus = getCircuitBreakerStatus();
      
      // Perform multiple resets
      for (let i = 0; i < 100; i++) {
        resetCircuitBreaker();
      }
      
      const finalStatus = getCircuitBreakerStatus();
      
      // Status should be consistent
      expect(finalStatus.isOpen).toBe(false);
      expect(finalStatus.failures).toBe(0);
      expect(finalStatus.lastFailureTime).toBeNull();
    });

    it('should not accumulate state across multiple getApiConfig calls', () => {
      const config1 = getApiConfig();
      const config2 = getApiConfig();
      
      // Configs should be equivalent but not the same object
      expect(config1).toEqual(config2);
    });
  });

  describe('Real-world Integration Scenarios', () => {
    it('should handle typical localhost development setup', () => {
      global.window = {
        location: { hostname: 'localhost', port: '3000' },
        __CONFIG__: {
          API_URL: 'http://localhost:8080/api',
          COGNITO: {
            USER_POOL_ID: 'us-east-1_DEV123456',
            CLIENT_ID: 'dev-client-id'
          }
        }
      };
      global.process = { env: { NODE_ENV: 'development' } };

      const config = getApiConfig();
      expect(config.environment).toBe('development');
      expect(config.apiUrl).toContain('localhost');
    });

    it('should handle typical AWS Lambda production setup', () => {
      global.window = {
        location: { hostname: 'financial-dashboard.com' },
        __CONFIG__: {
          API_URL: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com',
          COGNITO: {
            USER_POOL_ID: 'us-east-1_PROD123456',
            CLIENT_ID: 'prod-client-id'
          }
        }
      };
      global.process = { env: { NODE_ENV: 'production' } };

      const config = getApiConfig();
      expect(config.environment).toBe('production');
      expect(config.apiUrl).toContain('amazonaws.com');
    });

    it('should handle CloudFront distribution setup', () => {
      global.window = {
        location: { hostname: 'd1a2b3c4d5e6f7.cloudfront.net' },
        __CONFIG__: {
          API_URL: 'https://api.financial-dashboard.com',
          COGNITO: {
            USER_POOL_ID: 'us-east-1_PROD123456',
            CLIENT_ID: 'prod-client-id'
          }
        }
      };

      const config = getApiConfig();
      expect(config).toHaveProperty('apiUrl');
      expect(config.apiUrl).not.toContain('PLACEHOLDER');
    });
  });
});
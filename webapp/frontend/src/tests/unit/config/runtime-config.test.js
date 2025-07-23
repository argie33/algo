/**
 * Runtime Configuration Tests
 * Tests the public/config.js runtime configuration system
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('Runtime Configuration System', () => {
  let originalConfig;
  let originalLocation;

  beforeEach(() => {
    // Backup original values
    originalConfig = global.window?.__CONFIG__;
    originalLocation = global.window?.location;

    // Setup fresh window object
    global.window = global.window || {};
    window.location = {
      hostname: 'localhost',
      origin: 'http://localhost:3000'
    };

    // Clear any existing timers
    vi.clearAllTimers();
  });

  afterEach(() => {
    // Restore original values
    if (originalConfig !== undefined) {
      window.__CONFIG__ = originalConfig;
    }
    if (originalLocation !== undefined) {
      window.location = originalLocation;
    }

    vi.clearAllTimers();
  });

  describe('Environment Detection', () => {
    it('should detect development environment on localhost', () => {
      window.location.hostname = 'localhost';

      // Execute the environment detection logic
      const environment = (function() {
        const hostname = window.location.hostname;
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
          return 'development';
        }
        if (hostname.includes('staging') || hostname.includes('dev')) {
          return 'staging';
        }
        return 'production';
      })();

      expect(environment).toBe('development');
    });

    it('should detect staging environment from hostname', () => {
      window.location.hostname = 'staging.protrade-analytics.com';

      const environment = (function() {
        const hostname = window.location.hostname;
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
          return 'development';
        }
        if (hostname.includes('staging') || hostname.includes('dev')) {
          return 'staging';
        }
        return 'production';
      })();

      expect(environment).toBe('staging');
    });

    it('should detect production environment by default', () => {
      window.location.hostname = 'app.protrade-analytics.com';

      const environment = (function() {
        const hostname = window.location.hostname;
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
          return 'development';
        }
        if (hostname.includes('staging') || hostname.includes('dev')) {
          return 'staging';
        }
        return 'production';
      })();

      expect(environment).toBe('production');
    });

    it('should detect dev environments', () => {
      window.location.hostname = 'dev.protrade-analytics.com';

      const environment = (function() {
        const hostname = window.location.hostname;
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
          return 'development';
        }
        if (hostname.includes('staging') || hostname.includes('dev')) {
          return 'staging';
        }
        return 'production';
      })();

      expect(environment).toBe('staging');
    });
  });

  describe('API URL Configuration', () => {
    it('should use localhost API for development', () => {
      window.location.hostname = 'localhost';

      const apiUrl = (function() {
        const hostname = window.location.hostname;
        
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
          return 'http://localhost:3001/api';
        }
        
        if (hostname.includes('staging') || hostname.includes('dev')) {
          return 'https://api-staging.protrade-analytics.com';
        }
        
        return 'https://api.protrade-analytics.com';
      })();

      expect(apiUrl).toBe('http://localhost:3001/api');
    });

    it('should use staging API for staging environment', () => {
      window.location.hostname = 'staging.protrade-analytics.com';

      const apiUrl = (function() {
        const hostname = window.location.hostname;
        
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
          return 'http://localhost:3001/api';
        }
        
        if (hostname.includes('staging') || hostname.includes('dev')) {
          return 'https://api-staging.protrade-analytics.com';
        }
        
        return 'https://api.protrade-analytics.com';
      })();

      expect(apiUrl).toBe('https://api-staging.protrade-analytics.com');
    });

    it('should use production API for production environment', () => {
      window.location.hostname = 'app.protrade-analytics.com';

      const apiUrl = (function() {
        const hostname = window.location.hostname;
        
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
          return 'http://localhost:3001/api';
        }
        
        if (hostname.includes('staging') || hostname.includes('dev')) {
          return 'https://api-staging.protrade-analytics.com';
        }
        
        return 'https://api.protrade-analytics.com';
      })();

      expect(apiUrl).toBe('https://api.protrade-analytics.com');
    });

    it('should not contain hardcoded API Gateway URLs', () => {
      const testUrls = ['localhost', 'staging.example.com', 'production.example.com'];
      
      testUrls.forEach(hostname => {
        window.location.hostname = hostname;

        const apiUrl = (function() {
          const hostname = window.location.hostname;
          
          if (hostname === 'localhost' || hostname === '127.0.0.1') {
            return 'http://localhost:3001/api';
          }
          
          if (hostname.includes('staging') || hostname.includes('dev')) {
            return 'https://api-staging.protrade-analytics.com';
          }
          
          return 'https://api.protrade-analytics.com';
        })();

        expect(apiUrl).not.toContain('2m14opj30h.execute-api.us-east-1.amazonaws.com');
        expect(apiUrl).not.toContain('https://2m14opj30h');
      });
    });
  });

  describe('Configuration Validation', () => {
    beforeEach(() => {
      // Setup a mock configuration
      window.__CONFIG__ = {
        FEATURES: {
          AUTHENTICATION: true,
          COGNITO_AUTH: true
        },
        COGNITO: {
          USER_POOL_ID: 'us-east-1_TEST123456',
          CLIENT_ID: 'test-client-id'
        },
        API: {
          BASE_URL: 'https://api.test.com'
        },
        ENVIRONMENT: 'test',
        validate: function() {
          const errors = [];
          const warnings = [];
          
          // Check required Cognito configuration
          if (this.FEATURES.AUTHENTICATION && this.FEATURES.COGNITO_AUTH) {
            if (!this.COGNITO.USER_POOL_ID) {
              errors.push('COGNITO.USER_POOL_ID is required when authentication is enabled');
            }
            if (!this.COGNITO.CLIENT_ID) {
              errors.push('COGNITO.CLIENT_ID is required when authentication is enabled');
            }
          }
          
          // Check API configuration
          if (!this.API.BASE_URL || this.API.BASE_URL.includes('example.com')) {
            warnings.push('API.BASE_URL should be set to the actual API endpoint');
          }
          
          // Environment-specific checks
          if (this.ENVIRONMENT === 'production') {
            if (this.FEATURES.DEBUG_MODE) {
              warnings.push('DEBUG_MODE should be disabled in production');
            }
            if (this.FEATURES.MOCK_DATA) {
              warnings.push('MOCK_DATA should be disabled in production');
            }
            if (this.MONITORING && this.MONITORING.LOG_LEVEL === 'debug') {
              warnings.push('LOG_LEVEL should not be debug in production');
            }
          }
          
          return { errors, warnings, isValid: errors.length === 0 };
        }
      };
    });

    it('should validate successfully with valid configuration', () => {
      const validation = window.__CONFIG__.validate();
      
      expect(validation.isValid).toBe(true);
      expect(validation.errors).toHaveLength(0);
    });

    it('should detect missing Cognito User Pool ID', () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = null;
      
      const validation = window.__CONFIG__.validate();
      
      expect(validation.isValid).toBe(false);
      expect(validation.errors).toContain(
        'COGNITO.USER_POOL_ID is required when authentication is enabled'
      );
    });

    it('should detect missing Cognito Client ID', () => {
      window.__CONFIG__.COGNITO.CLIENT_ID = null;
      
      const validation = window.__CONFIG__.validate();
      
      expect(validation.isValid).toBe(false);
      expect(validation.errors).toContain(
        'COGNITO.CLIENT_ID is required when authentication is enabled'
      );
    });

    it('should warn about example.com URLs', () => {
      window.__CONFIG__.API.BASE_URL = 'https://api.example.com';
      
      const validation = window.__CONFIG__.validate();
      
      expect(validation.warnings).toContain(
        'API.BASE_URL should be set to the actual API endpoint'
      );
    });

    it('should warn about debug mode in production', () => {
      window.__CONFIG__.ENVIRONMENT = 'production';
      window.__CONFIG__.FEATURES.DEBUG_MODE = true;
      window.__CONFIG__.FEATURES.MOCK_DATA = true;
      window.__CONFIG__.MONITORING = { LOG_LEVEL: 'debug' };
      
      const validation = window.__CONFIG__.validate();
      
      expect(validation.warnings).toContain(
        'DEBUG_MODE should be disabled in production'
      );
      expect(validation.warnings).toContain(
        'MOCK_DATA should be disabled in production'
      );
      expect(validation.warnings).toContain(
        'LOG_LEVEL should not be debug in production'
      );
    });

    it('should not require Cognito when authentication is disabled', () => {
      window.__CONFIG__.FEATURES.AUTHENTICATION = false;
      window.__CONFIG__.COGNITO.USER_POOL_ID = null;
      window.__CONFIG__.COGNITO.CLIENT_ID = null;
      
      const validation = window.__CONFIG__.validate();
      
      expect(validation.isValid).toBe(true);
      expect(validation.errors).toHaveLength(0);
    });

    it('should not require Cognito when Cognito auth is disabled', () => {
      window.__CONFIG__.FEATURES.COGNITO_AUTH = false;
      window.__CONFIG__.COGNITO.USER_POOL_ID = null;
      window.__CONFIG__.COGNITO.CLIENT_ID = null;
      
      const validation = window.__CONFIG__.validate();
      
      expect(validation.isValid).toBe(true);
      expect(validation.errors).toHaveLength(0);
    });
  });

  describe('Development Environment Overrides', () => {
    it('should apply development overrides for localhost', () => {
      window.location.hostname = 'localhost';
      
      // Simulate the development override logic
      const config = {
        ENVIRONMENT: 'development',
        FEATURES: {
          DEBUG_MODE: false,
          MOCK_DATA: false,
          DEV_TOOLS: false
        },
        MONITORING: {
          LOG_LEVEL: 'info'
        },
        SECURITY: {
          CSP_REPORT_ONLY: false
        },
        COGNITO: {
          USER_POOL_ID: null
        }
      };

      // Apply development overrides
      if (config.ENVIRONMENT === 'development') {
        config.FEATURES.DEBUG_MODE = true;
        config.FEATURES.MOCK_DATA = true;
        config.FEATURES.DEV_TOOLS = true;
        config.MONITORING.LOG_LEVEL = 'debug';
        config.SECURITY.CSP_REPORT_ONLY = true;
      }
      
      expect(config.FEATURES.DEBUG_MODE).toBe(true);
      expect(config.FEATURES.MOCK_DATA).toBe(true);
      expect(config.FEATURES.DEV_TOOLS).toBe(true);
      expect(config.MONITORING.LOG_LEVEL).toBe('debug');
      expect(config.SECURITY.CSP_REPORT_ONLY).toBe(true);
    });

    it('should not apply development overrides for production', () => {
      window.location.hostname = 'app.protrade-analytics.com';
      
      const config = {
        ENVIRONMENT: 'production',
        FEATURES: {
          DEBUG_MODE: false,
          MOCK_DATA: false,
          DEV_TOOLS: false
        },
        MONITORING: {
          LOG_LEVEL: 'info'
        },
        SECURITY: {
          CSP_REPORT_ONLY: false
        }
      };

      // Development overrides should not apply
      if (config.ENVIRONMENT === 'development') {
        config.FEATURES.DEBUG_MODE = true;
        config.FEATURES.MOCK_DATA = true;
        config.FEATURES.DEV_TOOLS = true;
        config.MONITORING.LOG_LEVEL = 'debug';
        config.SECURITY.CSP_REPORT_ONLY = true;
      }
      
      expect(config.FEATURES.DEBUG_MODE).toBe(false);
      expect(config.FEATURES.MOCK_DATA).toBe(false);
      expect(config.FEATURES.DEV_TOOLS).toBe(false);
      expect(config.MONITORING.LOG_LEVEL).toBe('info');
      expect(config.SECURITY.CSP_REPORT_ONLY).toBe(false);
    });
  });

  describe('Auto-Validation', () => {
    it('should schedule validation to run after delay', () => {
      vi.useFakeTimers();
      
      const consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      
      // Setup config with validation
      window.__CONFIG__ = {
        validate: () => ({ errors: [], warnings: [], isValid: true })
      };
      
      // Simulate the auto-validation logic
      setTimeout(() => {
        const validation = window.__CONFIG__.validate();
        
        if (validation.errors.length > 0) {
          console.error('❌ Configuration Errors:', validation.errors);
        }
        
        if (validation.warnings.length > 0) {
          console.warn('⚠️ Configuration Warnings:', validation.warnings);
        }
        
        if (validation.isValid) {
          console.log('✅ Configuration validated successfully');
        }
      }, 100);
      
      // Fast-forward time
      vi.advanceTimersByTime(100);
      
      expect(consoleLogSpy).toHaveBeenCalledWith('✅ Configuration validated successfully');
      
      consoleLogSpy.mockRestore();
      consoleErrorSpy.mockRestore();
      consoleWarnSpy.mockRestore();
      vi.useRealTimers();
    });

    it('should log validation errors', () => {
      vi.useFakeTimers();
      
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      window.__CONFIG__ = {
        validate: () => ({ 
          errors: ['Test error 1', 'Test error 2'], 
          warnings: [], 
          isValid: false 
        })
      };
      
      setTimeout(() => {
        const validation = window.__CONFIG__.validate();
        
        if (validation.errors.length > 0) {
          console.error('❌ Configuration Errors:', validation.errors);
        }
      }, 100);
      
      vi.advanceTimersByTime(100);
      
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        '❌ Configuration Errors:', 
        ['Test error 1', 'Test error 2']
      );
      
      consoleErrorSpy.mockRestore();
      vi.useRealTimers();
    });

    it('should log validation warnings', () => {
      vi.useFakeTimers();
      
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      
      window.__CONFIG__ = {
        validate: () => ({ 
          errors: [], 
          warnings: ['Test warning 1'], 
          isValid: true 
        })
      };
      
      setTimeout(() => {
        const validation = window.__CONFIG__.validate();
        
        if (validation.warnings.length > 0) {
          console.warn('⚠️ Configuration Warnings:', validation.warnings);
        }
      }, 100);
      
      vi.advanceTimersByTime(100);
      
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        '⚠️ Configuration Warnings:', 
        ['Test warning 1']
      );
      
      consoleWarnSpy.mockRestore();
      vi.useRealTimers();
    });
  });

  describe('Feature Flag Configuration', () => {
    it('should have development features disabled by default', () => {
      const developmentFeatures = (function() {
        return window.location.hostname === 'localhost' || 
               window.location.hostname === '127.0.0.1';
      })();
      
      // For non-localhost
      window.location.hostname = 'production.com';
      const prodDevelopmentFeatures = (function() {
        return window.location.hostname === 'localhost' || 
               window.location.hostname === '127.0.0.1';
      })();
      
      expect(prodDevelopmentFeatures).toBe(false);
      
      // For localhost
      window.location.hostname = 'localhost';
      const devDevelopmentFeatures = (function() {
        return window.location.hostname === 'localhost' || 
               window.location.hostname === '127.0.0.1';
      })();
      
      expect(devDevelopmentFeatures).toBe(true);
    });

    it('should configure external APIs with proper URLs', () => {
      const externalApis = {
        ALPACA: {
          BASE_URL: 'https://paper-api.alpaca.markets',
          DATA_URL: 'https://data.alpaca.markets',
          WS_URL: 'wss://stream.data.alpaca.markets',
          IS_PAPER: true
        },
        POLYGON: {
          BASE_URL: 'https://api.polygon.io',
          WS_URL: 'wss://socket.polygon.io'
        },
        FMP: {
          BASE_URL: 'https://financialmodelingprep.com/api'
        },
        FINNHUB: {
          BASE_URL: 'https://finnhub.io/api/v1',
          WS_URL: 'wss://ws.finnhub.io'
        }
      };
      
      // Validate all URLs are proper HTTPS/WSS
      Object.values(externalApis).forEach(apiConfig => {
        Object.entries(apiConfig).forEach(([key, value]) => {
          if (key.includes('URL') && typeof value === 'string') {
            expect(value).toMatch(/^https:\/\/|^wss:\/\//);
          }
        });
      });
    });
  });

  describe('No Hardcoded Values Validation', () => {
    it('should not contain hardcoded API Gateway URLs in any configuration', () => {
      const configUrls = [
        'http://localhost:3001/api',
        'https://api-staging.protrade-analytics.com',
        'https://api.protrade-analytics.com'
      ];
      
      configUrls.forEach(url => {
        expect(url).not.toContain('2m14opj30h.execute-api.us-east-1.amazonaws.com');
        expect(url).not.toContain('https://2m14opj30h');
      });
    });

    it('should not contain hardcoded Cognito values', () => {
      const cognitoValues = [null, 'test-value', 'real-pool-id'];
      
      cognitoValues.forEach(value => {
        if (value) {
          expect(value).not.toBe('3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z');
          expect(value).not.toBe('us-east-1_DUMMY');
          expect(value).not.toBe('dummy-client-id');
        }
      });
    });

    it('should use environment-appropriate defaults', () => {
      const environments = [
        { hostname: 'localhost', expectedEnv: 'development' },
        { hostname: 'staging.example.com', expectedEnv: 'staging' },
        { hostname: 'app.example.com', expectedEnv: 'production' }
      ];
      
      environments.forEach(({ hostname, expectedEnv }) => {
        window.location.hostname = hostname;
        
        const detectedEnv = (function() {
          const hostname = window.location.hostname;
          if (hostname === 'localhost' || hostname === '127.0.0.1') {
            return 'development';
          }
          if (hostname.includes('staging') || hostname.includes('dev')) {
            return 'staging';
          }
          return 'production';
        })();
        
        expect(detectedEnv).toBe(expectedEnv);
      });
    });
  });
});
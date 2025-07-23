/**
 * Configuration Service Unit Tests
 * Comprehensive test coverage for configuration loading and validation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock import.meta.env
vi.mock('import.meta', () => ({
  env: {
    VITE_API_URL: 'https://test-api.example.com/api',
    VITE_COGNITO_USER_POOL_ID: 'us-east-1_TestPool123',
    VITE_COGNITO_CLIENT_ID: 'test-client-id-123',
    VITE_COGNITO_DOMAIN: 'test-domain.auth.us-east-1.amazoncognito.com',
    VITE_AWS_REGION: 'us-east-1'
  }
}));

describe('ConfigurationService', () => {
  let ConfigurationService;
  let configService;

  beforeEach(async () => {
    // Clear any existing window properties
    if (typeof window !== 'undefined') {
      delete window.__CLOUDFORMATION_CONFIG__;
      delete window.__CONFIG__;
    }

    // Create fresh instance for each test
    const module = await import('../../../services/configurationService');
    ConfigurationService = module.default.constructor;
    configService = new ConfigurationService();
  });

  afterEach(() => {
    configService.reset();
    vi.clearAllMocks();
  });

  describe('Initialization', () => {
    it('should initialize with default configuration when no other sources available', async () => {
      const config = await configService.initialize();

      expect(config).toBeDefined();
      expect(config.api.baseUrl).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev');
      expect(config.aws.region).toBe('us-east-1');
      expect(config.source).toBe('environment'); // Environment takes precedence over defaults
    });

    it('should cache configuration after first initialization', async () => {
      const config1 = await configService.initialize();
      const config2 = await configService.initialize();

      expect(config1).toBe(config2); // Same object reference
    });

    it('should handle initialization errors gracefully', async () => {
      // Mock a scenario that would cause an error
      vi.spyOn(configService, 'validateConfiguration').mockImplementation(() => {
        throw new Error('Validation failed');
      });

      const config = await configService.initialize();

      expect(config.source).toBe('safety_fallback');
      expect(config.error).toBe(true);
      expect(config.features.authentication).toBe(false);
    });
  });

  describe('CloudFormation Configuration Loading', () => {
    it('should load CloudFormation configuration when available', () => {
      // Mock window.__CLOUDFORMATION_CONFIG__
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://real-api.execute-api.us-east-1.amazonaws.com/prod',
          UserPoolId: 'us-east-1_RealPoolId',
          UserPoolClientId: 'real-client-id-456',
          UserPoolDomain: 'real-domain.auth.us-east-1.amazoncognito.com'
        }
      };

      const config = configService.loadCloudFormationConfig();

      expect(config.api.baseUrl).toBe('https://real-api.execute-api.us-east-1.amazonaws.com/prod');
      expect(config.cognito.userPoolId).toBe('us-east-1_RealPoolId');
      expect(config.cognito.clientId).toBe('real-client-id-456');
      expect(config.source).toBe('cloudformation');
    });

    it('should return empty object when CloudFormation config is not available', () => {
      global.window = {};
      const config = configService.loadCloudFormationConfig();
      expect(config).toEqual({});
    });

    it('should handle server-side rendering (no window)', () => {
      const originalWindow = global.window;
      delete global.window;

      const config = configService.loadCloudFormationConfig();
      expect(config).toEqual({});

      global.window = originalWindow;
    });
  });

  describe('Window Configuration Loading', () => {
    it('should load window.__CONFIG__ when available', () => {
      global.window = {
        __CONFIG__: {
          API: {
            BASE_URL: 'https://window-api.example.com'
          },
          COGNITO: {
            USER_POOL_ID: 'us-east-1_WindowPool',
            CLIENT_ID: 'window-client-id',
            DOMAIN: 'window-domain.auth.us-east-1.amazoncognito.com'
          },
          AWS: {
            REGION: 'us-west-2'
          },
          ENVIRONMENT: 'production'
        }
      };

      const config = configService.loadWindowConfig();

      expect(config.api.baseUrl).toBe('https://window-api.example.com');
      expect(config.cognito.userPoolId).toBe('us-east-1_WindowPool');
      expect(config.aws.region).toBe('us-west-2');
      expect(config.environment).toBe('production');
      expect(config.source).toBe('window_config');
    });

    it('should handle alternative API_URL format in window config', () => {
      global.window = {
        __CONFIG__: {
          API_URL: 'https://alt-api.example.com'
        }
      };

      const config = configService.loadWindowConfig();
      expect(config.api.baseUrl).toBe('https://alt-api.example.com');
    });
  });

  describe('Environment Configuration Loading', () => {
    it('should load environment variables correctly', () => {
      const config = configService.loadEnvironmentConfig();

      expect(config.api.baseUrl).toBe('https://test-api.example.com/api');
      expect(config.cognito.userPoolId).toBe('us-east-1_TestPool123');
      expect(config.cognito.clientId).toBe('test-client-id-123');
      expect(config.cognito.domain).toBe('test-domain.auth.us-east-1.amazoncognito.com');
      expect(config.aws.region).toBe('us-east-1');
      expect(config.source).toBe('environment');
    });
  });

  describe('Configuration Merging', () => {
    it('should merge configurations with correct priority', async () => {
      // Set up multiple configuration sources
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://cf-api.example.com',
          UserPoolId: 'us-east-1_CFPool'
        },
        __CONFIG__: {
          API: {
            BASE_URL: 'https://window-api.example.com'
          },
          COGNITO: {
            CLIENT_ID: 'window-client-id'
          }
        }
      };

      const config = await configService.initialize();

      // CloudFormation should take precedence for API URL
      expect(config.api.baseUrl).toBe('https://cf-api.example.com');
      // CloudFormation should take precedence for User Pool ID
      expect(config.cognito.userPoolId).toBe('us-east-1_CFPool');
      // Environment should provide Client ID if not in higher priority sources
      expect(config.cognito.clientId).toBe('test-client-id-123');
    });

    it('should handle partial configurations correctly', async () => {
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://partial-cf.example.com'
          // Missing cognito config
        }
      };

      const config = await configService.initialize();

      expect(config.api.baseUrl).toBe('https://partial-cf.example.com');
      expect(config.cognito.userPoolId).toBe('us-east-1_TestPool123'); // From environment
      expect(config.cognito.clientId).toBe('test-client-id-123'); // From environment
    });
  });

  describe('Configuration Validation', () => {
    it('should pass validation for valid configuration', () => {
      const validConfig = {
        api: {
          baseUrl: 'https://valid-api.example.com'
        },
        cognito: {
          userPoolId: 'us-east-1_ValidPool123',
          clientId: 'valid-client-id-456'
        },
        features: {
          authentication: true,
          cognito: true
        }
      };

      expect(() => configService.validateConfiguration(validConfig)).not.toThrow();
    });

    it('should throw error for missing API base URL', () => {
      const invalidConfig = {
        api: {},
        features: { authentication: false }
      };

      expect(() => configService.validateConfiguration(invalidConfig)).toThrow('API base URL is required');
    });

    it('should warn about placeholder values', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      
      const configWithPlaceholders = {
        api: {
          baseUrl: 'https://api-gateway-placeholder.example.com'
        },
        cognito: {
          userPoolId: '3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z',
          clientId: 'dummy-client-id'
        },
        features: {
          authentication: true,
          cognito: true
        }
      };

      configService.validateConfiguration(configWithPlaceholders);

      expect(consoleSpy).toHaveBeenCalledWith(
        '⚠️ Configuration validation warnings:',
        expect.arrayContaining([
          expect.stringContaining('placeholder value')
        ])
      );

      consoleSpy.mockRestore();
    });
  });

  describe('Placeholder Value Detection', () => {
    it('should detect various placeholder patterns', () => {
      const placeholders = [
        '3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z', // 32-char hex
        'dummy-value',
        'placeholder-text',
        'example.com',
        'test-value',
        'mock-data',
        'us-east-1_DUMMY',
        'undefined',
        'null'
      ];

      placeholders.forEach(placeholder => {
        expect(configService.isPlaceholderValue(placeholder)).toBe(true);
      });
    });

    it('should not detect valid values as placeholders', () => {
      const validValues = [
        'us-east-1_RealPoolId123',
        'real-client-id-456',
        'https://real-api.execute-api.us-east-1.amazonaws.com/prod',
        'production-domain.auth.us-east-1.amazoncognito.com'
      ];

      validValues.forEach(value => {
        expect(configService.isPlaceholderValue(value)).toBe(false);
      });
    });

    it('should handle null and undefined values', () => {
      expect(configService.isPlaceholderValue(null)).toBe(true);
      expect(configService.isPlaceholderValue(undefined)).toBe(true);
      expect(configService.isPlaceholderValue('')).toBe(true);
    });
  });

  describe('Configuration Access Methods', () => {
    beforeEach(async () => {
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://access-test.example.com',
          UserPoolId: 'us-east-1_AccessTest',
          UserPoolClientId: 'access-test-client'
        }
      };
      await configService.initialize();
    });

    it('should return API configuration', async () => {
      const apiConfig = await configService.getApiConfig();

      expect(apiConfig).toEqual({
        baseUrl: 'https://access-test.example.com',
        timeout: 30000,
        retryAttempts: 3
      });
    });

    it('should return Cognito configuration', async () => {
      const cognitoConfig = await configService.getCognitoConfig();

      expect(cognitoConfig.userPoolId).toBe('us-east-1_AccessTest');
      expect(cognitoConfig.clientId).toBe('access-test-client');
      expect(cognitoConfig.region).toBe('us-east-1');
      expect(cognitoConfig.redirectSignIn).toBe('');
      expect(cognitoConfig.redirectSignOut).toBe('');
    });

    it('should check authentication configuration status', async () => {
      const isConfigured = await configService.isAuthenticationConfigured();
      expect(isConfigured).toBe(true);
    });

    it('should detect misconfigured authentication', async () => {
      // Reset and initialize with placeholder values
      configService.reset();
      global.window = {
        __CONFIG__: {
          COGNITO: {
            USER_POOL_ID: '3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z', // placeholder
            CLIENT_ID: 'dummy-client-id' // placeholder
          }
        }
      };
      await configService.initialize();

      const isConfigured = await configService.isAuthenticationConfigured();
      expect(isConfigured).toBe(false);
    });
  });

  describe('Deep Merge Utility', () => {
    it('should merge nested objects correctly', () => {
      const target = {
        api: { baseUrl: 'old-url' },
        features: { auth: false }
      };
      const source = {
        api: { timeout: 5000 },
        features: { auth: true, debug: true }
      };

      configService.deepMerge(target, source);

      expect(target).toEqual({
        api: { baseUrl: 'old-url', timeout: 5000 },
        features: { auth: true, debug: true }
      });
    });

    it('should not overwrite with null or undefined values', () => {
      const target = { api: { baseUrl: 'existing-url' } };
      const source = { api: { baseUrl: null, timeout: undefined } };

      configService.deepMerge(target, source);

      expect(target.api.baseUrl).toBe('existing-url'); // Should not be overwritten
      expect(target.api.timeout).toBeUndefined(); // Should not be set
    });
  });

  describe('Reset Functionality', () => {
    it('should reset configuration cache', async () => {
      await configService.initialize();
      expect(configService.initialized).toBe(true);

      configService.reset();
      expect(configService.initialized).toBe(false);
      expect(configService.configCache).toBe(null);
    });
  });

  describe('Safety Fallback Configuration', () => {
    it('should provide safe fallback when everything fails', () => {
      const fallback = configService.getSafetyFallbackConfig();

      expect(fallback.api.baseUrl).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev');
      expect(fallback.features.authentication).toBe(false);
      expect(fallback.features.cognito).toBe(false);
      expect(fallback.source).toBe('safety_fallback');
      expect(fallback.error).toBe(true);
    });
  });
});
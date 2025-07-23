/**
 * Environment Configuration Tests
 * Tests the centralized configuration system and validates no hardcoded values remain
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock window.__CONFIG__ for testing
const mockConfig = {
  API: {
    BASE_URL: 'https://api-test.example.com',
    VERSION: 'v1',
    TIMEOUT: 30000
  },
  COGNITO: {
    USER_POOL_ID: 'us-east-1_TEST123456',
    CLIENT_ID: 'test-client-id-123',
    REGION: 'us-east-1'
  },
  FEATURES: {
    AUTHENTICATION: true,
    COGNITO_AUTH: true,
    TRADING: true,
    PAPER_TRADING: true,
    REAL_TRADING: false,
    DEBUG_MODE: true
  },
  EXTERNAL_APIS: {
    ALPACA: {
      BASE_URL: 'https://paper-api.alpaca.markets',
      API_KEY: null
    },
    POLYGON: {
      BASE_URL: 'https://api.polygon.io',
      API_KEY: null
    }
  }
};

describe('Environment Configuration System', () => {
  beforeEach(() => {
    // Mock window.__CONFIG__
    global.window = global.window || {};
    window.__CONFIG__ = { ...mockConfig };
    
    // Mock environment variables
    vi.stubEnv('VITE_COGNITO_USER_POOL_ID', 'us-east-1_ENV123456');
    vi.stubEnv('VITE_COGNITO_CLIENT_ID', 'env-client-id-123');
    vi.stubEnv('VITE_API_BASE_URL', 'https://api-env.example.com');
    vi.stubEnv('NODE_ENV', 'test');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  describe('Environment Detection', () => {
    it('should correctly detect development environment', async () => {
      vi.stubEnv('NODE_ENV', 'development');
      
      const { NODE_ENV, IS_DEVELOPMENT, IS_PRODUCTION } = await import('../../../config/environment');
      
      expect(NODE_ENV).toBe('development');
      expect(IS_DEVELOPMENT).toBe(true);
      expect(IS_PRODUCTION).toBe(false);
    });

    it('should correctly detect production environment', async () => {
      vi.stubEnv('NODE_ENV', 'production');
      
      // Re-import to get fresh values
      vi.resetModules();
      const { NODE_ENV, IS_DEVELOPMENT, IS_PRODUCTION } = await import('../../../config/environment');
      
      expect(NODE_ENV).toBe('production');
      expect(IS_DEVELOPMENT).toBe(false);
      expect(IS_PRODUCTION).toBe(true);
    });

    it('should default to development when NODE_ENV is not set', async () => {
      vi.stubEnv('NODE_ENV', undefined);
      
      vi.resetModules();
      const { NODE_ENV, IS_DEVELOPMENT } = await import('../../../config/environment');
      
      expect(NODE_ENV).toBe('development');
      expect(IS_DEVELOPMENT).toBe(true);
    });
  });

  describe('AWS Configuration', () => {
    it('should prioritize runtime config over environment variables', async () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = 'us-east-1_RUNTIME123';
      
      const { AWS_CONFIG } = await import('../../../config/environment');
      
      expect(AWS_CONFIG.cognito.userPoolId).toBe('us-east-1_RUNTIME123');
    });

    it('should fall back to environment variables when runtime config is missing', async () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = null;
      
      vi.resetModules();
      const { AWS_CONFIG } = await import('../../../config/environment');
      
      expect(AWS_CONFIG.cognito.userPoolId).toBe('us-east-1_ENV123456');
    });

    it('should handle missing configuration gracefully', async () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = null;
      vi.stubEnv('VITE_COGNITO_USER_POOL_ID', undefined);
      
      vi.resetModules();
      const { AWS_CONFIG } = await import('../../../config/environment');
      
      expect(AWS_CONFIG.cognito.userPoolId).toBeNull();
    });

    it('should configure API settings correctly', async () => {
      const { AWS_CONFIG } = await import('../../../config/environment');
      
      expect(AWS_CONFIG.api).toMatchObject({
        baseUrl: expect.any(String),
        version: expect.any(String),
        timeout: expect.any(Number),
        retryAttempts: expect.any(Number),
        retryDelay: expect.any(Number)
      });
      
      expect(AWS_CONFIG.api.timeout).toBeGreaterThan(0);
      expect(AWS_CONFIG.api.retryAttempts).toBeGreaterThan(0);
    });
  });

  describe('External API Configuration', () => {
    it('should configure Alpaca API settings', async () => {
      const { EXTERNAL_APIS } = await import('../../../config/environment');
      
      expect(EXTERNAL_APIS.alpaca).toMatchObject({
        baseUrl: expect.stringMatching(/^https:\/\//),
        dataUrl: expect.stringMatching(/^https:\/\//),
        websocketUrl: expect.stringMatching(/^wss:\/\//),
        isPaper: expect.any(Boolean)
      });
    });

    it('should configure Polygon API settings', async () => {
      const { EXTERNAL_APIS } = await import('../../../config/environment');
      
      expect(EXTERNAL_APIS.polygon).toMatchObject({
        baseUrl: expect.stringMatching(/^https:\/\//),
        websocketUrl: expect.stringMatching(/^wss:\/\//)
      });
    });

    it('should not expose API keys in configuration', async () => {
      const { EXTERNAL_APIS } = await import('../../../config/environment');
      
      // API keys should be null or undefined, not hardcoded
      Object.values(EXTERNAL_APIS).forEach(apiConfig => {
        if (apiConfig.apiKey !== undefined) {
          expect(apiConfig.apiKey).toBeNull();
        }
        if (apiConfig.apiKeyId !== undefined) {
          expect(apiConfig.apiKeyId).toBeNull();
        }
        if (apiConfig.secretKey !== undefined) {
          expect(apiConfig.secretKey).toBeNull();
        }
      });
    });
  });

  describe('Feature Flags', () => {
    it('should enable authentication by default', async () => {
      const { FEATURES } = await import('../../../config/environment');
      
      expect(FEATURES.authentication.enabled).toBe(true);
      expect(FEATURES.authentication.methods.cognito).toBe(true);
    });

    it('should configure trading features appropriately', async () => {
      const { FEATURES } = await import('../../../config/environment');
      
      expect(FEATURES.trading.enabled).toBe(true);
      expect(FEATURES.trading.paperTrading).toBe(true);
      // Real trading should be disabled by default for safety
      expect(FEATURES.trading.realTrading).toBe(false);
    });

    it('should configure AI features', async () => {
      const { FEATURES } = await import('../../../config/environment');
      
      expect(FEATURES.ai.enabled).toBe(true);
      expect(FEATURES.ai.tradingSignals).toBe(true);
    });

    it('should set appropriate development features', async () => {
      vi.stubEnv('NODE_ENV', 'development');
      
      vi.resetModules();
      const { FEATURES } = await import('../../../config/environment');
      
      expect(FEATURES.development.debugMode).toBe(true);
      expect(FEATURES.development.mockData).toBe(true);
    });

    it('should disable development features in production', async () => {
      vi.stubEnv('NODE_ENV', 'production');
      
      vi.resetModules();
      const { FEATURES } = await import('../../../config/environment');
      
      expect(FEATURES.development.debugMode).toBe(false);
      expect(FEATURES.development.mockData).toBe(false);
    });
  });

  describe('Helper Functions', () => {
    it('should construct API URLs correctly', async () => {
      const { getApiUrl } = await import('../../../config/environment');
      
      const url = getApiUrl('portfolio');
      expect(url).toMatch(/^https:\/\/.+\/v1\/portfolio$/);
    });

    it('should handle API URLs with leading slashes', async () => {
      const { getApiUrl } = await import('../../../config/environment');
      
      const url = getApiUrl('/portfolio');
      expect(url).toMatch(/^https:\/\/.+\/v1\/portfolio$/);
      expect(url).not.toContain('//portfolio');
    });

    it('should construct external API URLs correctly', async () => {
      const { getExternalApiUrl } = await import('../../../config/environment');
      
      const url = getExternalApiUrl('alpaca', 'account');
      expect(url).toMatch(/^https:\/\/.+\/account$/);
    });

    it('should throw error for unknown API providers', async () => {
      const { getExternalApiUrl } = await import('../../../config/environment');
      
      expect(() => {
        getExternalApiUrl('unknown-provider', 'endpoint');
      }).toThrow('Unknown API provider: unknown-provider');
    });

    it('should check feature flags correctly', async () => {
      const { isFeatureEnabled } = await import('../../../config/environment');
      
      expect(isFeatureEnabled('authentication.enabled')).toBe(true);
      expect(isFeatureEnabled('trading.realTrading')).toBe(false);
      expect(isFeatureEnabled('nonexistent.feature')).toBe(false);
    });
  });

  describe('Configuration Validation', () => {
    it('should validate required AWS configuration', async () => {
      const { validateConfig } = await import('../../../config/environment');
      
      const { errors, warnings } = validateConfig();
      
      expect(errors).toBeInstanceOf(Array);
      expect(warnings).toBeInstanceOf(Array);
    });

    it('should detect missing Cognito configuration', async () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = null;
      vi.stubEnv('VITE_COGNITO_USER_POOL_ID', undefined);
      
      vi.resetModules();
      const { validateConfig } = await import('../../../config/environment');
      
      const { errors } = validateConfig();
      
      expect(errors.some(error => 
        error.includes('Cognito User Pool ID')
      )).toBe(true);
    });

    it('should warn about default API URLs', async () => {
      window.__CONFIG__.API.BASE_URL = 'https://api.protrade.com';
      
      vi.resetModules();
      const { validateConfig } = await import('../../../config/environment');
      
      const { warnings } = validateConfig();
      
      expect(warnings.some(warning => 
        warning.includes('default API base URL')
      )).toBe(true);
    });
  });

  describe('No Hardcoded Values', () => {
    it('should not contain hardcoded API Gateway URLs', async () => {
      const config = await import('../../../config/environment');
      
      // Check that no configuration contains the hardcoded API Gateway URL
      const configString = JSON.stringify(config);
      expect(configString).not.toContain('2m14opj30h.execute-api.us-east-1.amazonaws.com');
      expect(configString).not.toContain('https://2m14opj30h');
    });

    it('should not contain hardcoded Cognito pool IDs', async () => {
      const config = await import('../../../config/environment');
      
      const configString = JSON.stringify(config);
      expect(configString).not.toContain('3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z');
      expect(configString).not.toContain('us-east-1_DUMMY');
    });

    it('should not contain example.com URLs', async () => {
      const config = await import('../../../config/environment');
      
      const configString = JSON.stringify(config);
      expect(configString).not.toContain('example.com');
    });

    it('should use environment variables or runtime config', async () => {
      const { AWS_CONFIG, EXTERNAL_APIS } = await import('../../../config/environment');
      
      // Verify that configuration comes from environment or runtime
      if (AWS_CONFIG.cognito.userPoolId) {
        expect(AWS_CONFIG.cognito.userPoolId).toMatch(/^(us-east-1_|us-west-2_)/);
      }
      
      // External API URLs should be legitimate service URLs
      expect(EXTERNAL_APIS.alpaca.baseUrl).toMatch(/^https:\/\/.*alpaca\.markets/);
      expect(EXTERNAL_APIS.polygon.baseUrl).toMatch(/^https:\/\/.*polygon\.io/);
    });
  });

  describe('Performance Configuration', () => {
    it('should set reasonable cache TTL values', async () => {
      const { PERFORMANCE_CONFIG } = await import('../../../config/environment');
      
      expect(PERFORMANCE_CONFIG.cache.ttl.marketData).toBeGreaterThan(30000); // At least 30 seconds
      expect(PERFORMANCE_CONFIG.cache.ttl.marketData).toBeLessThan(600000); // At most 10 minutes
      
      expect(PERFORMANCE_CONFIG.cache.ttl.portfolio).toBeGreaterThan(60000); // At least 1 minute
      expect(PERFORMANCE_CONFIG.cache.ttl.static).toBeGreaterThan(1800000); // At least 30 minutes
    });

    it('should configure rate limiting appropriately', async () => {
      const { PERFORMANCE_CONFIG } = await import('../../../config/environment');
      
      expect(PERFORMANCE_CONFIG.rateLimit.requests.perMinute).toBeGreaterThan(10);
      expect(PERFORMANCE_CONFIG.rateLimit.requests.perMinute).toBeLessThan(1000);
      
      expect(PERFORMANCE_CONFIG.rateLimit.requests.perHour).toBeGreaterThan(100);
      expect(PERFORMANCE_CONFIG.rateLimit.requests.perDay).toBeGreaterThan(1000);
    });

    it('should configure WebSocket settings', async () => {
      const { PERFORMANCE_CONFIG } = await import('../../../config/environment');
      
      expect(PERFORMANCE_CONFIG.websocket.reconnectInterval).toBeGreaterThan(1000);
      expect(PERFORMANCE_CONFIG.websocket.maxReconnectAttempts).toBeGreaterThan(3);
      expect(PERFORMANCE_CONFIG.websocket.heartbeatInterval).toBeGreaterThan(10000);
    });
  });

  describe('Security Configuration', () => {
    it('should enable encryption by default', async () => {
      const { SECURITY_CONFIG } = await import('../../../config/environment');
      
      expect(SECURITY_CONFIG.encryption.enabled).toBe(true);
      expect(SECURITY_CONFIG.encryption.algorithm).toBe('AES-256-GCM');
    });

    it('should set appropriate session timeouts', async () => {
      const { SECURITY_CONFIG } = await import('../../../config/environment');
      
      expect(SECURITY_CONFIG.session.timeout).toBeGreaterThan(900000); // At least 15 minutes
      expect(SECURITY_CONFIG.session.timeout).toBeLessThan(14400000); // At most 4 hours
      
      expect(SECURITY_CONFIG.session.renewBeforeExpiry).toBeLessThan(SECURITY_CONFIG.session.timeout);
    });

    it('should limit concurrent sessions reasonably', async () => {
      const { SECURITY_CONFIG } = await import('../../../config/environment');
      
      expect(SECURITY_CONFIG.session.maxConcurrentSessions).toBeGreaterThan(0);
      expect(SECURITY_CONFIG.session.maxConcurrentSessions).toBeLessThan(10);
    });
  });

  describe('Runtime Configuration Loading', () => {
    it('should load configuration from window.__CONFIG__', () => {
      expect(window.__CONFIG__).toBeDefined();
      expect(window.__CONFIG__.API).toBeDefined();
      expect(window.__CONFIG__.COGNITO).toBeDefined();
    });

    it('should handle missing window.__CONFIG__ gracefully', async () => {
      const originalConfig = window.__CONFIG__;
      delete window.__CONFIG__;
      
      vi.resetModules();
      
      expect(async () => {
        await import('../../../config/environment');
      }).not.toThrow();
      
      // Restore config
      window.__CONFIG__ = originalConfig;
    });

    it('should validate runtime configuration structure', () => {
      const requiredKeys = ['API', 'COGNITO', 'FEATURES'];
      
      requiredKeys.forEach(key => {
        expect(window.__CONFIG__).toHaveProperty(key);
      });
    });
  });
});
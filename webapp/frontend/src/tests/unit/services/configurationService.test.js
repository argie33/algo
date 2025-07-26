/**
 * Configuration Service Unit Tests
 * Tests the URL construction fixes and core functionality
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import configurationService from '../../../services/configurationService';

describe('ConfigurationService', () => {
  let mockFetch;
  let originalWindow;

  beforeEach(() => {
    // Reset the service state
    configurationService.reset();
    
    // Store original window
    originalWindow = global.window;
    
    // Setup mock fetch
    mockFetch = vi.fn();
    global.fetch = mockFetch;
    
    // Setup clean window environment
    global.window = {
      location: { origin: 'http://localhost:3000' },
    };
  });

  afterEach(() => {
    global.window = originalWindow;
    vi.restoreAllMocks();
  });

  describe('🔧 Critical Bug Fix: URL Construction', () => {
    it('should NOT construct [object Promise]/api/config URLs', async () => {
      // Mock successful JSON response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (header) => header === 'content-type' ? 'application/json' : null
        },
        text: () => Promise.resolve(JSON.stringify({
          api: { gatewayUrl: 'https://api-response.amazonaws.com' },
          cognito: { userPoolId: 'pool123', clientId: 'client123' }
        }))
      });

      await configurationService.initialize();

      // Verify fetch was called with proper URL (not [object Promise])
      const fetchUrl = mockFetch.mock.calls[0][0];
      expect(fetchUrl).toMatch(/^https:\/\/.+\.execute-api\..+\/dev\/api\/config$/);
      expect(fetchUrl).not.toContain('[object Promise]');
      expect(fetchUrl).not.toContain('undefined');
    });

    it('should handle API response correctly without HTML errors', async () => {
      // Mock successful API response with proper JSON
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (header) => header === 'content-type' ? 'application/json' : null
        },
        text: () => Promise.resolve(JSON.stringify({
          api: { gatewayUrl: 'https://working-api.com' },
          cognito: { userPoolId: 'test-pool' },
          source: 'cloudformation'
        }))
      });

      const config = await configurationService.initialize();
      
      // Should successfully initialize without emergency mode
      expect(config.source).not.toBe('emergency_fallback');
      expect(config.api.baseUrl).toBeDefined();
    });
  });

  describe('Error Handling and Fallbacks', () => {
    it('should handle HTML response instead of JSON', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (header) => header === 'content-type' ? 'text/html' : null
        },
        text: () => Promise.resolve('<!DOCTYPE html><html>Error page</html>')
      });

      const config = await configurationService.initialize();

      // Should use emergency fallback
      expect(config.emergency).toBe(true);
      expect(config.features.authentication).toBe(false);
      expect(config.message).toContain('emergency mode');
    });

    it('should handle fetch network errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      const config = await configurationService.initialize();

      // Should use emergency fallback
      expect(config.emergency).toBe(true);
      expect(config.api.baseUrl).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev');
    });

    it('should handle malformed JSON response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (header) => header === 'content-type' ? 'application/json' : null
        },
        text: () => Promise.resolve('{ invalid json }')
      });

      const config = await configurationService.initialize();

      // Should use emergency fallback
      expect(config.emergency).toBe(true);
    });
  });

  describe('Emergency Mode', () => {
    it('should create proper emergency fallback configuration', () => {
      const emergencyConfig = configurationService.getEmergencyFallbackConfig();

      expect(emergencyConfig.emergency).toBe(true);
      expect(emergencyConfig.features.authentication).toBe(false);
      expect(emergencyConfig.features.cognito).toBe(false);
      expect(emergencyConfig.cognito.userPoolId).toBe('us-east-1_EMERGENCY');
      expect(emergencyConfig.source).toBe('emergency_fallback');
      expect(emergencyConfig.message).toContain('emergency mode');
    });

    it('should detect emergency mode correctly', async () => {
      // Force emergency mode by making API fail
      mockFetch.mockRejectedValueOnce(new Error('API failure'));

      const config = await configurationService.initialize();
      const isEmergency = await configurationService.isEmergencyMode();

      expect(isEmergency).toBe(true);
    });

    it('should disable authentication in emergency mode', async () => {
      // Force emergency mode
      mockFetch.mockRejectedValueOnce(new Error('API failure'));

      await configurationService.initialize();
      const isAuthConfigured = await configurationService.isAuthenticationConfigured();

      expect(isAuthConfigured).toBe(false);
    });
  });

  describe('Configuration Merging', () => {
    it('should properly merge CloudFormation, window, and environment configs', async () => {
      // Setup window config
      global.window.__CONFIG__ = {
        API: { BASE_URL: 'https://window-api.com' },
        COGNITO: { USER_POOL_ID: 'window-pool' }
      };

      // Setup CloudFormation config
      global.window.__CLOUDFORMATION_CONFIG__ = {
        ApiGatewayUrl: 'https://cf-api.com',
        UserPoolId: 'cf-pool-id'
      };

      // Mock successful API response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (header) => header === 'content-type' ? 'application/json' : null
        },
        text: () => Promise.resolve(JSON.stringify({
          api: { gatewayUrl: 'https://api-response.com' },
          cognito: { userPoolId: 'api-pool' }
        }))
      });

      const config = await configurationService.initialize();

      // CloudFormation should have highest priority for API URL
      expect(config.api.baseUrl).toBe('https://api-response.com');
    });

    it('should fallback through configuration sources properly', async () => {
      // No CloudFormation or window config
      // Mock API failure
      mockFetch.mockRejectedValueOnce(new Error('API failure'));

      const config = await configurationService.initialize();

      // Should use emergency fallback
      expect(config.source).toBe('emergency_fallback');
      expect(config.api.baseUrl).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev');
    });
  });

  describe('Content Type Validation', () => {
    it('should reject non-JSON content types', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (header) => header === 'content-type' ? 'text/plain' : null
        },
        text: () => Promise.resolve('plain text response')
      });

      const config = await configurationService.initialize();

      expect(config.emergency).toBe(true);
    });

    it('should accept valid JSON content type', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (header) => header === 'content-type' ? 'application/json; charset=utf-8' : null
        },
        text: () => Promise.resolve(JSON.stringify({
          api: { gatewayUrl: 'https://valid-api.com' },
          cognito: { userPoolId: 'valid-pool' }
        }))
      });

      const config = await configurationService.initialize();

      expect(config.emergency).toBeUndefined();
      expect(config.api.baseUrl).toBe('https://valid-api.com');
    });
  });

  describe('Configuration Validation', () => {
    it('should validate required API configuration', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (header) => header === 'content-type' ? 'application/json' : null
        },
        text: () => Promise.resolve(JSON.stringify({
          // Missing api.gatewayUrl
          cognito: { userPoolId: 'test-pool' }
        }))
      });

      const config = await configurationService.initialize();

      // Should use emergency fallback due to validation failure
      expect(config.emergency).toBe(true);
    });

    it('should detect placeholder values', () => {
      const isPlaceholder1 = configurationService.isPlaceholderValue('us-east-1_DUMMY');
      const isPlaceholder2 = configurationService.isPlaceholderValue('placeholder-value');
      const isPlaceholder3 = configurationService.isPlaceholderValue('real-pool-id-12345');

      expect(isPlaceholder1).toBe(true);
      expect(isPlaceholder2).toBe(true);
      expect(isPlaceholder3).toBe(false);
    });
  });

  describe('API Configuration Methods', () => {
    beforeEach(async () => {
      // Setup successful response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (header) => header === 'content-type' ? 'application/json' : null
        },
        text: () => Promise.resolve(JSON.stringify({
          api: { gatewayUrl: 'https://test-api.com' },
          cognito: { 
            userPoolId: 'us-east-1_TestPool',
            clientId: 'test-client-id',
            domain: 'test-domain'
          },
          region: 'us-east-1'
        }))
      });

      await configurationService.initialize();
    });

    it('should return proper API configuration', async () => {
      const apiConfig = await configurationService.getApiConfig();

      expect(apiConfig.baseUrl).toBe('https://test-api.com');
      expect(apiConfig.timeout).toBe(30000);
      expect(apiConfig.retryAttempts).toBe(3);
    });

    it('should return proper Cognito configuration', async () => {
      const cognitoConfig = await configurationService.getCognitoConfig();

      expect(cognitoConfig.userPoolId).toBe('us-east-1_TestPool');
      expect(cognitoConfig.clientId).toBe('test-client-id');
      expect(cognitoConfig.domain).toBe('test-domain');
      expect(cognitoConfig.region).toBe('us-east-1');
      expect(cognitoConfig.redirectSignIn).toBe(global.window.location.origin);
    });
  });
});
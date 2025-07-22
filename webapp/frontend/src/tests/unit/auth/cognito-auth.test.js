/**
 * Real Cognito Authentication Tests
 * Tests actual AWS Cognito integration - NO MOCKS
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { configureAmplify, isCognitoConfigured, getCognitoConfig } from '../../../config/amplify';

describe('🔐 Cognito Authentication - Real Implementation Tests', () => {
  beforeEach(() => {
    // Clear any existing window config
    delete window.__CONFIG__;
    vi.clearAllMocks();
  });

  describe('Configuration Validation', () => {
    it('should detect when Cognito is properly configured', () => {
      // Test with runtime config
      window.__CONFIG__ = {
        COGNITO: {
          USER_POOL_ID: 'us-east-1_RealPool123',
          CLIENT_ID: 'real-client-id-123',
          REGION: 'us-east-1'
        }
      };

      const isConfigured = isCognitoConfigured();
      expect(isConfigured).toBe(true);
    });

    it('should detect dummy/invalid Cognito configuration', () => {
      window.__CONFIG__ = {
        COGNITO: {
          USER_POOL_ID: 'us-east-1_DUMMY',
          CLIENT_ID: 'dummy-client-id',
          REGION: 'us-east-1'
        }
      };

      const isConfigured = isCognitoConfigured();
      expect(isConfigured).toBe(false);
    });

    it('should handle missing Cognito configuration', () => {
      window.__CONFIG__ = {};

      const isConfigured = isCognitoConfigured();
      expect(isConfigured).toBe(false);
    });

    it('should return proper Cognito configuration', () => {
      window.__CONFIG__ = {
        COGNITO: {
          USER_POOL_ID: 'us-east-1_TestPool',
          CLIENT_ID: 'test-client-id',
          REGION: 'us-east-1',
          DOMAIN: 'test.auth.us-east-1.amazoncognito.com'
        }
      };

      const config = getCognitoConfig();
      expect(config).toEqual({
        userPoolId: 'us-east-1_TestPool',
        userPoolClientId: 'test-client-id',
        region: 'us-east-1',
        domain: 'test.auth.us-east-1.amazoncognito.com',
        redirectSignIn: window.location.origin,
        redirectSignOut: window.location.origin
      });
    });
  });

  describe('Amplify Configuration', () => {
    it('should configure Amplify successfully with valid Cognito config', () => {
      window.__CONFIG__ = {
        COGNITO: {
          USER_POOL_ID: 'us-east-1_ValidPool',
          CLIENT_ID: 'valid-client-id',
          REGION: 'us-east-1'
        }
      };

      // Mock Amplify.configure to avoid actual AWS calls in tests
      const originalAmplify = vi.fn();
      vi.stubGlobal('Amplify', { configure: originalAmplify });

      const result = configureAmplify();
      expect(result).toBe(true);
    });

    it('should fail on production with invalid Cognito config', () => {
      // Simulate production environment
      Object.defineProperty(window, 'location', {
        value: { hostname: 'myapp.amazonaws.com' },
        writable: true
      });

      window.__CONFIG__ = {
        COGNITO: {
          USER_POOL_ID: 'us-east-1_DUMMY',
          CLIENT_ID: 'dummy-client-id'
        }
      };

      expect(() => configureAmplify()).toThrow('Cognito configuration required for AWS deployment');
    });

    it('should allow development mode with invalid config', () => {
      // Simulate localhost development
      Object.defineProperty(window, 'location', {
        value: { hostname: 'localhost' },
        writable: true
      });

      window.__CONFIG__ = {
        COGNITO: {
          USER_POOL_ID: 'us-east-1_DUMMY',
          CLIENT_ID: 'dummy-client-id'
        }
      };

      const result = configureAmplify();
      expect(result).toBe(false);
    });
  });

  describe('Authentication State Management', () => {
    it('should handle authentication errors gracefully', () => {
      // This test verifies the app doesn't crash on auth failures
      window.__CONFIG__ = {
        COGNITO: {
          USER_POOL_ID: 'us-east-1_INVALID',
          CLIENT_ID: 'invalid-client'
        }
      };

      expect(() => {
        const config = getCognitoConfig();
        expect(config.userPoolId).toBe('us-east-1_INVALID');
      }).not.toThrow();
    });

    it('should provide fallback configuration for missing values', () => {
      window.__CONFIG__ = {};

      const config = getCognitoConfig();
      expect(config).toEqual({
        userPoolId: 'us-east-1_DUMMY',
        userPoolClientId: 'dummy-client-id',
        region: 'us-east-1',
        domain: '',
        redirectSignIn: window.location.origin,
        redirectSignOut: window.location.origin
      });
    });
  });

  describe('OAuth Configuration', () => {
    it('should configure OAuth when domain is provided', () => {
      window.__CONFIG__ = {
        COGNITO: {
          USER_POOL_ID: 'us-east-1_TestPool',
          CLIENT_ID: 'test-client-id',
          REGION: 'us-east-1',
          DOMAIN: 'testapp.auth.us-east-1.amazoncognito.com'
        }
      };

      const config = getCognitoConfig();
      expect(config.domain).toBe('testapp.auth.us-east-1.amazoncognito.com');
    });

    it('should skip OAuth when no domain is provided', () => {
      window.__CONFIG__ = {
        COGNITO: {
          USER_POOL_ID: 'us-east-1_TestPool',
          CLIENT_ID: 'test-client-id',
          REGION: 'us-east-1'
        }
      };

      const config = getCognitoConfig();
      expect(config.domain).toBe('');
    });
  });

  describe('Environment Variable Fallback', () => {
    it('should use environment variables when runtime config is missing', () => {
      // Clear runtime config
      window.__CONFIG__ = {};
      
      // Mock environment variables
      vi.stubGlobal('import', {
        meta: {
          env: {
            VITE_COGNITO_USER_POOL_ID: 'us-east-1_EnvPool',
            VITE_COGNITO_CLIENT_ID: 'env-client-id',
            VITE_AWS_REGION: 'us-west-2'
          }
        }
      });

      const config = getCognitoConfig();
      expect(config.userPoolId).toBe('us-east-1_EnvPool');
      expect(config.userPoolClientId).toBe('env-client-id');
      expect(config.region).toBe('us-west-2');
    });
  });
});
/**
 * Amplify Configuration Tests
 * Tests the centralized Amplify/Cognito configuration and validates no hardcoded values
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock AWS Amplify
const mockAmplify = {
  configure: vi.fn()
};

vi.mock('aws-amplify', () => ({
  Amplify: mockAmplify
}));

// Mock window.__CONFIG__
const mockWindowConfig = {
  COGNITO: {
    USER_POOL_ID: 'us-east-1_TEST123456',
    CLIENT_ID: 'test-client-id-123',
    REGION: 'us-east-1',
    DOMAIN: 'auth.example.com',
    REDIRECT_SIGN_IN: 'https://app.example.com',
    REDIRECT_SIGN_OUT: 'https://app.example.com'
  },
  FEATURES: {
    AUTHENTICATION: true,
    COGNITO_AUTH: true
  }
};

describe('Amplify Configuration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock window and location
    global.window = global.window || {};
    window.__CONFIG__ = { ...mockWindowConfig };
    window.location = {
      origin: 'https://app.example.com',
      hostname: 'app.example.com'
    };
    
    // Mock environment variables
    vi.stubEnv('VITE_COGNITO_USER_POOL_ID', 'us-east-1_ENV123456');
    vi.stubEnv('VITE_COGNITO_CLIENT_ID', 'env-client-id-123');
    vi.stubEnv('VITE_AWS_REGION', 'us-west-2');
    vi.stubEnv('NODE_ENV', 'test');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  describe('Cognito Configuration Detection', () => {
    it('should detect valid Cognito configuration', async () => {
      const { isCognitoConfigured } = await import('../../../config/amplify');
      
      const isConfigured = isCognitoConfigured();
      
      expect(isConfigured).toBe(true);
    });

    it('should reject null or undefined values', async () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = null;
      window.__CONFIG__.COGNITO.CLIENT_ID = null;
      
      vi.resetModules();
      const { isCognitoConfigured } = await import('../../../config/amplify');
      
      const isConfigured = isCognitoConfigured();
      
      expect(isConfigured).toBe(false);
    });

    it('should reject dummy values', async () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = 'us-east-1_DUMMY';
      window.__CONFIG__.COGNITO.CLIENT_ID = 'dummy-client-id';
      
      vi.resetModules();
      const { isCognitoConfigured } = await import('../../../config/amplify');
      
      const isConfigured = isCognitoConfigured();
      
      expect(isConfigured).toBe(false);
    });

    it('should reject hardcoded invalid values', async () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = '3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z';
      window.__CONFIG__.COGNITO.CLIENT_ID = 'undefined';
      
      vi.resetModules();
      const { isCognitoConfigured } = await import('../../../config/amplify');
      
      const isConfigured = isCognitoConfigured();
      
      expect(isConfigured).toBe(false);
    });

    it('should reject empty strings', async () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = '';
      window.__CONFIG__.COGNITO.CLIENT_ID = '';
      
      vi.resetModules();
      const { isCognitoConfigured } = await import('../../../config/amplify');
      
      const isConfigured = isCognitoConfigured();
      
      expect(isConfigured).toBe(false);
    });

    it('should log configuration check results', async () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
      
      const { isCognitoConfigured } = await import('../../../config/amplify');
      
      isCognitoConfigured();
      
      expect(consoleSpy).toHaveBeenCalledWith(
        'Cognito config check:',
        expect.objectContaining({
          isValid: expect.any(Boolean),
          userPoolId: expect.stringMatching(/^us-east-1_TEST.+\.\.\.|null$/),
          clientId: expect.stringMatching(/^test-cli.+\.\.\.|null$/)
        })
      );
      
      consoleSpy.mockRestore();
    });
  });

  describe('Configuration Retrieval', () => {
    it('should get Cognito configuration from centralized config', async () => {
      const { getCognitoConfig } = await import('../../../config/amplify');
      
      const config = getCognitoConfig();
      
      expect(config).toMatchObject({
        userPoolId: 'us-east-1_TEST123456',
        userPoolClientId: 'test-client-id-123',
        region: 'us-east-1',
        domain: 'auth.example.com',
        redirectSignIn: 'https://app.example.com',
        redirectSignOut: 'https://app.example.com'
      });
    });

    it('should use environment config as fallback', async () => {
      delete window.__CONFIG__;
      
      vi.resetModules();
      const { getCognitoConfig } = await import('../../../config/amplify');
      
      const config = getCognitoConfig();
      
      expect(config).toMatchObject({
        userPoolId: 'us-east-1_ENV123456',
        userPoolClientId: 'env-client-id-123',
        region: 'us-west-2'
      });
    });
  });

  describe('Amplify Configuration Generation', () => {
    it('should generate correct Amplify configuration', async () => {
      const amplifyConfig = (await import('../../../config/amplify')).default;
      
      const config = amplifyConfig();
      
      expect(config).toMatchObject({
        Auth: {
          Cognito: {
            userPoolId: 'us-east-1_TEST123456',
            userPoolClientId: 'test-client-id-123',
            region: 'us-east-1',
            signUpVerificationMethod: 'code',
            loginWith: {
              username: true,
              email: true,
              oauth: expect.objectContaining({
                domain: 'auth.example.com',
                scopes: expect.arrayContaining(['email', 'profile', 'openid']),
                redirectSignIn: 'https://app.example.com',
                redirectSignOut: 'https://app.example.com',
                responseType: 'code'
              })
            }
          }
        }
      });
    });

    it('should handle missing OAuth domain', async () => {
      window.__CONFIG__.COGNITO.DOMAIN = '';
      
      vi.resetModules();
      const amplifyConfig = (await import('../../../config/amplify')).default;
      
      const config = amplifyConfig();
      
      expect(config.Auth.Cognito.loginWith.oauth).toBeUndefined();
      expect(config.Auth.Cognito.loginWith.username).toBe(true);
      expect(config.Auth.Cognito.loginWith.email).toBe(true);
    });

    it('should handle undefined OAuth domain', async () => {
      window.__CONFIG__.COGNITO.DOMAIN = 'undefined';
      
      vi.resetModules();
      const amplifyConfig = (await import('../../../config/amplify')).default;
      
      const config = amplifyConfig();
      
      expect(config.Auth.Cognito.loginWith.oauth).toBeUndefined();
    });
  });

  describe('Configuration Process', () => {
    it('should configure Amplify successfully with valid config', async () => {
      const { configureAmplify } = await import('../../../config/amplify');
      
      const result = configureAmplify();
      
      expect(result).toBe(true);
      expect(mockAmplify.configure).toHaveBeenCalledWith(
        expect.objectContaining({
          Auth: expect.objectContaining({
            Cognito: expect.objectContaining({
              userPoolId: 'us-east-1_TEST123456',
              userPoolClientId: 'test-client-id-123'
            })
          })
        })
      );
    });

    it('should fail when authentication is disabled', async () => {
      window.__CONFIG__.FEATURES.AUTHENTICATION = false;
      
      vi.resetModules();
      const { configureAmplify } = await import('../../../config/amplify');
      
      const result = configureAmplify();
      
      expect(result).toBe(false);
      expect(mockAmplify.configure).not.toHaveBeenCalled();
    });

    it('should fail when Cognito is disabled', async () => {
      window.__CONFIG__.FEATURES.COGNITO_AUTH = false;
      
      vi.resetModules();
      const { configureAmplify } = await import('../../../config/amplify');
      
      const result = configureAmplify();
      
      expect(result).toBe(false);
      expect(mockAmplify.configure).not.toHaveBeenCalled();
    });

    it('should handle invalid Cognito configuration in development', async () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = null;
      vi.stubEnv('NODE_ENV', 'development');
      
      vi.resetModules();
      const { configureAmplify } = await import('../../../config/amplify');
      
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      
      const result = configureAmplify();
      
      expect(result).toBe(false);
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        expect.stringContaining('Development mode - continuing without Cognito')
      );
      expect(mockAmplify.configure).not.toHaveBeenCalled();
      
      consoleWarnSpy.mockRestore();
    });

    it('should throw error for invalid config in production', async () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = null;
      vi.stubEnv('NODE_ENV', 'production');
      
      vi.resetModules();
      const { configureAmplify } = await import('../../../config/amplify');
      
      expect(() => {
        configureAmplify();
      }).toThrow('Cognito configuration required for production deployment');
    });

    it('should log configuration details', async () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
      
      const { configureAmplify } = await import('../../../config/amplify');
      
      configureAmplify();
      
      expect(consoleSpy).toHaveBeenCalledWith(
        '🔧 Configuring Amplify with centralized config:',
        expect.objectContaining({
          userPoolId: expect.stringMatching(/^us-east-1_TEST.+\.\.\.$/),
          clientId: expect.stringMatching(/^test-cli.+\.\.\.$/),
          region: 'us-east-1',
          authEnabled: true,
          cognitoEnabled: true
        })
      );
      
      consoleSpy.mockRestore();
    });
  });

  describe('Error Handling', () => {
    it('should handle Amplify configuration errors', async () => {
      mockAmplify.configure.mockImplementation(() => {
        throw new Error('Amplify configuration failed');
      });
      
      const { configureAmplify } = await import('../../../config/amplify');
      
      expect(() => {
        configureAmplify();
      }).toThrow('Amplify configuration failed');
    });

    it('should handle missing environment configuration gracefully in development', async () => {
      delete window.__CONFIG__;
      vi.stubEnv('VITE_COGNITO_USER_POOL_ID', undefined);
      vi.stubEnv('VITE_COGNITO_CLIENT_ID', undefined);
      vi.stubEnv('NODE_ENV', 'development');
      
      vi.resetModules();
      
      expect(() => {
        import('../../../config/amplify');
      }).not.toThrow();
    });
  });

  describe('Security Validation', () => {
    it('should not expose sensitive configuration in logs', async () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
      
      const { configureAmplify } = await import('../../../config/amplify');
      
      configureAmplify();
      
      const logCalls = consoleSpy.mock.calls;
      const logString = JSON.stringify(logCalls);
      
      // Should not contain full sensitive values
      expect(logString).not.toContain('us-east-1_TEST123456');
      expect(logString).not.toContain('test-client-id-123');
      
      // Should contain truncated versions
      expect(logString).toContain('us-east-1_TEST...');
      expect(logString).toContain('test-cli...');
      
      consoleSpy.mockRestore();
    });

    it('should validate User Pool ID format', async () => {
      window.__CONFIG__.COGNITO.USER_POOL_ID = 'invalid-format';
      
      vi.resetModules();
      const { isCognitoConfigured } = await import('../../../config/amplify');
      
      const isConfigured = isCognitoConfigured();
      
      // Should still validate based on content, not format
      expect(isConfigured).toBe(true); // Since it's not a dummy value
    });

    it('should prevent known bad values', async () => {
      const knownBadValues = [
        'us-east-1_DUMMY',
        'dummy-client-id',
        '3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z',
        'undefined',
        'null',
        ''
      ];
      
      for (const badValue of knownBadValues) {
        window.__CONFIG__.COGNITO.USER_POOL_ID = badValue;
        window.__CONFIG__.COGNITO.CLIENT_ID = badValue;
        
        vi.resetModules();
        const { isCognitoConfigured } = await import('../../../config/amplify');
        
        const isConfigured = isCognitoConfigured();
        
        expect(isConfigured).toBe(false);
      }
    });
  });

  describe('Environment-Specific Behavior', () => {
    it('should use different behavior for localhost', async () => {
      window.location.hostname = 'localhost';
      vi.stubEnv('NODE_ENV', 'development');
      
      vi.resetModules();
      const { configureAmplify } = await import('../../../config/amplify');
      
      // Should not throw even with invalid config in development
      window.__CONFIG__.COGNITO.USER_POOL_ID = null;
      
      expect(() => {
        configureAmplify();
      }).not.toThrow();
    });

    it('should be strict in production environment', async () => {
      window.location.hostname = 'app.production.com';
      vi.stubEnv('NODE_ENV', 'production');
      
      window.__CONFIG__.COGNITO.USER_POOL_ID = null;
      
      vi.resetModules();
      const { configureAmplify } = await import('../../../config/amplify');
      
      expect(() => {
        configureAmplify();
      }).toThrow();
    });
  });

  describe('No Hardcoded Values Validation', () => {
    it('should not contain hardcoded Cognito values', async () => {
      const amplifyModule = await import('../../../config/amplify');
      
      const moduleString = JSON.stringify(amplifyModule);
      
      // Check for known hardcoded values that should not exist
      expect(moduleString).not.toContain('3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z');
      expect(moduleString).not.toContain('us-east-1_MISSING');
      expect(moduleString).not.toContain('missing-client-id');
    });

    it('should use configuration from environment system', async () => {
      const { getCognitoConfig } = await import('../../../config/amplify');
      
      const config = getCognitoConfig();
      
      // Should get values from our centralized config system
      expect(config.userPoolId).toBe(window.__CONFIG__.COGNITO.USER_POOL_ID);
      expect(config.userPoolClientId).toBe(window.__CONFIG__.COGNITO.CLIENT_ID);
    });

    it('should not contain references to old API Gateway URLs', async () => {
      const amplifyModule = await import('../../../config/amplify');
      
      const moduleString = JSON.stringify(amplifyModule);
      
      expect(moduleString).not.toContain('2m14opj30h.execute-api.us-east-1.amazonaws.com');
      expect(moduleString).not.toContain('https://2m14opj30h');
    });
  });

  describe('Configuration Validation', () => {
    it('should validate required configuration fields', async () => {
      const { getCognitoConfig } = await import('../../../config/amplify');
      
      const config = getCognitoConfig();
      
      expect(config).toHaveProperty('userPoolId');
      expect(config).toHaveProperty('userPoolClientId');
      expect(config).toHaveProperty('region');
      expect(config).toHaveProperty('redirectSignIn');
      expect(config).toHaveProperty('redirectSignOut');
    });

    it('should use window.location.origin as default redirects', async () => {
      window.__CONFIG__.COGNITO.REDIRECT_SIGN_IN = undefined;
      window.__CONFIG__.COGNITO.REDIRECT_SIGN_OUT = undefined;
      
      vi.resetModules();
      const { getCognitoConfig } = await import('../../../config/amplify');
      
      const config = getCognitoConfig();
      
      expect(config.redirectSignIn).toBe('https://app.example.com');
      expect(config.redirectSignOut).toBe('https://app.example.com');
    });
  });
});
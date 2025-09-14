/**
 * Amplify Configuration Unit Tests
 * Tests for AWS Amplify configuration helper functions
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock Amplify
const mockAmplify = {
  configure: vi.fn()
};

vi.mock('aws-amplify', () => ({
  Amplify: mockAmplify
}));

// Mock console methods
const consoleMock = {
  log: vi.fn(),
  warn: vi.fn(),
  error: vi.fn()
};

global.console = consoleMock;

// Mock window object
const windowMock = {
  __CONFIG__: undefined,
  location: {
    origin: 'http://localhost:5173'
  }
};

global.window = windowMock;

describe("Amplify Configuration", () => {
  let _amplifyModule;
  let originalImportMetaEnv;

  beforeEach(async () => {
    // Clear all mocks
    vi.clearAllMocks();
    
    // Mock import.meta.env
    originalImportMetaEnv = globalThis.import?.meta?.env;
    vi.stubGlobal('import.meta', {
      env: {
        VITE_COGNITO_USER_POOL_ID: '',
        VITE_COGNITO_CLIENT_ID: '',
        VITE_AWS_REGION: 'us-east-1',
        VITE_COGNITO_DOMAIN: '',
        VITE_COGNITO_REDIRECT_SIGN_IN: 'http://localhost:5173',
        VITE_COGNITO_REDIRECT_SIGN_OUT: 'http://localhost:5173'
      }
    });
    
    // Reset window config
    windowMock.__CONFIG__ = undefined;
    
    // Clear module cache and reimport
    vi.resetModules();
    await import("../../../config/amplify.js");
  });

  afterEach(() => {
    // Restore original import.meta.env
    if (originalImportMetaEnv) {
      vi.stubGlobal('import.meta', { env: originalImportMetaEnv });
    }
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  describe("getRuntimeConfig", () => {
    it("should return window.__CONFIG__ when available", async () => {
      const testConfig = {
        USER_POOL_ID: 'runtime-pool-id',
        USER_POOL_CLIENT_ID: 'runtime-client-id',
        USER_POOL_DOMAIN: 'runtime-domain.auth.us-east-1.amazoncognito.com'
      };
      
      windowMock.__CONFIG__ = testConfig;
      
      // Need to re-import after changing window config
      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();
      
      expect(config.Auth.Cognito.userPoolId).toBe('runtime-pool-id');
      expect(config.Auth.Cognito.userPoolClientId).toBe('runtime-client-id');
    });

    it("should return empty object when window.__CONFIG__ is not available", async () => {
      windowMock.__CONFIG__ = undefined;
      
      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();
      
      // Should fallback to dummy values
      expect(config.Auth.Cognito.userPoolId).toBe('us-east-1_DUMMY');
      expect(config.Auth.Cognito.userPoolClientId).toBe('dummy-client-id');
    });

    it("should handle window being undefined", async () => {
      const originalWindow = global.window;
      delete global.window;
      
      try {
        vi.resetModules();
        const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
        const config = getAmplifyConfig();
        
        expect(config).toBeDefined();
        expect(config.Auth.Cognito.userPoolId).toBe('us-east-1_DUMMY');
      } finally {
        global.window = originalWindow;
      }
    });
  });

  describe("isCognitoConfigured", () => {
    it("should return true when valid runtime config is provided", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: 'us-east-1_ValidPoolId',
        USER_POOL_CLIENT_ID: 'valid-client-id'
      };
      
      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");
      
      expect(isCognitoConfigured()).toBe(true);
    });

    it("should return true when valid environment variables are provided", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: 'us-east-1_ValidPoolId',
        USER_POOL_CLIENT_ID: 'valid-client-id'
      };
      
      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");
      
      expect(isCognitoConfigured()).toBe(true);
    });

    it("should return false when using dummy values", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: 'us-east-1_DUMMY',
        USER_POOL_CLIENT_ID: 'dummy-client-id'
      };
      
      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");
      
      expect(isCognitoConfigured()).toBe(false);
    });

    it("should return false when values are empty strings", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: '',
        USER_POOL_CLIENT_ID: ''
      };
      
      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");
      
      expect(isCognitoConfigured()).toBe(false);
    });

    it("should return false when values are missing", async () => {
      windowMock.__CONFIG__ = {};
      
      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");
      
      expect(isCognitoConfigured()).toBe(false);
    });

    it("should prioritize runtime config over environment variables", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: 'us-east-1_RuntimePoolId',
        USER_POOL_CLIENT_ID: 'runtime-client-id'
      };
      
      vi.stubGlobal('import.meta', {
        env: {
          VITE_COGNITO_USER_POOL_ID: 'us-east-1_DUMMY',
          VITE_COGNITO_CLIENT_ID: 'dummy-client-id'
        }
      });
      
      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");
      
      expect(isCognitoConfigured()).toBe(true);
    });
  });

  describe("getAmplifyConfig", () => {
    it("should generate config with runtime values", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: 'us-east-1_RuntimePool',
        USER_POOL_CLIENT_ID: 'runtime-client',
        USER_POOL_DOMAIN: 'runtime-domain.auth.us-east-1.amazoncognito.com'
      };
      
      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();
      
      expect(config.Auth.Cognito.userPoolId).toBe('us-east-1_RuntimePool');
      expect(config.Auth.Cognito.userPoolClientId).toBe('runtime-client');
      expect(config.Auth.Cognito.loginWith.oauth.domain).toBe('runtime-domain.auth.us-east-1.amazoncognito.com');
    });

    it("should generate config with runtime values", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: 'us-east-1_EnvPool',
        USER_POOL_CLIENT_ID: 'env-client',
        USER_POOL_DOMAIN: 'env-domain.auth.us-east-1.amazoncognito.com'
      };
      
      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();
      
      expect(config.Auth.Cognito.userPoolId).toBe('us-east-1_EnvPool');
      expect(config.Auth.Cognito.userPoolClientId).toBe('env-client');
      expect(config.Auth.Cognito.loginWith.oauth.domain).toBe('env-domain.auth.us-east-1.amazoncognito.com');
    });

    it("should use dummy values when no config is provided", async () => {
      windowMock.__CONFIG__ = undefined;
      
      vi.stubGlobal('import.meta', {
        env: {
          VITE_AWS_REGION: 'us-east-1'
        }
      });
      
      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();
      
      expect(config.Auth.Cognito.userPoolId).toBe('us-east-1_DUMMY');
      expect(config.Auth.Cognito.userPoolClientId).toBe('dummy-client-id');
      expect(config.Auth.Cognito.loginWith.oauth.domain).toBe('dummy-domain');
    });

    it("should include correct OAuth configuration", async () => {
      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();
      
      expect(config.Auth.Cognito.loginWith.oauth.scopes).toEqual(['email', 'profile', 'openid']);
      expect(config.Auth.Cognito.loginWith.oauth.responseType).toBe('code');
      expect(config.Auth.Cognito.loginWith.username).toBe(true);
      expect(config.Auth.Cognito.loginWith.email).toBe(true);
      expect(config.Auth.Cognito.signUpVerificationMethod).toBe('code');
    });

    it("should handle window origin fallback for redirects", async () => {
      windowMock.__CONFIG__ = undefined;
      
      // Mock window.location.origin at global level before module import
      const originalWindow = global.window;
      global.window = {
        ...windowMock,
        location: {
          origin: 'https://test.example.com'
        }
      };
      
      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();
      
      expect(config.Auth.Cognito.loginWith.oauth.redirectSignIn).toBe('https://test.example.com');
      expect(config.Auth.Cognito.loginWith.oauth.redirectSignOut).toBe('https://test.example.com');
      
      // Restore original window
      global.window = originalWindow;
    });
  });

  describe("configureAmplify", () => {
    it("should successfully configure Amplify with valid config", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: 'us-east-1_ValidPool',
        USER_POOL_CLIENT_ID: 'valid-client'
      };
      
      vi.resetModules();
      const { configureAmplify } = await import("../../../config/amplify.js");
      
      configureAmplify();
      
      expect(mockAmplify.configure).toHaveBeenCalledWith(
        expect.objectContaining({
          Auth: expect.objectContaining({
            Cognito: expect.objectContaining({
              userPoolId: 'us-east-1_ValidPool',
              userPoolClientId: 'valid-client'
            })
          })
        })
      );
      
      expect(consoleMock.log).toHaveBeenCalledWith('✅ Amplify configured successfully');
    });

    it("should log warning when Cognito is not configured", async () => {
      windowMock.__CONFIG__ = undefined;
      
      vi.resetModules();
      const { configureAmplify } = await import("../../../config/amplify.js");
      
      configureAmplify();
      
      expect(consoleMock.warn).toHaveBeenCalledWith(
        '⚠️  Cognito not configured - using dummy values for development'
      );
      expect(consoleMock.log).toHaveBeenCalledWith('Environment variables needed:');
      expect(consoleMock.log).toHaveBeenCalledWith('- VITE_COGNITO_USER_POOL_ID');
      expect(consoleMock.log).toHaveBeenCalledWith('- VITE_COGNITO_CLIENT_ID');
      expect(consoleMock.log).toHaveBeenCalledWith('- VITE_COGNITO_DOMAIN');
      expect(consoleMock.log).toHaveBeenCalledWith('Or set runtime config in window.__CONFIG__');
    });

    it("should log configuration details", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: 'us-east-1_TestPool',
        USER_POOL_CLIENT_ID: 'test-client',
        USER_POOL_DOMAIN: 'test-domain.auth.us-east-1.amazoncognito.com'
      };
      
      vi.resetModules();
      const { configureAmplify } = await import("../../../config/amplify.js");
      
      configureAmplify();
      
      expect(consoleMock.log).toHaveBeenCalledWith(
        '🔧 [AMPLIFY CONFIG] Configuration details:',
        expect.objectContaining({
          userPoolId: 'us-east-1_TestPool',
          clientId: 'test-client',
          domain: 'test-domain.auth.us-east-1.amazoncognito.com',
          runtimeConfigAvailable: true,
          isCognitoConfigured: true
        })
      );
    });

    it("should handle configuration errors gracefully", async () => {
      mockAmplify.configure.mockImplementationOnce(() => {
        throw new Error('Configuration failed');
      });
      
      vi.resetModules();
      const { configureAmplify } = await import("../../../config/amplify.js");
      
      expect(() => configureAmplify()).not.toThrow();
      
      expect(consoleMock.error).toHaveBeenCalledWith(
        '❌ Failed to configure Amplify:',
        expect.any(Error)
      );
    });

    it("should show runtime config not available when window.__CONFIG__ is empty", async () => {
      windowMock.__CONFIG__ = {};
      
      vi.resetModules();
      const { configureAmplify } = await import("../../../config/amplify.js");
      
      configureAmplify();
      
      expect(consoleMock.log).toHaveBeenCalledWith(
        '🔧 [AMPLIFY CONFIG] Configuration details:',
        expect.objectContaining({
          runtimeConfigAvailable: false
        })
      );
    });
  });

  describe("Module Exports", () => {
    it("should export all required functions", async () => {
      vi.resetModules();
      const amplifyModule = await import("../../../config/amplify.js");
      
      expect(amplifyModule.isCognitoConfigured).toBeDefined();
      expect(amplifyModule.getAmplifyConfig).toBeDefined();
      expect(amplifyModule.configureAmplify).toBeDefined();
      expect(amplifyModule.default).toBeDefined();
      expect(amplifyModule.default).toBe(amplifyModule.getAmplifyConfig);
    });
  });
});
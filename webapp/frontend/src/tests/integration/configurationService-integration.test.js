/**
 * Configuration Service Integration Tests
 * Tests the configuration service with real-world scenarios and Amplify integration
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('ConfigurationService Integration Tests', () => {
  let configurationService;
  let originalWindow;

  beforeEach(async () => {
    // Save original window
    originalWindow = global.window;
    
    // Import the service
    const module = await import('../../services/configurationService');
    configurationService = module.default;
    configurationService.reset();
  });

  afterEach(() => {
    // Restore window
    global.window = originalWindow;
    configurationService.reset();
    vi.clearAllMocks();
  });

  describe('Real CloudFormation Integration', () => {
    it('should handle complete CloudFormation configuration', async () => {
      // Simulate a real CloudFormation deployment configuration
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod',
          UserPoolId: 'us-east-1_AbC123XyZ',
          UserPoolClientId: '1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p',
          UserPoolDomain: 'financial-dashboard-prod.auth.us-east-1.amazoncognito.com',
          FrontendBucketName: 'financial-dashboard-frontend-prod-123456789012',
          WebsiteURL: 'https://d1234567890123.cloudfront.net'
        }
      };

      const config = await configurationService.initialize();

      expect(config.api.baseUrl).toBe('https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod');
      expect(config.cognito.userPoolId).toBe('us-east-1_AbC123XyZ');
      expect(config.cognito.clientId).toBe('1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p');
      expect(config.cognito.domain).toBe('financial-dashboard-prod.auth.us-east-1.amazoncognito.com');
      expect(config.source).toBe('cloudformation');

      // Should be properly configured for authentication
      const isAuthConfigured = await configurationService.isAuthenticationConfigured();
      expect(isAuthConfigured).toBe(true);
    });

    it('should handle development environment CloudFormation config', async () => {
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
          UserPoolId: 'us-east-1_ZqooNeQtV',
          UserPoolClientId: '243r98prucoickch12djkahrhk',
          UserPoolDomain: 'https://financial-dashboard-dev-626216981288.auth.us-east-1.amazoncognito.com',
          FrontendBucketName: 'financial-dashboard-frontend-dev-626216981288'
        }
      };

      const config = await configurationService.initialize();

      expect(config.api.baseUrl).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev');
      expect(config.cognito.userPoolId).toBe('us-east-1_ZqooNeQtV');
      expect(config.cognito.clientId).toBe('243r98prucoickch12djkahrhk');
      
      const isAuthConfigured = await configurationService.isAuthenticationConfigured();
      expect(isAuthConfigured).toBe(true);
    });
  });

  describe('Amplify Configuration Integration', () => {
    it('should provide Amplify-compatible configuration', async () => {
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://test-api.execute-api.us-east-1.amazonaws.com/prod',
          UserPoolId: 'us-east-1_TestPool123',
          UserPoolClientId: 'test-client-id-amplify',
          UserPoolDomain: 'test-amplify.auth.us-east-1.amazoncognito.com'
        },
        location: {
          origin: 'https://test-app.example.com'
        }
      };

      const cognitoConfig = await configurationService.getCognitoConfig();

      expect(cognitoConfig).toEqual({
        userPoolId: 'us-east-1_TestPool123',
        clientId: 'test-client-id-amplify',
        domain: 'test-amplify.auth.us-east-1.amazoncognito.com',
        region: 'us-east-1',
        redirectSignIn: 'https://test-app.example.com',
        redirectSignOut: 'https://test-app.example.com'
      });
    });

    it('should handle missing window.location gracefully', async () => {
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          UserPoolId: 'us-east-1_TestPool123',
          UserPoolClientId: 'test-client-id'
        }
        // No location object
      };

      const cognitoConfig = await configurationService.getCognitoConfig();

      expect(cognitoConfig.redirectSignIn).toBe('');
      expect(cognitoConfig.redirectSignOut).toBe('');
    });
  });

  describe('Error Recovery Integration', () => {
    it('should recover from malformed CloudFormation config', async () => {
      // Simulate corrupted/malformed CloudFormation config
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: null,
          UserPoolId: '',
          UserPoolClientId: undefined
        }
      };

      // Mock import.meta.env with fallback values
      vi.doMock('import.meta', () => ({
        env: {
          VITE_API_URL: 'https://fallback-api.example.com',
          VITE_COGNITO_USER_POOL_ID: 'us-east-1_FallbackPool',
          VITE_COGNITO_CLIENT_ID: 'fallback-client-id'
        }
      }));

      const config = await configurationService.initialize();

      // Should fall back to environment variables
      expect(config.api.baseUrl).toBe('https://fallback-api.example.com');
      expect(config.cognito.userPoolId).toBe('us-east-1_FallbackPool');
      expect(config.cognito.clientId).toBe('fallback-client-id');
    });

    it('should handle network errors during configuration loading', async () => {
      // Mock a scenario where configuration loading throws an error
      const originalLoadCloudFormationConfig = configurationService.loadCloudFormationConfig;
      configurationService.loadCloudFormationConfig = () => {
        throw new Error('Network error loading CloudFormation config');
      };

      const config = await configurationService.initialize();

      expect(config.source).toBe('safety_fallback');
      expect(config.error).toBe(true);
      expect(config.features.authentication).toBe(false);

      // Restore original method
      configurationService.loadCloudFormationConfig = originalLoadCloudFormationConfig;
    });
  });

  describe('Multi-source Priority Integration', () => {
    it('should correctly prioritize CloudFormation over window config', async () => {
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://cf-priority.execute-api.us-east-1.amazonaws.com/prod',
          UserPoolId: 'us-east-1_CFPriority'
        },
        __CONFIG__: {
          API: {
            BASE_URL: 'https://window-priority.example.com'
          },
          COGNITO: {
            USER_POOL_ID: 'us-east-1_WindowPriority'
          }
        }
      };

      const config = await configurationService.initialize();

      // CloudFormation should win
      expect(config.api.baseUrl).toBe('https://cf-priority.execute-api.us-east-1.amazonaws.com/prod');
      expect(config.cognito.userPoolId).toBe('us-east-1_CFPriority');
    });

    it('should fill gaps from lower priority sources', async () => {
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://cf-api.execute-api.us-east-1.amazonaws.com/prod'
          // Missing Cognito config
        },
        __CONFIG__: {
          COGNITO: {
            USER_POOL_ID: 'us-east-1_WindowFillGap',
            CLIENT_ID: 'window-fill-gap-client'
          }
        }
      };

      const config = await configurationService.initialize();

      // API from CloudFormation (highest priority)
      expect(config.api.baseUrl).toBe('https://cf-api.execute-api.us-east-1.amazonaws.com/prod');
      // Cognito from window config (fills the gap)
      expect(config.cognito.userPoolId).toBe('us-east-1_WindowFillGap');
      expect(config.cognito.clientId).toBe('window-fill-gap-client');
    });
  });

  describe('Placeholder Detection Integration', () => {
    it('should detect and warn about GitHub Actions placeholder patterns', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://api-gateway-placeholder-prod.execute-api.us-east-1.amazonaws.com/prod',
          UserPoolId: '3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z', // Common test placeholder pattern
          UserPoolClientId: 'dummy-client-id'
        }
      };

      await configurationService.initialize();

      expect(consoleSpy).toHaveBeenCalledWith(
        '⚠️ Configuration validation warnings:',
        expect.arrayContaining([
          expect.stringContaining('placeholder value')
        ])
      );

      consoleSpy.mockRestore();
    });

    it('should pass validation for real AWS resource values', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://abc123def456.execute-api.us-east-1.amazonaws.com/prod',
          UserPoolId: 'us-east-1_AbC123DeF456', // Real AWS format
          UserPoolClientId: '1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p' // Real client ID format
        }
      };

      await configurationService.initialize();

      // Should not have warning calls about placeholder values
      const warnings = consoleSpy.mock.calls.filter(call => 
        call[0] === '⚠️ Configuration validation warnings:'
      );
      expect(warnings).toHaveLength(0);

      consoleSpy.mockRestore();
    });
  });

  describe('Concurrent Access Integration', () => {
    it('should handle concurrent initialization calls', async () => {
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://concurrent-test.execute-api.us-east-1.amazonaws.com/prod',
          UserPoolId: 'us-east-1_ConcurrentTest'
        }
      };

      // Start multiple initializations concurrently
      const promises = Array(5).fill().map(() => configurationService.initialize());
      const configs = await Promise.all(promises);

      // All should return the same cached configuration
      configs.forEach(config => {
        expect(config).toBe(configs[0]); // Same object reference
        expect(config.api.baseUrl).toBe('https://concurrent-test.execute-api.us-east-1.amazonaws.com/prod');
      });
    });

    it('should handle concurrent access to different methods', async () => {
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://multi-access.execute-api.us-east-1.amazonaws.com/prod',
          UserPoolId: 'us-east-1_MultiAccess',
          UserPoolClientId: 'multi-access-client'
        }
      };

      // Access different methods concurrently
      const [apiConfig, cognitoConfig, isConfigured] = await Promise.all([
        configurationService.getApiConfig(),
        configurationService.getCognitoConfig(),
        configurationService.isAuthenticationConfigured()
      ]);

      expect(apiConfig.baseUrl).toBe('https://multi-access.execute-api.us-east-1.amazonaws.com/prod');
      expect(cognitoConfig.userPoolId).toBe('us-east-1_MultiAccess');
      expect(cognitoConfig.clientId).toBe('multi-access-client');
      expect(isConfigured).toBe(true);
    });
  });

  describe('Configuration Updates Integration', () => {
    it('should handle configuration reset and re-initialization', async () => {
      // Initial configuration
      global.window = {
        __CLOUDFORMATION_CONFIG__: {
          ApiGatewayUrl: 'https://initial-config.execute-api.us-east-1.amazonaws.com/prod'
        }
      };

      const initialConfig = await configurationService.initialize();
      expect(initialConfig.api.baseUrl).toBe('https://initial-config.execute-api.us-east-1.amazonaws.com/prod');

      // Reset and change configuration
      configurationService.reset();
      global.window.__CLOUDFORMATION_CONFIG__.ApiGatewayUrl = 'https://updated-config.execute-api.us-east-1.amazonaws.com/prod';

      const updatedConfig = await configurationService.initialize();
      expect(updatedConfig.api.baseUrl).toBe('https://updated-config.execute-api.us-east-1.amazonaws.com/prod');
      expect(updatedConfig).not.toBe(initialConfig); // Different object
    });
  });
});
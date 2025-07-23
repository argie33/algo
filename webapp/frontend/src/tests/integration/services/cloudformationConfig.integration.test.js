/**
 * CloudFormation Configuration Integration Tests
 * Tests the full flow from frontend to backend for CloudFormation configuration
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock fetch for integration testing
global.fetch = vi.fn();

describe('🔧 CloudFormation Configuration Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock console methods
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Real CloudFormation Configuration Flow', () => {
    it('should successfully fetch and transform CloudFormation config', async () => {
      // Mock the real CloudFormation API response structure
      const mockCloudFormationResponse = {
        success: true,
        stackName: 'stocks-webapp-dev',
        region: 'us-east-1',
        accountId: '123456789012',
        stackStatus: 'CREATE_COMPLETE',
        outputs: {
          ApiGatewayUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
          ApiGatewayId: 'abc123def456',
          UserPoolId: 'us-east-1_RealPoolId123',
          UserPoolClientId: 'real-client-id-456',
          UserPoolDomain: 'stocks-dev.auth.us-east-1.amazoncognito.com',
          FrontendBucketName: 'stocks-frontend-bucket-dev',
          CloudFrontDistributionId: 'E1234567890ABC',
          WebsiteURL: 'https://d1zb7knau41vl9.cloudfront.net'
        },
        api: {
          gatewayUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
          gatewayId: 'abc123def456'
        },
        cognito: {
          userPoolId: 'us-east-1_RealPoolId123',
          clientId: 'real-client-id-456',
          domain: 'stocks-dev.auth.us-east-1.amazoncognito.com',
          region: 'us-east-1'
        },
        fetchedAt: new Date().toISOString()
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockCloudFormationResponse)
      });

      // Import and test the configuration service
      const configurationService = await import('../../../services/configurationService');
      const service = configurationService.default;
      service.reset();

      // Test the loadCloudFormationConfig method
      const config = await service.loadCloudFormationConfig();

      // Verify the API call was made with correct endpoint
      expect(fetch).toHaveBeenCalledWith(
        'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/config/cloudformation?stackName=stocks-webapp-dev'
      );

      // Verify configuration transformation
      expect(config).toEqual({
        api: {
          baseUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
        },
        cognito: {
          userPoolId: 'us-east-1_RealPoolId123',
          clientId: 'real-client-id-456',
          domain: 'stocks-dev.auth.us-east-1.amazoncognito.com'
        },
        aws: {
          region: 'us-east-1'
        },
        source: 'api'
      });
    });

    it('should handle CloudFormation stack not found (404)', async () => {
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found'
      });

      const configurationService = await import('../../../services/configurationService');
      const service = configurationService.default;
      service.reset();

      const config = await service.loadCloudFormationConfig();

      expect(config).toEqual({});
      expect(console.warn).toHaveBeenCalledWith(
        '⚠️ Failed to fetch CloudFormation config from API:', 
        404
      );
    });

    it('should handle CloudFormation access denied (403)', async () => {
      const mockErrorResponse = {
        error: 'Access denied',
        message: 'Lambda function does not have permission to describe CloudFormation stacks',
        code: 'AccessDenied'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: () => Promise.resolve(mockErrorResponse)
      });

      const configurationService = await import('../../../services/configurationService');
      const service = configurationService.default;
      service.reset();

      const config = await service.loadCloudFormationConfig();

      expect(config).toEqual({});
      expect(console.warn).toHaveBeenCalledWith(
        '⚠️ Failed to fetch CloudFormation config from API:', 
        403
      );
    });

    it('should handle network errors gracefully', async () => {
      fetch.mockRejectedValueOnce(new Error('Network request failed'));

      const configurationService = await import('../../../services/configurationService');
      const service = configurationService.default;
      service.reset();

      const config = await service.loadCloudFormationConfig();

      expect(config).toEqual({});
      expect(console.warn).toHaveBeenCalledWith(
        '⚠️ Error fetching CloudFormation config from API:', 
        'Network request failed'
      );
    });
  });

  describe('CloudFormationConfigService Integration', () => {
    it('should initialize and fetch real configuration successfully', async () => {
      const mockCloudFormationResponse = {
        success: true,
        stackName: 'stocks-webapp-dev',
        outputs: {
          ApiGatewayUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
          UserPoolId: 'us-east-1_RealPoolId123',
          UserPoolClientId: 'real-client-id-456',
          UserPoolDomain: 'stocks-dev.auth.us-east-1.amazoncognito.com'
        },
        region: 'us-east-1',
        accountId: '123456789012'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockCloudFormationResponse)
      });

      // Mock environment for testing
      vi.mock('../../../config/environment', () => ({
        getApiUrl: () => 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
      }));

      const cloudFormationConfigService = await import('../../../services/cloudFormationConfigService');
      const service = cloudFormationConfigService.default;

      const config = await service.initialize();

      expect(fetch).toHaveBeenCalledWith(
        'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/config/cloudformation?stackName=stocks-webapp-dev',
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          }
        }
      );

      expect(config).toEqual(expect.objectContaining({
        api: expect.objectContaining({
          baseUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
        }),
        cognito: expect.objectContaining({
          userPoolId: 'us-east-1_RealPoolId123',
          clientId: 'real-client-id-456',
          domain: 'stocks-dev.auth.us-east-1.amazoncognito.com'
        }),
        stack: expect.objectContaining({
          name: 'stocks-webapp-dev',
          region: 'us-east-1'
        }),
        metadata: expect.objectContaining({
          source: 'cloudformation'
        })
      }));
    });

    it('should validate real configuration correctly', async () => {
      const mockValidConfig = {
        success: true,
        outputs: {
          ApiGatewayUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
          UserPoolId: 'us-east-1_RealPoolId123',
          UserPoolClientId: 'real-client-id-456'
        }
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockValidConfig)
      });

      const cloudFormationConfigService = await import('../../../services/cloudFormationConfigService');
      const service = cloudFormationConfigService.default;

      const validation = await service.validateRealConfig();

      expect(validation.isValid).toBe(true);
      expect(validation.issues).toHaveLength(0);
      expect(validation.source).toBe('cloudformation');
    });

    it('should detect invalid/placeholder configuration', async () => {
      const mockInvalidConfig = {
        success: true,
        outputs: {
          ApiGatewayUrl: 'https://api.protrade.com/placeholder', // Fake domain
          UserPoolId: '3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z', // Placeholder pattern
          UserPoolClientId: null // Missing
        }
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockInvalidConfig)
      });

      const cloudFormationConfigService = await import('../../../services/cloudFormationConfigService');
      const service = cloudFormationConfigService.default;

      const validation = await service.validateRealConfig();

      expect(validation.isValid).toBe(false);
      expect(validation.issues).toEqual(
        expect.arrayContaining([
          'Cognito Client ID is missing',
          expect.stringContaining('fake domain')
        ])
      );
    });
  });

  describe('Error Recovery and Fallbacks', () => {
    it('should fallback to environment configuration when CloudFormation fails', async () => {
      fetch.mockRejectedValueOnce(new Error('CloudFormation service unavailable'));

      const configurationService = await import('../../../services/configurationService');
      const service = configurationService.default;
      service.reset();

      const config = await service.initialize();

      // Should fall back to environment configuration
      expect(config.source).not.toBe('cloudformation');
      expect(config.api.baseUrl).toBeDefined();
      expect(config.aws.region).toBe('us-east-1');
    });

    it('should use safety fallback when all configuration sources fail', async () => {
      fetch.mockRejectedValueOnce(new Error('Network error'));

      // Mock validation failure
      const configurationService = await import('../../../services/configurationService');
      const service = configurationService.default;
      service.reset();

      vi.spyOn(service, 'validateConfiguration').mockImplementation(() => {
        throw new Error('Validation failed');
      });

      const config = await service.initialize();

      expect(config.source).toBe('safety_fallback');
      expect(config.error).toBe(true);
      expect(config.features.authentication).toBe(false);
      expect(config.api.baseUrl).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev');
    });
  });

  describe('Configuration Caching', () => {
    it('should cache configuration after first successful fetch', async () => {
      const mockResponse = {
        success: true,
        outputs: { ApiGatewayUrl: 'https://cached.example.com' }
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      });

      const configurationService = await import('../../../services/configurationService');
      const service = configurationService.default;
      service.reset();

      // First call should fetch
      const config1 = await service.initialize();
      expect(fetch).toHaveBeenCalledTimes(1);

      // Second call should use cache
      const config2 = await service.initialize();
      expect(fetch).toHaveBeenCalledTimes(1); // Still only 1 call
      expect(config1).toBe(config2); // Same object reference
    });
  });
});
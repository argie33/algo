/**
 * Cognito Configuration Integration Test
 * Tests that the Cognito configuration is properly injected from CloudFormation
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import configurationService from '../../services/configurationService';

describe('Cognito Configuration Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset configuration service state
    configurationService.configCache = null;
  });

  it('loads real Cognito configuration from CloudFormation API', async () => {
    // Mock the fetch API to return real CloudFormation values
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          cognito: {
            userPoolId: 'us-east-1_ZqooNeQtV',
            clientId: '243r98prucoickch12djkahrhk',
            region: 'us-east-1'
          },
          api: {
            gatewayUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
          }
        })
      })
    );

    await configurationService.initialize();
    const cognitoConfig = await configurationService.getCognitoConfig();

    expect(cognitoConfig).toEqual({
      userPoolId: 'us-east-1_ZqooNeQtV',
      clientId: '243r98prucoickch12djkahrhk',
      region: 'us-east-1'
    });

    expect(fetch).toHaveBeenCalledWith(
      'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/config/cloudformation?stackName=stocks-webapp-dev'
    );
  });

  it('detects placeholder values and uses fallback', async () => {
    // Mock with placeholder values
    window.__CLOUDFORMATION_CONFIG__ = {
      COGNITO_USER_POOL_ID: 'user-pool-placeholder',
      COGNITO_CLIENT_ID: '3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z', // Placeholder ID
      COGNITO_REGION: 'us-east-1',
      API_GATEWAY_URL: 'https://api-placeholder.execute-api.us-east-1.amazonaws.com/dev'
    };

    await configurationService.initialize();
    const isValid = await configurationService.validateConfiguration();

    expect(isValid.cognitoValid).toBe(false);
    expect(isValid.errors).toContain('Cognito client ID appears to be a placeholder');
  });

  it('falls back to environment variables when CloudFormation config is invalid', async () => {
    // Mock environment variables
    process.env.REACT_APP_COGNITO_USER_POOL_ID = 'us-east-1_RealPoolId';
    process.env.REACT_APP_COGNITO_CLIENT_ID = 'realclientid123456789';
    
    // Mock invalid CloudFormation config
    window.__CLOUDFORMATION_CONFIG__ = {
      COGNITO_USER_POOL_ID: 'placeholder',
      COGNITO_CLIENT_ID: '3d2m8n9k5l6p7q8r9s0t1u2v3w4x5y6z',
      COGNITO_REGION: 'us-east-1'
    };

    await configurationService.initialize();
    const cognitoConfig = await configurationService.getCognitoConfig();

    expect(cognitoConfig.clientId).toBe('realclientid123456789');
    expect(cognitoConfig.userPoolId).toBe('us-east-1_RealPoolId');
  });

  it('validates configuration and reports issues', async () => {
    window.__CLOUDFORMATION_CONFIG__ = {};

    await configurationService.initialize();
    const validation = await configurationService.validateConfiguration();

    expect(validation.isValid).toBe(false);
    expect(validation.errors.length).toBeGreaterThan(0);
    expect(validation.errors).toContain('Cognito user pool ID is missing');
  });
});
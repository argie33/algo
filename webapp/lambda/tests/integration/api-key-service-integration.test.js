/**
 * API Key Service Integration Test
 * Tests the real AWS Parameter Store integration without mocking
 * NOTE: This test requires actual AWS credentials and Parameter Store access
 */

const simpleApiKeyService = require('../../utils/simpleApiKeyService');

describe('API Key Service Integration (Real AWS)', () => {
  const testUserId = 'integration-test-user';
  const testProvider = 'alpaca';
  const testApiKey = 'PKTEST123456789012345678901234567890';
  const testSecret = 'test-secret-key-1234567890123456789012345678901234567890';

  // Skip tests if not in AWS environment
  const skipIfNoAWS = () => {
    if (!process.env.AWS_REGION && !process.env.WEBAPP_AWS_REGION) {
      console.log('⚠️ Skipping AWS integration tests - no AWS environment detected');
      return true;
    }
    return false;
  };

  beforeAll(async () => {
    if (skipIfNoAWS()) return;
    
    // Clean up any existing test data
    try {
      await simpleApiKeyService.deleteApiKey(testUserId, testProvider);
      console.log('🧹 Cleaned up existing test data');
    } catch (error) {
      console.log('🧹 No existing test data to clean up');
    }
  });

  afterAll(async () => {
    if (skipIfNoAWS()) return;
    
    // Clean up test data
    try {
      await simpleApiKeyService.deleteApiKey(testUserId, testProvider);
      console.log('🧹 Test cleanup completed');
    } catch (error) {
      console.warn('⚠️ Error during test cleanup:', error.message);
    }
  });

  test('Service should be enabled and configured', () => {
    if (skipIfNoAWS()) return;
    
    expect(simpleApiKeyService.isEnabled).toBe(true);
    expect(simpleApiKeyService.parameterPrefix).toBe('/financial-platform/users');
  });

  test('Should store and retrieve API key successfully', async () => {
    if (skipIfNoAWS()) return;
    
    // Store API key
    console.log('🔐 Storing API key for integration test...');
    const storeResult = await simpleApiKeyService.storeApiKey(
      testUserId, 
      testProvider, 
      testApiKey, 
      testSecret
    );
    
    expect(storeResult).toBe(true);
    
    // Retrieve API key
    console.log('🔍 Retrieving API key...');
    const retrievedKey = await simpleApiKeyService.getApiKey(testUserId, testProvider);
    
    expect(retrievedKey).toBeTruthy();
    expect(retrievedKey.keyId).toBe(testApiKey);
    expect(retrievedKey.secretKey).toBe(testSecret);
    expect(retrievedKey.provider).toBe(testProvider);
    expect(retrievedKey.created).toBeTruthy();
    expect(retrievedKey.version).toBe('1.0');
  });

  test('Should list API keys correctly', async () => {
    if (skipIfNoAWS()) return;
    
    console.log('📋 Listing API keys...');
    const apiKeys = await simpleApiKeyService.listApiKeys(testUserId);
    
    expect(Array.isArray(apiKeys)).toBe(true);
    expect(apiKeys.length).toBe(1);
    
    const apiKey = apiKeys[0];
    expect(apiKey.provider).toBe(testProvider);
    expect(apiKey.keyId).toMatch(/^PKTES\*\*\*7890$/); // Masked format
    expect(apiKey.hasSecret).toBe(true);
    expect(apiKey.created).toBeTruthy();
  });

  test('Should delete API key successfully', async () => {
    if (skipIfNoAWS()) return;
    
    console.log('🗑️ Deleting API key...');
    const deleteResult = await simpleApiKeyService.deleteApiKey(testUserId, testProvider);
    
    expect(deleteResult).toBe(true);
    
    // Verify deletion by trying to retrieve
    const retrievedKey = await simpleApiKeyService.getApiKey(testUserId, testProvider);
    expect(retrievedKey).toBeNull();
    
    // List should be empty
    const apiKeys = await simpleApiKeyService.listApiKeys(testUserId);
    expect(apiKeys).toEqual([]);
  });

  test('Should handle non-existent keys gracefully', async () => {
    if (skipIfNoAWS()) return;
    
    // Try to get non-existent key
    const nonExistentKey = await simpleApiKeyService.getApiKey(testUserId, 'polygon');
    expect(nonExistentKey).toBeNull();
    
    // Try to delete non-existent key (should succeed)
    const deleteResult = await simpleApiKeyService.deleteApiKey(testUserId, 'polygon');
    expect(deleteResult).toBe(true);
  });

  test('Should validate providers correctly', async () => {
    if (skipIfNoAWS()) return;
    
    // Valid provider should work
    await expect(
      simpleApiKeyService.storeApiKey(testUserId, 'polygon', testApiKey, testSecret)
    ).resolves.toBe(true);
    
    // Clean up
    await simpleApiKeyService.deleteApiKey(testUserId, 'polygon');
    
    // Invalid provider should fail
    await expect(
      simpleApiKeyService.storeApiKey(testUserId, 'invalid-provider', testApiKey, testSecret)
    ).rejects.toThrow('Invalid provider');
  });

  test('Should perform health check successfully', async () => {
    if (skipIfNoAWS()) return;
    
    console.log('🔍 Performing health check...');
    const healthResult = await simpleApiKeyService.healthCheck();
    
    expect(healthResult).toBeTruthy();
    expect(healthResult.healthy).toBe(true);
    expect(healthResult.backend).toBe('AWS Parameter Store');
    expect(healthResult.timestamp).toBeTruthy();
  }, 30000); // Longer timeout for health check

}, 60000); // Longer timeout for the entire suite
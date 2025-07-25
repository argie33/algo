/**
 * Simple API Key Service Unit Tests
 * Tests the core AWS Parameter Store API key functionality
 */

const simpleApiKeyService = require('../../utils/apiKeyService');

// Mock AWS SDK
jest.mock('@aws-sdk/client-ssm', () => {
  const mockSend = jest.fn();
  const mockSSMClient = jest.fn(() => ({
    send: mockSend
  }));

  return {
    SSMClient: mockSSMClient,
    GetParameterCommand: jest.fn(),
    PutParameterCommand: jest.fn(),
    DeleteParameterCommand: jest.fn(),
    __mockSend: mockSend
  };
});

describe('SimpleApiKeyService', () => {
  let mockSend;
  
  const testUserId = 'test-user-123';
  const testProvider = 'alpaca';
  const testApiKey = 'PKTEST123456789012345678901234567890';
  const testSecret = 'test-secret-key-1234567890123456789012345678901234567890';

  beforeEach(() => {
    // Clear all mocks
    jest.clearAllMocks();
    
    // Get mock send function
    const { __mockSend } = require('@aws-sdk/client-ssm');
    mockSend = __mockSend;
  });

  describe('Constructor', () => {
    test('should initialize with correct defaults', () => {
      expect(simpleApiKeyService.isEnabled).toBe(true);
      expect(simpleApiKeyService.parameterPrefix).toBe('/financial-platform/users');
    });
  });

  describe('storeApiKey', () => {
    test('should store API key successfully', async () => {
      // Mock successful storage
      mockSend.mockResolvedValue({});

      const result = await simpleApiKeyService.storeApiKey(testUserId, testProvider, testApiKey, testSecret);

      expect(result).toBe(true);
      expect(mockSend).toHaveBeenCalledTimes(1);
      
      // Verify the parameter name format
      const putCommand = require('@aws-sdk/client-ssm').PutParameterCommand;
      expect(putCommand).toHaveBeenCalledWith(expect.objectContaining({
        Name: `/financial-platform/users/${testUserId}/${testProvider}`,
        Type: 'SecureString',
        Overwrite: true
      }));
    });

    test('should reject invalid provider', async () => {
      await expect(
        simpleApiKeyService.storeApiKey(testUserId, 'invalid-provider', testApiKey, testSecret)
      ).rejects.toThrow('Invalid provider: invalid-provider');

      expect(mockSend).not.toHaveBeenCalled();
    });

    test('should reject missing parameters', async () => {
      await expect(
        simpleApiKeyService.storeApiKey('', testProvider, testApiKey, testSecret)
      ).rejects.toThrow('Missing required parameters');

      expect(mockSend).not.toHaveBeenCalled();
    });

    test('should handle AWS errors gracefully', async () => {
      const awsError = new Error('AWS service error');
      mockSend.mockRejectedValue(awsError);

      await expect(
        simpleApiKeyService.storeApiKey(testUserId, testProvider, testApiKey, testSecret)
      ).rejects.toThrow('Failed to store API key: AWS service error');
    });
  });

  describe('getApiKey', () => {
    test('should retrieve API key successfully', async () => {
      const mockApiKeyData = {
        keyId: testApiKey,
        secretKey: testSecret,
        provider: testProvider,
        created: '2023-01-01T00:00:00Z',
        version: '1.0'
      };

      mockSend.mockResolvedValue({
        Parameter: {
          Value: JSON.stringify(mockApiKeyData)
        }
      });

      const result = await simpleApiKeyService.getApiKey(testUserId, testProvider);

      expect(result).toEqual(mockApiKeyData);
      expect(mockSend).toHaveBeenCalledTimes(1);

      const getCommand = require('@aws-sdk/client-ssm').GetParameterCommand;
      expect(getCommand).toHaveBeenCalledWith(expect.objectContaining({
        Name: `/financial-platform/users/${testUserId}/${testProvider}`,
        WithDecryption: true
      }));
    });

    test('should return null for non-existent key', async () => {
      const notFoundError = new Error('Parameter not found');
      notFoundError.name = 'ParameterNotFound';
      mockSend.mockRejectedValue(notFoundError);

      const result = await simpleApiKeyService.getApiKey(testUserId, testProvider);

      expect(result).toBeNull();
    });

    test('should handle missing parameters', async () => {
      await expect(
        simpleApiKeyService.getApiKey('', testProvider)
      ).rejects.toThrow('Missing required parameters');
    });
  });

  describe('deleteApiKey', () => {
    test('should delete API key successfully', async () => {
      mockSend.mockResolvedValue({});

      const result = await simpleApiKeyService.deleteApiKey(testUserId, testProvider);

      expect(result).toBe(true);
      expect(mockSend).toHaveBeenCalledTimes(1);

      const deleteCommand = require('@aws-sdk/client-ssm').DeleteParameterCommand;
      expect(deleteCommand).toHaveBeenCalledWith(expect.objectContaining({
        Name: `/financial-platform/users/${testUserId}/${testProvider}`
      }));
    });

    test('should return true for already deleted key', async () => {
      const notFoundError = new Error('Parameter not found');
      notFoundError.name = 'ParameterNotFound';
      mockSend.mockRejectedValue(notFoundError);

      const result = await simpleApiKeyService.deleteApiKey(testUserId, testProvider);

      expect(result).toBe(true);
    });
  });

  describe('listApiKeys', () => {
    test('should list available API keys', async () => {
      // Mock responses for each provider check
      mockSend
        .mockResolvedValueOnce({
          Parameter: {
            Value: JSON.stringify({
              keyId: 'ALPACA123456789',
              secretKey: 'secret123',
              provider: 'alpaca',
              created: '2023-01-01T00:00:00Z',
              version: '1.0'
            })
          }
        })
        .mockRejectedValueOnce({ name: 'ParameterNotFound' }) // polygon not found
        .mockRejectedValueOnce({ name: 'ParameterNotFound' }) // finnhub not found
        .mockRejectedValueOnce({ name: 'ParameterNotFound' }); // iex not found

      const result = await simpleApiKeyService.listApiKeys(testUserId);

      expect(result).toHaveLength(1);
      expect(result[0]).toEqual({
        provider: 'alpaca',
        keyId: 'ALPA***6789', // masked (first 4 + *** + last 4)
        created: '2023-01-01T00:00:00Z',
        hasSecret: true
      });
    });

    test('should return empty array when no keys exist', async () => {
      // Mock all providers as not found
      mockSend.mockRejectedValue({ name: 'ParameterNotFound' });

      const result = await simpleApiKeyService.listApiKeys(testUserId);

      expect(result).toEqual([]);
    });

    test('should handle missing userId', async () => {
      await expect(
        simpleApiKeyService.listApiKeys('')
      ).rejects.toThrow('Missing required parameter: userId');
    });
  });

  describe('Provider validation', () => {
    test('should accept valid providers', async () => {
      const validProviders = ['alpaca', 'polygon', 'finnhub', 'iex'];
      
      for (const provider of validProviders) {
        mockSend.mockResolvedValue({});
        
        const result = await simpleApiKeyService.storeApiKey(testUserId, provider, testApiKey, testSecret);
        expect(result).toBe(true);
      }
    });

    test('should reject invalid providers', async () => {
      const invalidProviders = ['invalid', 'td_ameritrade', 'robinhood'];
      
      for (const provider of invalidProviders) {
        await expect(
          simpleApiKeyService.storeApiKey(testUserId, provider, testApiKey, testSecret)
        ).rejects.toThrow(`Invalid provider: ${provider}`);
      }
    });
  });

  describe('Parameter naming', () => {
    test('should use correct parameter naming convention', async () => {
      mockSend.mockResolvedValue({});

      await simpleApiKeyService.storeApiKey(testUserId, testProvider, testApiKey, testSecret);

      const putCommand = require('@aws-sdk/client-ssm').PutParameterCommand;
      expect(putCommand).toHaveBeenCalledWith(expect.objectContaining({
        Name: `/financial-platform/users/${testUserId}/${testProvider}`
      }));
    });

    test('should normalize provider names to lowercase', async () => {
      mockSend.mockResolvedValue({});

      await simpleApiKeyService.storeApiKey(testUserId, 'ALPACA', testApiKey, testSecret);

      const putCommand = require('@aws-sdk/client-ssm').PutParameterCommand;
      expect(putCommand).toHaveBeenCalledWith(expect.objectContaining({
        Name: `/financial-platform/users/${testUserId}/alpaca`
      }));
    });
  });
});
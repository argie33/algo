const ApiKeyService = require('../../utils/apiKeyService');

// Mock dependencies
jest.mock('../../utils/database');
jest.mock('@aws-sdk/client-secrets-manager');
jest.mock('aws-jwt-verify');

describe('ApiKeyService', () => {
  let apiKeyService;
  
  beforeEach(() => {
    apiKeyService = new ApiKeyService();
    jest.clearAllMocks();
  });

  describe('JWT Token Validation', () => {
    it('should validate JWT tokens successfully', async () => {
      const mockToken = 'valid.jwt.token';
      const mockPayload = {
        sub: 'user-123',
        'cognito:username': 'testuser',
        email: 'test@example.com'
      };

      // Mock successful JWT verification
      apiKeyService.jwtVerifier = {
        verify: jest.fn().mockResolvedValue(mockPayload)
      };

      const result = await apiKeyService.validateJwtToken(mockToken);
      expect(result).toEqual(mockPayload);
      expect(apiKeyService.jwtVerifier.verify).toHaveBeenCalledWith(mockToken);
    });

    it('should handle invalid JWT tokens', async () => {
      const mockToken = 'invalid.jwt.token';
      
      apiKeyService.jwtVerifier = {
        verify: jest.fn().mockRejectedValue(new Error('Invalid token'))
      };

      await expect(apiKeyService.validateJwtToken(mockToken)).rejects.toThrow('Invalid token');
    });

    it('should handle expired JWT tokens', async () => {
      const mockToken = 'expired.jwt.token';
      const expiredError = new Error('Token expired');
      expiredError.name = 'TokenExpiredError';
      
      apiKeyService.jwtVerifier = {
        verify: jest.fn().mockRejectedValue(expiredError)
      };

      await expect(apiKeyService.validateJwtToken(mockToken)).rejects.toThrow('Token expired');
    });
  });

  describe('API Key Encryption/Decryption', () => {
    beforeEach(() => {
      // Mock encryption key
      apiKeyService.encryptionKey = 'test-key-32-characters-long-123';
    });

    it('should encrypt API keys securely', async () => {
      const apiKey = 'test-api-key-12345';
      
      const encrypted = await apiKeyService.encryptApiKey(apiKey);
      
      expect(encrypted).toHaveProperty('encryptedData');
      expect(encrypted).toHaveProperty('iv');
      expect(encrypted).toHaveProperty('authTag');
      expect(encrypted.encryptedData).not.toBe(apiKey);
    });

    it('should decrypt API keys correctly', async () => {
      const apiKey = 'test-api-key-12345';
      
      const encrypted = await apiKeyService.encryptApiKey(apiKey);
      const decrypted = await apiKeyService.decryptApiKey(encrypted);
      
      expect(decrypted).toBe(apiKey);
    });

    it('should handle decryption errors', async () => {
      const invalidEncrypted = {
        encryptedData: 'invalid',
        iv: 'invalid',
        authTag: 'invalid'
      };
      
      await expect(apiKeyService.decryptApiKey(invalidEncrypted)).rejects.toThrow();
    });
  });

  describe('API Key Storage and Retrieval', () => {
    it('should store API keys in database', async () => {
      const userId = 'user-123';
      const apiKeys = {
        alpaca: 'alpaca-key-123',
        polygon: 'polygon-key-456'
      };

      // Mock database query
      const mockQuery = require('../../utils/database').query;
      mockQuery.mockResolvedValue({ rowCount: 1 });

      const result = await apiKeyService.storeApiKeys(userId, apiKeys);
      
      expect(result).toBe(true);
      expect(mockQuery).toHaveBeenCalled();
    });

    it('should retrieve API keys for user', async () => {
      const userId = 'user-123';
      const mockEncryptedKeys = {
        rows: [{
          provider: 'alpaca',
          encrypted_key: JSON.stringify({
            encryptedData: 'encrypted',
            iv: 'iv',
            authTag: 'authTag'
          })
        }]
      };

      const mockQuery = require('../../utils/database').query;
      mockQuery.mockResolvedValue(mockEncryptedKeys);

      // Mock decryption
      apiKeyService.decryptApiKey = jest.fn().mockResolvedValue('decrypted-key');

      const result = await apiKeyService.getApiKeys(userId);
      
      expect(result).toHaveProperty('alpaca', 'decrypted-key');
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('SELECT provider, encrypted_key FROM user_api_keys'),
        [userId]
      );
    });

    it('should handle missing API keys gracefully', async () => {
      const userId = 'user-without-keys';
      
      const mockQuery = require('../../utils/database').query;
      mockQuery.mockResolvedValue({ rows: [] });

      const result = await apiKeyService.getApiKeys(userId);
      
      expect(result).toEqual({});
    });
  });

  describe('Circuit Breaker Pattern', () => {
    it('should track failures and open circuit breaker', async () => {
      const userId = 'user-123';
      
      // Mock database failures
      const mockQuery = require('../../utils/database').query;
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      // Trigger multiple failures to open circuit breaker
      for (let i = 0; i < 6; i++) {
        try {
          await apiKeyService.getApiKeys(userId);
        } catch (error) {
          // Expected to fail
        }
      }

      expect(apiKeyService.circuitBreaker.state).toBe('OPEN');
      expect(apiKeyService.circuitBreaker.failures).toBeGreaterThanOrEqual(5);
    });

    it('should reject requests when circuit breaker is open', async () => {
      const userId = 'user-123';
      
      // Manually set circuit breaker to open
      apiKeyService.circuitBreaker.state = 'OPEN';
      apiKeyService.circuitBreaker.lastFailureTime = Date.now();

      await expect(apiKeyService.getApiKeys(userId)).rejects.toThrow('Circuit breaker is open');
    });

    it('should reset circuit breaker after timeout', async () => {
      const userId = 'user-123';
      
      // Set circuit breaker to open with old timestamp
      apiKeyService.circuitBreaker.state = 'OPEN';
      apiKeyService.circuitBreaker.lastFailureTime = Date.now() - 70000; // 70 seconds ago

      const mockQuery = require('../../utils/database').query;
      mockQuery.mockResolvedValue({ rows: [] });

      const result = await apiKeyService.getApiKeys(userId);
      
      expect(result).toEqual({});
      expect(apiKeyService.circuitBreaker.state).toBe('CLOSED');
    });
  });

  describe('Input Validation', () => {
    it('should validate user ID format', async () => {
      const invalidUserId = null;
      
      await expect(apiKeyService.getApiKeys(invalidUserId)).rejects.toThrow('Invalid user ID');
    });

    it('should validate API key format', async () => {
      const userId = 'user-123';
      const invalidApiKeys = { alpaca: '' };
      
      await expect(apiKeyService.storeApiKeys(userId, invalidApiKeys)).rejects.toThrow();
    });

    it('should validate supported providers', async () => {
      const userId = 'user-123';
      const unsupportedProvider = { unsupported: 'key-123' };
      
      await expect(apiKeyService.storeApiKeys(userId, unsupportedProvider)).rejects.toThrow();
    });
  });

  describe('Cache Management', () => {
    it('should cache API keys to reduce database calls', async () => {
      const userId = 'user-123';
      const mockKeys = { alpaca: 'cached-key' };
      
      // Mock initial database call
      const mockQuery = require('../../utils/database').query;
      mockQuery.mockResolvedValue({
        rows: [{
          provider: 'alpaca',
          encrypted_key: JSON.stringify({
            encryptedData: 'encrypted',
            iv: 'iv',
            authTag: 'authTag'
          })
        }]
      });

      apiKeyService.decryptApiKey = jest.fn().mockResolvedValue('cached-key');

      // First call should hit database
      const result1 = await apiKeyService.getApiKeys(userId);
      expect(mockQuery).toHaveBeenCalledTimes(1);
      
      // Second call should use cache
      const result2 = await apiKeyService.getApiKeys(userId);
      expect(mockQuery).toHaveBeenCalledTimes(1); // No additional database call
      
      expect(result1).toEqual(mockKeys);
      expect(result2).toEqual(mockKeys);
    });

    it('should expire cache after timeout', async () => {
      const userId = 'user-123';
      
      // Set short cache timeout for testing
      apiKeyService.cacheTimeout = 1; // 1ms
      
      const mockQuery = require('../../utils/database').query;
      mockQuery.mockResolvedValue({ rows: [] });

      await apiKeyService.getApiKeys(userId);
      
      // Wait for cache to expire
      await new Promise(resolve => setTimeout(resolve, 10));
      
      await apiKeyService.getApiKeys(userId);
      
      expect(mockQuery).toHaveBeenCalledTimes(2);
    });
  });
});
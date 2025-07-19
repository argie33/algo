/**
 * Real Settings Service Unit Tests
 * Testing the actual settingsService.js with backend API integration and settings management
 * CRITICAL COMPONENT - Handles sensitive API key storage and user settings persistence
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock the api service dependency
const mockApi = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn()
};

vi.mock('../../../services/api', () => ({
  default: mockApi
}));

// Mock localStorage globally before any imports
const mockLocalStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn()
};

// Create a mock that will work in both browser and Node.js environments
Object.defineProperty(globalThis, 'localStorage', {
  value: mockLocalStorage,
  writable: true,
  configurable: true
});

Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage,
  writable: true,
  configurable: true
});

Object.defineProperty(global, 'localStorage', {
  value: mockLocalStorage,
  writable: true,
  configurable: true
});

// Mock via vitest's global mocking
vi.stubGlobal('localStorage', mockLocalStorage);

// Import the REAL SettingsService after mocking dependencies
let settingsService;

describe('⚙️ Real Settings Service', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Mock console methods to avoid noise
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    
    // Reset localStorage mock
    mockLocalStorage.getItem.mockReturnValue(null);
    mockLocalStorage.setItem.mockImplementation(() => {});
    mockLocalStorage.removeItem.mockImplementation(() => {});
    mockLocalStorage.clear.mockImplementation(() => {});
    
    // Dynamically import to get fresh instance
    const settingsServiceModule = await import('../../../services/settingsService');
    settingsService = settingsServiceModule.default;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with correct base URL', () => {
      expect(settingsService.baseUrl).toBe('/api/settings');
    });
  });

  describe('Get API Keys', () => {
    it('should fetch API keys successfully', async () => {
      const mockApiKeys = [
        {
          id: 'key_1',
          provider: 'alpaca',
          masked_api_key: 'PKT...123',
          is_active: true,
          is_sandbox: true,
          validation_status: 'valid',
          last_validated: '2024-01-01T00:00:00Z'
        },
        {
          id: 'key_2',
          provider: 'polygon',
          masked_api_key: 'pol...456',
          is_active: true,
          is_sandbox: false,
          validation_status: 'valid',
          last_validated: '2024-01-01T00:00:00Z'
        }
      ];
      
      mockApi.get.mockResolvedValue({
        data: {
          success: true,
          data: mockApiKeys
        }
      });
      
      const result = await settingsService.getApiKeys();
      
      expect(mockApi.get).toHaveBeenCalledWith('/api/settings/api-keys');
      expect(result).toEqual(mockApiKeys);
      expect(console.log).toHaveBeenCalledWith(
        '✅ Successfully fetched API keys:',
        2,
        'keys'
      );
    });

    it('should throw error when API response is not successful', async () => {
      mockApi.get.mockResolvedValue({
        data: {
          success: false,
          error: 'Authentication failed'
        }
      });
      
      await expect(settingsService.getApiKeys()).rejects.toThrow('Authentication failed');
      expect(console.error).toHaveBeenCalledWith(
        '❌ Error fetching API keys:',
        expect.any(Error)
      );
    });

    it('should return empty array for 404 errors', async () => {
      mockApi.get.mockRejectedValue({
        response: { status: 404 },
        message: 'Not found'
      });
      
      const result = await settingsService.getApiKeys();
      
      expect(result).toEqual([]);
      expect(console.log).toHaveBeenCalledWith(
        '📝 No API keys found or service unavailable, returning empty array'
      );
    });

    it('should return empty array for 422 errors', async () => {
      mockApi.get.mockRejectedValue({
        response: { status: 422 },
        message: 'Unprocessable entity'
      });
      
      const result = await settingsService.getApiKeys();
      
      expect(result).toEqual([]);
    });

    it('should throw error for other HTTP status codes', async () => {
      mockApi.get.mockRejectedValue({
        response: { status: 500 },
        message: 'Internal server error'
      });
      
      await expect(settingsService.getApiKeys()).rejects.toThrow();
    });

    it('should handle network errors', async () => {
      mockApi.get.mockRejectedValue(new Error('Network error'));
      
      await expect(settingsService.getApiKeys()).rejects.toThrow('Network error');
    });
  });

  describe('Add API Key', () => {
    it('should add API key successfully', async () => {
      const apiKeyData = {
        provider: 'alpaca',
        apiKey: 'PK123456',
        apiSecret: 'secret123',
        isSandbox: true,
        description: 'Test API key'
      };
      
      const mockResponse = {
        id: 'new_key_id',
        provider: 'alpaca',
        is_active: true
      };
      
      mockApi.post.mockResolvedValue({
        data: {
          success: true,
          data: mockResponse
        }
      });
      
      const result = await settingsService.addApiKey(apiKeyData);
      
      expect(mockApi.post).toHaveBeenCalledWith('/api/settings/api-keys', {
        provider: 'alpaca',
        apiKey: 'PK123456',
        apiSecret: 'secret123',
        isSandbox: true,
        description: 'Test API key'
      });
      
      expect(result).toEqual(mockResponse);
      expect(console.log).toHaveBeenCalledWith(
        '✅ Successfully added API key:',
        'new_key_id'
      );
    });

    it('should use default description when not provided', async () => {
      const apiKeyData = {
        provider: 'polygon',
        apiKey: 'pol123456',
        apiSecret: 'secret456'
      };
      
      mockApi.post.mockResolvedValue({
        data: {
          success: true,
          data: { id: 'key_id' }
        }
      });
      
      await settingsService.addApiKey(apiKeyData);
      
      expect(mockApi.post).toHaveBeenCalledWith('/api/settings/api-keys', {
        provider: 'polygon',
        apiKey: 'pol123456',
        apiSecret: 'secret456',
        isSandbox: true, // Default value
        description: 'polygon API key' // Default description
      });
    });

    it('should handle API response without success flag', async () => {
      mockApi.post.mockResolvedValue({
        data: {
          success: false,
          error: 'Invalid API key format'
        }
      });
      
      await expect(settingsService.addApiKey({
        provider: 'alpaca',
        apiKey: 'invalid',
        apiSecret: 'invalid'
      })).rejects.toThrow('Invalid API key format');
    });

    it('should handle network errors during addition', async () => {
      mockApi.post.mockRejectedValue(new Error('Connection timeout'));
      
      await expect(settingsService.addApiKey({
        provider: 'alpaca',
        apiKey: 'PK123',
        apiSecret: 'secret'
      })).rejects.toThrow('Connection timeout');
      
      expect(console.error).toHaveBeenCalledWith(
        '❌ Error adding API key:',
        expect.any(Error)
      );
    });
  });

  describe('Update API Key', () => {
    it('should update API key successfully', async () => {
      const keyId = 'key_123';
      const updates = {
        is_active: false,
        description: 'Updated description'
      };
      
      const mockResponse = {
        id: 'key_123',
        provider: 'alpaca',
        is_active: false
      };
      
      mockApi.put.mockResolvedValue({
        data: {
          success: true,
          data: mockResponse
        }
      });
      
      const result = await settingsService.updateApiKey(keyId, updates);
      
      expect(mockApi.put).toHaveBeenCalledWith(
        '/api/settings/api-keys/key_123',
        updates
      );
      
      expect(result).toEqual(mockResponse);
      expect(console.log).toHaveBeenCalledWith(
        '✅ Successfully updated API key:',
        'key_123'
      );
    });

    it('should handle update failures', async () => {
      mockApi.put.mockResolvedValue({
        data: {
          success: false,
          error: 'API key not found'
        }
      });
      
      await expect(settingsService.updateApiKey('nonexistent', {}))
        .rejects.toThrow('API key not found');
    });

    it('should handle network errors during update', async () => {
      mockApi.put.mockRejectedValue(new Error('Update failed'));
      
      await expect(settingsService.updateApiKey('key_123', {}))
        .rejects.toThrow('Update failed');
      
      expect(console.error).toHaveBeenCalledWith(
        '❌ Error updating API key:',
        expect.any(Error)
      );
    });
  });

  describe('Delete API Key', () => {
    it('should delete API key successfully', async () => {
      mockApi.delete.mockResolvedValue({
        data: {
          success: true
        }
      });
      
      const result = await settingsService.deleteApiKey('key_123');
      
      expect(mockApi.delete).toHaveBeenCalledWith('/api/settings/api-keys/key_123');
      expect(result).toBe(true);
      expect(console.log).toHaveBeenCalledWith(
        '✅ Successfully deleted API key:',
        'key_123'
      );
    });

    it('should handle deletion failures', async () => {
      mockApi.delete.mockResolvedValue({
        data: {
          success: false,
          error: 'Cannot delete active API key'
        }
      });
      
      await expect(settingsService.deleteApiKey('key_123'))
        .rejects.toThrow('Cannot delete active API key');
    });

    it('should handle network errors during deletion', async () => {
      mockApi.delete.mockRejectedValue(new Error('Deletion failed'));
      
      await expect(settingsService.deleteApiKey('key_123'))
        .rejects.toThrow('Deletion failed');
      
      expect(console.error).toHaveBeenCalledWith(
        '❌ Error deleting API key:',
        expect.any(Error)
      );
    });
  });

  describe('Validate API Key', () => {
    it('should validate API key successfully', async () => {
      const mockValidationResult = {
        valid: true,
        status: 'connected',
        accountInfo: {
          accountId: 'TEST123',
          accountType: 'paper'
        }
      };
      
      mockApi.post.mockResolvedValue({
        data: {
          success: true,
          data: mockValidationResult
        }
      });
      
      const result = await settingsService.validateApiKey('key_123', 'alpaca');
      
      expect(mockApi.post).toHaveBeenCalledWith(
        '/api/settings/api-keys/key_123/validate',
        { provider: 'alpaca' }
      );
      
      expect(result).toEqual(mockValidationResult);
      expect(console.log).toHaveBeenCalledWith(
        '✅ API key validation result:',
        true
      );
    });

    it('should handle validation failures', async () => {
      mockApi.post.mockResolvedValue({
        data: {
          success: false,
          error: 'Invalid credentials'
        }
      });
      
      await expect(settingsService.validateApiKey('key_123', 'alpaca'))
        .rejects.toThrow('Invalid credentials');
    });

    it('should handle validation errors', async () => {
      mockApi.post.mockRejectedValue(new Error('Validation service unavailable'));
      
      await expect(settingsService.validateApiKey('key_123', 'alpaca'))
        .rejects.toThrow('Validation service unavailable');
      
      expect(console.error).toHaveBeenCalledWith(
        '❌ Error validating API key:',
        expect.any(Error)
      );
    });
  });

  describe('Get Validation Status', () => {
    it('should get validation status for specific provider', async () => {
      const mockStatus = {
        provider: 'alpaca',
        validationStatus: 'valid',
        lastValidated: '2024-01-01T00:00:00Z',
        accountInfo: { accountId: 'TEST123' }
      };
      
      mockApi.get.mockResolvedValue({
        data: {
          success: true,
          data: mockStatus
        }
      });
      
      const result = await settingsService.getValidationStatus('alpaca');
      
      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/settings/api-keys/validation-status?provider=alpaca'
      );
      
      expect(result).toEqual(mockStatus);
    });

    it('should get validation status for all providers', async () => {
      const mockAllStatus = [
        { provider: 'alpaca', validationStatus: 'valid' },
        { provider: 'polygon', validationStatus: 'invalid' }
      ];
      
      mockApi.get.mockResolvedValue({
        data: {
          success: true,
          data: mockAllStatus
        }
      });
      
      const result = await settingsService.getValidationStatus();
      
      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/settings/api-keys/validation-status'
      );
      
      expect(result).toEqual(mockAllStatus);
    });

    it('should return default status on errors', async () => {
      mockApi.get.mockRejectedValue(new Error('Service unavailable'));
      
      const result = await settingsService.getValidationStatus('alpaca');
      
      expect(result).toEqual({
        validationStatus: 'unknown',
        lastValidated: null
      });
      
      expect(console.error).toHaveBeenCalledWith(
        '❌ Error getting validation status:',
        expect.any(Error)
      );
    });
  });

  describe('Validate All API Keys', () => {
    it('should validate all API keys successfully', async () => {
      const mockValidationResults = {
        validationResults: [
          { provider: 'alpaca', valid: true },
          { provider: 'polygon', valid: false }
        ],
        summary: { total: 2, valid: 1, invalid: 1 }
      };
      
      mockApi.post.mockResolvedValue({
        data: {
          success: true,
          data: mockValidationResults
        }
      });
      
      const result = await settingsService.validateAllApiKeys();
      
      expect(mockApi.post).toHaveBeenCalledWith('/api/settings/api-keys/validate-all');
      expect(result).toEqual(mockValidationResults);
      expect(console.log).toHaveBeenCalledWith(
        '✅ Validated all API keys:',
        mockValidationResults.validationResults
      );
    });

    it('should handle validation failures', async () => {
      mockApi.post.mockResolvedValue({
        data: {
          success: false,
          error: 'No API keys to validate'
        }
      });
      
      await expect(settingsService.validateAllApiKeys())
        .rejects.toThrow('No API keys to validate');
    });

    it('should handle validation errors', async () => {
      mockApi.post.mockRejectedValue(new Error('Validation batch failed'));
      
      await expect(settingsService.validateAllApiKeys())
        .rejects.toThrow('Validation batch failed');
      
      expect(console.error).toHaveBeenCalledWith(
        '❌ Error validating all API keys:',
        expect.any(Error)
      );
    });
  });

  describe('Get Provider Credentials', () => {
    it('should get provider credentials successfully', async () => {
      const mockCredentials = {
        provider: 'alpaca',
        apiKey: 'decrypted_key',
        apiSecret: 'decrypted_secret',
        endpoint: 'https://paper-api.alpaca.markets'
      };
      
      mockApi.get.mockResolvedValue({
        data: {
          success: true,
          data: mockCredentials
        }
      });
      
      const result = await settingsService.getProviderCredentials('alpaca');
      
      expect(mockApi.get).toHaveBeenCalledWith('/api/settings/api-keys/alpaca/credentials');
      expect(result).toEqual(mockCredentials);
      expect(console.log).toHaveBeenCalledWith(
        '✅ Got credentials for provider:',
        'alpaca'
      );
    });

    it('should handle credential retrieval failures', async () => {
      mockApi.get.mockResolvedValue({
        data: {
          success: false,
          error: 'Provider not found'
        }
      });
      
      await expect(settingsService.getProviderCredentials('unknown'))
        .rejects.toThrow('Provider not found');
    });

    it('should handle credential retrieval errors', async () => {
      mockApi.get.mockRejectedValue(new Error('Decryption failed'));
      
      await expect(settingsService.getProviderCredentials('alpaca'))
        .rejects.toThrow('Decryption failed');
      
      expect(console.error).toHaveBeenCalledWith(
        '❌ Error getting provider credentials:',
        expect.any(Error)
      );
    });
  });

  describe('Format API Keys for Frontend', () => {
    it('should format backend API keys correctly', () => {
      const backendApiKeys = [
        {
          id: 'key_1',
          provider: 'alpaca',
          masked_api_key: 'PKT...123',
          is_active: true,
          is_sandbox: true,
          validation_status: 'valid',
          last_validated: '2024-01-01T00:00:00Z'
        },
        {
          id: 'key_2',
          provider: 'polygon',
          masked_api_key: 'pol...456',
          is_active: false,
          is_sandbox: false,
          validation_status: 'invalid',
          last_validated: '2024-01-01T00:00:00Z'
        },
        {
          id: 'key_3',
          provider: 'finnhub',
          masked_api_key: 'fin...789',
          is_active: true,
          is_sandbox: false,
          validation_status: 'valid',
          last_validated: '2024-01-01T00:00:00Z'
        }
      ];
      
      const result = settingsService.formatApiKeysForFrontend(backendApiKeys);
      
      expect(result).toEqual({
        alpaca: {
          keyId: 'PKT...123',
          secretKey: '••••••••',
          paperTrading: true,
          enabled: true,
          id: 'key_1',
          validationStatus: 'valid',
          lastValidated: '2024-01-01T00:00:00Z'
        },
        polygon: {
          apiKey: 'pol...456',
          enabled: false,
          id: 'key_2',
          validationStatus: 'invalid',
          lastValidated: '2024-01-01T00:00:00Z'
        },
        finnhub: {
          apiKey: 'fin...789',
          enabled: true,
          id: 'key_3',
          validationStatus: 'valid',
          lastValidated: '2024-01-01T00:00:00Z'
        }
      });
    });

    it('should handle empty backend API keys array', () => {
      const result = settingsService.formatApiKeysForFrontend([]);
      
      expect(result).toEqual({
        alpaca: { keyId: '', secretKey: '', paperTrading: true, enabled: false },
        polygon: { apiKey: '', enabled: false },
        finnhub: { apiKey: '', enabled: false }
      });
    });

    it('should handle null/undefined backend API keys', () => {
      const result1 = settingsService.formatApiKeysForFrontend(null);
      const result2 = settingsService.formatApiKeysForFrontend(undefined);
      
      const expectedDefault = {
        alpaca: { keyId: '', secretKey: '', paperTrading: true, enabled: false },
        polygon: { apiKey: '', enabled: false },
        finnhub: { apiKey: '', enabled: false }
      };
      
      expect(result1).toEqual(expectedDefault);
      expect(result2).toEqual(expectedDefault);
    });

    it('should handle backend API keys with missing fields', () => {
      const incompleteApiKeys = [
        {
          id: 'key_1',
          provider: 'alpaca'
          // Missing other fields
        }
      ];
      
      const result = settingsService.formatApiKeysForFrontend(incompleteApiKeys);
      
      expect(result.alpaca).toEqual({
        keyId: '',
        secretKey: '••••••••',
        paperTrading: true,
        enabled: false,
        id: 'key_1',
        validationStatus: undefined,
        lastValidated: undefined
      });
    });
  });

  describe('Migrate localStorage to Backend', () => {
    it('should migrate localStorage settings successfully', async () => {
      const localStorageSettings = {
        apiKeys: {
          alpaca: {
            keyId: 'PK123456',
            secretKey: 'secret123',
            paperTrading: true
          },
          polygon: {
            apiKey: 'pol123456'
          },
          finnhub: {
            apiKey: 'fin123456'
          }
        }
      };
      
      // Override localStorage.getItem directly in the test
      Object.defineProperty(Storage.prototype, 'getItem', {
        value: vi.fn((key) => {
          if (key === 'app_settings') {
            return JSON.stringify(localStorageSettings);
          }
          return null;
        }),
        writable: true,
        configurable: true
      });
      
      Object.defineProperty(Storage.prototype, 'removeItem', {
        value: vi.fn(),
        writable: true,
        configurable: true
      });
      
      // Mock successful API key additions
      mockApi.post.mockResolvedValue({
        data: {
          success: true,
          data: { id: 'new_key_id' }
        }
      });
      
      const result = await settingsService.migrateLocalStorageToBackend();
      
      expect(mockApi.post).toHaveBeenCalledTimes(3); // Three API keys to migrate
      expect(result.migrated).toBe(true);
      expect(result.keys).toEqual(['alpaca', 'polygon', 'finnhub']);
      expect(localStorage.removeItem).toHaveBeenCalledWith('app_settings');
      expect(result).toEqual({
        migrated: true,
        keys: ['alpaca', 'polygon', 'finnhub']
      });
      
      expect(console.log).toHaveBeenCalledWith(
        '✅ Successfully migrated API keys:',
        ['alpaca', 'polygon', 'finnhub']
      );
    });

    it('should handle no localStorage settings', async () => {
      mockLocalStorage.getItem.mockReturnValue(null);
      
      const result = await settingsService.migrateLocalStorageToBackend();
      
      expect(result).toEqual({
        migrated: false,
        reason: 'no_local_settings'
      });
      
      expect(mockApi.post).not.toHaveBeenCalled();
    });

    it('should handle localStorage settings without API keys', async () => {
      Object.defineProperty(Storage.prototype, 'getItem', {
        value: vi.fn((key) => {
          if (key === 'app_settings') {
            return JSON.stringify({ theme: 'dark' });
          }
          return null;
        }),
        writable: true,
        configurable: true
      });
      
      const result = await settingsService.migrateLocalStorageToBackend();
      
      expect(result).toEqual({
        migrated: false,
        reason: 'no_api_keys'
      });
    });

    it('should handle partial migration failures gracefully', async () => {
      const localStorageSettings = {
        apiKeys: {
          alpaca: {
            keyId: 'PK123456',
            secretKey: 'secret123'
          },
          polygon: {
            apiKey: 'pol123456'
          }
        }
      };
      
      Object.defineProperty(Storage.prototype, 'getItem', {
        value: vi.fn((key) => {
          if (key === 'app_settings') {
            return JSON.stringify(localStorageSettings);
          }
          return null;
        }),
        writable: true,
        configurable: true
      });
      
      Object.defineProperty(Storage.prototype, 'removeItem', {
        value: vi.fn(),
        writable: true,
        configurable: true
      });
      
      // Mock first API key success, second failure
      mockApi.post
        .mockResolvedValueOnce({
          data: { success: true, data: { id: 'key1' } }
        })
        .mockRejectedValueOnce(new Error('Duplicate key'));
      
      const result = await settingsService.migrateLocalStorageToBackend();
      
      expect(result).toEqual({
        migrated: true,
        keys: ['alpaca'] // Only one succeeded
      });
      
      expect(console.warn).toHaveBeenCalledWith(
        '⚠️ Failed to migrate Polygon API key:',
        'Duplicate key'
      );
    });

    it('should handle malformed localStorage data', async () => {
      Object.defineProperty(Storage.prototype, 'getItem', {
        value: vi.fn((key) => {
          if (key === 'app_settings') {
            return 'invalid json';
          }
          return null;
        }),
        writable: true,
        configurable: true
      });
      
      const result = await settingsService.migrateLocalStorageToBackend();
      
      expect(result).toEqual({
        migrated: false,
        reason: 'migration_error',
        error: expect.any(String)
      });
      
      expect(console.error).toHaveBeenCalledWith(
        '❌ Error during localStorage migration:',
        expect.any(Error)
      );
    });

    it('should not clear localStorage if no successful migrations', async () => {
      const localStorageSettings = {
        apiKeys: {
          alpaca: {
            keyId: 'invalid_key'
          }
        }
      };
      
      const mockRemoveItem = vi.fn();
      
      Object.defineProperty(Storage.prototype, 'getItem', {
        value: vi.fn((key) => {
          if (key === 'app_settings') {
            return JSON.stringify(localStorageSettings);
          }
          return null;
        }),
        writable: true,
        configurable: true
      });
      
      Object.defineProperty(Storage.prototype, 'removeItem', {
        value: mockRemoveItem,
        writable: true,
        configurable: true
      });
      
      mockApi.post.mockRejectedValue(new Error('Invalid key format'));
      
      const result = await settingsService.migrateLocalStorageToBackend();
      
      expect(result).toEqual({
        migrated: false,
        reason: 'no_valid_keys'
      });
      
      expect(mockRemoveItem).not.toHaveBeenCalled();
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle concurrent API calls safely', async () => {
      mockApi.get.mockResolvedValue({
        data: { success: true, data: [] }
      });
      
      const promises = [
        settingsService.getApiKeys(),
        settingsService.getValidationStatus(),
        settingsService.getApiKeys()
      ];
      
      const results = await Promise.all(promises);
      
      expect(results).toHaveLength(3);
      expect(mockApi.get).toHaveBeenCalledTimes(3);
    });

    it('should handle malformed API responses gracefully', async () => {
      mockApi.get.mockResolvedValue({
        data: 'invalid response format'
      });
      
      await expect(settingsService.getApiKeys()).rejects.toThrow();
    });

    it('should handle very large API key lists efficiently', async () => {
      const largeApiKeyList = Array.from({ length: 1000 }, (_, i) => ({
        id: `key_${i}`,
        provider: i % 3 === 0 ? 'alpaca' : i % 3 === 1 ? 'polygon' : 'finnhub',
        masked_api_key: `key...${i}`,
        is_active: true
      }));
      
      mockApi.get.mockResolvedValue({
        data: { success: true, data: largeApiKeyList }
      });
      
      const startTime = performance.now();
      const result = await settingsService.getApiKeys();
      const duration = performance.now() - startTime;
      
      expect(duration).toBeLessThan(100); // Should complete within 100ms
      expect(result).toHaveLength(1000);
    });
  });

  describe('Security Considerations', () => {
    it('should never log sensitive API key data', async () => {
      const sensitiveApiKeyData = {
        provider: 'alpaca',
        apiKey: 'SENSITIVE_API_KEY',
        apiSecret: 'SUPER_SECRET_KEY'
      };
      
      mockApi.post.mockResolvedValue({
        data: { success: true, data: { id: 'key_id' } }
      });
      
      await settingsService.addApiKey(sensitiveApiKeyData);
      
      // Verify console methods were not called with sensitive data
      const allConsoleCalls = [
        ...console.log.mock.calls,
        ...console.warn.mock.calls,
        ...console.error.mock.calls
      ].flat();
      
      const hasSensitiveData = allConsoleCalls.some(call => 
        String(call).includes('SENSITIVE_API_KEY') || 
        String(call).includes('SUPER_SECRET_KEY')
      );
      
      expect(hasSensitiveData).toBe(false);
    });

    it('should mask secrets in formatted output', () => {
      const backendApiKeys = [
        {
          id: 'key_1',
          provider: 'alpaca',
          masked_api_key: 'PKT...123',
          is_active: true
        }
      ];
      
      const result = settingsService.formatApiKeysForFrontend(backendApiKeys);
      
      expect(result.alpaca.secretKey).toBe('••••••••');
      expect(result.alpaca.keyId).toBe('PKT...123'); // Should show masked version
    });

    it('should handle authentication errors appropriately', async () => {
      mockApi.get.mockRejectedValue({
        response: { status: 401 },
        message: 'Unauthorized'
      });
      
      await expect(settingsService.getApiKeys()).rejects.toEqual(
        expect.objectContaining({
          response: { status: 401 }
        })
      );
    });
  });
});
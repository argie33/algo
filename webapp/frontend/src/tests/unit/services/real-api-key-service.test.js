/**
 * Real API Key Service Unit Tests
 * Testing the actual apiKeyService.js with API key management, authentication, and credential retrieval
 * CRITICAL COMPONENT - Handles sensitive API credentials and authentication
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock the api service dependency
vi.mock('../../../services/api', () => ({
  getApiConfig: vi.fn(() => ({
    apiUrl: 'https://api.example.com',
    isConfigured: true,
    environment: 'test'
  }))
}));

// Mock fetch globally
global.fetch = vi.fn();

// Mock localStorage and sessionStorage
const mockLocalStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn()
};

const mockSessionStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn()
};

Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage,
  writable: true
});

Object.defineProperty(window, 'sessionStorage', {
  value: mockSessionStorage,
  writable: true
});

// Import the REAL ApiKeyService after mocking dependencies
let apiKeyService;

describe('🔑 Real API Key Service', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Mock successful fetch responses by default
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({
        success: true,
        apiKeys: [
          {
            id: 'key_1',
            provider: 'alpaca',
            isActive: true,
            name: 'Alpaca Production',
            createdAt: '2024-01-01T00:00:00Z'
          },
          {
            id: 'key_2',
            provider: 'td_ameritrade',
            isActive: true,
            name: 'TD Ameritrade Account',
            createdAt: '2024-01-02T00:00:00Z'
          },
          {
            id: 'key_3',
            provider: 'alpaca',
            isActive: false,
            name: 'Alpaca Sandbox',
            createdAt: '2024-01-03T00:00:00Z'
          }
        ]
      })
    });
    
    // Mock localStorage with default auth token
    mockLocalStorage.getItem.mockImplementation((key) => {
      if (key === 'accessToken') return 'test-access-token';
      return null;
    });
    
    // Mock console methods to avoid noise
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    
    // Dynamically import to get fresh instance
    const apiKeyServiceModule = await import('../../../services/apiKeyService');
    apiKeyService = apiKeyServiceModule.default;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with API configuration', () => {
      expect(apiKeyService.apiConfig).toEqual(expect.objectContaining({
        apiUrl: 'https://api.example.com',
        isConfigured: true,
        environment: 'test'
      }));
    });
  });

  describe('Get All API Keys', () => {
    it('should fetch API keys successfully with access token', async () => {
      const result = await apiKeyService.getApiKeys();
      
      expect(global.fetch).toHaveBeenCalledWith(
        'https://api.example.com/api/settings/api-keys',
        expect.objectContaining({
          method: 'GET',
          headers: {
            'Authorization': 'Bearer test-access-token',
            'Content-Type': 'application/json'
          }
        })
      );
      
      expect(result).toHaveLength(3);
      expect(result[0]).toEqual(expect.objectContaining({
        id: 'key_1',
        provider: 'alpaca',
        isActive: true
      }));
    });

    it('should use authToken as fallback when accessToken not available', async () => {
      mockLocalStorage.getItem.mockImplementation((key) => {
        if (key === 'accessToken') return null;
        if (key === 'authToken') return 'test-auth-token';
        return null;
      });
      
      await apiKeyService.getApiKeys();
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer test-auth-token'
          })
        })
      );
    });

    it('should use generic token as final fallback', async () => {
      mockLocalStorage.getItem.mockImplementation((key) => {
        if (key === 'accessToken') return null;
        if (key === 'authToken') return null;
        if (key === 'token') return 'generic-token';
        return null;
      });
      
      await apiKeyService.getApiKeys();
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer generic-token'
          })
        })
      );
    });

    it('should return empty array when API response is not successful', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: false,
          error: 'Failed to fetch API keys'
        })
      });
      
      const result = await apiKeyService.getApiKeys();
      
      expect(result).toEqual([]);
    });

    it('should handle HTTP errors gracefully', async () => {
      global.fetch.mockResolvedValue({
        ok: false,
        status: 500
      });
      
      const result = await apiKeyService.getApiKeys();
      
      expect(result).toEqual([]);
      expect(console.error).toHaveBeenCalledWith(
        'Error fetching API keys:',
        expect.any(Error)
      );
    });

    it('should handle network errors gracefully', async () => {
      global.fetch.mockRejectedValue(new Error('Network error'));
      
      const result = await apiKeyService.getApiKeys();
      
      expect(result).toEqual([]);
      expect(console.error).toHaveBeenCalledWith(
        'Error fetching API keys:',
        expect.any(Error)
      );
    });

    it('should handle malformed JSON responses', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockRejectedValue(new Error('Invalid JSON'))
      });
      
      const result = await apiKeyService.getApiKeys();
      
      expect(result).toEqual([]);
    });
  });

  describe('Get API Key for Provider', () => {
    it('should return active API key for specified provider', async () => {
      const result = await apiKeyService.getApiKeyForProvider('alpaca');
      
      expect(result).toEqual(expect.objectContaining({
        id: 'key_1',
        provider: 'alpaca',
        isActive: true
      }));
    });

    it('should return null when provider has no active keys', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: true,
          apiKeys: [
            {
              id: 'key_3',
              provider: 'alpaca',
              isActive: false
            }
          ]
        })
      });
      
      const result = await apiKeyService.getApiKeyForProvider('alpaca');
      
      expect(result).toBeUndefined();
    });

    it('should return null when provider not found', async () => {
      const result = await apiKeyService.getApiKeyForProvider('unknown_provider');
      
      expect(result).toBeUndefined();
    });

    it('should handle errors gracefully', async () => {
      global.fetch.mockRejectedValue(new Error('API error'));
      
      const result = await apiKeyService.getApiKeyForProvider('alpaca');
      
      // When getApiKeys() fails, it returns [], so find() returns undefined
      expect(result).toBeUndefined();
      expect(console.error).toHaveBeenCalledWith(
        'Error fetching API keys:',
        expect.any(Error)
      );
    });
  });

  describe('Test and Get API Key', () => {
    it('should test API key connection successfully', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: true,
          connection: {
            keyId: 'key_1',
            provider: 'alpaca',
            status: 'connected',
            credentials: {
              apiKey: 'decrypted_key',
              secretKey: 'decrypted_secret'
            }
          }
        })
      });
      
      const result = await apiKeyService.testAndGetApiKey('key_1');
      
      expect(global.fetch).toHaveBeenCalledWith(
        'https://api.example.com/api/settings/test-connection/key_1',
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Authorization': 'Bearer test-access-token',
            'Content-Type': 'application/json'
          }
        })
      );
      
      expect(result).toEqual(expect.objectContaining({
        keyId: 'key_1',
        provider: 'alpaca',
        status: 'connected'
      }));
    });

    it('should return null when connection test fails', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: false,
          error: 'Invalid credentials'
        })
      });
      
      const result = await apiKeyService.testAndGetApiKey('invalid_key');
      
      expect(result).toBeNull();
    });

    it('should handle HTTP errors during connection test', async () => {
      global.fetch.mockResolvedValue({
        ok: false,
        status: 404
      });
      
      const result = await apiKeyService.testAndGetApiKey('nonexistent_key');
      
      expect(result).toBeNull();
      expect(console.error).toHaveBeenCalledWith(
        'Error testing API key connection:',
        expect.any(Error)
      );
    });
  });

  describe('Get Alpaca API Key', () => {
    it('should return active Alpaca API key', async () => {
      const result = await apiKeyService.getAlpacaApiKey();
      
      expect(result).toEqual(expect.objectContaining({
        id: 'key_1',
        provider: 'alpaca',
        isActive: true
      }));
    });

    it('should return null when no active Alpaca key found', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: true,
          apiKeys: []
        })
      });
      
      const result = await apiKeyService.getAlpacaApiKey();
      
      expect(result).toBeNull();
      expect(console.error).toHaveBeenCalledWith(
        'Error getting Alpaca API key:',
        expect.any(Error)
      );
    });

    it('should handle errors during Alpaca key retrieval', async () => {
      global.fetch.mockRejectedValue(new Error('Network error'));
      
      const result = await apiKeyService.getAlpacaApiKey();
      
      expect(result).toBeNull();
    });
  });

  describe('Get TD Ameritrade API Key', () => {
    it('should return active TD Ameritrade API key', async () => {
      const result = await apiKeyService.getTdAmeritradeApiKey();
      
      expect(result).toEqual(expect.objectContaining({
        id: 'key_2',
        provider: 'td_ameritrade',
        isActive: true
      }));
    });

    it('should return null when no active TD Ameritrade key found', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: true,
          apiKeys: [
            {
              id: 'key_1',
              provider: 'alpaca',
              isActive: true
            }
          ]
        })
      });
      
      const result = await apiKeyService.getTdAmeritradeApiKey();
      
      expect(result).toBeNull();
      expect(console.error).toHaveBeenCalledWith(
        'Error getting TD Ameritrade API key:',
        expect.any(Error)
      );
    });
  });

  describe('Check Active API Key', () => {
    it('should return true when provider has active key', async () => {
      const result = await apiKeyService.hasActiveApiKey('alpaca');
      
      expect(result).toBe(true);
    });

    it('should return false when provider has no active key', async () => {
      const result = await apiKeyService.hasActiveApiKey('unknown_provider');
      
      expect(result).toBe(false);
    });

    it('should return false when API call fails', async () => {
      global.fetch.mockRejectedValue(new Error('API error'));
      
      const result = await apiKeyService.hasActiveApiKey('alpaca');
      
      expect(result).toBe(false);
      expect(console.error).toHaveBeenCalledWith(
        'Error fetching API keys:',
        expect.any(Error)
      );
    });
  });

  describe('Get Active Providers', () => {
    it('should return list of active providers', async () => {
      const result = await apiKeyService.getActiveProviders();
      
      expect(result).toEqual(['alpaca', 'td_ameritrade']);
    });

    it('should return empty array when no active providers', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: true,
          apiKeys: [
            {
              id: 'key_1',
              provider: 'alpaca',
              isActive: false
            }
          ]
        })
      });
      
      const result = await apiKeyService.getActiveProviders();
      
      expect(result).toEqual([]);
    });

    it('should handle errors gracefully', async () => {
      global.fetch.mockRejectedValue(new Error('Network error'));
      
      const result = await apiKeyService.getActiveProviders();
      
      expect(result).toEqual([]);
      expect(console.error).toHaveBeenCalledWith(
        'Error fetching API keys:',
        expect.any(Error)
      );
    });
  });

  describe('Get Decrypted Credentials', () => {
    beforeEach(() => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: true,
          credentials: {
            apiKey: 'decrypted_api_key',
            secretKey: 'decrypted_secret_key',
            endpoint: 'https://paper-api.alpaca.markets'
          }
        })
      });
    });

    it('should return decrypted credentials for provider', async () => {
      const result = await apiKeyService.getDecryptedCredentials('alpaca');
      
      expect(global.fetch).toHaveBeenCalledWith(
        'https://api.example.com/api/settings/api-keys/alpaca/credentials',
        expect.objectContaining({
          method: 'GET',
          headers: {
            'Authorization': 'Bearer test-access-token',
            'Content-Type': 'application/json'
          }
        })
      );
      
      expect(result).toEqual({
        apiKey: 'decrypted_api_key',
        secretKey: 'decrypted_secret_key',
        endpoint: 'https://paper-api.alpaca.markets'
      });
    });

    it('should check multiple token storage locations', async () => {
      mockLocalStorage.getItem.mockImplementation((key) => {
        if (key === 'authToken') return null;
        if (key === 'accessToken') return null;
        if (key === 'token') return null;
        return null;
      });
      
      mockSessionStorage.getItem.mockImplementation((key) => {
        if (key === 'authToken') return 'session-auth-token';
        return null;
      });
      
      const result = await apiKeyService.getDecryptedCredentials('alpaca');
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer session-auth-token'
          })
        })
      );
    });

    it('should return null when no authentication token found', async () => {
      mockLocalStorage.getItem.mockReturnValue(null);
      mockSessionStorage.getItem.mockReturnValue(null);
      
      const result = await apiKeyService.getDecryptedCredentials('alpaca');
      
      expect(result).toBeNull();
      expect(console.warn).toHaveBeenCalledWith(
        'No authentication token found - skipping alpaca credential retrieval'
      );
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it('should handle authentication failures gracefully', async () => {
      global.fetch.mockResolvedValue({
        ok: false,
        status: 401
      });
      
      const result = await apiKeyService.getDecryptedCredentials('alpaca');
      
      expect(result).toBeNull();
      expect(console.warn).toHaveBeenCalledWith(
        'Authentication failed for alpaca credentials - user may need to log in'
      );
    });

    it('should handle missing API key gracefully', async () => {
      global.fetch.mockResolvedValue({
        ok: false,
        status: 404
      });
      
      const result = await apiKeyService.getDecryptedCredentials('unknown_provider');
      
      expect(result).toBeNull();
      expect(console.warn).toHaveBeenCalledWith(
        'No active unknown_provider API key found'
      );
    });

    it('should handle server errors', async () => {
      global.fetch.mockResolvedValue({
        ok: false,
        status: 500
      });
      
      const result = await apiKeyService.getDecryptedCredentials('alpaca');
      
      expect(result).toBeNull();
      expect(console.error).toHaveBeenCalledWith(
        'Error getting decrypted credentials for alpaca:',
        expect.any(Error)
      );
    });

    it('should return null when credentials are not successful', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: false,
          error: 'Failed to decrypt credentials'
        })
      });
      
      const result = await apiKeyService.getDecryptedCredentials('alpaca');
      
      expect(result).toBeNull();
    });

    it('should handle non-browser environments gracefully', async () => {
      // Simulate non-browser environment
      const originalWindow = global.window;
      delete global.window;
      
      const result = await apiKeyService.getDecryptedCredentials('alpaca');
      
      expect(result).toBeNull();
      expect(console.warn).toHaveBeenCalledWith(
        'No authentication token found - skipping alpaca credential retrieval'
      );
      
      // Restore window
      global.window = originalWindow;
    });
  });

  describe('Get Alpaca Credentials', () => {
    it('should delegate to getDecryptedCredentials for Alpaca', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: true,
          credentials: {
            apiKey: 'alpaca_key',
            secretKey: 'alpaca_secret'
          }
        })
      });
      
      const result = await apiKeyService.getAlpacaCredentials();
      
      expect(global.fetch).toHaveBeenCalledWith(
        'https://api.example.com/api/settings/api-keys/alpaca/credentials',
        expect.any(Object)
      );
      
      expect(result).toEqual({
        apiKey: 'alpaca_key',
        secretKey: 'alpaca_secret'
      });
    });

    it('should return null when Alpaca credentials not available', async () => {
      global.fetch.mockResolvedValue({
        ok: false,
        status: 404
      });
      
      const result = await apiKeyService.getAlpacaCredentials();
      
      expect(result).toBeNull();
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle network timeouts gracefully', async () => {
      global.fetch.mockRejectedValue(new Error('Request timeout'));
      
      const result = await apiKeyService.getApiKeys();
      
      expect(result).toEqual([]);
      expect(console.error).toHaveBeenCalledWith(
        'Error fetching API keys:',
        expect.any(Error)
      );
    });

    it('should handle malformed response data', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          // Missing success field and malformed structure
          data: 'unexpected format'
        })
      });
      
      const result = await apiKeyService.getApiKeys();
      
      expect(result).toEqual([]);
    });

    it('should handle empty or null provider names', async () => {
      const result1 = await apiKeyService.getApiKeyForProvider(null);
      const result2 = await apiKeyService.getApiKeyForProvider('');
      const result3 = await apiKeyService.getApiKeyForProvider(undefined);
      
      expect(result1).toBeUndefined();
      expect(result2).toBeUndefined();
      expect(result3).toBeUndefined();
    });

    it('should handle concurrent API calls safely', async () => {
      const promises = [
        apiKeyService.getApiKeys(),
        apiKeyService.getAlpacaApiKey(),
        apiKeyService.getTdAmeritradeApiKey(),
        apiKeyService.getActiveProviders()
      ];
      
      const results = await Promise.all(promises);
      
      expect(results).toHaveLength(4);
      expect(global.fetch).toHaveBeenCalledTimes(4);
    });

    it('should handle very large API key lists efficiently', async () => {
      const largeApiKeyList = Array.from({ length: 1000 }, (_, i) => ({
        id: `key_${i}`,
        provider: i % 2 === 0 ? 'alpaca' : 'td_ameritrade',
        isActive: i % 10 === 0, // Every 10th key is active
        name: `Test Key ${i}`
      }));
      
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: true,
          apiKeys: largeApiKeyList
        })
      });
      
      const startTime = performance.now();
      const result = await apiKeyService.getActiveProviders();
      const duration = performance.now() - startTime;
      
      expect(duration).toBeLessThan(100); // Should complete within 100ms
      expect(result).toHaveLength(100); // 100 active keys (every 10th key is active)
    });
  });

  describe('Security Considerations', () => {
    it('should not log sensitive credential data', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          success: true,
          credentials: {
            apiKey: 'SENSITIVE_API_KEY',
            secretKey: 'SUPER_SECRET_KEY'
          }
        })
      });
      
      await apiKeyService.getAlpacaCredentials();
      
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

    it('should handle authorization header correctly', async () => {
      await apiKeyService.getApiKeys();
      
      const fetchCall = global.fetch.mock.calls[0];
      const headers = fetchCall[1].headers;
      
      expect(headers.Authorization).toBe('Bearer test-access-token');
      expect(headers['Content-Type']).toBe('application/json');
    });

    it('should not expose internal API structure in errors', async () => {
      global.fetch.mockRejectedValue(new Error('Internal server details'));
      
      const result = await apiKeyService.getApiKeys();
      
      expect(result).toEqual([]);
      // Error should be logged but not exposed to caller
    });
  });
});
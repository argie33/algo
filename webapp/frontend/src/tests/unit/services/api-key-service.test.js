/**
 * API Key Service Unit Tests - Simplified Version
 * Testing the apiKeyService.js for critical functionality with singleton pattern
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock the API config dependency
const mockApiConfig = {
  apiUrl: 'https://test-api.protrade.com'
};

vi.mock('../../../services/api', () => ({
  getApiConfig: vi.fn(() => mockApiConfig)
}));

// Mock localStorage globally
const mockLocalStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn()
};

Object.defineProperty(global, 'localStorage', {
  value: mockLocalStorage,
  writable: true
});

// Mock fetch globally
global.fetch = vi.fn();

describe('🔐 API Key Service - Simple Tests', () => {
  let getApiKeyService;
  let apiKeyService;

  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Mock console methods
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    
    // Reset localStorage mock
    mockLocalStorage.getItem.mockReturnValue(null);
    
    // Import the service
    const apiKeyServiceModule = await import('../../../services/apiKeyService');
    getApiKeyService = apiKeyServiceModule.default;
    apiKeyService = getApiKeyService();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with null API config', () => {
      expect(apiKeyService.apiConfig).toBeNull();
    });

    it('should lazy initialize API config on first use', () => {
      const config = apiKeyService._getApiConfig();
      expect(config).toEqual(mockApiConfig);
      expect(apiKeyService.apiConfig).toEqual(mockApiConfig);
    });
  });

  describe('Get API Keys - Basic Functionality', () => {
    it('should return empty array when no auth token', async () => {
      mockLocalStorage.getItem.mockReturnValue(null);

      const result = await apiKeyService.getApiKeys();

      expect(result).toEqual([]);
      expect(console.warn).toHaveBeenCalledWith(
        'No authentication token available for API key request'
      );
    });

    it('should make API call when token is available', async () => {
      mockLocalStorage.getItem.mockImplementation((key) => {
        if (key === 'accessToken') return 'valid-token-123';
        return null;
      });

      const mockApiKeys = [
        { id: 'key_1', provider: 'alpaca', isActive: true }
      ];

      fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          apiKeys: mockApiKeys
        })
      });

      const result = await apiKeyService.getApiKeys();
      expect(result).toEqual(mockApiKeys);
    });

    it('should handle API errors gracefully', async () => {
      mockLocalStorage.getItem.mockImplementation((key) => {
        if (key === 'accessToken') return 'valid-token-123';
        return null;
      });

      fetch.mockRejectedValueOnce(new Error('Network error'));

      const result = await apiKeyService.getApiKeys();
      expect(result).toEqual([]);
    });
  });

  describe('Provider-Specific Methods', () => {
    it('should find API key for provider when available', async () => {
      // Mock getApiKeys to return test data
      vi.spyOn(apiKeyService, 'getApiKeys').mockResolvedValue([
        { id: 'key_1', provider: 'alpaca', isActive: true },
        { id: 'key_2', provider: 'polygon', isActive: true }
      ]);

      const result = await apiKeyService.getApiKeyForProvider('alpaca');
      expect(result).toEqual({ id: 'key_1', provider: 'alpaca', isActive: true });
    });

    it('should return undefined when provider not found', async () => {
      vi.spyOn(apiKeyService, 'getApiKeys').mockResolvedValue([
        { id: 'key_1', provider: 'polygon', isActive: true }
      ]);

      const result = await apiKeyService.getApiKeyForProvider('alpaca');
      expect(result).toBeUndefined();
    });

    it('should get Alpaca API key', async () => {
      const mockAlpacaKey = { id: 'alpaca_key', provider: 'alpaca', isActive: true };
      vi.spyOn(apiKeyService, 'getApiKeyForProvider').mockResolvedValue(mockAlpacaKey);

      const result = await apiKeyService.getAlpacaApiKey();
      expect(result).toEqual(mockAlpacaKey);
    });
  });

  describe('Connection Testing', () => {
    it('should return error when no auth token for connection test', async () => {
      mockLocalStorage.getItem.mockReturnValue(null);

      const result = await apiKeyService.testAndGetApiKey('key_123');
      expect(result).toEqual({ success: false, error: 'Authentication required' });
    });

    it('should test API key connection when token available', async () => {
      mockLocalStorage.getItem.mockImplementation((key) => {
        if (key === 'accessToken') return 'valid-token-123';
        return null;
      });

      const mockConnection = {
        success: true,
        provider: 'alpaca'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          connection: mockConnection
        })
      });

      const result = await apiKeyService.testAndGetApiKey('key_123');
      expect(result).toEqual(mockConnection);
    });
  });

  describe('Security and Error Handling', () => {
    it('should handle malformed API responses', async () => {
      mockLocalStorage.getItem.mockImplementation((key) => {
        if (key === 'accessToken') return 'valid-token-123';
        return null;
      });

      fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(null)
      });

      const result = await apiKeyService.getApiKeys();
      expect(result).toEqual([]);
    });

    it('should not log sensitive data', async () => {
      mockLocalStorage.getItem.mockImplementation((key) => {
        if (key === 'accessToken') return 'valid-token-123';
        return null;
      });

      const mockApiKeys = [
        {
          id: 'key_1',
          provider: 'alpaca',
          apiKey: 'SENSITIVE_KEY_123',
          secretKey: 'SECRET_456',
          isActive: true
        }
      ];

      fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          apiKeys: mockApiKeys
        })
      });

      await apiKeyService.getApiKeys();

      // Verify sensitive data is not logged
      expect(console.log).not.toHaveBeenCalledWith(
        expect.stringContaining('SENSITIVE_KEY_123')
      );
      expect(console.log).not.toHaveBeenCalledWith(
        expect.stringContaining('SECRET_456')
      );
    });
  });
});
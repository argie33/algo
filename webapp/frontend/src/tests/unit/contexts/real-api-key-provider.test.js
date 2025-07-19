/**
 * UNIT TESTS: ApiKeyProvider Context
 * Real implementation testing with zero mocks for business logic
 * Comprehensive coverage of API key management, validation, and state synchronization
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { ApiKeyProvider, useApiKeys } from '../../../components/ApiKeyProvider';

// Mock external dependencies only
vi.mock('../../../services/api');
vi.mock('../../../contexts/AuthContext');

const api = await import('../../../services/api');
const { useAuth } = await import('../../../contexts/AuthContext');

describe('ApiKeyProvider Context Unit Tests', () => {
  let mockLocalStorage;
  
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock localStorage
    mockLocalStorage = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn()
    };
    Object.defineProperty(window, 'localStorage', {
      value: mockLocalStorage,
      writable: true
    });
    
    // Mock console methods to reduce noise in tests
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    
    // Default auth context mock
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { sub: 'test-user-123', email: 'test@example.com' }
    });
    
    // Default API mocks
    api.default.get = vi.fn();
    api.default.post = vi.fn();
    api.default.delete = vi.fn();
  });
  
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderApiKeyProvider = (initialProps = {}) => {
    const wrapper = ({ children }) => (
      <ApiKeyProvider {...initialProps}>
        {children}
      </ApiKeyProvider>
    );
    
    return renderHook(() => useApiKeys(), { wrapper });
  };

  describe('Context Initialization', () => {
    it('initializes with correct default state when authenticated', async () => {
      api.default.get.mockResolvedValue({
        data: { success: true, data: [] }
      });

      const { result } = renderApiKeyProvider();

      expect(result.current.isLoading).toBe(true);
      expect(result.current.hasApiKeys).toBe(false);
      expect(result.current.needsOnboarding).toBe(false);
      expect(result.current.error).toBe(null);
      expect(result.current.apiKeys).toEqual({});

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });
    });

    it('throws error when useApiKeys is used outside provider', () => {
      expect(() => {
        renderHook(() => useApiKeys());
      }).toThrow('useApiKeys must be used within an ApiKeyProvider');
    });

    it('resets state when user is not authenticated', async () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null
      });

      const { result } = renderApiKeyProvider();

      expect(result.current.isLoading).toBe(false);
      expect(result.current.hasApiKeys).toBe(false);
      expect(result.current.needsOnboarding).toBe(false);
      expect(result.current.error).toBe(null);
      expect(result.current.apiKeys).toEqual({});
    });
  });

  describe('Backend API Key Loading', () => {
    it('loads API keys from backend successfully', async () => {
      const mockBackendResponse = {
        data: {
          success: true,
          data: [
            {
              provider: 'alpaca',
              masked_api_key: 'PK****ABCD',
              is_active: true,
              validation_status: 'valid',
              created_at: '2024-01-01T00:00:00Z'
            },
            {
              provider: 'td_ameritrade',
              masked_api_key: 'TD****XYZ@AMER.OAUTHAP',
              is_active: true,
              validation_status: 'valid',
              created_at: '2024-01-01T00:00:00Z'
            }
          ]
        }
      };

      api.default.get.mockResolvedValue(mockBackendResponse);

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(api.default.get).toHaveBeenCalledWith('/api/settings/api-keys');
      expect(result.current.hasApiKeys).toBe(true);
      expect(result.current.needsOnboarding).toBe(false);
      expect(Object.keys(result.current.apiKeys)).toHaveLength(2);
      expect(result.current.apiKeys.alpaca).toMatchObject({
        keyId: 'PK****ABCD',
        secretKey: '***masked***',
        isActive: true,
        validationStatus: 'valid',
        fromBackend: true
      });
    });

    it('handles empty backend response correctly', async () => {
      api.default.get.mockResolvedValue({
        data: { success: true, data: [] }
      });

      mockLocalStorage.getItem.mockReturnValue(null);

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasApiKeys).toBe(false);
      expect(result.current.needsOnboarding).toBe(true);
      expect(result.current.apiKeys).toEqual({});
    });

    it('handles backend error and falls back to localStorage', async () => {
      api.default.get.mockRejectedValue(new Error('Backend unavailable'));
      
      mockLocalStorage.getItem
        .mockReturnValueOnce('PKTEST12345678901234567890') // alpaca_key_id
        .mockReturnValueOnce('test_secret_key_1234567890123456789012345') // alpaca_secret_key
        .mockReturnValueOnce(null) // td_ameritrade_key_id
        .mockReturnValueOnce(null); // td_ameritrade_secret_key

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(console.warn).toHaveBeenCalledWith(
        expect.stringContaining('Backend API keys failed'),
        'Backend unavailable'
      );
      expect(result.current.hasApiKeys).toBe(true);
      expect(result.current.apiKeys.alpaca).toMatchObject({
        keyId: 'PKTEST12345678901234567890',
        secretKey: 'test_secret_key_1234567890123456789012345',
        fromBackend: false
      });
    });

    it('handles invalid backend response format', async () => {
      api.default.get.mockResolvedValue({
        data: { success: false, error: 'Invalid request' }
      });

      mockLocalStorage.getItem.mockReturnValue(null);

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasApiKeys).toBe(false);
      expect(result.current.apiKeys).toEqual({});
    });
  });

  describe('LocalStorage Migration', () => {
    it('migrates localStorage keys to backend when backend is empty', async () => {
      // Backend returns empty on first call, then returns migrated keys
      api.default.get
        .mockResolvedValueOnce({ data: { success: true, data: [] } })
        .mockResolvedValueOnce({
          data: {
            success: true,
            data: [{
              provider: 'alpaca',
              masked_api_key: 'PK****ABCD',
              is_active: true,
              validation_status: 'pending'
            }]
          }
        });

      api.default.post.mockResolvedValue({ data: { success: true } });

      mockLocalStorage.getItem
        .mockReturnValueOnce('PKTEST12345678901234567890') // alpaca_key_id
        .mockReturnValueOnce('test_secret_key_1234567890123456789012345') // alpaca_secret_key
        .mockReturnValueOnce(null) // td_ameritrade_key_id
        .mockReturnValueOnce(null); // td_ameritrade_secret_key

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(api.default.post).toHaveBeenCalledWith('/api/settings/api-keys', {
        provider: 'alpaca',
        keyId: 'PKTEST12345678901234567890',
        secretKey: 'test_secret_key_1234567890123456789012345'
      });

      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('alpaca_key_id');
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('alpaca_secret_key');
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('Successfully migrated API keys')
      );
    });

    it('handles migration failure gracefully', async () => {
      api.default.get.mockResolvedValue({ data: { success: true, data: [] } });
      api.default.post.mockRejectedValue(new Error('Migration failed'));

      mockLocalStorage.getItem
        .mockReturnValueOnce('PKTEST12345678901234567890')
        .mockReturnValueOnce('test_secret_key_1234567890123456789012345')
        .mockReturnValueOnce(null)
        .mockReturnValueOnce(null);

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(console.error).toHaveBeenCalledWith(
        expect.stringContaining('Migration from localStorage failed'),
        expect.any(Error)
      );
    });
  });

  describe('API Key Validation', () => {
    it('validates Alpaca API key format correctly', () => {
      const { result } = renderApiKeyProvider();

      // Valid Alpaca keys
      let validation = result.current.validateApiKey(
        'alpaca',
        'PKTEST12345678901234567890',
        'test_secret_key_1234567890123456789012345'
      );
      expect(validation.valid).toBe(true);

      // Invalid key ID format
      validation = result.current.validateApiKey('alpaca', 'invalid-key', 'valid_secret');
      expect(validation.valid).toBe(false);
      expect(validation.error).toContain('Invalid Alpaca Trading API key format');

      // Invalid secret format
      validation = result.current.validateApiKey(
        'alpaca',
        'PKTEST12345678901234567890',
        'short_secret'
      );
      expect(validation.valid).toBe(false);
      expect(validation.error).toContain('Invalid Alpaca Trading API secret format');
    });

    it('validates TD Ameritrade API key format correctly', () => {
      const { result } = renderApiKeyProvider();

      // Valid TD Ameritrade key
      let validation = result.current.validateApiKey(
        'td_ameritrade',
        'TESTCLIENTID@AMER.OAUTHAP'
      );
      expect(validation.valid).toBe(true);

      // Invalid format
      validation = result.current.validateApiKey('td_ameritrade', 'short');
      expect(validation.valid).toBe(false);
      expect(validation.error).toContain('Invalid TD Ameritrade API key format');
    });

    it('handles unknown provider validation', () => {
      const { result } = renderApiKeyProvider();

      const validation = result.current.validateApiKey('unknown_provider', 'any_key');
      expect(validation.valid).toBe(false);
      expect(validation.error).toContain('Unknown provider: unknown_provider');
    });
  });

  describe('API Key Management Operations', () => {
    it('saves API key successfully', async () => {
      api.default.get.mockResolvedValue({ data: { success: true, data: [] } });
      api.default.post.mockResolvedValue({ data: { success: true } });

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        await result.current.saveApiKey(
          'alpaca',
          'PKTEST12345678901234567890',
          'test_secret_key_1234567890123456789012345'
        );
      });

      expect(api.default.post).toHaveBeenCalledWith('/api/settings/api-keys', {
        provider: 'alpaca',
        keyId: 'PKTEST12345678901234567890',
        secretKey: 'test_secret_key_1234567890123456789012345'
      });

      expect(result.current.hasApiKeys).toBe(true);
      expect(result.current.needsOnboarding).toBe(false);
      expect(result.current.apiKeys.alpaca).toMatchObject({
        keyId: 'PKTEST12345678901234567890',
        secretKey: '***masked***',
        isActive: true,
        validationStatus: 'pending',
        fromBackend: true
      });
    });

    it('handles save API key validation failure', async () => {
      api.default.get.mockResolvedValue({ data: { success: true, data: [] } });

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        try {
          await result.current.saveApiKey('alpaca', 'invalid-key', 'invalid-secret');
        } catch (error) {
          expect(error.message).toContain('Invalid Alpaca Trading API key format');
        }
      });

      expect(result.current.error).toContain('Invalid Alpaca Trading API key format');
      expect(api.default.post).not.toHaveBeenCalled();
    });

    it('handles save API key backend failure', async () => {
      api.default.get.mockResolvedValue({ data: { success: true, data: [] } });
      api.default.post.mockRejectedValue(new Error('Backend save failed'));

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        try {
          await result.current.saveApiKey(
            'alpaca',
            'PKTEST12345678901234567890',
            'test_secret_key_1234567890123456789012345'
          );
        } catch (error) {
          expect(error.message).toBe('Backend save failed');
        }
      });

      expect(result.current.error).toBe('Backend save failed');
    });

    it('removes API key successfully', async () => {
      // Set up initial state with API keys
      api.default.get.mockResolvedValue({
        data: {
          success: true,
          data: [{
            provider: 'alpaca',
            masked_api_key: 'PK****ABCD',
            is_active: true,
            validation_status: 'valid'
          }]
        }
      });
      api.default.delete.mockResolvedValue({ data: { success: true } });

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.hasApiKeys).toBe(true);
      });

      await act(async () => {
        await result.current.removeApiKey('alpaca');
      });

      expect(api.default.delete).toHaveBeenCalledWith('/api/settings/api-keys/alpaca');
      expect(result.current.hasApiKeys).toBe(false);
      expect(result.current.needsOnboarding).toBe(true);
      expect(result.current.apiKeys.alpaca).toBeUndefined();
    });

    it('handles remove API key backend failure', async () => {
      api.default.get.mockResolvedValue({
        data: {
          success: true,
          data: [{
            provider: 'alpaca',
            masked_api_key: 'PK****ABCD',
            is_active: true
          }]
        }
      });
      api.default.delete.mockRejectedValue(new Error('Delete failed'));

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.hasApiKeys).toBe(true);
      });

      await act(async () => {
        try {
          await result.current.removeApiKey('alpaca');
        } catch (error) {
          expect(error.message).toBe('Delete failed');
        }
      });

      expect(result.current.error).toBe('Delete failed');
      expect(result.current.hasApiKeys).toBe(true); // Should remain unchanged
    });
  });

  describe('Provider Status Methods', () => {
    it('hasValidProvider returns correct status', async () => {
      api.default.get.mockResolvedValue({
        data: {
          success: true,
          data: [
            {
              provider: 'alpaca',
              masked_api_key: 'PK****ABCD',
              is_active: true,
              validation_status: 'valid'
            },
            {
              provider: 'td_ameritrade',
              masked_api_key: 'TD****XYZ',
              is_active: false,
              validation_status: 'invalid'
            }
          ]
        }
      });

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasValidProvider('alpaca')).toBe(true);
      expect(result.current.hasValidProvider('td_ameritrade')).toBe(false);
      expect(result.current.hasValidProvider('unknown')).toBe(false);
    });

    it('hasAnyValidProvider returns correct status', async () => {
      api.default.get.mockResolvedValue({
        data: {
          success: true,
          data: [{
            provider: 'alpaca',
            masked_api_key: 'PK****ABCD',
            is_active: true,
            validation_status: 'valid'
          }]
        }
      });

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.hasAnyValidProvider()).toBe(true);
      });
    });

    it('getActiveProviders returns correct list', async () => {
      api.default.get.mockResolvedValue({
        data: {
          success: true,
          data: [
            {
              provider: 'alpaca',
              masked_api_key: 'PK****ABCD',
              is_active: true,
              validation_status: 'valid'
            },
            {
              provider: 'td_ameritrade',
              masked_api_key: 'TD****XYZ',
              is_active: true,
              validation_status: 'pending'
            }
          ]
        }
      });

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        const activeProviders = result.current.getActiveProviders();
        expect(activeProviders).toEqual(['alpaca', 'td_ameritrade']);
      });
    });

    it('getApiKey returns correct key object', async () => {
      api.default.get.mockResolvedValue({
        data: {
          success: true,
          data: [{
            provider: 'alpaca',
            masked_api_key: 'PK****ABCD',
            is_active: true,
            validation_status: 'valid'
          }]
        }
      });

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        const alpacaKey = result.current.getApiKey('alpaca');
        expect(alpacaKey).toMatchObject({
          keyId: 'PK****ABCD',
          isActive: true,
          validationStatus: 'valid'
        });
      });
    });
  });

  describe('Onboarding Management', () => {
    it('markOnboardingComplete updates state correctly', async () => {
      api.default.get.mockResolvedValue({ data: { success: true, data: [] } });

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.needsOnboarding).toBe(true);
      });

      act(() => {
        result.current.markOnboardingComplete();
      });

      expect(result.current.needsOnboarding).toBe(false);
      expect(result.current.hasApiKeys).toBe(true);
    });
  });

  describe('Refresh Functionality', () => {
    it('refreshes API keys when called', async () => {
      api.default.get.mockResolvedValue({
        data: {
          success: true,
          data: [{
            provider: 'alpaca',
            masked_api_key: 'PK****ABCD',
            is_active: true
          }]
        }
      });

      const { result } = renderApiKeyProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Clear previous calls
      api.default.get.mockClear();

      await act(async () => {
        await result.current.loadApiKeys();
      });

      expect(api.default.get).toHaveBeenCalledWith('/api/settings/api-keys');
    });
  });

  describe('Authentication State Changes', () => {
    it('reloads API keys when authentication state changes', async () => {
      const { rerender } = renderApiKeyProvider();

      // Change auth state
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { sub: 'different-user', email: 'different@example.com' }
      });

      api.default.get.mockResolvedValue({ data: { success: true, data: [] } });

      rerender();

      await waitFor(() => {
        expect(api.default.get).toHaveBeenCalledWith('/api/settings/api-keys');
      });
    });
  });
});
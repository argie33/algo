/**
 * Unit Tests for ApiKeyProvider Component
 * Tests the API key loading and response parsing logic
 */

import React from 'react';
import { render, waitFor, screen } from '@testing-library/react';
import { vi } from 'vitest';
import ApiKeyProvider, { useApiKeys } from '../../../components/ApiKeyProvider';
import api from '../../../services/api';

// Mock the API service
vi.mock('../../../services/api');

// Mock AuthContext
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    user: { sub: 'test-user-123', email: 'test@example.com' }
  })
}));

// Test component that uses the ApiKeyProvider
const TestComponent = () => {
  const { apiKeys, hasApiKeys, isLoading, needsOnboarding } = useApiKeys();
  
  if (isLoading) return <div>Loading...</div>;
  
  return (
    <div>
      <div data-testid="has-api-keys">{hasApiKeys.toString()}</div>
      <div data-testid="needs-onboarding">{needsOnboarding.toString()}</div>
      <div data-testid="api-keys-count">{Object.keys(apiKeys).length}</div>
    </div>
  );
};

describe('ApiKeyProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Clear localStorage
    localStorage.clear();
    
    // Set up default API mock behavior
    api.get = vi.fn();
  });

  describe('Backend API Response Handling', () => {
    test('should handle correct backend response format', async () => {
      // Mock successful API response with correct format
      const mockResponse = {
        data: {
          success: true,
          data: [
            {
              id: 'alpaca-test-user-123',
              provider: 'alpaca',
              masked_api_key: 'PK***MASKED***123',
              is_active: true,
              validation_status: 'valid',
              created_at: '2024-01-15T10:30:00Z'
            },
            {
              id: 'polygon-test-user-123', 
              provider: 'polygon',
              masked_api_key: 'pk_***MASKED***456',
              is_active: true,
              validation_status: 'valid',
              created_at: '2024-01-16T10:30:00Z'
            }
          ]
        }
      };

      api.get.mockResolvedValue(mockResponse);

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('has-api-keys')).toHaveTextContent('true');
        expect(screen.getByTestId('needs-onboarding')).toHaveTextContent('false');
        expect(screen.getByTestId('api-keys-count')).toHaveTextContent('2');
      });

      expect(api.get).toHaveBeenCalledWith('/api/settings/api-keys');
    });

    test('should handle invalid backend response format and fallback', async () => {
      // Mock backend response with wrong format (using 'apiKeys' instead of 'data')
      const mockResponse = {
        data: {
          success: true,
          apiKeys: [ // Wrong field name - should be 'data'
            {
              provider: 'alpaca',
              masked_api_key: 'PK***MASKED***123',
              is_active: true
            }
          ]
        }
      };

      api.get.mockResolvedValue(mockResponse);

      // Mock console.warn to verify error handling
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('has-api-keys')).toHaveTextContent('false');
        expect(screen.getByTestId('needs-onboarding')).toHaveTextContent('true');
      });

      // Should log the invalid format error
      expect(consoleSpy).toHaveBeenCalledWith(
        '⚠️ Backend API keys failed, checking localStorage:', 
        'Invalid backend response format'
      );

      consoleSpy.mockRestore();
    });

    test('should handle API authentication errors', async () => {
      // Mock 401 authentication error
      const authError = new Error('Authentication required');
      authError.response = { status: 401 };
      api.get.mockRejectedValue(authError);

      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('has-api-keys')).toHaveTextContent('false');
      });

      expect(consoleSpy).toHaveBeenCalledWith(
        '⚠️ Backend API keys failed, checking localStorage:', 
        'Authentication required'
      );

      consoleSpy.mockRestore();
    });

    test('should handle 503 service unavailable errors', async () => {
      // Mock 503 service unavailable error
      const serviceError = new Error('Service Unavailable');
      serviceError.response = { status: 503 };
      api.get.mockRejectedValue(serviceError);

      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('has-api-keys')).toHaveTextContent('false');
      });

      expect(consoleSpy).toHaveBeenCalledWith(
        '⚠️ Backend API keys failed, checking localStorage:', 
        'Service Unavailable'
      );

      consoleSpy.mockRestore();
    });

    test('should transform backend API keys to frontend format correctly', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: [
            {
              provider: 'alpaca',
              masked_api_key: 'PK***MASKED***123',
              is_active: true,
              validation_status: 'valid',
              created_at: '2024-01-15T10:30:00Z'
            }
          ]
        }
      };

      api.get.mockResolvedValue(mockResponse);

      let capturedApiKeys;
      
      const TestCaptureComponent = () => {
        const { apiKeys } = useApiKeys();
        capturedApiKeys = apiKeys;
        return <div>Test</div>;
      };

      render(
        <ApiKeyProvider>
          <TestCaptureComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(capturedApiKeys).toBeDefined();
      });

      // Verify the transformation to frontend format
      expect(capturedApiKeys.alpaca).toEqual({
        keyId: 'PK***MASKED***123',
        secretKey: '***masked***',
        isActive: true,
        validationStatus: 'valid',
        createdAt: '2024-01-15T10:30:00Z',
        fromBackend: true
      });
    });
  });

  describe('LocalStorage Fallback', () => {
    test('should fallback to localStorage when backend fails', async () => {
      // Mock API failure
      api.get.mockRejectedValue(new Error('Network error'));

      // Set up localStorage data
      localStorage.setItem('alpaca_key_id', 'test-key-123');
      localStorage.setItem('alpaca_secret_key', 'test-secret-456');
      localStorage.setItem('alpaca_paper_trading', 'true');

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('has-api-keys')).toHaveTextContent('true');
      });
    });
  });
});
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, test, beforeEach, expect } from 'vitest';
import '@testing-library/jest-dom';
import { ApiKeyProvider, useApiKeys } from '../../../components/ApiKeyProvider';

// Mock localStorage
const mockLocalStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage
});

// Mock API service - use the global mock from setup.js to avoid cycles

// Test component that uses the hook
const TestComponent = () => {
  const { apiKeys, loading, error, setApiKey, removeApiKey, validateApiKeys } = useApiKeys();
  
  return (
    <div>
      <div data-testid="loading">{loading ? 'loading' : 'not loading'}</div>
      <div data-testid="error">{error || 'no error'}</div>
      <div data-testid="api-keys-count">{Object.keys(apiKeys).length}</div>
      <button 
        onClick={() => setApiKey('alpaca', 'test-key-value')}
        data-testid="add-key"
      >
        Add Key
      </button>
      <button 
        onClick={() => validateApiKeys()}
        data-testid="validate-key"
      >
        Validate Key
      </button>
      <button 
        onClick={() => removeApiKey('alpaca')}
        data-testid="delete-key"
      >
        Delete Key
      </button>
    </div>
  );
};

describe('ApiKeyProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocalStorage.getItem.mockReturnValue(null);
  });

  describe('Provider Functionality', () => {
    test('provides API key context to children', async () => {
      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      expect(screen.getByTestId('api-keys-count')).toHaveTextContent('0');
      expect(screen.getByTestId('loading')).toHaveTextContent('not loading');
      expect(screen.getByTestId('error')).toHaveTextContent('no error');
    });

    test('initializes with localStorage data when available', async () => {
      const mockStoredKeys = JSON.stringify({
        alpaca: { keyId: 'stored-key', secret: 'stored-secret' }
      });
      mockLocalStorage.getItem.mockReturnValue(mockStoredKeys);

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('api-keys-count')).toHaveTextContent('1');
      });
    });

    test('handles corrupted localStorage data gracefully', async () => {
      mockLocalStorage.getItem.mockReturnValue('invalid-json');

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      expect(screen.getByTestId('api-keys-count')).toHaveTextContent('0');
      expect(screen.getByTestId('error')).toHaveTextContent('no error');
    });
  });

  describe('API Key Operations', () => {
    test('adds new API key successfully', async () => {
      const { default: api } = await import('../../../services/api');
      api.post.mockResolvedValue({ 
        data: { success: true, message: 'API key added successfully' }
      });

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      fireEvent.click(screen.getByTestId('add-key'));

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith('/api/settings/api-keys', {
          provider: 'alpaca',
          key: 'test-key-value'
        });
      });
    });

    test('handles API key addition error', async () => {
      const { default: api } = await import('../../../services/api');
      api.post.mockRejectedValue(new Error('Network error'));

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      fireEvent.click(screen.getByTestId('add-key'));

      await waitFor(() => {
        expect(screen.getByTestId('error')).not.toHaveTextContent('no error');
      });
    });

    test('validates API key successfully', async () => {
      const { default: api } = await import('../../../services/api');
      api.post.mockResolvedValue({
        data: { success: true, valid: true, message: 'API key is valid' }
      });

      mockLocalStorage.getItem.mockReturnValue(JSON.stringify({
        alpaca: { keyId: 'test-key', secret: 'test-secret' }
      }));

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      fireEvent.click(screen.getByTestId('validate-key'));

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith('/api/settings/api-keys/validate');
      });
    });

    test('deletes API key successfully', async () => {
      const { default: api } = await import('../../../services/api');
      api.delete.mockResolvedValue({
        data: { success: true, message: 'API key deleted successfully' }
      });

      mockLocalStorage.getItem.mockReturnValue(JSON.stringify({
        alpaca: { keyId: 'test-key', secret: 'test-secret' }
      }));

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      fireEvent.click(screen.getByTestId('delete-key'));

      await waitFor(() => {
        expect(api.delete).toHaveBeenCalledWith('/api/settings/api-keys/alpaca');
      });
    });
  });

  describe('Loading States', () => {
    test('shows loading state during API operations', async () => {
      const { default: api } = await import('../../../services/api');
      let resolvePromise;
      const promise = new Promise(resolve => {
        resolvePromise = resolve;
      });
      api.post.mockReturnValue(promise);

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      fireEvent.click(screen.getByTestId('add-key'));

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('loading');
      });

      resolvePromise({ data: { success: true } });

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('not loading');
      });
    });
  });

  describe('Error Handling', () => {
    test('handles network errors gracefully', async () => {
      const { default: api } = await import('../../../services/api');
      api.post.mockRejectedValue(new Error('Network Error'));

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      fireEvent.click(screen.getByTestId('add-key'));

      await waitFor(() => {
        expect(screen.getByTestId('error')).toHaveTextContent('Network Error');
      });
    });

    test('handles API errors with custom messages', async () => {
      const { default: api } = await import('../../../services/api');
      api.post.mockRejectedValue({
        response: {
          data: { message: 'Invalid API key format' }
        }
      });

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      fireEvent.click(screen.getByTestId('add-key'));

      await waitFor(() => {
        expect(screen.getByTestId('error')).toHaveTextContent('Invalid API key format');
      });
    });

    test('clears errors on successful operations', async () => {
      const { default: api } = await import('../../../services/api');
      
      // First, cause an error
      api.post.mockRejectedValueOnce(new Error('Initial error'));
      
      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      fireEvent.click(screen.getByTestId('add-key'));

      await waitFor(() => {
        expect(screen.getByTestId('error')).toHaveTextContent('Initial error');
      });

      // Then, succeed on next operation
      api.post.mockResolvedValueOnce({ data: { success: true } });

      fireEvent.click(screen.getByTestId('add-key'));

      await waitFor(() => {
        expect(screen.getByTestId('error')).toHaveTextContent('no error');
      });
    });
  });

  describe('LocalStorage Integration', () => {
    test('migrates localStorage data to backend on mount', async () => {
      const { default: api } = await import('../../../services/api');
      api.post.mockResolvedValue({ data: { success: true } });
      
      const mockStoredKeys = JSON.stringify({
        alpaca: { keyId: 'local-key', secret: 'local-secret' }
      });
      mockLocalStorage.getItem.mockReturnValue(mockStoredKeys);

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(mockLocalStorage.getItem).toHaveBeenCalledWith('api-keys');
      });
    });

    test('clears localStorage after successful migration', async () => {
      const { default: api } = await import('../../../services/api');
      api.post.mockResolvedValue({ data: { success: true } });
      
      const mockStoredKeys = JSON.stringify({
        alpaca: { keyId: 'local-key', secret: 'local-secret' }
      });
      mockLocalStorage.getItem.mockReturnValue(mockStoredKeys);

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('financial_api_keys');
      });
    });
  });

  describe('Hook Usage Outside Provider', () => {
    test('throws error when hook used outside provider', () => {
      // Suppress console.error for this test
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      expect(() => {
        render(<TestComponent />);
      }).toThrow('useApiKeys must be used within an ApiKeyProvider');

      consoleSpy.mockRestore();
    });
  });
});
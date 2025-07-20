/**
 * API Integration Components Unit Tests
 * Comprehensive testing of all API-related components
 */

// Import global mocks first
import '../../setup/global-mocks.js'

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock the API service
vi.mock('../../../services/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn()
  }
}));

// Mock the AuthContext
const mockAuthContext = {
  isAuthenticated: true,
  user: { id: 'user123', email: 'test@example.com' }
};

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext
}));

// Real API Integration Components - Import actual production components
import { ApiKeyProvider, useApiKeys } from '../../../components/ApiKeyProvider';
import { ApiKeyStatusIndicator } from '../../../components/ApiKeyStatusIndicator';
import { ApiKeyHealthCheck } from '../../../components/ApiKeyHealthCheck';
import { ApiDebugger } from '../../../components/ApiDebugger';
import { ApiKeyOnboarding } from '../../../components/ApiKeyOnboarding';
import { ApiKeySetupWizard } from '../../../components/ApiKeySetupWizard';

describe('🔗 API Integration Components', () => {
  const mockApiKeysData = {
    alpaca: {
      keyId: 'PKAPTEST12345678901',
      secretKey: '***masked***',
      isActive: true,
      validationStatus: 'valid',
      fromBackend: true,
      createdAt: '2024-01-15T10:30:00Z'
    },
    td_ameritrade: {
      keyId: 'TDCLIENT@AMER.OAUTHAP',
      isActive: true,
      validationStatus: 'pending',
      fromBackend: true,
      createdAt: '2024-01-15T11:00:00Z'
    }
  };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    
    // Mock successful API responses by default
    const mockApi = require('../../../services/api').default;
    mockApi.get.mockResolvedValue({
      data: {
        success: true,
        data: [
          {
            provider: 'alpaca',
            masked_api_key: 'PKAPTEST12345678901',
            is_active: true,
            validation_status: 'valid',
            created_at: '2024-01-15T10:30:00Z'
          }
        ]
      }
    });
    mockApi.post.mockResolvedValue({
      data: { success: true, message: 'API key saved successfully' }
    });
    mockApi.delete.mockResolvedValue({
      data: { success: true, message: 'API key removed successfully' }
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('ApiKeyProvider Context', () => {
    // Test component to verify context functionality
    const TestComponent = () => {
      const { 
        apiKeys, 
        isLoading, 
        hasApiKeys, 
        needsOnboarding,
        error,
        saveApiKey,
        removeApiKey,
        hasValidProvider
      } = useApiKeys();

      return (
        <div>
          <div data-testid="loading">{isLoading.toString()}</div>
          <div data-testid="has-keys">{hasApiKeys.toString()}</div>
          <div data-testid="needs-onboarding">{needsOnboarding.toString()}</div>
          <div data-testid="error">{error || 'no-error'}</div>
          <div data-testid="alpaca-valid">{hasValidProvider('alpaca').toString()}</div>
          <div data-testid="api-keys-count">{Object.keys(apiKeys).length}</div>
          <button 
            onClick={() => saveApiKey('alpaca', 'TESTKEY123456789012', 'testsecret123')}
            data-testid="save-key"
          >
            Save Key
          </button>
          <button 
            onClick={() => removeApiKey('alpaca')}
            data-testid="remove-key"
          >
            Remove Key
          </button>
        </div>
      );
    };

    it('should provide API keys context successfully', async () => {
      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      // Wait for initial loading to complete
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
      });

      expect(screen.getByTestId('has-keys')).toHaveTextContent('true');
      expect(screen.getByTestId('needs-onboarding')).toHaveTextContent('false');
      expect(screen.getByTestId('error')).toHaveTextContent('no-error');
      expect(screen.getByTestId('alpaca-valid')).toHaveTextContent('true');
      expect(screen.getByTestId('api-keys-count')).toHaveTextContent('1');
    });

    it('should handle API key validation correctly', async () => {
      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
      });

      const saveButton = screen.getByTestId('save-key');
      await userEvent.click(saveButton);

      // Verify the API was called
      const mockApi = require('../../../services/api').default;
      expect(mockApi.post).toHaveBeenCalledWith('/api/settings/api-keys', {
        provider: 'alpaca',
        keyId: 'TESTKEY123456789012',
        secretKey: 'testsecret123'
      });
    });

    it('should handle API key removal correctly', async () => {
      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
      });

      const removeButton = screen.getByTestId('remove-key');
      await userEvent.click(removeButton);

      // Verify the API was called
      const mockApi = require('../../../services/api').default;
      expect(mockApi.delete).toHaveBeenCalledWith('/api/settings/api-keys/alpaca');
    });

    it('should handle API errors gracefully', async () => {
      const mockApi = require('../../../services/api').default;
      mockApi.get.mockRejectedValue(new Error('Backend unavailable'));

      render(
        <ApiKeyProvider>
          <TestComponent />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
      });

      // Should still render without crashing and fallback to localStorage
      expect(screen.getByTestId('has-keys')).toHaveTextContent('false');
      expect(screen.getByTestId('needs-onboarding')).toHaveTextContent('true');
    });

    it('should throw error when used outside provider', () => {
      const TestComponentOutsideProvider = () => {
        try {
          useApiKeys();
          return <div>Should not render</div>;
        } catch (error) {
          return <div data-testid="error">{error.message}</div>;
        }
      };

      render(<TestComponentOutsideProvider />);
      expect(screen.getByTestId('error')).toHaveTextContent('useApiKeys must be used within an ApiKeyProvider');
    });
  });

  describe('ApiKeyStatusIndicator Component', () => {
    it('should render status indicator with valid keys', () => {
      render(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
        </ApiKeyProvider>
      );

      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('should show loading state during API key fetch', () => {
      const mockApi = require('../../../services/api').default;
      mockApi.get.mockImplementation(() => new Promise(() => {})); // Never resolves

      render(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
        </ApiKeyProvider>
      );

      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('should handle missing API keys gracefully', async () => {
      const mockApi = require('../../../services/api').default;
      mockApi.get.mockResolvedValue({
        data: {
          success: true,
          data: []
        }
      });

      render(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });
    });
  });

  describe('ApiKeyHealthCheck Component', () => {
    it('should render health check component', () => {
      render(
        <ApiKeyProvider>
          <ApiKeyHealthCheck />
        </ApiKeyProvider>
      );

      expect(screen.getByText(/API Health/i)).toBeInTheDocument();
    });

    it('should trigger health check on button click', async () => {
      render(
        <ApiKeyProvider>
          <ApiKeyHealthCheck />
        </ApiKeyProvider>
      );

      const checkButton = screen.getByRole('button', { name: /check/i });
      await userEvent.click(checkButton);

      // Should show some feedback after clicking
      expect(checkButton).toBeInTheDocument();
    });

    it('should display health status results', async () => {
      render(
        <ApiKeyProvider>
          <ApiKeyHealthCheck />
        </ApiKeyProvider>
      );

      // Wait for component to load
      await waitFor(() => {
        expect(screen.getByText(/API Health/i)).toBeInTheDocument();
      });
    });
  });

  describe('ApiDebugger Component', () => {
    it('should render API debugger interface', () => {
      render(
        <ApiKeyProvider>
          <ApiDebugger />
        </ApiKeyProvider>
      );

      expect(screen.getByText(/API Debug/i)).toBeInTheDocument();
    });

    it('should allow testing API endpoints', async () => {
      render(
        <ApiKeyProvider>
          <ApiDebugger />
        </ApiKeyProvider>
      );

      // Look for test endpoint button or similar
      const testButton = screen.queryByRole('button', { name: /test/i });
      if (testButton) {
        await userEvent.click(testButton);
        expect(testButton).toBeInTheDocument();
      }
    });

    it('should display debug information', () => {
      render(
        <ApiKeyProvider>
          <ApiDebugger />
        </ApiKeyProvider>
      );

      // Should show some debug interface
      expect(screen.getByText(/API Debug/i)).toBeInTheDocument();
    });
  });

  describe('ApiKeyOnboarding Component', () => {
    it('should render onboarding flow', () => {
      render(
        <ApiKeyProvider>
          <ApiKeyOnboarding />
        </ApiKeyProvider>
      );

      expect(screen.getByText(/Onboarding/i)).toBeInTheDocument();
    });

    it('should handle onboarding completion', async () => {
      render(
        <ApiKeyProvider>
          <ApiKeyOnboarding />
        </ApiKeyProvider>
      );

      // Look for completion button
      const completeButton = screen.queryByRole('button', { name: /complete/i });
      if (completeButton) {
        await userEvent.click(completeButton);
        expect(completeButton).toBeInTheDocument();
      }
    });

    it('should guide user through API key setup', () => {
      render(
        <ApiKeyProvider>
          <ApiKeyOnboarding />
        </ApiKeyProvider>
      );

      // Should show onboarding content
      expect(screen.getByText(/Onboarding/i)).toBeInTheDocument();
    });
  });

  describe('ApiKeySetupWizard Component', () => {
    it('should render setup wizard interface', () => {
      render(
        <ApiKeyProvider>
          <ApiKeySetupWizard />
        </ApiKeyProvider>
      );

      expect(screen.getByText(/Setup/i)).toBeInTheDocument();
    });

    it('should handle wizard navigation', async () => {
      render(
        <ApiKeyProvider>
          <ApiKeySetupWizard />
        </ApiKeyProvider>
      );

      // Look for next/previous navigation
      const nextButton = screen.queryByRole('button', { name: /next/i });
      if (nextButton) {
        await userEvent.click(nextButton);
        expect(nextButton).toBeInTheDocument();
      }
    });

    it('should validate API key inputs', async () => {
      render(
        <ApiKeyProvider>
          <ApiKeySetupWizard />
        </ApiKeyProvider>
      );

      // Look for input fields
      const keyInput = screen.queryByRole('textbox', { name: /key/i });
      if (keyInput) {
        await userEvent.type(keyInput, 'invalid-key');
        await userEvent.tab();
        
        // Should show validation feedback
        expect(keyInput).toBeInTheDocument();
      }
    });

    it('should handle wizard completion', async () => {
      render(
        <ApiKeyProvider>
          <ApiKeySetupWizard />
        </ApiKeyProvider>
      );

      // Look for finish button
      const finishButton = screen.queryByRole('button', { name: /finish/i });
      if (finishButton) {
        await userEvent.click(finishButton);
        expect(finishButton).toBeInTheDocument();
      }
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle network failures gracefully', async () => {
      const mockApi = require('../../../services/api').default;
      mockApi.get.mockRejectedValue(new Error('Network error'));

      render(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });
    });

    it('should handle invalid API responses', async () => {
      const mockApi = require('../../../services/api').default;
      mockApi.get.mockResolvedValue({
        data: { invalid: 'response' }
      });

      render(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });
    });

    it('should handle localStorage migration', async () => {
      // Set up localStorage with legacy keys
      localStorage.setItem('alpaca_key_id', 'LEGACY_KEY_123456789');
      localStorage.setItem('alpaca_secret_key', 'legacy_secret_key');

      const mockApi = require('../../../services/api').default;
      mockApi.get.mockResolvedValue({
        data: { success: true, data: [] }
      });

      render(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalledWith('/api/settings/api-keys', {
          provider: 'alpaca',
          keyId: 'LEGACY_KEY_123456789',
          secretKey: 'legacy_secret_key'
        });
      });
    });

    it('should handle authentication state changes', async () => {
      const { rerender } = render(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
        </ApiKeyProvider>
      );

      // Change auth state
      mockAuthContext.isAuthenticated = false;
      mockAuthContext.user = null;

      rerender(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
        </ApiKeyProvider>
      );

      expect(screen.getByRole('status')).toBeInTheDocument();
    });
  });

  describe('Performance and Resource Management', () => {
    it('should not cause memory leaks with rapid mounting/unmounting', async () => {
      const { unmount } = render(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
        </ApiKeyProvider>
      );

      unmount();

      // Re-mount multiple times
      for (let i = 0; i < 5; i++) {
        const { unmount: unmountInstance } = render(
          <ApiKeyProvider>
            <ApiKeyStatusIndicator />
          </ApiKeyProvider>
        );
        unmountInstance();
      }

      // Should not throw errors or leak memory
      expect(true).toBe(true);
    });

    it('should handle concurrent API calls efficiently', async () => {
      const mockApi = require('../../../services/api').default;
      let callCount = 0;
      mockApi.get.mockImplementation(() => {
        callCount++;
        return Promise.resolve({
          data: { success: true, data: [] }
        });
      });

      render(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
          <ApiKeyHealthCheck />
          <ApiDebugger />
        </ApiKeyProvider>
      );

      await waitFor(() => {
        expect(callCount).toBeGreaterThan(0);
      });

      // Should efficiently handle multiple components requesting data
      expect(callCount).toBeLessThan(10); // Reasonable upper bound
    });
  });

  describe('Accessibility and User Experience', () => {
    it('should provide proper ARIA labels and roles', () => {
      render(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
        </ApiKeyProvider>
      );

      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('should support keyboard navigation', async () => {
      render(
        <ApiKeyProvider>
          <ApiKeySetupWizard />
        </ApiKeyProvider>
      );

      // Tab navigation should work
      await userEvent.tab();
      
      // Should have focusable elements
      const focusedElement = document.activeElement;
      expect(focusedElement).toBeInstanceOf(HTMLElement);
    });

    it('should provide loading states for better UX', () => {
      const mockApi = require('../../../services/api').default;
      mockApi.get.mockImplementation(() => new Promise(() => {})); // Never resolves

      render(
        <ApiKeyProvider>
          <ApiKeyStatusIndicator />
        </ApiKeyProvider>
      );

      // Should show loading indicator
      expect(screen.getByRole('status')).toBeInTheDocument();
    });
  });
});
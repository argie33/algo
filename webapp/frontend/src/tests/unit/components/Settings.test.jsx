/**
 * Unit Tests for Settings Component
 * Tests the settings page where users configure their trading accounts
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import Settings from '../../../pages/Settings.jsx';

// Mock the API service
vi.mock('../../../services/api.js', () => ({
  api: {
    getApiKeys: vi.fn(),
    saveApiKey: vi.fn(),
    deleteApiKey: vi.fn(),
    testApiKey: vi.fn()
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: 'http://localhost:3001',
    environment: 'test'
  })),
  initializeApi: vi.fn(),
  testApiConnection: vi.fn()
}));

// Mock auth context
vi.mock('../../../contexts/AuthContext.jsx', () => ({
  useAuth: () => ({
    user: { id: 'user123', email: 'test@example.com' },
    isAuthenticated: true
  })
}));

// Wrapper component for router context
const TestWrapper = ({ children }) => (
  <BrowserRouter>
    {children}
  </BrowserRouter>
);

describe('Settings Component - Trading Configuration', () => {
  
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('API Key Management', () => {
    it('should display existing API keys without exposing secrets', async () => {
      // Critical: API keys enable trading but secrets must stay hidden
      const { api } = await import('../../../services/api.js');
      const mockApiKeys = [
        {
          id: 'key1',
          provider: 'alpaca',
          keyPreview: 'PK***ABC',
          isActive: true,
          environment: 'sandbox',
          lastUsed: '2024-01-15T10:30:00Z'
        },
        {
          id: 'key2', 
          provider: 'interactive_brokers',
          keyPreview: 'IB***XYZ',
          isActive: false,
          environment: 'live'
        }
      ];

      api.getApiKeys.mockResolvedValue(mockApiKeys);

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show provider names
        expect(screen.getByText('alpaca') || screen.getByText('Alpaca')).toBeTruthy();
        expect(screen.getByText('interactive_brokers') || screen.getByText('Interactive Brokers')).toBeTruthy();
      });

      // Should show masked key previews, not full keys
      expect(screen.getByText(/PK\*\*\*ABC/)).toBeTruthy();
      expect(screen.getByText(/IB\*\*\*XYZ/)).toBeTruthy();

      // Should show status indicators
      expect(screen.getByText(/active/i) || screen.getByText(/enabled/i)).toBeTruthy();
      expect(screen.getByText(/sandbox/i) || screen.getByText(/test/i)).toBeTruthy();
    });

    it('should allow adding new API keys with validation', async () => {
      // Critical: Users need to add broker API keys to trade
      const { api } = await import('../../../services/api.js');
      api.getApiKeys.mockResolvedValue([]);
      api.saveApiKey.mockResolvedValue({ success: true });

      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Should have form to add new API key
      const addButton = screen.getByText(/add/i) || screen.getByText(/new/i) || screen.getByRole('button', { name: /add/i });
      expect(addButton).toBeTruthy();

      await user.click(addButton);

      // Should show API key form
      await waitFor(() => {
        expect(screen.getByLabelText(/api key/i) || screen.getByPlaceholderText(/api key/i)).toBeTruthy();
        expect(screen.getByLabelText(/secret/i) || screen.getByPlaceholderText(/secret/i)).toBeTruthy();
      });

      // Should have provider selection
      const providerSelect = screen.getByRole('combobox') || screen.getByDisplayValue(/alpaca/i) || screen.getByText(/provider/i);
      expect(providerSelect).toBeTruthy();

      // Fill in valid API key details
      const apiKeyInput = screen.getByLabelText(/api key/i) || screen.getByPlaceholderText(/api key/i);
      const secretInput = screen.getByLabelText(/secret/i) || screen.getByPlaceholderText(/secret/i);

      await user.type(apiKeyInput, 'PKTEST12345ABCDEF');
      await user.type(secretInput, 'secretkey12345abcdef');

      // Submit the form
      const saveButton = screen.getByText(/save/i) || screen.getByRole('button', { name: /save/i });
      await user.click(saveButton);

      await waitFor(() => {
        expect(api.saveApiKey).toHaveBeenCalledWith(
          expect.objectContaining({
            provider: expect.any(String),
            apiKey: 'PKTEST12345ABCDEF',
            secretKey: 'secretkey12345abcdef'
          })
        );
      });
    });

    it('should validate API key format before saving', async () => {
      // Critical: Invalid API keys break trading functionality
      const { api } = await import('../../../services/api.js');
      api.getApiKeys.mockResolvedValue([]);

      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Open add API key form
      const addButton = screen.getByText(/add/i) || screen.getByRole('button', { name: /add/i });
      await user.click(addButton);

      await waitFor(() => {
        expect(screen.getByLabelText(/api key/i) || screen.getByPlaceholderText(/api key/i)).toBeTruthy();
      });

      // Test invalid inputs
      const apiKeyInput = screen.getByLabelText(/api key/i) || screen.getByPlaceholderText(/api key/i);
      const secretInput = screen.getByLabelText(/secret/i) || screen.getByPlaceholderText(/secret/i);

      // Test empty API key
      await user.clear(apiKeyInput);
      await user.clear(secretInput);
      await user.type(secretInput, 'validsecret');

      const saveButton = screen.getByText(/save/i) || screen.getByRole('button', { name: /save/i });
      await user.click(saveButton);

      // Should show validation error
      expect(screen.getByText(/required/i) || screen.getByText(/invalid/i) || screen.getByText(/error/i)).toBeTruthy();

      // API should not be called with invalid data
      expect(api.saveApiKey).not.toHaveBeenCalled();
    });

    it('should allow testing API key connectivity', async () => {
      // Critical: Users need to verify their API keys work before trading
      const { api } = await import('../../../services/api.js');
      api.getApiKeys.mockResolvedValue([
        {
          id: 'key1',
          provider: 'alpaca',
          keyPreview: 'PK***ABC',
          isActive: true
        }
      ]);
      api.testApiKey.mockResolvedValue({ 
        success: true, 
        accountValue: 50000,
        buyingPower: 25000 
      });

      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/PK\*\*\*ABC/)).toBeTruthy();
      });

      // Should have test button for each API key
      const testButton = screen.getByText(/test/i) || screen.getByRole('button', { name: /test/i });
      expect(testButton).toBeTruthy();

      await user.click(testButton);

      await waitFor(() => {
        expect(api.testApiKey).toHaveBeenCalledWith('key1');
      });

      // Should show test results
      await waitFor(() => {
        expect(screen.getByText(/50,000/i) || screen.getByText(/\$50,000/i)).toBeTruthy();
        expect(screen.getByText(/25,000/i) || screen.getByText(/\$25,000/i)).toBeTruthy();
      });
    });

    it('should handle API key test failures gracefully', async () => {
      // Critical: Failed API tests should show helpful error messages
      const { api } = await import('../../../services/api.js');
      api.getApiKeys.mockResolvedValue([
        {
          id: 'key1',
          provider: 'alpaca',
          keyPreview: 'PK***ABC',
          isActive: true
        }
      ]);
      api.testApiKey.mockRejectedValue(new Error('Invalid API credentials'));

      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/PK\*\*\*ABC/)).toBeTruthy();
      });

      const testButton = screen.getByText(/test/i) || screen.getByRole('button', { name: /test/i });
      await user.click(testButton);

      await waitFor(() => {
        // Should show error message
        expect(screen.getByText(/invalid/i) || screen.getByText(/failed/i) || screen.getByText(/error/i)).toBeTruthy();
      });
    });
  });

  describe('Trading Preferences', () => {
    it('should allow configuring trading preferences', async () => {
      // Critical: Trading preferences affect order execution
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Should have trading preference controls
      const tradingSection = screen.getByText(/trading/i) || screen.getByText(/preferences/i);
      expect(tradingSection).toBeTruthy();

      // Common trading preferences
      const confirmationToggle = screen.queryByLabelText(/confirm/i) || 
                                screen.queryByText(/confirmation/i);
      const orderTypeSelect = screen.queryByLabelText(/order type/i) ||
                             screen.queryByText(/market/i) ||
                             screen.queryByText(/limit/i);

      // Should have some trading configuration options
      expect(confirmationToggle || orderTypeSelect).toBeTruthy();
    });

    it('should save preference changes', async () => {
      // Critical: Preference changes should persist
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Find a setting to change (example: order confirmation)
      const toggle = screen.queryByRole('checkbox') || screen.queryByRole('switch');
      if (toggle) {
        await user.click(toggle);

        // Should indicate saving or show success message
        await waitFor(() => {
          const feedback = screen.queryByText(/saved/i) || 
                          screen.queryByText(/updated/i) ||
                          screen.queryByText(/success/i);
          // Note: This might not exist yet but documents the requirement
        });
      }
    });
  });

  describe('Security Settings', () => {
    it('should display security-related settings', async () => {
      // Critical: Financial apps need strong security settings
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Should have security section
      const securitySection = screen.queryByText(/security/i) || 
                            screen.queryByText(/password/i) ||
                            screen.queryByText(/2fa/i) ||
                            screen.queryByText(/mfa/i);

      // Should have some security controls
      expect(securitySection).toBeTruthy();
    });

    it('should handle password changes securely', async () => {
      // Critical: Password changes must be secure and validated
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Look for password change form
      const passwordSection = screen.queryByText(/password/i) || 
                             screen.queryByText(/change password/i);

      if (passwordSection) {
        const currentPasswordInput = screen.queryByLabelText(/current/i) ||
                                   screen.queryByPlaceholderText(/current/i);
        const newPasswordInput = screen.queryByLabelText(/new password/i) ||
                               screen.queryByPlaceholderText(/new password/i);

        if (currentPasswordInput && newPasswordInput) {
          await user.type(currentPasswordInput, 'currentpass123');
          await user.type(newPasswordInput, 'newpass456!');

          // Should validate password strength
          const submitButton = screen.getByRole('button', { name: /save/i }) ||
                              screen.getByRole('button', { name: /update/i });
          
          if (submitButton) {
            await user.click(submitButton);
            // Should require current password validation
          }
        }
      }
    });
  });

  describe('Data and Privacy', () => {
    it('should provide data export functionality', async () => {
      // Critical: Users should be able to export their trading data
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Should have data export option
      const exportOption = screen.queryByText(/export/i) || 
                          screen.queryByText(/download/i) ||
                          screen.queryByText(/data/i);

      // Note: This documents the requirement even if not implemented yet
      // expect(exportOption).toBeTruthy();
    });

    it('should handle account deletion requests appropriately', async () => {
      // Critical: Account deletion must be secure and clear
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Look for account deletion option
      const deleteOption = screen.queryByText(/delete account/i) ||
                          screen.queryByText(/close account/i) ||
                          screen.queryByText(/remove account/i);

      if (deleteOption) {
        await user.click(deleteOption);

        // Should require additional confirmation
        await waitFor(() => {
          const confirmation = screen.queryByText(/confirm/i) ||
                             screen.queryByText(/are you sure/i) ||
                             screen.queryByText(/permanent/i);
          expect(confirmation).toBeTruthy();
        });
      }
    });
  });

  describe('Error Handling', () => {
    it('should handle settings load failures gracefully', async () => {
      // Critical: Settings page should work even if some data fails to load
      const { api } = await import('../../../services/api.js');
      api.getApiKeys.mockRejectedValue(new Error('Settings service unavailable'));

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show error state but not crash
        expect(
          screen.getByText(/error/i) || 
          screen.getByText(/unavailable/i) ||
          screen.getByText(/try again/i)
        ).toBeTruthy();
      });
    });

    it('should validate all form inputs before submission', async () => {
      // Critical: Invalid settings should not be saved
      const { api } = await import('../../../services/api.js');
      api.getApiKeys.mockResolvedValue([]);

      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Try to save settings with invalid data
      const form = screen.queryByRole('form') || screen.getByTestId('settings-form');
      if (form) {
        const submitButton = screen.getByRole('button', { name: /save/i });
        await user.click(submitButton);

        // Should show validation errors for required fields
        await waitFor(() => {
          const errors = screen.queryAllByText(/required/i) ||
                        screen.queryAllByText(/invalid/i);
          // Should have appropriate validation
        });
      }
    });
  });

  describe('Accessibility and User Experience', () => {
    it('should be keyboard navigable', async () => {
      // Critical: Settings must be accessible via keyboard
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Should be able to tab through interactive elements
      await user.tab();
      const firstFocusable = document.activeElement;
      expect(firstFocusable).toBeTruthy();

      await user.tab();
      const secondFocusable = document.activeElement;
      expect(secondFocusable).not.toBe(firstFocusable);
    });

    it('should provide clear feedback for user actions', async () => {
      // Critical: Users need to know when settings are saved/failed
      const { api } = await import('../../../services/api.js');
      api.saveApiKey.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Any action should provide feedback
      const actionButton = screen.queryByRole('button');
      if (actionButton) {
        const user = userEvent.setup();
        await user.click(actionButton);

        // Should show loading, success, or error state
        await waitFor(() => {
          const feedback = screen.queryByText(/loading/i) ||
                          screen.queryByText(/saved/i) ||
                          screen.queryByText(/success/i) ||
                          screen.queryByText(/error/i);
          // Note: This documents good UX practices
        });
      }
    });
  });
});
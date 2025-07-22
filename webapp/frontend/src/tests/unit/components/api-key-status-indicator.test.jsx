import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import ApiKeyStatusIndicator from '../../../components/ApiKeyStatusIndicator';
import * as apiService from '../../../services/api';

// Mock only the API service module
vi.mock('../../../services/api', () => ({
  getApiKeys: vi.fn()
}));

const TestWrapper = ({ children }) => (
  <BrowserRouter>
    {children}
  </BrowserRouter>
);

const renderComponent = (props = {}) => {
  return render(
    <TestWrapper>
      <ApiKeyStatusIndicator {...props} />
    </TestWrapper>
  );
};

describe('ApiKeyStatusIndicator Component - Real Implementation Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering and States', () => {
    test('renders loading state initially', () => {
      apiService.getApiKeys.mockImplementation(() => new Promise(() => {})); // Never resolves
      
      renderComponent();
      
      expect(screen.getByText('Checking API keys...')).toBeInTheDocument();
    });

    test('displays no API keys configured state', async () => {
      apiService.getApiKeys.mockResolvedValueOnce([]);
      
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('No broker API keys configured')).toBeInTheDocument();
        expect(screen.getByText('Setup API Keys')).toBeInTheDocument();
      });
    });

    test('displays connected state with API keys', async () => {
      const mockApiKeys = [
        { provider: 'alpaca', isActive: true, id: '1' },
        { provider: 'polygon', isActive: true, id: '2' }
      ];
      
      apiService.getApiKeys.mockResolvedValueOnce(mockApiKeys);
      
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('2 brokers connected')).toBeInTheDocument();
        expect(screen.getByText('. Live data from: alpaca, polygon')).toBeInTheDocument();
      });
    });

    test('handles API service error gracefully', async () => {
      apiService.getApiKeys.mockRejectedValueOnce(new Error('API Error'));
      
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('Failed to check API keys')).toBeInTheDocument();
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
    });
  });

  describe('Provider-Specific Filtering', () => {
    test('filters keys by specific provider', async () => {
      const mockApiKeys = [
        { provider: 'alpaca', isActive: true, id: '1' },
        { provider: 'polygon', isActive: true, id: '2' },
        { provider: 'alpaca', isActive: false, id: '3' }
      ];
      
      apiService.getApiKeys.mockResolvedValueOnce(mockApiKeys);
      
      renderComponent({ provider: 'alpaca' });
      
      await waitFor(() => {
        expect(screen.getByText('alpaca connected')).toBeInTheDocument();
      });
    });

    test('shows provider-specific missing message', async () => {
      apiService.getApiKeys.mockResolvedValueOnce([
        { provider: 'polygon', isActive: true, id: '1' }
      ]);
      
      renderComponent({ provider: 'alpaca' });
      
      await waitFor(() => {
        expect(screen.getByText('alpaca API key not configured')).toBeInTheDocument();
      });
    });

    test('only shows active API keys', async () => {
      const mockApiKeys = [
        { provider: 'alpaca', isActive: true, id: '1' },
        { provider: 'polygon', isActive: false, id: '2' }
      ];
      
      apiService.getApiKeys.mockResolvedValueOnce(mockApiKeys);
      
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('1 broker connected')).toBeInTheDocument();
        expect(screen.getByText('. Live data from: alpaca')).toBeInTheDocument();
      });
    });
  });

  describe('Status Change Callbacks', () => {
    test('calls onStatusChange with correct data when keys are present', async () => {
      const onStatusChange = vi.fn();
      const mockApiKeys = [
        { provider: 'alpaca', isActive: true, id: '1' },
        { provider: 'polygon', isActive: true, id: '2' }
      ];
      
      apiService.getApiKeys.mockResolvedValueOnce(mockApiKeys);
      
      renderComponent({ onStatusChange });
      
      await waitFor(() => {
        expect(onStatusChange).toHaveBeenCalledWith({
          hasKeys: true,
          keyCount: 2,
          providers: ['alpaca', 'polygon']
        });
      });
    });

    test('calls onStatusChange with correct data when no keys', async () => {
      const onStatusChange = vi.fn();
      
      apiService.getApiKeys.mockResolvedValueOnce([]);
      
      renderComponent({ onStatusChange });
      
      await waitFor(() => {
        expect(onStatusChange).toHaveBeenCalledWith({
          hasKeys: false,
          keyCount: 0,
          providers: []
        });
      });
    });

    test('does not crash when onStatusChange is not provided', async () => {
      apiService.getApiKeys.mockResolvedValueOnce([
        { provider: 'alpaca', isActive: true, id: '1' }
      ]);
      
      expect(() => {
        renderComponent();
      }).not.toThrow();
    });
  });

  describe('Compact Mode', () => {
    test('renders compact version with chip', async () => {
      const mockApiKeys = [
        { provider: 'alpaca', isActive: true, id: '1' }
      ];
      
      apiService.getApiKeys.mockResolvedValueOnce(mockApiKeys);
      
      renderComponent({ compact: true });
      
      await waitFor(() => {
        expect(screen.getByText('1 connected')).toBeInTheDocument();
        // Should not show the full Alert component in compact mode
        expect(screen.queryByText('Setup API Keys')).not.toBeInTheDocument();
      });
    });

    test('shows settings button in compact mode when no keys', async () => {
      apiService.getApiKeys.mockResolvedValueOnce([]);
      
      renderComponent({ compact: true });
      
      await waitFor(() => {
        expect(screen.getByText('No API keys')).toBeInTheDocument();
        expect(screen.getByRole('button')).toBeInTheDocument();
      });
    });
  });

  describe('Setup Dialog Functionality', () => {
    test('opens setup dialog when Setup API Keys button is clicked', async () => {
      apiService.getApiKeys.mockResolvedValueOnce([]);
      
      renderComponent({ showSetupDialog: true });
      
      await waitFor(() => {
        fireEvent.click(screen.getByText('Setup API Keys'));
      });
      
      expect(screen.getByText('Setup Broker API Keys')).toBeInTheDocument();
      expect(screen.getByText('Supported Brokers:')).toBeInTheDocument();
      expect(screen.getByText('• Alpaca (Paper & Live Trading)')).toBeInTheDocument();
    });

    test('closes setup dialog when Use Demo Data is clicked', async () => {
      apiService.getApiKeys.mockResolvedValueOnce([]);
      
      renderComponent({ showSetupDialog: true });
      
      await waitFor(() => {
        fireEvent.click(screen.getByText('Setup API Keys'));
      });
      
      fireEvent.click(screen.getByText('Use Demo Data'));
      
      await waitFor(() => {
        expect(screen.queryByText('Setup Broker API Keys')).not.toBeInTheDocument();
      });
    });

    test('bypasses dialog when showSetupDialog is false', async () => {
      apiService.getApiKeys.mockResolvedValueOnce([]);
      
      renderComponent({ showSetupDialog: false });
      
      await waitFor(() => {
        expect(screen.getByText('Setup API Keys')).toBeInTheDocument();
      });
      
      // Should not show dialog - would navigate directly (but we can't test navigation easily)
      fireEvent.click(screen.getByText('Setup API Keys'));
      expect(screen.queryByText('Setup Broker API Keys')).not.toBeInTheDocument();
    });
  });

  describe('Retry Functionality', () => {
    test('allows retry after error', async () => {
      // First call fails
      apiService.getApiKeys.mockRejectedValueOnce(new Error('Network Error'));
      
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('Failed to check API keys')).toBeInTheDocument();
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
      
      // Second call succeeds
      apiService.getApiKeys.mockResolvedValueOnce([
        { provider: 'alpaca', isActive: true, id: '1' }
      ]);
      
      fireEvent.click(screen.getByText('Retry'));
      
      await waitFor(() => {
        expect(screen.getByText('1 broker connected')).toBeInTheDocument();
      });
      
      expect(apiService.getApiKeys).toHaveBeenCalledTimes(2);
    });

    test('shows loading state during retry', async () => {
      apiService.getApiKeys.mockRejectedValueOnce(new Error('Error'));
      
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
      
      // Make retry hang to test loading state
      apiService.getApiKeys.mockImplementation(() => new Promise(() => {}));
      
      fireEvent.click(screen.getByText('Retry'));
      
      await waitFor(() => {
        expect(screen.getByText('Checking API keys...')).toBeInTheDocument();
      });
    });
  });

  describe('Component Lifecycle', () => {
    test('triggers API check on mount', () => {
      apiService.getApiKeys.mockResolvedValueOnce([]);
      
      renderComponent();
      
      expect(apiService.getApiKeys).toHaveBeenCalledTimes(1);
    });

    test('updates when provider prop changes', async () => {
      const mockApiKeys = [
        { provider: 'alpaca', isActive: true, id: '1' },
        { provider: 'polygon', isActive: true, id: '2' }
      ];
      
      apiService.getApiKeys.mockResolvedValue(mockApiKeys);
      
      const { rerender } = renderComponent({ provider: 'alpaca' });
      
      await waitFor(() => {
        expect(screen.getByText('alpaca connected')).toBeInTheDocument();
      });
      
      // Change provider
      rerender(
        <TestWrapper>
          <ApiKeyStatusIndicator provider="polygon" />
        </TestWrapper>
      );
      
      await waitFor(() => {
        expect(screen.getByText('polygon connected')).toBeInTheDocument();
      });
      
      // Should have called getApiKeys twice - once for each provider
      expect(apiService.getApiKeys).toHaveBeenCalledTimes(2);
    });
  });

  describe('Demo Data Notice', () => {
    test('shows demo data notice when no API keys configured', async () => {
      apiService.getApiKeys.mockResolvedValueOnce([]);
      
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText(/Portfolio data will use demo\/mock data/)).toBeInTheDocument();
      });
    });

    test('shows live data sources when API keys are configured', async () => {
      const mockApiKeys = [
        { provider: 'alpaca', isActive: true, id: '1' },
        { provider: 'polygon', isActive: true, id: '2' }
      ];
      
      apiService.getApiKeys.mockResolvedValueOnce(mockApiKeys);
      
      renderComponent();
      
      await waitFor(() => {
        expect(screen.getByText('. Live data from: alpaca, polygon')).toBeInTheDocument();
      });
    });
  });

  describe('Security Information', () => {
    test('displays security information in setup dialog', async () => {
      apiService.getApiKeys.mockResolvedValueOnce([]);
      
      renderComponent({ showSetupDialog: true });
      
      await waitFor(() => {
        fireEvent.click(screen.getByText('Setup API Keys'));
      });
      
      expect(screen.getByText('Security:')).toBeInTheDocument();
      expect(screen.getByText(/Your API keys are encrypted with AES-256-GCM/)).toBeInTheDocument();
      expect(screen.getByText(/We never store your credentials in plaintext/)).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    test('provides tooltips in compact mode', async () => {
      apiService.getApiKeys.mockResolvedValueOnce([]);
      
      renderComponent({ compact: true });
      
      await waitFor(() => {
        const chipElement = screen.getByText('No API keys').closest('[data-testid], [title]');
        expect(chipElement).toBeInTheDocument();
      });
    });

    test('setup dialog is properly labeled', async () => {
      apiService.getApiKeys.mockResolvedValueOnce([]);
      
      renderComponent({ showSetupDialog: true });
      
      await waitFor(() => {
        fireEvent.click(screen.getByText('Setup API Keys'));
      });
      
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText('Setup Broker API Keys')).toBeInTheDocument();
    });
  });
});


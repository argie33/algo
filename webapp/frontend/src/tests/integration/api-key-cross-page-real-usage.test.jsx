/**
 * Cross-Page API Key Integration Tests - HIGH PRIORITY #6
 * Tests how API keys actually work across different pages in the site
 */
import React from 'react';
import { describe it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import muiTheme from '../../theme/muiTheme';

// Import actual pages that use API keys
import Dashboard from '../../pages/Dashboard';
import Portfolio from '../../pages/Portfolio';
import Settings from '../../pages/Settings';
import RequiresApiKeys from '../../components/RequiresApiKeys';

// Mock AuthContext
const mockAuthContext = {
  user: { sub: 'user-123', email: 'test@example.com' },
  isAuthenticated: true,
  isLoading: false,
  tokens: { accessToken: 'mock-token' }
};

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext
}));

// Mock API services
const mockApiService = {
  // Portfolio page functions
  getPortfolioData: vi.fn(),
  importPortfolioFromBroker: vi.fn(),
  getAvailableAccounts: vi.fn(),
  
  // Dashboard functions
  getStockPrices: vi.fn(),
  getStockMetrics: vi.fn(),
  getBuySignals: vi.fn(),
  getSellSignals: vi.fn(),
  
  // Settings functions
  getApiKeys: vi.fn(),
  testApiConnection: vi.fn(),
  
  // Shared functions
  getApiConfig: vi.fn().mockReturnValue({ apiUrl: 'http://localhost:3001' })
};

vi.mock('../../services/api', () => ({
  default: mockApiService,
  ...mockApiService
}));

// Mock RequiresApiKeys behavior
const MockRequiresApiKeys = ({ children, requiredProviders, fallbackContent }) => {
  const [hasApiKeys, setHasApiKeys] = React.useState(false);
  
  React.useEffect(() => {
    // Simulate checking for API keys
    mockApiService.getApiKeys().then(keys => {
      setHasApiKeys(keys && keys.length > 0);
    });
  }, []);

  if (!hasApiKeys && fallbackContent) {
    return fallbackContent;
  }
  
  if (!hasApiKeys) {
    return (
      <div data-testid="api-keys-required">
        API Keys Required for {requiredProviders?.join(', ')}
        <button onClick={() => setHasApiKeys(true)}>Setup API Keys</button>
      </div>
    );
  }
  
  return children;
};

vi.mock('../../components/RequiresApiKeys', () => ({
  default: MockRequiresApiKeys
}));

// Test wrapper component
const TestWrapper = ({ children }) => (
  <BrowserRouter>
    <ThemeProvider theme={muiTheme}>
      {children}
    </ThemeProvider>
  </BrowserRouter>
);

describe('Cross-Page API Key Integration - Real Site Behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Settings → Portfolio Flow (Real User Journey)', () => {
    test('should allow user to add API keys in Settings then use them in Portfolio', async () => {
      // Step 1: User goes to Settings with no API keys
      mockApiService.getApiKeys.mockResolvedValueOnce([]);
      
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Should show empty API keys list
      await waitFor(() => {
        expect(screen.getByText(/no api keys/i)).toBeInTheDocument();
      });

      // Step 2: User adds Alpaca API key
      const addButton = screen.getByText(/add api key/i);
      fireEvent.click(addButton);

      // Fill in API key form (simulate real user input)
      const apiKeyInput = screen.getByLabelText(/api key/i);
      const secretInput = screen.getByLabelText(/secret/i);
      
      fireEvent.change(apiKeyInput, { target: { value: 'PKTEST1234567890123456' } });
      fireEvent.change(secretInput, { target: { value: 'test-secret-1234567890' } });
      
      // Mock successful API key save
      mockApiService.testApiConnection.mockResolvedValue({ success: true });
      
      const saveButton = screen.getByText(/save/i);
      fireEvent.click(saveButton);

      // Step 3: Navigate to Portfolio page (API keys now available)
      mockApiService.getApiKeys.mockResolvedValue([
        { provider: 'alpaca', keyId: 'PKTE***3456', status: 'active' }
      ]);

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Should now show portfolio data from Alpaca
      await waitFor(() => {
        expect(mockApiService.getPortfolioData).toHaveBeenCalled();
        expect(mockApiService.importPortfolioFromBroker).toHaveBeenCalledWith({ source: 'alpaca' });
      });
    });
  });

  describe('Dashboard Real-Time Data (API Key Dependent)', () => {
    test('should show live stock data when API keys are configured', async () => {
      // Mock API keys exist
      mockApiService.getApiKeys.mockResolvedValue([
        { provider: 'alpaca', status: 'active' }
      ]);

      // Mock live market data
      mockApiService.getStockPrices.mockResolvedValue({
        AAPL: { price: 150.25, change: 2.50 },
        GOOGL: { price: 2650.00, change: -15.75 }
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should fetch and display live stock prices
      await waitFor(() => {
        expect(mockApiService.getStockPrices).toHaveBeenCalled();
        expect(screen.getByText(/150.25/)).toBeInTheDocument();
        expect(screen.getByText(/2650.00/)).toBeInTheDocument();
      });
    });

    test('should show demo mode when no API keys configured', async () => {
      // Mock no API keys
      mockApiService.getApiKeys.mockResolvedValue([]);

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should show demo data instead
      await waitFor(() => {
        expect(screen.getByText(/demo mode/i)).toBeInTheDocument();
        expect(mockApiService.getStockPrices).not.toHaveBeenCalled();
      });
    });
  });

  describe('RequiresApiKeys Component (Page Protection)', () => {
    test('should guard Portfolio page when no API keys exist', async () => {
      mockApiService.getApiKeys.mockResolvedValue([]);

      render(
        <TestWrapper>
          <RequiresApiKeys requiredProviders={['alpaca']}>
            <div data-testid="portfolio-content">Portfolio Data</div>
          </RequiresApiKeys>
        </TestWrapper>
      );

      // Should show API keys required message instead of portfolio
      await waitFor(() => {
        expect(screen.getByTestId('api-keys-required')).toBeInTheDocument();
        expect(screen.queryByTestId('portfolio-content')).not.toBeInTheDocument();
      });
    });

    test('should allow access to Portfolio page when API keys exist', async () => {
      mockApiService.getApiKeys.mockResolvedValue([
        { provider: 'alpaca', status: 'active' }
      ]);

      render(
        <TestWrapper>
          <RequiresApiKeys requiredProviders={['alpaca']}>
            <div data-testid="portfolio-content">Portfolio Data</div>
          </RequiresApiKeys>
        </TestWrapper>
      );

      // Should show actual portfolio content
      await waitFor(() => {
        expect(screen.getByTestId('portfolio-content')).toBeInTheDocument();
        expect(screen.queryByTestId('api-keys-required')).not.toBeInTheDocument();
      });
    });

    test('should redirect to Settings when user clicks Setup API Keys', async () => {
      mockApiService.getApiKeys.mockResolvedValue([]);
      
      const mockNavigate = vi.fn();
      vi.mock('react-router-dom', async () => {
        const actual = await vi.importActual('react-router-dom');
        return {
          ...actual,
          useNavigate: () => mockNavigate
        };
      });

      render(
        <TestWrapper>
          <RequiresApiKeys requiredProviders={['alpaca']}>
            <div>Protected Content</div>
          </RequiresApiKeys>
        </TestWrapper>
      );

      const setupButton = screen.getByText(/setup api keys/i);
      fireEvent.click(setupButton);

      // Should trigger navigation to settings
      expect(mockNavigate).toHaveBeenCalledWith('/settings');
    });
  });

  describe('API Key Status Synchronization', () => {
    test('should update all pages when API key status changes', async () => {
      // Start with no API keys
      mockApiService.getApiKeys.mockResolvedValue([]);

      const { rerender } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should show demo mode
      await waitFor(() => {
        expect(screen.getByText(/demo mode/i)).toBeInTheDocument();
      });

      // Simulate API key being added (user completed Settings flow)
      mockApiService.getApiKeys.mockResolvedValue([
        { provider: 'alpaca', status: 'active' }
      ]);

      // Re-render Dashboard
      rerender(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should now show live data
      await waitFor(() => {
        expect(screen.queryByText(/demo mode/i)).not.toBeInTheDocument();
        expect(mockApiService.getStockPrices).toHaveBeenCalled();
      });
    });

    test('should handle API key failures gracefully across pages', async () => {
      mockApiService.getApiKeys.mockResolvedValue([
        { provider: 'alpaca', status: 'error' }
      ]);

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Should show error state and fallback to demo data
      await waitFor(() => {
        expect(screen.getByText(/api connection error/i)).toBeInTheDocument();
        expect(screen.getByText(/using demo data/i)).toBeInTheDocument();
      });
    });
  });

  describe('Live Data Flow Integration', () => {
    test('should maintain real-time updates across Portfolio and Dashboard', async () => {
      mockApiService.getApiKeys.mockResolvedValue([
        { provider: 'alpaca', status: 'active' }
      ]);

      // Mock WebSocket-like live data updates
      const mockLiveData = {
        AAPL: { price: 151.00, timestamp: Date.now() },
        GOOGL: { price: 2655.50, timestamp: Date.now() }
      };

      mockApiService.getStockPrices.mockResolvedValue(mockLiveData);

      // Render both Dashboard and Portfolio
      const { container } = render(
        <TestWrapper>
          <div>
            <Dashboard />
            <Portfolio />
          </div>
        </TestWrapper>
      );

      // Both should receive the same live data
      await waitFor(() => {
        expect(mockApiService.getStockPrices).toHaveBeenCalledTimes(2);
        const priceElements = container.querySelectorAll('[data-testid*="price"]');
        expect(priceElements.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Error Recovery Flow', () => {
    test('should handle API key service outage across all pages', async () => {
      // Simulate service outage
      mockApiService.getApiKeys.mockRejectedValue(new Error('Service unavailable'));

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Should show service error message
      await waitFor(() => {
        expect(screen.getByText(/service temporarily unavailable/i)).toBeInTheDocument();
      });

      // Should offer retry option
      const retryButton = screen.getByText(/retry/i);
      fireEvent.click(retryButton);

      expect(mockApiService.getApiKeys).toHaveBeenCalledTimes(2);
    });
  });
});
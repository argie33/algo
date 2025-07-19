/**
 * React Components Unit Tests
 * Comprehensive testing for UI components, hooks, and user interactions
 */

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock external dependencies
const mockApiService = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn()
};

vi.mock('../../services/api', () => ({
  default: mockApiService
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  AreaChart: ({ children }) => <div data-testid="area-chart">{children}</div>,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  Area: () => <div data-testid="area" />,
  Cell: () => <div data-testid="cell" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />
}));

// Mock MUI components that might cause issues
vi.mock('@mui/material', () => ({
  ThemeProvider: ({ children }) => children,
  createTheme: () => ({}),
  CssBaseline: () => null,
  AppBar: ({ children, ...props }) => <header {...props}>{children}</header>,
  Toolbar: ({ children, ...props }) => <div {...props}>{children}</div>,
  Typography: ({ children, ...props }) => <span {...props}>{children}</span>,
  Button: ({ children, onClick, ...props }) => (
    <button onClick={onClick} {...props}>{children}</button>
  ),
  TextField: ({ onChange, value, ...props }) => (
    <input onChange={(e) => onChange?.(e)} value={value} {...props} />
  ),
  Paper: ({ children, ...props }) => <div {...props}>{children}</div>,
  Container: ({ children, ...props }) => <div {...props}>{children}</div>,
  Grid: ({ children, ...props }) => <div {...props}>{children}</div>,
  Card: ({ children, ...props }) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }) => <div {...props}>{children}</div>,
  CircularProgress: () => <div data-testid="loading" />,
  Alert: ({ children, severity, ...props }) => (
    <div data-testid={`alert-${severity}`} {...props}>{children}</div>
  ),
  Snackbar: ({ children, open, ...props }) => 
    open ? <div data-testid="snackbar" {...props}>{children}</div> : null
}));

// Import components to test
import Dashboard from '../../pages/Dashboard.jsx';
import Portfolio from '../../pages/Portfolio.jsx';
import Settings from '../../pages/Settings.jsx';
import ApiKeyOnboarding from '../../components/ApiKeyOnboarding.jsx';
import StockChart from '../../components/StockChart.jsx';
import SignalCardEnhanced from '../../components/trading/SignalCardEnhanced.jsx';

// Test wrapper with providers
const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {children}
      </BrowserRouter>
    </QueryClientProvider>
  );
};

describe('Page Components', () => {
  let queryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false }
      }
    });
    vi.clearAllMocks();
  });

  describe('Dashboard Component', () => {
    test('should render dashboard with key sections', async () => {
      mockApiService.get.mockResolvedValue({
        data: {
          portfolioValue: 25000,
          dailyChange: 150.75,
          positions: 5,
          marketStatus: 'open'
        }
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByTestId('dashboard')).toBeInTheDocument();
      
      await waitFor(() => {
        expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
      });
    });

    test('should display portfolio summary', async () => {
      mockApiService.get.mockResolvedValue({
        data: {
          totalValue: 25000.50,
          dailyChange: 150.75,
          dailyChangePercent: 0.61,
          positions: [
            { symbol: 'AAPL', value: 15000 },
            { symbol: 'MSFT', value: 10000 }
          ]
        }
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/25,000.50/)).toBeInTheDocument();
      });
    });

    test('should handle loading state', () => {
      mockApiService.get.mockImplementation(() => new Promise(resolve => 
        setTimeout(() => resolve({ data: {} }), 1000)
      ));

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByTestId('loading')).toBeInTheDocument();
    });

    test('should handle error state', async () => {
      mockApiService.get.mockRejectedValue(new Error('API Error'));

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('alert-error')).toBeInTheDocument();
      });
    });
  });

  describe('Portfolio Component', () => {
    const mockPortfolioData = {
      overview: {
        totalValue: 25000.50,
        dailyChange: 150.75,
        dailyChangePercent: 0.61,
        totalGain: 2500.25,
        totalGainPercent: 11.11
      },
      positions: [
        {
          id: 1,
          symbol: 'AAPL',
          shares: 100,
          avgCost: 140.00,
          currentPrice: 150.00,
          marketValue: 15000.00,
          unrealizedGain: 1000.00,
          unrealizedGainPercent: 7.14
        },
        {
          id: 2,
          symbol: 'MSFT',
          shares: 50,
          avgCost: 180.00,
          currentPrice: 200.00,
          marketValue: 10000.00,
          unrealizedGain: 1000.00,
          unrealizedGainPercent: 11.11
        }
      ]
    };

    test('should render portfolio overview', async () => {
      mockApiService.get.mockResolvedValue({ data: mockPortfolioData });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/portfolio overview/i)).toBeInTheDocument();
        expect(screen.getByText(/25,000.50/)).toBeInTheDocument();
      });
    });

    test('should display individual positions', async () => {
      mockApiService.get.mockResolvedValue({ data: mockPortfolioData });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('MSFT')).toBeInTheDocument();
        expect(screen.getByText('100')).toBeInTheDocument(); // shares
        expect(screen.getByText('50')).toBeInTheDocument(); // shares
      });
    });

    test('should handle adding new position', async () => {
      mockApiService.get.mockResolvedValue({ data: mockPortfolioData });
      mockApiService.post.mockResolvedValue({ data: { success: true } });

      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/add position/i)).toBeInTheDocument();
      });

      await user.click(screen.getByText(/add position/i));

      await waitFor(() => {
        expect(screen.getByTestId('add-position-form')).toBeInTheDocument();
      });

      // Fill out form
      await user.type(screen.getByLabelText(/symbol/i), 'TSLA');
      await user.type(screen.getByLabelText(/shares/i), '25');
      await user.type(screen.getByLabelText(/price/i), '200.00');

      await user.click(screen.getByText(/save/i));

      await waitFor(() => {
        expect(mockApiService.post).toHaveBeenCalledWith(
          '/api/portfolio/positions',
          expect.objectContaining({
            symbol: 'TSLA',
            shares: 25,
            price: 200.00
          })
        );
      });
    });

    test('should handle position editing', async () => {
      mockApiService.get.mockResolvedValue({ data: mockPortfolioData });
      mockApiService.put.mockResolvedValue({ data: { success: true } });

      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('edit-position-1')).toBeInTheDocument();
      });

      await user.click(screen.getByTestId('edit-position-1'));

      await waitFor(() => {
        expect(screen.getByTestId('edit-position-form')).toBeInTheDocument();
      });

      const sharesInput = screen.getByDisplayValue('100');
      await user.clear(sharesInput);
      await user.type(sharesInput, '150');

      await user.click(screen.getByText(/update/i));

      await waitFor(() => {
        expect(mockApiService.put).toHaveBeenCalledWith(
          '/api/portfolio/positions/1',
          expect.objectContaining({ shares: 150 })
        );
      });
    });

    test('should handle position deletion', async () => {
      mockApiService.get.mockResolvedValue({ data: mockPortfolioData });
      mockApiService.delete.mockResolvedValue({ data: { success: true } });

      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId('delete-position-1')).toBeInTheDocument();
      });

      await user.click(screen.getByTestId('delete-position-1'));

      await waitFor(() => {
        expect(screen.getByText(/confirm delete/i)).toBeInTheDocument();
      });

      await user.click(screen.getByText(/confirm/i));

      await waitFor(() => {
        expect(mockApiService.delete).toHaveBeenCalledWith('/api/portfolio/positions/1');
      });
    });
  });

  describe('Settings Component', () => {
    const mockUserSettings = {
      profile: {
        email: 'test@example.com',
        username: 'testuser',
        timezone: 'America/New_York'
      },
      preferences: {
        theme: 'dark',
        notifications: true,
        defaultChartPeriod: '1Y'
      },
      apiKeys: [
        { provider: 'alpaca', hasKey: true, lastUpdated: '2024-03-15' },
        { provider: 'polygon', hasKey: false, lastUpdated: null }
      ]
    };

    test('should render settings sections', async () => {
      mockApiService.get.mockResolvedValue({ data: mockUserSettings });

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/profile settings/i)).toBeInTheDocument();
        expect(screen.getByText(/api keys/i)).toBeInTheDocument();
        expect(screen.getByText(/preferences/i)).toBeInTheDocument();
      });
    });

    test('should handle API key configuration', async () => {
      mockApiService.get.mockResolvedValue({ data: mockUserSettings });
      mockApiService.post.mockResolvedValue({ data: { success: true } });

      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/configure alpaca/i)).toBeInTheDocument();
      });

      await user.click(screen.getByText(/configure alpaca/i));

      await waitFor(() => {
        expect(screen.getByTestId('api-key-form')).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText(/api key/i), 'PKTEST123456789012345');
      await user.type(screen.getByLabelText(/secret key/i), 'secretkey123456789012345');

      await user.click(screen.getByText(/save/i));

      await waitFor(() => {
        expect(mockApiService.post).toHaveBeenCalledWith(
          '/api/settings/api-keys',
          expect.objectContaining({
            provider: 'alpaca',
            apiKey: 'PKTEST123456789012345',
            secretKey: 'secretkey123456789012345'
          })
        );
      });
    });

    test('should handle preferences updates', async () => {
      mockApiService.get.mockResolvedValue({ data: mockUserSettings });
      mockApiService.put.mockResolvedValue({ data: { success: true } });

      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByLabelText(/theme/i)).toBeInTheDocument();
      });

      await user.selectOptions(screen.getByLabelText(/theme/i), 'light');

      await waitFor(() => {
        expect(mockApiService.put).toHaveBeenCalledWith(
          '/api/settings/preferences',
          expect.objectContaining({ theme: 'light' })
        );
      });
    });
  });
});

describe('Utility Components', () => {
  describe('ApiKeyOnboarding Component', () => {
    test('should render onboarding steps', () => {
      render(
        <TestWrapper>
          <ApiKeyOnboarding />
        </TestWrapper>
      );

      expect(screen.getByText(/welcome/i)).toBeInTheDocument();
      expect(screen.getByText(/get started/i)).toBeInTheDocument();
    });

    test('should navigate through steps', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <ApiKeyOnboarding />
        </TestWrapper>
      );

      // Start onboarding
      await user.click(screen.getByText(/get started/i));

      await waitFor(() => {
        expect(screen.getByText(/alpaca setup/i)).toBeInTheDocument();
      });

      // Navigate to next step
      await user.click(screen.getByText(/next/i));

      await waitFor(() => {
        expect(screen.getByText(/market data/i)).toBeInTheDocument();
      });
    });

    test('should validate API key format', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <ApiKeyOnboarding />
        </TestWrapper>
      );

      await user.click(screen.getByText(/get started/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/api key/i)).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText(/api key/i), 'invalid-key');
      await user.click(screen.getByText(/validate/i));

      await waitFor(() => {
        expect(screen.getByText(/invalid format/i)).toBeInTheDocument();
      });
    });

    test('should complete onboarding successfully', async () => {
      mockApiService.post.mockResolvedValue({ data: { success: true } });

      const user = userEvent.setup();
      const onComplete = vi.fn();

      render(
        <TestWrapper>
          <ApiKeyOnboarding onComplete={onComplete} />
        </TestWrapper>
      );

      // Go through all steps (simplified)
      await user.click(screen.getByText(/get started/i));
      
      // Fill valid API keys
      await user.type(screen.getByLabelText(/api key/i), 'PKTEST123456789012345');
      await user.type(screen.getByLabelText(/secret key/i), 'secretkey123456789012345');
      
      await user.click(screen.getByText(/complete setup/i));

      await waitFor(() => {
        expect(onComplete).toHaveBeenCalled();
      });
    });
  });

  describe('StockChart Component', () => {
    const mockChartData = [
      { date: '2024-01-01', price: 100, volume: 1000000 },
      { date: '2024-01-02', price: 102, volume: 1100000 },
      { date: '2024-01-03', price: 101, volume: 950000 },
      { date: '2024-01-04', price: 105, volume: 1200000 },
      { date: '2024-01-05', price: 107, volume: 1300000 }
    ];

    test('should render chart with data', () => {
      render(
        <TestWrapper>
          <StockChart 
            symbol="AAPL" 
            data={mockChartData} 
            height={400} 
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      expect(screen.getByTestId('line-chart')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    test('should handle different chart types', () => {
      render(
        <TestWrapper>
          <StockChart 
            symbol="AAPL" 
            data={mockChartData} 
            type="area"
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('area-chart')).toBeInTheDocument();
    });

    test('should handle empty data gracefully', () => {
      render(
        <TestWrapper>
          <StockChart 
            symbol="AAPL" 
            data={[]} 
          />
        </TestWrapper>
      );

      expect(screen.getByText(/no data available/i)).toBeInTheDocument();
    });

    test('should handle period selection', async () => {
      const user = userEvent.setup();
      const onPeriodChange = vi.fn();

      render(
        <TestWrapper>
          <StockChart 
            symbol="AAPL" 
            data={mockChartData}
            onPeriodChange={onPeriodChange}
          />
        </TestWrapper>
      );

      await user.click(screen.getByText('1M'));

      expect(onPeriodChange).toHaveBeenCalledWith('1M');
    });

    test('should display technical indicators', () => {
      render(
        <TestWrapper>
          <StockChart 
            symbol="AAPL" 
            data={mockChartData}
            showTechnicals={true}
          />
        </TestWrapper>
      );

      expect(screen.getByText(/moving average/i)).toBeInTheDocument();
    });
  });

  describe('SignalCardEnhanced Component', () => {
    const mockSignal = {
      symbol: 'AAPL',
      signal: 'BUY',
      confidence: 85,
      price: 150.00,
      targetPrice: 165.00,
      stopLoss: 140.00,
      reason: 'Bullish momentum with strong fundamentals',
      timestamp: '2024-03-15T10:30:00Z'
    };

    test('should render signal card', () => {
      render(
        <TestWrapper>
          <SignalCardEnhanced signal={mockSignal} />
        </TestWrapper>
      );

      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('BUY')).toBeInTheDocument();
    });

    test('should display signal confidence', () => {
      render(
        <TestWrapper>
          <SignalCardEnhanced signal={mockSignal} />
        </TestWrapper>
      );

      expect(screen.getByText('85%')).toBeInTheDocument();
    });

    test('should show price information', () => {
      render(
        <TestWrapper>
          <SignalCardEnhanced signal={mockSignal} />
        </TestWrapper>
      );

      expect(screen.getByText('$150.00')).toBeInTheDocument();
      expect(screen.getByText('$165.00')).toBeInTheDocument(); // target
      expect(screen.getByText('$140.00')).toBeInTheDocument(); // stop loss
    });
  });
});

describe('Component Interactions & User Flows', () => {
  describe('Form Validation', () => {
    test('should validate required fields', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Try to submit empty form
      await user.click(screen.getByText(/add position/i));
      await user.click(screen.getByText(/save/i));

      await waitFor(() => {
        expect(screen.getByText(/symbol is required/i)).toBeInTheDocument();
        expect(screen.getByText(/shares is required/i)).toBeInTheDocument();
      });
    });

    test('should validate input formats', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      await user.click(screen.getByText(/configure alpaca/i));
      await user.type(screen.getByLabelText(/api key/i), 'invalid-format');
      await user.click(screen.getByText(/validate/i));

      await waitFor(() => {
        expect(screen.getByText(/invalid api key format/i)).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    test('should display network error messages', async () => {
      mockApiService.get.mockRejectedValue(new Error('Network Error'));

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/network error/i)).toBeInTheDocument();
      });
    });

    test('should handle API rate limiting', async () => {
      mockApiService.get.mockRejectedValue({
        response: { status: 429, data: { error: 'Rate limit exceeded' } }
      });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/rate limit exceeded/i)).toBeInTheDocument();
      });
    });

    test('should recover from errors with retry', async () => {
      mockApiService.get
        .mockRejectedValueOnce(new Error('Network Error'))
        .mockResolvedValueOnce({ data: { totalValue: 25000 } });

      const user = userEvent.setup();

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/network error/i)).toBeInTheDocument();
      });

      await user.click(screen.getByText(/retry/i));

      await waitFor(() => {
        expect(screen.getByText(/25,000/)).toBeInTheDocument();
      });
    });
  });

  describe('Loading States', () => {
    test('should show skeleton loaders', () => {
      mockApiService.get.mockImplementation(() => new Promise(() => {})); // Never resolves

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      expect(screen.getByTestId('loading')).toBeInTheDocument();
    });

    test('should show progressive loading for charts', async () => {
      mockApiService.get.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({ 
            data: Array.from({ length: 100 }, (_, i) => ({ 
              date: `2024-01-${i + 1}`, 
              price: 100 + Math.random() * 10 
            }))
          }), 500)
        )
      );

      render(
        <TestWrapper>
          <StockChart symbol="AAPL" />
        </TestWrapper>
      );

      expect(screen.getByTestId('loading')).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByTestId('line-chart')).toBeInTheDocument();
      }, { timeout: 1000 });
    });
  });

  describe('Responsive Behavior', () => {
    test('should adapt to mobile viewport', () => {
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Mobile-specific elements should be present
      expect(screen.getByTestId('mobile-nav')).toBeInTheDocument();
    });

    test('should show/hide elements based on screen size', () => {
      // Mock desktop viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 1920
      });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Desktop-specific elements should be present
      expect(screen.getByTestId('sidebar')).toBeInTheDocument();
    });
  });
});
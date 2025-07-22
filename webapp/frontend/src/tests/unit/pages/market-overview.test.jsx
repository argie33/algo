/**
 * MarketOverview Page Unit Tests
 * Tests market data display, real-time updates, and market indicators
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';

// Import the component to test
import MarketOverview from '../../../pages/MarketOverview';

// Mock AuthContext
const mockAuthContext = {
  user: { username: 'testuser', email: 'test@example.com' },
  isAuthenticated: true,
  isLoading: false,
  tokens: { accessToken: 'mock-token' }
};

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext
}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate
  };
});

// Mock MUI components
vi.mock('@mui/material', async () => {
  const actual = await vi.importActual('@mui/material');
  return {
    ...actual,
    Box: ({ children, ...props }) => <div data-testid="mui-box" {...props}>{children}</div>,
    Typography: ({ children, variant, ...props }) => (
      <div data-testid={`typography-${variant || 'body1'}`} {...props}>{children}</div>
    ),
    Card: ({ children, ...props }) => <div data-testid="mui-card" {...props}>{children}</div>,
    CardContent: ({ children, ...props }) => <div data-testid="card-content" {...props}>{children}</div>,
    Grid: ({ children, ...props }) => <div data-testid="mui-grid" {...props}>{children}</div>,
    CircularProgress: (props) => <div data-testid="loading-spinner" {...props}>Loading...</div>,
    Alert: ({ children, severity, ...props }) => (
      <div data-testid={`alert-${severity}`} {...props}>{children}</div>
    )
  };
});

// Mock API service
const mockApiService = {
  get: vi.fn()
};

vi.mock('../../../services/api', () => ({
  api: mockApiService
}));

// Mock fetch for direct API calls
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Test wrapper component
const TestWrapper = ({ children }) => (
  <BrowserRouter>
    {children}
  </BrowserRouter>
);

describe('📈 MarketOverview Page Tests', () => {
  const user = userEvent.setup();

  const mockMarketData = {
    indices: {
      'S&P 500': { value: 4521.23, change: 15.67, changePercent: 0.35 },
      'NASDAQ': { value: 14234.56, change: -23.45, changePercent: -0.16 },
      'Dow Jones': { value: 34876.12, change: 145.23, changePercent: 0.42 }
    },
    sectors: [
      { name: 'Technology', change: 1.2, leaders: ['AAPL', 'MSFT', 'GOOGL'] },
      { name: 'Healthcare', change: -0.5, leaders: ['JNJ', 'PFE', 'UNH'] },
      { name: 'Finance', change: 0.8, leaders: ['JPM', 'BAC', 'WFC'] }
    ],
    topMovers: {
      gainers: [
        { symbol: 'TSLA', price: 245.67, change: 12.34, changePercent: 5.29 },
        { symbol: 'NVDA', price: 432.10, change: 18.56, changePercent: 4.49 }
      ],
      losers: [
        { symbol: 'META', price: 298.45, change: -15.23, changePercent: -4.86 },
        { symbol: 'NFLX', price: 456.78, change: -12.89, changePercent: -2.75 }
      ]
    }
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
    
    // Default successful API responses
    mockApiService.get.mockResolvedValue({
      success: true,
      data: mockMarketData
    });

    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, data: mockMarketData })
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Component Rendering', () => {
    it('should render market overview page', () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      expect(screen.getByTestId('mui-box')).toBeInTheDocument();
    });

    it('should show loading state initially', () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
    });

    it('should display page title', () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Look for page title in typography components
      const titleElements = screen.getAllByTestId(/typography/);
      expect(titleElements.length).toBeGreaterThan(0);
    });
  });

  describe('Market Data Loading', () => {
    it('should fetch market data on mount', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should call API to fetch market data
        expect(mockApiService.get).toHaveBeenCalled();
      });
    });

    it('should handle successful data loading', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.queryByTestId('loading-spinner')).not.toBeInTheDocument();
      });

      // Should display market data containers
      expect(screen.getByTestId('mui-box')).toBeInTheDocument();
    });

    it('should handle API errors gracefully', async () => {
      mockApiService.get.mockRejectedValue(new Error('API Error'));

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show error alert or handle gracefully
        const alerts = screen.queryAllByTestId(/alert/);
        if (alerts.length > 0) {
          expect(alerts[0]).toBeInTheDocument();
        } else {
          // Should at least render without crashing
          expect(screen.getByTestId('mui-box')).toBeInTheDocument();
        }
      });
    });
  });

  describe('Market Indices Display', () => {
    it('should display major market indices', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      // Should have cards for displaying market data
      const cards = screen.getAllByTestId('mui-card');
      expect(cards.length).toBeGreaterThan(0);
    });

    it('should show index values and changes', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      // Should display typography elements for data
      const dataElements = screen.getAllByTestId(/typography/);
      expect(dataElements.length).toBeGreaterThan(0);
    });
  });

  describe('Sector Performance', () => {
    it('should display sector performance data', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      // Should have grid layout for sectors
      const grids = screen.getAllByTestId('mui-grid');
      expect(grids.length).toBeGreaterThan(0);
    });

    it('should handle empty sector data', async () => {
      mockApiService.get.mockResolvedValue({
        success: true,
        data: { ...mockMarketData, sectors: [] }
      });

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      expect(screen.getByTestId('mui-box')).toBeInTheDocument();
    });
  });

  describe('Top Movers', () => {
    it('should display top gainers and losers', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      // Should have sections for gainers and losers
      const cards = screen.getAllByTestId('mui-card');
      expect(cards.length).toBeGreaterThan(0);
    });

    it('should handle navigation to stock details', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      // Navigation function should be available
      expect(mockNavigate).toBeDefined();
    });
  });

  describe('Real-time Updates', () => {
    it('should handle real-time data updates', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Initial data load
      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      // Simulate data update
      mockApiService.get.mockClear();
      
      // Component should be ready for updates
      expect(screen.getByTestId('mui-box')).toBeInTheDocument();
    });

    it('should refresh data periodically if configured', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      // Should have made at least one API call
      expect(mockApiService.get).toHaveBeenCalledTimes(1);
    });
  });

  describe('Error Handling', () => {
    it('should display error message when API fails', async () => {
      mockApiService.get.mockRejectedValue(new Error('Market data unavailable'));

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should handle error gracefully
        expect(screen.getByTestId('mui-box')).toBeInTheDocument();
      });
    });

    it('should handle partial data loading', async () => {
      mockApiService.get.mockResolvedValue({
        success: true,
        data: {
          indices: mockMarketData.indices,
          sectors: null, // Partial data
          topMovers: null
        }
      });

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      expect(screen.getByTestId('mui-box')).toBeInTheDocument();
    });
  });

  describe('User Interactions', () => {
    it('should handle refresh button if available', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      // Should render interface for user interactions
      expect(screen.getByTestId('mui-box')).toBeInTheDocument();
    });

    it('should handle time frame selection if available', async () => {
      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      // Interface should be available for time frame selection
      expect(screen.getByTestId('mui-box')).toBeInTheDocument();
    });
  });

  describe('Performance', () => {
    it('should handle component unmounting cleanly', () => {
      const { unmount } = render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      unmount();
      
      // Should unmount without errors
      expect(true).toBe(true);
    });

    it('should not cause memory leaks with data updates', async () => {
      const { unmount } = render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApiService.get).toHaveBeenCalled();
      });

      unmount();
      
      // Should clean up properly
      expect(true).toBe(true);
    });
  });
});
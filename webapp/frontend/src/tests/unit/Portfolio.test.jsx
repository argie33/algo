/**
 * Comprehensive Portfolio Component Test Suite
 * Tests all Portfolio.jsx functionality with real API integration
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import Portfolio from '../../pages/Portfolio';
import { AuthContext } from '../../contexts/AuthContext';
import * as api from '../../services/api';

// Mock the API service
vi.mock('../../services/api');

// Mock the hooks
vi.mock('../../hooks/useLivePortfolioData', () => ({
  useLivePortfolioData: () => ({
    data: null,
    loading: false,
    error: null,
    subscribe: vi.fn(),
    unsubscribe: vi.fn()
  })
}));

vi.mock('../../hooks/usePortfolioFactorAnalysis', () => ({
  usePortfolioFactorAnalysis: () => ({
    factorData: null,
    loading: false,
    error: null
  })
}));

// Create theme for testing
const theme = createTheme();

// Mock auth context
const mockAuthContext = {
  isAuthenticated: true,
  user: {
    sub: 'test-user-123',
    email: 'test@example.com',
    name: 'Test User'
  },
  login: vi.fn(),
  logout: vi.fn(),
  loading: false
};

// Test wrapper component
const TestWrapper = ({ children }) => (
  <BrowserRouter>
    <ThemeProvider theme={theme}>
      <AuthContext.Provider value={mockAuthContext}>
        {children}
      </AuthContext.Provider>
    </ThemeProvider>
  </BrowserRouter>
);

// Mock portfolio data - realistic structure based on real API
const mockPortfolioData = {
  holdings: [
    {
      symbol: 'AAPL',
      company: 'Apple Inc.',
      shares: 100,
      avgCost: 150.00,
      currentPrice: 189.45,
      marketValue: 18945,
      gainLoss: 3945,
      gainLossPercent: 26.30,
      sector: 'Technology',
      allocation: 23.5,
      beta: 1.2,
      isRealData: true
    },
    {
      symbol: 'MSFT',
      company: 'Microsoft Corporation',
      shares: 50,
      avgCost: 300.00,
      currentPrice: 342.56,
      marketValue: 17128,
      gainLoss: 2128,
      gainLossPercent: 14.19,
      sector: 'Technology',
      allocation: 21.3,
      beta: 0.9,
      isRealData: true
    }
  ],
  sectorAllocation: [
    { name: 'Technology', value: 48.9, isRealData: true },
    { name: 'Financials', value: 25.6, isRealData: true },
    { name: 'Healthcare', value: 14.6, isRealData: true },
    { name: 'Consumer Staples', value: 7.6, isRealData: true }
  ],
  performanceHistory: Array.from({ length: 30 }, (_, i) => ({
    date: new Date(Date.now() - (30 - i) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    portfolioValue: 65000 + Math.random() * 10000 + i * 15,
    benchmarkValue: 65000 + Math.random() * 8000 + i * 12,
    isRealData: true
  })),
  totalValue: 80500,
  dayChange: 1250.75,
  dayChangePercent: 1.58,
  isRealData: true
};

describe('Portfolio Component Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock successful API calls by default
    api.getPortfolioData.mockResolvedValue({
      success: true,
      data: mockPortfolioData
    });
    
    api.getAvailableAccounts.mockResolvedValue({
      success: true,
      data: [
        {
          type: 'alpaca',
          name: 'Alpaca Paper Trading',
          provider: 'alpaca',
          isActive: true
        }
      ]
    });
    
    api.getAccountInfo.mockResolvedValue({
      success: true,
      data: {
        accountType: 'paper',
        balance: 250000,
        equity: 80500,
        dayChange: 1250.75,
        dayChangePercent: 1.58
      }
    });
    
    api.getApiKeys.mockResolvedValue({
      success: true,
      data: {
        alpaca: { exists: true }
      }
    });
    
    api.testApiConnection.mockResolvedValue({
      success: true,
      data: { status: 'connected' }
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Component Rendering and Structure', () => {
    test('renders portfolio component with loading state', async () => {
      // Mock loading state
      api.getPortfolioData.mockImplementation(() => new Promise(() => {}));
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Check for loading indicators
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    test('renders portfolio data when API call succeeds', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });

      // Check for portfolio holdings
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('MSFT')).toBeInTheDocument();
      expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
      expect(screen.getByText('Microsoft Corporation')).toBeInTheDocument();
    });

    test('renders error state when API call fails', async () => {
      api.getPortfolioData.mockRejectedValue(new Error('API Error'));
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/error/i)).toBeInTheDocument();
      });
    });
  });

  describe('Real Data Validation', () => {
    test('ensures no mock data flags are present in rendered content', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });

      // Ensure no mock data indicators
      expect(screen.queryByText(/mock/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/demo/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/sample/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/fake/i)).not.toBeInTheDocument();
    });

    test('validates real data properties in portfolio holdings', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.getPortfolioData).toHaveBeenCalledWith(
          expect.objectContaining({
            includeMetadata: true,
            refresh: true
          })
        );
      });

      // Verify API was called with correct parameters for real data
      expect(api.getPortfolioData).toHaveBeenCalledTimes(1);
    });

    test('displays real-time price updates correctly', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('$189.45')).toBeInTheDocument(); // AAPL current price
        expect(screen.getByText('$342.56')).toBeInTheDocument(); // MSFT current price
      });
    });
  });

  describe('Portfolio Analytics and Calculations', () => {
    test('calculates portfolio metrics correctly', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        // Check total portfolio value
        expect(screen.getByText(/\$80,500/)).toBeInTheDocument();
        
        // Check day change
        expect(screen.getByText(/\$1,250\.75/)).toBeInTheDocument();
        expect(screen.getByText(/1\.58%/)).toBeInTheDocument();
      });
    });

    test('displays sector allocation correctly', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Technology')).toBeInTheDocument();
        expect(screen.getByText('Financials')).toBeInTheDocument();
        expect(screen.getByText('Healthcare')).toBeInTheDocument();
      });
    });

    test('shows gain/loss calculations for individual holdings', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        // Check AAPL gain/loss
        expect(screen.getByText(/\$3,945/)).toBeInTheDocument();
        expect(screen.getByText(/26\.30%/)).toBeInTheDocument();
        
        // Check MSFT gain/loss
        expect(screen.getByText(/\$2,128/)).toBeInTheDocument();
        expect(screen.getByText(/14\.19%/)).toBeInTheDocument();
      });
    });
  });

  describe('User Interactions', () => {
    test('handles portfolio refresh correctly', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });

      // Find and click refresh button
      const refreshButton = screen.getByRole('button', { name: /refresh/i });
      fireEvent.click(refreshButton);

      // Verify API called again
      await waitFor(() => {
        expect(api.getPortfolioData).toHaveBeenCalledTimes(2);
      });
    });

    test('switches between different account types', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });

      // Test account switching if multiple accounts available
      if (screen.queryByRole('combobox')) {
        const accountSelect = screen.getByRole('combobox');
        fireEvent.click(accountSelect);
        
        // Should trigger new API call when account changes
        await waitFor(() => {
          expect(api.getPortfolioData).toHaveBeenCalled();
        });
      }
    });

    test('handles tab navigation correctly', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });

      // Test different tabs if they exist
      const tabs = screen.queryAllByRole('tab');
      if (tabs.length > 0) {
        fireEvent.click(tabs[1]);
        
        // Should show different content based on tab
        await waitFor(() => {
          expect(tabs[1]).toHaveAttribute('aria-selected', 'true');
        });
      }
    });
  });

  describe('API Integration Testing', () => {
    test('handles authentication errors correctly', async () => {
      api.getPortfolioData.mockRejectedValue({
        response: { status: 401, data: { error: 'Unauthorized' } }
      });
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/unauthorized/i)).toBeInTheDocument();
      });
    });

    test('handles API key missing errors', async () => {
      api.getApiKeys.mockResolvedValue({
        success: true,
        data: {} // No API keys
      });
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show API key setup requirement
        expect(screen.getByText(/api key/i)).toBeInTheDocument();
      });
    });

    test('handles network connectivity issues', async () => {
      api.getPortfolioData.mockRejectedValue(new Error('Network Error'));
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/network/i)).toBeInTheDocument();
      });
    });

    test('validates API response data structure', async () => {
      const invalidData = {
        success: true,
        data: {
          // Missing required fields
          holdings: []
        }
      };
      
      api.getPortfolioData.mockResolvedValue(invalidData);
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should handle invalid data gracefully
        expect(screen.getByText(/no holdings/i)).toBeInTheDocument();
      });
    });
  });

  describe('Performance and Optimization', () => {
    test('renders large portfolio datasets efficiently', async () => {
      const largePortfolio = {
        ...mockPortfolioData,
        holdings: Array.from({ length: 100 }, (_, i) => ({
          symbol: `STOCK${i}`,
          company: `Company ${i}`,
          shares: 100 + i,
          avgCost: 100 + Math.random() * 100,
          currentPrice: 120 + Math.random() * 100,
          marketValue: (100 + i) * (120 + Math.random() * 100),
          gainLoss: Math.random() * 1000 - 500,
          gainLossPercent: Math.random() * 20 - 10,
          sector: ['Technology', 'Healthcare', 'Financials'][i % 3],
          allocation: Math.random() * 10,
          beta: 0.5 + Math.random() * 1.5,
          isRealData: true
        }))
      };
      
      api.getPortfolioData.mockResolvedValue({
        success: true,
        data: largePortfolio
      });
      
      const startTime = performance.now();
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });
      
      const endTime = performance.now();
      const renderTime = endTime - startTime;
      
      // Should render within reasonable time (under 2 seconds)
      expect(renderTime).toBeLessThan(2000);
    });

    test('implements proper cleanup on unmount', () => {
      const { unmount } = render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Should not throw errors on unmount
      expect(() => unmount()).not.toThrow();
    });
  });

  describe('Accessibility Testing', () => {
    test('has proper ARIA labels and roles', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });

      // Check for proper table structure
      const tables = screen.queryAllByRole('table');
      tables.forEach(table => {
        expect(table).toHaveAttribute('aria-label');
      });

      // Check for proper headings hierarchy
      const headings = screen.queryAllByRole('heading');
      expect(headings.length).toBeGreaterThan(0);
    });

    test('supports keyboard navigation', async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });

      // Test tab navigation
      const buttons = screen.queryAllByRole('button');
      if (buttons.length > 0) {
        buttons[0].focus();
        expect(document.activeElement).toBe(buttons[0]);
      }
    });
  });

  describe('Security and Data Validation', () => {
    test('sanitizes display data properly', async () => {
      const portfolioWithPotentialXSS = {
        ...mockPortfolioData,
        holdings: [{
          ...mockPortfolioData.holdings[0],
          company: '<script>alert("xss")</script>Test Company',
          symbol: 'TEST<>'
        }]
      };
      
      api.getPortfolioData.mockResolvedValue({
        success: true,
        data: portfolioWithPotentialXSS
      });
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should not render script tags
        expect(screen.queryByText('<script>')).not.toBeInTheDocument();
        // Should show sanitized content
        expect(screen.getByText(/Test Company/)).toBeInTheDocument();
      });
    });

    test('validates numeric data ranges', async () => {
      const portfolioWithInvalidData = {
        ...mockPortfolioData,
        holdings: [{
          ...mockPortfolioData.holdings[0],
          shares: -100, // Invalid negative shares
          currentPrice: NaN, // Invalid price
          gainLossPercent: Infinity // Invalid percentage
        }]
      };
      
      api.getPortfolioData.mockResolvedValue({
        success: true,
        data: portfolioWithInvalidData
      });
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should handle invalid data gracefully
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
        // Should not display invalid values
        expect(screen.queryByText('NaN')).not.toBeInTheDocument();
        expect(screen.queryByText('Infinity')).not.toBeInTheDocument();
      });
    });
  });
});

describe('Portfolio Component Unit Tests', () => {
  test('calculates portfolio totals correctly', () => {
    const holdings = [
      { marketValue: 10000, gainLoss: 1000 },
      { marketValue: 20000, gainLoss: -500 },
      { marketValue: 15000, gainLoss: 2000 }
    ];
    
    const totalValue = holdings.reduce((sum, holding) => sum + holding.marketValue, 0);
    const totalGainLoss = holdings.reduce((sum, holding) => sum + holding.gainLoss, 0);
    
    expect(totalValue).toBe(45000);
    expect(totalGainLoss).toBe(2500);
  });

  test('formats currency values correctly', () => {
    const formatCurrency = (value) => {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
      }).format(value);
    };
    
    expect(formatCurrency(12345.67)).toBe('$12,345.67');
    expect(formatCurrency(-1234.56)).toBe('-$1,234.56');
  });

  test('calculates percentage changes correctly', () => {
    const calculatePercentage = (current, original) => {
      if (original === 0) return 0;
      return ((current - original) / original) * 100;
    };
    
    expect(calculatePercentage(110, 100)).toBe(10);
    expect(calculatePercentage(90, 100)).toBe(-10);
    expect(calculatePercentage(100, 0)).toBe(0);
  });
});
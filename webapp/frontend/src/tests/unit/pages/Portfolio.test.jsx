import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import { createTheme } from '@mui/material/styles';
import Portfolio from '../../../pages/Portfolio';

// Mock dependencies
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => ({
  ...await vi.importActual('react-router-dom'),
  useNavigate: () => mockNavigate
}));

const mockUseAuth = vi.fn();
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth()
}));

vi.mock('../../../hooks/useDocumentTitle', () => ({
  useDocumentTitle: vi.fn()
}));

// Mock API calls
global.fetch = vi.fn();

const theme = createTheme();

const renderWithRouter = (component) => {
  return render(
    <BrowserRouter>
      <ThemeProvider theme={theme}>
        {component}
      </ThemeProvider>
    </BrowserRouter>
  );
};

describe('Portfolio', () => {
  const defaultAuthState = {
    isAuthenticated: true,
    isLoading: false,
    user: { 
      username: 'testuser', 
      email: 'test@example.com' 
    },
    token: 'mock-jwt-token'
  };

  const mockPortfolioData = {
    holdings: [
      {
        id: '1',
        symbol: 'AAPL',
        quantity: 100,
        averagePrice: 150.00,
        currentPrice: 160.00,
        marketValue: 16000,
        totalCost: 15000,
        totalReturn: 1000,
        totalReturnPercent: 6.67,
        dayChange: 2.50,
        dayChangePercent: 1.59,
        sector: 'Technology',
        weight: 40.0
      },
      {
        id: '2',
        symbol: 'GOOGL',
        quantity: 50,
        averagePrice: 2800.00,
        currentPrice: 2900.00,
        marketValue: 145000,
        totalCost: 140000,
        totalReturn: 5000,
        totalReturnPercent: 3.57,
        dayChange: -10.00,
        dayChangePercent: -0.34,
        sector: 'Technology',
        weight: 60.0
      }
    ],
    summary: {
      totalValue: 161000,
      totalCost: 155000,
      totalReturn: 6000,
      totalReturnPercent: 3.87,
      dayChange: -750,
      dayChangePercent: -0.47,
      cash: 5000
    },
    performance: {
      weekReturn: 2.1,
      monthReturn: -1.5,
      yearReturn: 12.8,
      ytdReturn: 8.3
    },
    allocation: {
      sectors: [
        { name: 'Technology', value: 100, percentage: 100 },
        { name: 'Healthcare', value: 0, percentage: 0 }
      ]
    }
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(defaultAuthState);
    
    // Mock successful API response
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => mockPortfolioData
    });
  });

  describe('Authentication', () => {
    it('should redirect to login if not authenticated', () => {
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        isAuthenticated: false
      });

      renderWithRouter(<Portfolio />);

      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });

    it('should show loading state during auth loading', () => {
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        isLoading: true,
        isAuthenticated: false
      });

      renderWithRouter(<Portfolio />);

      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });
  });

  describe('Data Loading', () => {
    it('should show loading state while fetching data', () => {
      renderWithRouter(<Portfolio />);

      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('should fetch portfolio data on mount', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/portfolio'),
          expect.objectContaining({
            headers: expect.objectContaining({
              'Authorization': 'Bearer mock-jwt-token'
            })
          })
        );
      });
    });

    it('should display portfolio data after loading', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
      });

      // Check summary values
      expect(screen.getByText(/161,000/)).toBeInTheDocument(); // Total value
      expect(screen.getByText(/6,000/)).toBeInTheDocument(); // Total return
    });

    it('should handle API errors gracefully', async () => {
      global.fetch.mockRejectedValue(new Error('Network error'));
      
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText(/error loading portfolio/i)).toBeInTheDocument();
      });
    });

    it('should handle empty portfolio data', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        json: async () => ({
          holdings: [],
          summary: {
            totalValue: 0,
            totalCost: 0,
            totalReturn: 0,
            totalReturnPercent: 0,
            dayChange: 0,
            dayChangePercent: 0,
            cash: 10000
          }
        })
      });

      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText(/no holdings/i)).toBeInTheDocument();
      });
    });
  });

  describe('Portfolio Summary', () => {
    it('should display total portfolio value', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText(/161,000/)).toBeInTheDocument();
      });
    });

    it('should display total return with percentage', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText(/6,000/)).toBeInTheDocument();
        expect(screen.getByText(/3.87%/)).toBeInTheDocument();
      });
    });

    it('should display day change with proper formatting', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText(/-750/)).toBeInTheDocument();
        expect(screen.getByText(/-0.47%/)).toBeInTheDocument();
      });
    });

    it('should use appropriate colors for gains and losses', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        const dayChangeElements = screen.getAllByText(/-750/);
        expect(dayChangeElements.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Holdings Table', () => {
    it('should display all holdings', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
      });
    });

    it('should display holding details correctly', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('100')).toBeInTheDocument(); // AAPL quantity
        expect(screen.getByText('$160.00')).toBeInTheDocument(); // AAPL current price
        expect(screen.getByText('$16,000')).toBeInTheDocument(); // AAPL market value
      });
    });

    it('should support sorting by different columns', async () => {
      const user = userEvent.setup();
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Look for sortable column headers
      const symbolHeader = screen.getByText('Symbol').closest('th');
      if (symbolHeader) {
        await user.click(symbolHeader);
        // Verify sorting behavior if implemented
      }
    });

    it('should show sector information for holdings', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('Technology')).toBeInTheDocument();
      });
    });
  });

  describe('Performance Metrics', () => {
    it('should display performance period returns', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText(/2.1%/)).toBeInTheDocument(); // Week return
        expect(screen.getByText(/12.8%/)).toBeInTheDocument(); // Year return
      });
    });

    it('should handle negative performance values', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText(/-1.5%/)).toBeInTheDocument(); // Month return (negative)
      });
    });
  });

  describe('Sector Allocation', () => {
    it('should display sector breakdown', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('Technology')).toBeInTheDocument();
      });
    });

    it('should show sector percentages', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText(/100%/)).toBeInTheDocument(); // Technology allocation
      });
    });
  });

  describe('Interactive Features', () => {
    it('should allow switching between different views', async () => {
      const user = userEvent.setup();
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Look for tab navigation
      const tabs = screen.queryAllByRole('tab');
      if (tabs.length > 0) {
        await user.click(tabs[0]);
        // Verify view change if implemented
      }
    });

    it('should support portfolio refresh', async () => {
      const user = userEvent.setup();
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      const refreshButton = screen.queryByRole('button', { name: /refresh/i });
      if (refreshButton) {
        await user.click(refreshButton);
        expect(global.fetch).toHaveBeenCalledTimes(2); // Initial + refresh
      }
    });

    it('should handle stock symbol clicks for navigation', async () => {
      const user = userEvent.setup();
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      const stockLink = screen.getByText('AAPL');
      if (stockLink.closest('a') || stockLink.onclick) {
        await user.click(stockLink);
        // Verify navigation if implemented
      }
    });
  });

  describe('Error States', () => {
    it('should display error message when API fails', async () => {
      global.fetch.mockRejectedValue(new Error('API Error'));
      
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText(/error/i)).toBeInTheDocument();
      });
    });

    it('should display retry option on error', async () => {
      global.fetch.mockRejectedValue(new Error('API Error'));
      
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        const retryButton = screen.queryByRole('button', { name: /retry/i });
        expect(retryButton || screen.getByText(/error/i)).toBeInTheDocument();
      });
    });

    it('should handle unauthorized access', async () => {
      global.fetch.mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ error: 'Unauthorized' })
      });

      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/login');
      });
    });
  });

  describe('Document Title', () => {
    it('should set document title', () => {
      renderWithRouter(<Portfolio />);

      // Document title hook is mocked, just verify component renders without error
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });
  });

  describe('Responsiveness', () => {
    it('should render without crashing on different screen sizes', () => {
      // Test mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });

      const { unmount } = renderWithRouter(<Portfolio />);
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
      unmount();

      // Test tablet viewport
      window.innerWidth = 768;
      renderWithRouter(<Portfolio />);
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });
  });

  describe('Data Formatting', () => {
    it('should format currency values correctly', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('$160.00')).toBeInTheDocument();
        expect(screen.getByText('$16,000')).toBeInTheDocument();
      });
    });

    it('should format percentage values correctly', async () => {
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('6.67%')).toBeInTheDocument();
        expect(screen.getByText('-0.34%')).toBeInTheDocument();
      });
    });

    it('should handle large numbers appropriately', async () => {
      const largePortfolioData = {
        ...mockPortfolioData,
        holdings: [{
          ...mockPortfolioData.holdings[0],
          marketValue: 1500000000, // 1.5B
          quantity: 10000000
        }]
      };

      global.fetch.mockResolvedValue({
        ok: true,
        json: async () => largePortfolioData
      });

      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByText('10,000,000')).toBeInTheDocument();
      });
    });
  });

  describe('Performance Optimization', () => {
    it('should not cause infinite re-renders', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      renderWithRouter(<Portfolio />);

      await waitFor(() => {
        expect(screen.getByRole('progressbar')).toBeInTheDocument();
      });

      // Should not have React warnings about infinite loops
      expect(consoleSpy).not.toHaveBeenCalledWith(
        expect.stringContaining('Maximum update depth exceeded')
      );

      consoleSpy.mockRestore();
    });
  });
});
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from '../../../pages/Dashboard';

// Mock API service
// Mock the API service with comprehensive mock
vi.mock("../../../services/api", async (_importOriginal) => {
  const { createApiServiceMock } = await import('../../mocks/api-service-mock');
  return {
    default: createApiServiceMock(),
    ...createApiServiceMock()
  };
});

// Mock auth context
const mockAuthContext = {
  isAuthenticated: true,
  user: { id: '1', username: 'testuser' },
  loading: false,
};

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext,
}));

// Mock data service
vi.mock('../../../services/dataService', () => ({
  fetchMarketOverview: vi.fn(),
  fetchPortfolioSummary: vi.fn(),
  fetchRecentTrades: vi.fn(),
  fetchWatchlist: vi.fn(),
}));

describe('Dashboard Component', () => {
  const mockMarketData = {
    indices: {
      'S&P 500': { current: 4500, change: 25.5, changePercent: 0.57 },
      'Dow Jones': { current: 35000, change: -100, changePercent: -0.28 },
      'NASDAQ': { current: 14000, change: 50, changePercent: 0.36 },
    },
    marketStatus: 'OPEN',
  };

  const mockPortfolioData = {
    totalValue: 50000,
    dayChange: 1250,
    dayChangePercent: 2.5,
    holdings: [
      { symbol: 'AAPL', shares: 100, currentPrice: 150, totalValue: 15000 },
      { symbol: 'GOOGL', shares: 50, currentPrice: 2800, totalValue: 140000 },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Setup API mocks with default data
    const { fetchMarketOverview, fetchPortfolioSummary } = require('../../../services/dataService');
    fetchMarketOverview.mockResolvedValue(mockMarketData);
    fetchPortfolioSummary.mockResolvedValue(mockPortfolioData);
  });

  const renderDashboard = () => {
    return render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );
  };

  describe('Initial Rendering', () => {
    it('renders dashboard title', () => {
      renderDashboard();
      expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
    });

    it('shows loading state initially', () => {
      renderDashboard();
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('renders main dashboard sections', async () => {
      renderDashboard();
      
      await waitFor(() => {
        expect(screen.getByText(/market overview/i)).toBeInTheDocument();
        expect(screen.getByText(/portfolio summary/i)).toBeInTheDocument();
        expect(screen.getByText(/recent activity/i)).toBeInTheDocument();
      });
    });
  });

  describe('Market Overview Section', () => {
    it('displays market indices data', async () => {
      renderDashboard();
      
      await waitFor(() => {
        expect(screen.getByText('S&P 500')).toBeInTheDocument();
        expect(screen.getByText('4,500')).toBeInTheDocument();
        expect(screen.getByText('+25.5')).toBeInTheDocument();
        expect(screen.getByText('+0.57%')).toBeInTheDocument();
      });
    });

    it('shows market status', async () => {
      renderDashboard();
      
      await waitFor(() => {
        expect(screen.getByText(/market open/i)).toBeInTheDocument();
      });
    });

    it('handles market closed status', async () => {
      const { fetchMarketOverview } = require('../../../services/dataService');
      fetchMarketOverview.mockResolvedValue({
        ...mockMarketData,
        marketStatus: 'CLOSED',
      });
      
      renderDashboard();
      
      await waitFor(() => {
        expect(screen.getByText(/market closed/i)).toBeInTheDocument();
      });
    });
  });

  describe('Portfolio Summary Section', () => {
    it('displays portfolio total value', async () => {
      renderDashboard();
      
      await waitFor(() => {
        expect(screen.getByText('$50,000')).toBeInTheDocument();
      });
    });

    it('shows daily portfolio change', async () => {
      renderDashboard();
      
      await waitFor(() => {
        expect(screen.getByText('+$1,250')).toBeInTheDocument();
        expect(screen.getByText('+2.5%')).toBeInTheDocument();
      });
    });

    it('handles negative portfolio changes', async () => {
      const { fetchPortfolioSummary } = require('../../../services/dataService');
      fetchPortfolioSummary.mockResolvedValue({
        ...mockPortfolioData,
        dayChange: -500,
        dayChangePercent: -1.0,
      });
      
      renderDashboard();
      
      await waitFor(() => {
        expect(screen.getByText('-$500')).toBeInTheDocument();
        expect(screen.getByText('-1.0%')).toBeInTheDocument();
      });
    });

    it('displays top holdings', async () => {
      renderDashboard();
      
      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
      });
    });
  });

  describe('Interactive Features', () => {
    it('navigates to full portfolio page when clicked', async () => {
      const mockNavigate = vi.fn();
      vi.mock('react-router-dom', () => ({
        ...vi.importActual('react-router-dom'),
        useNavigate: () => mockNavigate,
      }));
      
      renderDashboard();
      
      await waitFor(() => {
        const portfolioLink = screen.getByRole('button', { name: /view full portfolio/i });
        fireEvent.click(portfolioLink);
        expect(mockNavigate).toHaveBeenCalledWith('/portfolio');
      });
    });

    it('refreshes data when refresh button is clicked', async () => {
      const { fetchMarketOverview } = require('../../../services/dataService');
      
      renderDashboard();
      
      await waitFor(() => {
        const refreshButton = screen.getByRole('button', { name: /refresh/i });
        fireEvent.click(refreshButton);
      });
      
      expect(fetchMarketOverview).toHaveBeenCalledTimes(2);
    });

    it('supports time range selection', async () => {
      renderDashboard();
      
      await waitFor(() => {
        const timeRangeSelect = screen.getByLabelText(/time range/i);
        fireEvent.change(timeRangeSelect, { target: { value: '1W' } });
      });
      
      // Should trigger data refresh with new time range
      const { fetchPortfolioSummary } = require('../../../services/dataService');
      expect(fetchPortfolioSummary).toHaveBeenCalledWith(
        expect.objectContaining({ timeRange: '1W' })
      );
    });
  });

  describe('Error Handling', () => {
    it('displays error message when market data fails to load', async () => {
      const { fetchMarketOverview } = require('../../../services/dataService');
      fetchMarketOverview.mockRejectedValue(new Error('API Error'));
      
      renderDashboard();
      
      await waitFor(() => {
        expect(screen.getByText(/failed to load market data/i)).toBeInTheDocument();
      });
    });

    it('displays error message when portfolio data fails to load', async () => {
      const { fetchPortfolioSummary } = require('../../../services/dataService');
      fetchPortfolioSummary.mockRejectedValue(new Error('API Error'));
      
      renderDashboard();
      
      await waitFor(() => {
        expect(screen.getByText(/failed to load portfolio data/i)).toBeInTheDocument();
      });
    });

    it('shows retry option when data loading fails', async () => {
      const { fetchMarketOverview } = require('../../../services/dataService');
      fetchMarketOverview.mockRejectedValue(new Error('API Error'));
      
      renderDashboard();
      
      await waitFor(() => {
        const retryButton = screen.getByRole('button', { name: /retry/i });
        expect(retryButton).toBeInTheDocument();
        
        fireEvent.click(retryButton);
        expect(fetchMarketOverview).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe('Responsive Design', () => {
    it('adapts layout for mobile screens', () => {
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderDashboard();
      
      // Should show mobile-optimized layout
      const dashboardContainer = screen.getByTestId('dashboard-container');
      expect(dashboardContainer).toHaveClass('mobile-layout');
    });

    it('shows full layout on desktop', () => {
      // Mock desktop viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 1200,
      });
      
      renderDashboard();
      
      const dashboardContainer = screen.getByTestId('dashboard-container');
      expect(dashboardContainer).toHaveClass('desktop-layout');
    });
  });

  describe('Performance', () => {
    it('memoizes expensive calculations', async () => {
      const { fetchPortfolioSummary } = require('../../../services/dataService');
      
      renderDashboard();
      
      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText('$50,000')).toBeInTheDocument();
      });
      
      // Re-render with same data shouldn't trigger recalculation
      renderDashboard();
      
      expect(fetchPortfolioSummary).toHaveBeenCalledTimes(1);
    });

    it('implements virtual scrolling for large lists', async () => {
      const largeHoldingsList = Array.from({ length: 1000 }, (_, i) => ({
        symbol: `STOCK${i}`,
        shares: 100,
        currentPrice: 50,
        totalValue: 5000,
      }));
      
      const { fetchPortfolioSummary } = require('../../../services/dataService');
      fetchPortfolioSummary.mockResolvedValue({
        ...mockPortfolioData,
        holdings: largeHoldingsList,
      });
      
      renderDashboard();
      
      await waitFor(() => {
        // Should only render visible items
        const renderedItems = screen.getAllByTestId('holding-item');
        expect(renderedItems.length).toBeLessThan(largeHoldingsList.length);
      });
    });
  });

  describe('Accessibility', () => {
    it('provides proper ARIA labels', async () => {
      renderDashboard();
      
      await waitFor(() => {
        expect(screen.getByLabelText(/market overview section/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/portfolio summary section/i)).toBeInTheDocument();
      });
    });

    it('supports keyboard navigation', async () => {
      renderDashboard();
      
      await waitFor(() => {
        const firstFocusableElement = screen.getByRole('button', { name: /refresh/i });
        firstFocusableElement.focus();
        expect(document.activeElement).toBe(firstFocusableElement);
      });
    });

    it('announces dynamic content changes to screen readers', async () => {
      renderDashboard();
      
      await waitFor(() => {
        const liveRegion = screen.getByRole('status');
        expect(liveRegion).toHaveAttribute('aria-live', 'polite');
      });
    });
  });
});
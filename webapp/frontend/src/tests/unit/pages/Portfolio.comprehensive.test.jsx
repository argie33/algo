import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Portfolio from '../../../pages/Portfolio';

// Mock API service
// Mock the API service with comprehensive mock
vi.mock("../../services/api", async (_importOriginal) => {
  const { createApiServiceMock } = await import('../mocks/api-service-mock');
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

describe('Portfolio Page', () => {
  const mockPortfolioData = {
    summary: {
      totalValue: 125000,
      dayChange: 2500,
      dayChangePercent: 2.04,
      totalGainLoss: 15000,
      totalGainLossPercent: 13.64,
    },
    holdings: [
      {
        id: '1',
        symbol: 'AAPL',
        companyName: 'Apple Inc.',
        shares: 100,
        avgCost: 140,
        currentPrice: 150,
        marketValue: 15000,
        gainLoss: 1000,
        gainLossPercent: 7.14,
        dayChange: 2.5,
        dayChangePercent: 1.69,
      },
      {
        id: '2',
        symbol: 'GOOGL',
        companyName: 'Alphabet Inc.',
        shares: 50,
        avgCost: 2500,
        currentPrice: 2800,
        marketValue: 140000,
        gainLoss: 15000,
        gainLossPercent: 12.0,
        dayChange: -50,
        dayChangePercent: -1.75,
      },
    ],
    performance: {
      '1D': { return: 2.04, benchmark: 1.2 },
      '1W': { return: 5.8, benchmark: 3.1 },
      '1M': { return: 12.3, benchmark: 8.7 },
      '3M': { return: 18.5, benchmark: 15.2 },
      '1Y': { return: 28.4, benchmark: 22.1 },
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    
    const api = require('../../../services/api').default;
    api.get.mockImplementation((url) => {
      if (url.includes('/portfolio')) {
        return Promise.resolve({ data: mockPortfolioData });
      }
      if (url.includes('/holdings')) {
        return Promise.resolve({ data: mockPortfolioData.holdings });
      }
      return Promise.reject(new Error('Unknown endpoint'));
    });
  });

  const renderPortfolio = () => {
    return render(
      <MemoryRouter>
        <Portfolio />
      </MemoryRouter>
    );
  };

  describe('Portfolio Summary', () => {
    it('displays total portfolio value', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        expect(screen.getByText('$125,000')).toBeInTheDocument();
      });
    });

    it('shows daily change with correct formatting', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        expect(screen.getByText('+$2,500')).toBeInTheDocument();
        expect(screen.getByText('+2.04%')).toBeInTheDocument();
      });
    });

    it('displays total gain/loss', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        expect(screen.getByText('+$15,000')).toBeInTheDocument();
        expect(screen.getByText('+13.64%')).toBeInTheDocument();
      });
    });

    it('handles negative changes correctly', async () => {
      const api = require('../../../services/api').default;
      api.get.mockResolvedValue({
        data: {
          ...mockPortfolioData,
          summary: {
            ...mockPortfolioData.summary,
            dayChange: -1500,
            dayChangePercent: -1.18,
            totalGainLoss: -5000,
            totalGainLossPercent: -4.0,
          },
        },
      });
      
      renderPortfolio();
      
      await waitFor(() => {
        expect(screen.getByText('-$1,500')).toBeInTheDocument();
        expect(screen.getByText('-1.18%')).toBeInTheDocument();
        expect(screen.getByText('-$5,000')).toBeInTheDocument();
        expect(screen.getByText('-4.0%')).toBeInTheDocument();
      });
    });
  });

  describe('Holdings Table', () => {
    it('displays all holdings with correct data', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
        expect(screen.getByText('100')).toBeInTheDocument();
        expect(screen.getByText('$15,000')).toBeInTheDocument();
        
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
        expect(screen.getByText('Alphabet Inc.')).toBeInTheDocument();
        expect(screen.getByText('50')).toBeInTheDocument();
        expect(screen.getByText('$140,000')).toBeInTheDocument();
      });
    });

    it('sorts holdings by different columns', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const symbolHeader = screen.getByText('Symbol');
        fireEvent.click(symbolHeader);
      });
      
      // Holdings should be sorted by symbol
      const holdingRows = screen.getAllByTestId('holding-row');
      expect(holdingRows[0]).toHaveTextContent('AAPL');
      expect(holdingRows[1]).toHaveTextContent('GOOGL');
    });

    it('filters holdings by search term', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const searchInput = screen.getByPlaceholderText(/search holdings/i);
        fireEvent.change(searchInput, { target: { value: 'AAPL' } });
      });
      
      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.queryByText('GOOGL')).not.toBeInTheDocument();
      });
    });

    it('shows gain/loss indicators with correct colors', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const aaplGainLoss = screen.getByText('+$1,000');
        expect(aaplGainLoss).toHaveClass('text-green-600');
        
        // Note: GOOGL has positive total gain but negative day change
        const googlDayChange = screen.getByText('-$50');
        expect(googlDayChange).toHaveClass('text-red-600');
      });
    });
  });

  describe('Performance Charts', () => {
    it('displays performance chart', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        expect(screen.getByTestId('performance-chart')).toBeInTheDocument();
      });
    });

    it('allows time period selection', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const timePeriodButtons = screen.getAllByRole('button');
        const oneMonthButton = timePeriodButtons.find(btn => btn.textContent === '1M');
        fireEvent.click(oneMonthButton);
      });
      
      // Should update chart data for 1 month period
      await waitFor(() => {
        expect(screen.getByText('12.3%')).toBeInTheDocument(); // 1M return
      });
    });

    it('compares portfolio performance to benchmark', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        expect(screen.getByText(/vs benchmark/i)).toBeInTheDocument();
        expect(screen.getByText('22.1%')).toBeInTheDocument(); // Benchmark 1Y return
      });
    });
  });

  describe('Holdings Management', () => {
    it('allows adding new holdings', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const addButton = screen.getByRole('button', { name: /add holding/i });
        fireEvent.click(addButton);
      });
      
      expect(screen.getByText(/add new holding/i)).toBeInTheDocument();
    });

    it('allows editing existing holdings', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const editButton = screen.getByTestId('edit-AAPL');
        fireEvent.click(editButton);
      });
      
      expect(screen.getByText(/edit holding/i)).toBeInTheDocument();
      expect(screen.getByDisplayValue('AAPL')).toBeInTheDocument();
    });

    it('confirms before deleting holdings', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const deleteButton = screen.getByTestId('delete-AAPL');
        fireEvent.click(deleteButton);
      });
      
      expect(screen.getByText(/confirm deletion/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
    });

    it('validates holding data before saving', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const addButton = screen.getByRole('button', { name: /add holding/i });
        fireEvent.click(addButton);
        
        const saveButton = screen.getByRole('button', { name: /save/i });
        fireEvent.click(saveButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText(/symbol is required/i)).toBeInTheDocument();
        expect(screen.getByText(/shares must be positive/i)).toBeInTheDocument();
      });
    });
  });

  describe('Data Refresh', () => {
    it('refreshes data automatically', async () => {
      vi.useFakeTimers();
      renderPortfolio();
      
      const api = require('../../../services/api').default;
      await waitFor(() => {
        expect(api.get).toHaveBeenCalledTimes(1);
      });
      
      // Fast-forward 30 seconds (auto-refresh interval)
      vi.advanceTimersByTime(30000);
      
      await waitFor(() => {
        expect(api.get).toHaveBeenCalledTimes(2);
      });
      
      vi.useRealTimers();
    });

    it('allows manual refresh', async () => {
      renderPortfolio();
      
      const api = require('../../../services/api').default;
      await waitFor(() => {
        const refreshButton = screen.getByRole('button', { name: /refresh/i });
        fireEvent.click(refreshButton);
      });
      
      expect(api.get).toHaveBeenCalledTimes(2);
    });

    it('shows loading state during refresh', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const refreshButton = screen.getByRole('button', { name: /refresh/i });
        fireEvent.click(refreshButton);
        
        expect(screen.getByRole('progressbar')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('displays error message when portfolio data fails to load', async () => {
      const api = require('../../../services/api').default;
      api.get.mockRejectedValue(new Error('Network error'));
      
      renderPortfolio();
      
      await waitFor(() => {
        expect(screen.getByText(/failed to load portfolio data/i)).toBeInTheDocument();
      });
    });

    it('provides retry option on error', async () => {
      const api = require('../../../services/api').default;
      api.get.mockRejectedValueOnce(new Error('Network error'));
      
      renderPortfolio();
      
      await waitFor(() => {
        const retryButton = screen.getByRole('button', { name: /retry/i });
        fireEvent.click(retryButton);
      });
      
      expect(api.get).toHaveBeenCalledTimes(2);
    });

    it('handles API errors gracefully during updates', async () => {
      renderPortfolio();
      
      const api = require('../../../services/api').default;
      api.put.mockRejectedValue(new Error('Update failed'));
      
      await waitFor(() => {
        const editButton = screen.getByTestId('edit-AAPL');
        fireEvent.click(editButton);
        
        const sharesInput = screen.getByDisplayValue('100');
        fireEvent.change(sharesInput, { target: { value: '150' } });
        
        const saveButton = screen.getByRole('button', { name: /save/i });
        fireEvent.click(saveButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText(/failed to update holding/i)).toBeInTheDocument();
      });
    });
  });

  describe('Export Functionality', () => {
    it('allows exporting portfolio data', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const exportButton = screen.getByRole('button', { name: /export/i });
        fireEvent.click(exportButton);
      });
      
      expect(screen.getByText(/export options/i)).toBeInTheDocument();
      expect(screen.getByText(/CSV/i)).toBeInTheDocument();
      expect(screen.getByText(/PDF/i)).toBeInTheDocument();
    });

    it('generates CSV export with correct data', async () => {
      const mockCreateElement = vi.fn(() => ({
        click: vi.fn(),
        setAttribute: vi.fn(),
      }));
      document.createElement = mockCreateElement;
      
      renderPortfolio();
      
      await waitFor(() => {
        const exportButton = screen.getByRole('button', { name: /export/i });
        fireEvent.click(exportButton);
        
        const csvOption = screen.getByText(/CSV/i);
        fireEvent.click(csvOption);
      });
      
      expect(mockCreateElement).toHaveBeenCalledWith('a');
    });
  });

  describe('Accessibility', () => {
    it('provides proper ARIA labels for interactive elements', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        expect(screen.getByLabelText(/portfolio summary/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/holdings table/i)).toBeInTheDocument();
      });
    });

    it('supports keyboard navigation', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const firstButton = screen.getByRole('button', { name: /add holding/i });
        firstButton.focus();
        expect(document.activeElement).toBe(firstButton);
        
        // Tab to next element
        fireEvent.keyDown(firstButton, { key: 'Tab' });
      });
    });

    it('announces data updates to screen readers', async () => {
      renderPortfolio();
      
      await waitFor(() => {
        const liveRegion = screen.getByRole('status');
        expect(liveRegion).toHaveAttribute('aria-live', 'polite');
      });
    });
  });

  describe('Mobile Responsiveness', () => {
    it('adapts table layout for mobile screens', () => {
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderPortfolio();
      
      const holdingsTable = screen.getByTestId('holdings-table');
      expect(holdingsTable).toHaveClass('mobile-responsive');
    });

    it('provides swipe-to-action on mobile', async () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderPortfolio();
      
      await waitFor(() => {
        const holdingRow = screen.getByTestId('holding-row-AAPL');
        
        // Simulate swipe gesture
        fireEvent.touchStart(holdingRow, {
          touches: [{ clientX: 100, clientY: 100 }],
        });
        fireEvent.touchMove(holdingRow, {
          touches: [{ clientX: 50, clientY: 100 }],
        });
        fireEvent.touchEnd(holdingRow);
      });
      
      expect(screen.getByTestId('swipe-actions')).toBeInTheDocument();
    });
  });
});
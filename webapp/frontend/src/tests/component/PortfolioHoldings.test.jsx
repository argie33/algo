import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { BrowserRouter } from 'react-router-dom';
import PortfolioHoldings from '../../components/PortfolioHoldings';

// Mock the API service
vi.mock('../../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

// Mock AuthContext
const mockAuthContext = {
  user: { sub: 'test-user', email: 'test@example.com' },
  token: 'mock-jwt-token',
  isAuthenticated: true,
};

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext,
}));

// Mock recharts for chart rendering
vi.mock('recharts', () => ({
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
}));

// Import after mocking
import api from '../../services/api';

const renderWithRouter = (component) => {
  return render(
    <BrowserRouter>
      {component}
    </BrowserRouter>
  );
};

describe('PortfolioHoldings Component', () => {
  const mockHoldingsData = {
    holdings: [
      {
        symbol: 'AAPL',
        companyName: 'Apple Inc.',
        quantity: 100,
        averagePrice: 120.00,
        currentPrice: 150.00,
        marketValue: 15000.00,
        costBasis: 12000.00,
        unrealizedGainLoss: 3000.00,
        unrealizedGainLossPercent: 25.00,
        dayChange: 125.00,
        dayChangePercent: 0.84,
        sector: 'Technology',
        allocation: 35.7
      },
      {
        symbol: 'GOOGL',
        companyName: 'Alphabet Inc.',
        quantity: 25,
        averagePrice: 2500.00,
        currentPrice: 2800.00,
        marketValue: 70000.00,
        costBasis: 62500.00,
        unrealizedGainLoss: 7500.00,
        unrealizedGainLossPercent: 12.00,
        dayChange: -350.00,
        dayChangePercent: -1.25,
        sector: 'Technology',
        allocation: 16.7
      },
      {
        symbol: 'TSLA',
        companyName: 'Tesla Inc.',
        quantity: 50,
        averagePrice: 800.00,
        currentPrice: 900.00,
        marketValue: 45000.00,
        costBasis: 40000.00,
        unrealizedGainLoss: 5000.00,
        unrealizedGainLossPercent: 12.50,
        dayChange: 225.00,
        dayChangePercent: 2.56,
        sector: 'Consumer Discretionary',
        allocation: 10.7
      }
    ],
    summary: {
      totalMarketValue: 130000.00,
      totalCostBasis: 114500.00,
      totalUnrealizedGainLoss: 15500.00,
      totalUnrealizedGainLossPercent: 13.54,
      totalDayChange: 0.00,
      totalDayChangePercent: 0.00,
      diversificationScore: 82
    },
    sectors: [
      { name: 'Technology', value: 85000, percentage: 65.4 },
      { name: 'Consumer Discretionary', value: 45000, percentage: 34.6 }
    ]
  };

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Default API responses
    api.get.mockResolvedValue({
      data: {
        success: true,
        data: mockHoldingsData
      }
    });
  });

  describe('Component Loading', () => {
    it('should render portfolio holdings interface', async () => {
      renderWithRouter(<PortfolioHoldings />);
      
      expect(screen.getByText(/Portfolio Holdings/i)).toBeInTheDocument();
      
      await waitFor(() => {
        expect(screen.getByText(/Total Market Value/i)).toBeInTheDocument();
        expect(screen.getByText(/Holdings/i)).toBeInTheDocument();
      });
    });

    it('should load holdings data on mount', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith('/api/portfolio/holdings');
      });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
        expect(screen.getByText('TSLA')).toBeInTheDocument();
      });
    });

    it('should show loading state initially', async () => {
      api.get.mockImplementation(() => 
        new Promise(resolve => setTimeout(() => resolve({
          data: { success: true, data: mockHoldingsData }
        }), 100))
      );

      renderWithRouter(<PortfolioHoldings />);

      expect(screen.getByText(/Loading holdings/i)).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.queryByText(/Loading holdings/i)).not.toBeInTheDocument();
      }, { timeout: 200 });
    });
  });

  describe('Holdings Summary', () => {
    it('should display portfolio summary metrics', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('$130,000.00')).toBeInTheDocument(); // Total market value
        expect(screen.getByText('$114,500.00')).toBeInTheDocument(); // Total cost basis
        expect(screen.getByText('+$15,500.00')).toBeInTheDocument(); // Total gain/loss
        expect(screen.getByText('+13.54%')).toBeInTheDocument(); // Total gain/loss %
      });
    });

    it('should display diversification score', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('82')).toBeInTheDocument(); // Diversification score
        expect(screen.getByText(/Diversification Score/i)).toBeInTheDocument();
      });
    });

    it('should handle negative performance correctly', async () => {
      const negativeData = {
        ...mockHoldingsData,
        summary: {
          ...mockHoldingsData.summary,
          totalUnrealizedGainLoss: -5500.00,
          totalUnrealizedGainLossPercent: -4.80,
          totalDayChange: -1250.00,
          totalDayChangePercent: -0.96
        }
      };

      api.get.mockResolvedValue({
        data: { success: true, data: negativeData }
      });

      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('-$5,500.00')).toBeInTheDocument();
        expect(screen.getByText('-4.80%')).toBeInTheDocument();
        expect(screen.getByText('-$1,250.00')).toBeInTheDocument();
        expect(screen.getByText('-0.96%')).toBeInTheDocument();
      });
    });
  });

  describe('Holdings Table', () => {
    it('should display all holdings with correct data', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        // Check for all symbols
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
        expect(screen.getByText('TSLA')).toBeInTheDocument();

        // Check company names
        expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
        expect(screen.getByText('Alphabet Inc.')).toBeInTheDocument();
        expect(screen.getByText('Tesla Inc.')).toBeInTheDocument();

        // Check quantities
        expect(screen.getByText('100')).toBeInTheDocument(); // AAPL quantity
        expect(screen.getByText('25')).toBeInTheDocument(); // GOOGL quantity
        expect(screen.getByText('50')).toBeInTheDocument(); // TSLA quantity
      });
    });

    it('should display market values and gains/losses', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        // Market values
        expect(screen.getByText('$15,000.00')).toBeInTheDocument(); // AAPL
        expect(screen.getByText('$70,000.00')).toBeInTheDocument(); // GOOGL
        expect(screen.getByText('$45,000.00')).toBeInTheDocument(); // TSLA

        // Gain/Loss percentages
        expect(screen.getByText('+25.00%')).toBeInTheDocument(); // AAPL
        expect(screen.getByText('+12.00%')).toBeInTheDocument(); // GOOGL
        expect(screen.getByText('+12.50%')).toBeInTheDocument(); // TSLA
      });
    });

    it('should display current prices and day changes', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        // Current prices
        expect(screen.getByText('$150.00')).toBeInTheDocument(); // AAPL
        expect(screen.getByText('$2,800.00')).toBeInTheDocument(); // GOOGL
        expect(screen.getByText('$900.00')).toBeInTheDocument(); // TSLA

        // Day changes
        expect(screen.getByText('+$125.00')).toBeInTheDocument(); // AAPL day change
        expect(screen.getByText('-$350.00')).toBeInTheDocument(); // GOOGL day change
        expect(screen.getByText('+$225.00')).toBeInTheDocument(); // TSLA day change
      });
    });

    it('should show allocation percentages', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('35.7%')).toBeInTheDocument(); // AAPL allocation
        expect(screen.getByText('16.7%')).toBeInTheDocument(); // GOOGL allocation
        expect(screen.getByText('10.7%')).toBeInTheDocument(); // TSLA allocation
      });
    });
  });

  describe('Sorting and Filtering', () => {
    it('should sort holdings by different criteria', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Click sort by market value
      const sortButton = screen.getByText(/Sort by Market Value/i);
      fireEvent.click(sortButton);

      // Holdings should be reordered (GOOGL first with highest value)
      const rows = screen.getAllByTestId('holding-row');
      expect(rows[0]).toHaveTextContent('GOOGL');
      expect(rows[1]).toHaveTextContent('TSLA');
      expect(rows[2]).toHaveTextContent('AAPL');
    });

    it('should filter holdings by sector', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Filter by Technology sector
      const sectorFilter = screen.getByLabelText(/Filter by Sector/i);
      fireEvent.change(sectorFilter, { target: { value: 'Technology' } });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
        expect(screen.queryByText('TSLA')).not.toBeInTheDocument();
      });
    });

    it('should search holdings by symbol or company name', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Search for Apple
      const searchInput = screen.getByPlaceholderText(/Search holdings/i);
      fireEvent.change(searchInput, { target: { value: 'Apple' } });

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.queryByText('GOOGL')).not.toBeInTheDocument();
        expect(screen.queryByText('TSLA')).not.toBeInTheDocument();
      });
    });

    it('should show/hide holdings based on minimum value filter', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Set minimum value filter
      const minValueInput = screen.getByLabelText(/Minimum Value/i);
      fireEvent.change(minValueInput, { target: { value: '50000' } });

      await waitFor(() => {
        expect(screen.getByText('GOOGL')).toBeInTheDocument(); // $70,000
        expect(screen.queryByText('AAPL')).not.toBeInTheDocument(); // $15,000
        expect(screen.queryByText('TSLA')).not.toBeInTheDocument(); // $45,000
      });
    });
  });

  describe('Sector Allocation Chart', () => {
    it('should render sector allocation pie chart', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });
    });

    it('should display sector allocation data', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('Technology')).toBeInTheDocument();
        expect(screen.getByText('Consumer Discretionary')).toBeInTheDocument();
        expect(screen.getByText('65.4%')).toBeInTheDocument();
        expect(screen.getByText('34.6%')).toBeInTheDocument();
      });
    });

    it('should toggle chart visibility', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
      });

      // Hide chart
      fireEvent.click(screen.getByText(/Hide Chart/i));

      await waitFor(() => {
        expect(screen.queryByTestId('pie-chart')).not.toBeInTheDocument();
      });

      // Show chart again
      fireEvent.click(screen.getByText(/Show Chart/i));

      await waitFor(() => {
        expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
      });
    });
  });

  describe('Individual Holding Actions', () => {
    it('should show holding details on row click', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Click on AAPL row
      const appleRow = screen.getByText('AAPL').closest('tr');
      fireEvent.click(appleRow);

      await waitFor(() => {
        expect(screen.getByText(/Holding Details/i)).toBeInTheDocument();
        expect(screen.getByText(/Average Price:/i)).toBeInTheDocument();
        expect(screen.getByText('$120.00')).toBeInTheDocument();
      });
    });

    it('should allow quick trade actions', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Click trade button for AAPL
      const tradeButtons = screen.getAllByText(/Trade/i);
      fireEvent.click(tradeButtons[0]);

      await waitFor(() => {
        expect(screen.getByText(/Trade AAPL/i)).toBeInTheDocument();
        expect(screen.getByText(/Buy/i)).toBeInTheDocument();
        expect(screen.getByText(/Sell/i)).toBeInTheDocument();
      });
    });

    it('should show position analysis', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Click analyze button
      const analyzeButtons = screen.getAllByText(/Analyze/i);
      fireEvent.click(analyzeButtons[0]);

      await waitFor(() => {
        expect(screen.getByText(/Position Analysis/i)).toBeInTheDocument();
        expect(screen.getByText(/Risk Metrics/i)).toBeInTheDocument();
        expect(screen.getByText(/Performance/i)).toBeInTheDocument();
      });
    });
  });

  describe('Export and Sharing', () => {
    it('should export holdings data to CSV', async () => {
      const mockDownload = vi.fn();
      global.URL.createObjectURL = jest.fn(() => 'mock-url');
      global.URL.revokeObjectURL = vi.fn();
      
      // Mock link click
      const mockLink = {
        click: mockDownload,
        setAttribute: vi.fn(),
        style: {}
      };
      vi.spyOn(document, 'createElement').mockReturnValue(mockLink);
      vi.spyOn(document.body, 'appendChild').mockImplementation(() => {});
      vi.spyOn(document.body, 'removeChild').mockImplementation(() => {});

      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Click export button
      fireEvent.click(screen.getByText(/Export CSV/i));

      await waitFor(() => {
        expect(mockDownload).toHaveBeenCalled();
      });
    });

    it('should generate portfolio report', async () => {
      api.post.mockResolvedValue({
        data: {
          success: true,
          data: { reportUrl: 'mock-report-url' }
        }
      });

      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Click generate report button
      fireEvent.click(screen.getByText(/Generate Report/i));

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith('/api/portfolio/report', {
          includeHoldings: true,
          includeAnalysis: true
        });
      });
    });
  });

  describe('Real-time Updates', () => {
    it('should update prices automatically', async () => {
      vi.useFakeTimers();

      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('$150.00')).toBeInTheDocument(); // AAPL price
      });

      // Mock updated price data
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: {
            ...mockHoldingsData,
            holdings: [
              {
                ...mockHoldingsData.holdings[0],
                currentPrice: 155.00, // Updated AAPL price
                marketValue: 15500.00
              },
              ...mockHoldingsData.holdings.slice(1)
            ]
          }
        }
      });

      // Trigger auto-refresh
      vi.advanceTimersByTime(30000); // 30 seconds

      await waitFor(() => {
        expect(screen.getByText('$155.00')).toBeInTheDocument(); // Updated price
      });

      vi.useRealTimers();
    });

    it('should show last updated timestamp', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText(/Last updated:/i)).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle API errors gracefully', async () => {
      api.get.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: 'Failed to load holdings'
          }
        }
      });

      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText(/Failed to load holdings/i)).toBeInTheDocument();
      });
    });

    it('should handle network errors', async () => {
      api.get.mockRejectedValue(new Error('Network error'));

      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText(/Unable to load portfolio holdings/i)).toBeInTheDocument();
      });
    });

    it('should provide retry functionality', async () => {
      api.get.mockRejectedValueOnce(new Error('Network error'))
           .mockResolvedValue({
             data: { success: true, data: mockHoldingsData }
           });

      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText(/Unable to load portfolio holdings/i)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Retry/i));

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      expect(api.get).toHaveBeenCalledTimes(2);
    });

    it('should handle empty holdings gracefully', async () => {
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: {
            holdings: [],
            summary: {
              totalMarketValue: 0,
              totalCostBasis: 0,
              totalUnrealizedGainLoss: 0,
              totalUnrealizedGainLossPercent: 0
            },
            sectors: []
          }
        }
      });

      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText(/No holdings found/i)).toBeInTheDocument();
        expect(screen.getByText(/Start investing/i)).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    it('should have proper table structure and headers', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByRole('table')).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: /Symbol/i })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: /Company/i })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: /Market Value/i })).toBeInTheDocument();
      });
    });

    it('should have proper ARIA labels', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByLabelText(/Portfolio holdings table/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/Search holdings/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/Filter by Sector/i)).toBeInTheDocument();
      });
    });

    it('should be keyboard navigable', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Focus on first holding row
      const firstRow = screen.getAllByRole('row')[1]; // Skip header row
      firstRow.focus();
      expect(firstRow).toHaveFocus();

      // Arrow key navigation
      fireEvent.keyDown(firstRow, { key: 'ArrowDown' });
      const secondRow = screen.getAllByRole('row')[2];
      expect(secondRow).toHaveFocus();
    });

    it('should announce updates to screen readers', async () => {
      renderWithRouter(<PortfolioHoldings />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });

      // Refresh data
      fireEvent.click(screen.getByLabelText(/Refresh holdings/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/Holdings updated/i)).toBeInTheDocument();
      });
    });
  });
});
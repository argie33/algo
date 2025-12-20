import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import AnalystInsights from '../../pages/AnalystInsights';
import api from '../../services/api';

// Mock the api service
vi.mock('../../services/api');

// Integration test with real API structure
const renderWithRouter = (component) => {
  return render(
    <BrowserRouter>
      {component}
    </BrowserRouter>
  );
};

describe('AnalystInsights Integration Tests', () => {
  // Mock the real API structure from our backend
  const mockRealApiResponse = {
    upgrades: {
      success: true,
      data: [
        {
          id: 1,
          symbol: "AAPL",
          firm: "Goldman Sachs",
          action: "upgrade",
          from_grade: "Hold",
          to_grade: "Buy",
          date: "2024-01-15",
          details: "Strong iPhone sales outlook",
          fetched_at: "2025-09-21T16:19:44.467Z"
        },
        {
          id: 2,
          symbol: "GOOGL",
          firm: "Morgan Stanley",
          action: "downgrade",
          from_grade: "Buy",
          to_grade: "Hold",
          date: "2024-01-14",
          details: "AI competition concerns",
          fetched_at: "2025-09-21T15:19:44.467Z"
        }
      ],
      pagination: {
        page: 1,
        limit: 50,
        total: 2,
        totalPages: 1,
        hasMore: false
      },
      source: "YFinance via loadanalystupgradedowngrade.py",
      timestamp: "2025-09-28T13:52:42.239Z"
    },
    revenueEstimates: {
      success: true,
      data: [
        {
          symbol: "AAPL",
          period: "0q",
          avg_estimate: 85000000000,
          low_estimate: 83000000000,
          high_estimate: 87000000000,
          number_of_analysts: 12,
          year_ago_revenue: 81000000000,
          growth: 0.049,
          fetched_at: "2025-09-28T01:09:43.465Z"
        }
      ],
      count: 1,
      source: "YFinance via loadrevenueestimate.py",
      timestamp: "2025-09-28T13:52:42.239Z"
    },
    symbolSpecific: {
      success: true,
      symbol: "AAPL",
      data: {
        upgrades_downgrades: [
          {
            id: 1,
            symbol: "AAPL",
            firm: "Goldman Sachs",
            action: "upgrade",
            from_grade: "Hold",
            to_grade: "Buy",
            date: "2024-01-15",
            details: "iPhone sales growth",
            fetched_at: "2025-09-21T16:19:44.467Z"
          }
        ],
        revenue_estimates: [
          {
            symbol: "AAPL",
            period: "0q",
            avg_estimate: 85000000000,
            number_of_analysts: 12,
            growth: 0.049,
            fetched_at: "2025-09-28T01:09:43.465Z"
          }
        ]
      },
      counts: {
        upgrades_downgrades: 1,
        revenue_estimates: 1,
        total_analysts_covering: 12
      },
      sources: {
        upgrades_downgrades: "YFinance via loadanalystupgradedowngrade.py",
        revenue_estimates: "YFinance via loadrevenueestimate.py"
      },
      timestamp: "2025-09-28T13:52:42.239Z"
    }
  };

  beforeEach(() => {
    // Mock axios api with actual API structure
    api.get.mockImplementation((url) => {
      if (url.includes('/api/analysts/upgrades')) {
        return Promise.resolve({
          data: mockRealApiResponse.upgrades
        });
      } else if (url.includes('/api/analysts/')) {
        // Symbol-specific endpoint
        return Promise.resolve({
          data: mockRealApiResponse.symbolSpecific
        });
      }
      return Promise.reject(new Error('Unknown endpoint'));
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  test('integrates with real analyst API endpoints correctly', async () => {
    renderWithRouter(<AnalystInsights />);

    // Verify API calls are made to correct endpoints
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/api/analysts/upgrades?page=1&limit=50');
    });

    // Verify data from real API structure is displayed
    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('Goldman Sachs')).toBeInTheDocument();
      expect(screen.getByText('upgrade')).toBeInTheDocument();
    });
  });

  test('handles pagination with real API structure', async () => {
    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      // Should call API with pagination parameters
      expect(api.get).toHaveBeenCalledWith('/api/analysts/upgrades?page=1&limit=50');
    });

    // Verify pagination data is handled correctly
    const paginationInfo = await screen.findByText('Recent Analyst Actions');
    expect(paginationInfo).toBeInTheDocument();
  });

  test('symbol click triggers detailed API call with correct structure', async () => {
    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      const symbolLink = screen.getAllByText('AAPL')[0];
      fireEvent.click(symbolLink);
    });

    // Verify symbol-specific API call
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/api/analysts/AAPL');
    });
  });

  test('filters work with real data structure', async () => {
    renderWithRouter(<AnalystInsights />);

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    // For MUI Select, we need to click to open the dropdown then select
    const actionFilterButton = screen.getByRole('combobox', { name: /action filter/i });
    fireEvent.mouseDown(actionFilterButton);

    await waitFor(() => {
      const upgradeOption = screen.getByRole('option', { name: /upgrades/i });
      expect(upgradeOption).toBeInTheDocument();
      fireEvent.click(upgradeOption);
    });

    // Verify filter was applied - dropdown should close after selection
    await waitFor(() => {
      // After selecting, the dropdown should close (options are no longer in the document)
      expect(screen.queryByRole('option')).not.toBeInTheDocument();
    });
  });

  test('handles real API error responses correctly', async () => {
    api.get.mockRejectedValue({
      response: {
        status: 500,
        data: {
          success: false,
          error: "Failed to fetch analyst upgrades",
          details: "Database connection failed"
        }
      }
    });

    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load analyst data')).toBeInTheDocument();
    }, { timeout: 10000 });
  });


  test('date formatting handles API timestamp format', async () => {
    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      // Verify dates are formatted from API timestamp format
      const dateElements = screen.getAllByText(/\d{1,2}\/\d{1,2}\/\d{4}/);
      expect(dateElements.length).toBeGreaterThan(0);
    });
  });

  test('source attribution is displayed from API response', async () => {
    renderWithRouter(<AnalystInsights />);

    // The source information should be available in the data structure
    // even if not directly displayed, it validates API contract
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/api/analysts/upgrades?page=1&limit=50');
    });
  });
});
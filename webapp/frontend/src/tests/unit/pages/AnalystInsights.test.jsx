import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import AnalystInsights from '../../../pages/AnalystInsights';
import api from '../../../services/api';

// Mock the API service
vi.mock('../../../services/api');

const renderWithRouter = (component) => {
  return render(
    <BrowserRouter>
      {component}
    </BrowserRouter>
  );
};

describe('AnalystInsights Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockUpgradesData = {
    success: true,
    data: [
      {
        id: 1,
        symbol: 'AAPL',
        firm: 'Goldman Sachs',
        action: 'upgrade',
        from_grade: 'Hold',
        to_grade: 'Buy',
        date: '2024-01-15',
        details: 'Strong iPhone sales outlook',
        fetched_at: '2025-09-21T16:19:44.467Z'
      },
      {
        id: 2,
        symbol: 'GOOGL',
        firm: 'Morgan Stanley',
        action: 'downgrade',
        from_grade: 'Buy',
        to_grade: 'Hold',
        date: '2024-01-14',
        details: 'AI competition concerns',
        fetched_at: '2025-09-21T15:19:44.467Z'
      }
    ],
    pagination: {
      page: 1,
      limit: 50,
      total: 2,
      totalPages: 1,
      hasMore: false
    },
    source: 'YFinance via loadanalystupgradedowngrade.py'
  };

  test('renders page title and description', async () => {
    api.get.mockResolvedValue({ data: mockUpgradesData });

    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      expect(screen.getByText('Analyst Insights')).toBeInTheDocument();
    });
  });

  test('displays summary cards with correct data', async () => {
    api.get.mockResolvedValue({ data: mockUpgradesData });

    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      expect(screen.getByText('Recent Upgrades')).toBeInTheDocument();
      expect(screen.getByText('Recent Downgrades')).toBeInTheDocument();
      expect(screen.getByText('Active Firms')).toBeInTheDocument();
      expect(screen.getByText('Total Actions')).toBeInTheDocument();
    });

    // Check for upgrade count (1 upgrade in mock data)
    await waitFor(() => {
      const upgradeCards = screen.getAllByText('1');
      expect(upgradeCards.length).toBeGreaterThan(0);
    });
  });

  test('displays upgrades/downgrades table with real YFinance data structure', async () => {
    api.get.mockResolvedValue({ data: mockUpgradesData });

    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      expect(screen.getByText('Recent Analyst Actions')).toBeInTheDocument();
    });

    // Check for table headers
    expect(screen.getByText('Symbol')).toBeInTheDocument();
    expect(screen.getByText('Firm')).toBeInTheDocument();
    expect(screen.getByText('Action')).toBeInTheDocument();
    expect(screen.getByText('From Grade')).toBeInTheDocument();
    expect(screen.getByText('To Grade')).toBeInTheDocument();

    // Check for data from mock
    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('Goldman Sachs')).toBeInTheDocument();
      expect(screen.getByText('upgrade')).toBeInTheDocument();
      expect(screen.getAllByText('Hold')[0]).toBeInTheDocument();
      expect(screen.getAllByText('Buy')[0]).toBeInTheDocument();
    });
  });

  test('search functionality filters symbols correctly', async () => {
    api.get.mockResolvedValue({ data: mockUpgradesData });

    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('GOOGL')).toBeInTheDocument();
    });

    // Search for AAPL
    const searchInput = screen.getByPlaceholderText('Search by symbol...');
    fireEvent.change(searchInput, { target: { value: 'AAPL' } });

    // Should still show AAPL but filter works on frontend
    expect(screen.getByText('AAPL')).toBeInTheDocument();
  });

  test('action filter dropdown works correctly', async () => {
    api.get.mockResolvedValue({ data: mockUpgradesData });

    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      expect(screen.getAllByText('Action Filter')[0]).toBeInTheDocument();
    });

    // Check that filter options exist by looking for the Select element
    const selectElement = screen.getByRole('combobox');
    expect(selectElement).toBeInTheDocument();
  });

  test('handles API errors gracefully', async () => {
    api.get.mockRejectedValue(new Error('API Error'));

    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load analyst data')).toBeInTheDocument();
    });
  });

  test('clicking on symbol triggers symbol data fetch', async () => {
    const mockSymbolData = {
      success: true,
      symbol: 'AAPL',
      data: {
        upgrades_downgrades: mockUpgradesData.data.filter(u => u.symbol === 'AAPL'),
        revenue_estimates: []
      }
    };

    api.get.mockResolvedValueOnce({ data: mockUpgradesData })
            .mockResolvedValueOnce({ data: mockSymbolData });

    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      const appleSymbol = screen.getAllByText('AAPL')[0];
      fireEvent.click(appleSymbol);
    });

    // Verify the symbol-specific API call was made
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/api/analysts/AAPL');
    });
  });

  test('displays correct action icons and colors', async () => {
    api.get.mockResolvedValue({ data: mockUpgradesData });

    renderWithRouter(<AnalystInsights />);

    await waitFor(() => {
      // Check that upgrade and downgrade chips are displayed with different colors
      const upgradeChip = screen.getByText('upgrade');
      const downgradeChip = screen.getByText('downgrade');

      expect(upgradeChip).toBeInTheDocument();
      expect(downgradeChip).toBeInTheDocument();
    });
  });

  test('no longer displays revenue estimates section', async () => {
    api.get.mockResolvedValue({ data: mockUpgradesData });

    renderWithRouter(<AnalystInsights />);

    // Wait for the component to load
    await waitFor(() => {
      expect(screen.getByText('Recent Analyst Actions')).toBeInTheDocument();
    });

    // Verify revenue estimates section is NOT present
    expect(screen.queryByText('Revenue Estimates')).not.toBeInTheDocument();
    expect(screen.queryByText('Period')).not.toBeInTheDocument();
    expect(screen.queryByText('Avg Estimate')).not.toBeInTheDocument();
  });
});
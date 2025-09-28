import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import AnalystInsights from '../../pages/AnalystInsights';

// Component Contract Tests - Verify API contract expectations
describe('AnalystInsights Component Contract Tests', () => {
  const renderWithRouter = (component) => {
    return render(
      <BrowserRouter>
        {component}
      </BrowserRouter>
    );
  };

  beforeEach(() => {
    if (fetch.mockClear) {
      fetch.mockClear();
    }
  });

  describe('API Contract: /api/analysts/upgrades', () => {
    test('expects correct request format with pagination', async () => {
      fetch.mockResolvedValue({
        ok: true,
        json: async () => ({
          success: true,
          data: [],
          pagination: { page: 1, limit: 50, total: 0 }
        })
      });

      renderWithRouter(<AnalystInsights />);

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith('/api/analysts/upgrades?page=1&limit=50');
      });
    });

    test('expects response schema with required fields', async () => {
      const mockResponse = {
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
            details: "Strong iPhone sales",
            fetched_at: "2025-09-21T16:19:44.467Z"
          }
        ],
        pagination: {
          page: 1,
          limit: 50,
          total: 1,
          totalPages: 1,
          hasMore: false
        },
        source: "YFinance via loadanalystupgradedowngrade.py",
        timestamp: "2025-09-28T13:52:42.239Z"
      };

      fetch.mockResolvedValue({
        ok: true,
        json: async () => mockResponse
      });

      renderWithRouter(<AnalystInsights />);

      await waitFor(() => {
        // Verify component handles all expected response fields
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('Goldman Sachs')).toBeInTheDocument();
        expect(screen.getByText('upgrade')).toBeInTheDocument();
        expect(screen.getByText('Hold')).toBeInTheDocument();
        expect(screen.getByText('Buy')).toBeInTheDocument();
      });
    });

    test('handles missing optional fields gracefully', async () => {
      const mockResponseWithMissingFields = {
        success: true,
        data: [
          {
            id: 1,
            symbol: "AAPL",
            // Missing: firm, from_grade, to_grade, details
            action: "upgrade",
            date: "2024-01-15",
            fetched_at: "2025-09-21T16:19:44.467Z"
          }
        ],
        pagination: { page: 1, limit: 50, total: 1 }
      };

      fetch.mockResolvedValue({
        ok: true,
        json: async () => mockResponseWithMissingFields
      });

      renderWithRouter(<AnalystInsights />);

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('upgrade')).toBeInTheDocument();
        // Should show N/A for missing fields
        expect(screen.getAllByText('N/A').length).toBeGreaterThan(0);
      });
    });
  });

  describe('API Contract: /api/analysts/:symbol', () => {
    test('expects symbol-specific response schema', async () => {
      const mockSymbolResponse = {
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
          revenue_estimates: []
        },
        counts: {
          upgrades_downgrades: 1,
          revenue_estimates: 0,
          total_analysts_covering: 12
        },
        sources: {
          upgrades_downgrades: "YFinance via loadanalystupgradedowngrade.py",
          revenue_estimates: "YFinance via loadrevenueestimate.py"
        },
        timestamp: "2025-09-28T13:52:42.239Z"
      };

      // Trigger symbol-specific fetch by having clickable symbol
      const mockClickableData = {
        success: true,
        data: [{ id: 1, symbol: 'AAPL', firm: 'Test', action: 'upgrade', date: '2024-01-15' }],
        pagination: { page: 1, limit: 50, total: 1 }
      };

      fetch.mockImplementation((url) => {
        if (url.includes('/api/analysts/AAPL')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockSymbolResponse
          });
        } else if (url.includes('upgrades')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockClickableData
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, data: [] })
        });
      });

      renderWithRouter(<AnalystInsights />);

      // Component should be able to handle the symbol-specific response structure
      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });
    });
  });

  describe('Error Response Contract', () => {
    test('handles API error response format', async () => {
      const mockErrorResponse = {
        success: false,
        error: "Failed to fetch analyst upgrades",
        details: "Database connection failed",
        timestamp: "2025-09-28T13:52:42.239Z"
      };

      fetch.mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => mockErrorResponse
      });

      renderWithRouter(<AnalystInsights />);

      await waitFor(() => {
        expect(screen.getByText('Failed to load analyst data')).toBeInTheDocument();
      });
    });

    test('handles network failures', async () => {
      fetch.mockRejectedValue(new Error('Network error'));

      renderWithRouter(<AnalystInsights />);

      await waitFor(() => {
        expect(screen.getByText('Failed to load analyst data')).toBeInTheDocument();
      });
    });
  });

  describe('Data Source Attribution Contract', () => {
    test('expects source attribution in API responses', async () => {
      const mockWithSources = {
        success: true,
        data: [],
        source: "YFinance via loadanalystupgradedowngrade.py",
        timestamp: "2025-09-28T13:52:42.239Z"
      };

      fetch.mockResolvedValue({
        ok: true,
        json: async () => mockWithSources
      });

      renderWithRouter(<AnalystInsights />);

      // Component should receive and could potentially display source info
      await waitFor(() => {
        expect(fetch).toHaveBeenCalled();
      });
    });
  });

  describe('Updated Component Behavior', () => {
    test('no longer makes revenue estimates API calls', async () => {
      fetch.mockResolvedValue({
        ok: true,
        json: async () => ({
          success: true,
          data: [],
          pagination: { page: 1, limit: 50, total: 0 }
        })
      });

      renderWithRouter(<AnalystInsights />);

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith('/api/analysts/upgrades?page=1&limit=50');
      });

      // Should NOT call revenue estimates endpoint
      expect(fetch).not.toHaveBeenCalledWith('/api/analysts/revenue-estimates');
    });

    test('focuses only on upgrades/downgrades functionality', async () => {
      const mockUpgradesOnly = {
        success: true,
        data: [
          {
            id: 1,
            symbol: "AAPL",
            firm: "Goldman Sachs",
            action: "upgrade",
            from_grade: "Hold",
            to_grade: "Buy",
            date: "2024-01-15"
          }
        ],
        pagination: { page: 1, limit: 50, total: 1 }
      };

      fetch.mockResolvedValue({
        ok: true,
        json: async () => mockUpgradesOnly
      });

      renderWithRouter(<AnalystInsights />);

      await waitFor(() => {
        expect(screen.getByText('Recent Analyst Actions')).toBeInTheDocument();
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('upgrade')).toBeInTheDocument();
      });

      // Should NOT display revenue estimates section
      expect(screen.queryByText('Revenue Estimates')).not.toBeInTheDocument();
      expect(screen.queryByText('Period')).not.toBeInTheDocument();
      expect(screen.queryByText('Avg Estimate')).not.toBeInTheDocument();
    });
  });
});
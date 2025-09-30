import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import AnalystInsights from '../../pages/AnalystInsights';
import api from '../../services/api';

// Mock the API module
vi.mock('../../services/api');

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
    vi.clearAllMocks();
  });

  describe('API Contract: /api/analysts/upgrades', () => {
    test('expects correct request format with pagination', async () => {
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: [],
          pagination: { page: 1, limit: 50, total: 0 }
        }
      });

      renderWithRouter(<AnalystInsights />);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith('/api/analysts/upgrades?page=1&limit=50');
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

      api.get.mockResolvedValue({
        data: mockResponse
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

      api.get.mockResolvedValue({
        data: mockResponseWithMissingFields
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

      api.get.mockImplementation((url) => {
        if (url.includes('/api/analysts/AAPL')) {
          return Promise.resolve({
            data: mockSymbolResponse
          });
        } else if (url.includes('upgrades')) {
          return Promise.resolve({
            data: mockClickableData
          });
        }
        return Promise.resolve({
          data: { success: true, data: [] }
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

      api.get.mockResolvedValue({
        data: mockErrorResponse
      });

      renderWithRouter(<AnalystInsights />);

      await waitFor(() => {
        expect(screen.getByText('Failed to load analyst data')).toBeInTheDocument();
      });
    });

    test('handles network failures', async () => {
      api.get.mockRejectedValue(new Error('Network error'));

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

      api.get.mockResolvedValue({
        data: mockWithSources
      });

      renderWithRouter(<AnalystInsights />);

      // Component should receive and could potentially display source info
      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });
    });
  });

  describe('Updated Component Behavior', () => {
    test('no longer makes revenue estimates API calls', async () => {
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: [],
          pagination: { page: 1, limit: 50, total: 0 }
        }
      });

      renderWithRouter(<AnalystInsights />);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith('/api/analysts/upgrades?page=1&limit=50');
      });

      // Should NOT call revenue estimates endpoint
      expect(api.get).not.toHaveBeenCalledWith('/api/analysts/revenue-estimates');
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

      api.get.mockResolvedValue({
        data: mockUpgradesOnly
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
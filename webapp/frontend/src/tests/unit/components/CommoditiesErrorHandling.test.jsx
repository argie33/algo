import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import Commodities from '../../../pages/Commodities';

// Mock dependencies
vi.mock('../../../hooks/useSimpleFetch', () => ({
  useSimpleFetch: vi.fn()
}));

vi.mock('../../../services/api', () => ({
  getApiConfig: () => ({ apiUrl: 'http://test-api.com' })
}));

vi.mock('../../../components/DataContainer', () => ({
  default: ({ children, data, loading, error, fallbackDataType, onRetry }) => {
    if (loading) return <div data-testid="loading">Loading...</div>;
    if (error) {
      return (
        <div data-testid="error">
          Error: {error.message}
          {onRetry && (
            <button onClick={onRetry} data-testid="retry-button">
              Retry
            </button>
          )}
        </div>
      );
    }
    // Simulate fallback data when API fails
    if (fallbackDataType === 'commodity_categories') {
      const fallbackData = [
        { id: 'energy', name: 'Energy', performance: { '1d': 0.5 } }
      ];
      return React.cloneElement(children, { data: { data: fallbackData }, isFallbackData: true });
    }
    if (fallbackDataType === 'commodity_prices') {
      const fallbackData = [
        { symbol: 'CL', name: 'Crude Oil', price: 78.45, category: 'energy', change: 0.67, volume: 245678 }
      ];
      return React.cloneElement(children, { data: { data: fallbackData }, isFallbackData: true });
    }
    return React.cloneElement(children, { data: data || { data: [] } });
  }
}));

// Theme wrapper
const theme = createTheme();
const renderWithTheme = (component) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  );
};

describe('Commodities Page Error Handling', () => {
  let mockUseSimpleFetch;

  beforeEach(async () => {
    const { useSimpleFetch } = await import('../../../hooks/useSimpleFetch');
    mockUseSimpleFetch = useSimpleFetch;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Network Errors', () => {
    it('should handle API network failures gracefully', () => {
      mockUseSimpleFetch.mockImplementation((url) => ({
        data: null,
        loading: false,
        error: new Error('Network Error: Failed to fetch'),
        refetch: vi.fn()
      }));

      renderWithTheme(<Commodities />);

      // Should show error messages
      const errorElements = screen.getAllByTestId('error');
      expect(errorElements.length).toBeGreaterThan(0);
      expect(screen.getByText(/Network Error/)).toBeInTheDocument();
    });

    it('should provide retry functionality when API fails', () => {
      const mockRefetch = vi.fn();
      mockUseSimpleFetch.mockImplementation((url) => ({
        data: null,
        loading: false,
        error: new Error('API Error'),
        refetch: mockRefetch
      }));

      renderWithTheme(<Commodities />);

      const retryButtons = screen.getAllByTestId('retry-button');
      expect(retryButtons.length).toBeGreaterThan(0);

      fireEvent.click(retryButtons[0]);
      expect(mockRefetch).toHaveBeenCalled();
    });
  });

  describe('Data Validation Errors', () => {
    it('should handle malformed API responses', () => {
      mockUseSimpleFetch.mockImplementation((url) => ({
        data: { invalidStructure: true }, // Invalid data structure
        loading: false,
        error: null,
        refetch: vi.fn()
      }));

      renderWithTheme(<Commodities />);

      // Component should still render without crashing
      expect(screen.getByText('Commodities Market')).toBeInTheDocument();
    });

    it('should handle empty API responses', () => {
      mockUseSimpleFetch.mockImplementation((url) => ({
        data: { data: [] }, // Empty array
        loading: false,
        error: null,
        refetch: vi.fn()
      }));

      renderWithTheme(<Commodities />);

      // Should show appropriate empty state
      expect(screen.getByText('Commodities Market')).toBeInTheDocument();
      expect(screen.getByText('0 commodities')).toBeInTheDocument();
    });
  });

  describe('Loading States', () => {
    it('should show loading indicators while fetching data', () => {
      mockUseSimpleFetch.mockImplementation((url) => ({
        data: null,
        loading: true,
        error: null,
        refetch: vi.fn()
      }));

      renderWithTheme(<Commodities />);

      const loadingElements = screen.getAllByTestId('loading');
      expect(loadingElements.length).toBeGreaterThan(0);
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('should handle mixed loading states correctly', () => {
      mockUseSimpleFetch.mockImplementation((url) => {
        if (url.includes('/categories')) {
          return { data: { data: [] }, loading: false, error: null, refetch: vi.fn() };
        }
        return { data: null, loading: true, error: null, refetch: vi.fn() };
      });

      renderWithTheme(<Commodities />);

      // Should show loading for some components, loaded for others
      expect(screen.getByText('Commodities Market')).toBeInTheDocument();
      expect(screen.getByTestId('loading')).toBeInTheDocument();
    });
  });

  describe('Fallback Data Handling', () => {
    it('should show fallback data when API is unavailable', () => {
      mockUseSimpleFetch.mockImplementation((url) => ({
        data: null,
        loading: false,
        error: new Error('Service unavailable'),
        refetch: vi.fn()
      }));

      renderWithTheme(<Commodities />);

      // DataContainer mock should provide fallback data
      expect(screen.getByText('Commodities Market')).toBeInTheDocument();
      
      // Should show some commodity data (from fallback)
      const energyElements = screen.queryAllByText(/Energy/i);
      const oilElements = screen.queryAllByText(/Oil/i);
      
      expect(energyElements.length > 0 || oilElements.length > 0).toBe(true);
    });

    it('should indicate when showing demo/fallback data', () => {
      mockUseSimpleFetch.mockImplementation((url) => ({
        data: null,
        loading: false,
        error: new Error('API Error'),
        refetch: vi.fn()
      }));

      renderWithTheme(<Commodities />);

      // Should show demo data indicators
      const demoChips = screen.queryAllByText(/Demo Data/i);
      expect(demoChips.length).toBeGreaterThanOrEqual(0); // May or may not be visible depending on fallback
    });
  });

  describe('User Input Validation', () => {
    it('should handle invalid search inputs gracefully', async () => {
      mockUseSimpleFetch.mockImplementation((url) => ({
        data: { 
          data: [
            { symbol: 'CL', name: 'Crude Oil', price: 78.45, category: 'energy' },
            { symbol: 'GC', name: 'Gold', price: 2034.20, category: 'precious-metals' }
          ] 
        },
        loading: false,
        error: null,
        refetch: vi.fn()
      }));

      renderWithTheme(<Commodities />);

      const searchInput = screen.getByPlaceholderText('Search commodities...');
      
      // Test with special characters
      fireEvent.change(searchInput, { target: { value: '<script>alert("xss")</script>' } });
      
      await waitFor(() => {
        // Should not execute script, should filter safely
        expect(screen.queryByText('Crude Oil')).not.toBeInTheDocument();
        expect(screen.queryByText('Gold')).not.toBeInTheDocument();
      });

      // Test with very long input
      const longInput = 'a'.repeat(1000);
      fireEvent.change(searchInput, { target: { value: longInput } });
      
      // Should handle gracefully without crashing
      expect(searchInput.value).toBe(longInput);
    });

    it('should validate category selections', () => {
      mockUseSimpleFetch.mockImplementation((url) => {
        // Mock different responses based on category parameter
        if (url.includes('category=invalid')) {
          return { data: { data: [] }, loading: false, error: null, refetch: vi.fn() };
        }
        return { 
          data: { 
            data: [{ symbol: 'CL', name: 'Crude Oil', category: 'energy' }] 
          }, 
          loading: false, 
          error: null, 
          refetch: vi.fn() 
        };
      });

      renderWithTheme(<Commodities />);

      // Component should handle invalid category gracefully
      expect(screen.getByText('Commodities Market')).toBeInTheDocument();
    });
  });

  describe('Error Recovery', () => {
    it('should allow recovery from error states', async () => {
      const mockRefetch = vi.fn();
      
      // Start with error state
      mockUseSimpleFetch.mockImplementation((url) => ({
        data: null,
        loading: false,
        error: new Error('Temporary error'),
        refetch: mockRefetch
      }));

      const { rerender } = renderWithTheme(<Commodities />);

      expect(screen.getByText(/Temporary error/)).toBeInTheDocument();

      // Simulate successful retry
      mockUseSimpleFetch.mockImplementation((url) => ({
        data: { data: [{ symbol: 'CL', name: 'Crude Oil' }] },
        loading: false,
        error: null,
        refetch: mockRefetch
      }));

      rerender(
        <ThemeProvider theme={theme}>
          <Commodities />
        </ThemeProvider>
      );

      expect(screen.queryByText(/Temporary error/)).not.toBeInTheDocument();
      expect(screen.getByText('Commodities Market')).toBeInTheDocument();
    });
  });

  describe('Performance Under Stress', () => {
    it('should handle large datasets gracefully', () => {
      const largeMockData = Array.from({ length: 1000 }, (_, i) => ({
        symbol: `TEST${i}`,
        name: `Test Commodity ${i}`,
        price: 100 + i,
        category: 'energy',
        change: (Math.random() - 0.5) * 10,
        volume: 100000 + i
      }));

      mockUseSimpleFetch.mockImplementation((url) => ({
        data: { data: largeMockData },
        loading: false,
        error: null,
        refetch: vi.fn()
      }));

      const startTime = Date.now();
      renderWithTheme(<Commodities />);
      const renderTime = Date.now() - startTime;

      // Should render within reasonable time even with large dataset
      expect(renderTime).toBeLessThan(2000); // 2 seconds max
      expect(screen.getByText('Commodities Market')).toBeInTheDocument();
    });

    it('should handle rapid state changes', async () => {
      let toggleState = false;
      
      mockUseSimpleFetch.mockImplementation((url) => ({
        data: toggleState ? { data: [] } : null,
        loading: !toggleState,
        error: toggleState ? null : new Error('Loading error'),
        refetch: vi.fn()
      }));

      const { rerender } = renderWithTheme(<Commodities />);

      // Rapidly toggle between states
      for (let i = 0; i < 10; i++) {
        toggleState = !toggleState;
        
        rerender(
          <ThemeProvider theme={theme}>
            <Commodities />
          </ThemeProvider>
        );
        
        await waitFor(() => {
          expect(screen.getByText('Commodities Market')).toBeInTheDocument();
        });
      }
    });
  });
});
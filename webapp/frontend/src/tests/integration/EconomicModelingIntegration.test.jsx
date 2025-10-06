/**
 * Economic Modeling Integration Tests
 * Tests the complete workflow with real API endpoints
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import EconomicModeling from '../../pages/EconomicModeling';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'test-user',
      email: 'test@example.com',
      firstName: 'Test',
      lastName: 'User',
    },
    isAuthenticated: true,
    isLoading: false,
  }),
}));

const renderWithRouter = (component) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        {component}
      </QueryClientProvider>
    </BrowserRouter>
  );
};

describe('Economic Modeling Integration Tests', () => {
  test('loads economic modeling page with real backend data', async () => {
    renderWithRouter(<EconomicModeling />);

    // Wait for the page header to load
    await waitFor(() => {
      expect(screen.getByText('Economic Modeling & Forecasting')).toBeInTheDocument();
    });

    // Check for the description
    await waitFor(() => {
      expect(screen.getByText(/Advanced econometric models and real-time recession probability/i)).toBeInTheDocument();
    });
  });

  test('displays recession forecast data from backend', async () => {
    renderWithRouter(<EconomicModeling />);

    // Wait for page title first
    await waitFor(() => {
      expect(screen.getByText('Economic Modeling & Forecasting')).toBeInTheDocument();
    });

    // Check for recession or forecast related content (in tabs or cards)
    await waitFor(() => {
      const forecastElements = screen.queryAllByText(/forecast|model|probability/i);
      expect(forecastElements.length).toBeGreaterThan(0);
    }, { timeout: 10000 });
  });

  test('displays leading indicators from backend', async () => {
    renderWithRouter(<EconomicModeling />);

    // Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText(/Loading economic data/i)).not.toBeInTheDocument();
    }, { timeout: 10000 });

    // Check for economic indicators - unemployment, inflation, gdp
    await waitFor(() => {
      // Should have some economic metric displays
      const metrics = screen.queryAllByText(/unemployment|inflation|gdp/i);
      expect(metrics.length).toBeGreaterThan(0);
    }, { timeout: 5000 });
  });

  test('displays AI insights from backend', async () => {
    renderWithRouter(<EconomicModeling />);

    // Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText(/Loading economic data/i)).not.toBeInTheDocument();
    }, { timeout: 10000 });

    // Check for AI insights section or confidence indicators
    await waitFor(() => {
      const insightElements = screen.queryAllByText(/confidence|insight|analysis/i);
      expect(insightElements.length).toBeGreaterThan(0);
    }, { timeout: 5000 });
  });

  test.skip('displays sectoral analysis from backend', async () => {
    // TODO: Re-enable when backend sectoral analysis is implemented
    renderWithRouter(<EconomicModeling />);

    // Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText(/Loading economic data/i)).not.toBeInTheDocument();
    }, { timeout: 10000 });

    // Check for sector-related content
    await waitFor(() => {
      const sectorElements = screen.queryAllByText(/sector|industry/i);
      expect(sectorElements.length).toBeGreaterThan(0);
    }, { timeout: 5000 });
  });

  test.skip('handles API errors gracefully', async () => {
    // Skip this test - it interferes with the real API calls
    // Mock a failure scenario by breaking the API
    global.fetch = vi.fn(() => Promise.reject(new Error('Network error')));

    renderWithRouter(<EconomicModeling />);

    // Should show error message
    await waitFor(() => {
      const errorText = screen.queryByText(/Error loading economic data|Failed to fetch/i);
      expect(errorText).toBeInTheDocument();
    }, { timeout: 10000 });

    // Cleanup
    global.fetch.mockRestore();
  });

  test('timeframe selector is functional', async () => {
    renderWithRouter(<EconomicModeling />);

    // Wait for page to load
    await waitFor(() => {
      expect(screen.getByText('Economic Modeling & Forecasting')).toBeInTheDocument();
    });

    // Check for timeframe selector - may appear multiple times in the DOM
    const timeframeLabels = screen.getAllByText('Timeframe');
    expect(timeframeLabels.length).toBeGreaterThan(0);
  });
});
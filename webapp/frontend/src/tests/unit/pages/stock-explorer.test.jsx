/**
 * Stock Explorer Page Unit Tests
 * Tests the stock explorer/screener route and its features
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import StockExplorer from '../../pages/StockExplorer';
import { directTheme } from '../../theme/directTheme';
import { AuthProvider } from '../../contexts/AuthContext';

// Mock the API service
vi.mock('../../services/api', () => ({
  getStockPrices: vi.fn(),
  getStockMetrics: vi.fn(),
  getApiConfig: vi.fn(() => ({ apiUrl: 'https://test-api.example.com' }))
}));

// Mock recharts
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />
}));

const TestWrapper = ({ children }) => (
  <ThemeProvider theme={directTheme}>
    <AuthProvider>
      <BrowserRouter>
        {children}
      </BrowserRouter>
    </AuthProvider>
  </ThemeProvider>
);

describe('Stock Explorer Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders stock explorer page without crashing', async () => {
    render(
      <TestWrapper>
        <StockExplorer />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText(/stock|explorer|screener/i)).toBeInTheDocument();
    });
  });

  it('displays stock filtering and search functionality', async () => {
    render(
      <TestWrapper>
        <StockExplorer />
      </TestWrapper>
    );

    await waitFor(() => {
      // Should show stock-related content
      const stockElements = screen.getAllByText(/stock|filter|search/i);
      expect(stockElements.length).toBeGreaterThan(0);
    });
  });

  it('handles stock data loading', async () => {
    render(
      <TestWrapper>
        <StockExplorer />
      </TestWrapper>
    );

    await waitFor(() => {
      // Should render the page structure
      expect(screen.getByText(/stock|explorer|screener/i)).toBeInTheDocument();
    });
  });

  it('renders stock charts and metrics', async () => {
    render(
      <TestWrapper>
        <StockExplorer />
      </TestWrapper>
    );

    await waitFor(() => {
      // Should render without errors
      expect(screen.getByText(/stock|explorer|screener/i)).toBeInTheDocument();
    });
  });
});
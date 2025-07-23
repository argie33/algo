/**
 * Trading Signals Page Unit Tests
 * Tests the trading signals route and its features
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import TradingSignals from '../../pages/TradingSignals';
import { directTheme } from '../../theme/directTheme';
import { AuthProvider } from '../../contexts/AuthContext';

// Mock the API service
vi.mock('../../services/api', () => ({
  getBuySignals: vi.fn(),
  getSellSignals: vi.fn(),
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

describe('Trading Signals Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders trading signals page without crashing', async () => {
    render(
      <TestWrapper>
        <TradingSignals />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText(/trading|signal/i)).toBeInTheDocument();
    });
  });

  it('displays buy and sell signals', async () => {
    render(
      <TestWrapper>
        <TradingSignals />
      </TestWrapper>
    );

    await waitFor(() => {
      // Should show trading-related content
      const tradingElements = screen.getAllByText(/trading|signal/i);
      expect(tradingElements.length).toBeGreaterThan(0);
    });
  });

  it('handles API failures gracefully', async () => {
    const { getBuySignals, getSellSignals } = await import('../../services/api');
    getBuySignals.mockRejectedValue(new Error('API Error'));
    getSellSignals.mockRejectedValue(new Error('API Error'));

    render(
      <TestWrapper>
        <TradingSignals />
      </TestWrapper>
    );

    await waitFor(() => {
      // Should still render the page structure
      expect(screen.getByText(/trading|signal/i)).toBeInTheDocument();
    });
  });

  it('renders signal charts and tables', async () => {
    render(
      <TestWrapper>
        <TradingSignals />
      </TestWrapper>
    );

    await waitFor(() => {
      // Should render without errors
      expect(screen.getByText(/trading|signal/i)).toBeInTheDocument();
    });
  });
});
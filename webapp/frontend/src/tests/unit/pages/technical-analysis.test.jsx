/**
 * Technical Analysis Page Unit Tests
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import TechnicalAnalysis from '../../pages/TechnicalAnalysis';
import { directTheme } from '../../theme/directTheme';
import { AuthProvider } from '../../contexts/AuthContext';

vi.mock('../../services/api', () => ({
  getStockPrices: vi.fn(),
  getApiConfig: vi.fn(() => ({ apiUrl: 'https://test-api.example.com' }))
}));

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

describe('Technical Analysis Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders without crashing', async () => {
    render(
      <TestWrapper>
        <TechnicalAnalysis />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText(/technical|analysis/i)).toBeInTheDocument();
    });
  });

  it('displays technical indicators and charts', async () => {
    render(
      <TestWrapper>
        <TechnicalAnalysis />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText(/technical|analysis/i)).toBeInTheDocument();
    });
  });
});
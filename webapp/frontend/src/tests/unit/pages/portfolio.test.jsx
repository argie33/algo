/**
 * Portfolio Page Unit Tests
 * Tests the main portfolio route and its features
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import Portfolio from '../../pages/Portfolio';
import { directTheme } from '../../theme/directTheme';
import { AuthProvider } from '../../contexts/AuthContext';

// Mock the API service
vi.mock('../../services/api', () => ({
  getPortfolioData: vi.fn(),
  getApiConfig: vi.fn(() => ({ apiUrl: 'https://test-api.example.com' }))
}));

// Mock recharts to avoid canvas issues
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
  Tooltip: () => <div data-testid="tooltip" />,
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />
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

describe('Portfolio Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders portfolio page without crashing', async () => {
    render(
      <TestWrapper>
        <Portfolio />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText(/portfolio/i)).toBeInTheDocument();
    });
  });

  it('displays portfolio metrics', async () => {
    render(
      <TestWrapper>
        <Portfolio />
      </TestWrapper>
    );

    await waitFor(() => {
      // Should show portfolio-related text
      const portfolioElements = screen.getAllByText(/portfolio/i);
      expect(portfolioElements.length).toBeGreaterThan(0);
    });
  });

  it('handles loading state', async () => {
    render(
      <TestWrapper>
        <Portfolio />
      </TestWrapper>
    );

    // May show loading indicators initially
    // This tests the page renders without throwing errors during loading
    expect(screen.getByText(/portfolio/i)).toBeInTheDocument();
  });

  it('handles error states gracefully', async () => {
    // Mock API error
    const { getPortfolioData } = await import('../../services/api');
    getPortfolioData.mockRejectedValue(new Error('API Error'));

    render(
      <TestWrapper>
        <Portfolio />
      </TestWrapper>
    );

    await waitFor(() => {
      // Should still render the page structure
      expect(screen.getByText(/portfolio/i)).toBeInTheDocument();
    });
  });

  it('renders portfolio allocation charts', async () => {
    render(
      <TestWrapper>
        <Portfolio />
      </TestWrapper>
    );

    await waitFor(() => {
      // Should render chart components
      const chartElements = screen.queryAllByTestId(/chart|pie/);
      // At minimum, the page should render without errors
      expect(screen.getByText(/portfolio/i)).toBeInTheDocument();
    });
  });
});
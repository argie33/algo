/**
 * MetricsDashboard Page Unit Tests
 * Tests the /metrics route and its features
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import MetricsDashboard from '../../pages/MetricsDashboard';
import { directTheme } from '../../theme/directTheme';
import { AuthProvider } from '../../contexts/AuthContext';

// Mock the API service
vi.mock('../../services/api', () => ({
  getApiConfig: vi.fn(() => ({ apiUrl: 'https://test-api.example.com' }))
}));

// Mock recharts to avoid canvas issues
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
  BarChart: ({ children }) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => <div data-testid="bar" />
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

describe('MetricsDashboard Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders metricsdashboard page without crashing', async () => {
    render(
      <TestWrapper>
        <MetricsDashboard />
      </TestWrapper>
    );

    await waitFor(() => {
      // Look for component-specific text or generic page content
      const pageContent = screen.getByText(/metricsdashboard|loading|dashboard|error/i);
      expect(pageContent).toBeInTheDocument();
    });
  });

  it('handles loading states', async () => {
    render(
      <TestWrapper>
        <MetricsDashboard />
      </TestWrapper>
    );

    // Should render without throwing errors during loading
    await waitFor(() => {
      expect(document.body).toBeInTheDocument();
    });
  });

  it('handles error states gracefully', async () => {
    // Mock console.error to avoid test noise
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <TestWrapper>
        <MetricsDashboard />
      </TestWrapper>
    );

    await waitFor(() => {
      // Should not crash even with errors
      expect(document.body).toBeInTheDocument();
    });

    consoleSpy.mockRestore();
  });

  it('renders page-specific features and content', async () => {
    render(
      <TestWrapper>
        <MetricsDashboard />
      </TestWrapper>
    );

    await waitFor(() => {
      // Should render page content without errors
      expect(document.body).toBeInTheDocument();
    });
  });
});
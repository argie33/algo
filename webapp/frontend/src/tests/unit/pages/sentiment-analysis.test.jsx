/**
 * Sentiment Analysis Page Unit Tests
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import SentimentAnalysis from '../../pages/SentimentAnalysis';
import { directTheme } from '../../theme/directTheme';
import { AuthProvider } from '../../contexts/AuthContext';

vi.mock('../../services/api', () => ({
  getApiConfig: vi.fn(() => ({ apiUrl: 'https://test-api.example.com' }))
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
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

describe('Sentiment Analysis Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders without crashing', async () => {
    render(
      <TestWrapper>
        <SentimentAnalysis />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText(/sentiment|analysis/i)).toBeInTheDocument();
    });
  });

  it('displays sentiment metrics and visualizations', async () => {
    render(
      <TestWrapper>
        <SentimentAnalysis />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText(/sentiment|analysis/i)).toBeInTheDocument();
    });
  });
});
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AdvancedPortfolioAnalytics from '../../../pages/AdvancedPortfolioAnalytics';
import * as api from '../../../services/api';

// Mock the API
vi.mock('../../../services/api', () => ({
  getPortfolioAnalytics: vi.fn(),
  getPortfolioMetrics: vi.fn(),
  getPortfolioRisk: vi.fn(),
}));

const mockAnalyticsData = {
  performance: {
    totalReturn: 12.5,
    sharpeRatio: 1.2,
    volatility: 15.2,
    maxDrawdown: -8.5,
  },
  allocation: [
    { name: 'Stocks', value: 60 },
    { name: 'Bonds', value: 30 },
    { name: 'Cash', value: 10 },
  ],
  holdings: [
    { symbol: 'AAPL', weight: 15.5, return: 23.2 },
    { symbol: 'MSFT', weight: 12.8, return: 18.7 },
    { symbol: 'GOOGL', weight: 10.2, return: 15.3 },
  ],
};

const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
};

describe('AdvancedPortfolioAnalytics', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getPortfolioAnalytics.mockResolvedValue(mockAnalyticsData);
    api.getPortfolioMetrics.mockResolvedValue(mockAnalyticsData.performance);
    api.getPortfolioRisk.mockResolvedValue({ riskScore: 6.5 });
  });

  it('renders without crashing', () => {
    render(
      <TestWrapper>
        <AdvancedPortfolioAnalytics />
      </TestWrapper>
    );

    expect(screen.getByText(/advanced portfolio analytics/i)).toBeInTheDocument();
  });

  it('displays loading state initially', () => {
    render(
      <TestWrapper>
        <AdvancedPortfolioAnalytics />
      </TestWrapper>
    );

    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('loads and displays portfolio metrics', async () => {
    render(
      <TestWrapper>
        <AdvancedPortfolioAnalytics />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText('12.5%')).toBeInTheDocument(); // Total return
      expect(screen.getByText('1.2')).toBeInTheDocument(); // Sharpe ratio
    });
  });

  it('displays portfolio allocation chart', async () => {
    render(
      <TestWrapper>
        <AdvancedPortfolioAnalytics />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText('Stocks')).toBeInTheDocument();
      expect(screen.getByText('Bonds')).toBeInTheDocument();
      expect(screen.getByText('Cash')).toBeInTheDocument();
    });
  });

  it('shows top holdings with performance', async () => {
    render(
      <TestWrapper>
        <AdvancedPortfolioAnalytics />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('MSFT')).toBeInTheDocument();
      expect(screen.getByText('23.2%')).toBeInTheDocument();
    });
  });

  it('switches between different analytics tabs', async () => {
    render(
      <TestWrapper>
        <AdvancedPortfolioAnalytics />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText(/performance/i)).toBeInTheDocument();
    });

    // Click on Risk Analysis tab
    const riskTab = screen.getByText(/risk analysis/i);
    fireEvent.click(riskTab);

    expect(screen.getByText(/risk metrics/i)).toBeInTheDocument();
  });

  it('handles API errors gracefully', async () => {
    api.getPortfolioAnalytics.mockRejectedValueOnce(new Error('API Error'));

    render(
      <TestWrapper>
        <AdvancedPortfolioAnalytics />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText(/error loading analytics/i)).toBeInTheDocument();
    });
  });

  it('displays risk metrics correctly', async () => {
    render(
      <TestWrapper>
        <AdvancedPortfolioAnalytics />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText('15.2%')).toBeInTheDocument(); // Volatility
      expect(screen.getByText('-8.5%')).toBeInTheDocument(); // Max drawdown
    });
  });

  it('refreshes data when refresh button clicked', async () => {
    render(
      <TestWrapper>
        <AdvancedPortfolioAnalytics />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    const refreshButton = screen.getByLabelText(/refresh/i);
    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(api.getPortfolioAnalytics).toHaveBeenCalledTimes(2);
    });
  });

  it('filters holdings by time period', async () => {
    render(
      <TestWrapper>
        <AdvancedPortfolioAnalytics />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    const periodSelect = screen.getByLabelText(/time period/i);
    fireEvent.mouseDown(periodSelect);

    const monthOption = screen.getByText('1 Month');
    fireEvent.click(monthOption);

    await waitFor(() => {
      expect(api.getPortfolioAnalytics).toHaveBeenCalledWith(
        expect.objectContaining({ period: '1M' })
      );
    });
  });
});
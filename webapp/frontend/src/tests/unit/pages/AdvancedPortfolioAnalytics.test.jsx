import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AdvancedPortfolioAnalytics from '../../../pages/AdvancedPortfolioAnalytics';
import * as api from '../../../services/api';

// Mock the API
vi.mock('../../../services/api', () => ({
  getPerformanceAnalytics: vi.fn(),
  getRiskAnalytics: vi.fn(),
  getCorrelationAnalytics: vi.fn(),
  getAllocationAnalytics: vi.fn(),
  getReturnsAnalytics: vi.fn(),
  getSectorsAnalytics: vi.fn(),
  getVolatilityAnalytics: vi.fn(),
  getTrendsAnalytics: vi.fn(),
  exportAnalytics: vi.fn(),
}));

const mockPerformanceData = {
  data: {
    returns: 0.125, // 12.5%
    volatility: 0.152, // 15.2%
    sharpe_ratio: 1.2,
    portfolio_metrics: {
      total_value: 102500,
      top_performers: [
        { symbol: 'AAPL', return_percent: 23.2 },
        { symbol: 'MSFT', return_percent: 18.7 },
        { symbol: 'GOOGL', return_percent: 15.3 },
      ]
    },
    performance_timeline: [],
    benchmark_comparison: { data: [] }
  }
};

const mockRiskData = {
  data: {
    risk: {
      risk_assessment: { overall_risk: 'Medium' },
      portfolio_metrics: {
        portfolio_volatility: 15.2,
        max_drawdown: -8.5,
        value_at_risk_95: -5.2,
        concentration_risk: 'Low'
      },
      position_analysis: {
        position_breakdown: [
          { symbol: 'AAPL', position_weight: 15.5, unrealized_return: 23.2 },
          { symbol: 'MSFT', position_weight: 12.8, unrealized_return: 18.7 }
        ]
      }
    }
  }
};

const mockAllocationData = {
  data: {
    sectors: [
      { name: 'Technology', percentage: 60 },
      { name: 'Healthcare', percentage: 30 },
      { name: 'Finance', percentage: 10 }
    ],
    assets: [
      { symbol: 'AAPL', percentage: 15.5, shares: 100, sector: 'Technology', value: 15000 },
      { symbol: 'MSFT', percentage: 12.8, shares: 80, sector: 'Technology', value: 12000 }
    ]
  }
};

const mockCorrelationData = {
  data: {
    correlations: {
      insights: {
        diversification_score: 8.5,
        average_correlation: 0.35,
        assets_analyzed: 10,
        highest_correlation: { pair: ['AAPL', 'MSFT'], value: 0.85 },
        lowest_correlation: { pair: ['AAPL', 'GLD'], value: -0.12 }
      }
    }
  }
};

const mockVolatilityData = {
  data: {
    volatility: {
      annualized_volatility: 15.2,
      risk_level: 'Medium',
      returns_data: []
    }
  }
};

const mockTrendsData = {
  data: {
    trends: {
      trend_direction: 'Upward',
      trend_strength: 'Strong'
    }
  }
};

const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
    logger: {
      log: () => {},
      warn: () => {},
      error: () => {},
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
    api.getPerformanceAnalytics.mockResolvedValue(mockPerformanceData);
    api.getRiskAnalytics.mockResolvedValue(mockRiskData);
    api.getCorrelationAnalytics.mockResolvedValue(mockCorrelationData);
    api.getAllocationAnalytics.mockResolvedValue(mockAllocationData);
    api.getReturnsAnalytics.mockResolvedValue({ data: {} });
    api.getSectorsAnalytics.mockResolvedValue({ data: {} });
    api.getVolatilityAnalytics.mockResolvedValue(mockVolatilityData);
    api.getTrendsAnalytics.mockResolvedValue(mockTrendsData);
    api.exportAnalytics.mockResolvedValue({});
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

    // Click on Asset Allocation tab first
    const allocationTab = screen.getByText('Asset Allocation');
    fireEvent.click(allocationTab);

    await waitFor(() => {
      expect(screen.getByText('Technology')).toBeInTheDocument();
      expect(screen.getByText('Healthcare')).toBeInTheDocument();
      expect(screen.getByText('Finance')).toBeInTheDocument();
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
    api.getPerformanceAnalytics.mockRejectedValueOnce(new Error('API Error'));

    render(
      <TestWrapper>
        <AdvancedPortfolioAnalytics />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText(/Failed to load performance data/i)).toBeInTheDocument();
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

    const refreshButton = screen.getByText(/refresh/i);
    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(api.getPerformanceAnalytics).toHaveBeenCalledTimes(2);
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
      expect(api.getPerformanceAnalytics).toHaveBeenCalledWith('1m', 'SPY');
    });
  });
});
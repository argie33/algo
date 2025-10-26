/**
 * Portfolio Dashboard Integration Tests
 * Tests the frontend component's integration with the professional metrics API
 */

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import PortfolioDashboard from '../pages/PortfolioDashboard';
import * as api from '../services/api';

// Mock the API module
jest.mock('../services/api');

// Create a test theme
const theme = createTheme({
  palette: {
    mode: 'light',
  },
});

// Wrapper component with providers
const Wrapper = ({ children }) => (
  <BrowserRouter>
    <ThemeProvider theme={theme}>
      {children}
    </ThemeProvider>
  </BrowserRouter>
);

describe('PortfolioDashboard Integration Tests', () => {
  const mockMetricsResponse = {
    success: true,
    data: {
      summary: {
        total_return: 24.35,
        ytd_return: 12.15,
        return_1y: 18.45,
        return_3y: 34.22,
        alpha: 2.45,
        sharpe_ratio: 1.85,
        sortino_ratio: 2.65,
        calmar_ratio: 0.95,
        information_ratio: 0.75,
        treynor_ratio: 0.045,
        volatility_annualized: 15.5,
        downside_deviation: 8.2,
        beta: 1.1,
        max_drawdown: 18.5,
        var_95: -2.15,
        cvar_95: -3.45,
        var_99: -4.75,
        skewness: 0.25,
        kurtosis: -0.5,
        semi_skewness: 0.15,
        current_drawdown: 5.2,
        drawdown_duration_days: 23,
        avg_drawdown: 8.5,
        max_recovery_days: 45,
        top_1_weight: 18.5,
        top_5_weight: 52.3,
        top_10_weight: 72.5,
        herfindahl_index: 0.085,
        effective_n: 11.76,
        avg_correlation: 0.45,
        diversification_ratio: 1.25,
        num_sectors: 8,
        num_industries: 15,
        best_day_gain: 3.45,
        worst_day_loss: -2.85,
        top_5_days_contribution: 15.3,
        win_rate: 58.5,
        return_1m: 2.15,
        return_3m: 5.85,
        return_6m: 10.45,
        return_rolling_1y: 18.45,
        return_risk_ratio: 1.57,
        cash_drag: 0.05,
        turnover_ratio: 125,
        transaction_costs: 0.15,
        top_sector: 'Technology',
        sector_concentration: 0.28,
        sector_momentum: 0.85,
        best_performer_sector: 'Healthcare',
        tracking_error: 8.5,
        active_return: 2.45,
        relative_volatility: 0.92,
        correlation_with_spy: 0.88,
      },
      positions: [
        {
          symbol: 'AAPL',
          name: 'Apple Inc.',
          weight: 18.5,
          value: 185000,
          cost_basis: 160000,
          gain: 25000,
          gain_percent: 15.6,
          ytd_gain: 8500,
          ytd_gain_percent: 4.8,
          sector: 'Technology',
          beta: 1.2,
          correlation: 0.92,
        },
        {
          symbol: 'MSFT',
          name: 'Microsoft Corporation',
          weight: 15.3,
          value: 153000,
          cost_basis: 135000,
          gain: 18000,
          gain_percent: 13.3,
          ytd_gain: 6200,
          ytd_gain_percent: 4.2,
          sector: 'Technology',
          beta: 0.95,
          correlation: 0.85,
        },
      ],
      metadata: {
        calculation_basis: '252 trading days',
        risk_free_rate: '2%',
        benchmark: 'SPY',
        data_points: 500,
        portfolio_value: 1000000,
        position_count: 2,
      },
    },
    timestamp: new Date().toISOString(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should render the dashboard with KPI header', async () => {
    api.get.mockResolvedValueOnce(mockMetricsResponse);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    // Check for KPI header elements
    await waitFor(() => {
      expect(screen.queryByText(/Total Return/i)).toBeInTheDocument();
      expect(screen.queryByText(/YTD Return/i)).toBeInTheDocument();
      expect(screen.queryByText(/Volatility/i)).toBeInTheDocument();
      expect(screen.queryByText(/Sharpe Ratio/i)).toBeInTheDocument();
    });
  });

  it('should display correct metric values', async () => {
    api.get.mockResolvedValueOnce(mockMetricsResponse);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      // Total return
      expect(screen.queryByText('24.35%')).toBeInTheDocument();
      // Sharpe ratio
      expect(screen.queryByText('1.85')).toBeInTheDocument();
      // Max drawdown
      expect(screen.queryByText('18.50%')).toBeInTheDocument();
    });
  });

  it('should render holdings table with positions', async () => {
    api.get.mockResolvedValueOnce(mockMetricsResponse);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.queryByText('AAPL')).toBeInTheDocument();
      expect(screen.queryByText('MSFT')).toBeInTheDocument();
      expect(screen.queryByText('Apple Inc.')).toBeInTheDocument();
      expect(screen.queryByText('Microsoft Corporation')).toBeInTheDocument();
    });
  });

  it('should render Advanced Analytics tabs', async () => {
    api.get.mockResolvedValueOnce(mockMetricsResponse);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.queryByText(/Return Attribution/i)).toBeInTheDocument();
      expect(screen.queryByText(/Rolling Performance/i)).toBeInTheDocument();
    });
  });

  it('should handle loading state', async () => {
    api.get.mockImplementation(() => new Promise(resolve => {
      setTimeout(() => resolve(mockMetricsResponse), 100);
    }));

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    // Component should render (with or without loading indicator)
    await waitFor(() => {
      expect(screen.queryByText(/Total Return/i)).toBeInTheDocument();
    }, { timeout: 1000 });
  });

  it('should handle no portfolio data gracefully', async () => {
    const emptyResponse = {
      ...mockMetricsResponse,
      data: {
        ...mockMetricsResponse.data,
        positions: [],
        metadata: {
          ...mockMetricsResponse.data.metadata,
          position_count: 0,
          portfolio_value: 0,
        },
      },
    };

    api.get.mockResolvedValueOnce(emptyResponse);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.queryByText(/Total Return/i)).toBeInTheDocument();
    });
  });

  it('should handle API errors gracefully', async () => {
    api.get.mockRejectedValueOnce(new Error('API Error'));

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    // Should still render without crashing
    await waitFor(() => {
      expect(screen.queryByText(/Total Return/i)).toBeInTheDocument();
    });
  });

  it('should call the correct API endpoint', async () => {
    api.get.mockResolvedValueOnce(mockMetricsResponse);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/analytics/professional-metrics');
    });
  });

  it('should display metadata information', async () => {
    api.get.mockResolvedValueOnce(mockMetricsResponse);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.queryByText(/Calculation Basis/i)).toBeInTheDocument();
      expect(screen.queryByText(/252 trading days/i)).toBeInTheDocument();
    });
  });

  it('should render responsive grid layout', async () => {
    api.get.mockResolvedValueOnce(mockMetricsResponse);

    const { container } = render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      // Check for MUI Grid container
      const gridContainers = container.querySelectorAll('[class*="MuiGrid-container"]');
      expect(gridContainers.length).toBeGreaterThan(0);
    });
  });

  it('should render sector and industry information', async () => {
    api.get.mockResolvedValueOnce(mockMetricsResponse);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.queryByText(/Technology/i)).toBeInTheDocument();
      expect(screen.queryByText(/Healthcare/i)).toBeInTheDocument();
    });
  });

  it('should display all major metric sections', async () => {
    api.get.mockResolvedValueOnce(mockMetricsResponse);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.queryByText(/Performance Metrics/i)).toBeInTheDocument();
      expect(screen.queryByText(/Risk Metrics/i)).toBeInTheDocument();
      expect(screen.queryByText(/Concentration/i)).toBeInTheDocument();
      expect(screen.queryByText(/Diversification/i)).toBeInTheDocument();
    });
  });

  it('should calculate and display metric change indicators', async () => {
    api.get.mockResolvedValueOnce(mockMetricsResponse);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      // YTD return should be visible
      expect(screen.queryByText('12.15%')).toBeInTheDocument();
    });
  });

  it('should display portfolio value information', async () => {
    api.get.mockResolvedValueOnce(mockMetricsResponse);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      const portfolioValue = within(screen.getByText(/Portfolio Value/i).closest('div'));
      expect(portfolioValue.getByText(/1,000,000/i)).toBeInTheDocument();
    });
  });
});

// Performance and rendering speed tests
describe('PortfolioDashboard Performance Tests', () => {
  it('should render within acceptable time', async () => {
    const mockMetrics = {
      success: true,
      data: {
        summary: {
          total_return: 24.35,
          ytd_return: 12.15,
          return_1y: 18.45,
          return_3y: 34.22,
          volatility_annualized: 15.5,
          sharpe_ratio: 1.85,
          max_drawdown: 18.5,
          beta: 1.1,
          alpha: 2.45,
          sortino_ratio: 2.65,
          top_1_weight: 18.5,
          top_5_weight: 52.3,
          effective_n: 11.76,
          best_day_gain: 3.45,
          worst_day_loss: -2.85,
          win_rate: 58.5,
          tracking_error: 8.5,
        },
        positions: [],
        metadata: {
          calculation_basis: '252 trading days',
          risk_free_rate: '2%',
          benchmark: 'SPY',
          data_points: 500,
          portfolio_value: 1000000,
          position_count: 0,
        },
      },
      timestamp: new Date().toISOString(),
    };

    api.get.mockResolvedValueOnce(mockMetrics);

    const startTime = performance.now();

    render(<PortfolioDashboard />, {
      wrapper: Wrapper
    });

    await waitFor(() => {
      expect(screen.queryByText(/Total Return/i)).toBeInTheDocument();
    });

    const endTime = performance.now();
    const renderTime = endTime - startTime;

    // Should render in less than 2 seconds
    expect(renderTime).toBeLessThan(2000);
  });
});

// Responsive design tests
describe('PortfolioDashboard Responsive Design', () => {
  it('should handle mobile viewport (xs)', async () => {
    global.innerWidth = 360;
    global.innerHeight = 640;
    global.dispatchEvent(new Event('resize'));

    const mockMetrics = {
      success: true,
      data: {
        summary: {
          total_return: 24.35,
          ytd_return: 12.15,
          return_1y: 18.45,
          return_3y: 34.22,
          volatility_annualized: 15.5,
          sharpe_ratio: 1.85,
          max_drawdown: 18.5,
          beta: 1.1,
          alpha: 2.45,
          sortino_ratio: 2.65,
          top_1_weight: 18.5,
          top_5_weight: 52.3,
          effective_n: 11.76,
          best_day_gain: 3.45,
          worst_day_loss: -2.85,
          win_rate: 58.5,
          tracking_error: 8.5,
        },
        positions: [],
        metadata: {
          calculation_basis: '252 trading days',
          risk_free_rate: '2%',
          benchmark: 'SPY',
          data_points: 500,
          portfolio_value: 1000000,
          position_count: 0,
        },
      },
      timestamp: new Date().toISOString(),
    };

    api.get.mockResolvedValueOnce(mockMetrics);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.queryByText(/Total Return/i)).toBeInTheDocument();
    });
  });

  it('should handle tablet viewport (md)', async () => {
    global.innerWidth = 768;
    global.innerHeight = 1024;
    global.dispatchEvent(new Event('resize'));

    const mockMetrics = {
      success: true,
      data: {
        summary: {
          total_return: 24.35,
          ytd_return: 12.15,
          return_1y: 18.45,
          return_3y: 34.22,
          volatility_annualized: 15.5,
          sharpe_ratio: 1.85,
          max_drawdown: 18.5,
          beta: 1.1,
          alpha: 2.45,
          sortino_ratio: 2.65,
          top_1_weight: 18.5,
          top_5_weight: 52.3,
          effective_n: 11.76,
          best_day_gain: 3.45,
          worst_day_loss: -2.85,
          win_rate: 58.5,
          tracking_error: 8.5,
        },
        positions: [],
        metadata: {
          calculation_basis: '252 trading days',
          risk_free_rate: '2%',
          benchmark: 'SPY',
          data_points: 500,
          portfolio_value: 1000000,
          position_count: 0,
        },
      },
      timestamp: new Date().toISOString(),
    };

    api.get.mockResolvedValueOnce(mockMetrics);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.queryByText(/Total Return/i)).toBeInTheDocument();
    });
  });

  it('should handle desktop viewport (lg)', async () => {
    global.innerWidth = 1920;
    global.innerHeight = 1080;
    global.dispatchEvent(new Event('resize'));

    const mockMetrics = {
      success: true,
      data: {
        summary: {
          total_return: 24.35,
          ytd_return: 12.15,
          return_1y: 18.45,
          return_3y: 34.22,
          volatility_annualized: 15.5,
          sharpe_ratio: 1.85,
          max_drawdown: 18.5,
          beta: 1.1,
          alpha: 2.45,
          sortino_ratio: 2.65,
          top_1_weight: 18.5,
          top_5_weight: 52.3,
          effective_n: 11.76,
          best_day_gain: 3.45,
          worst_day_loss: -2.85,
          win_rate: 58.5,
          tracking_error: 8.5,
        },
        positions: [],
        metadata: {
          calculation_basis: '252 trading days',
          risk_free_rate: '2%',
          benchmark: 'SPY',
          data_points: 500,
          portfolio_value: 1000000,
          position_count: 0,
        },
      },
      timestamp: new Date().toISOString(),
    };

    api.get.mockResolvedValueOnce(mockMetrics);

    render(<PortfolioDashboard />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.queryByText(/Total Return/i)).toBeInTheDocument();
    });
  });
});

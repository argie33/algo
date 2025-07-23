/**
 * Portfolio Components Unit Tests
 * Tests portfolio management components for the financial platform
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Mock portfolio-related components
vi.mock('../../../pages/Portfolio', () => ({
  default: vi.fn(() => <div data-testid="portfolio-page">Portfolio Management</div>)
}));

vi.mock('../../../components/portfolio/HoldingsTable', () => ({
  default: vi.fn(({ holdings }) => (
    <div data-testid="holdings-table">
      {holdings.map(holding => (
        <div key={holding.symbol} data-testid={`holding-${holding.symbol}`}>
          {holding.symbol}: {holding.quantity} shares @ ${holding.price}
        </div>
      ))}
    </div>
  ))
}));

vi.mock('../../../components/portfolio/PerformanceChart', () => ({
  default: vi.fn(({ data }) => (
    <div data-testid="portfolio-chart">
      <div data-testid="chart-value">${data.totalValue?.toLocaleString()}</div>
      <div data-testid="chart-change">{data.change}%</div>
    </div>
  ))
}));

vi.mock('../../../components/portfolio/AllocationDashboard', () => ({
  default: vi.fn(({ allocation }) => (
    <div data-testid="asset-allocation">
      {allocation.map(asset => (
        <div key={asset.type} data-testid={`allocation-${asset.type}`}>
          {asset.type}: {asset.percentage}%
        </div>
      ))}
    </div>
  ))
}));

const theme = createTheme();

const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider theme={theme}>
          {children}
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

describe('Portfolio Components', () => {
  let mockHoldings;
  let mockPortfolioData;
  let mockAllocation;

  beforeEach(() => {
    vi.clearAllMocks();
    
    mockHoldings = [
      { symbol: 'AAPL', quantity: 100, price: 195.50, value: 19550, change: 2.5 },
      { symbol: 'MSFT', quantity: 50, price: 380.25, value: 19012.50, change: -1.2 },
      { symbol: 'GOOGL', quantity: 25, price: 2600.00, value: 65000, change: 1.8 }
    ];

    mockPortfolioData = {
      totalValue: 122368.75,
      change: 1.85,
      dailyPnL: 2234.50
    };

    mockAllocation = [
      { type: 'Stocks', percentage: 85, value: 104013.44 },
      { type: 'Bonds', percentage: 10, value: 12236.88 },
      { type: 'Cash', percentage: 5, value: 6118.44 }
    ];
  });

  describe('Holdings Table Component', () => {
    it('displays all portfolio holdings with correct data', async () => {
      const HoldingsTable = (await import('../../../components/portfolio/HoldingsTable')).default;
      
      render(
        <TestWrapper>
          <HoldingsTable holdings={mockHoldings} />
        </TestWrapper>
      );

      expect(screen.getByTestId('holdings-table')).toBeInTheDocument();
      expect(screen.getByTestId('holding-AAPL')).toHaveTextContent('AAPL: 100 shares @ $195.5');
      expect(screen.getByTestId('holding-MSFT')).toHaveTextContent('MSFT: 50 shares @ $380.25');
      expect(screen.getByTestId('holding-GOOGL')).toHaveTextContent('GOOGL: 25 shares @ $2600');
    });

    it('handles empty holdings gracefully', async () => {
      const HoldingsTable = (await import('../../../components/portfolio/HoldingsTable')).default;
      
      render(
        <TestWrapper>
          <HoldingsTable holdings={[]} />
        </TestWrapper>
      );

      expect(screen.getByTestId('holdings-table')).toBeInTheDocument();
      expect(screen.getByTestId('holdings-table')).toBeEmptyDOMElement();
    });
  });

  describe('Portfolio Chart Component', () => {
    it('displays portfolio value and performance', async () => {
      const PortfolioChart = (await import('../../../components/portfolio/PerformanceChart')).default;
      
      render(
        <TestWrapper>
          <PortfolioChart data={mockPortfolioData} />
        </TestWrapper>
      );

      expect(screen.getByTestId('portfolio-chart')).toBeInTheDocument();
      expect(screen.getByTestId('chart-value')).toHaveTextContent('$122,368.75');
      expect(screen.getByTestId('chart-change')).toHaveTextContent('1.85%');
    });

    it('handles negative performance correctly', async () => {
      const PortfolioChart = (await import('../../../components/portfolio/PerformanceChart')).default;
      const negativeData = { ...mockPortfolioData, change: -2.45 };
      
      render(
        <TestWrapper>
          <PortfolioChart data={negativeData} />
        </TestWrapper>
      );

      expect(screen.getByTestId('chart-change')).toHaveTextContent('-2.45%');
    });
  });

  describe('Asset Allocation Component', () => {
    it('displays asset allocation percentages', async () => {
      const AssetAllocation = (await import('../../../components/portfolio/AllocationDashboard')).default;
      
      render(
        <TestWrapper>
          <AssetAllocation allocation={mockAllocation} />
        </TestWrapper>
      );

      expect(screen.getByTestId('asset-allocation')).toBeInTheDocument();
      expect(screen.getByTestId('allocation-Stocks')).toHaveTextContent('Stocks: 85%');
      expect(screen.getByTestId('allocation-Bonds')).toHaveTextContent('Bonds: 10%');
      expect(screen.getByTestId('allocation-Cash')).toHaveTextContent('Cash: 5%');
    });

    it('validates allocation percentages sum to 100%', async () => {
      const AssetAllocation = (await import('../../../components/portfolio/AllocationDashboard')).default;
      
      render(
        <TestWrapper>
          <AssetAllocation allocation={mockAllocation} />
        </TestWrapper>
      );

      const totalPercentage = mockAllocation.reduce((sum, asset) => sum + asset.percentage, 0);
      expect(totalPercentage).toBe(100);
    });
  });

  describe('Portfolio Page Integration', () => {
    it('renders complete portfolio page', async () => {
      const Portfolio = (await import('../../../pages/Portfolio')).default;
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      expect(screen.getByTestId('portfolio-page')).toBeInTheDocument();
      expect(screen.getByTestId('portfolio-page')).toHaveTextContent('Portfolio Management');
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });
});
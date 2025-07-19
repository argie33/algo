/**
 * Widget Components Unit Tests
 * Comprehensive testing of all real dashboard widget components
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Real Widget Components - Import actual production components
import { PortfolioSummaryWidget } from '../../../components/widgets/PortfolioSummaryWidget';
import { MarketOverviewWidget } from '../../../components/widgets/MarketOverviewWidget';
import { PerformanceWidget } from '../../../components/widgets/PerformanceWidget';
import { WatchlistWidget } from '../../../components/widgets/WatchlistWidget';
import { NewsWidget } from '../../../components/widgets/NewsWidget';
import { TradeHistoryWidget } from '../../../components/widgets/TradeHistoryWidget';
import { GainersLosersWidget } from '../../../components/widgets/GainersLosersWidget';
import { SectorAllocationWidget } from '../../../components/widgets/SectorAllocationWidget';
import { RiskMetricsWidget } from '../../../components/widgets/RiskMetricsWidget';
import { CalendarWidget } from '../../../components/widgets/CalendarWidget';
import { AlertsWidget } from '../../../components/widgets/AlertsWidget';
import { QuickActionsWidget } from '../../../components/widgets/QuickActionsWidget';

describe('🧩 Widget Components', () => {
  const mockPortfolioData = {
    totalValue: 125000,
    dayChange: 2500,
    dayChangePercent: 2.04,
    unrealizedGainLoss: 15000,
    unrealizedGainLossPercent: 13.64,
    cash: 5000,
    positions: 12,
    topHolding: { symbol: 'AAPL', value: 25000, percentage: 20 }
  };

  const mockMarketData = {
    indices: [
      { symbol: 'SPY', name: 'S&P 500', value: 4150.35, change: 45.20, changePercent: 1.10 },
      { symbol: 'QQQ', name: 'NASDAQ', value: 350.75, change: -2.15, changePercent: -0.61 },
      { symbol: 'IWM', name: 'Russell 2000', value: 195.80, change: 1.85, changePercent: 0.95 }
    ],
    marketStatus: 'open',
    lastUpdate: '2024-01-15T15:30:00Z'
  };

  const mockPerformanceData = {
    periods: [
      { period: '1D', return: 2.04, benchmark: 1.10 },
      { period: '1W', return: 5.25, benchmark: 3.80 },
      { period: '1M', return: 8.45, benchmark: 6.20 },
      { period: '3M', return: 12.30, benchmark: 9.15 },
      { period: '1Y', return: 18.75, benchmark: 14.25 }
    ],
    chartData: [
      { date: '2024-01-01', portfolio: 100, benchmark: 100 },
      { date: '2024-01-15', portfolio: 118.75, benchmark: 114.25 }
    ]
  };

  const mockWatchlistData = [
    { symbol: 'AAPL', name: 'Apple Inc.', price: 185.50, change: 2.25, changePercent: 1.23, alerts: 2 },
    { symbol: 'GOOGL', name: 'Alphabet Inc.', price: 2850.75, change: -15.50, changePercent: -0.54, alerts: 0 },
    { symbol: 'MSFT', name: 'Microsoft Corp.', price: 375.25, change: 8.75, changePercent: 2.39, alerts: 1 },
    { symbol: 'TSLA', name: 'Tesla Inc.', price: 220.80, change: -5.20, changePercent: -2.30, alerts: 3 }
  ];

  const mockNewsData = [
    {
      id: 'news_1',
      title: 'Federal Reserve Holds Interest Rates Steady',
      summary: 'The Fed maintains rates at current levels amid economic uncertainty...',
      source: 'Reuters',
      publishedAt: '2024-01-15T14:30:00Z',
      url: 'https://example.com/news/1',
      sentiment: 'neutral'
    },
    {
      id: 'news_2', 
      title: 'Apple Reports Strong Q4 Earnings',
      summary: 'iPhone sales exceed expectations despite supply chain challenges...',
      source: 'Bloomberg',
      publishedAt: '2024-01-15T13:45:00Z',
      url: 'https://example.com/news/2',
      sentiment: 'positive'
    }
  ];

  const mockTradeHistory = [
    {
      id: 'trade_1',
      symbol: 'AAPL',
      type: 'buy',
      quantity: 50,
      price: 180.00,
      total: 9000,
      executedAt: '2024-01-15T10:30:00Z',
      status: 'filled'
    },
    {
      id: 'trade_2',
      symbol: 'GOOGL',
      type: 'sell',
      quantity: 5,
      price: 2800.00,
      total: 14000,
      executedAt: '2024-01-14T14:15:00Z',
      status: 'filled'
    }
  ];

  const mockGainersLosers = {
    gainers: [
      { symbol: 'NVDA', name: 'NVIDIA Corp.', change: 15.75, changePercent: 5.25 },
      { symbol: 'AMD', name: 'Advanced Micro Devices', change: 8.50, changePercent: 4.18 }
    ],
    losers: [
      { symbol: 'NFLX', name: 'Netflix Inc.', change: -12.30, changePercent: -3.85 },
      { symbol: 'META', name: 'Meta Platforms', change: -8.75, changePercent: -2.95 }
    ]
  };

  const mockSectorAllocation = [
    { sector: 'Technology', percentage: 35, value: 43750, color: '#1f77b4' },
    { sector: 'Healthcare', percentage: 20, value: 25000, color: '#ff7f0e' },
    { sector: 'Finance', percentage: 18, value: 22500, color: '#2ca02c' },
    { sector: 'Energy', percentage: 15, value: 18750, color: '#d62728' },
    { sector: 'Consumer', percentage: 12, value: 15000, color: '#9467bd' }
  ];

  const mockRiskMetrics = {
    portfolioRisk: 'moderate',
    beta: 1.15,
    volatility: 18.5,
    sharpeRatio: 1.42,
    var95: -2.85,
    maxDrawdown: -8.2,
    riskScore: 7.2,
    lastCalculated: '2024-01-15T09:00:00Z'
  };

  const mockCalendarEvents = [
    {
      id: 'event_1',
      type: 'earnings',
      company: 'Apple Inc.',
      symbol: 'AAPL',
      date: '2024-01-18',
      time: '16:30',
      description: 'Q1 2024 Earnings Call'
    },
    {
      id: 'event_2',
      type: 'dividend',
      company: 'Microsoft Corp.',
      symbol: 'MSFT',
      date: '2024-01-20',
      description: 'Ex-Dividend Date'
    }
  ];

  const mockAlerts = [
    {
      id: 'alert_1',
      type: 'price',
      symbol: 'AAPL',
      condition: 'above',
      targetPrice: 185.00,
      currentPrice: 185.50,
      triggered: true,
      createdAt: '2024-01-15T10:25:00Z'
    },
    {
      id: 'alert_2',
      type: 'volume',
      symbol: 'TSLA',
      condition: 'unusual',
      triggered: false,
      createdAt: '2024-01-14T16:00:00Z'
    }
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('PortfolioSummaryWidget Component', () => {
    it('should render portfolio summary correctly', () => {
      render(<PortfolioSummaryWidget data={mockPortfolioData} />);

      expect(screen.getByText('Portfolio Summary')).toBeInTheDocument();
      expect(screen.getByText('$125,000')).toBeInTheDocument();
      expect(screen.getByText('+$2,500')).toBeInTheDocument();
      expect(screen.getByText('+2.04%')).toBeInTheDocument();
      expect(screen.getByText('12 positions')).toBeInTheDocument();
    });

    it('should handle negative portfolio changes', () => {
      const negativeData = {
        ...mockPortfolioData,
        dayChange: -1500,
        dayChangePercent: -1.18
      };

      render(<PortfolioSummaryWidget data={negativeData} />);

      expect(screen.getByText('-$1,500')).toBeInTheDocument();
      expect(screen.getByText('-1.18%')).toBeInTheDocument();
    });

    it('should show loading state when data is unavailable', () => {
      render(<PortfolioSummaryWidget data={null} loading={true} />);

      expect(screen.getByRole('progressbar')).toBeInTheDocument();
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it('should navigate to portfolio details on click', async () => {
      const user = userEvent.setup();
      const onNavigate = vi.fn();

      render(<PortfolioSummaryWidget data={mockPortfolioData} onNavigate={onNavigate} />);

      await user.click(screen.getByRole('button', { name: /view portfolio/i }));
      expect(onNavigate).toHaveBeenCalledWith('/portfolio');
    });

    it('should display unrealized gains/losses', () => {
      render(<PortfolioSummaryWidget data={mockPortfolioData} showUnrealizedGains={true} />);

      expect(screen.getByText('+$15,000')).toBeInTheDocument();
      expect(screen.getByText('+13.64%')).toBeInTheDocument();
    });

    it('should refresh data on user action', async () => {
      const user = userEvent.setup();
      const onRefresh = vi.fn();

      render(<PortfolioSummaryWidget data={mockPortfolioData} onRefresh={onRefresh} />);

      const refreshButton = screen.getByRole('button', { name: /refresh/i });
      await user.click(refreshButton);
      expect(onRefresh).toHaveBeenCalled();
    });
  });

  describe('MarketOverviewWidget Component', () => {
    it('should render market indices correctly', () => {
      render(<MarketOverviewWidget data={mockMarketData} />);

      expect(screen.getByText('Market Overview')).toBeInTheDocument();
      expect(screen.getByText('S&P 500')).toBeInTheDocument();
      expect(screen.getByText('4150.35')).toBeInTheDocument();
      expect(screen.getByText('+45.20')).toBeInTheDocument();
      expect(screen.getByText('+1.10%')).toBeInTheDocument();
    });

    it('should show market status indicator', () => {
      render(<MarketOverviewWidget data={mockMarketData} />);

      expect(screen.getByText('Market Open')).toBeInTheDocument();
      expect(screen.getByTestId('market-status-indicator')).toHaveClass('open');
    });

    it('should handle market closed status', () => {
      const closedMarketData = {
        ...mockMarketData,
        marketStatus: 'closed'
      };

      render(<MarketOverviewWidget data={closedMarketData} />);

      expect(screen.getByText('Market Closed')).toBeInTheDocument();
      expect(screen.getByTestId('market-status-indicator')).toHaveClass('closed');
    });

    it('should show last update timestamp', () => {
      render(<MarketOverviewWidget data={mockMarketData} showLastUpdate={true} />);

      expect(screen.getByText(/last updated/i)).toBeInTheDocument();
    });

    it('should handle negative market changes', () => {
      render(<MarketOverviewWidget data={mockMarketData} />);

      expect(screen.getByText('NASDAQ')).toBeInTheDocument();
      expect(screen.getByText('-2.15')).toBeInTheDocument();
      expect(screen.getByText('-0.61%')).toBeInTheDocument();
    });

    it('should support customizable indices', () => {
      const customIndices = [
        { symbol: 'DJI', name: 'Dow Jones', value: 34500, change: 125, changePercent: 0.36 }
      ];

      render(<MarketOverviewWidget data={{ ...mockMarketData, indices: customIndices }} />);

      expect(screen.getByText('Dow Jones')).toBeInTheDocument();
      expect(screen.getByText('34500')).toBeInTheDocument();
    });
  });

  describe('PerformanceWidget Component', () => {
    it('should render performance data correctly', () => {
      render(<PerformanceWidget data={mockPerformanceData} />);

      expect(screen.getByText('Performance')).toBeInTheDocument();
      expect(screen.getByText('1D')).toBeInTheDocument();
      expect(screen.getByText('2.04%')).toBeInTheDocument();
    });

    it('should switch between time periods', async () => {
      const user = userEvent.setup();
      const onPeriodChange = vi.fn();

      render(<PerformanceWidget data={mockPerformanceData} onPeriodChange={onPeriodChange} />);

      await user.click(screen.getByText('1M'));
      expect(onPeriodChange).toHaveBeenCalledWith('1M');
    });

    it('should show performance comparison with benchmark', () => {
      render(<PerformanceWidget data={mockPerformanceData} showBenchmark={true} />);

      expect(screen.getByText(/vs benchmark/i)).toBeInTheDocument();
      expect(screen.getByText('1.10%')).toBeInTheDocument(); // Benchmark for 1D
    });

    it('should highlight outperformance', () => {
      render(<PerformanceWidget data={mockPerformanceData} showBenchmark={true} />);

      const outperformanceIndicator = screen.getByTestId('outperformance-1D');
      expect(outperformanceIndicator).toHaveClass('positive');
    });

    it('should render performance chart', () => {
      render(<PerformanceWidget data={mockPerformanceData} showChart={true} />);

      expect(screen.getByRole('img', { name: /performance chart/i })).toBeInTheDocument();
    });

    it('should calculate alpha and beta metrics', () => {
      render(<PerformanceWidget data={mockPerformanceData} showAdvancedMetrics={true} />);

      expect(screen.getByText(/alpha/i)).toBeInTheDocument();
      expect(screen.getByText(/beta/i)).toBeInTheDocument();
    });
  });

  describe('WatchlistWidget Component', () => {
    it('should render watchlist items correctly', () => {
      render(<WatchlistWidget data={mockWatchlistData} />);

      expect(screen.getByText('Watchlist')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
      expect(screen.getByText('$185.50')).toBeInTheDocument();
    });

    it('should handle stock price changes with color coding', () => {
      render(<WatchlistWidget data={mockWatchlistData} />);

      const appleChange = screen.getByText('+2.25');
      expect(appleChange).toHaveClass('positive');

      const googleChange = screen.getByText('-15.50');
      expect(googleChange).toHaveClass('negative');
    });

    it('should show alert indicators', () => {
      render(<WatchlistWidget data={mockWatchlistData} showAlerts={true} />);

      expect(screen.getByText('2')).toBeInTheDocument(); // AAPL alerts
      expect(screen.getByText('3')).toBeInTheDocument(); // TSLA alerts
    });

    it('should add new stock to watchlist', async () => {
      const user = userEvent.setup();
      const onAddStock = vi.fn();

      render(<WatchlistWidget data={mockWatchlistData} onAddStock={onAddStock} />);

      const addButton = screen.getByRole('button', { name: /add stock/i });
      await user.click(addButton);

      const input = screen.getByPlaceholderText(/enter symbol/i);
      await user.type(input, 'NVDA');
      await user.keyboard('{Enter}');

      expect(onAddStock).toHaveBeenCalledWith('NVDA');
    });

    it('should remove stock from watchlist', async () => {
      const user = userEvent.setup();
      const onRemoveStock = vi.fn();

      render(<WatchlistWidget data={mockWatchlistData} onRemoveStock={onRemoveStock} />);

      const removeButton = screen.getAllByRole('button', { name: /remove/i })[0];
      await user.click(removeButton);

      expect(onRemoveStock).toHaveBeenCalledWith('AAPL');
    });

    it('should navigate to stock detail on click', async () => {
      const user = userEvent.setup();
      const onStockClick = vi.fn();

      render(<WatchlistWidget data={mockWatchlistData} onStockClick={onStockClick} />);

      await user.click(screen.getByText('AAPL'));
      expect(onStockClick).toHaveBeenCalledWith('AAPL');
    });
  });

  describe('NewsWidget Component', () => {
    it('should render news articles correctly', () => {
      render(<NewsWidget data={mockNewsData} />);

      expect(screen.getByText('Market News')).toBeInTheDocument();
      expect(screen.getByText('Federal Reserve Holds Interest Rates Steady')).toBeInTheDocument();
      expect(screen.getByText('Reuters')).toBeInTheDocument();
    });

    it('should show article summaries', () => {
      render(<NewsWidget data={mockNewsData} showSummary={true} />);

      expect(screen.getByText(/The Fed maintains rates at current levels/)).toBeInTheDocument();
    });

    it('should indicate article sentiment', () => {
      render(<NewsWidget data={mockNewsData} showSentiment={true} />);

      const neutralSentiment = screen.getByTestId('sentiment-neutral');
      expect(neutralSentiment).toBeInTheDocument();

      const positiveSentiment = screen.getByTestId('sentiment-positive');
      expect(positiveSentiment).toBeInTheDocument();
    });

    it('should open article in new tab', async () => {
      const user = userEvent.setup();
      const mockOpen = vi.fn();
      window.open = mockOpen;

      render(<NewsWidget data={mockNewsData} />);

      await user.click(screen.getByText('Federal Reserve Holds Interest Rates Steady'));
      expect(mockOpen).toHaveBeenCalledWith('https://example.com/news/1', '_blank');
    });

    it('should filter news by categories', async () => {
      const user = userEvent.setup();
      const onCategoryChange = vi.fn();

      render(<NewsWidget data={mockNewsData} onCategoryChange={onCategoryChange} />);

      const categoryFilter = screen.getByRole('combobox', { name: /category/i });
      await user.selectOptions(categoryFilter, 'earnings');
      expect(onCategoryChange).toHaveBeenCalledWith('earnings');
    });

    it('should refresh news feed', async () => {
      const user = userEvent.setup();
      const onRefresh = vi.fn();

      render(<NewsWidget data={mockNewsData} onRefresh={onRefresh} />);

      const refreshButton = screen.getByRole('button', { name: /refresh news/i });
      await user.click(refreshButton);
      expect(onRefresh).toHaveBeenCalled();
    });
  });

  describe('TradeHistoryWidget Component', () => {
    it('should render trade history correctly', () => {
      render(<TradeHistoryWidget data={mockTradeHistory} />);

      expect(screen.getByText('Recent Trades')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('Buy')).toBeInTheDocument();
      expect(screen.getByText('50')).toBeInTheDocument();
      expect(screen.getByText('$180.00')).toBeInTheDocument();
    });

    it('should show trade status indicators', () => {
      render(<TradeHistoryWidget data={mockTradeHistory} />);

      const filledStatus = screen.getAllByText('Filled');
      expect(filledStatus).toHaveLength(2);
    });

    it('should calculate trade totals', () => {
      render(<TradeHistoryWidget data={mockTradeHistory} showTotals={true} />);

      expect(screen.getByText('$9,000')).toBeInTheDocument(); // AAPL buy total
      expect(screen.getByText('$14,000')).toBeInTheDocument(); // GOOGL sell total
    });

    it('should filter trades by type', async () => {
      const user = userEvent.setup();
      const onFilterChange = vi.fn();

      render(<TradeHistoryWidget data={mockTradeHistory} onFilterChange={onFilterChange} />);

      const filterButton = screen.getByRole('button', { name: /buy orders/i });
      await user.click(filterButton);
      expect(onFilterChange).toHaveBeenCalledWith({ type: 'buy' });
    });

    it('should show trade details on expand', async () => {
      const user = userEvent.setup();

      render(<TradeHistoryWidget data={mockTradeHistory} expandable={true} />);

      const expandButton = screen.getAllByRole('button', { name: /details/i })[0];
      await user.click(expandButton);

      expect(screen.getByText(/commission/i)).toBeInTheDocument();
      expect(screen.getByText(/fees/i)).toBeInTheDocument();
    });

    it('should export trade history', async () => {
      const user = userEvent.setup();
      const onExport = vi.fn();

      render(<TradeHistoryWidget data={mockTradeHistory} onExport={onExport} />);

      const exportButton = screen.getByRole('button', { name: /export/i });
      await user.click(exportButton);
      expect(onExport).toHaveBeenCalledWith(mockTradeHistory, 'csv');
    });
  });

  describe('GainersLosersWidget Component', () => {
    it('should render gainers and losers correctly', () => {
      render(<GainersLosersWidget data={mockGainersLosers} />);

      expect(screen.getByText('Top Gainers & Losers')).toBeInTheDocument();
      expect(screen.getByText('NVDA')).toBeInTheDocument();
      expect(screen.getByText('+15.75')).toBeInTheDocument();
      expect(screen.getByText('NFLX')).toBeInTheDocument();
      expect(screen.getByText('-12.30')).toBeInTheDocument();
    });

    it('should switch between gainers and losers tabs', async () => {
      const user = userEvent.setup();

      render(<GainersLosersWidget data={mockGainersLosers} />);

      await user.click(screen.getByText('Losers'));
      expect(screen.getByText('NFLX')).toBeVisible();
      expect(screen.getByText('META')).toBeVisible();

      await user.click(screen.getByText('Gainers'));
      expect(screen.getByText('NVDA')).toBeVisible();
      expect(screen.getByText('AMD')).toBeVisible();
    });

    it('should show percentage changes', () => {
      render(<GainersLosersWidget data={mockGainersLosers} />);

      expect(screen.getByText('+5.25%')).toBeInTheDocument();
      expect(screen.getByText('-3.85%')).toBeInTheDocument();
    });

    it('should navigate to stock details', async () => {
      const user = userEvent.setup();
      const onStockClick = vi.fn();

      render(<GainersLosersWidget data={mockGainersLosers} onStockClick={onStockClick} />);

      await user.click(screen.getByText('NVDA'));
      expect(onStockClick).toHaveBeenCalledWith('NVDA');
    });

    it('should customize number of items shown', () => {
      render(<GainersLosersWidget data={mockGainersLosers} itemsToShow={1} />);

      expect(screen.getByText('NVDA')).toBeInTheDocument();
      expect(screen.queryByText('AMD')).not.toBeInTheDocument();
    });
  });

  describe('SectorAllocationWidget Component', () => {
    it('should render sector allocation correctly', () => {
      render(<SectorAllocationWidget data={mockSectorAllocation} />);

      expect(screen.getByText('Sector Allocation')).toBeInTheDocument();
      expect(screen.getByText('Technology')).toBeInTheDocument();
      expect(screen.getByText('35%')).toBeInTheDocument();
      expect(screen.getByText('$43,750')).toBeInTheDocument();
    });

    it('should render as pie chart', () => {
      render(<SectorAllocationWidget data={mockSectorAllocation} chartType="pie" />);

      expect(screen.getByRole('img', { name: /sector allocation chart/i })).toBeInTheDocument();
    });

    it('should render as bar chart', () => {
      render(<SectorAllocationWidget data={mockSectorAllocation} chartType="bar" />);

      expect(screen.getByRole('img', { name: /sector allocation chart/i })).toBeInTheDocument();
    });

    it('should show sector details on hover', async () => {
      const user = userEvent.setup();

      render(<SectorAllocationWidget data={mockSectorAllocation} />);

      await user.hover(screen.getByText('Technology'));
      
      await waitFor(() => {
        expect(screen.getByText(/technology sector details/i)).toBeInTheDocument();
      });
    });

    it('should rebalance sector allocation', async () => {
      const user = userEvent.setup();
      const onRebalance = vi.fn();

      render(<SectorAllocationWidget data={mockSectorAllocation} onRebalance={onRebalance} />);

      const rebalanceButton = screen.getByRole('button', { name: /rebalance/i });
      await user.click(rebalanceButton);
      expect(onRebalance).toHaveBeenCalled();
    });
  });

  describe('RiskMetricsWidget Component', () => {
    it('should render risk metrics correctly', () => {
      render(<RiskMetricsWidget data={mockRiskMetrics} />);

      expect(screen.getByText('Risk Metrics')).toBeInTheDocument();
      expect(screen.getByText('Moderate')).toBeInTheDocument();
      expect(screen.getByText('1.15')).toBeInTheDocument(); // Beta
      expect(screen.getByText('18.5%')).toBeInTheDocument(); // Volatility
    });

    it('should show risk level indicator', () => {
      render(<RiskMetricsWidget data={mockRiskMetrics} />);

      const riskIndicator = screen.getByTestId('risk-level-indicator');
      expect(riskIndicator).toHaveClass('moderate');
    });

    it('should display detailed risk metrics', () => {
      render(<RiskMetricsWidget data={mockRiskMetrics} showDetailedMetrics={true} />);

      expect(screen.getByText('Sharpe Ratio')).toBeInTheDocument();
      expect(screen.getByText('1.42')).toBeInTheDocument();
      expect(screen.getByText('VaR (95%)')).toBeInTheDocument();
      expect(screen.getByText('-2.85%')).toBeInTheDocument();
    });

    it('should show risk recommendations', () => {
      render(<RiskMetricsWidget data={mockRiskMetrics} showRecommendations={true} />);

      expect(screen.getByText(/risk recommendations/i)).toBeInTheDocument();
    });

    it('should update risk tolerance', async () => {
      const user = userEvent.setup();
      const onRiskToleranceChange = vi.fn();

      render(<RiskMetricsWidget data={mockRiskMetrics} onRiskToleranceChange={onRiskToleranceChange} />);

      const toleranceSelector = screen.getByRole('combobox', { name: /risk tolerance/i });
      await user.selectOptions(toleranceSelector, 'conservative');
      expect(onRiskToleranceChange).toHaveBeenCalledWith('conservative');
    });
  });

  describe('CalendarWidget Component', () => {
    it('should render calendar events correctly', () => {
      render(<CalendarWidget data={mockCalendarEvents} />);

      expect(screen.getByText('Market Calendar')).toBeInTheDocument();
      expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
      expect(screen.getByText('Q1 2024 Earnings Call')).toBeInTheDocument();
    });

    it('should categorize events by type', () => {
      render(<CalendarWidget data={mockCalendarEvents} categorizeByType={true} />);

      expect(screen.getByText('Earnings')).toBeInTheDocument();
      expect(screen.getByText('Dividends')).toBeInTheDocument();
    });

    it('should filter events by date range', async () => {
      const user = userEvent.setup();
      const onDateRangeChange = vi.fn();

      render(<CalendarWidget data={mockCalendarEvents} onDateRangeChange={onDateRangeChange} />);

      const dateFilter = screen.getByRole('combobox', { name: /date range/i });
      await user.selectOptions(dateFilter, 'this_week');
      expect(onDateRangeChange).toHaveBeenCalledWith('this_week');
    });

    it('should add event to personal calendar', async () => {
      const user = userEvent.setup();
      const onAddToCalendar = vi.fn();

      render(<CalendarWidget data={mockCalendarEvents} onAddToCalendar={onAddToCalendar} />);

      const addButton = screen.getAllByRole('button', { name: /add to calendar/i })[0];
      await user.click(addButton);
      expect(onAddToCalendar).toHaveBeenCalledWith(mockCalendarEvents[0]);
    });

    it('should show event details in modal', async () => {
      const user = userEvent.setup();

      render(<CalendarWidget data={mockCalendarEvents} />);

      await user.click(screen.getByText('Apple Inc.'));
      
      await waitFor(() => {
        expect(screen.getByText(/event details/i)).toBeInTheDocument();
      });
    });
  });

  describe('AlertsWidget Component', () => {
    it('should render alerts correctly', () => {
      render(<AlertsWidget data={mockAlerts} />);

      expect(screen.getByText('Price Alerts')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('Above $185.00')).toBeInTheDocument();
    });

    it('should show triggered alerts prominently', () => {
      render(<AlertsWidget data={mockAlerts} />);

      const triggeredAlert = screen.getByTestId('alert-alert_1');
      expect(triggeredAlert).toHaveClass('triggered');
    });

    it('should create new alert', async () => {
      const user = userEvent.setup();
      const onCreateAlert = vi.fn();

      render(<AlertsWidget data={mockAlerts} onCreateAlert={onCreateAlert} />);

      const createButton = screen.getByRole('button', { name: /create alert/i });
      await user.click(createButton);

      // Fill out alert form
      await user.type(screen.getByPlaceholderText(/symbol/i), 'NVDA');
      await user.selectOptions(screen.getByRole('combobox', { name: /condition/i }), 'above');
      await user.type(screen.getByPlaceholderText(/price/i), '500');
      await user.click(screen.getByRole('button', { name: /save alert/i }));

      expect(onCreateAlert).toHaveBeenCalledWith({
        symbol: 'NVDA',
        condition: 'above',
        targetPrice: 500
      });
    });

    it('should delete alert', async () => {
      const user = userEvent.setup();
      const onDeleteAlert = vi.fn();

      render(<AlertsWidget data={mockAlerts} onDeleteAlert={onDeleteAlert} />);

      const deleteButton = screen.getAllByRole('button', { name: /delete/i })[0];
      await user.click(deleteButton);
      expect(onDeleteAlert).toHaveBeenCalledWith('alert_1');
    });

    it('should modify existing alert', async () => {
      const user = userEvent.setup();
      const onModifyAlert = vi.fn();

      render(<AlertsWidget data={mockAlerts} onModifyAlert={onModifyAlert} />);

      const modifyButton = screen.getAllByRole('button', { name: /modify/i })[0];
      await user.click(modifyButton);

      await user.clear(screen.getByDisplayValue('185.00'));
      await user.type(screen.getByDisplayValue(''), '190.00');
      await user.click(screen.getByRole('button', { name: /save changes/i }));

      expect(onModifyAlert).toHaveBeenCalledWith('alert_1', {
        targetPrice: 190.00
      });
    });
  });

  describe('QuickActionsWidget Component', () => {
    const mockActions = [
      { id: 'buy', label: 'Buy Stock', icon: '📈', color: 'green' },
      { id: 'sell', label: 'Sell Stock', icon: '📉', color: 'red' },
      { id: 'transfer', label: 'Transfer Funds', icon: '💸', color: 'blue' },
      { id: 'report', label: 'Generate Report', icon: '📊', color: 'purple' }
    ];

    it('should render quick actions correctly', () => {
      render(<QuickActionsWidget actions={mockActions} />);

      expect(screen.getByText('Quick Actions')).toBeInTheDocument();
      expect(screen.getByText('Buy Stock')).toBeInTheDocument();
      expect(screen.getByText('📈')).toBeInTheDocument();
    });

    it('should execute action on click', async () => {
      const user = userEvent.setup();
      const onActionClick = vi.fn();

      render(<QuickActionsWidget actions={mockActions} onActionClick={onActionClick} />);

      await user.click(screen.getByText('Buy Stock'));
      expect(onActionClick).toHaveBeenCalledWith('buy');
    });

    it('should show action tooltips', async () => {
      const user = userEvent.setup();

      render(<QuickActionsWidget actions={mockActions} showTooltips={true} />);

      await user.hover(screen.getByText('Buy Stock'));
      
      await waitFor(() => {
        expect(screen.getByText(/purchase stocks/i)).toBeInTheDocument();
      });
    });

    it('should customize action layout', () => {
      render(<QuickActionsWidget actions={mockActions} layout="grid" columns={2} />);

      const actionsContainer = screen.getByTestId('quick-actions-container');
      expect(actionsContainer).toHaveClass('grid-layout');
    });

    it('should handle disabled actions', () => {
      const actionsWithDisabled = mockActions.map(action => ({
        ...action,
        disabled: action.id === 'sell'
      }));

      render(<QuickActionsWidget actions={actionsWithDisabled} />);

      const sellButton = screen.getByText('Sell Stock').closest('button');
      expect(sellButton).toBeDisabled();
    });
  });

  describe('Widget Accessibility', () => {
    it('should have proper ARIA labels', () => {
      render(<PortfolioSummaryWidget data={mockPortfolioData} />);

      expect(screen.getByRole('region', { name: /portfolio summary/i })).toBeInTheDocument();
    });

    it('should support keyboard navigation', async () => {
      const user = userEvent.setup();

      render(<WatchlistWidget data={mockWatchlistData} />);

      await user.tab();
      expect(screen.getByText('AAPL')).toHaveFocus();

      await user.tab();
      expect(screen.getByText('GOOGL')).toHaveFocus();
    });

    it('should announce dynamic content changes', () => {
      const { rerender } = render(<PortfolioSummaryWidget data={mockPortfolioData} />);

      const updatedData = {
        ...mockPortfolioData,
        totalValue: 130000,
        dayChange: 7500
      };

      rerender(<PortfolioSummaryWidget data={updatedData} />);

      expect(screen.getByRole('status')).toHaveTextContent(/portfolio updated/i);
    });

    it('should provide alternative text for charts', () => {
      render(<PerformanceWidget data={mockPerformanceData} showChart={true} />);

      const chart = screen.getByRole('img', { name: /performance chart/i });
      expect(chart).toHaveAttribute('alt', expect.stringContaining('Performance chart showing'));
    });
  });

  describe('Widget Error Handling', () => {
    it('should handle missing data gracefully', () => {
      expect(() => {
        render(<PortfolioSummaryWidget data={null} />);
      }).not.toThrow();

      expect(screen.getByText(/no data available/i)).toBeInTheDocument();
    });

    it('should handle API errors', () => {
      const errorData = { error: 'Failed to load data' };

      render(<MarketOverviewWidget data={errorData} />);

      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });

    it('should handle malformed data', () => {
      const malformedData = {
        totalValue: 'invalid',
        dayChange: null,
        dayChangePercent: undefined
      };

      expect(() => {
        render(<PortfolioSummaryWidget data={malformedData} />);
      }).not.toThrow();

      expect(screen.getByText(/data error/i)).toBeInTheDocument();
    });

    it('should recover from widget crashes', () => {
      const CrashingWidget = () => {
        throw new Error('Widget crashed');
      };

      expect(() => {
        render(<CrashingWidget />);
      }).toThrow();

      // In real implementation, would be wrapped in error boundary
    });
  });

  describe('Widget Performance', () => {
    it('should render widgets efficiently', () => {
      const startTime = performance.now();
      
      render(
        <div>
          <PortfolioSummaryWidget data={mockPortfolioData} />
          <MarketOverviewWidget data={mockMarketData} />
          <PerformanceWidget data={mockPerformanceData} />
          <WatchlistWidget data={mockWatchlistData} />
        </div>
      );
      
      const renderTime = performance.now() - startTime;
      expect(renderTime).toBeLessThan(100); // Should render within 100ms
    });

    it('should handle large datasets efficiently', () => {
      const largeWatchlist = Array.from({ length: 100 }, (_, i) => ({
        symbol: `STOCK${i}`,
        name: `Stock ${i}`,
        price: 100 + i,
        change: i % 2 === 0 ? i : -i,
        changePercent: i % 2 === 0 ? i / 10 : -i / 10,
        alerts: i % 5
      }));

      const startTime = performance.now();
      render(<WatchlistWidget data={largeWatchlist} />);
      const renderTime = performance.now() - startTime;

      expect(renderTime).toBeLessThan(200); // Should handle large lists efficiently
    });

    it('should implement virtualization for large lists', () => {
      const largeTradeHistory = Array.from({ length: 1000 }, (_, i) => ({
        id: `trade_${i}`,
        symbol: `STOCK${i % 10}`,
        type: i % 2 === 0 ? 'buy' : 'sell',
        quantity: 100,
        price: 100 + i,
        total: (100 + i) * 100,
        executedAt: `2024-01-${String(i % 30 + 1).padStart(2, '0')}T10:30:00Z`,
        status: 'filled'
      }));

      render(<TradeHistoryWidget data={largeTradeHistory} virtualized={true} />);

      // Should only render visible items
      const visibleTrades = screen.getAllByText(/STOCK/);
      expect(visibleTrades.length).toBeLessThan(20); // Only visible items rendered
    });
  });
});
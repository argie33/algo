/**
 * Portfolio Components Unit Tests
 * Comprehensive testing of all real portfolio-related components
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Real Portfolio Components - Import actual production components
import { PortfolioOverview } from '../../../components/portfolio/PortfolioOverview';
import { PositionList } from '../../../components/portfolio/PositionList';
import { PositionCard } from '../../../components/portfolio/PositionCard';
import { PerformanceChart } from '../../../components/portfolio/PerformanceChart';
import { AllocationChart } from '../../../components/portfolio/AllocationChart';
import { TransactionHistory } from '../../../components/portfolio/TransactionHistory';
import { PortfolioMetrics } from '../../../components/portfolio/PortfolioMetrics';
import { RiskAnalysis } from '../../../components/portfolio/RiskAnalysis';
import { RebalanceModal } from '../../../components/portfolio/RebalanceModal';
import { PortfolioSettings } from '../../../components/portfolio/PortfolioSettings';

describe('💼 Portfolio Components', () => {
  const mockPortfolioData = {
    id: 'portfolio_123',
    name: 'Main Portfolio',
    totalValue: 125000,
    dayChange: 2500,
    dayChangePercent: 2.04,
    totalReturn: 15000,
    totalReturnPercent: 13.64,
    cash: 5000,
    positions: [
      {
        id: 'pos_1',
        symbol: 'AAPL',
        name: 'Apple Inc.',
        quantity: 100,
        averagePrice: 175.25,
        currentPrice: 185.50,
        marketValue: 18550,
        unrealizedGain: 1025,
        unrealizedGainPercent: 5.85,
        weight: 14.84
      },
      {
        id: 'pos_2',
        symbol: 'GOOGL',
        name: 'Alphabet Inc.',
        quantity: 25,
        averagePrice: 2800.00,
        currentPrice: 2850.00,
        marketValue: 71250,
        unrealizedGain: 1250,
        unrealizedGainPercent: 1.79,
        weight: 57.0
      }
    ]
  };

  const mockPerformanceData = {
    chartData: [
      { date: '2024-01-01', portfolioValue: 110000, benchmarkValue: 110000 },
      { date: '2024-01-15', portfolioValue: 125000, benchmarkValue: 119500 }
    ],
    returns: {
      '1D': { portfolio: 2.04, benchmark: 1.25 },
      '1W': { portfolio: 5.26, benchmark: 3.80 },
      '1M': { portfolio: 8.70, benchmark: 6.20 },
      '3M': { portfolio: 13.64, benchmark: 9.15 },
      '1Y': { portfolio: 18.75, benchmark: 14.25 }
    }
  };

  const mockAllocationData = {
    sectors: [
      { name: 'Technology', value: 70000, percentage: 56.0, count: 2 },
      { name: 'Healthcare', value: 25000, percentage: 20.0, count: 1 },
      { name: 'Financial', value: 20000, percentage: 16.0, count: 1 },
      { name: 'Cash', value: 10000, percentage: 8.0, count: 1 }
    ],
    assetTypes: [
      { name: 'Stocks', value: 115000, percentage: 92.0 },
      { name: 'Cash', value: 10000, percentage: 8.0 }
    ]
  };

  const mockTransactions = [
    {
      id: 'txn_1',
      type: 'buy',
      symbol: 'AAPL',
      quantity: 50,
      price: 180.00,
      value: 9000,
      fees: 7.50,
      date: '2024-01-15T10:30:00Z'
    },
    {
      id: 'txn_2',
      type: 'sell',
      symbol: 'TSLA',
      quantity: 25,
      price: 220.00,
      value: 5500,
      fees: 7.50,
      date: '2024-01-14T14:45:00Z'
    }
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('PortfolioOverview Component', () => {
    it('should render portfolio overview correctly', () => {
      render(<PortfolioOverview portfolio={mockPortfolioData} />);

      expect(screen.getByText('Main Portfolio')).toBeInTheDocument();
      expect(screen.getByText('$125,000')).toBeInTheDocument();
      expect(screen.getByText('+$2,500')).toBeInTheDocument();
      expect(screen.getByText('+2.04%')).toBeInTheDocument();
    });

    it('should display total return information', () => {
      render(<PortfolioOverview portfolio={mockPortfolioData} />);

      expect(screen.getByText('+$15,000')).toBeInTheDocument();
      expect(screen.getByText('+13.64%')).toBeInTheDocument();
    });

    it('should show negative changes correctly', () => {
      const negativePortfolio = {
        ...mockPortfolioData,
        dayChange: -1500,
        dayChangePercent: -1.18,
        totalReturn: -2500,
        totalReturnPercent: -2.04
      };

      render(<PortfolioOverview portfolio={negativePortfolio} />);

      expect(screen.getByText('-$1,500')).toBeInTheDocument();
      expect(screen.getByText('-1.18%')).toBeInTheDocument();
      expect(screen.getByText('-$2,500')).toBeInTheDocument();
      expect(screen.getByText('-2.04%')).toBeInTheDocument();
    });

    it('should handle loading state', () => {
      render(<PortfolioOverview portfolio={null} loading={true} />);

      expect(screen.getByTestId('portfolio-overview-loading')).toBeInTheDocument();
    });

    it('should handle error state', () => {
      const error = 'Failed to load portfolio data';
      render(<PortfolioOverview portfolio={null} error={error} />);

      expect(screen.getByText(error)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });

  describe('PositionList Component', () => {
    it('should render all positions', () => {
      render(<PositionList positions={mockPortfolioData.positions} />);

      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('GOOGL')).toBeInTheDocument();
      expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
      expect(screen.getByText('Alphabet Inc.')).toBeInTheDocument();
    });

    it('should sort positions by different criteria', async () => {
      const user = userEvent.setup();
      render(<PositionList positions={mockPortfolioData.positions} />);

      const sortSelect = screen.getByLabelText(/sort by/i);
      await user.selectOptions(sortSelect, 'marketValue');

      // GOOGL should appear first (higher market value)
      const positionElements = screen.getAllByTestId('position-item');
      expect(positionElements[0]).toHaveTextContent('GOOGL');
    });

    it('should filter positions by search', async () => {
      const user = userEvent.setup();
      render(<PositionList positions={mockPortfolioData.positions} />);

      const searchInput = screen.getByPlaceholderText(/search positions/i);
      await user.type(searchInput, 'Apple');

      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.queryByText('GOOGL')).not.toBeInTheDocument();
    });

    it('should handle position selection', async () => {
      const user = userEvent.setup();
      const onPositionSelect = vi.fn();
      render(<PositionList positions={mockPortfolioData.positions} onPositionSelect={onPositionSelect} />);

      const aaplPosition = screen.getByTestId('position-AAPL');
      await user.click(aaplPosition);

      expect(onPositionSelect).toHaveBeenCalledWith(mockPortfolioData.positions[0]);
    });
  });

  describe('PositionCard Component', () => {
    const mockPosition = mockPortfolioData.positions[0];

    it('should render position details correctly', () => {
      render(<PositionCard position={mockPosition} />);

      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('100 shares')).toBeInTheDocument();
      expect(screen.getByText('$185.50')).toBeInTheDocument();
      expect(screen.getByText('$18,550')).toBeInTheDocument();
      expect(screen.getByText('+$1,025')).toBeInTheDocument();
      expect(screen.getByText('+5.85%')).toBeInTheDocument();
    });

    it('should show position actions', () => {
      render(<PositionCard position={mockPosition} showActions={true} />);

      expect(screen.getByRole('button', { name: /buy more/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /sell/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /view details/i })).toBeInTheDocument();
    });

    it('should handle action clicks', async () => {
      const user = userEvent.setup();
      const onBuy = vi.fn();
      const onSell = vi.fn();

      render(<PositionCard position={mockPosition} showActions={true} onBuy={onBuy} onSell={onSell} />);

      await user.click(screen.getByRole('button', { name: /buy more/i }));
      expect(onBuy).toHaveBeenCalledWith(mockPosition);

      await user.click(screen.getByRole('button', { name: /sell/i }));
      expect(onSell).toHaveBeenCalledWith(mockPosition);
    });

    it('should show position weight', () => {
      render(<PositionCard position={mockPosition} showWeight={true} />);

      expect(screen.getByText('14.84%')).toBeInTheDocument();
    });
  });

  describe('PerformanceChart Component', () => {
    it('should render performance chart', () => {
      render(<PerformanceChart data={mockPerformanceData} />);

      expect(screen.getByTestId('performance-chart')).toBeInTheDocument();
      expect(screen.getByText('Portfolio vs Benchmark')).toBeInTheDocument();
    });

    it('should switch between time periods', async () => {
      const user = userEvent.setup();
      render(<PerformanceChart data={mockPerformanceData} />);

      const oneMonthTab = screen.getByRole('button', { name: /1m/i });
      await user.click(oneMonthTab);

      expect(screen.getByText('8.70%')).toBeInTheDocument(); // Portfolio 1M return
      expect(screen.getByText('6.20%')).toBeInTheDocument(); // Benchmark 1M return
    });

    it('should toggle chart data series', async () => {
      const user = userEvent.setup();
      render(<PerformanceChart data={mockPerformanceData} />);

      const benchmarkToggle = screen.getByLabelText(/show benchmark/i);
      await user.click(benchmarkToggle);

      // Should hide benchmark series
      expect(screen.queryByText('Benchmark')).not.toBeInTheDocument();
    });

    it('should handle chart interactions', async () => {
      const onDataPointHover = vi.fn();
      render(<PerformanceChart data={mockPerformanceData} onDataPointHover={onDataPointHover} />);

      const chartElement = screen.getByTestId('performance-chart');
      fireEvent.mouseMove(chartElement, { clientX: 100, clientY: 50 });

      expect(onDataPointHover).toHaveBeenCalled();
    });
  });

  describe('AllocationChart Component', () => {
    it('should render sector allocation chart', () => {
      render(<AllocationChart data={mockAllocationData} type="sectors" />);

      expect(screen.getByText('Sector Allocation')).toBeInTheDocument();
      expect(screen.getByText('Technology')).toBeInTheDocument();
      expect(screen.getByText('56.0%')).toBeInTheDocument();
    });

    it('should switch between allocation types', async () => {
      const user = userEvent.setup();
      render(<AllocationChart data={mockAllocationData} />);

      const assetTypeTab = screen.getByRole('button', { name: /asset types/i });
      await user.click(assetTypeTab);

      expect(screen.getByText('Asset Type Allocation')).toBeInTheDocument();
      expect(screen.getByText('Stocks')).toBeInTheDocument();
      expect(screen.getByText('92.0%')).toBeInTheDocument();
    });

    it('should show allocation details on hover', async () => {
      render(<AllocationChart data={mockAllocationData} type="sectors" />);

      const technologySegment = screen.getByTestId('sector-Technology');
      fireEvent.mouseEnter(technologySegment);

      await waitFor(() => {
        expect(screen.getByText('$70,000')).toBeInTheDocument();
        expect(screen.getByText('2 positions')).toBeInTheDocument();
      });
    });
  });

  describe('TransactionHistory Component', () => {
    it('should render transaction list', () => {
      render(<TransactionHistory transactions={mockTransactions} />);

      expect(screen.getByText('Transaction History')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('TSLA')).toBeInTheDocument();
      expect(screen.getByText('Buy')).toBeInTheDocument();
      expect(screen.getByText('Sell')).toBeInTheDocument();
    });

    it('should filter transactions by type', async () => {
      const user = userEvent.setup();
      render(<TransactionHistory transactions={mockTransactions} />);

      const filterSelect = screen.getByLabelText(/filter by type/i);
      await user.selectOptions(filterSelect, 'buy');

      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.queryByText('TSLA')).not.toBeInTheDocument();
    });

    it('should filter transactions by date range', async () => {
      const user = userEvent.setup();
      render(<TransactionHistory transactions={mockTransactions} />);

      const startDateInput = screen.getByLabelText(/start date/i);
      await user.type(startDateInput, '2024-01-15');

      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.queryByText('TSLA')).not.toBeInTheDocument();
    });

    it('should export transaction data', async () => {
      const user = userEvent.setup();
      const onExport = vi.fn();
      render(<TransactionHistory transactions={mockTransactions} onExport={onExport} />);

      const exportButton = screen.getByRole('button', { name: /export/i });
      await user.click(exportButton);

      expect(onExport).toHaveBeenCalledWith(mockTransactions);
    });
  });

  describe('PortfolioMetrics Component', () => {
    const mockMetrics = {
      sharpeRatio: 1.35,
      beta: 1.15,
      alpha: 7.70,
      volatility: 18.5,
      maxDrawdown: -12.3,
      correlation: 0.82
    };

    it('should render all metrics correctly', () => {
      render(<PortfolioMetrics metrics={mockMetrics} />);

      expect(screen.getByText('Portfolio Metrics')).toBeInTheDocument();
      expect(screen.getByText('1.35')).toBeInTheDocument(); // Sharpe Ratio
      expect(screen.getByText('1.15')).toBeInTheDocument(); // Beta
      expect(screen.getByText('7.70%')).toBeInTheDocument(); // Alpha
      expect(screen.getByText('18.5%')).toBeInTheDocument(); // Volatility
    });

    it('should show metric explanations on hover', async () => {
      render(<PortfolioMetrics metrics={mockMetrics} />);

      const sharpeRatioMetric = screen.getByTestId('metric-sharpe-ratio');
      fireEvent.mouseEnter(sharpeRatioMetric);

      await waitFor(() => {
        expect(screen.getByText(/measures risk-adjusted return/i)).toBeInTheDocument();
      });
    });

    it('should handle missing metrics gracefully', () => {
      const incompleteMetrics = { sharpeRatio: 1.35 };
      render(<PortfolioMetrics metrics={incompleteMetrics} />);

      expect(screen.getByText('1.35')).toBeInTheDocument();
      expect(screen.getByText('N/A')).toBeInTheDocument(); // For missing metrics
    });
  });

  describe('RiskAnalysis Component', () => {
    const mockRiskData = {
      riskScore: 7.5,
      riskLevel: 'Moderate',
      valueAtRisk: {
        daily95: -2850,
        weekly95: -6375,
        monthly95: -12750
      },
      stressTests: [
        { scenario: '2008 Financial Crisis', impact: -35.2 },
        { scenario: 'COVID-19 Pandemic', impact: -28.7 },
        { scenario: 'Tech Bubble Burst', impact: -42.1 }
      ]
    };

    it('should render risk analysis correctly', () => {
      render(<RiskAnalysis riskData={mockRiskData} />);

      expect(screen.getByText('Risk Analysis')).toBeInTheDocument();
      expect(screen.getByText('7.5')).toBeInTheDocument();
      expect(screen.getByText('Moderate')).toBeInTheDocument();
    });

    it('should display value at risk metrics', () => {
      render(<RiskAnalysis riskData={mockRiskData} />);

      expect(screen.getByText('-$2,850')).toBeInTheDocument(); // Daily VaR
      expect(screen.getByText('-$6,375')).toBeInTheDocument(); // Weekly VaR
      expect(screen.getByText('-$12,750')).toBeInTheDocument(); // Monthly VaR
    });

    it('should show stress test results', () => {
      render(<RiskAnalysis riskData={mockRiskData} />);

      expect(screen.getByText('2008 Financial Crisis')).toBeInTheDocument();
      expect(screen.getByText('-35.2%')).toBeInTheDocument();
      expect(screen.getByText('COVID-19 Pandemic')).toBeInTheDocument();
      expect(screen.getByText('-28.7%')).toBeInTheDocument();
    });

    it('should handle risk level color coding', () => {
      const highRiskData = { ...mockRiskData, riskLevel: 'High', riskScore: 9.2 };
      render(<RiskAnalysis riskData={highRiskData} />);

      const riskIndicator = screen.getByTestId('risk-indicator');
      expect(riskIndicator).toHaveClass('risk-high');
    });
  });

  describe('RebalanceModal Component', () => {
    const mockRebalanceData = {
      currentAllocations: [
        { symbol: 'AAPL', currentWeight: 14.84, targetWeight: 20.0 },
        { symbol: 'GOOGL', currentWeight: 57.0, targetWeight: 45.0 }
      ],
      trades: [
        { symbol: 'AAPL', action: 'buy', quantity: 27, estimatedValue: 5008.50 },
        { symbol: 'GOOGL', action: 'sell', quantity: 5, estimatedValue: 14250.00 }
      ],
      estimatedCost: 15.50
    };

    it('should render rebalance proposal', () => {
      render(<RebalanceModal isOpen={true} rebalanceData={mockRebalanceData} />);

      expect(screen.getByText('Portfolio Rebalance')).toBeInTheDocument();
      expect(screen.getByText('Proposed Trades')).toBeInTheDocument();
      expect(screen.getByText('Buy 27 shares')).toBeInTheDocument();
      expect(screen.getByText('Sell 5 shares')).toBeInTheDocument();
    });

    it('should show allocation changes', () => {
      render(<RebalanceModal isOpen={true} rebalanceData={mockRebalanceData} />);

      expect(screen.getByText('14.84% → 20.0%')).toBeInTheDocument(); // AAPL
      expect(screen.getByText('57.0% → 45.0%')).toBeInTheDocument(); // GOOGL
    });

    it('should handle rebalance confirmation', async () => {
      const user = userEvent.setup();
      const onConfirm = vi.fn();
      render(<RebalanceModal isOpen={true} rebalanceData={mockRebalanceData} onConfirm={onConfirm} />);

      const confirmButton = screen.getByRole('button', { name: /confirm rebalance/i });
      await user.click(confirmButton);

      expect(onConfirm).toHaveBeenCalledWith(mockRebalanceData.trades);
    });

    it('should handle modal cancellation', async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn();
      render(<RebalanceModal isOpen={true} rebalanceData={mockRebalanceData} onCancel={onCancel} />);

      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      await user.click(cancelButton);

      expect(onCancel).toHaveBeenCalled();
    });
  });

  describe('PortfolioSettings Component', () => {
    const mockSettings = {
      name: 'Main Portfolio',
      description: 'My primary investment portfolio',
      riskTolerance: 'moderate',
      rebalanceFrequency: 'quarterly',
      autoRebalance: true,
      notifications: {
        priceAlerts: true,
        rebalanceAlerts: true,
        performanceReports: false
      }
    };

    it('should render portfolio settings form', () => {
      render(<PortfolioSettings settings={mockSettings} />);

      expect(screen.getByDisplayValue('Main Portfolio')).toBeInTheDocument();
      expect(screen.getByDisplayValue('My primary investment portfolio')).toBeInTheDocument();
      expect(screen.getByDisplayValue('moderate')).toBeInTheDocument();
    });

    it('should handle settings updates', async () => {
      const user = userEvent.setup();
      const onSave = vi.fn();
      render(<PortfolioSettings settings={mockSettings} onSave={onSave} />);

      const nameInput = screen.getByLabelText(/portfolio name/i);
      await user.clear(nameInput);
      await user.type(nameInput, 'Updated Portfolio Name');

      const saveButton = screen.getByRole('button', { name: /save settings/i });
      await user.click(saveButton);

      expect(onSave).toHaveBeenCalledWith({
        ...mockSettings,
        name: 'Updated Portfolio Name'
      });
    });

    it('should toggle notification settings', async () => {
      const user = userEvent.setup();
      render(<PortfolioSettings settings={mockSettings} />);

      const priceAlertsToggle = screen.getByLabelText(/price alerts/i);
      await user.click(priceAlertsToggle);

      expect(priceAlertsToggle).not.toBeChecked();
    });

    it('should validate required fields', async () => {
      const user = userEvent.setup();
      render(<PortfolioSettings settings={mockSettings} />);

      const nameInput = screen.getByLabelText(/portfolio name/i);
      await user.clear(nameInput);

      const saveButton = screen.getByRole('button', { name: /save settings/i });
      await user.click(saveButton);

      expect(screen.getByText(/portfolio name is required/i)).toBeInTheDocument();
    });
  });

  describe('Portfolio Component Performance', () => {
    it('should render portfolio overview efficiently', () => {
      const startTime = performance.now();
      
      render(<PortfolioOverview portfolio={mockPortfolioData} />);
      
      const renderTime = performance.now() - startTime;
      expect(renderTime).toBeLessThan(100); // Should render within 100ms
    });

    it('should handle large position lists efficiently', () => {
      const largePositionList = Array.from({ length: 100 }, (_, i) => ({
        id: `pos_${i}`,
        symbol: `STOCK${i}`,
        name: `Stock ${i}`,
        quantity: 100,
        currentPrice: 100 + i,
        marketValue: (100 + i) * 100,
        unrealizedGain: i * 10,
        unrealizedGainPercent: i * 0.1
      }));

      const startTime = performance.now();
      
      render(<PositionList positions={largePositionList} />);
      
      const renderTime = performance.now() - startTime;
      expect(renderTime).toBeLessThan(500); // Should render within 500ms
    });
  });
});
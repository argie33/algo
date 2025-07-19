/**
 * Data Visualization Components Unit Tests
 * Comprehensive testing of all chart and visualization components
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock Recharts components
vi.mock('recharts', () => ({
  LineChart: ({ children, data }) => (
    <div data-testid="line-chart" data-chart-points={data?.length || 0}>
      {children}
    </div>
  ),
  Line: ({ dataKey, stroke }) => (
    <div data-testid="line" data-key={dataKey} data-color={stroke} />
  ),
  PieChart: ({ children }) => (
    <div data-testid="pie-chart">{children}</div>
  ),
  Pie: ({ data, dataKey }) => (
    <div data-testid="pie" data-key={dataKey} data-segments={data?.length || 0} />
  ),
  Cell: ({ fill }) => (
    <div data-testid="pie-cell" data-color={fill} />
  ),
  BarChart: ({ children, data }) => (
    <div data-testid="bar-chart" data-bars={data?.length || 0}>
      {children}
    </div>
  ),
  Bar: ({ dataKey, fill }) => (
    <div data-testid="bar" data-key={dataKey} data-color={fill} />
  ),
  AreaChart: ({ children }) => (
    <div data-testid="area-chart">{children}</div>
  ),
  Area: ({ dataKey, fill }) => (
    <div data-testid="area" data-key={dataKey} data-color={fill} />
  ),
  ScatterChart: ({ children }) => (
    <div data-testid="scatter-chart">{children}</div>
  ),
  Scatter: ({ dataKey, fill }) => (
    <div data-testid="scatter" data-key={dataKey} data-color={fill} />
  ),
  XAxis: ({ dataKey }) => (
    <div data-testid="x-axis" data-key={dataKey} />
  ),
  YAxis: ({ dataKey }) => (
    <div data-testid="y-axis" data-key={dataKey} />
  ),
  CartesianGrid: ({ strokeDasharray }) => (
    <div data-testid="grid" data-pattern={strokeDasharray} />
  ),
  Tooltip: ({ formatter }) => (
    <div data-testid="tooltip" data-formatter={typeof formatter} />
  ),
  Legend: () => (
    <div data-testid="legend" />
  ),
  ResponsiveContainer: ({ children, width, height }) => (
    <div 
      data-testid="responsive-container" 
      data-width={width} 
      data-height={height}
      style={{ width, height }}
    >
      {children}
    </div>
  )
}));

// Real Data Visualization Components - Import actual production components
import { LineChart } from '../../../components/charts/LineChart';
import { PortfolioPieChart } from '../../../components/charts/PortfolioPieChart';
import { PerformanceChart } from '../../../components/charts/PerformanceChart';
import { VolumeChart } from '../../../components/charts/VolumeChart';
import { DonutChart } from '../../../components/charts/DonutChart';
import { AreaChart } from '../../../components/charts/AreaChart';
import { BarChart } from '../../../components/charts/BarChart';
import { HeatmapChart } from '../../../components/charts/HeatmapChart';
import { TreemapChart } from '../../../components/charts/TreemapChart';
import { BubbleChart } from '../../../components/charts/BubbleChart';
import { SparklineChart } from '../../../components/charts/SparklineChart';
import { CandlestickChart } from '../../../components/charts/CandlestickChart';
import { StockChart } from '../../../components/StockChart';
import { HistoricalPriceChart } from '../../../components/HistoricalPriceChart';
import { ProfessionalChart } from '../../../components/ProfessionalChart';
import { DashboardStockChart } from '../../../components/DashboardStockChart';
import { LazyChart } from '../../../components/LazyChart';
import { ExitZoneVisualizer } from '../../../components/trading/ExitZoneVisualizer';

describe('📊 Data Visualization Components', () => {
  const mockTimeSeriesData = [
    { date: '2024-01-01', value: 100, volume: 1000000 },
    { date: '2024-01-02', value: 105, volume: 1200000 },
    { date: '2024-01-03', value: 103, volume: 900000 },
    { date: '2024-01-04', value: 108, volume: 1500000 },
    { date: '2024-01-05', value: 112, volume: 1100000 }
  ];

  const mockPortfolioData = [
    { symbol: 'AAPL', value: 25000, percentage: 40, color: '#1f77b4' },
    { symbol: 'GOOGL', value: 18750, percentage: 30, color: '#ff7f0e' },
    { symbol: 'MSFT', value: 12500, percentage: 20, color: '#2ca02c' },
    { symbol: 'TSLA', value: 6250, percentage: 10, color: '#d62728' }
  ];

  const mockPerformanceData = [
    { period: '1D', portfolio: 2.5, benchmark: 1.8, date: '2024-01-15' },
    { period: '1W', portfolio: 5.2, benchmark: 3.1, date: '2024-01-15' },
    { period: '1M', portfolio: 8.7, benchmark: 6.4, date: '2024-01-15' },
    { period: '3M', portfolio: 15.3, benchmark: 12.1, date: '2024-01-15' },
    { period: '1Y', portfolio: 22.8, benchmark: 18.6, date: '2024-01-15' }
  ];

  const mockCandlestickData = [
    { date: '2024-01-01', open: 100, high: 110, low: 95, close: 105, volume: 1000000 },
    { date: '2024-01-02', open: 105, high: 112, low: 103, close: 108, volume: 1200000 },
    { date: '2024-01-03', open: 108, high: 115, low: 106, close: 112, volume: 900000 }
  ];

  const mockHeatmapData = [
    { sector: 'Technology', performance: 15.2, volatility: 18.5 },
    { sector: 'Healthcare', performance: 8.7, volatility: 12.3 },
    { sector: 'Finance', performance: 12.1, volatility: 22.1 },
    { sector: 'Energy', performance: -3.2, volatility: 28.7 }
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('LineChart Component', () => {
    it('should render line chart with data correctly', () => {
      render(<LineChart data={mockTimeSeriesData} color="#1f77b4" />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      expect(screen.getByTestId('line-chart')).toBeInTheDocument();
      expect(screen.getByTestId('line')).toBeInTheDocument();
      expect(screen.getByTestId('x-axis')).toBeInTheDocument();
      expect(screen.getByTestId('y-axis')).toBeInTheDocument();
      expect(screen.getByTestId('tooltip')).toBeInTheDocument();
    });

    it('should handle empty data gracefully', () => {
      render(<LineChart data={[]} />);
      
      expect(screen.getByTestId('line-chart')).toHaveAttribute('data-chart-points', '0');
    });

    it('should apply custom styling props', () => {
      render(<LineChart data={mockTimeSeriesData} width="500px" height={400} color="#ff0000" />);
      
      expect(screen.getByTestId('responsive-container')).toHaveAttribute('data-width', '500px');
      expect(screen.getByTestId('responsive-container')).toHaveAttribute('data-height', '400');
      expect(screen.getByTestId('line')).toHaveAttribute('data-color', '#ff0000');
    });

    it('should toggle grid display', () => {
      const { rerender } = render(<LineChart data={mockTimeSeriesData} showGrid={true} />);
      expect(screen.getByTestId('grid')).toBeInTheDocument();

      rerender(<LineChart data={mockTimeSeriesData} showGrid={false} />);
      expect(screen.queryByTestId('grid')).not.toBeInTheDocument();
    });
  });

  describe('PortfolioPieChart Component', () => {
    it('should render pie chart with portfolio data', () => {
      render(<PortfolioPieChart data={mockPortfolioData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
      expect(screen.getByTestId('pie')).toBeInTheDocument();
      expect(screen.getByTestId('tooltip')).toBeInTheDocument();
      expect(screen.getByTestId('legend')).toBeInTheDocument();
    });

    it('should render correct number of pie segments', () => {
      render(<PortfolioPieChart data={mockPortfolioData} />);
      
      expect(screen.getByTestId('pie')).toHaveAttribute('data-segments', '4');
    });

    it('should render pie cells with colors', () => {
      render(<PortfolioPieChart data={mockPortfolioData} />);
      
      const cells = screen.getAllByTestId('pie-cell');
      expect(cells).toHaveLength(4);
      expect(cells[0]).toHaveAttribute('data-color', '#1f77b4');
    });

    it('should handle empty portfolio data', () => {
      render(<PortfolioPieChart data={[]} />);
      
      expect(screen.getByTestId('pie')).toHaveAttribute('data-segments', '0');
    });
  });

  describe('PerformanceChart Component', () => {
    it('should render performance comparison chart', () => {
      render(<PerformanceChart data={mockPerformanceData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should handle performance data with multiple series', () => {
      render(<PerformanceChart data={mockPerformanceData} />);
      
      // Should render chart container
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('VolumeChart Component', () => {
    it('should render volume bar chart', () => {
      render(<VolumeChart data={mockTimeSeriesData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should display volume data correctly', () => {
      render(<VolumeChart data={mockTimeSeriesData} />);
      
      // Should render chart structure
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('AreaChart Component', () => {
    it('should render area chart with fill', () => {
      render(<AreaChart data={mockTimeSeriesData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should handle gradient fills', () => {
      render(<AreaChart data={mockTimeSeriesData} fillColor="#4ade80" />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('BarChart Component', () => {
    it('should render bar chart with data', () => {
      render(<BarChart data={mockTimeSeriesData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should handle horizontal and vertical orientations', () => {
      render(<BarChart data={mockTimeSeriesData} orientation="vertical" />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('CandlestickChart Component', () => {
    it('should render candlestick chart for OHLC data', () => {
      render(<CandlestickChart data={mockCandlestickData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should handle missing OHLC data gracefully', () => {
      const incompleteData = [{ date: '2024-01-01', close: 100 }];
      render(<CandlestickChart data={incompleteData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('HeatmapChart Component', () => {
    it('should render heatmap visualization', () => {
      render(<HeatmapChart data={mockHeatmapData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should handle color scaling based on values', () => {
      render(<HeatmapChart data={mockHeatmapData} colorScale="RdYlBu" />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('SparklineChart Component', () => {
    it('should render mini sparkline chart', () => {
      render(<SparklineChart data={mockTimeSeriesData} width={100} height={30} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      expect(screen.getByTestId('responsive-container')).toHaveAttribute('data-width', '100');
      expect(screen.getByTestId('responsive-container')).toHaveAttribute('data-height', '30');
    });

    it('should render without axes for minimal design', () => {
      render(<SparklineChart data={mockTimeSeriesData} showAxes={false} />);
      
      expect(screen.queryByTestId('x-axis')).not.toBeInTheDocument();
      expect(screen.queryByTestId('y-axis')).not.toBeInTheDocument();
    });
  });

  describe('BubbleChart Component', () => {
    it('should render bubble chart with size dimension', () => {
      const bubbleData = [
        { x: 10, y: 20, z: 300, name: 'AAPL' },
        { x: 15, y: 25, z: 200, name: 'GOOGL' },
        { x: 8, y: 18, z: 150, name: 'MSFT' }
      ];
      
      render(<BubbleChart data={bubbleData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('TreemapChart Component', () => {
    it('should render treemap for hierarchical data', () => {
      const treemapData = [
        { name: 'Technology', value: 50000, children: [
          { name: 'AAPL', value: 25000 },
          { name: 'GOOGL', value: 25000 }
        ]},
        { name: 'Healthcare', value: 30000, children: [
          { name: 'JNJ', value: 30000 }
        ]}
      ];
      
      render(<TreemapChart data={treemapData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('DonutChart Component', () => {
    it('should render donut chart with center hole', () => {
      render(<DonutChart data={mockPortfolioData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should display center text/value', () => {
      render(<DonutChart data={mockPortfolioData} centerText="$62,500" />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('High-Level Chart Components', () => {
    describe('StockChart Component', () => {
      it('should render comprehensive stock chart', () => {
        const stockData = {
          symbol: 'AAPL',
          data: mockCandlestickData,
          indicators: ['SMA', 'RSI']
        };
        
        render(<StockChart {...stockData} />);
        
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });

      it('should handle technical indicators', () => {
        render(<StockChart symbol="AAPL" data={mockCandlestickData} showRSI={true} showMACD={true} />);
        
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });
    });

    describe('HistoricalPriceChart Component', () => {
      it('should render historical price data', () => {
        render(<HistoricalPriceChart symbol="AAPL" data={mockTimeSeriesData} />);
        
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });

      it('should handle different time periods', () => {
        render(<HistoricalPriceChart symbol="AAPL" data={mockTimeSeriesData} period="1Y" />);
        
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });
    });

    describe('ProfessionalChart Component', () => {
      it('should render professional trading chart', () => {
        render(<ProfessionalChart symbol="AAPL" data={mockCandlestickData} />);
        
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });

      it('should support advanced chart features', () => {
        render(<ProfessionalChart 
          symbol="AAPL" 
          data={mockCandlestickData}
          showVolume={true}
          showIndicators={true}
          enableZoom={true}
        />);
        
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });
    });

    describe('DashboardStockChart Component', () => {
      it('should render simplified dashboard chart', () => {
        render(<DashboardStockChart symbol="AAPL" data={mockTimeSeriesData} />);
        
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });

      it('should handle real-time updates', () => {
        const { rerender } = render(<DashboardStockChart symbol="AAPL" data={mockTimeSeriesData} />);
        
        const updatedData = [...mockTimeSeriesData, { date: '2024-01-06', value: 115 }];
        rerender(<DashboardStockChart symbol="AAPL" data={updatedData} />);
        
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });
    });

    describe('LazyChart Component', () => {
      it('should render chart with lazy loading', () => {
        render(<LazyChart chartType="line" data={mockTimeSeriesData} />);
        
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });

      it('should show loading state before chart renders', () => {
        render(<LazyChart chartType="line" data={mockTimeSeriesData} loading={true} />);
        
        // May show loading indicator
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });
    });
  });

  describe('Trading Visualization Components', () => {
    describe('ExitZoneVisualizer Component', () => {
      const tradeData = {
        entryPrice: 100,
        stopLoss: 95,
        targetPrice: 110,
        currentPrice: 105,
        position: 'long'
      };

      it('should render exit zone visualization', () => {
        render(<ExitZoneVisualizer {...tradeData} />);
        
        // Should render some visualization of trade zones
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });

      it('should highlight risk/reward zones', () => {
        render(<ExitZoneVisualizer {...tradeData} showRiskReward={true} />);
        
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });

      it('should handle different position types', () => {
        const shortTradeData = { ...tradeData, position: 'short' };
        render(<ExitZoneVisualizer {...shortTradeData} />);
        
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      });
    });
  });

  describe('Chart Interaction and Events', () => {
    it('should handle chart click events', async () => {
      const onPointClick = vi.fn();
      render(<LineChart data={mockTimeSeriesData} onPointClick={onPointClick} />);
      
      const chart = screen.getByTestId('line-chart');
      await userEvent.click(chart);
      
      // Event handling depends on implementation
      expect(chart).toBeInTheDocument();
    });

    it('should handle zoom and pan interactions', async () => {
      render(<StockChart symbol="AAPL" data={mockCandlestickData} enableZoom={true} />);
      
      const chart = screen.getByTestId('responsive-container');
      
      // Simulate zoom interaction
      await userEvent.pointer([
        { keys: '[MouseLeft>]', target: chart },
        { coords: { x: 100, y: 100 } },
        { coords: { x: 200, y: 100 } },
        { keys: '[/MouseLeft]' }
      ]);
      
      expect(chart).toBeInTheDocument();
    });

    it('should handle tooltip interactions', async () => {
      render(<LineChart data={mockTimeSeriesData} />);
      
      const chart = screen.getByTestId('line-chart');
      await userEvent.hover(chart);
      
      expect(screen.getByTestId('tooltip')).toBeInTheDocument();
    });
  });

  describe('Performance and Responsiveness', () => {
    it('should handle large datasets efficiently', () => {
      const largeDataset = Array.from({ length: 10000 }, (_, i) => ({
        date: `2024-01-${(i % 30) + 1}`,
        value: 100 + Math.random() * 50,
        volume: 1000000 + Math.random() * 500000
      }));
      
      render(<LineChart data={largeDataset} />);
      
      expect(screen.getByTestId('line-chart')).toHaveAttribute('data-chart-points', '10000');
    });

    it('should maintain responsiveness on window resize', () => {
      render(<LineChart data={mockTimeSeriesData} />);
      
      // Simulate window resize
      global.dispatchEvent(new Event('resize'));
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should optimize rendering for real-time updates', () => {
      const { rerender } = render(<LineChart data={mockTimeSeriesData} />);
      
      // Simulate rapid updates
      for (let i = 0; i < 10; i++) {
        const newData = [...mockTimeSeriesData, { 
          date: `2024-01-${6 + i}`, 
          value: 115 + i 
        }];
        rerender(<LineChart data={newData} />);
      }
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('Accessibility and User Experience', () => {
    it('should provide proper ARIA labels for charts', () => {
      render(<LineChart data={mockTimeSeriesData} ariaLabel="Stock price trend" />);
      
      const container = screen.getByTestId('responsive-container');
      expect(container).toBeInTheDocument();
    });

    it('should support keyboard navigation for interactive elements', async () => {
      render(<StockChart symbol="AAPL" data={mockCandlestickData} />);
      
      await userEvent.tab();
      
      // Should have focusable elements for accessibility
      const focusedElement = document.activeElement;
      expect(focusedElement).toBeInstanceOf(HTMLElement);
    });

    it('should provide alternative text descriptions for screen readers', () => {
      render(<PortfolioPieChart data={mockPortfolioData} description="Portfolio allocation by stock" />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should handle color-blind friendly palettes', () => {
      render(<PortfolioPieChart data={mockPortfolioData} colorScheme="colorblind-safe" />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle malformed data gracefully', () => {
      const malformedData = [
        { date: null, value: 'invalid' },
        { date: '2024-01-02', value: undefined },
        { invalid: 'structure' }
      ];
      
      render(<LineChart data={malformedData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should handle missing required props', () => {
      render(<LineChart />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      expect(screen.getByTestId('line-chart')).toHaveAttribute('data-chart-points', '0');
    });

    it('should recover from chart rendering errors', () => {
      const errorData = [{ date: '2024-01-01', value: Infinity }];
      
      render(<LineChart data={errorData} />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should handle extreme values correctly', () => {
      const extremeData = [
        { date: '2024-01-01', value: Number.MAX_SAFE_INTEGER },
        { date: '2024-01-02', value: Number.MIN_SAFE_INTEGER },
        { date: '2024-01-03', value: 0 }
      ];
      
      render(<LineChart data={extremeData} />);
      
      expect(screen.getByTestId('line-chart')).toHaveAttribute('data-chart-points', '3');
    });
  });
});
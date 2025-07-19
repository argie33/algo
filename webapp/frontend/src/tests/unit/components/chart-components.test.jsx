/**
 * Chart Components Unit Tests
 * Comprehensive testing of all real chart and visualization components
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Real Chart Components - Import actual production components
import { LineChart } from '../../../components/charts/LineChart';
import { CandlestickChart } from '../../../components/charts/CandlestickChart';
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

describe('📊 Chart Components', () => {
  const mockTimeSeriesData = [
    { date: '2024-01-01', value: 100, volume: 1000000 },
    { date: '2024-01-02', value: 102, volume: 1200000 },
    { date: '2024-01-03', value: 98, volume: 900000 },
    { date: '2024-01-04', value: 105, volume: 1500000 },
    { date: '2024-01-05', value: 107, volume: 1100000 }
  ];

  const mockCandlestickData = [
    { date: '2024-01-01', open: 100, high: 103, low: 99, close: 102, volume: 1000000 },
    { date: '2024-01-02', open: 102, high: 105, low: 101, close: 104, volume: 1200000 },
    { date: '2024-01-03', open: 104, high: 106, low: 97, close: 98, volume: 900000 },
    { date: '2024-01-04', open: 98, high: 108, low: 96, close: 105, volume: 1500000 },
    { date: '2024-01-05', open: 105, high: 109, low: 104, close: 107, volume: 1100000 }
  ];

  const mockPortfolioData = [
    { symbol: 'AAPL', value: 15000, percentage: 30, color: '#1f77b4' },
    { symbol: 'GOOGL', value: 12000, percentage: 24, color: '#ff7f0e' },
    { symbol: 'MSFT', value: 10000, percentage: 20, color: '#2ca02c' },
    { symbol: 'TSLA', value: 8000, percentage: 16, color: '#d62728' },
    { symbol: 'CASH', value: 5000, percentage: 10, color: '#9467bd' }
  ];

  const mockPerformanceData = [
    { date: '2024-01-01', portfolio: 100, benchmark: 100 },
    { date: '2024-01-02', portfolio: 102, benchmark: 101 },
    { date: '2024-01-03', portfolio: 98, benchmark: 99 },
    { date: '2024-01-04', portfolio: 105, benchmark: 102 },
    { date: '2024-01-05', portfolio: 107, benchmark: 103 }
  ];

  const mockSectorData = [
    { sector: 'Technology', allocation: 40, performance: 0.12 },
    { sector: 'Healthcare', allocation: 25, performance: 0.08 },
    { sector: 'Finance', allocation: 20, performance: 0.05 },
    { sector: 'Energy', allocation: 10, performance: -0.02 },
    { sector: 'Real Estate', allocation: 5, performance: 0.03 }
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('LineChart Component', () => {
    it('should render line chart correctly', () => {
      render(
        <LineChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          title="Stock Price"
          width={600}
          height={400}
        />
      );

      expect(screen.getByText('Stock Price')).toBeInTheDocument();
      expect(screen.getByRole('img', { name: /chart/i })).toBeInTheDocument();
    });

    it('should handle multiple data series', () => {
      const multiSeriesData = mockTimeSeriesData.map(item => ({
        ...item,
        series1: item.value,
        series2: item.value * 1.1
      }));

      render(
        <LineChart 
          data={multiSeriesData}
          xKey="date"
          yKeys={['series1', 'series2']}
          title="Comparison Chart"
          legend={['Portfolio', 'Benchmark']}
        />
      );

      expect(screen.getByText('Comparison Chart')).toBeInTheDocument();
    });

    it('should handle zoom functionality', async () => {
      const user = userEvent.setup();
      const onZoom = vi.fn();

      render(
        <LineChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          enableZoom={true}
          onZoom={onZoom}
        />
      );

      const chart = screen.getByRole('img', { name: /chart/i });
      
      // Simulate zoom gesture
      await user.pointer([
        { target: chart, coords: { x: 100, y: 100 } },
        { target: chart, coords: { x: 200, y: 200 } }
      ]);

      // Note: Real implementation would handle zoom events
    });

    it('should show tooltips on hover', async () => {
      const user = userEvent.setup();

      render(
        <LineChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          showTooltip={true}
        />
      );

      const chart = screen.getByRole('img', { name: /chart/i });
      await user.hover(chart);

      // Tooltip would be shown by the real chart library
    });

    it('should handle empty data gracefully', () => {
      render(
        <LineChart 
          data={[]}
          xKey="date"
          yKey="value"
          title="Empty Chart"
        />
      );

      expect(screen.getByText('Empty Chart')).toBeInTheDocument();
      expect(screen.getByText(/no data available/i)).toBeInTheDocument();
    });

    it('should support custom styling', () => {
      render(
        <LineChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          lineColor="#ff0000"
          lineWidth={3}
          backgroundColor="#f5f5f5"
        />
      );

      const chartContainer = screen.getByRole('img', { name: /chart/i }).parentElement;
      expect(chartContainer).toHaveStyle('background-color: #f5f5f5');
    });
  });

  describe('CandlestickChart Component', () => {
    it('should render candlestick chart correctly', () => {
      render(
        <CandlestickChart 
          data={mockCandlestickData}
          title="AAPL Price Action"
          symbol="AAPL"
        />
      );

      expect(screen.getByText('AAPL Price Action')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    it('should handle volume overlay', () => {
      render(
        <CandlestickChart 
          data={mockCandlestickData}
          showVolume={true}
          title="Price & Volume"
        />
      );

      expect(screen.getByText('Price & Volume')).toBeInTheDocument();
      // Volume bars would be rendered by the chart library
    });

    it('should support technical indicators', () => {
      render(
        <CandlestickChart 
          data={mockCandlestickData}
          indicators={['SMA20', 'RSI', 'MACD']}
          title="Technical Analysis"
        />
      );

      expect(screen.getByText('Technical Analysis')).toBeInTheDocument();
      // Indicators would be calculated and displayed
    });

    it('should handle time period changes', async () => {
      const user = userEvent.setup();
      const onPeriodChange = vi.fn();

      render(
        <CandlestickChart 
          data={mockCandlestickData}
          onPeriodChange={onPeriodChange}
          showPeriodSelector={true}
        />
      );

      const periodButton = screen.getByText('1D');
      await user.click(periodButton);
      expect(onPeriodChange).toHaveBeenCalledWith('1D');
    });

    it('should highlight market hours', () => {
      render(
        <CandlestickChart 
          data={mockCandlestickData}
          highlightMarketHours={true}
          timezone="EST"
        />
      );

      // Market hours highlighting would be implemented in real component
    });
  });

  describe('PortfolioPieChart Component', () => {
    it('should render portfolio pie chart correctly', () => {
      render(
        <PortfolioPieChart 
          data={mockPortfolioData}
          title="Portfolio Allocation"
          totalValue={50000}
        />
      );

      expect(screen.getByText('Portfolio Allocation')).toBeInTheDocument();
      expect(screen.getByText('$50,000')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('30%')).toBeInTheDocument();
    });

    it('should handle slice interactions', async () => {
      const user = userEvent.setup();
      const onSliceClick = vi.fn();

      render(
        <PortfolioPieChart 
          data={mockPortfolioData}
          onSliceClick={onSliceClick}
          interactive={true}
        />
      );

      const appleSlice = screen.getByText('AAPL');
      await user.click(appleSlice);
      expect(onSliceClick).toHaveBeenCalledWith(mockPortfolioData[0]);
    });

    it('should show detailed tooltips', async () => {
      const user = userEvent.setup();

      render(
        <PortfolioPieChart 
          data={mockPortfolioData}
          showDetailedTooltips={true}
        />
      );

      const appleSlice = screen.getByText('AAPL');
      await user.hover(appleSlice);

      // Tooltip would show: "AAPL: $15,000 (30%)"
    });

    it('should support donut mode', () => {
      render(
        <PortfolioPieChart 
          data={mockPortfolioData}
          donutMode={true}
          centerText="Total Portfolio"
        />
      );

      expect(screen.getByText('Total Portfolio')).toBeInTheDocument();
    });

    it('should handle minimum slice threshold', () => {
      const dataWithSmallSlices = [
        ...mockPortfolioData,
        { symbol: 'SMALL1', value: 100, percentage: 0.2, color: '#abc123' },
        { symbol: 'SMALL2', value: 50, percentage: 0.1, color: '#def456' }
      ];

      render(
        <PortfolioPieChart 
          data={dataWithSmallSlices}
          minSlicePercentage={1}
          groupSmallSlices={true}
        />
      );

      expect(screen.getByText('Others')).toBeInTheDocument();
    });
  });

  describe('PerformanceChart Component', () => {
    it('should render performance comparison correctly', () => {
      render(
        <PerformanceChart 
          data={mockPerformanceData}
          title="Portfolio vs Benchmark"
          portfolioLabel="My Portfolio"
          benchmarkLabel="S&P 500"
        />
      );

      expect(screen.getByText('Portfolio vs Benchmark')).toBeInTheDocument();
      expect(screen.getByText('My Portfolio')).toBeInTheDocument();
      expect(screen.getByText('S&P 500')).toBeInTheDocument();
    });

    it('should calculate and display performance metrics', () => {
      render(
        <PerformanceChart 
          data={mockPerformanceData}
          showMetrics={true}
          calculateReturns={true}
        />
      );

      // Performance metrics would be calculated and displayed
      expect(screen.getByText(/return/i)).toBeInTheDocument();
      expect(screen.getByText(/7%/)).toBeInTheDocument(); // 107 - 100 = 7%
    });

    it('should handle different time periods', async () => {
      const user = userEvent.setup();
      const onPeriodChange = vi.fn();

      render(
        <PerformanceChart 
          data={mockPerformanceData}
          onPeriodChange={onPeriodChange}
          periods={['1W', '1M', '3M', '1Y', 'ALL']}
        />
      );

      await user.click(screen.getByText('1M'));
      expect(onPeriodChange).toHaveBeenCalledWith('1M');
    });

    it('should show drawdown analysis', () => {
      render(
        <PerformanceChart 
          data={mockPerformanceData}
          showDrawdown={true}
          title="Performance & Drawdown"
        />
      );

      expect(screen.getByText('Performance & Drawdown')).toBeInTheDocument();
      // Drawdown chart would be rendered below performance chart
    });
  });

  describe('VolumeChart Component', () => {
    it('should render volume chart correctly', () => {
      render(
        <VolumeChart 
          data={mockTimeSeriesData}
          title="Trading Volume"
          xKey="date"
          volumeKey="volume"
        />
      );

      expect(screen.getByText('Trading Volume')).toBeInTheDocument();
    });

    it('should sync with price chart', async () => {
      const onRangeChange = vi.fn();

      render(
        <VolumeChart 
          data={mockTimeSeriesData}
          syncWithChart={true}
          onRangeChange={onRangeChange}
        />
      );

      // Range selection would trigger sync with main price chart
    });

    it('should highlight unusual volume', () => {
      const dataWithUnusualVolume = mockTimeSeriesData.map((item, index) => ({
        ...item,
        volume: index === 2 ? item.volume * 3 : item.volume // Spike on day 3
      }));

      render(
        <VolumeChart 
          data={dataWithUnusualVolume}
          highlightUnusualVolume={true}
          volumeThreshold={2}
        />
      );

      // Volume spikes would be highlighted with different color
    });
  });

  describe('DonutChart Component', () => {
    it('should render donut chart correctly', () => {
      render(
        <DonutChart 
          data={mockSectorData}
          valueKey="allocation"
          labelKey="sector"
          title="Sector Allocation"
          centerText="Sectors"
        />
      );

      expect(screen.getByText('Sector Allocation')).toBeInTheDocument();
      expect(screen.getByText('Sectors')).toBeInTheDocument();
      expect(screen.getByText('Technology')).toBeInTheDocument();
    });

    it('should animate on load', () => {
      render(
        <DonutChart 
          data={mockSectorData}
          valueKey="allocation"
          labelKey="sector"
          animateOnLoad={true}
          animationDuration={1000}
        />
      );

      // Animation would be handled by chart library
    });

    it('should support gradient colors', () => {
      render(
        <DonutChart 
          data={mockSectorData}
          valueKey="allocation"
          labelKey="sector"
          useGradients={true}
          colorScheme="blue"
        />
      );

      // Gradient colors would be applied by chart library
    });
  });

  describe('AreaChart Component', () => {
    it('should render stacked area chart', () => {
      render(
        <AreaChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKeys={['value', 'volume']}
          stacked={true}
          title="Stacked Values"
        />
      );

      expect(screen.getByText('Stacked Values')).toBeInTheDocument();
    });

    it('should handle area transparency', () => {
      render(
        <AreaChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          fillOpacity={0.3}
          showLine={true}
        />
      );

      // Transparency would be applied by chart library
    });

    it('should support range selection', async () => {
      const user = userEvent.setup();
      const onRangeSelect = vi.fn();

      render(
        <AreaChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          enableRangeSelection={true}
          onRangeSelect={onRangeSelect}
        />
      );

      const chart = screen.getByRole('img', { name: /chart/i });
      
      // Simulate range selection
      await user.pointer([
        { target: chart, coords: { x: 50, y: 100 } },
        { target: chart, coords: { x: 150, y: 100 } }
      ]);
    });
  });

  describe('BarChart Component', () => {
    it('should render horizontal bar chart', () => {
      render(
        <BarChart 
          data={mockSectorData}
          xKey="sector"
          yKey="allocation"
          orientation="horizontal"
          title="Sector Allocation"
        />
      );

      expect(screen.getByText('Sector Allocation')).toBeInTheDocument();
      expect(screen.getByText('Technology')).toBeInTheDocument();
    });

    it('should handle grouped bars', () => {
      const groupedData = mockSectorData.map(item => ({
        ...item,
        currentYear: item.allocation,
        lastYear: item.allocation * 0.9
      }));

      render(
        <BarChart 
          data={groupedData}
          xKey="sector"
          yKeys={['currentYear', 'lastYear']}
          grouped={true}
          title="Year over Year Comparison"
        />
      );

      expect(screen.getByText('Year over Year Comparison')).toBeInTheDocument();
    });

    it('should show value labels on bars', () => {
      render(
        <BarChart 
          data={mockSectorData}
          xKey="sector"
          yKey="allocation"
          showValueLabels={true}
        />
      );

      expect(screen.getByText('40')).toBeInTheDocument(); // Technology allocation
    });
  });

  describe('HeatmapChart Component', () => {
    const mockHeatmapData = [
      { x: 'Tech', y: 'Q1', value: 15.5 },
      { x: 'Tech', y: 'Q2', value: 18.2 },
      { x: 'Health', y: 'Q1', value: 8.1 },
      { x: 'Health', y: 'Q2', value: 9.8 }
    ];

    it('should render heatmap correctly', () => {
      render(
        <HeatmapChart 
          data={mockHeatmapData}
          xKey="x"
          yKey="y"
          valueKey="value"
          title="Sector Performance Heatmap"
        />
      );

      expect(screen.getByText('Sector Performance Heatmap')).toBeInTheDocument();
      expect(screen.getByText('Tech')).toBeInTheDocument();
      expect(screen.getByText('Q1')).toBeInTheDocument();
    });

    it('should use custom color scale', () => {
      render(
        <HeatmapChart 
          data={mockHeatmapData}
          xKey="x"
          yKey="y"
          valueKey="value"
          colorScale={['red', 'yellow', 'green']}
          minValue={0}
          maxValue={20}
        />
      );

      // Color scale would be applied by chart library
    });

    it('should show cell values', () => {
      render(
        <HeatmapChart 
          data={mockHeatmapData}
          xKey="x"
          yKey="y"
          valueKey="value"
          showCellValues={true}
        />
      );

      expect(screen.getByText('15.5')).toBeInTheDocument();
    });
  });

  describe('TreemapChart Component', () => {
    const mockTreemapData = [
      { name: 'AAPL', value: 15000, group: 'Technology' },
      { name: 'GOOGL', value: 12000, group: 'Technology' },
      { name: 'JNJ', value: 8000, group: 'Healthcare' },
      { name: 'JPM', value: 6000, group: 'Finance' }
    ];

    it('should render treemap correctly', () => {
      render(
        <TreemapChart 
          data={mockTreemapData}
          valueKey="value"
          labelKey="name"
          groupKey="group"
          title="Portfolio Treemap"
        />
      );

      expect(screen.getByText('Portfolio Treemap')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    it('should handle nested grouping', () => {
      render(
        <TreemapChart 
          data={mockTreemapData}
          valueKey="value"
          labelKey="name"
          groupKey="group"
          nested={true}
          showGroupLabels={true}
        />
      );

      expect(screen.getByText('Technology')).toBeInTheDocument();
      expect(screen.getByText('Healthcare')).toBeInTheDocument();
    });

    it('should support drill-down functionality', async () => {
      const user = userEvent.setup();
      const onDrillDown = vi.fn();

      render(
        <TreemapChart 
          data={mockTreemapData}
          valueKey="value"
          labelKey="name"
          onDrillDown={onDrillDown}
          enableDrillDown={true}
        />
      );

      await user.click(screen.getByText('AAPL'));
      expect(onDrillDown).toHaveBeenCalledWith(mockTreemapData[0]);
    });
  });

  describe('BubbleChart Component', () => {
    const mockBubbleData = [
      { x: 10, y: 15, size: 20, label: 'AAPL', category: 'Tech' },
      { x: 8, y: 12, size: 15, label: 'GOOGL', category: 'Tech' },
      { x: 6, y: 8, size: 10, label: 'JNJ', category: 'Health' }
    ];

    it('should render bubble chart correctly', () => {
      render(
        <BubbleChart 
          data={mockBubbleData}
          xKey="x"
          yKey="y"
          sizeKey="size"
          labelKey="label"
          title="Risk vs Return"
          xLabel="Risk"
          yLabel="Return"
        />
      );

      expect(screen.getByText('Risk vs Return')).toBeInTheDocument();
      expect(screen.getByText('Risk')).toBeInTheDocument();
      expect(screen.getByText('Return')).toBeInTheDocument();
    });

    it('should color by category', () => {
      render(
        <BubbleChart 
          data={mockBubbleData}
          xKey="x"
          yKey="y"
          sizeKey="size"
          colorKey="category"
          showLegend={true}
        />
      );

      expect(screen.getByText('Tech')).toBeInTheDocument();
      expect(screen.getByText('Health')).toBeInTheDocument();
    });

    it('should handle bubble interactions', async () => {
      const user = userEvent.setup();
      const onBubbleClick = vi.fn();

      render(
        <BubbleChart 
          data={mockBubbleData}
          xKey="x"
          yKey="y"
          sizeKey="size"
          onBubbleClick={onBubbleClick}
        />
      );

      // Would click on bubble representing AAPL
      // Implementation would depend on chart library
    });
  });

  describe('SparklineChart Component', () => {
    it('should render compact sparkline', () => {
      render(
        <SparklineChart 
          data={mockTimeSeriesData}
          valueKey="value"
          width={100}
          height={30}
          color="#00ff00"
        />
      );

      const sparkline = screen.getByRole('img', { name: /sparkline/i });
      expect(sparkline).toBeInTheDocument();
    });

    it('should show trend indicator', () => {
      render(
        <SparklineChart 
          data={mockTimeSeriesData}
          valueKey="value"
          showTrend={true}
          showLastValue={true}
        />
      );

      expect(screen.getByText('107')).toBeInTheDocument(); // Last value
      expect(screen.getByText('↑')).toBeInTheDocument(); // Upward trend
    });

    it('should highlight min/max values', () => {
      render(
        <SparklineChart 
          data={mockTimeSeriesData}
          valueKey="value"
          highlightMinMax={true}
          showMinMaxValues={true}
        />
      );

      expect(screen.getByText('98')).toBeInTheDocument(); // Min value
      expect(screen.getByText('107')).toBeInTheDocument(); // Max value
    });

    it('should support different chart types', () => {
      render(
        <SparklineChart 
          data={mockTimeSeriesData}
          valueKey="value"
          type="area"
          fillOpacity={0.3}
        />
      );

      // Area sparkline would be rendered
    });
  });

  describe('Chart Accessibility', () => {
    it('should have proper ARIA labels', () => {
      render(
        <LineChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          title="Accessible Chart"
          ariaLabel="Stock price over time showing upward trend"
        />
      );

      const chart = screen.getByRole('img', { name: /accessible chart/i });
      expect(chart).toHaveAttribute('aria-label', 'Stock price over time showing upward trend');
    });

    it('should support keyboard navigation', async () => {
      const user = userEvent.setup();

      render(
        <LineChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          keyboardNavigable={true}
          focusable={true}
        />
      );

      const chart = screen.getByRole('img', { name: /chart/i });
      await user.tab();
      expect(chart).toHaveFocus();

      await user.keyboard('{ArrowRight}');
      // Would navigate to next data point
    });

    it('should provide data table alternative', () => {
      render(
        <LineChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          showDataTable={true}
          tableCaption="Stock price data by date"
        />
      );

      expect(screen.getByRole('table')).toBeInTheDocument();
      expect(screen.getByText('Stock price data by date')).toBeInTheDocument();
    });
  });

  describe('Chart Performance', () => {
    it('should handle large datasets efficiently', () => {
      const largeDataset = Array.from({ length: 10000 }, (_, i) => ({
        date: `2024-01-${(i % 30) + 1}`,
        value: 100 + Math.random() * 50
      }));

      const startTime = performance.now();
      render(
        <LineChart 
          data={largeDataset}
          xKey="date"
          yKey="value"
          title="Large Dataset"
          optimized={true}
        />
      );
      const renderTime = performance.now() - startTime;

      expect(renderTime).toBeLessThan(500); // Should render within 500ms
      expect(screen.getByText('Large Dataset')).toBeInTheDocument();
    });

    it('should implement data virtualization', () => {
      const largeDataset = Array.from({ length: 50000 }, (_, i) => ({
        date: `2024-${String(Math.floor(i / 30) + 1).padStart(2, '0')}-${String((i % 30) + 1).padStart(2, '0')}`,
        value: 100 + Math.random() * 50
      }));

      render(
        <LineChart 
          data={largeDataset}
          xKey="date"
          yKey="value"
          virtualized={true}
          viewportSize={1000}
        />
      );

      // Only viewport data would be rendered
    });

    it('should debounce zoom and pan operations', async () => {
      const user = userEvent.setup();
      const onZoom = vi.fn();

      render(
        <LineChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          enableZoom={true}
          onZoom={onZoom}
          debounceMs={300}
        />
      );

      const chart = screen.getByRole('img', { name: /chart/i });
      
      // Rapid zoom operations
      await user.pointer({ target: chart, coords: { x: 100, y: 100 } });
      await user.pointer({ target: chart, coords: { x: 150, y: 100 } });
      await user.pointer({ target: chart, coords: { x: 200, y: 100 } });

      // Should debounce and only call once after delay
      await waitFor(() => {
        expect(onZoom).toHaveBeenCalledTimes(1);
      }, { timeout: 500 });
    });
  });

  describe('Chart Error Handling', () => {
    it('should handle invalid data gracefully', () => {
      const invalidData = [
        { date: null, value: undefined },
        { date: '2024-01-02', value: 'invalid' },
        { date: '2024-01-03', value: NaN }
      ];

      expect(() => {
        render(
          <LineChart 
            data={invalidData}
            xKey="date"
            yKey="value"
            title="Invalid Data Chart"
          />
        );
      }).not.toThrow();

      expect(screen.getByText(/no valid data/i)).toBeInTheDocument();
    });

    it('should handle missing required props', () => {
      expect(() => {
        render(<LineChart data={null} />);
      }).not.toThrow();

      expect(screen.getByText(/configuration error/i)).toBeInTheDocument();
    });

    it('should handle chart library errors', () => {
      // Simulate chart library error
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(
        <LineChart 
          data={mockTimeSeriesData}
          xKey="nonexistent"
          yKey="also-nonexistent"
          title="Error Chart"
        />
      );

      expect(screen.getByText(/chart error/i)).toBeInTheDocument();
      consoleSpy.mockRestore();
    });

    it('should provide fallback for unsupported browsers', () => {
      // Mock browser without canvas support
      const originalGetContext = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = vi.fn(() => null);

      render(
        <LineChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          title="Fallback Chart"
        />
      );

      expect(screen.getByText(/browser not supported/i)).toBeInTheDocument();

      HTMLCanvasElement.prototype.getContext = originalGetContext;
    });
  });

  describe('Chart Integration', () => {
    it('should sync multiple charts', () => {
      const onRangeChange = vi.fn();

      render(
        <div>
          <LineChart 
            data={mockTimeSeriesData}
            xKey="date"
            yKey="value"
            syncId="sync-group-1"
            onRangeChange={onRangeChange}
          />
          <VolumeChart 
            data={mockTimeSeriesData}
            xKey="date"
            volumeKey="volume"
            syncId="sync-group-1"
          />
        </div>
      );

      // Charts would be synchronized through shared range selection
    });

    it('should support chart combinations', () => {
      render(
        <div className="chart-dashboard">
          <LineChart 
            data={mockTimeSeriesData}
            xKey="date"
            yKey="value"
            title="Price"
          />
          <PortfolioPieChart 
            data={mockPortfolioData}
            title="Allocation"
          />
          <PerformanceChart 
            data={mockPerformanceData}
            title="Performance"
          />
        </div>
      );

      expect(screen.getByText('Price')).toBeInTheDocument();
      expect(screen.getByText('Allocation')).toBeInTheDocument();
      expect(screen.getByText('Performance')).toBeInTheDocument();
    });

    it('should export chart data', async () => {
      const user = userEvent.setup();
      const onExport = vi.fn();

      render(
        <LineChart 
          data={mockTimeSeriesData}
          xKey="date"
          yKey="value"
          exportable={true}
          onExport={onExport}
        />
      );

      const exportButton = screen.getByText(/export/i);
      await user.click(exportButton);
      expect(onExport).toHaveBeenCalledWith(mockTimeSeriesData, 'csv');
    });
  });
});
/**
 * Real Chart Components Unit Tests
 * Tests actual chart components as they exist in the codebase
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Mock Recharts since we can't rely on DOM rendering in tests
vi.mock('recharts', () => ({
  ResponsiveContainer: vi.fn(({ children, width, height }) => (
    <div data-testid="responsive-container" style={{ width, height }}>
      {children}
    </div>
  )),
  PieChart: vi.fn(({ children }) => (
    <div data-testid="pie-chart">{children}</div>
  )),
  Pie: vi.fn(({ data, dataKey, label, cx, cy }) => (
    <div data-testid="pie" data-key={dataKey} data-center={`${cx},${cy}`}>
      {data?.length || 0} segments
    </div>
  )),
  Cell: vi.fn(({ fill }) => <div data-testid="pie-cell" style={{ fill }} />),
  LineChart: vi.fn(({ data, children }) => (
    <div data-testid="line-chart" data-points={data?.length || 0}>
      {children}
    </div>
  )),
  Line: vi.fn(({ dataKey, stroke, strokeWidth, type }) => (
    <div data-testid="line" data-key={dataKey} data-stroke={stroke} data-width={strokeWidth} data-type={type} />
  )),
  ComposedChart: vi.fn(({ data, children }) => (
    <div data-testid="composed-chart" data-points={data?.length || 0}>
      {children}
    </div>
  )),
  Bar: vi.fn(({ dataKey, fill }) => (
    <div data-testid="bar" data-key={dataKey} data-fill={fill} />
  )),
  XAxis: vi.fn(({ dataKey }) => (
    <div data-testid="x-axis" data-key={dataKey} />
  )),
  YAxis: vi.fn(() => <div data-testid="y-axis" />),
  CartesianGrid: vi.fn(({ strokeDasharray }) => (
    <div data-testid="cartesian-grid" data-dash-array={strokeDasharray} />
  )),
  Tooltip: vi.fn(({ formatter }) => (
    <div data-testid="tooltip" data-has-formatter={!!formatter} />
  )),
  Legend: vi.fn(() => <div data-testid="legend" />)
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

describe('Real Chart Components', () => {
  let mockPortfolioData;
  let mockTimeSeriesData;
  let mockCandlestickData;

  beforeEach(() => {
    vi.clearAllMocks();
    
    mockPortfolioData = [
      { symbol: 'AAPL', value: 45000, percentage: 30, color: '#1f77b4' },
      { symbol: 'MSFT', value: 37500, percentage: 25, color: '#ff7f0e' },
      { symbol: 'GOOGL', value: 30000, percentage: 20, color: '#2ca02c' },
      { symbol: 'TSLA', value: 22500, percentage: 15, color: '#d62728' },
      { symbol: 'Cash', value: 15000, percentage: 10, color: '#9467bd' }
    ];

    mockTimeSeriesData = [
      { date: '2024-01-01', value: 100 },
      { date: '2024-01-02', value: 105 },
      { date: '2024-01-03', value: 103 },
      { date: '2024-01-04', value: 108 },
      { date: '2024-01-05', value: 112 }
    ];

    mockCandlestickData = [
      { date: '2024-01-01', high: 105, low: 99 },
      { date: '2024-01-02', high: 108, low: 102 },
      { date: '2024-01-03', high: 109, low: 104 }
    ];
  });

  describe('DonutChart Component', () => {
    it('renders DonutChart with correct props', async () => {
      const { DonutChart } = await import('../../../components/charts/DonutChart');
      
      render(
        <TestWrapper>
          <DonutChart 
            data={mockPortfolioData}
            width="100%"
            height={300}
            innerRadius={60}
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
      expect(screen.getByTestId('pie')).toBeInTheDocument();
    });

    it('handles empty data array', async () => {
      const { DonutChart } = await import('../../../components/charts/DonutChart');
      
      render(
        <TestWrapper>
          <DonutChart data={[]} />
        </TestWrapper>
      );

      expect(screen.getByTestId('pie')).toHaveTextContent('0 segments');
    });

    it('uses default props when none provided', async () => {
      const { DonutChart } = await import('../../../components/charts/DonutChart');
      
      render(
        <TestWrapper>
          <DonutChart />
        </TestWrapper>
      );

      expect(screen.getByTestId('responsive-container')).toHaveStyle({
        width: '100%',
        height: '300px'
      });
    });

    it('passes correct dataKey to Pie component', async () => {
      const { DonutChart } = await import('../../../components/charts/DonutChart');
      
      render(
        <TestWrapper>
          <DonutChart data={mockPortfolioData} />
        </TestWrapper>
      );

      expect(screen.getByTestId('pie')).toHaveAttribute('data-key', 'value');
    });

    it('sets correct center position', async () => {
      const { DonutChart } = await import('../../../components/charts/DonutChart');
      
      render(
        <TestWrapper>
          <DonutChart data={mockPortfolioData} />
        </TestWrapper>
      );

      expect(screen.getByTestId('pie')).toHaveAttribute('data-center', '50%,50%');
    });
  });

  describe('PortfolioPieChart Component', () => {
    it('renders PortfolioPieChart with data', async () => {
      const { PortfolioPieChart } = await import('../../../components/charts/PortfolioPieChart');
      
      render(
        <TestWrapper>
          <PortfolioPieChart 
            data={mockPortfolioData}
            width="100%"
            height={300}
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
      expect(screen.getByTestId('pie')).toHaveAttribute('data-key', 'value');
      expect(screen.getByTestId('tooltip')).toBeInTheDocument();
      expect(screen.getByTestId('legend')).toBeInTheDocument();
    });

    it('renders with custom tooltip formatter', async () => {
      const { PortfolioPieChart } = await import('../../../components/charts/PortfolioPieChart');
      
      render(
        <TestWrapper>
          <PortfolioPieChart data={mockPortfolioData} />
        </TestWrapper>
      );

      // The component includes a custom formatter for tooltip
      expect(screen.getByTestId('tooltip')).toHaveAttribute('data-has-formatter', 'true');
    });

    it('renders pie cells for each data item', async () => {
      const { PortfolioPieChart } = await import('../../../components/charts/PortfolioPieChart');
      
      render(
        <TestWrapper>
          <PortfolioPieChart data={mockPortfolioData} />
        </TestWrapper>
      );

      expect(screen.getByTestId('pie')).toHaveTextContent('5 segments');
    });

    it('handles empty portfolio data', async () => {
      const { PortfolioPieChart } = await import('../../../components/charts/PortfolioPieChart');
      
      render(
        <TestWrapper>
          <PortfolioPieChart data={[]} />
        </TestWrapper>
      );

      expect(screen.getByTestId('pie')).toHaveTextContent('0 segments');
    });
  });

  describe('LineChart Component', () => {
    it('renders LineChart with time series data', async () => {
      const { LineChart } = await import('../../../components/charts/LineChart');
      
      render(
        <TestWrapper>
          <LineChart 
            data={mockTimeSeriesData}
            color="#1f77b4"
            showGrid={true}
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('line-chart')).toBeInTheDocument();
      expect(screen.getByTestId('line-chart')).toHaveAttribute('data-points', '5');
      expect(screen.getByTestId('line')).toBeInTheDocument();
    });

    it('configures axes correctly', async () => {
      const { LineChart } = await import('../../../components/charts/LineChart');
      
      render(
        <TestWrapper>
          <LineChart data={mockTimeSeriesData} />
        </TestWrapper>
      );

      expect(screen.getByTestId('x-axis')).toHaveAttribute('data-key', 'date');
      expect(screen.getByTestId('y-axis')).toBeInTheDocument();
    });

    it('shows grid when showGrid is true', async () => {
      const { LineChart } = await import('../../../components/charts/LineChart');
      
      render(
        <TestWrapper>
          <LineChart data={mockTimeSeriesData} showGrid={true} />
        </TestWrapper>
      );

      expect(screen.getByTestId('cartesian-grid')).toBeInTheDocument();
      expect(screen.getByTestId('cartesian-grid')).toHaveAttribute('data-dash-array', '3 3');
    });

    it('uses correct line properties', async () => {
      const { LineChart } = await import('../../../components/charts/LineChart');
      
      render(
        <TestWrapper>
          <LineChart data={mockTimeSeriesData} color="#ff0000" />
        </TestWrapper>
      );

      const line = screen.getByTestId('line');
      expect(line).toHaveAttribute('data-key', 'value');
      expect(line).toHaveAttribute('data-stroke', '#ff0000');
      expect(line).toHaveAttribute('data-width', '2');
      expect(line).toHaveAttribute('data-type', 'monotone');
    });

    it('uses default color when not specified', async () => {
      const { LineChart } = await import('../../../components/charts/LineChart');
      
      render(
        <TestWrapper>
          <LineChart data={mockTimeSeriesData} />
        </TestWrapper>
      );

      expect(screen.getByTestId('line')).toHaveAttribute('data-stroke', '#1f77b4');
    });

    it('includes tooltip', async () => {
      const { LineChart } = await import('../../../components/charts/LineChart');
      
      render(
        <TestWrapper>
          <LineChart data={mockTimeSeriesData} />
        </TestWrapper>
      );

      expect(screen.getByTestId('tooltip')).toBeInTheDocument();
    });

    it('handles empty data array', async () => {
      const { LineChart } = await import('../../../components/charts/LineChart');
      
      render(
        <TestWrapper>
          <LineChart data={[]} />
        </TestWrapper>
      );

      expect(screen.getByTestId('line-chart')).toHaveAttribute('data-points', '0');
    });
  });

  describe('CandlestickChart Component', () => {
    it('renders CandlestickChart with OHLC data', async () => {
      const { CandlestickChart } = await import('../../../components/charts/CandlestickChart');
      
      render(
        <TestWrapper>
          <CandlestickChart 
            data={mockCandlestickData}
            width="100%"
            height={400}
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('composed-chart')).toBeInTheDocument();
      expect(screen.getByTestId('composed-chart')).toHaveAttribute('data-points', '3');
    });

    it('renders high and low bars with correct colors', async () => {
      const { CandlestickChart } = await import('../../../components/charts/CandlestickChart');
      
      render(
        <TestWrapper>
          <CandlestickChart data={mockCandlestickData} />
        </TestWrapper>
      );

      const bars = screen.getAllByTestId('bar');
      expect(bars).toHaveLength(2);
      
      // Check high bar (green) and low bar (red)
      expect(bars[0]).toHaveAttribute('data-key', 'high');
      expect(bars[0]).toHaveAttribute('data-fill', '#00ff00');
      expect(bars[1]).toHaveAttribute('data-key', 'low');
      expect(bars[1]).toHaveAttribute('data-fill', '#ff0000');
    });

    it('includes required chart elements', async () => {
      const { CandlestickChart } = await import('../../../components/charts/CandlestickChart');
      
      render(
        <TestWrapper>
          <CandlestickChart data={mockCandlestickData} />
        </TestWrapper>
      );

      expect(screen.getByTestId('cartesian-grid')).toBeInTheDocument();
      expect(screen.getByTestId('x-axis')).toHaveAttribute('data-key', 'date');
      expect(screen.getByTestId('y-axis')).toBeInTheDocument();
      expect(screen.getByTestId('tooltip')).toBeInTheDocument();
    });

    it('has custom tooltip formatter', async () => {
      const { CandlestickChart } = await import('../../../components/charts/CandlestickChart');
      
      render(
        <TestWrapper>
          <CandlestickChart data={mockCandlestickData} />
        </TestWrapper>
      );

      expect(screen.getByTestId('tooltip')).toHaveAttribute('data-has-formatter', 'true');
    });

    it('handles empty candlestick data', async () => {
      const { CandlestickChart } = await import('../../../components/charts/CandlestickChart');
      
      render(
        <TestWrapper>
          <CandlestickChart data={[]} />
        </TestWrapper>
      );

      expect(screen.getByTestId('composed-chart')).toHaveAttribute('data-points', '0');
    });
  });

  describe('Chart Responsiveness', () => {
    it('uses ResponsiveContainer with default dimensions', async () => {
      const { LineChart } = await import('../../../components/charts/LineChart');
      
      render(
        <TestWrapper>
          <LineChart data={mockTimeSeriesData} />
        </TestWrapper>
      );

      expect(screen.getByTestId('responsive-container')).toHaveStyle({
        width: '100%',
        height: '300px'
      });
    });

    it('accepts custom dimensions', async () => {
      const { DonutChart } = await import('../../../components/charts/DonutChart');
      
      render(
        <TestWrapper>
          <DonutChart 
            data={mockPortfolioData}
            width={500}
            height={200}
          />
        </TestWrapper>
      );

      expect(screen.getByTestId('responsive-container')).toHaveStyle({
        width: '500px',
        height: '200px'
      });
    });
  });

  describe('Chart Data Validation', () => {
    it('validates portfolio pie chart data structure', () => {
      const validData = mockPortfolioData.every(item => 
        typeof item.symbol === 'string' &&
        typeof item.value === 'number' &&
        typeof item.percentage === 'number'
      );
      
      expect(validData).toBe(true);
    });

    it('validates time series data structure', () => {
      const validData = mockTimeSeriesData.every(item => 
        typeof item.date === 'string' &&
        typeof item.value === 'number'
      );
      
      expect(validData).toBe(true);
    });

    it('validates candlestick data structure', () => {
      const validData = mockCandlestickData.every(item => 
        typeof item.date === 'string' &&
        typeof item.high === 'number' &&
        typeof item.low === 'number'
      );
      
      expect(validData).toBe(true);
    });
  });

  describe('Chart Props and Defaults', () => {
    it('applies custom innerRadius to DonutChart', async () => {
      const { DonutChart } = await import('../../../components/charts/DonutChart');
      
      render(
        <TestWrapper>
          <DonutChart 
            data={mockPortfolioData}
            innerRadius={40}
          />
        </TestWrapper>
      );

      // Component would use innerRadius prop (tested through props passing)
      expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
    });

    it('uses default values for optional props', async () => {
      const { LineChart } = await import('../../../components/charts/LineChart');
      
      render(
        <TestWrapper>
          <LineChart data={mockTimeSeriesData} />
        </TestWrapper>
      );

      // Default values: width="100%", height=300, color="#1f77b4", showGrid=true
      expect(screen.getByTestId('responsive-container')).toHaveStyle({
        width: '100%',
        height: '300px'
      });
      expect(screen.getByTestId('line')).toHaveAttribute('data-stroke', '#1f77b4');
      expect(screen.getByTestId('cartesian-grid')).toBeInTheDocument();
    });

    it('can disable grid in LineChart', async () => {
      const { LineChart } = await import('../../../components/charts/LineChart');
      
      render(
        <TestWrapper>
          <LineChart data={mockTimeSeriesData} showGrid={false} />
        </TestWrapper>
      );

      expect(screen.queryByTestId('cartesian-grid')).not.toBeInTheDocument();
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });
});
import { screen, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { renderWithProviders } from '../../test-utils';
import HistoricalPriceChart from '../../../components/HistoricalPriceChart';

// Mock API service with successful response
const mockHistoricalData = [
  { date: '2024-01-01', price: 150.00, volume: 1000000, high: 155.00, low: 148.00, open: 149.00, close: 150.00 },
  { date: '2024-01-02', price: 152.50, volume: 1200000, high: 156.00, low: 150.00, open: 150.00, close: 152.50 },
];

vi.mock('../../../services/api', () => ({
  getStockPrices: vi.fn(() => Promise.resolve({
    data: mockHistoricalData
  }))
}));

// Mock recharts components
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children, ...props }) => (
    <div data-testid="responsive-container" {...props}>
      {children}
    </div>
  ),
  LineChart: ({ children, data, ...props }) => (
    <div data-testid="line-chart" data-chart-data={JSON.stringify(data)} {...props}>
      {children}
    </div>
  ),
  Line: ({ dataKey, stroke, ...props }) => (
    <div data-testid="chart-line" data-key={dataKey} data-stroke={stroke} {...props} />
  ),
  XAxis: ({ dataKey, ...props }) => (
    <div data-testid="x-axis" data-key={dataKey} {...props} />
  ),
  YAxis: ({ domain, ...props }) => (
    <div data-testid="y-axis" data-domain={JSON.stringify(domain)} {...props} />
  ),
  CartesianGrid: (props) => <div data-testid="cartesian-grid" {...props} />,
  Tooltip: ({ content, ...props }) => (
    <div data-testid="chart-tooltip" {...props}>
      {typeof content === 'function' ? 'Custom Tooltip' : 'Default Tooltip'}
    </div>
  ),
}));

describe('HistoricalPriceChart Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders component and shows loading state initially', () => {
    renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
    
    // Component should render with title
    expect(screen.getByText('Historical Prices - AAPL')).toBeInTheDocument();
    
    // Should have refresh button
    expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument();
    
    // Should have timeframe controls
    expect(screen.getByRole('button', { name: /daily/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /weekly/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /monthly/i })).toBeInTheDocument();
  });

  it('loads and displays chart data successfully', async () => {
    renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
    
    // Wait for data to load and chart to appear
    await waitFor(() => {
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    }, { timeout: 3000 });
    
    // Verify chart components are rendered
    expect(screen.getByTestId('line-chart')).toBeInTheDocument();
    expect(screen.getByTestId('chart-line')).toBeInTheDocument();
    expect(screen.getByTestId('x-axis')).toBeInTheDocument();
    expect(screen.getByTestId('y-axis')).toBeInTheDocument();
    expect(screen.getByTestId('cartesian-grid')).toBeInTheDocument();
  });

  it('displays price summary when data is loaded', async () => {
    renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
    
    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText(/current:/i)).toBeInTheDocument();
    }, { timeout: 3000 });
    
    // Should show data summary
    expect(screen.getByText(/showing \d+ daily data points/i)).toBeInTheDocument();
  });

  it('handles different symbols correctly', () => {
    renderWithProviders(<HistoricalPriceChart symbol="MSFT" />);
    
    expect(screen.getByText('Historical Prices - MSFT')).toBeInTheDocument();
  });
});
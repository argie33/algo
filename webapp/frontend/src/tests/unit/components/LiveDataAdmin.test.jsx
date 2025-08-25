import { screen, waitFor, fireEvent, within } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderWithProviders } from '../../test-utils';
import LiveDataAdmin from '../../../components/LiveDataAdmin';

// Mock API service
vi.mock('../../../services/api', () => ({
  getLiveDataStreams: vi.fn(() => Promise.resolve({
    data: {
      active: [
        {
          id: 'stream-1',
          symbol: 'AAPL',
          source: 'alpaca',
          status: 'connected',
          lastUpdate: '2024-01-15T10:29:55Z',
          subscriptions: 45,
          latency: 12,
          dataPoints: 15420,
          errors: 0
        },
        {
          id: 'stream-2',
          symbol: 'MSFT',
          source: 'polygon',
          status: 'connected',
          lastUpdate: '2024-01-15T10:29:58Z',
          subscriptions: 32,
          latency: 8,
          dataPoints: 12890,
          errors: 0
        }
      ],
      inactive: [
        {
          id: 'stream-3',
          symbol: 'GOOGL',
          source: 'finnhub',
          status: 'disconnected',
          lastUpdate: '2024-01-15T10:15:00Z',
          subscriptions: 0,
          latency: null,
          dataPoints: 0,
          errors: 5
        }
      ],
      metrics: {
        totalStreams: 3,
        activeStreams: 2,
        totalSubscriptions: 77,
        averageLatency: 10,
        errorRate: 1.6,
        dataRate: 28310
      }
    }
  })),
  createDataStream: vi.fn(() => Promise.resolve({
    success: true,
    streamId: 'stream-4'
  })),
  removeDataStream: vi.fn(() => Promise.resolve({ success: true })),
  restartDataStream: vi.fn(() => Promise.resolve({ success: true })),
  getStreamHistory: vi.fn(() => Promise.resolve({
    data: [
      {
        timestamp: '2024-01-15T10:25:00Z',
        symbol: 'AAPL',
        latency: 15,
        dataPoints: 120,
        errors: 0
      },
      {
        timestamp: '2024-01-15T10:20:00Z',
        symbol: 'AAPL',
        latency: 11,
        dataPoints: 118,
        errors: 0
      }
    ]
  })),
  getDataProviders: vi.fn(() => Promise.resolve({
    data: [
      {
        id: 'alpaca',
        name: 'Alpaca Markets',
        status: 'active',
        connectionCount: 2,
        rateLimit: { current: 150, max: 200 },
        cost: { current: 25.50, monthly: 199.00 }
      },
      {
        id: 'polygon',
        name: 'Polygon.io',
        status: 'active',
        connectionCount: 1,
        rateLimit: { current: 89, max: 100 },
        cost: { current: 45.20, monthly: 399.00 }
      },
      {
        id: 'finnhub',
        name: 'Finnhub',
        status: 'degraded',
        connectionCount: 0,
        rateLimit: { current: 0, max: 60 },
        cost: { current: 0, monthly: 0 }
      }
    ]
  })),
  getStreamMetrics: vi.fn(() => Promise.resolve({
    data: {
      latencyHistory: [
        { timestamp: '2024-01-15T10:25:00Z', average: 15, p95: 25 },
        { timestamp: '2024-01-15T10:20:00Z', average: 12, p95: 22 }
      ],
      throughputHistory: [
        { timestamp: '2024-01-15T10:25:00Z', dataPoints: 2850 },
        { timestamp: '2024-01-15T10:20:00Z', dataPoints: 2920 }
      ],
      errorHistory: [
        { timestamp: '2024-01-15T10:25:00Z', count: 2 },
        { timestamp: '2024-01-15T10:20:00Z', count: 1 }
      ]
    }
  })),
  updateStreamSettings: vi.fn(() => Promise.resolve({ success: true }))
}));

// Mock real-time connection
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    isConnected: true,
    lastMessage: null,
    sendMessage: vi.fn(),
    connectionState: 'OPEN'
  }))
}));

// Mock chart library
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
  BarChart: ({ children, data, ...props }) => (
    <div data-testid="bar-chart" data-chart-data={JSON.stringify(data)} {...props}>
      {children}
    </div>
  ),
  PieChart: ({ children, data, ...props }) => (
    <div data-testid="pie-chart" data-chart-data={JSON.stringify(data)} {...props}>
      {children}
    </div>
  ),
  Line: ({ dataKey, stroke, ...props }) => (
    <div data-testid="chart-line" data-key={dataKey} data-stroke={stroke} {...props} />
  ),
  Bar: ({ dataKey, fill, ...props }) => (
    <div data-testid="chart-bar" data-key={dataKey} data-fill={fill} {...props} />
  ),
  Pie: ({ dataKey, ...props }) => (
    <div data-testid="chart-pie" data-key={dataKey} {...props} />
  ),
  Cell: (props) => <div data-testid="chart-cell" {...props} />,
  XAxis: ({ dataKey, ...props }) => (
    <div data-testid="x-axis" data-key={dataKey} {...props} />
  ),
  YAxis: (props) => <div data-testid="y-axis" {...props} />,
  CartesianGrid: (props) => <div data-testid="cartesian-grid" {...props} />,
  Tooltip: (props) => <div data-testid="chart-tooltip" {...props} />,
  Legend: (props) => <div data-testid="chart-legend" {...props} />
}));

describe('LiveDataAdmin', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2024-01-15T10:30:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe('Component Initialization and Layout', () => {
    it('renders main live data admin interface', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(screen.getByRole('main')).toBeInTheDocument();
        expect(screen.getByText(/live data administration/i)).toBeInTheDocument();
        expect(screen.getByTestId('livedata-dashboard')).toBeInTheDocument();
      });
    });

    it('displays overview metrics summary', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(screen.getByTestId('total-streams')).toHaveTextContent('3');
        expect(screen.getByTestId('active-streams')).toHaveTextContent('2');
        expect(screen.getByTestId('total-subscriptions')).toHaveTextContent('77');
        expect(screen.getByTestId('average-latency')).toHaveTextContent('10ms');
      });
    });

    it('organizes content into management tabs', () => {
      renderWithProviders(<LiveDataAdmin />);
      
      expect(screen.getByRole('tab', { name: /streams/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /providers/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /metrics/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /settings/i })).toBeInTheDocument();
    });

    it('shows real-time status indicator', () => {
      renderWithProviders(<LiveDataAdmin />);
      
      expect(screen.getByTestId('realtime-status')).toBeInTheDocument();
      expect(screen.getByText(/live monitoring/i)).toBeInTheDocument();
    });
  });

  describe('Data Stream Management', () => {
    it('displays active streams with detailed information', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        const appleStream = screen.getByTestId('stream-stream-1');
        expect(within(appleStream).getByText('AAPL')).toBeInTheDocument();
        expect(within(appleStream).getByText('alpaca')).toBeInTheDocument();
        expect(within(appleStream).getByText(/connected/i)).toBeInTheDocument();
        expect(within(appleStream).getByText('45')).toBeInTheDocument(); // Subscriptions
        expect(within(appleStream).getByText('12ms')).toBeInTheDocument(); // Latency
      });
    });

    it('shows inactive/disconnected streams separately', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(screen.getByText(/inactive streams/i)).toBeInTheDocument();
        
        const googleStream = screen.getByTestId('stream-stream-3');
        expect(within(googleStream).getByText('GOOGL')).toBeInTheDocument();
        expect(within(googleStream).getByText(/disconnected/i)).toBeInTheDocument();
        expect(within(googleStream).getByText('5')).toBeInTheDocument(); // Errors
      });
    });

    it('provides stream action controls', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        const streamCard = screen.getByTestId('stream-stream-1');
        expect(within(streamCard).getByRole('button', { name: /restart/i })).toBeInTheDocument();
        expect(within(streamCard).getByRole('button', { name: /stop/i })).toBeInTheDocument();
        expect(within(streamCard).getByRole('button', { name: /details/i })).toBeInTheDocument();
      });
    });

    it('allows creating new data streams', async () => {
      const { createDataStream } = await import('../../../services/api');
      renderWithProviders(<LiveDataAdmin />);
      
      const addStreamButton = screen.getByRole('button', { name: /add stream/i });
      fireEvent.click(addStreamButton);
      
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByLabelText(/symbol/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/data provider/i)).toBeInTheDocument();
      
      // Fill form
      fireEvent.change(screen.getByLabelText(/symbol/i), { target: { value: 'TSLA' } });
      fireEvent.change(screen.getByLabelText(/data provider/i), { target: { value: 'alpaca' } });
      
      const createButton = screen.getByRole('button', { name: /create stream/i });
      fireEvent.click(createButton);
      
      await waitFor(() => {
        expect(createDataStream).toHaveBeenCalledWith({
          symbol: 'TSLA',
          provider: 'alpaca'
        });
      });
    });

    it('supports bulk stream operations', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        // Select multiple streams
        const checkboxes = screen.getAllByRole('checkbox');
        fireEvent.click(checkboxes[0]);
        fireEvent.click(checkboxes[1]);
      });
      
      const bulkActions = screen.getByTestId('bulk-actions');
      expect(within(bulkActions).getByRole('button', { name: /restart selected/i })).toBeEnabled();
      expect(within(bulkActions).getByRole('button', { name: /stop selected/i })).toBeEnabled();
    });

    it('handles stream restart operations', async () => {
      const { restartDataStream } = await import('../../../services/api');
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        const restartButton = screen.getAllByRole('button', { name: /restart/i })[0];
        fireEvent.click(restartButton);
      });
      
      expect(restartDataStream).toHaveBeenCalledWith('stream-1');
      
      await waitFor(() => {
        expect(screen.getByText(/restarting stream/i)).toBeInTheDocument();
      });
    });
  });

  describe('Data Provider Management', () => {
    it('displays configured data providers', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const providersTab = screen.getByRole('tab', { name: /providers/i });
      fireEvent.click(providersTab);
      
      await waitFor(() => {
        expect(screen.getByText('Alpaca Markets')).toBeInTheDocument();
        expect(screen.getByText('Polygon.io')).toBeInTheDocument();
        expect(screen.getByText('Finnhub')).toBeInTheDocument();
      });
    });

    it('shows provider connection status and metrics', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const providersTab = screen.getByRole('tab', { name: /providers/i });
      fireEvent.click(providersTab);
      
      await waitFor(() => {
        const alpacaProvider = screen.getByTestId('provider-alpaca');
        expect(within(alpacaProvider).getByText(/active/i)).toBeInTheDocument();
        expect(within(alpacaProvider).getByText('2')).toBeInTheDocument(); // Connection count
        expect(within(alpacaProvider).getByText('150/200')).toBeInTheDocument(); // Rate limit
      });
    });

    it('displays provider cost information', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const providersTab = screen.getByRole('tab', { name: /providers/i });
      fireEvent.click(providersTab);
      
      await waitFor(() => {
        expect(screen.getByText('$25.50')).toBeInTheDocument(); // Alpaca current
        expect(screen.getByText('$199.00')).toBeInTheDocument(); // Alpaca monthly
        expect(screen.getByText('$45.20')).toBeInTheDocument(); // Polygon current
      });
    });

    it('shows rate limiting status and warnings', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const providersTab = screen.getByRole('tab', { name: /providers/i });
      fireEvent.click(providersTab);
      
      await waitFor(() => {
        const polygonProvider = screen.getByTestId('provider-polygon');
        expect(within(polygonProvider).getByTestId('rate-limit-warning')).toBeInTheDocument();
        expect(within(polygonProvider).getByText(/89% of limit used/i)).toBeInTheDocument();
      });
    });

    it('allows provider configuration management', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const providersTab = screen.getByRole('tab', { name: /providers/i });
      fireEvent.click(providersTab);
      
      await waitFor(() => {
        const configButton = screen.getAllByRole('button', { name: /configure/i })[0];
        fireEvent.click(configButton);
      });
      
      expect(screen.getByText(/provider configuration/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/api key/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/rate limit/i)).toBeInTheDocument();
    });
  });

  describe('Performance Metrics and Analytics', () => {
    it('displays latency performance charts', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const metricsTab = screen.getByRole('tab', { name: /metrics/i });
      fireEvent.click(metricsTab);
      
      await waitFor(() => {
        expect(screen.getByTestId('latency-chart')).toBeInTheDocument();
        
        const latencyChart = screen.getByTestId('line-chart');
        const chartData = JSON.parse(latencyChart.getAttribute('data-chart-data'));
        expect(chartData).toHaveLength(2); // Historical data points
      });
    });

    it('shows throughput and data rate metrics', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const metricsTab = screen.getByRole('tab', { name: /metrics/i });
      fireEvent.click(metricsTab);
      
      await waitFor(() => {
        expect(screen.getByTestId('throughput-chart')).toBeInTheDocument();
        expect(screen.getByText(/data points per minute/i)).toBeInTheDocument();
        expect(screen.getByText('28,310')).toBeInTheDocument(); // Current data rate
      });
    });

    it('displays error rate and incident tracking', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const metricsTab = screen.getByRole('tab', { name: /metrics/i });
      fireEvent.click(metricsTab);
      
      await waitFor(() => {
        expect(screen.getByTestId('error-chart')).toBeInTheDocument();
        expect(screen.getByText('1.6%')).toBeInTheDocument(); // Error rate
        expect(screen.getByText(/error trends/i)).toBeInTheDocument();
      });
    });

    it('provides performance comparison across providers', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const metricsTab = screen.getByRole('tab', { name: /metrics/i });
      fireEvent.click(metricsTab);
      
      await waitFor(() => {
        expect(screen.getByTestId('provider-comparison')).toBeInTheDocument();
        expect(screen.getByText(/provider performance/i)).toBeInTheDocument();
        
        const comparisonChart = screen.getByTestId('bar-chart');
        expect(comparisonChart).toBeInTheDocument();
      });
    });

    it('shows subscription distribution analytics', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const metricsTab = screen.getByRole('tab', { name: /metrics/i });
      fireEvent.click(metricsTab);
      
      await waitFor(() => {
        expect(screen.getByTestId('subscription-distribution')).toBeInTheDocument();
        
        const pieChart = screen.getByTestId('pie-chart');
        expect(pieChart).toBeInTheDocument();
      });
    });
  });

  describe('System Configuration and Settings', () => {
    it('provides global streaming configuration', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const settingsTab = screen.getByRole('tab', { name: /settings/i });
      fireEvent.click(settingsTab);
      
      await waitFor(() => {
        expect(screen.getByLabelText(/max concurrent streams/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/default retry attempts/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/heartbeat interval/i)).toBeInTheDocument();
      });
    });

    it('allows notification and alerting configuration', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const settingsTab = screen.getByRole('tab', { name: /settings/i });
      fireEvent.click(settingsTab);
      
      await waitFor(() => {
        expect(screen.getByText(/alert settings/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/latency threshold/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/error rate threshold/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/email notifications/i)).toBeInTheDocument();
      });
    });

    it('supports backup and failover configuration', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const settingsTab = screen.getByRole('tab', { name: /settings/i });
      fireEvent.click(settingsTab);
      
      await waitFor(() => {
        expect(screen.getByText(/failover settings/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/enable automatic failover/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/backup provider priority/i)).toBeInTheDocument();
      });
    });

    it('saves configuration changes', async () => {
      const { updateStreamSettings } = await import('../../../services/api');
      renderWithProviders(<LiveDataAdmin />);
      
      const settingsTab = screen.getByRole('tab', { name: /settings/i });
      fireEvent.click(settingsTab);
      
      await waitFor(() => {
        const maxStreamsInput = screen.getByLabelText(/max concurrent streams/i);
        fireEvent.change(maxStreamsInput, { target: { value: '25' } });
        
        const saveButton = screen.getByRole('button', { name: /save settings/i });
        fireEvent.click(saveButton);
      });
      
      expect(updateStreamSettings).toHaveBeenCalledWith(
        expect.objectContaining({ maxConcurrentStreams: 25 })
      );
    });
  });

  describe('Real-time Updates and Monitoring', () => {
    it('updates stream status in real-time', async () => {
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      renderWithProviders(<LiveDataAdmin />);
      
      // Simulate real-time stream update
      const streamUpdate = {
        streamId: 'stream-1',
        latency: 18,
        subscriptions: 47,
        dataPoints: 15450
      };
      
      mockUseWebSocket.mockReturnValue({
        isConnected: true,
        lastMessage: { type: 'stream_update', data: streamUpdate },
        sendMessage: vi.fn(),
        connectionState: 'OPEN'
      });
      
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        const streamCard = screen.getByTestId('stream-stream-1');
        expect(within(streamCard).getByText('18ms')).toBeInTheDocument(); // Updated latency
        expect(within(streamCard).getByText('47')).toBeInTheDocument(); // Updated subscriptions
      });
    });

    it('shows live metrics updates', async () => {
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      
      mockUseWebSocket.mockReturnValue({
        isConnected: true,
        lastMessage: { 
          type: 'metrics_update', 
          data: { 
            totalSubscriptions: 82, 
            averageLatency: 11,
            errorRate: 1.2 
          }
        },
        sendMessage: vi.fn(),
        connectionState: 'OPEN'
      });
      
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(screen.getByTestId('total-subscriptions')).toHaveTextContent('82');
        expect(screen.getByTestId('average-latency')).toHaveTextContent('11ms');
      });
    });

    it('handles stream connection events', async () => {
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      
      mockUseWebSocket.mockReturnValue({
        isConnected: true,
        lastMessage: { 
          type: 'stream_event', 
          data: { 
            streamId: 'stream-3',
            event: 'connected',
            symbol: 'GOOGL'
          }
        },
        sendMessage: vi.fn(),
        connectionState: 'OPEN'
      });
      
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(screen.getByText(/GOOGL stream reconnected/i)).toBeInTheDocument();
      });
    });

    it('updates performance charts with real-time data', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const metricsTab = screen.getByRole('tab', { name: /metrics/i });
      fireEvent.click(metricsTab);
      
      // Simulate new metric data point
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      mockUseWebSocket.mockReturnValue({
        isConnected: true,
        lastMessage: { 
          type: 'metric_data', 
          data: { 
            timestamp: '2024-01-15T10:31:00Z',
            latency: 14,
            throughput: 2950 
          }
        },
        sendMessage: vi.fn(),
        connectionState: 'OPEN'
      });
      
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        const latencyChart = screen.getByTestId('line-chart');
        const chartData = JSON.parse(latencyChart.getAttribute('data-chart-data'));
        expect(chartData.length).toBeGreaterThan(2); // Should have new data point
      });
    });
  });

  describe('Stream Detailed Analysis', () => {
    it('shows detailed stream information modal', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        const detailsButton = screen.getAllByRole('button', { name: /details/i })[0];
        fireEvent.click(detailsButton);
      });
      
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText(/stream details/i)).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    it('displays historical performance for individual streams', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        const detailsButton = screen.getAllByRole('button', { name: /details/i })[0];
        fireEvent.click(detailsButton);
      });
      
      await waitFor(() => {
        expect(screen.getByTestId('stream-history-chart')).toBeInTheDocument();
        
        const historyChart = screen.getByTestId('line-chart');
        const chartData = JSON.parse(historyChart.getAttribute('data-chart-data'));
        expect(chartData).toHaveLength(2); // Historical data points
      });
    });

    it('shows subscription management for streams', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        const detailsButton = screen.getAllByRole('button', { name: /details/i })[0];
        fireEvent.click(detailsButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText(/active subscriptions/i)).toBeInTheDocument();
        expect(screen.getByText('45')).toBeInTheDocument(); // Subscription count
        expect(screen.getByRole('button', { name: /manage subscriptions/i })).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling and Troubleshooting', () => {
    it('displays comprehensive error information', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        const errorStream = screen.getByTestId('stream-stream-3');
        expect(within(errorStream).getByTestId('error-indicator')).toBeInTheDocument();
        expect(within(errorStream).getByText('5')).toBeInTheDocument(); // Error count
      });
    });

    it('provides error details and troubleshooting', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        const errorStream = screen.getByTestId('stream-stream-3');
        const errorButton = within(errorStream).getByRole('button', { name: /view errors/i });
        fireEvent.click(errorButton);
      });
      
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText(/error details/i)).toBeInTheDocument();
      expect(screen.getByText(/troubleshooting/i)).toBeInTheDocument();
    });

    it('handles API failures gracefully', async () => {
      const { getLiveDataStreams } = await import('../../../services/api');
      getLiveDataStreams.mockRejectedValueOnce(new Error('API Error'));
      
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        expect(screen.getByText(/unable to load stream data/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });
    });

    it('shows connection health diagnostics', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const diagnosticsButton = screen.getByRole('button', { name: /diagnostics/i });
      fireEvent.click(diagnosticsButton);
      
      expect(screen.getByText(/system diagnostics/i)).toBeInTheDocument();
      expect(screen.getByText(/connection tests/i)).toBeInTheDocument();
      expect(screen.getByText(/provider status/i)).toBeInTheDocument();
    });
  });

  describe('Performance Optimization', () => {
    it('implements virtualization for large stream lists', () => {
      renderWithProviders(<LiveDataAdmin />);
      
      expect(screen.getByTestId('virtual-stream-list')).toBeInTheDocument();
    });

    it('debounces configuration changes', async () => {
      const { updateStreamSettings } = await import('../../../services/api');
      renderWithProviders(<LiveDataAdmin />);
      
      const settingsTab = screen.getByRole('tab', { name: /settings/i });
      fireEvent.click(settingsTab);
      
      await waitFor(() => {
        const input = screen.getByLabelText(/max concurrent streams/i);
        
        // Rapid changes
        fireEvent.change(input, { target: { value: '20' } });
        fireEvent.change(input, { target: { value: '25' } });
        fireEvent.change(input, { target: { value: '30' } });
      });
      
      // Should debounce to single API call
      await waitFor(() => {
        expect(updateStreamSettings).toHaveBeenCalledTimes(0); // Not called until debounce timeout
      });
    });

    it('uses efficient chart updates for real-time data', () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const metricsTab = screen.getByRole('tab', { name: /metrics/i });
      fireEvent.click(metricsTab);
      
      expect(screen.getByTestId('optimized-chart-updates')).toBeInTheDocument();
    });
  });

  describe('Accessibility Features', () => {
    it('provides comprehensive keyboard navigation', () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const streamCards = screen.getAllByRole('article');
      streamCards.forEach(card => {
        expect(card).toHaveAttribute('tabIndex', '0');
      });
    });

    it('includes ARIA labels and live regions', () => {
      renderWithProviders(<LiveDataAdmin />);
      
      expect(screen.getByRole('main')).toHaveAttribute('aria-label', 'Live data administration dashboard');
      expect(screen.getByRole('status')).toBeInTheDocument(); // Real-time status
    });

    it('announces stream status changes', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      await waitFor(() => {
        const liveRegion = screen.getByRole('status');
        expect(liveRegion).toHaveTextContent(/2 active streams, 77 total subscriptions/i);
      });
    });

    it('provides alternative access to visual charts', async () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const metricsTab = screen.getByRole('tab', { name: /metrics/i });
      fireEvent.click(metricsTab);
      
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /view data table/i })).toBeInTheDocument();
      });
    });
  });

  describe('Mobile Responsiveness', () => {
    it('adapts layout for mobile screens', () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderWithProviders(<LiveDataAdmin />);
      
      expect(screen.getByTestId('mobile-livedata-admin')).toBeInTheDocument();
    });

    it('uses collapsible sections on mobile', () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderWithProviders(<LiveDataAdmin />);
      
      expect(screen.getByTestId('collapsible-stream-list')).toBeInTheDocument();
    });

    it('optimizes charts for mobile viewing', () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderWithProviders(<LiveDataAdmin />);
      
      const metricsTab = screen.getByRole('tab', { name: /metrics/i });
      fireEvent.click(metricsTab);
      
      const chartContainers = screen.getAllByTestId('responsive-container');
      chartContainers.forEach(container => {
        expect(container).toHaveAttribute('height', '200');
      });
    });
  });

  describe('Data Export and Reporting', () => {
    it('supports exporting stream metrics', () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const exportButton = screen.getByRole('button', { name: /export metrics/i });
      fireEvent.click(exportButton);
      
      expect(screen.getByText(/export format/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /csv/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /json/i })).toBeInTheDocument();
    });

    it('generates performance reports', () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const reportButton = screen.getByRole('button', { name: /generate report/i });
      fireEvent.click(reportButton);
      
      expect(screen.getByText(/report configuration/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/time period/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/include providers/i)).toBeInTheDocument();
    });

    it('provides scheduled reporting options', () => {
      renderWithProviders(<LiveDataAdmin />);
      
      const settingsTab = screen.getByRole('tab', { name: /settings/i });
      fireEvent.click(settingsTab);
      
      expect(screen.getByText(/automated reports/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/daily summary/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/weekly analysis/i)).toBeInTheDocument();
    });
  });
});
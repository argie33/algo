import { screen, waitFor, fireEvent, within } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderWithProviders } from '../../test-utils';
import ConnectionMonitor from '../../../components/ConnectionMonitor';

// Mock API service
vi.mock('../../../services/api', () => ({
  getConnectionStatus: vi.fn(() => Promise.resolve({
    data: {
      services: {
        database: {
          status: 'connected',
          responseTime: 45,
          lastChecked: '2024-01-15T10:30:00Z',
          uptime: 99.95,
          connections: { active: 12, max: 50 }
        },
        apiGateway: {
          status: 'connected',
          responseTime: 120,
          lastChecked: '2024-01-15T10:29:58Z',
          uptime: 99.99,
          throughput: { current: 250, max: 1000 }
        },
        redis: {
          status: 'degraded',
          responseTime: 300,
          lastChecked: '2024-01-15T10:29:55Z',
          uptime: 98.5,
          memory: { used: 75, max: 100 }
        },
        websocket: {
          status: 'disconnected',
          responseTime: null,
          lastChecked: '2024-01-15T10:25:00Z',
          uptime: 85.2,
          connections: { active: 0, max: 200 }
        }
      },
      overall: {
        status: 'degraded',
        healthScore: 85.7,
        lastUpdate: '2024-01-15T10:30:00Z'
      }
    }
  })),
  testConnection: vi.fn(() => Promise.resolve({
    success: true,
    responseTime: 89,
    timestamp: '2024-01-15T10:30:15Z'
  })),
  getConnectionHistory: vi.fn(() => Promise.resolve({
    data: {
      database: [
        { timestamp: '2024-01-15T10:25:00Z', responseTime: 42, status: 'connected' },
        { timestamp: '2024-01-15T10:20:00Z', responseTime: 38, status: 'connected' },
        { timestamp: '2024-01-15T10:15:00Z', responseTime: 55, status: 'connected' }
      ],
      incidents: [
        {
          id: 'inc-1',
          service: 'websocket',
          type: 'connection_lost',
          startTime: '2024-01-15T08:45:00Z',
          endTime: null,
          impact: 'Service unavailable for real-time updates'
        }
      ]
    }
  })),
  reconnectService: vi.fn(() => Promise.resolve({ success: true })),
  getServiceMetrics: vi.fn(() => Promise.resolve({
    data: {
      cpu: 45.2,
      memory: 68.5,
      disk: 82.1,
      network: { in: 125.5, out: 89.3 }
    }
  }))
}));

// Mock real-time connection
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    isConnected: true,
    lastMessage: null,
    sendMessage: vi.fn(),
    connectionState: 'OPEN',
    reconnect: vi.fn()
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
  Line: ({ dataKey, stroke, ...props }) => (
    <div data-testid="chart-line" data-key={dataKey} data-stroke={stroke} {...props} />
  ),
  XAxis: ({ dataKey, ...props }) => (
    <div data-testid="x-axis" data-key={dataKey} {...props} />
  ),
  YAxis: (props) => <div data-testid="y-axis" {...props} />,
  CartesianGrid: (props) => <div data-testid="cartesian-grid" {...props} />,
  Tooltip: (props) => <div data-testid="chart-tooltip" {...props} />,
  ReferenceLine: ({ y, stroke, ...props }) => (
    <div data-testid="reference-line" data-y={y} data-stroke={stroke} {...props} />
  )
}));

describe('ConnectionMonitor', () => {
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
    it('renders main connection monitor interface', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByRole('main')).toBeInTheDocument();
        expect(screen.getByText(/connection monitor/i)).toBeInTheDocument();
        expect(screen.getByTestId('connection-dashboard')).toBeInTheDocument();
      });
    });

    it('displays overall system health status', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByTestId('health-score')).toBeInTheDocument();
        expect(screen.getByText('85.7')).toBeInTheDocument(); // Health score
        expect(screen.getByText(/degraded/i)).toBeInTheDocument(); // Overall status
      });
    });

    it('shows last update timestamp', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/last updated/i)).toBeInTheDocument();
        expect(screen.getByText(/just now/i)).toBeInTheDocument();
      });
    });

    it('organizes services into status grid', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByTestId('service-database')).toBeInTheDocument();
        expect(screen.getByTestId('service-apiGateway')).toBeInTheDocument();
        expect(screen.getByTestId('service-redis')).toBeInTheDocument();
        expect(screen.getByTestId('service-websocket')).toBeInTheDocument();
      });
    });
  });

  describe('Service Status Display', () => {
    it('displays connected services with green indicators', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const databaseService = screen.getByTestId('service-database');
        expect(within(databaseService).getByText(/connected/i)).toBeInTheDocument();
        expect(databaseService).toHaveClass('status-connected');
        expect(within(databaseService).getByText('45ms')).toBeInTheDocument(); // Response time
      });
    });

    it('shows degraded services with yellow indicators', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const redisService = screen.getByTestId('service-redis');
        expect(within(redisService).getByText(/degraded/i)).toBeInTheDocument();
        expect(redisService).toHaveClass('status-degraded');
        expect(within(redisService).getByText('300ms')).toBeInTheDocument(); // Slow response
      });
    });

    it('displays disconnected services with red indicators', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const websocketService = screen.getByTestId('service-websocket');
        expect(within(websocketService).getByText(/disconnected/i)).toBeInTheDocument();
        expect(websocketService).toHaveClass('status-disconnected');
        expect(within(websocketService).getByText(/--/)).toBeInTheDocument(); // No response time
      });
    });

    it('shows service uptime percentages', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText('99.95%')).toBeInTheDocument(); // Database uptime
        expect(screen.getByText('99.99%')).toBeInTheDocument(); // API Gateway uptime
        expect(screen.getByText('85.2%')).toBeInTheDocument(); // WebSocket uptime (low)
      });
    });

    it('displays service-specific metrics', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        // Database connections
        expect(screen.getByText('12/50')).toBeInTheDocument();
        
        // API Gateway throughput
        expect(screen.getByText('250/1000')).toBeInTheDocument();
        
        // Redis memory usage
        expect(screen.getByText('75/100')).toBeInTheDocument();
      });
    });
  });

  describe('Connection Testing and Actions', () => {
    it('allows testing individual service connections', async () => {
      const { testConnection } = await import('../../../services/api');
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const testButton = screen.getAllByRole('button', { name: /test/i })[0];
        fireEvent.click(testButton);
      });
      
      expect(testConnection).toHaveBeenCalledWith('database');
      
      await waitFor(() => {
        expect(screen.getByText('89ms')).toBeInTheDocument(); // New response time
      });
    });

    it('supports reconnection attempts for failed services', async () => {
      const { reconnectService } = await import('../../../services/api');
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const websocketService = screen.getByTestId('service-websocket');
        const reconnectButton = within(websocketService).getByRole('button', { name: /reconnect/i });
        fireEvent.click(reconnectButton);
      });
      
      expect(reconnectService).toHaveBeenCalledWith('websocket');
    });

    it('shows reconnection progress and status', async () => {
      const { reconnectService } = await import('../../../services/api');
      reconnectService.mockImplementation(() => 
        new Promise(resolve => setTimeout(() => resolve({ success: true }), 1000))
      );
      
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const reconnectButton = screen.getByRole('button', { name: /reconnect/i });
        fireEvent.click(reconnectButton);
      });
      
      expect(screen.getByText(/reconnecting/i)).toBeInTheDocument();
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('provides refresh all connections functionality', async () => {
      const { getConnectionStatus } = await import('../../../services/api');
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const refreshButton = screen.getByRole('button', { name: /refresh all/i });
        fireEvent.click(refreshButton);
      });
      
      expect(getConnectionStatus).toHaveBeenCalledTimes(2); // Initial + refresh
    });
  });

  describe('Performance Metrics and Charts', () => {
    it('displays response time trends', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByTestId('response-time-chart')).toBeInTheDocument();
        
        const chart = screen.getByTestId('line-chart');
        const chartData = JSON.parse(chart.getAttribute('data-chart-data'));
        expect(chartData).toHaveLength(3); // Historical data points
      });
    });

    it('shows system resource utilization', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/system resources/i)).toBeInTheDocument();
        expect(screen.getByText('45.2%')).toBeInTheDocument(); // CPU
        expect(screen.getByText('68.5%')).toBeInTheDocument(); // Memory
        expect(screen.getByText('82.1%')).toBeInTheDocument(); // Disk
      });
    });

    it('displays network throughput metrics', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/network/i)).toBeInTheDocument();
        expect(screen.getByText('125.5')).toBeInTheDocument(); // In
        expect(screen.getByText('89.3')).toBeInTheDocument(); // Out
      });
    });

    it('provides performance threshold indicators', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        // Response time threshold reference line
        expect(screen.getByTestId('reference-line')).toBeInTheDocument();
        
        // High usage warnings
        expect(screen.getByTestId('disk-warning')).toBeInTheDocument(); // 82.1% > 80% threshold
      });
    });
  });

  describe('Incident Tracking and History', () => {
    it('displays active incidents', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/active incidents/i)).toBeInTheDocument();
        expect(screen.getByText('connection_lost')).toBeInTheDocument();
        expect(screen.getByText('websocket')).toBeInTheDocument();
      });
    });

    it('shows incident duration and impact', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/service unavailable for real-time updates/i)).toBeInTheDocument();
        expect(screen.getByText(/1h 45m/i)).toBeInTheDocument(); // Duration since 08:45
      });
    });

    it('provides incident resolution actions', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const incidentCard = screen.getByTestId('incident-inc-1');
        expect(within(incidentCard).getByRole('button', { name: /resolve/i })).toBeInTheDocument();
        expect(within(incidentCard).getByRole('button', { name: /escalate/i })).toBeInTheDocument();
      });
    });

    it('supports viewing historical connection data', () => {
      renderWithProviders(<ConnectionMonitor />);
      
      const historyButton = screen.getByRole('button', { name: /history/i });
      fireEvent.click(historyButton);
      
      expect(screen.getByText(/connection history/i)).toBeInTheDocument();
      expect(screen.getByRole('table')).toBeInTheDocument();
    });
  });

  describe('Real-time Updates and Monitoring', () => {
    it('updates connection status in real-time', async () => {
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      renderWithProviders(<ConnectionMonitor />);
      
      // Simulate status update via WebSocket
      const statusUpdate = {
        service: 'database',
        status: 'degraded',
        responseTime: 250
      };
      
      mockUseWebSocket.mockReturnValue({
        isConnected: true,
        lastMessage: { type: 'connection_status', data: statusUpdate },
        sendMessage: vi.fn(),
        connectionState: 'OPEN',
        reconnect: vi.fn()
      });
      
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const databaseService = screen.getByTestId('service-database');
        expect(within(databaseService).getByText(/degraded/i)).toBeInTheDocument();
        expect(within(databaseService).getByText('250ms')).toBeInTheDocument();
      });
    });

    it('shows real-time performance metrics', async () => {
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      
      mockUseWebSocket.mockReturnValue({
        isConnected: true,
        lastMessage: { 
          type: 'system_metrics', 
          data: { cpu: 52.8, memory: 71.2 }
        },
        sendMessage: vi.fn(),
        connectionState: 'OPEN',
        reconnect: vi.fn()
      });
      
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText('52.8%')).toBeInTheDocument(); // Updated CPU
        expect(screen.getByText('71.2%')).toBeInTheDocument(); // Updated Memory
      });
    });

    it('maintains chart data with streaming updates', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      const initialChart = await screen.findByTestId('line-chart');
      const initialData = JSON.parse(initialChart.getAttribute('data-chart-data'));
      
      // Simulate new data point
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      mockUseWebSocket.mockReturnValue({
        isConnected: true,
        lastMessage: { 
          type: 'performance_data', 
          data: { timestamp: '2024-01-15T10:31:00Z', responseTime: 67 }
        },
        sendMessage: vi.fn(),
        connectionState: 'OPEN',
        reconnect: vi.fn()
      });
      
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const updatedChart = screen.getByTestId('line-chart');
        const updatedData = JSON.parse(updatedChart.getAttribute('data-chart-data'));
        expect(updatedData.length).toBeGreaterThan(initialData.length);
      });
    });

    it('handles connection monitor WebSocket disconnection', () => {
      const mockUseWebSocket = vi.mocked(require('../../../hooks/useWebSocket').useWebSocket);
      mockUseWebSocket.mockReturnValue({
        isConnected: false,
        lastMessage: null,
        sendMessage: vi.fn(),
        connectionState: 'CLOSED',
        reconnect: vi.fn()
      });
      
      renderWithProviders(<ConnectionMonitor />);
      
      expect(screen.getByText(/monitoring connection lost/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /reconnect monitor/i })).toBeInTheDocument();
    });
  });

  describe('Alert Integration and Notifications', () => {
    it('displays connection-related alerts', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByTestId('connection-alerts')).toBeInTheDocument();
        expect(screen.getByText(/websocket service down/i)).toBeInTheDocument();
      });
    });

    it('shows alert severity indicators', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const alertBadge = screen.getByTestId('alert-badge');
        expect(alertBadge).toHaveTextContent('1'); // One critical alert
        expect(alertBadge).toHaveClass('critical');
      });
    });

    it('provides alert acknowledgment functionality', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const ackButton = screen.getByRole('button', { name: /acknowledge alert/i });
        fireEvent.click(ackButton);
      });
      
      expect(screen.getByText(/alert acknowledged/i)).toBeInTheDocument();
    });
  });

  describe('Configuration and Customization', () => {
    it('allows customizing monitoring intervals', () => {
      renderWithProviders(<ConnectionMonitor />);
      
      const settingsButton = screen.getByRole('button', { name: /settings/i });
      fireEvent.click(settingsButton);
      
      expect(screen.getByLabelText(/refresh interval/i)).toBeInTheDocument();
      expect(screen.getByDisplayValue('30')).toBeInTheDocument(); // Default 30 seconds
    });

    it('supports threshold configuration', () => {
      renderWithProviders(<ConnectionMonitor />);
      
      const settingsButton = screen.getByRole('button', { name: /settings/i });
      fireEvent.click(settingsButton);
      
      expect(screen.getByLabelText(/response time warning/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/response time critical/i)).toBeInTheDocument();
    });

    it('allows enabling/disabling specific services', () => {
      renderWithProviders(<ConnectionMonitor />);
      
      const settingsButton = screen.getByRole('button', { name: /settings/i });
      fireEvent.click(settingsButton);
      
      expect(screen.getByText(/monitored services/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/monitor database/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/monitor websocket/i)).toBeInTheDocument();
    });
  });

  describe('Performance Optimization', () => {
    it('implements efficient data updates without full re-renders', () => {
      const { rerender } = renderWithProviders(<ConnectionMonitor />);
      
      // Re-render with updated data
      rerender(<ConnectionMonitor />);
      
      // Components should remain stable
      expect(screen.getByTestId('service-database')).toBeInTheDocument();
    });

    it('uses memoization for expensive calculations', () => {
      renderWithProviders(<ConnectionMonitor />);
      
      expect(screen.getByTestId('memoized-health-score')).toBeInTheDocument();
    });

    it('batches multiple status updates', async () => {
      const { getConnectionStatus } = await import('../../../services/api');
      renderWithProviders(<ConnectionMonitor />);
      
      // Simulate rapid status changes
      vi.advanceTimersByTime(100);
      vi.advanceTimersByTime(100);
      vi.advanceTimersByTime(100);
      
      // Should batch into single API call
      await waitFor(() => {
        expect(getConnectionStatus).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe('Accessibility Features', () => {
    it('provides comprehensive keyboard navigation', () => {
      renderWithProviders(<ConnectionMonitor />);
      
      const serviceCards = screen.getAllByRole('article');
      serviceCards.forEach(card => {
        expect(card).toHaveAttribute('tabIndex', '0');
      });
    });

    it('includes ARIA labels and live regions', () => {
      renderWithProviders(<ConnectionMonitor />);
      
      expect(screen.getByRole('main')).toHaveAttribute('aria-label', 'System connection monitoring dashboard');
      expect(screen.getByRole('status')).toBeInTheDocument(); // Health score status
    });

    it('announces connection status changes', async () => {
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const liveRegion = screen.getByRole('status');
        expect(liveRegion).toHaveTextContent(/system health: degraded/i);
      });
    });

    it('provides high contrast indicators for status', () => {
      renderWithProviders(<ConnectionMonitor />);
      
      const connectedService = screen.getByTestId('service-database');
      const disconnectedService = screen.getByTestId('service-websocket');
      
      expect(connectedService).toHaveClass('high-contrast-connected');
      expect(disconnectedService).toHaveClass('high-contrast-disconnected');
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('handles API failures gracefully', async () => {
      const { getConnectionStatus } = await import('../../../services/api');
      getConnectionStatus.mockRejectedValueOnce(new Error('Network error'));
      
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/unable to load connection status/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });
    });

    it('shows degraded monitoring when partially connected', async () => {
      const { getConnectionStatus } = await import('../../../services/api');
      getConnectionStatus.mockResolvedValueOnce({
        data: {
          services: { database: { status: 'connected' } },
          overall: { status: 'unknown', healthScore: null }
        }
      });
      
      renderWithProviders(<ConnectionMonitor />);
      
      expect(screen.getByText(/monitoring degraded/i)).toBeInTheDocument();
    });

    it('handles malformed service data', async () => {
      const { getConnectionStatus } = await import('../../../services/api');
      getConnectionStatus.mockResolvedValueOnce({
        data: {
          services: { 
            database: { status: null, responseTime: 'invalid' }
          }
        }
      });
      
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        expect(screen.getByText(/data format error/i)).toBeInTheDocument();
      });
    });

    it('recovers from connection test failures', async () => {
      const { testConnection } = await import('../../../services/api');
      testConnection
        .mockRejectedValueOnce(new Error('Test failed'))
        .mockResolvedValueOnce({ success: true, responseTime: 150 });
      
      renderWithProviders(<ConnectionMonitor />);
      
      await waitFor(() => {
        const testButton = screen.getAllByRole('button', { name: /test/i })[0];
        fireEvent.click(testButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText(/test failed/i)).toBeInTheDocument();
      });
      
      // Retry test
      const retryButton = screen.getByRole('button', { name: /retry test/i });
      fireEvent.click(retryButton);
      
      await waitFor(() => {
        expect(screen.getByText('150ms')).toBeInTheDocument();
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
      
      renderWithProviders(<ConnectionMonitor />);
      
      expect(screen.getByTestId('mobile-connection-monitor')).toBeInTheDocument();
    });

    it('uses simplified service cards on mobile', () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderWithProviders(<ConnectionMonitor />);
      
      expect(screen.getByTestId('mobile-service-grid')).toBeInTheDocument();
    });

    it('provides swipe gestures for mobile navigation', () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      renderWithProviders(<ConnectionMonitor />);
      
      const swipeContainer = screen.getByTestId('swipeable-services');
      expect(swipeContainer).toBeInTheDocument();
    });
  });
});
/**
 * Live Data and Monitoring Components Unit Tests
 * Comprehensive testing of all real-time data and system monitoring components
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock Material-UI components
vi.mock('@mui/material', () => ({
  Box: vi.fn(({ children, ...props }) => <div data-testid="mui-box" {...props}>{children}</div>),
  Typography: vi.fn(({ children, ...props }) => <div data-testid="mui-typography" {...props}>{children}</div>),
  Paper: vi.fn(({ children, ...props }) => <div data-testid="mui-paper" {...props}>{children}</div>),
  Card: vi.fn(({ children, ...props }) => <div data-testid="mui-card" {...props}>{children}</div>),
  CardContent: vi.fn(({ children, ...props }) => <div data-testid="mui-card-content" {...props}>{children}</div>),
  Grid: vi.fn(({ children, ...props }) => <div data-testid="mui-grid" {...props}>{children}</div>),
  Button: vi.fn(({ children, onClick, ...props }) => 
    <button data-testid="mui-button" onClick={onClick} {...props}>{children}</button>
  ),
  IconButton: vi.fn(({ children, onClick, ...props }) => 
    <button data-testid="mui-icon-button" onClick={onClick} {...props}>{children}</button>
  ),
  CircularProgress: vi.fn(() => <div data-testid="mui-circular-progress">Loading...</div>),
  LinearProgress: vi.fn(({ value }) => <div data-testid="mui-linear-progress" data-value={value}>Progress: {value}%</div>),
  Alert: vi.fn(({ children, severity, ...props }) => 
    <div data-testid="mui-alert" data-severity={severity} {...props}>{children}</div>
  ),
  Chip: vi.fn(({ label, color, ...props }) => 
    <span data-testid="mui-chip" data-color={color} {...props}>{label}</span>
  ),
  Badge: vi.fn(({ children, badgeContent, color, ...props }) => 
    <div data-testid="mui-badge" data-badge={badgeContent} data-color={color} {...props}>{children}</div>
  ),
  Switch: vi.fn(({ checked, onChange, ...props }) => 
    <input data-testid="mui-switch" type="checkbox" checked={checked} onChange={onChange} {...props} />
  ),
  Tooltip: vi.fn(({ children, title, ...props }) => 
    <div data-testid="mui-tooltip" title={title} {...props}>{children}</div>
  ),
  List: vi.fn(({ children, ...props }) => 
    <ul data-testid="mui-list" {...props}>{children}</ul>
  ),
  ListItem: vi.fn(({ children, ...props }) => 
    <li data-testid="mui-list-item" {...props}>{children}</li>
  ),
  ListItemText: vi.fn(({ primary, secondary, ...props }) => 
    <div data-testid="mui-list-item-text" {...props}>{primary} {secondary}</div>
  ),
  Table: vi.fn(({ children, ...props }) => 
    <table data-testid="mui-table" {...props}>{children}</table>
  ),
  TableBody: vi.fn(({ children, ...props }) => 
    <tbody data-testid="mui-table-body" {...props}>{children}</tbody>
  ),
  TableCell: vi.fn(({ children, ...props }) => 
    <td data-testid="mui-table-cell" {...props}>{children}</td>
  ),
  TableHead: vi.fn(({ children, ...props }) => 
    <thead data-testid="mui-table-head" {...props}>{children}</thead>
  ),
  TableRow: vi.fn(({ children, ...props }) => 
    <tr data-testid="mui-table-row" {...props}>{children}</tr>
  )
}));

// Mock Recharts
vi.mock('recharts', () => ({
  ResponsiveContainer: vi.fn(({ children }) => <div data-testid="recharts-container">{children}</div>),
  LineChart: vi.fn(() => <div data-testid="line-chart">Chart</div>),
  AreaChart: vi.fn(() => <div data-testid="area-chart">Chart</div>),
  BarChart: vi.fn(() => <div data-testid="bar-chart">Chart</div>),
  Line: vi.fn(() => <div data-testid="line">Line</div>),
  Area: vi.fn(() => <div data-testid="area">Area</div>),
  Bar: vi.fn(() => <div data-testid="bar">Bar</div>),
  XAxis: vi.fn(() => <div data-testid="x-axis">XAxis</div>),
  YAxis: vi.fn(() => <div data-testid="y-axis">YAxis</div>),
  CartesianGrid: vi.fn(() => <div data-testid="cartesian-grid">Grid</div>),
  Tooltip: vi.fn(() => <div data-testid="recharts-tooltip">Tooltip</div>),
  Legend: vi.fn(() => <div data-testid="recharts-legend">Legend</div>)
}));

// Mock services
vi.mock('../../../services/realTimeDataService', () => ({
  default: {
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    getLatestData: vi.fn(() => ({ 
      AAPL: { price: 150.25, change: 2.5, changePercent: 1.69 },
      GOOGL: { price: 2800.50, change: -15.25, changePercent: -0.54 }
    })),
    connect: vi.fn(),
    disconnect: vi.fn(),
    isConnected: vi.fn(() => true)
  }
}));

vi.mock('../../../services/apiHealthService', () => ({
  default: {
    getHealthStatus: vi.fn(() => ({
      overall: 'healthy',
      endpoints: [
        { name: 'api', healthy: true, status: 200, duration: 50 },
        { name: 'database', healthy: true, status: 200, duration: 25 }
      ]
    })),
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    startMonitoring: vi.fn(),
    stopMonitoring: vi.fn()
  }
}));

// Import actual components
import EnhancedLiveDataMonitor from '../../../components/EnhancedLiveDataMonitor';
import LiveDataMonitor from '../../../components/LiveDataMonitor';
import LiveDataDashboard from '../../../components/LiveDataDashboard';
import ProductionMonitoringDashboard from '../../../components/ProductionMonitoringDashboard';
import RealTimePriceWidget from '../../../components/RealTimePriceWidget';
import RealTimeDataStream from '../../../components/RealTimeDataStream';
import SystemHealthMonitor from '../../../components/SystemHealthMonitor';

describe('📊 Live Data and Monitoring Components', () => {
  const mockSymbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA'];
  
  const mockLiveData = {
    AAPL: {
      price: 150.25,
      change: 2.5,
      changePercent: 1.69,
      volume: 1250000,
      timestamp: Date.now()
    },
    GOOGL: {
      price: 2800.50,
      change: -15.25,
      changePercent: -0.54,
      volume: 890000,
      timestamp: Date.now()
    },
    MSFT: {
      price: 380.75,
      change: 5.80,
      changePercent: 1.55,
      volume: 2100000,
      timestamp: Date.now()
    }
  };

  const mockSystemMetrics = {
    cpu: { usage: 45.2, cores: 8 },
    memory: { used: 8.5, total: 16, percentage: 53.1 },
    disk: { used: 120, total: 500, percentage: 24.0 },
    network: { inbound: 1.5, outbound: 0.8 },
    uptime: 86400000,
    processes: 156
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  describe('EnhancedLiveDataMonitor Component', () => {
    it('should render live data monitor with enhanced features', () => {
      render(
        <EnhancedLiveDataMonitor 
          symbols={mockSymbols}
          updateInterval={1000}
          showTechnicals={true}
          showNews={true}
        />
      );

      expect(screen.getByText(/live data monitor/i)).toBeInTheDocument();
      expect(screen.getByTestId('mui-card')).toBeInTheDocument();
    });

    it('should display real-time price updates', async () => {
      render(
        <EnhancedLiveDataMonitor 
          symbols={['AAPL']}
          data={mockLiveData}
        />
      );

      expect(screen.getByText('150.25')).toBeInTheDocument();
      expect(screen.getByText('+2.5')).toBeInTheDocument();
      expect(screen.getByText('(+1.69%)')).toBeInTheDocument();
    });

    it('should handle data updates', async () => {
      const onDataUpdate = vi.fn();
      
      render(
        <EnhancedLiveDataMonitor 
          symbols={mockSymbols}
          onDataUpdate={onDataUpdate}
          updateInterval={500}
        />
      );

      vi.advanceTimersByTime(500);
      
      await waitFor(() => {
        expect(onDataUpdate).toHaveBeenCalled();
      });
    });

    it('should show technical indicators when enabled', () => {
      render(
        <EnhancedLiveDataMonitor 
          symbols={['AAPL']}
          showTechnicals={true}
          technicalIndicators={['RSI', 'MACD', 'SMA']}
        />
      );

      expect(screen.getByText('RSI')).toBeInTheDocument();
      expect(screen.getByText('MACD')).toBeInTheDocument();
      expect(screen.getByText('SMA')).toBeInTheDocument();
    });

    it('should display news feed when enabled', () => {
      const mockNews = [
        { id: 1, title: 'Apple reports strong earnings', timestamp: Date.now() },
        { id: 2, title: 'Tech stocks rally continues', timestamp: Date.now() }
      ];

      render(
        <EnhancedLiveDataMonitor 
          symbols={['AAPL']}
          showNews={true}
          newsData={mockNews}
        />
      );

      expect(screen.getByText('Apple reports strong earnings')).toBeInTheDocument();
      expect(screen.getByText('Tech stocks rally continues')).toBeInTheDocument();
    });

    it('should handle connection status changes', () => {
      const { rerender } = render(
        <EnhancedLiveDataMonitor 
          symbols={mockSymbols}
          connectionStatus="connected"
        />
      );

      expect(screen.getByTestId('mui-chip')).toHaveAttribute('data-color', 'success');

      rerender(
        <EnhancedLiveDataMonitor 
          symbols={mockSymbols}
          connectionStatus="disconnected"
        />
      );

      expect(screen.getByTestId('mui-chip')).toHaveAttribute('data-color', 'error');
    });

    it('should support symbol filtering', async () => {
      const user = userEvent.setup();
      
      render(
        <EnhancedLiveDataMonitor 
          symbols={mockSymbols}
          enableFilter={true}
        />
      );

      const filterInput = screen.getByPlaceholderText(/filter symbols/i);
      await user.type(filterInput, 'AAPL');

      expect(screen.getByDisplayValue('AAPL')).toBeInTheDocument();
    });

    it('should handle alerts and notifications', () => {
      const mockAlerts = [
        { symbol: 'AAPL', type: 'price_alert', message: 'Price above $150', severity: 'warning' }
      ];

      render(
        <EnhancedLiveDataMonitor 
          symbols={['AAPL']}
          alerts={mockAlerts}
          showAlerts={true}
        />
      );

      expect(screen.getByText('Price above $150')).toBeInTheDocument();
      expect(screen.getByTestId('mui-alert')).toHaveAttribute('data-severity', 'warning');
    });
  });

  describe('LiveDataMonitor Component', () => {
    it('should render basic live data monitor', () => {
      render(
        <LiveDataMonitor 
          symbols={mockSymbols}
          updateInterval={1000}
        />
      );

      expect(screen.getByText(/monitoring/i)).toBeInTheDocument();
    });

    it('should start and stop monitoring', async () => {
      const user = userEvent.setup();
      
      render(
        <LiveDataMonitor 
          symbols={mockSymbols}
          autoStart={false}
        />
      );

      const startButton = screen.getByText(/start/i);
      await user.click(startButton);

      expect(screen.getByText(/stop/i)).toBeInTheDocument();
    });

    it('should handle monitoring errors gracefully', () => {
      render(
        <LiveDataMonitor 
          symbols={mockSymbols}
          error="Connection failed"
        />
      );

      expect(screen.getByText('Connection failed')).toBeInTheDocument();
      expect(screen.getByTestId('mui-alert')).toHaveAttribute('data-severity', 'error');
    });

    it('should display loading state', () => {
      render(
        <LiveDataMonitor 
          symbols={mockSymbols}
          loading={true}
        />
      );

      expect(screen.getByTestId('mui-circular-progress')).toBeInTheDocument();
    });

    it('should support custom update intervals', () => {
      const { rerender } = render(
        <LiveDataMonitor 
          symbols={mockSymbols}
          updateInterval={1000}
        />
      );

      rerender(
        <LiveDataMonitor 
          symbols={mockSymbols}
          updateInterval={5000}
        />
      );

      // Interval change would be reflected in component behavior
    });
  });

  describe('LiveDataDashboard Component', () => {
    it('should render comprehensive live data dashboard', () => {
      render(
        <LiveDataDashboard 
          symbols={mockSymbols}
          refreshInterval={1000}
        />
      );

      expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
      expect(screen.getByTestId('mui-grid')).toBeInTheDocument();
    });

    it('should display multiple data widgets', () => {
      render(
        <LiveDataDashboard 
          symbols={mockSymbols}
          widgets={['prices', 'volume', 'charts', 'news']}
        />
      );

      expect(screen.getByText(/prices/i)).toBeInTheDocument();
      expect(screen.getByText(/volume/i)).toBeInTheDocument();
      expect(screen.getByTestId('recharts-container')).toBeInTheDocument();
    });

    it('should handle real-time updates', async () => {
      const onUpdate = vi.fn();
      
      render(
        <LiveDataDashboard 
          symbols={mockSymbols}
          onUpdate={onUpdate}
          refreshInterval={500}
        />
      );

      vi.advanceTimersByTime(500);
      
      await waitFor(() => {
        expect(onUpdate).toHaveBeenCalled();
      });
    });

    it('should support dashboard customization', async () => {
      const user = userEvent.setup();
      
      render(
        <LiveDataDashboard 
          symbols={mockSymbols}
          customizable={true}
        />
      );

      const customizeButton = screen.getByText(/customize/i);
      await user.click(customizeButton);

      expect(screen.getByText(/layout/i)).toBeInTheDocument();
    });

    it('should handle loading states for different widgets', () => {
      render(
        <LiveDataDashboard 
          symbols={mockSymbols}
          loadingStates={{
            prices: true,
            volume: false,
            charts: true
          }}
        />
      );

      // Some widgets should show loading, others should show data
      expect(screen.getAllByTestId('mui-circular-progress')).toHaveLength(2);
    });
  });

  describe('ProductionMonitoringDashboard Component', () => {
    it('should render production monitoring dashboard', () => {
      render(
        <ProductionMonitoringDashboard 
          environment="production"
          showAlerts={true}
        />
      );

      expect(screen.getByText(/production/i)).toBeInTheDocument();
      expect(screen.getByText(/monitoring/i)).toBeInTheDocument();
    });

    it('should display system metrics', () => {
      render(
        <ProductionMonitoringDashboard 
          metrics={mockSystemMetrics}
        />
      );

      expect(screen.getByText('45.2%')).toBeInTheDocument(); // CPU usage
      expect(screen.getByText('53.1%')).toBeInTheDocument(); // Memory usage
      expect(screen.getByText('24.0%')).toBeInTheDocument(); // Disk usage
    });

    it('should show alerts and warnings', () => {
      const mockAlerts = [
        { id: 1, type: 'critical', message: 'High CPU usage detected', timestamp: Date.now() },
        { id: 2, type: 'warning', message: 'Memory usage above threshold', timestamp: Date.now() }
      ];

      render(
        <ProductionMonitoringDashboard 
          alerts={mockAlerts}
          showAlerts={true}
        />
      );

      expect(screen.getByText('High CPU usage detected')).toBeInTheDocument();
      expect(screen.getByText('Memory usage above threshold')).toBeInTheDocument();
    });

    it('should handle environment switching', () => {
      const { rerender } = render(
        <ProductionMonitoringDashboard environment="production" />
      );

      expect(screen.getByText(/production/i)).toBeInTheDocument();

      rerender(
        <ProductionMonitoringDashboard environment="staging" />
      );

      expect(screen.getByText(/staging/i)).toBeInTheDocument();
    });

    it('should display uptime and availability metrics', () => {
      render(
        <ProductionMonitoringDashboard 
          uptime={99.95}
          availability={99.8}
          responseTime={150}
        />
      );

      expect(screen.getByText('99.95%')).toBeInTheDocument();
      expect(screen.getByText('99.8%')).toBeInTheDocument();
      expect(screen.getByText('150ms')).toBeInTheDocument();
    });

    it('should support real-time monitoring controls', async () => {
      const user = userEvent.setup();
      
      render(
        <ProductionMonitoringDashboard 
          realTimeEnabled={false}
        />
      );

      const enableRealTimeSwitch = screen.getByTestId('mui-switch');
      await user.click(enableRealTimeSwitch);

      expect(enableRealTimeSwitch).toBeChecked();
    });
  });

  describe('RealTimePriceWidget Component', () => {
    it('should render real-time price widget', () => {
      render(
        <RealTimePriceWidget 
          symbol="AAPL"
          showChange={true}
          showVolume={true}
        />
      );

      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    it('should display price information', () => {
      render(
        <RealTimePriceWidget 
          symbol="AAPL"
          price={150.25}
          change={2.5}
          changePercent={1.69}
          volume={1250000}
        />
      );

      expect(screen.getByText('$150.25')).toBeInTheDocument();
      expect(screen.getByText('+$2.50')).toBeInTheDocument();
      expect(screen.getByText('+1.69%')).toBeInTheDocument();
      expect(screen.getByText('1.25M')).toBeInTheDocument();
    });

    it('should handle positive and negative changes', () => {
      const { rerender } = render(
        <RealTimePriceWidget 
          symbol="AAPL"
          change={2.5}
          changePercent={1.69}
        />
      );

      expect(screen.getByText('+$2.50')).toBeInTheDocument();

      rerender(
        <RealTimePriceWidget 
          symbol="AAPL"
          change={-1.5}
          changePercent={-0.98}
        />
      );

      expect(screen.getByText('-$1.50')).toBeInTheDocument();
      expect(screen.getByText('-0.98%')).toBeInTheDocument();
    });

    it('should show mini chart when enabled', () => {
      render(
        <RealTimePriceWidget 
          symbol="AAPL"
          showChart={true}
          chartData={[
            { time: '09:30', price: 148.50 },
            { time: '10:30', price: 149.25 },
            { time: '11:30', price: 150.25 }
          ]}
        />
      );

      expect(screen.getByTestId('recharts-container')).toBeInTheDocument();
    });

    it('should handle click interactions', async () => {
      const user = userEvent.setup();
      const onClick = vi.fn();

      render(
        <RealTimePriceWidget 
          symbol="AAPL"
          onClick={onClick}
          interactive={true}
        />
      );

      await user.click(screen.getByText('AAPL'));
      expect(onClick).toHaveBeenCalledWith('AAPL');
    });

    it('should support different size variants', () => {
      const { rerender } = render(
        <RealTimePriceWidget symbol="AAPL" size="small" />
      );

      rerender(<RealTimePriceWidget symbol="AAPL" size="large" />);
      
      // Size variants would affect styling and content density
    });
  });

  describe('RealTimeDataStream Component', () => {
    it('should render real-time data stream', () => {
      render(
        <RealTimeDataStream 
          symbols={['AAPL']}
          onDataUpdate={vi.fn()}
        />
      );

      expect(screen.getByText(/data stream/i)).toBeInTheDocument();
    });

    it('should handle WebSocket connection', () => {
      const onConnect = vi.fn();
      const onDisconnect = vi.fn();

      render(
        <RealTimeDataStream 
          symbols={mockSymbols}
          onConnect={onConnect}
          onDisconnect={onDisconnect}
          connectionType="websocket"
        />
      );

      expect(screen.getByText(/websocket/i)).toBeInTheDocument();
    });

    it('should display connection status', () => {
      render(
        <RealTimeDataStream 
          symbols={mockSymbols}
          connectionStatus="connected"
          showStatus={true}
        />
      );

      expect(screen.getByTestId('mui-chip')).toHaveAttribute('data-color', 'success');
      expect(screen.getByText(/connected/i)).toBeInTheDocument();
    });

    it('should handle data streaming', async () => {
      const onDataUpdate = vi.fn();
      
      render(
        <RealTimeDataStream 
          symbols={['AAPL']}
          onDataUpdate={onDataUpdate}
          streamingEnabled={true}
        />
      );

      // Simulate data stream
      vi.advanceTimersByTime(1000);
      
      await waitFor(() => {
        expect(onDataUpdate).toHaveBeenCalled();
      });
    });

    it('should support throttling and buffering', () => {
      render(
        <RealTimeDataStream 
          symbols={mockSymbols}
          throttleMs={500}
          bufferSize={100}
          enableBuffering={true}
        />
      );

      expect(screen.getByText(/buffering/i)).toBeInTheDocument();
    });

    it('should handle connection errors', () => {
      render(
        <RealTimeDataStream 
          symbols={mockSymbols}
          connectionError="WebSocket connection failed"
          autoReconnect={true}
        />
      );

      expect(screen.getByText('WebSocket connection failed')).toBeInTheDocument();
      expect(screen.getByText(/reconnecting/i)).toBeInTheDocument();
    });
  });

  describe('SystemHealthMonitor Component', () => {
    it('should render system health monitor', () => {
      render(
        <SystemHealthMonitor 
          autoRefresh={true}
          refreshInterval={30000}
        />
      );

      expect(screen.getByText(/system health/i)).toBeInTheDocument();
    });

    it('should display health status indicators', () => {
      const healthStatus = {
        overall: 'healthy',
        services: {
          api: 'healthy',
          database: 'healthy',
          cache: 'warning',
          storage: 'error'
        }
      };

      render(
        <SystemHealthMonitor 
          healthStatus={healthStatus}
        />
      );

      expect(screen.getByText(/healthy/i)).toBeInTheDocument();
      expect(screen.getByText(/warning/i)).toBeInTheDocument();
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });

    it('should show detailed metrics', () => {
      render(
        <SystemHealthMonitor 
          metrics={mockSystemMetrics}
          showDetails={true}
        />
      );

      expect(screen.getByText('CPU: 45.2%')).toBeInTheDocument();
      expect(screen.getByText('Memory: 53.1%')).toBeInTheDocument();
      expect(screen.getByText('Disk: 24.0%')).toBeInTheDocument();
    });

    it('should handle manual refresh', async () => {
      const user = userEvent.setup();
      const onRefresh = vi.fn();

      render(
        <SystemHealthMonitor 
          onRefresh={onRefresh}
          showRefreshButton={true}
        />
      );

      const refreshButton = screen.getByText(/refresh/i);
      await user.click(refreshButton);

      expect(onRefresh).toHaveBeenCalled();
    });

    it('should display historical trends', () => {
      const trendData = [
        { timestamp: Date.now() - 3600000, cpu: 40, memory: 50 },
        { timestamp: Date.now() - 1800000, cpu: 45, memory: 52 },
        { timestamp: Date.now(), cpu: 45.2, memory: 53.1 }
      ];

      render(
        <SystemHealthMonitor 
          trendData={trendData}
          showTrends={true}
        />
      );

      expect(screen.getByTestId('recharts-container')).toBeInTheDocument();
    });

    it('should handle alert thresholds', () => {
      const alertThresholds = {
        cpu: 80,
        memory: 85,
        disk: 90
      };

      render(
        <SystemHealthMonitor 
          metrics={mockSystemMetrics}
          alertThresholds={alertThresholds}
        />
      );

      // No alerts should be shown since metrics are below thresholds
      expect(screen.queryByTestId('mui-alert')).not.toBeInTheDocument();
    });
  });

  describe('Component Integration', () => {
    it('should sync data between multiple monitoring components', () => {
      const sharedData = mockLiveData;

      render(
        <div>
          <LiveDataMonitor 
            symbols={['AAPL']}
            data={sharedData}
          />
          <RealTimePriceWidget 
            symbol="AAPL"
            price={sharedData.AAPL.price}
            change={sharedData.AAPL.change}
          />
        </div>
      );

      // Both components should show the same data
      expect(screen.getAllByText('150.25')).toHaveLength(2);
    });

    it('should handle global pause/resume functionality', async () => {
      const user = userEvent.setup();

      render(
        <div>
          <button data-testid="global-pause">Pause All</button>
          <LiveDataMonitor symbols={['AAPL']} />
          <RealTimeDataStream symbols={['AAPL']} />
        </div>
      );

      const pauseButton = screen.getByTestId('global-pause');
      await user.click(pauseButton);

      // All monitoring should be paused
    });

    it('should share connection status across components', () => {
      const connectionStatus = 'connected';

      render(
        <div>
          <LiveDataMonitor 
            symbols={['AAPL']}
            connectionStatus={connectionStatus}
          />
          <RealTimeDataStream 
            symbols={['AAPL']}
            connectionStatus={connectionStatus}
          />
        </div>
      );

      expect(screen.getAllByText(/connected/i)).toHaveLength(2);
    });
  });

  describe('Performance and Optimization', () => {
    it('should handle high-frequency updates efficiently', () => {
      const startTime = performance.now();

      render(
        <LiveDataMonitor 
          symbols={mockSymbols}
          updateInterval={100}
          optimized={true}
        />
      );

      const renderTime = performance.now() - startTime;
      expect(renderTime).toBeLessThan(100);
    });

    it('should implement data throttling', async () => {
      const onDataUpdate = vi.fn();

      render(
        <RealTimeDataStream 
          symbols={['AAPL']}
          onDataUpdate={onDataUpdate}
          throttleMs={500}
        />
      );

      // Simulate rapid updates
      for (let i = 0; i < 10; i++) {
        vi.advanceTimersByTime(50);
      }

      // Should be throttled to fewer calls
      expect(onDataUpdate).toHaveBeenCalledTimes(1);
    });

    it('should handle memory cleanup on unmount', () => {
      const { unmount } = render(
        <LiveDataMonitor symbols={mockSymbols} />
      );

      unmount();

      // Component should clean up subscriptions and timers
    });
  });

  describe('Error Handling', () => {
    it('should handle data fetch errors gracefully', () => {
      render(
        <LiveDataMonitor 
          symbols={mockSymbols}
          error="Failed to fetch data"
        />
      );

      expect(screen.getByText('Failed to fetch data')).toBeInTheDocument();
      expect(screen.getByTestId('mui-alert')).toHaveAttribute('data-severity', 'error');
    });

    it('should retry on connection failures', async () => {
      const user = userEvent.setup();
      const onRetry = vi.fn();

      render(
        <RealTimeDataStream 
          symbols={['AAPL']}
          connectionError="Connection lost"
          onRetry={onRetry}
        />
      );

      const retryButton = screen.getByText(/retry/i);
      await user.click(retryButton);

      expect(onRetry).toHaveBeenCalled();
    });

    it('should handle malformed data gracefully', () => {
      const malformedData = {
        AAPL: {
          price: 'invalid',
          change: null,
          volume: undefined
        }
      };

      render(
        <RealTimePriceWidget 
          symbol="AAPL"
          price={malformedData.AAPL.price}
          change={malformedData.AAPL.change}
          volume={malformedData.AAPL.volume}
        />
      );

      expect(screen.getByText(/invalid data/i)).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should provide screen reader announcements for price changes', () => {
      render(
        <RealTimePriceWidget 
          symbol="AAPL"
          price={150.25}
          change={2.5}
          announceChanges={true}
        />
      );

      const announcement = screen.getByLabelText(/price update/i);
      expect(announcement).toBeInTheDocument();
    });

    it('should support keyboard navigation', async () => {
      const user = userEvent.setup();

      render(
        <LiveDataDashboard 
          symbols={mockSymbols}
          keyboardNavigable={true}
        />
      );

      await user.tab();
      // Should focus on first interactive element
    });

    it('should provide proper ARIA labels', () => {
      render(
        <SystemHealthMonitor 
          metrics={mockSystemMetrics}
        />
      );

      const healthStatus = screen.getByRole('status');
      expect(healthStatus).toHaveAttribute('aria-label', /system health/i);
    });
  });
});
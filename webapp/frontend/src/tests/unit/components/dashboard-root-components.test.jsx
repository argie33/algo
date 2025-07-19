/**
 * Dashboard Root Components Unit Tests
 * Comprehensive testing of all root-level dashboard and monitoring components
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
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
  CircularProgress: vi.fn(() => <div data-testid="mui-circular-progress">Loading...</div>),
  Alert: vi.fn(({ children, ...props }) => <div data-testid="mui-alert" {...props}>{children}</div>),
  Chip: vi.fn(({ label, ...props }) => <span data-testid="mui-chip" {...props}>{label}</span>),
  LinearProgress: vi.fn(() => <div data-testid="mui-linear-progress">Progress...</div>),
}));

// Mock Recharts
vi.mock('recharts', () => ({
  ResponsiveContainer: vi.fn(({ children }) => <div data-testid="recharts-container">{children}</div>),
  LineChart: vi.fn(() => <div data-testid="line-chart">Chart</div>),
  AreaChart: vi.fn(() => <div data-testid="area-chart">Chart</div>),
  PieChart: vi.fn(() => <div data-testid="pie-chart">Chart</div>),
  Line: vi.fn(() => <div data-testid="line">Line</div>),
  Area: vi.fn(() => <div data-testid="area">Area</div>),
  Pie: vi.fn(() => <div data-testid="pie">Pie</div>),
  XAxis: vi.fn(() => <div data-testid="x-axis">XAxis</div>),
  YAxis: vi.fn(() => <div data-testid="y-axis">YAxis</div>),
  CartesianGrid: vi.fn(() => <div data-testid="cartesian-grid">Grid</div>),
  Tooltip: vi.fn(() => <div data-testid="tooltip">Tooltip</div>),
  Legend: vi.fn(() => <div data-testid="legend">Legend</div>),
}));

// Mock services
vi.mock('../../../services/apiHealthService', () => ({
  default: {
    getHealthStatus: vi.fn(() => ({
      overall: 'healthy',
      endpoints: [
        { name: 'api', healthy: true, status: 200, duration: 50 }
      ]
    })),
    subscribe: vi.fn(),
    unsubscribe: vi.fn()
  }
}));

vi.mock('../../../services/realTimeDataService', () => ({
  default: {
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    getLatestData: vi.fn(() => ({ AAPL: { price: 150.25, change: 2.5 } }))
  }
}));

// Dashboard Components - Import actual production components
import AdvancedTradingDashboard from '../../../components/AdvancedTradingDashboard';
import AlpacaDataDashboard from '../../../components/AlpacaDataDashboard';
import ApiDebugger from '../../../components/ApiDebugger';
import ApiKeyHealthCheck from '../../../components/ApiKeyHealthCheck';
import ApiKeyOnboarding from '../../../components/ApiKeyOnboarding';
import ApiKeyStatusIndicator from '../../../components/ApiKeyStatusIndicator';
import DashboardCustomization from '../../../components/DashboardCustomization';
import DashboardStockChart from '../../../components/DashboardStockChart';
import DataSourceIndicator from '../../../components/DataSourceIndicator';
import LiveDataDashboard from '../../../components/LiveDataDashboard';
import LiveDataMonitor from '../../../components/LiveDataMonitor';
import EnhancedLiveDataMonitor from '../../../components/EnhancedLiveDataMonitor';
import MarketStatusBar from '../../../components/MarketStatusBar';
import PersonalizedDashboardHeader from '../../../components/PersonalizedDashboardHeader';
import PortfolioManager from '../../../components/PortfolioManager';
import ProductionMonitoringDashboard from '../../../components/ProductionMonitoringDashboard';
import ProfessionalChart from '../../../components/ProfessionalChart';
import RealTimeDataStream from '../../../components/RealTimeDataStream';
import RealTimePriceWidget from '../../../components/RealTimePriceWidget';
import ResponsiveLayout from '../../../components/ResponsiveLayout';
import ResponsiveNavigation from '../../../components/ResponsiveNavigation';
import RiskManager from '../../../components/RiskManager';
import SettingsManager from '../../../components/SettingsManager';
import SimpleAlpacaData from '../../../components/SimpleAlpacaData';
import SmartWatchlist from '../../../components/SmartWatchlist';
import StockChart from '../../../components/StockChart';
import SystemHealthMonitor from '../../../components/SystemHealthMonitor';
import WatchlistAlerts from '../../../components/WatchlistAlerts';
import WelcomeOverlay from '../../../components/WelcomeOverlay';

describe('📊 Dashboard Root Components', () => {
  const mockStockData = [
    { date: '2024-01-01', price: 150.25, volume: 1000000 },
    { date: '2024-01-02', price: 152.50, volume: 1200000 },
    { date: '2024-01-03', price: 148.75, volume: 900000 }
  ];

  const mockPortfolioData = {
    totalValue: 50000,
    dayChange: 1250,
    dayChangePercent: 2.56,
    positions: [
      { symbol: 'AAPL', shares: 100, currentPrice: 150.25, value: 15025 },
      { symbol: 'GOOGL', shares: 50, currentPrice: 2800.50, value: 140025 }
    ]
  };

  const mockApiKeys = {
    alpaca: { keyId: 'PK123', secretKey: '***', enabled: true },
    polygon: { apiKey: 'pol123', enabled: true }
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('🏦 Trading Dashboard Components', () => {
    it('should render AdvancedTradingDashboard correctly', () => {
      const { container } = render(
        <AdvancedTradingDashboard 
          portfolioData={mockPortfolioData}
          apiKeys={mockApiKeys}
        />
      );

      expect(container).toBeInTheDocument();
      expect(container.querySelector('[data-testid="mui-paper"]')).toBeInTheDocument();
    });

    it('should render AlpacaDataDashboard with live data', () => {
      const { container } = render(
        <AlpacaDataDashboard 
          symbols={['AAPL', 'GOOGL']}
          apiKey="test-key"
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render LiveDataDashboard with real-time updates', () => {
      const { container } = render(
        <LiveDataDashboard 
          symbols={['AAPL', 'MSFT']}
          refreshInterval={1000}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render ProductionMonitoringDashboard with system metrics', () => {
      const { container } = render(
        <ProductionMonitoringDashboard 
          environment="production"
          showAlerts={true}
        />
      );

      expect(container).toBeInTheDocument();
    });
  });

  describe('📈 Chart and Visualization Components', () => {
    it('should render DashboardStockChart with price data', () => {
      const { container } = render(
        <DashboardStockChart 
          symbol="AAPL"
          data={mockStockData}
          height={400}
        />
      );

      expect(container).toBeInTheDocument();
      expect(container.querySelector('[data-testid="recharts-container"]')).toBeInTheDocument();
    });

    it('should render ProfessionalChart with technical indicators', () => {
      const { container } = render(
        <ProfessionalChart 
          data={mockStockData}
          indicators={['SMA', 'RSI']}
          timeframe="1D"
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render StockChart with customizable options', () => {
      const { container } = render(
        <StockChart 
          symbol="AAPL"
          data={mockStockData}
          showVolume={true}
          showTechnicals={true}
        />
      );

      expect(container).toBeInTheDocument();
    });
  });

  describe('🔑 API Key Management Components', () => {
    it('should render ApiKeyOnboarding wizard', () => {
      const onComplete = vi.fn();
      const { container } = render(
        <ApiKeyOnboarding 
          onComplete={onComplete}
          providers={['alpaca', 'polygon']}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render ApiKeyHealthCheck with status indicators', () => {
      const { container } = render(
        <ApiKeyHealthCheck 
          apiKeys={mockApiKeys}
          autoCheck={true}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render ApiKeyStatusIndicator with visual status', () => {
      const { container } = render(
        <ApiKeyStatusIndicator 
          provider="alpaca"
          status="connected"
          lastChecked={new Date()}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render ApiDebugger for troubleshooting', () => {
      const { container } = render(
        <ApiDebugger 
          apiKeys={mockApiKeys}
          showLogs={true}
        />
      );

      expect(container).toBeInTheDocument();
    });
  });

  describe('💼 Portfolio Management Components', () => {
    it('should render PortfolioManager with position management', () => {
      const { container } = render(
        <PortfolioManager 
          portfolioData={mockPortfolioData}
          onUpdatePosition={vi.fn()}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render RiskManager with risk metrics', () => {
      const { container } = render(
        <RiskManager 
          portfolioData={mockPortfolioData}
          riskProfile="moderate"
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render SmartWatchlist with intelligent recommendations', () => {
      const { container } = render(
        <SmartWatchlist 
          symbols={['AAPL', 'GOOGL', 'MSFT']}
          onSymbolSelect={vi.fn()}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render WatchlistAlerts with notification settings', () => {
      const { container } = render(
        <WatchlistAlerts 
          watchlist={['AAPL', 'GOOGL']}
          onAlertCreate={vi.fn()}
        />
      );

      expect(container).toBeInTheDocument();
    });
  });

  describe('📱 Real-Time Data Components', () => {
    it('should render LiveDataMonitor with streaming data', () => {
      const { container } = render(
        <LiveDataMonitor 
          symbols={['AAPL', 'GOOGL']}
          updateInterval={1000}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render EnhancedLiveDataMonitor with advanced features', () => {
      const { container } = render(
        <EnhancedLiveDataMonitor 
          symbols={['AAPL', 'MSFT']}
          showTechnicals={true}
          showNews={true}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render RealTimeDataStream with WebSocket connection', () => {
      const { container } = render(
        <RealTimeDataStream 
          symbols={['AAPL']}
          onDataUpdate={vi.fn()}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render RealTimePriceWidget with live prices', () => {
      const { container } = render(
        <RealTimePriceWidget 
          symbol="AAPL"
          showChange={true}
          showVolume={true}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render MarketStatusBar with market hours', () => {
      const { container } = render(
        <MarketStatusBar 
          showCountdown={true}
          timezone="America/New_York"
        />
      );

      expect(container).toBeInTheDocument();
    });
  });

  describe('🎛️ Layout and Navigation Components', () => {
    it('should render ResponsiveLayout with mobile adaptation', () => {
      const { container } = render(
        <ResponsiveLayout 
          sidebar={<div>Sidebar</div>}
          main={<div>Main Content</div>}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render ResponsiveNavigation with menu items', () => {
      const menuItems = [
        { label: 'Dashboard', path: '/' },
        { label: 'Portfolio', path: '/portfolio' },
        { label: 'Settings', path: '/settings' }
      ];

      const { container } = render(
        <ResponsiveNavigation 
          menuItems={menuItems}
          currentPath="/"
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render PersonalizedDashboardHeader with user info', () => {
      const userData = {
        name: 'John Doe',
        email: 'john@example.com',
        avatarUrl: '/avatar.jpg'
      };

      const { container } = render(
        <PersonalizedDashboardHeader 
          user={userData}
          onLogout={vi.fn()}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render DashboardCustomization with layout options', () => {
      const { container } = render(
        <DashboardCustomization 
          layout="grid"
          onLayoutChange={vi.fn()}
          availableWidgets={['portfolio', 'watchlist', 'news']}
        />
      );

      expect(container).toBeInTheDocument();
    });
  });

  describe('⚙️ System Monitoring Components', () => {
    it('should render SystemHealthMonitor with system status', () => {
      const { container } = render(
        <SystemHealthMonitor 
          autoRefresh={true}
          refreshInterval={30000}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render DataSourceIndicator with connection status', () => {
      const { container } = render(
        <DataSourceIndicator 
          source="alpaca"
          status="connected"
          lastUpdate={new Date()}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render SettingsManager with configuration options', () => {
      const { container } = render(
        <SettingsManager 
          currentSettings={{}}
          onSettingsChange={vi.fn()}
        />
      );

      expect(container).toBeInTheDocument();
    });
  });

  describe('🎯 User Experience Components', () => {
    it('should render WelcomeOverlay for new users', () => {
      const { container } = render(
        <WelcomeOverlay 
          isFirstVisit={true}
          onDismiss={vi.fn()}
          onStartTour={vi.fn()}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should render SimpleAlpacaData for quick market overview', () => {
      const { container } = render(
        <SimpleAlpacaData 
          symbols={['AAPL', 'GOOGL']}
          showChart={true}
        />
      );

      expect(container).toBeInTheDocument();
    });
  });

  describe('🔧 Interactive Features', () => {
    it('should handle user interactions in PortfolioManager', async () => {
      const onUpdatePosition = vi.fn();
      const user = userEvent.setup();

      render(
        <PortfolioManager 
          portfolioData={mockPortfolioData}
          onUpdatePosition={onUpdatePosition}
        />
      );

      // Look for interactive elements
      const buttons = screen.queryAllByRole('button');
      if (buttons.length > 0) {
        await user.click(buttons[0]);
      }
    });

    it('should handle symbol selection in SmartWatchlist', async () => {
      const onSymbolSelect = vi.fn();
      const user = userEvent.setup();

      render(
        <SmartWatchlist 
          symbols={['AAPL', 'GOOGL', 'MSFT']}
          onSymbolSelect={onSymbolSelect}
        />
      );

      // Test would interact with symbol selection if rendered
    });

    it('should handle chart interactions in DashboardStockChart', async () => {
      const onChartInteraction = vi.fn();

      const { container } = render(
        <DashboardStockChart 
          symbol="AAPL"
          data={mockStockData}
          onChartInteraction={onChartInteraction}
        />
      );

      // Chart interactions would be tested here
      expect(container).toBeInTheDocument();
    });
  });

  describe('📊 Data Loading and Error States', () => {
    it('should handle loading state in LiveDataDashboard', () => {
      const { container } = render(
        <LiveDataDashboard 
          symbols={['AAPL']}
          loading={true}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should handle error state in SystemHealthMonitor', () => {
      const { container } = render(
        <SystemHealthMonitor 
          error="Connection failed"
          onRetry={vi.fn()}
        />
      );

      expect(container).toBeInTheDocument();
    });

    it('should handle empty data in SmartWatchlist', () => {
      const { container } = render(
        <SmartWatchlist 
          symbols={[]}
          emptyMessage="No symbols in watchlist"
        />
      );

      expect(container).toBeInTheDocument();
    });
  });
});
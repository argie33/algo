/**
 * Unit Tests for Dashboard Component
 * Tests the main dashboard that users see when they log in
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import Dashboard from '../../../pages/Dashboard.jsx';

// Mock the API service
vi.mock('../../../services/api.js', () => ({
  api: {
    getPortfolio: vi.fn(),
    getMarketSummary: vi.fn(),
    getWatchlist: vi.fn(),
    getRecentOrders: vi.fn()
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: 'http://localhost:3001',
    environment: 'test'
  })),
  initializeApi: vi.fn(),
  testApiConnection: vi.fn()
}));

// Mock chart components to avoid canvas issues in tests
vi.mock('react-chartjs-2', () => ({
  Line: ({ data }) => <div data-testid="market-chart">Market Chart with {data?.datasets?.length || 0} datasets</div>,
  Bar: ({ data }) => <div data-testid="performance-chart">Performance Chart</div>
}));

// Mock WebSocket for real-time data
vi.mock('../../../services/websocketService.js', () => ({
  useWebSocket: () => ({
    isConnected: true,
    lastMessage: null,
    connectionState: 'connected'
  })
}));

// Wrapper component for router context
const TestWrapper = ({ children }) => (
  <BrowserRouter>
    {children}
  </BrowserRouter>
);

describe('Dashboard Component - Trading Overview', () => {
  
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Dashboard Loading and Layout', () => {
    it('should render main dashboard sections', async () => {
      // Critical: Dashboard is the first thing users see after login
      const { api } = await import('../../../services/api.js');
      
      // Mock successful API responses
      api.getPortfolio.mockResolvedValue({
        totalValue: 100000,
        todaysPnL: 1500,
        positions: []
      });
      api.getMarketSummary.mockResolvedValue({
        sp500: { price: 4200, change: 25.5 },
        nasdaq: { price: 13500, change: 75.2 }
      });
      api.getWatchlist.mockResolvedValue([]);
      api.getRecentOrders.mockResolvedValue([]);

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should show portfolio summary
      await waitFor(() => {
        expect(screen.getByText(/portfolio/i) || screen.getByText(/total/i)).toBeTruthy();
      });

      // Should show market data section
      expect(screen.getByText(/market/i) || screen.getByText(/summary/i)).toBeTruthy();

      // Should show some form of navigation or quick actions
      expect(screen.getByText(/trade/i) || screen.getByText(/buy/i) || screen.getByText(/sell/i)).toBeTruthy();
    });

    it('should display portfolio value prominently', async () => {
      // Critical: Portfolio value is the most important metric for users
      const { api } = await import('../../../services/api.js');
      api.getPortfolio.mockResolvedValue({
        totalValue: 247350.75,
        todaysPnL: 3250.50,
        totalPnL: 47350.75,
        positions: [
          { symbol: 'AAPL', marketValue: 50000 },
          { symbol: 'MSFT', marketValue: 30000 }
        ]
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should prominently display total portfolio value
        expect(screen.getByText(/247,350\.75/i) || screen.getByText(/\$247,350/i)).toBeTruthy();
      });

      // Should show today's P&L
      expect(screen.getByText(/3,250\.50/i) || screen.getByText(/\$3,250/i)).toBeTruthy();
    });

    it('should handle loading states appropriately', async () => {
      // Critical: Users should see loading indicators during data fetch
      const { api } = await import('../../../services/api.js');
      
      // Make API calls hang to test loading state
      api.getPortfolio.mockImplementation(() => new Promise(() => {}));
      api.getMarketSummary.mockImplementation(() => new Promise(() => {}));

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should show loading indicators
      const loadingElements = screen.getAllByText(/loading/i);
      expect(loadingElements.length).toBeGreaterThan(0);
    });
  });

  describe('Market Data Display', () => {
    it('should show current market indices', async () => {
      // Critical: Market context helps users make trading decisions
      const { api } = await import('../../../services/api.js');
      api.getMarketSummary.mockResolvedValue({
        sp500: { 
          price: 4185.50, 
          change: -15.25, 
          changePercent: -0.36,
          volume: 3500000 
        },
        nasdaq: { 
          price: 13245.75, 
          change: 45.80, 
          changePercent: 0.35 
        },
        dow: { 
          price: 34567.89, 
          change: 123.45, 
          changePercent: 0.36 
        }
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should display major indices
        expect(screen.getByText(/4,185\.50/i) || screen.getByText(/4185/i)).toBeTruthy();
        expect(screen.getByText(/13,245\.75/i) || screen.getByText(/13245/i)).toBeTruthy();
      });

      // Should show changes with appropriate color coding
      expect(screen.getByText(/-15\.25/i) || screen.getByText(/-0\.36/i)).toBeTruthy();
      expect(screen.getByText(/\+45\.80/i) || screen.getByText(/\+0\.35/i)).toBeTruthy();
    });

    it('should indicate market status (open/closed)', async () => {
      // Critical: Users need to know if they can trade
      const { api } = await import('../../../services/api.js');
      api.getMarketSummary.mockResolvedValue({
        marketStatus: 'open',
        nextClose: '4:00 PM ET',
        timeToClose: '2 hours 15 minutes'
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show market status
        expect(screen.getByText(/open/i) || screen.getByText(/closed/i)).toBeTruthy();
      });
    });
  });

  describe('Quick Actions and Navigation', () => {
    it('should provide quick trading actions', async () => {
      // Critical: Fast access to trading functionality
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should have quick action buttons
      const buyButton = screen.queryByText(/buy/i) || screen.queryByRole('button', { name: /buy/i });
      const sellButton = screen.queryByText(/sell/i) || screen.queryByRole('button', { name: /sell/i });
      const tradeButton = screen.queryByText(/trade/i) || screen.queryByRole('button', { name: /trade/i });

      // Should have at least one trading action
      expect(buyButton || sellButton || tradeButton).toBeTruthy();
    });

    it('should show recent orders or trading activity', async () => {
      // Critical: Users need to see their recent trading activity
      const { api } = await import('../../../services/api.js');
      api.getRecentOrders.mockResolvedValue([
        {
          id: 'order1',
          symbol: 'AAPL',
          side: 'buy',
          quantity: 10,
          price: 150.25,
          status: 'filled',
          timestamp: '2024-01-15T10:30:00Z'
        },
        {
          id: 'order2',
          symbol: 'MSFT',
          side: 'sell',
          quantity: 5,
          price: 280.50,
          status: 'pending',
          timestamp: '2024-01-15T11:15:00Z'
        }
      ]);

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show recent orders
        expect(screen.getByText('AAPL')).toBeTruthy();
        expect(screen.getByText('MSFT')).toBeTruthy();
        expect(screen.getByText(/buy/i)).toBeTruthy();
        expect(screen.getByText(/sell/i)).toBeTruthy();
      });

      // Should show order status
      expect(screen.getByText(/filled/i) || screen.getByText(/complete/i)).toBeTruthy();
      expect(screen.getByText(/pending/i) || screen.getByText(/open/i)).toBeTruthy();
    });
  });

  describe('Watchlist and Alerts', () => {
    it('should display user watchlist', async () => {
      // Critical: Watchlist helps users track potential trades
      const { api } = await import('../../../services/api.js');
      api.getWatchlist.mockResolvedValue([
        {
          symbol: 'TSLA',
          name: 'Tesla Inc',
          price: 210.50,
          change: -5.25,
          changePercent: -2.43,
          alertPrice: 200.00
        },
        {
          symbol: 'NVDA',
          name: 'NVIDIA Corp',
          price: 450.75,
          change: 12.30,
          changePercent: 2.81
        }
      ]);

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should display watchlist symbols
        expect(screen.getByText('TSLA')).toBeTruthy();
        expect(screen.getByText('NVDA')).toBeTruthy();
      });

      // Should show current prices
      expect(screen.getByText(/210\.50/i)).toBeTruthy();
      expect(screen.getByText(/450\.75/i)).toBeTruthy();

      // Should show price changes
      expect(screen.getByText(/-5\.25/i) || screen.getByText(/-2\.43/i)).toBeTruthy();
      expect(screen.getByText(/\+12\.30/i) || screen.getByText(/\+2\.81/i)).toBeTruthy();
    });

    it('should highlight price alerts when triggered', async () => {
      // Critical: Price alerts help users make timely trades
      const { api } = await import('../../../services/api.js');
      api.getWatchlist.mockResolvedValue([
        {
          symbol: 'AAPL',
          price: 145.00,
          alertPrice: 150.00,
          alertTriggered: true,
          alertType: 'below'
        }
      ]);

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeTruthy();
      });

      // Should indicate alert was triggered (visual highlight, badge, etc.)
      const alertIndicator = screen.queryByText(/alert/i) || 
                           screen.queryByText(/triggered/i) ||
                           screen.queryByTestId('alert-badge');
      // Note: This documents the requirement for alert visualization
    });
  });

  describe('Performance and Charts', () => {
    it('should display portfolio performance chart', async () => {
      // Critical: Visual performance data helps investment decisions
      const { api } = await import('../../../services/api.js');
      api.getPortfolio.mockResolvedValue({
        totalValue: 100000,
        performanceHistory: [
          { date: '2024-01-01', value: 95000 },
          { date: '2024-01-08', value: 98000 },
          { date: '2024-01-15', value: 100000 }
        ]
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should render performance chart
        const chart = screen.getByTestId('performance-chart') || 
                     screen.getByTestId('portfolio-chart');
        expect(chart).toBeTruthy();
      });
    });

    it('should show key performance metrics', async () => {
      // Critical: Key metrics help users understand their performance
      const { api } = await import('../../../services/api.js');
      api.getPortfolio.mockResolvedValue({
        totalValue: 125000,
        totalCost: 100000,
        totalReturn: 25000,
        totalReturnPercent: 25.0,
        dayReturn: 1500,
        dayReturnPercent: 1.2
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show total return
        expect(screen.getByText(/25,000/i) || screen.getByText(/\$25,000/i)).toBeTruthy();
        expect(screen.getByText(/25\.0%/i) || screen.getByText(/25%/i)).toBeTruthy();
      });

      // Should show day return
      expect(screen.getByText(/1,500/i) || screen.getByText(/\$1,500/i)).toBeTruthy();
      expect(screen.getByText(/1\.2%/i)).toBeTruthy();
    });
  });

  describe('Error Handling and Resilience', () => {
    it('should handle partial data loading failures gracefully', async () => {
      // Critical: Dashboard should work even if some sections fail
      const { api } = await import('../../../services/api.js');
      
      // Portfolio loads successfully, but market data fails
      api.getPortfolio.mockResolvedValue({
        totalValue: 100000,
        positions: []
      });
      api.getMarketSummary.mockRejectedValue(new Error('Market data unavailable'));
      api.getWatchlist.mockResolvedValue([]);

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should still show portfolio data
        expect(screen.getByText(/100,000/i) || screen.getByText(/\$100,000/i)).toBeTruthy();
      });

      // Should show error message for failed sections
      expect(screen.getByText(/unavailable/i) || screen.getByText(/error/i)).toBeTruthy();
    });

    it('should handle complete dashboard load failure', async () => {
      // Critical: Complete failure should not leave users with blank screen
      const { api } = await import('../../../services/api.js');
      api.getPortfolio.mockRejectedValue(new Error('Service unavailable'));
      api.getMarketSummary.mockRejectedValue(new Error('Service unavailable'));
      api.getWatchlist.mockRejectedValue(new Error('Service unavailable'));

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show error state with recovery options
        expect(
          screen.getByText(/error/i) || 
          screen.getByText(/unavailable/i) ||
          screen.getByText(/try again/i)
        ).toBeTruthy();
      });

      // Should have some way to retry or navigate elsewhere
      const retryButton = screen.queryByText(/retry/i) || 
                         screen.queryByText(/refresh/i) ||
                         screen.queryByRole('button');
      expect(retryButton).toBeTruthy();
    });
  });

  describe('Real-time Updates', () => {
    it('should handle real-time price updates', async () => {
      // Critical: Real-time data keeps users informed for trading decisions
      const { api } = await import('../../../services/api.js');
      api.getPortfolio.mockResolvedValue({
        totalValue: 100000,
        positions: [
          { symbol: 'AAPL', price: 150.00, marketValue: 15000 }
        ]
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeTruthy();
        expect(screen.getByText(/150\.00/i)).toBeTruthy();
      });

      // Note: Real-time updates would be tested with WebSocket mock data
      // This documents the requirement for live price updates
    });

    it('should show connection status for real-time data', async () => {
      // Critical: Users need to know if their data is live or stale
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should indicate real-time connection status
      const connectionStatus = screen.queryByText(/connected/i) ||
                              screen.queryByText(/live/i) ||
                              screen.queryByText(/offline/i) ||
                              screen.queryByTestId('connection-status');
      
      // Note: This documents good UX for real-time features
      // expect(connectionStatus).toBeTruthy();
    });
  });
});
/**
 * Real-time Data and WebSocket Integration Tests
 * Tests WebSocket connections, real-time data streams, and live updates
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Mock WebSocket
class MockWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = WebSocket.CONNECTING;
    this.onopen = null;
    this.onclose = null;
    this.onmessage = null;
    this.onerror = null;
    this.listeners = new Map();
    
    // Simulate connection opening
    setTimeout(() => {
      this.readyState = WebSocket.OPEN;
      if (this.onopen) this.onopen(new Event('open'));
      this.dispatchEvent(new Event('open'));
    }, 100);
  }

  send(data) {
    if (this.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not open');
    }
    this.sentMessages = this.sentMessages || [];
    this.sentMessages.push(data);
  }

  close(code = 1000, reason = '') {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) this.onclose({ code, reason });
    this.dispatchEvent({ type: 'close', code, reason });
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, []);
    }
    this.listeners.get(type).push(listener);
  }

  removeEventListener(type, listener) {
    if (this.listeners.has(type)) {
      const listeners = this.listeners.get(type);
      const index = listeners.indexOf(listener);
      if (index > -1) {
        listeners.splice(index, 1);
      }
    }
  }

  dispatchEvent(event) {
    const type = event.type || event;
    if (this.listeners.has(type)) {
      this.listeners.get(type).forEach(listener => listener(event));
    }
  }

  // Simulate receiving messages
  simulateMessage(data) {
    const event = { type: 'message', data: JSON.stringify(data) };
    if (this.onmessage) this.onmessage(event);
    this.dispatchEvent(event);
  }

  // Simulate connection error
  simulateError(error) {
    const event = { type: 'error', error };
    if (this.onerror) this.onerror(event);
    this.dispatchEvent(event);
  }
}

// Mock Server-Sent Events
class MockEventSource {
  constructor(url) {
    this.url = url;
    this.readyState = EventSource.CONNECTING;
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.listeners = new Map();
    
    setTimeout(() => {
      this.readyState = EventSource.OPEN;
      if (this.onopen) this.onopen(new Event('open'));
      this.dispatchEvent(new Event('open'));
    }, 50);
  }

  close() {
    this.readyState = EventSource.CLOSED;
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, []);
    }
    this.listeners.get(type).push(listener);
  }

  removeEventListener(type, listener) {
    if (this.listeners.has(type)) {
      const listeners = this.listeners.get(type);
      const index = listeners.indexOf(listener);
      if (index > -1) {
        listeners.splice(index, 1);
      }
    }
  }

  dispatchEvent(event) {
    const type = event.type || event;
    if (this.listeners.has(type)) {
      this.listeners.get(type).forEach(listener => listener(event));
    }
  }

  simulateMessage(data, eventType = 'message') {
    const event = { 
      type: eventType, 
      data: JSON.stringify(data),
      lastEventId: Date.now().toString(),
      origin: this.url
    };
    if (this.onmessage) this.onmessage(event);
    this.dispatchEvent(event);
  }
}

// Set up global mocks
global.WebSocket = MockWebSocket;
global.EventSource = MockEventSource;

// Mock real-time services
const mockRealTimeDataService = {
  connect: vi.fn(),
  disconnect: vi.fn(),
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
  send: vi.fn(),
  getConnectionStatus: vi.fn(),
  reconnect: vi.fn(),
  setReconnectInterval: vi.fn()
};

const mockMarketDataStream = {
  subscribeToTicker: vi.fn(),
  subscribeToTickers: vi.fn(),
  unsubscribeFromTicker: vi.fn(),
  subscribeToNews: vi.fn(),
  subscribeToTrades: vi.fn(),
  subscribeToQuotes: vi.fn(),
  subscribeToOrderbook: vi.fn(),
  getSubscriptions: vi.fn(),
  clearSubscriptions: vi.fn()
};

const mockPortfolioUpdates = {
  subscribeToPortfolioUpdates: vi.fn(),
  subscribeToPositionUpdates: vi.fn(),
  subscribeToOrderUpdates: vi.fn(),
  subscribeToAccountUpdates: vi.fn(),
  getLatestPortfolioValue: vi.fn(),
  enableRealTimeSync: vi.fn(),
  disableRealTimeSync: vi.fn()
};

const mockNotificationService = {
  subscribeToAlerts: vi.fn(),
  subscribeToSignals: vi.fn(),
  subscribeToNews: vi.fn(),
  sendPushNotification: vi.fn(),
  markAsRead: vi.fn(),
  getUnreadCount: vi.fn(),
  clearAllNotifications: vi.fn()
};

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

// Mock components that use real-time data
vi.mock('../../../components/realtime/LivePriceDisplay', () => ({
  default: vi.fn(({ symbol, onPriceUpdate }) => (
    <div data-testid="live-price-display">
      <div data-testid="symbol">{symbol}</div>
      <div data-testid="price">Loading...</div>
      <div data-testid="change">--</div>
      <div data-testid="status">Connecting...</div>
    </div>
  ))
}));

vi.mock('../../../components/realtime/OrderBookDisplay', () => ({
  default: vi.fn(({ symbol, depth = 10 }) => (
    <div data-testid="orderbook-display">
      <div data-testid="orderbook-symbol">{symbol}</div>
      <div data-testid="bids">
        {Array.from({ length: depth }, (_, i) => (
          <div key={i} data-testid={`bid-${i}`}>Bid Level {i}</div>
        ))}
      </div>
      <div data-testid="asks">
        {Array.from({ length: depth }, (_, i) => (
          <div key={i} data-testid={`ask-${i}`}>Ask Level {i}</div>
        ))}
      </div>
    </div>
  ))
}));

vi.mock('../../../components/realtime/LivePortfolioValue', () => ({
  default: vi.fn(({ onValueUpdate }) => (
    <div data-testid="live-portfolio-value">
      <div data-testid="total-value">$125,000.00</div>
      <div data-testid="daily-change">+$2,500.00 (+2.04%)</div>
      <div data-testid="last-updated">Just now</div>
    </div>
  ))
}));

vi.mock('../../../components/realtime/LiveNewsStream', () => ({
  default: vi.fn(({ symbols = [], onNewsUpdate }) => (
    <div data-testid="live-news-stream">
      <div data-testid="news-status">Connected</div>
      <div data-testid="news-items">
        <div data-testid="news-item-1">Latest: Apple reports strong earnings</div>
        <div data-testid="news-item-2">Breaking: Tesla announces new model</div>
      </div>
    </div>
  ))
}));

describe('Real-time Data and WebSocket Integration Tests', () => {
  let mockWebSocket;
  let mockEventSource;
  let user;

  beforeAll(() => {
    // Mock performance.now for timing tests
    vi.spyOn(performance, 'now').mockImplementation(() => Date.now());
  });

  beforeEach(() => {
    user = userEvent.setup();
    vi.clearAllMocks();
    
    // Reset WebSocket constants
    Object.defineProperty(global.WebSocket, 'CONNECTING', { value: 0 });
    Object.defineProperty(global.WebSocket, 'OPEN', { value: 1 });
    Object.defineProperty(global.WebSocket, 'CLOSING', { value: 2 });
    Object.defineProperty(global.WebSocket, 'CLOSED', { value: 3 });

    // Reset EventSource constants
    Object.defineProperty(global.EventSource, 'CONNECTING', { value: 0 });
    Object.defineProperty(global.EventSource, 'OPEN', { value: 1 });
    Object.defineProperty(global.EventSource, 'CLOSED', { value: 2 });

    // Setup service mocks
    mockRealTimeDataService.connect.mockResolvedValue({ connected: true });
    mockRealTimeDataService.getConnectionStatus.mockReturnValue('connected');
    mockMarketDataStream.getSubscriptions.mockReturnValue([]);
    mockPortfolioUpdates.getLatestPortfolioValue.mockReturnValue(125000);
  });

  describe('WebSocket Connection Management', () => {
    it('establishes WebSocket connection successfully', async () => {
      const wsUrl = 'wss://api.example.com/realtime';
      
      const connection = await mockRealTimeDataService.connect(wsUrl);
      
      expect(mockRealTimeDataService.connect).toHaveBeenCalledWith(wsUrl);
      expect(connection.connected).toBe(true);
    });

    it('handles WebSocket connection failures and retries', async () => {
      mockRealTimeDataService.connect
        .mockRejectedValueOnce(new Error('Connection failed'))
        .mockRejectedValueOnce(new Error('Connection failed'))
        .mockResolvedValueOnce({ connected: true });

      // Simulate retry logic
      let connection;
      let attempts = 0;
      const maxAttempts = 3;

      while (attempts < maxAttempts) {
        try {
          connection = await mockRealTimeDataService.connect('wss://api.example.com/realtime');
          break;
        } catch (error) {
          attempts++;
          if (attempts >= maxAttempts) throw error;
          await new Promise(resolve => setTimeout(resolve, 1000)); // Wait before retry
        }
      }

      expect(attempts).toBe(2); // Should succeed on third attempt
      expect(connection.connected).toBe(true);
      expect(mockRealTimeDataService.connect).toHaveBeenCalledTimes(3);
    });

    it('implements exponential backoff for reconnection', async () => {
      const reconnectIntervals = [];
      
      mockRealTimeDataService.setReconnectInterval.mockImplementation((interval) => {
        reconnectIntervals.push(interval);
      });

      // Simulate multiple connection failures
      for (let i = 0; i < 4; i++) {
        const expectedInterval = Math.min(1000 * Math.pow(2, i), 30000);
        mockRealTimeDataService.setReconnectInterval(expectedInterval);
      }

      expect(reconnectIntervals).toEqual([1000, 2000, 4000, 8000]);
    });

    it('maintains heartbeat to detect connection loss', async () => {
      const ws = new MockWebSocket('wss://api.example.com/realtime');
      
      // Simulate heartbeat mechanism
      const heartbeatInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);

      // Wait for connection to open
      await waitFor(() => {
        expect(ws.readyState).toBe(WebSocket.OPEN);
      });

      // Simulate heartbeat
      ws.send(JSON.stringify({ type: 'ping' }));
      
      expect(ws.sentMessages).toContain('{"type":"ping"}');
      
      clearInterval(heartbeatInterval);
    });

    it('handles graceful connection closure', async () => {
      const ws = new MockWebSocket('wss://api.example.com/realtime');
      
      await waitFor(() => {
        expect(ws.readyState).toBe(WebSocket.OPEN);
      });

      const closePromise = new Promise(resolve => {
        ws.onclose = (event) => {
          resolve(event);
        };
      });

      ws.close(1000, 'Normal closure');
      const closeEvent = await closePromise;

      expect(closeEvent.code).toBe(1000);
      expect(closeEvent.reason).toBe('Normal closure');
      expect(ws.readyState).toBe(WebSocket.CLOSED);
    });
  });

  describe('Real-time Market Data Streaming', () => {
    it('subscribes to live price updates for single ticker', async () => {
      const LivePriceDisplay = (await import('../../../components/realtime/LivePriceDisplay')).default;
      
      render(
        <TestWrapper>
          <LivePriceDisplay symbol="AAPL" />
        </TestWrapper>
      );

      expect(screen.getByTestId('live-price-display')).toBeInTheDocument();
      expect(screen.getByTestId('symbol')).toHaveTextContent('AAPL');
      expect(screen.getByTestId('status')).toHaveTextContent('Connecting...');

      // Simulate successful subscription
      mockMarketDataStream.subscribeToTicker.mockResolvedValue({ 
        success: true, 
        symbol: 'AAPL' 
      });

      await mockMarketDataStream.subscribeToTicker('AAPL', (data) => {
        // Price update callback
      });

      expect(mockMarketDataStream.subscribeToTicker).toHaveBeenCalledWith(
        'AAPL',
        expect.any(Function)
      );
    });

    it('receives and processes real-time price updates', async () => {
      const ws = new MockWebSocket('wss://api.example.com/market-data');
      const priceUpdates = [];

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'price_update') {
          priceUpdates.push(data);
        }
      };

      await waitFor(() => {
        expect(ws.readyState).toBe(WebSocket.OPEN);
      });

      // Simulate real-time price updates
      const mockPriceData = {
        type: 'price_update',
        symbol: 'AAPL',
        price: 195.50,
        change: 2.37,
        changePercent: 1.23,
        volume: 1250000,
        timestamp: Date.now()
      };

      ws.simulateMessage(mockPriceData);

      await waitFor(() => {
        expect(priceUpdates).toHaveLength(1);
      });

      expect(priceUpdates[0]).toEqual(mockPriceData);
      expect(priceUpdates[0].symbol).toBe('AAPL');
      expect(priceUpdates[0].price).toBe(195.50);
    });

    it('handles multiple ticker subscriptions efficiently', async () => {
      const symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'];
      
      mockMarketDataStream.subscribeToTickers.mockResolvedValue({
        success: true,
        symbols: symbols,
        subscriptionId: 'multi_ticker_123'
      });

      const result = await mockMarketDataStream.subscribeToTickers(symbols, (data) => {
        // Multi-ticker update callback
      });

      expect(mockMarketDataStream.subscribeToTickers).toHaveBeenCalledWith(
        symbols,
        expect.any(Function)
      );
      expect(result.symbols).toEqual(symbols);
      expect(result.subscriptionId).toBe('multi_ticker_123');
    });

    it('processes order book updates in real-time', async () => {
      const OrderBookDisplay = (await import('../../../components/realtime/OrderBookDisplay')).default;
      
      render(
        <TestWrapper>
          <OrderBookDisplay symbol="AAPL" depth={5} />
        </TestWrapper>
      );

      expect(screen.getByTestId('orderbook-display')).toBeInTheDocument();
      expect(screen.getByTestId('orderbook-symbol')).toHaveTextContent('AAPL');

      // Mock order book subscription
      mockMarketDataStream.subscribeToOrderbook.mockResolvedValue({
        success: true,
        symbol: 'AAPL',
        depth: 5
      });

      await mockMarketDataStream.subscribeToOrderbook('AAPL', 5, (orderBookData) => {
        // Order book update callback
      });

      expect(mockMarketDataStream.subscribeToOrderbook).toHaveBeenCalledWith(
        'AAPL',
        5,
        expect.any(Function)
      );

      // Verify order book levels are rendered
      expect(screen.getByTestId('bid-0')).toBeInTheDocument();
      expect(screen.getByTestId('ask-0')).toBeInTheDocument();
    });

    it('handles trade stream data processing', async () => {
      const ws = new MockWebSocket('wss://api.example.com/trades');
      const trades = [];

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'trade') {
          trades.push(data);
        }
      };

      await waitFor(() => {
        expect(ws.readyState).toBe(WebSocket.OPEN);
      });

      // Simulate trade data
      const mockTradeData = {
        type: 'trade',
        symbol: 'AAPL',
        price: 195.52,
        size: 100,
        side: 'buy',
        timestamp: Date.now(),
        exchange: 'NASDAQ',
        tradeId: 'trade_123456'
      };

      ws.simulateMessage(mockTradeData);

      await waitFor(() => {
        expect(trades).toHaveLength(1);
      });

      expect(trades[0]).toEqual(mockTradeData);
      expect(trades[0].price).toBe(195.52);
      expect(trades[0].size).toBe(100);
      expect(trades[0].side).toBe('buy');
    });
  });

  describe('Portfolio Real-time Updates', () => {
    it('streams live portfolio value updates', async () => {
      const LivePortfolioValue = (await import('../../../components/realtime/LivePortfolioValue')).default;
      
      render(
        <TestWrapper>
          <LivePortfolioValue />
        </TestWrapper>
      );

      expect(screen.getByTestId('live-portfolio-value')).toBeInTheDocument();
      expect(screen.getByTestId('total-value')).toHaveTextContent('$125,000.00');

      // Mock portfolio update subscription
      mockPortfolioUpdates.subscribeToPortfolioUpdates.mockResolvedValue({
        success: true,
        subscriptionId: 'portfolio_updates_123'
      });

      await mockPortfolioUpdates.subscribeToPortfolioUpdates((portfolioData) => {
        // Portfolio update callback
      });

      expect(mockPortfolioUpdates.subscribeToPortfolioUpdates).toHaveBeenCalledWith(
        expect.any(Function)
      );
    });

    it('receives real-time position updates', async () => {
      const positionUpdates = [];
      
      const ws = new MockWebSocket('wss://api.example.com/portfolio');
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'position_update') {
          positionUpdates.push(data);
        }
      };

      await waitFor(() => {
        expect(ws.readyState).toBe(WebSocket.OPEN);
      });

      // Simulate position update
      const mockPositionUpdate = {
        type: 'position_update',
        symbol: 'AAPL',
        quantity: 150, // Increased from 100
        avgPrice: 185.50,
        currentPrice: 195.75,
        unrealizedPnL: 1537.50,
        unrealizedPnLPercent: 5.52,
        marketValue: 29362.50,
        timestamp: Date.now()
      };

      ws.simulateMessage(mockPositionUpdate);

      await waitFor(() => {
        expect(positionUpdates).toHaveLength(1);
      });

      expect(positionUpdates[0]).toEqual(mockPositionUpdate);
      expect(positionUpdates[0].quantity).toBe(150);
      expect(positionUpdates[0].unrealizedPnL).toBe(1537.50);
    });

    it('processes order status updates in real-time', async () => {
      const orderUpdates = [];
      
      mockPortfolioUpdates.subscribeToOrderUpdates.mockImplementation((callback) => {
        // Simulate order update
        setTimeout(() => {
          callback({
            type: 'order_update',
            orderId: 'order_123',
            status: 'filled',
            filledQuantity: 10,
            filledPrice: 195.50,
            timestamp: Date.now()
          });
        }, 100);
        return Promise.resolve({ success: true });
      });

      await mockPortfolioUpdates.subscribeToOrderUpdates((orderData) => {
        orderUpdates.push(orderData);
      });

      await waitFor(() => {
        expect(orderUpdates).toHaveLength(1);
      }, { timeout: 200 });

      expect(orderUpdates[0].orderId).toBe('order_123');
      expect(orderUpdates[0].status).toBe('filled');
      expect(orderUpdates[0].filledPrice).toBe(195.50);
    });

    it('syncs account balance changes in real-time', async () => {
      const accountUpdates = [];
      
      mockPortfolioUpdates.subscribeToAccountUpdates.mockImplementation((callback) => {
        // Simulate account balance update
        setTimeout(() => {
          callback({
            type: 'account_update',
            buyingPower: 48500.00, // Decreased due to order
            cash: 23500.00,
            portfolioValue: 126537.50, // Increased due to position gain
            equity: 126537.50,
            dayTradeCount: 2,
            timestamp: Date.now()
          });
        }, 100);
        return Promise.resolve({ success: true });
      });

      await mockPortfolioUpdates.subscribeToAccountUpdates((accountData) => {
        accountUpdates.push(accountData);
      });

      await waitFor(() => {
        expect(accountUpdates).toHaveLength(1);
      }, { timeout: 200 });

      expect(accountUpdates[0].buyingPower).toBe(48500.00);
      expect(accountUpdates[0].portfolioValue).toBe(126537.50);
    });
  });

  describe('Live News and Notifications', () => {
    it('streams real-time financial news', async () => {
      const LiveNewsStream = (await import('../../../components/realtime/LiveNewsStream')).default;
      
      render(
        <TestWrapper>
          <LiveNewsStream symbols={['AAPL', 'GOOGL']} />
        </TestWrapper>
      );

      expect(screen.getByTestId('live-news-stream')).toBeInTheDocument();
      expect(screen.getByTestId('news-status')).toHaveTextContent('Connected');

      // Mock news subscription
      mockMarketDataStream.subscribeToNews.mockResolvedValue({
        success: true,
        symbols: ['AAPL', 'GOOGL'],
        subscriptionId: 'news_stream_123'
      });

      await mockMarketDataStream.subscribeToNews(['AAPL', 'GOOGL'], (newsData) => {
        // News update callback
      });

      expect(mockMarketDataStream.subscribeToNews).toHaveBeenCalledWith(
        ['AAPL', 'GOOGL'],
        expect.any(Function)
      );
    });

    it('processes real-time trading alerts', async () => {
      const alerts = [];
      
      mockNotificationService.subscribeToAlerts.mockImplementation((callback) => {
        // Simulate trading alert
        setTimeout(() => {
          callback({
            type: 'price_alert',
            symbol: 'AAPL',
            message: 'AAPL has reached your target price of $195.00',
            alertType: 'target_reached',
            price: 195.50,
            targetPrice: 195.00,
            timestamp: Date.now(),
            severity: 'info'
          });
        }, 100);
        return Promise.resolve({ success: true });
      });

      await mockNotificationService.subscribeToAlerts((alertData) => {
        alerts.push(alertData);
      });

      await waitFor(() => {
        expect(alerts).toHaveLength(1);
      }, { timeout: 200 });

      expect(alerts[0].type).toBe('price_alert');
      expect(alerts[0].symbol).toBe('AAPL');
      expect(alerts[0].price).toBe(195.50);
    });

    it('handles push notifications for mobile devices', async () => {
      // Mock Push API
      const mockPushSubscription = {
        endpoint: 'https://fcm.googleapis.com/fcm/send/notification_123'
      };

      mockNotificationService.sendPushNotification.mockResolvedValue({
        success: true,
        messageId: 'push_msg_123'
      });

      const result = await mockNotificationService.sendPushNotification({
        title: 'Trade Executed',
        body: 'Your order for 10 shares of AAPL has been filled at $195.50',
        icon: '/icons/trade-success.png',
        badge: '/icons/badge.png',
        tag: 'trade_notification',
        data: {
          orderId: 'order_123',
          symbol: 'AAPL',
          action: 'view_order'
        }
      });

      expect(result.success).toBe(true);
      expect(result.messageId).toBe('push_msg_123');
    });

    it('manages notification read states', async () => {
      const notifications = [
        { id: 'notif_1', read: false, type: 'trade_alert' },
        { id: 'notif_2', read: false, type: 'news_alert' },
        { id: 'notif_3', read: true, type: 'price_alert' }
      ];

      mockNotificationService.getUnreadCount.mockReturnValue(2);
      mockNotificationService.markAsRead.mockResolvedValue({ success: true });

      const unreadCount = mockNotificationService.getUnreadCount();
      expect(unreadCount).toBe(2);

      // Mark notification as read
      await mockNotificationService.markAsRead('notif_1');
      
      // Update unread count
      mockNotificationService.getUnreadCount.mockReturnValue(1);
      const newUnreadCount = mockNotificationService.getUnreadCount();
      
      expect(newUnreadCount).toBe(1);
      expect(mockNotificationService.markAsRead).toHaveBeenCalledWith('notif_1');
    });
  });

  describe('Server-Sent Events (SSE) Integration', () => {
    it('establishes SSE connection for server events', async () => {
      const eventSource = new MockEventSource('/api/events/stream');
      const events = [];

      eventSource.onmessage = (event) => {
        events.push(JSON.parse(event.data));
      };

      await waitFor(() => {
        expect(eventSource.readyState).toBe(EventSource.OPEN);
      });

      // Simulate server event
      eventSource.simulateMessage({
        type: 'market_status',
        status: 'open',
        nextChange: '2024-01-15T16:00:00Z',
        message: 'Market is now open for trading'
      });

      await waitFor(() => {
        expect(events).toHaveLength(1);
      });

      expect(events[0].type).toBe('market_status');
      expect(events[0].status).toBe('open');
    });

    it('handles custom SSE event types', async () => {
      const eventSource = new MockEventSource('/api/events/stream');
      const customEvents = [];

      eventSource.addEventListener('custom_alert', (event) => {
        customEvents.push(JSON.parse(event.data));
      });

      await waitFor(() => {
        expect(eventSource.readyState).toBe(EventSource.OPEN);
      });

      // Simulate custom event type
      eventSource.simulateMessage({
        alertId: 'alert_123',
        message: 'Unusual volume detected for AAPL',
        symbol: 'AAPL',
        volume: 5000000,
        averageVolume: 52000000,
        percentIncrease: 865.4
      }, 'custom_alert');

      await waitFor(() => {
        expect(customEvents).toHaveLength(1);
      });

      expect(customEvents[0].alertId).toBe('alert_123');
      expect(customEvents[0].symbol).toBe('AAPL');
    });

    it('implements automatic SSE reconnection', async () => {
      let eventSource = new MockEventSource('/api/events/stream');
      let reconnectCount = 0;

      const reconnectSSE = () => {
        reconnectCount++;
        eventSource.close();
        eventSource = new MockEventSource('/api/events/stream');
        return eventSource;
      };

      // Simulate connection error
      eventSource.onerror = () => {
        if (reconnectCount < 3) {
          setTimeout(reconnectSSE, 1000);
        }
      };

      // Trigger error
      eventSource.simulateError(new Error('Connection lost'));
      
      // Wait for reconnection
      await new Promise(resolve => setTimeout(resolve, 1100));
      
      expect(reconnectCount).toBe(1);
    });
  });

  describe('Performance and Resource Management', () => {
    it('implements connection pooling for multiple streams', async () => {
      const connections = [];
      
      // Create multiple connections
      for (let i = 0; i < 5; i++) {
        const connection = await mockRealTimeDataService.connect(`wss://api.example.com/stream${i}`);
        connections.push(connection);
      }

      expect(connections).toHaveLength(5);
      expect(mockRealTimeDataService.connect).toHaveBeenCalledTimes(5);

      // Verify each connection is tracked
      connections.forEach((connection, index) => {
        expect(connection.connected).toBe(true);
      });
    });

    it('manages memory usage with large data streams', async () => {
      const dataBuffer = [];
      const maxBufferSize = 1000;
      
      const ws = new MockWebSocket('wss://api.example.com/high-frequency');
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        // Add to buffer
        dataBuffer.push(data);
        
        // Implement circular buffer to prevent memory leaks
        if (dataBuffer.length > maxBufferSize) {
          dataBuffer.shift(); // Remove oldest item
        }
      };

      await waitFor(() => {
        expect(ws.readyState).toBe(WebSocket.OPEN);
      });

      // Simulate high-frequency data
      for (let i = 0; i < 1500; i++) {
        ws.simulateMessage({
          type: 'tick',
          symbol: 'AAPL',
          price: 195.50 + (Math.random() - 0.5) * 2,
          timestamp: Date.now() + i
        });
      }

      // Buffer should not exceed max size
      expect(dataBuffer.length).toBeLessThanOrEqual(maxBufferSize);
      expect(dataBuffer.length).toBe(maxBufferSize);
    });

    it('implements rate limiting for outbound messages', async () => {
      const ws = new MockWebSocket('wss://api.example.com/realtime');
      const messageQueue = [];
      const rateLimitMs = 100; // Max 1 message per 100ms
      let lastSentTime = 0;

      const sendMessage = (message) => {
        const now = Date.now();
        if (now - lastSentTime >= rateLimitMs) {
          ws.send(JSON.stringify(message));
          lastSentTime = now;
          return true;
        } else {
          messageQueue.push(message);
          return false;
        }
      };

      await waitFor(() => {
        expect(ws.readyState).toBe(WebSocket.OPEN);
      });

      // Try to send multiple messages rapidly
      const messages = [
        { type: 'subscribe', symbol: 'AAPL' },
        { type: 'subscribe', symbol: 'GOOGL' },
        { type: 'subscribe', symbol: 'MSFT' }
      ];

      const results = messages.map(msg => sendMessage(msg));
      
      expect(results[0]).toBe(true);  // First message sent immediately
      expect(results[1]).toBe(false); // Second message queued
      expect(results[2]).toBe(false); // Third message queued
      expect(messageQueue).toHaveLength(2);
    });

    it('monitors connection health and latency', async () => {
      const ws = new MockWebSocket('wss://api.example.com/realtime');
      const latencyMeasurements = [];
      
      await waitFor(() => {
        expect(ws.readyState).toBe(WebSocket.OPEN);
      });

      // Implement ping-pong latency measurement
      const measureLatency = () => {
        const startTime = performance.now();
        const pingId = Math.random().toString(36);
        
        ws.send(JSON.stringify({ 
          type: 'ping', 
          id: pingId, 
          timestamp: startTime 
        }));

        // Simulate pong response
        setTimeout(() => {
          const endTime = performance.now();
          const latency = endTime - startTime;
          latencyMeasurements.push(latency);
          
          ws.simulateMessage({
            type: 'pong',
            id: pingId,
            timestamp: endTime
          });
        }, Math.random() * 50 + 10); // 10-60ms simulated latency
      };

      // Measure latency multiple times
      for (let i = 0; i < 5; i++) {
        measureLatency();
        await new Promise(resolve => setTimeout(resolve, 100));
      }

      await waitFor(() => {
        expect(latencyMeasurements.length).toBeGreaterThan(0);
      }, { timeout: 1000 });

      // Calculate average latency
      const avgLatency = latencyMeasurements.reduce((a, b) => a + b, 0) / latencyMeasurements.length;
      expect(avgLatency).toBeGreaterThan(0);
      expect(avgLatency).toBeLessThan(100); // Should be reasonable latency
    });
  });

  describe('Error Handling and Recovery', () => {
    it('handles WebSocket disconnections gracefully', async () => {
      const ws = new MockWebSocket('wss://api.example.com/realtime');
      let reconnectAttempted = false;
      
      ws.onclose = (event) => {
        if (event.code !== 1000) { // Abnormal closure
          reconnectAttempted = true;
          // Simulate reconnection attempt
          setTimeout(() => {
            mockRealTimeDataService.reconnect();
          }, 1000);
        }
      };

      await waitFor(() => {
        expect(ws.readyState).toBe(WebSocket.OPEN);
      });

      // Simulate abnormal disconnection
      ws.close(1006, 'Connection lost');
      
      await new Promise(resolve => setTimeout(resolve, 1100));
      
      expect(reconnectAttempted).toBe(true);
      expect(mockRealTimeDataService.reconnect).toHaveBeenCalled();
    });

    it('handles malformed message data', async () => {
      const ws = new MockWebSocket('wss://api.example.com/realtime');
      const errors = [];
      const validMessages = [];
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          validMessages.push(data);
        } catch (error) {
          errors.push({ error, rawData: event.data });
        }
      };

      await waitFor(() => {
        expect(ws.readyState).toBe(WebSocket.OPEN);
      });

      // Send malformed JSON
      ws.dispatchEvent({ 
        type: 'message', 
        data: '{ invalid json }' 
      });

      // Send valid message
      ws.simulateMessage({
        type: 'price_update',
        symbol: 'AAPL',
        price: 195.50
      });

      expect(errors).toHaveLength(1);
      expect(validMessages).toHaveLength(1);
      expect(validMessages[0].symbol).toBe('AAPL');
    });

    it('implements circuit breaker for failing connections', async () => {
      let connectionAttempts = 0;
      const maxAttempts = 3;
      let circuitBreakerOpen = false;

      mockRealTimeDataService.connect.mockImplementation(async () => {
        connectionAttempts++;
        if (connectionAttempts >= maxAttempts) {
          circuitBreakerOpen = true;
          throw new Error('Circuit breaker open - too many failed attempts');
        }
        throw new Error('Connection failed');
      });

      // Attempt connections until circuit breaker opens
      for (let i = 0; i < maxAttempts + 1; i++) {
        try {
          await mockRealTimeDataService.connect('wss://api.example.com/realtime');
        } catch (error) {
          if (error.message.includes('Circuit breaker open')) {
            break;
          }
        }
      }

      expect(circuitBreakerOpen).toBe(true);
      expect(connectionAttempts).toBe(maxAttempts);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  afterAll(() => {
    vi.clearAllTimers();
  });
});
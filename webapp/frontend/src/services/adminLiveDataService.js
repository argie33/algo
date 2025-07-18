import { getApiConfig } from './api';

/**
 * Admin Live Data Service
 * 
 * Handles all administrative operations for live data feeds:
 * - Feed management (start/stop/configure)
 * - Symbol management (add/remove/monitor)
 * - Performance monitoring and metrics
 * - Cost tracking and usage analytics
 * - Customer data distribution
 */

class AdminLiveDataService {
  constructor() {
    this.apiUrl = getApiConfig().apiUrl;
    this.wsConnection = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    this.eventListeners = new Map();
    
    // Cache for performance
    this.metricsCache = {
      data: null,
      lastUpdate: null,
      ttl: 5000 // 5 seconds
    };
  }

  /**
   * WebSocket Management
   */
  async connectWebSocket() {
    try {
      // Get WebSocket URL from config
      const wsUrl = this.getWebSocketUrl();
      
      this.wsConnection = new WebSocket(wsUrl);
      
      this.wsConnection.onopen = () => {
        console.log('🔌 Admin WebSocket connected');
        this.reconnectAttempts = 0;
        this.emit('connected');
        
        // Send admin authentication
        this.sendMessage({
          type: 'admin_auth',
          timestamp: new Date().toISOString()
        });
      };

      this.wsConnection.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.handleWebSocketMessage(message);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      this.wsConnection.onclose = (event) => {
        console.log('🔌 Admin WebSocket disconnected:', event.code, event.reason);
        this.emit('disconnected');
        
        // Attempt to reconnect if not manual disconnect
        if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          setTimeout(() => {
            console.log(`🔄 Reconnecting WebSocket (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
            this.connectWebSocket();
          }, this.reconnectDelay * this.reconnectAttempts);
        }
      };

      this.wsConnection.onerror = (error) => {
        console.error('❌ Admin WebSocket error:', error);
        this.emit('error', error);
      };

    } catch (error) {
      console.error('Failed to connect admin WebSocket:', error);
      throw error;
    }
  }

  disconnectWebSocket() {
    if (this.wsConnection) {
      this.wsConnection.close(1000, 'Manual disconnect');
      this.wsConnection = null;
    }
  }

  sendMessage(message) {
    if (this.wsConnection && this.wsConnection.readyState === WebSocket.OPEN) {
      this.wsConnection.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, cannot send message');
    }
  }

  handleWebSocketMessage(message) {
    switch (message.type) {
      case 'admin_auth_success':
        console.log('✅ Admin authentication successful');
        this.emit('authenticated');
        break;
      
      case 'feed_started':
        console.log('🚀 Feed started:', message.feedId);
        this.emit('feed_started', message);
        break;
      
      case 'feed_stopped':
        console.log('⏹️ Feed stopped:', message.feedId);
        this.emit('feed_stopped', message);
        break;
      
      case 'feed_data':
        this.emit('feed_data', message);
        break;
      
      case 'metrics_update':
        this.emit('metrics_update', message.metrics);
        break;
      
      case 'subscriber_update':
        this.emit('subscriber_update', message);
        break;
      
      default:
        console.log('Unknown admin message type:', message.type);
    }
  }

  getWebSocketUrl() {
    // Try to get from runtime config first
    if (window.__CONFIG__?.ADMIN_WS_URL) {
      return window.__CONFIG__.ADMIN_WS_URL;
    }
    
    // Fallback to main WebSocket URL with admin flag
    if (window.__CONFIG__?.WS_URL) {
      return window.__CONFIG__.WS_URL + '?admin=true';
    }
    
    // Default admin WebSocket URL
    return 'wss://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev?admin=true';
  }

  /**
   * System Metrics
   */
  async getSystemMetrics() {
    // Check cache first
    if (this.metricsCache.data && 
        this.metricsCache.lastUpdate && 
        Date.now() - this.metricsCache.lastUpdate < this.metricsCache.ttl) {
      return this.metricsCache.data;
    }

    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/metrics`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const metrics = await response.json();
      
      // Cache the metrics
      this.metricsCache.data = metrics;
      this.metricsCache.lastUpdate = Date.now();
      
      return metrics;
    } catch (error) {
      console.error('Failed to get system metrics:', error);
      throw error;
    }
  }

  /**
   * Feed Management
   */
  async getActiveFeeds() {
    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/feeds`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to get active feeds:', error);
      
      // Return mock data for development
      return [
        {
          id: 'feed-1',
          assetType: 'stocks',
          dataTypes: ['trades', 'quotes', 'bars'],
          symbols: ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'],
          status: 'running',
          subscriberCount: 8,
          messagesPerSecond: 150,
          createdAt: new Date().toISOString(),
          lastUpdate: new Date().toISOString()
        },
        {
          id: 'feed-2',
          assetType: 'crypto',
          dataTypes: ['trades', 'quotes'],
          symbols: ['BTC/USD', 'ETH/USD', 'LTC/USD'],
          status: 'running',
          subscriberCount: 5,
          messagesPerSecond: 80,
          createdAt: new Date().toISOString(),
          lastUpdate: new Date().toISOString()
        }
      ];
    }
  }

  async startFeed(feedConfig) {
    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/feeds`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        },
        body: JSON.stringify(feedConfig)
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      
      // Also send via WebSocket for real-time updates
      this.sendMessage({
        type: 'start_feed',
        config: feedConfig,
        timestamp: new Date().toISOString()
      });

      return result;
    } catch (error) {
      console.error('Failed to start feed:', error);
      throw error;
    }
  }

  async stopFeed(feedId) {
    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/feeds/${feedId}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // Also send via WebSocket for real-time updates
      this.sendMessage({
        type: 'stop_feed',
        feedId: feedId,
        timestamp: new Date().toISOString()
      });

      return await response.json();
    } catch (error) {
      console.error('Failed to stop feed:', error);
      throw error;
    }
  }

  async addSymbol(feedId, symbol) {
    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/feeds/${feedId}/symbols`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        },
        body: JSON.stringify({ symbol })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // Send via WebSocket for real-time updates
      this.sendMessage({
        type: 'add_symbol',
        feedId: feedId,
        symbol: symbol,
        timestamp: new Date().toISOString()
      });

      return await response.json();
    } catch (error) {
      console.error('Failed to add symbol:', error);
      throw error;
    }
  }

  async removeSymbol(feedId, symbol) {
    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/feeds/${feedId}/symbols/${symbol}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // Send via WebSocket for real-time updates
      this.sendMessage({
        type: 'remove_symbol',
        feedId: feedId,
        symbol: symbol,
        timestamp: new Date().toISOString()
      });

      return await response.json();
    } catch (error) {
      console.error('Failed to remove symbol:', error);
      throw error;
    }
  }

  /**
   * Subscriber Management
   */
  async getSubscribers() {
    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/subscribers`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to get subscribers:', error);
      
      // Return mock data for development
      return [
        {
          userId: 'user-1',
          userEmail: 'trader1@example.com',
          subscribedSymbols: ['AAPL', 'MSFT', 'GOOGL'],
          connectedSince: new Date(Date.now() - 3600000).toISOString(),
          messagesReceived: 1250,
          status: 'active'
        },
        {
          userId: 'user-2', 
          userEmail: 'trader2@example.com',
          subscribedSymbols: ['TSLA', 'NVDA', 'BTC/USD'],
          connectedSince: new Date(Date.now() - 7200000).toISOString(),
          messagesReceived: 890,
          status: 'active'
        }
      ];
    }
  }

  /**
   * Symbol Search and Management
   */
  async searchSymbols(query, assetType = 'stocks') {
    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/symbols/search?q=${encodeURIComponent(query)}&type=${assetType}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to search symbols:', error);
      
      // Return mock search results
      const mockResults = {
        stocks: [
          { symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ' },
          { symbol: 'MSFT', name: 'Microsoft Corporation', exchange: 'NASDAQ' },
          { symbol: 'GOOGL', name: 'Alphabet Inc.', exchange: 'NASDAQ' }
        ],
        crypto: [
          { symbol: 'BTC/USD', name: 'Bitcoin', exchange: 'CRYPTO' },
          { symbol: 'ETH/USD', name: 'Ethereum', exchange: 'CRYPTO' }
        ]
      };
      
      return mockResults[assetType] || [];
    }
  }

  /**
   * Performance Analytics
   */
  async getPerformanceMetrics(timeRange = '24h') {
    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/performance?range=${timeRange}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to get performance metrics:', error);
      
      // Return mock performance data
      return {
        timeRange: timeRange,
        metrics: {
          averageLatency: 15,
          maxLatency: 45,
          throughput: 450,
          errorRate: 0.1,
          uptime: 99.8,
          dataPoints: Array.from({ length: 24 }, (_, i) => ({
            timestamp: new Date(Date.now() - (23 - i) * 3600000).toISOString(),
            latency: Math.random() * 30 + 10,
            throughput: Math.random() * 200 + 350,
            errors: Math.random() * 5
          }))
        }
      };
    }
  }

  /**
   * Cost Analytics
   */
  async getCostAnalytics(timeRange = '30d') {
    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/costs?range=${timeRange}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to get cost analytics:', error);
      
      // Return mock cost data
      return {
        timeRange: timeRange,
        totalCost: 1250,
        costSavings: 2850,
        breakdown: {
          alpaca: { cost: 800, requests: 1500000 },
          polygon: { cost: 300, requests: 800000 },
          finnhub: { cost: 150, requests: 400000 }
        },
        trends: Array.from({ length: 30 }, (_, i) => ({
          date: new Date(Date.now() - (29 - i) * 86400000).toISOString().split('T')[0],
          cost: Math.random() * 60 + 20,
          requests: Math.random() * 100000 + 50000
        }))
      };
    }
  }

  /**
   * Feed Configuration
   */
  async saveFeedConfiguration(config) {
    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/config`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        },
        body: JSON.stringify(config)
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to save feed configuration:', error);
      throw error;
    }
  }

  async loadFeedConfiguration() {
    try {
      const response = await fetch(`${this.apiUrl}/admin/live-data/config`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('authToken')}`
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to load feed configuration:', error);
      return null;
    }
  }

  /**
   * Event Management
   */
  on(event, callback) {
    if (!this.eventListeners.has(event)) {
      this.eventListeners.set(event, []);
    }
    this.eventListeners.get(event).push(callback);
  }

  off(event, callback) {
    if (this.eventListeners.has(event)) {
      const callbacks = this.eventListeners.get(event);
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    }
  }

  emit(event, data) {
    if (this.eventListeners.has(event)) {
      this.eventListeners.get(event).forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error('Error in event callback:', error);
        }
      });
    }
  }

  /**
   * Utilities
   */
  formatPrice(price) {
    if (typeof price !== 'number') return 'N/A';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 4
    }).format(price);
  }

  formatNumber(num) {
    if (typeof num !== 'number') return 'N/A';
    return new Intl.NumberFormat('en-US').format(num);
  }

  formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }
}

// Export singleton instance
const adminLiveDataService = new AdminLiveDataService();
export default adminLiveDataService;
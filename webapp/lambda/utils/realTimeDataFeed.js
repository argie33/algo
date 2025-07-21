const { query } = require('./database');
const EventEmitter = require('events');

class RealTimeDataFeed extends EventEmitter {
  constructor() {
    super();
    this.connections = new Map();
    this.subscriptions = new Map();
    this.dataUpdateInterval = null;
    this.isRunning = false;
    this.updateFrequency = 1000; // 1 second for real-time streaming
    this.dataTypes = {
      MARKET_OVERVIEW: 'market_overview',
      PORTFOLIO: 'portfolio',
      WATCHLIST: 'watchlist',
      ALERTS: 'alerts',
      ECONOMIC: 'economic',
      PATTERNS: 'patterns',
      SENTIMENT: 'sentiment',
      RISK_METRICS: 'risk_metrics',
      LIVE_QUOTES: 'live_quotes',
      LIVE_TRADES: 'live_trades'
    };
    
    // Enhanced real-time capabilities
    this.alpacaConnections = new Map(); // userId -> AlpacaService
    this.liveDataCache = new Map(); // symbol -> latest data
    this.streamingActive = false;
  }

  start() {
    if (this.isRunning) return;
    
    this.isRunning = true;
    console.log('🔴 Starting real-time data feed...');
    
    // Start data update cycle
    this.dataUpdateInterval = setInterval(() => {
      this.updateAllDataFeeds();
    }, this.updateFrequency);
    
    // Emit startup event
    this.emit('started');
  }

  stop() {
    if (!this.isRunning) return;
    
    this.isRunning = false;
    console.log('🟡 Stopping real-time data feed...');
    
    if (this.dataUpdateInterval) {
      clearInterval(this.dataUpdateInterval);
      this.dataUpdateInterval = null;
    }
    
    // Clean up connections
    this.connections.clear();
    this.subscriptions.clear();
    
    // Clean up alpaca connections and cache
    this.alpacaConnections.clear();
    this.liveDataCache.clear();
    this.streamingActive = false;
    
    this.emit('stopped');
  }

  /**
   * Complete cleanup of all resources
   */
  cleanup() {
    this.stop();
    
    // Remove all listeners to prevent memory leaks
    this.removeAllListeners();
    
    // Clear all references
    this.connections.clear();
    this.subscriptions.clear();
    this.alpacaConnections.clear();
    this.liveDataCache.clear();
  }

  addConnection(connectionId, userId, ws) {
    this.connections.set(connectionId, {
      userId,
      ws,
      subscriptions: new Set(),
      lastSeen: Date.now()
    });
    
    console.log(`➕ Added connection ${connectionId} for user ${userId}`);
    
    // Send initial data
    this.sendInitialData(connectionId);
  }

  removeConnection(connectionId) {
    const connection = this.connections.get(connectionId);
    if (connection) {
      // Remove from subscriptions
      connection.subscriptions.forEach(dataType => {
        this.unsubscribe(connectionId, dataType);
      });
      
      this.connections.delete(connectionId);
      console.log(`➖ Removed connection ${connectionId}`);
    }
  }

  subscribe(connectionId, dataType, filters = {}) {
    const connection = this.connections.get(connectionId);
    if (!connection) return false;
    
    connection.subscriptions.add(dataType);
    
    // Add to global subscriptions
    if (!this.subscriptions.has(dataType)) {
      this.subscriptions.set(dataType, new Map());
    }
    
    this.subscriptions.get(dataType).set(connectionId, {
      userId: connection.userId,
      filters,
      lastUpdate: 0
    });
    
    console.log(`📡 Subscribed connection ${connectionId} to ${dataType}`);
    
    // Send initial data for this subscription
    this.sendDataUpdate(connectionId, dataType);
    
    return true;
  }

  unsubscribe(connectionId, dataType) {
    const connection = this.connections.get(connectionId);
    if (connection) {
      connection.subscriptions.delete(dataType);
    }
    
    if (this.subscriptions.has(dataType)) {
      this.subscriptions.get(dataType).delete(connectionId);
    }
    
    console.log(`📡 Unsubscribed connection ${connectionId} from ${dataType}`);
  }

  async updateAllDataFeeds() {
    if (!this.isRunning) return;
    
    try {
      // Update each data type
      for (const [dataType, subscribers] of this.subscriptions) {
        if (subscribers.size > 0) {
          await this.updateDataType(dataType);
        }
      }
    } catch (error) {
      console.error('Error updating data feeds:', error);
    }
  }

  async updateDataType(dataType) {
    try {
      const subscribers = this.subscriptions.get(dataType);
      if (!subscribers || subscribers.size === 0) return;
      
      const data = await this.fetchDataForType(dataType);
      
      // Send to all subscribers
      for (const [connectionId, subscription] of subscribers) {
        this.sendDataToConnection(connectionId, dataType, data, subscription.filters);
      }
    } catch (error) {
      console.error(`Error updating ${dataType}:`, error);
    }
  }

  async fetchDataForType(dataType) {
    switch (dataType) {
      case this.dataTypes.MARKET_OVERVIEW:
        return await this.fetchMarketOverview();
      case this.dataTypes.PORTFOLIO:
        return await this.fetchPortfolioData();
      case this.dataTypes.WATCHLIST:
        return await this.fetchWatchlistData();
      case this.dataTypes.ALERTS:
        return await this.fetchAlertsData();
      case this.dataTypes.ECONOMIC:
        return await this.fetchEconomicData();
      case this.dataTypes.PATTERNS:
        return await this.fetchPatternsData();
      case this.dataTypes.SENTIMENT:
        return await this.fetchSentimentData();
      case this.dataTypes.RISK_METRICS:
        return await this.fetchRiskMetrics();
      default:
        return null;
    }
  }

  async fetchMarketOverview() {
    try {
      const result = await query(`
        SELECT 
          symbol,
          close as price,
          volume,
          change_percent,
          market_cap,
          updated_at
        FROM stock_data sd
        WHERE symbol IN ('SPY', 'QQQ', 'IWM', 'VIX')
        AND date = (SELECT MAX(date) FROM stock_data WHERE symbol = sd.symbol)
      `);

      const indices = {};
      result.rows.forEach(row => {
        indices[row.symbol] = {
          price: parseFloat(row.price),
          volume: parseInt(row.volume),
          change_percent: parseFloat(row.change_percent),
          market_cap: row.market_cap,
          updated_at: row.updated_at
        };
      });

      // Get sector performance
      const sectorResult = await query(`
        SELECT 
          sse.sector,
          AVG(sd.change_percent) as avg_change,
          COUNT(*) as stock_count
        FROM stock_data sd
        JOIN stock_symbols_enhanced sse ON sd.symbol = sse.symbol
        WHERE sd.date = CURRENT_DATE
        GROUP BY sse.sector
        ORDER BY avg_change DESC
      `);

      const sectors = sectorResult.rows.map(row => ({
        sector: row.sector,
        avg_change: parseFloat(row.avg_change),
        stock_count: parseInt(row.stock_count)
      }));

      return {
        indices,
        sectors,
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error fetching market overview:', error);
      return null;
    }
  }

  async fetchPortfolioData() {
    try {
      // This would fetch real portfolio data based on user's holdings
      // For now, return mock data structure
      return {
        total_value: 125000,
        day_change: 2500,
        day_change_percent: 2.04,
        positions: [
          { symbol: 'AAPL', value: 25000, change: 500, change_percent: 2.0 },
          { symbol: 'MSFT', value: 20000, change: 400, change_percent: 2.0 },
          { symbol: 'GOOGL', value: 15000, change: 300, change_percent: 2.0 }
        ],
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error fetching portfolio data:', error);
      return null;
    }
  }

  async fetchWatchlistData() {
    try {
      const result = await query(`
        SELECT 
          sd.symbol,
          sd.close as price,
          sd.change_percent,
          sd.volume,
          sse.company_name,
          sse.sector
        FROM stock_data sd
        JOIN stock_symbols_enhanced sse ON sd.symbol = sse.symbol
        WHERE sd.date = CURRENT_DATE
        AND sd.symbol IN (
          SELECT DISTINCT symbol 
          FROM watchlist_items 
          WHERE is_active = true
        )
        ORDER BY sd.change_percent DESC
      `);

      return {
        watchlist: result.rows.map(row => ({
          symbol: row.symbol,
          company_name: row.company_name,
          sector: row.sector,
          price: parseFloat(row.price),
          change_percent: parseFloat(row.change_percent),
          volume: parseInt(row.volume)
        })),
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error fetching watchlist data:', error);
      return null;
    }
  }

  async fetchAlertsData() {
    try {
      const result = await query(`
        SELECT 
          an.id,
          an.symbol,
          an.alert_type,
          an.trigger_value,
          an.created_at,
          wa.message
        FROM alert_notifications an
        JOIN watchlist_alerts wa ON an.alert_id = wa.id
        WHERE an.created_at >= NOW() - INTERVAL '1 hour'
        AND an.is_read = false
        ORDER BY an.created_at DESC
      `);

      return {
        recent_alerts: result.rows.map(row => ({
          id: row.id,
          symbol: row.symbol,
          alert_type: row.alert_type,
          trigger_value: parseFloat(row.trigger_value),
          message: row.message,
          created_at: row.created_at
        })),
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error fetching alerts data:', error);
      return null;
    }
  }

  async fetchEconomicData() {
    try {
      const result = await query(`
        SELECT 
          indicator_id,
          indicator_name,
          value,
          date,
          category
        FROM economic_indicators
        WHERE date >= CURRENT_DATE - INTERVAL '1 day'
        ORDER BY date DESC
        LIMIT 20
      `);

      return {
        recent_indicators: result.rows.map(row => ({
          id: row.indicator_id,
          name: row.indicator_name,
          value: parseFloat(row.value),
          date: row.date,
          category: row.category
        })),
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error fetching economic data:', error);
      return null;
    }
  }

  async fetchPatternsData() {
    try {
      const result = await query(`
        SELECT 
          symbol,
          pattern_type,
          confidence_score,
          detected_at,
          status
        FROM pattern_detections
        WHERE detected_at >= NOW() - INTERVAL '1 hour'
        AND status = 'active'
        ORDER BY confidence_score DESC
        LIMIT 10
      `);

      return {
        recent_patterns: result.rows.map(row => ({
          symbol: row.symbol,
          pattern_type: row.pattern_type,
          confidence: parseFloat(row.confidence_score),
          detected_at: row.detected_at,
          status: row.status
        })),
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error fetching patterns data:', error);
      return null;
    }
  }

  async fetchSentimentData() {
    try {
      const result = await query(`
        SELECT 
          symbol,
          sentiment_score,
          sentiment_label,
          volume,
          date
        FROM sentiment_analysis
        WHERE date >= CURRENT_DATE - INTERVAL '1 day'
        ORDER BY date DESC
        LIMIT 20
      `);

      return {
        sentiment_updates: result.rows.map(row => ({
          symbol: row.symbol,
          sentiment_score: parseFloat(row.sentiment_score),
          sentiment_label: row.sentiment_label,
          volume: parseInt(row.volume),
          date: row.date
        })),
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error fetching sentiment data:', error);
      return null;
    }
  }

  async fetchRiskMetrics() {
    try {
      // Mock risk metrics data
      return {
        portfolio_var: 0.025,
        market_var: 0.035,
        correlation_risk: 0.15,
        sector_concentration: 0.28,
        volatility_regime: 'normal',
        risk_alerts: [
          { type: 'concentration', level: 'medium', message: 'High tech sector exposure' },
          { type: 'volatility', level: 'low', message: 'VIX below 20' }
        ],
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error fetching risk metrics:', error);
      return null;
    }
  }

  sendDataToConnection(connectionId, dataType, data, filters) {
    const connection = this.connections.get(connectionId);
    if (!connection || !connection.ws) return;

    try {
      // Apply filters if any
      const filteredData = this.applyFilters(data, filters);
      
      const message = {
        type: 'data_update',
        data_type: dataType,
        data: filteredData,
        timestamp: new Date().toISOString()
      };

      if (connection.ws.readyState === 1) { // WebSocket.OPEN
        connection.ws.send(JSON.stringify(message));
      }
    } catch (error) {
      console.error(`Error sending data to connection ${connectionId}:`, error);
      this.removeConnection(connectionId);
    }
  }

  applyFilters(data, filters) {
    if (!filters || Object.keys(filters).length === 0) return data;
    
    // Apply various filters based on data type
    let filteredData = data;
    
    if (filters.symbols && Array.isArray(filters.symbols)) {
      // Filter by specific symbols
      if (data.watchlist) {
        filteredData.watchlist = data.watchlist.filter(item => 
          filters.symbols.includes(item.symbol)
        );
      }
    }
    
    if (filters.sectors && Array.isArray(filters.sectors)) {
      // Filter by sectors
      if (data.sectors) {
        filteredData.sectors = data.sectors.filter(sector => 
          filters.sectors.includes(sector.sector)
        );
      }
    }
    
    if (filters.min_change && data.watchlist) {
      // Filter by minimum change threshold
      filteredData.watchlist = data.watchlist.filter(item => 
        Math.abs(item.change_percent) >= filters.min_change
      );
    }
    
    return filteredData;
  }

  sendInitialData(connectionId) {
    const connection = this.connections.get(connectionId);
    if (!connection || !connection.ws) return;

    try {
      const welcomeMessage = {
        type: 'connection_established',
        connection_id: connectionId,
        available_data_types: Object.values(this.dataTypes),
        timestamp: new Date().toISOString()
      };

      if (connection.ws.readyState === 1) {
        connection.ws.send(JSON.stringify(welcomeMessage));
      }
    } catch (error) {
      console.error(`Error sending initial data to connection ${connectionId}:`, error);
    }
  }

  sendDataUpdate(connectionId, dataType) {
    // Force immediate update for this data type
    this.updateDataType(dataType);
  }

  broadcast(message) {
    // Send message to all connections
    for (const [connectionId, connection] of this.connections) {
      if (connection.ws && connection.ws.readyState === 1) {
        try {
          connection.ws.send(JSON.stringify(message));
        } catch (error) {
          console.error(`Error broadcasting to connection ${connectionId}:`, error);
          this.removeConnection(connectionId);
        }
      }
    }
  }

  getStats() {
    return {
      total_connections: this.connections.size,
      active_subscriptions: Array.from(this.subscriptions.entries()).reduce((acc, [dataType, subs]) => {
        acc[dataType] = subs.size;
        return acc;
      }, {}),
      is_running: this.isRunning,
      update_frequency: this.updateFrequency
    };
  }
}

module.exports = RealTimeDataFeed;
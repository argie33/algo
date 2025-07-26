/**
 * Crypto WebSocket Manager
 * 
 * Real-time cryptocurrency data streaming with automatic reconnection,
 * multi-exchange support, and intelligent data normalization
 */

const WebSocket = require('ws');
const EventEmitter = require('events');

class CryptoWebSocketManager extends EventEmitter {
  constructor() {
    super();
    
    this.connections = new Map();
    this.subscriptions = new Map();
    this.reconnectAttempts = new Map();
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000; // Start with 1 second
    this.heartbeatInterval = 30000; // 30 seconds
    this.dataBuffer = new Map();
    this.lastPriceUpdate = new Map();
    
    // Exchange configurations
    this.exchanges = {
      binance: {
        url: 'wss://stream.binance.com:9443/ws/!ticker@arr',
        dataFormat: 'binance',
        heartbeat: true,
        reconnectOnClose: true
      },
      coinbase: {
        url: 'wss://ws-feed.pro.coinbase.com',
        dataFormat: 'coinbase',
        heartbeat: false,
        reconnectOnClose: true
      },
      kraken: {
        url: 'wss://ws.kraken.com',
        dataFormat: 'kraken',
        heartbeat: false,
        reconnectOnClose: true
      }
    };
    
    this.isActive = false;
    this.clientConnections = new Set();
    
    console.log('🔗 Crypto WebSocket Manager initialized');
  }

  /**
   * Start WebSocket connections to exchanges
   */
  async start() {
    if (this.isActive) {
      console.log('⚠️ WebSocket Manager already active');
      return;
    }

    this.isActive = true;
    console.log('🚀 Starting crypto WebSocket connections...');

    // Start primary exchange connections
    await this.connectToExchange('binance');
    await this.connectToExchange('coinbase');
    
    // Setup heartbeat
    this.setupHeartbeat();
    
    console.log('✅ Crypto WebSocket Manager started');
  }

  /**
   * Stop all WebSocket connections
   */
  async stop() {
    this.isActive = false;
    console.log('🛑 Stopping crypto WebSocket connections...');

    // Close all exchange connections
    for (const [exchange, connection] of this.connections.entries()) {
      if (connection && connection.readyState === WebSocket.OPEN) {
        connection.close();
      }
      this.connections.delete(exchange);
    }

    // Clear intervals
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
    }

    // Clear all subscriptions
    this.subscriptions.clear();
    this.reconnectAttempts.clear();
    this.clientConnections.clear();
    
    console.log('✅ Crypto WebSocket Manager stopped');
  }

  /**
   * Connect to specific exchange WebSocket
   */
  async connectToExchange(exchangeName) {
    const config = this.exchanges[exchangeName];
    if (!config) {
      throw new Error(`Unknown exchange: ${exchangeName}`);
    }

    try {
      console.log(`🔌 Connecting to ${exchangeName} WebSocket...`);
      
      const ws = new WebSocket(config.url);
      this.connections.set(exchangeName, ws);
      this.reconnectAttempts.set(exchangeName, 0);

      ws.on('open', () => {
        console.log(`✅ Connected to ${exchangeName} WebSocket`);
        this.reconnectAttempts.set(exchangeName, 0);
        
        // Send initial subscriptions
        this.sendSubscriptions(exchangeName);
        
        this.emit('exchange_connected', { exchange: exchangeName });
      });

      ws.on('message', (data) => {
        this.handleMessage(exchangeName, data);
      });

      ws.on('close', (code, reason) => {
        console.log(`🔌 ${exchangeName} WebSocket closed: ${code} ${reason}`);
        this.connections.delete(exchangeName);
        
        if (this.isActive && config.reconnectOnClose) {
          this.scheduleReconnect(exchangeName);
        }
        
        this.emit('exchange_disconnected', { exchange: exchangeName, code, reason });
      });

      ws.on('error', (error) => {
        console.error(`❌ ${exchangeName} WebSocket error:`, error);
        this.emit('exchange_error', { exchange: exchangeName, error });
      });

    } catch (error) {
      console.error(`❌ Failed to connect to ${exchangeName}:`, error);
      this.scheduleReconnect(exchangeName);
    }
  }

  /**
   * Handle incoming WebSocket messages
   */
  handleMessage(exchangeName, rawData) {
    try {
      const data = JSON.parse(rawData.toString());
      const normalizedData = this.normalizeData(exchangeName, data);
      
      if (normalizedData) {
        // Update data buffer
        this.updateDataBuffer(normalizedData);
        
        // Emit to all subscribed clients
        this.broadcastUpdate(normalizedData);
        
        // Emit specific events
        this.emit('price_update', normalizedData);
      }
      
    } catch (error) {
      console.error(`Error parsing ${exchangeName} message:`, error);
    }
  }

  /**
   * Normalize data from different exchanges to common format
   */
  normalizeData(exchangeName, data) {
    switch (exchangeName) {
      case 'binance':
        return this.normalizeBinanceData(data);
      case 'coinbase':
        return this.normalizeCoinbaseData(data);
      case 'kraken':
        return this.normalizeKrakenData(data);
      default:
        return null;
    }
  }

  normalizeBinanceData(data) {
    // Binance 24hr ticker format
    if (Array.isArray(data)) {
      return data.map(ticker => ({
        exchange: 'binance',
        symbol: ticker.s,
        base: ticker.s.replace(/USDT$|BTC$|ETH$|BNB$/i, ''),
        quote: ticker.s.match(/USDT$|BTC$|ETH$|BNB$/i)?.[0] || 'USDT',
        price: parseFloat(ticker.c),
        volume: parseFloat(ticker.v),
        high_24h: parseFloat(ticker.h),
        low_24h: parseFloat(ticker.l),
        change_24h: parseFloat(ticker.P),
        change_absolute: parseFloat(ticker.p),
        timestamp: new Date().toISOString(),
        last_updated: Date.now()
      })).filter(item => 
        item.quote === 'USDT' && 
        item.price > 0 &&
        ['BTC', 'ETH', 'BNB', 'ADA', 'DOT', 'LINK', 'XRP', 'LTC', 'BCH', 'UNI'].includes(item.base)
      );
    }

    return null;
  }

  normalizeCoinbaseData(data) {
    // Coinbase Pro WebSocket format
    if (data.type === 'ticker' && data.product_id) {
      const [base, quote] = data.product_id.split('-');
      
      return [{
        exchange: 'coinbase',
        symbol: data.product_id,
        base,
        quote,
        price: parseFloat(data.price),
        volume: parseFloat(data.volume_24h),
        high_24h: parseFloat(data.high_24h),
        low_24h: parseFloat(data.low_24h),
        change_24h: ((parseFloat(data.price) - parseFloat(data.open_24h)) / parseFloat(data.open_24h)) * 100,
        change_absolute: parseFloat(data.price) - parseFloat(data.open_24h),
        timestamp: data.time,
        last_updated: Date.now()
      }];
    }

    return null;
  }

  normalizeKrakenData(data) {
    // Kraken WebSocket format
    if (Array.isArray(data) && data.length > 3 && data[2] === 'ticker') {
      const tickerData = data[1];
      const pair = data[3];
      
      return [{
        exchange: 'kraken',
        symbol: pair,
        base: pair.substring(0, 3),
        quote: pair.substring(3),
        price: parseFloat(tickerData.c[0]),
        volume: parseFloat(tickerData.v[0]),
        high_24h: parseFloat(tickerData.h[0]),
        low_24h: parseFloat(tickerData.l[0]),
        change_24h: parseFloat(tickerData.p[0]),
        change_absolute: parseFloat(tickerData.p[1]),
        timestamp: new Date().toISOString(),
        last_updated: Date.now()
      }];
    }

    return null;
  }

  /**
   * Update internal data buffer
   */
  updateDataBuffer(normalizedData) {
    if (Array.isArray(normalizedData)) {
      normalizedData.forEach(item => {
        const key = `${item.exchange}_${item.symbol}`;
        this.dataBuffer.set(key, item);
        this.lastPriceUpdate.set(item.symbol, item.price);
      });
    }
  }

  /**
   * Broadcast updates to all connected clients
   */
  broadcastUpdate(data) {
    const message = JSON.stringify({
      type: 'crypto_update',
      data: data,
      timestamp: new Date().toISOString()
    });

    this.clientConnections.forEach(client => {
      if (client.readyState === WebSocket.OPEN) {
        try {
          client.send(message);
        } catch (error) {
          console.error('Error sending to client:', error);
          this.clientConnections.delete(client);
        }
      } else {
        this.clientConnections.delete(client);
      }
    });
  }

  /**
   * Add client WebSocket connection
   */
  addClient(clientWs) {
    this.clientConnections.add(clientWs);
    
    // Send current data buffer to new client
    const currentData = Array.from(this.dataBuffer.values());
    if (currentData.length > 0) {
      const message = JSON.stringify({
        type: 'crypto_snapshot',
        data: currentData,
        timestamp: new Date().toISOString()
      });
      
      if (clientWs.readyState === WebSocket.OPEN) {
        clientWs.send(message);
      }
    }

    clientWs.on('close', () => {
      this.clientConnections.delete(clientWs);
    });

    console.log(`👤 Client connected to crypto WebSocket. Total clients: ${this.clientConnections.size}`);
  }

  /**
   * Remove client WebSocket connection
   */
  removeClient(clientWs) {
    this.clientConnections.delete(clientWs);
    console.log(`👋 Client disconnected from crypto WebSocket. Total clients: ${this.clientConnections.size}`);
  }

  /**
   * Send subscriptions to exchange
   */
  sendSubscriptions(exchangeName) {
    const ws = this.connections.get(exchangeName);
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    switch (exchangeName) {
      case 'coinbase':
        // Subscribe to major crypto pairs
        const coinbaseSubscription = {
          type: 'subscribe',
          product_ids: [
            'BTC-USD', 'ETH-USD', 'LTC-USD', 'BCH-USD',
            'ADA-USD', 'DOT-USD', 'LINK-USD', 'XRP-USD'
          ],
          channels: ['ticker']
        };
        ws.send(JSON.stringify(coinbaseSubscription));
        break;
        
      case 'kraken':
        // Subscribe to major crypto pairs
        const krakenSubscription = {
          event: 'subscribe',
          pair: ['XBT/USD', 'ETH/USD', 'LTC/USD', 'BCH/USD'],
          subscription: { name: 'ticker' }
        };
        ws.send(JSON.stringify(krakenSubscription));
        break;
        
      case 'binance':
        // Binance streams are configured in URL, no additional subscription needed
        break;
    }
  }

  /**
   * Schedule reconnection attempt
   */
  scheduleReconnect(exchangeName) {
    const attempts = this.reconnectAttempts.get(exchangeName) || 0;
    
    if (attempts >= this.maxReconnectAttempts) {
      console.error(`❌ Max reconnection attempts reached for ${exchangeName}`);
      this.emit('exchange_failed', { exchange: exchangeName });
      return;
    }

    const delay = this.reconnectDelay * Math.pow(2, attempts); // Exponential backoff
    console.log(`🔄 Scheduling ${exchangeName} reconnection in ${delay}ms (attempt ${attempts + 1})`);

    setTimeout(() => {
      if (this.isActive) {
        this.reconnectAttempts.set(exchangeName, attempts + 1);
        this.connectToExchange(exchangeName);
      }
    }, delay);
  }

  /**
   * Setup heartbeat to keep connections alive
   */
  setupHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      this.connections.forEach((ws, exchangeName) => {
        if (ws.readyState === WebSocket.OPEN) {
          // Send ping if exchange supports it
          if (this.exchanges[exchangeName].heartbeat) {
            try {
              ws.ping();
            } catch (error) {
              console.error(`Heartbeat failed for ${exchangeName}:`, error);
            }
          }
        }
      });
    }, this.heartbeatInterval);
  }

  /**
   * Get current data snapshot
   */
  getDataSnapshot() {
    return {
      connections: Object.fromEntries(
        Array.from(this.connections.entries()).map(([exchange, ws]) => [
          exchange,
          {
            readyState: ws.readyState,
            readyStateText: ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'][ws.readyState]
          }
        ])
      ),
      dataBuffer: Array.from(this.dataBuffer.values()),
      clientCount: this.clientConnections.size,
      lastUpdates: Object.fromEntries(this.lastPriceUpdate.entries()),
      isActive: this.isActive,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Get specific symbol data
   */
  getSymbolData(symbol) {
    const results = [];
    
    for (const [key, data] of this.dataBuffer.entries()) {
      if (data.symbol === symbol || data.base === symbol) {
        results.push(data);
      }
    }
    
    return results.length > 0 ? results : null;
  }

  /**
   * Get aggregated price for symbol across exchanges
   */
  getAggregatedPrice(symbol) {
    const symbolData = this.getSymbolData(symbol);
    if (!symbolData || symbolData.length === 0) return null;

    // Volume-weighted average price
    const totalVolume = symbolData.reduce((sum, data) => sum + data.volume, 0);
    if (totalVolume === 0) return symbolData[0].price;

    const weightedPrice = symbolData.reduce((sum, data) => {
      return sum + (data.price * data.volume);
    }, 0);

    return {
      price: weightedPrice / totalVolume,
      sources: symbolData.length,
      volume: totalVolume,
      timestamp: new Date().toISOString(),
      exchanges: symbolData.map(d => d.exchange)
    };
  }

  /**
   * Health check
   */
  getHealthStatus() {
    const connections = Object.fromEntries(
      Array.from(this.connections.entries()).map(([exchange, ws]) => [
        exchange,
        {
          connected: ws.readyState === WebSocket.OPEN,
          readyState: ws.readyState,
          reconnectAttempts: this.reconnectAttempts.get(exchange) || 0
        }
      ])
    );

    const totalConnected = Object.values(connections).filter(c => c.connected).length;
    const totalExpected = Object.keys(this.exchanges).length;

    return {
      status: totalConnected === totalExpected ? 'healthy' : 
              totalConnected > 0 ? 'degraded' : 'unhealthy',
      connections,
      activeClients: this.clientConnections.size,
      dataPoints: this.dataBuffer.size,
      isActive: this.isActive,
      connectedRatio: `${totalConnected}/${totalExpected}`,
      timestamp: new Date().toISOString()
    };
  }
}

module.exports = CryptoWebSocketManager;
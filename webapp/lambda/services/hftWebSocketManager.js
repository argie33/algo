/**
 * HFT WebSocket Manager - Ultra-low latency market data streaming
 * Handles multiple data providers with failover and HFT optimization
 */

const WebSocket = require('ws');
const EventEmitter = require('events');
const { createLogger } = require('../utils/structuredLogger');

class HFTWebSocketManager extends EventEmitter {
  constructor() {
    super();
    this.logger = createLogger('financial-platform', 'hft-websocket-manager');
    this.correlationId = this.generateCorrelationId();
    
    // Connection management
    this.connections = new Map();
    this.subscriptions = new Map();
    this.reconnectAttempts = new Map();
    this.maxReconnectAttempts = 5;
    
    // HFT-specific configuration
    this.hftSymbols = new Set();
    this.latencyTracking = new Map();
    this.messageBuffer = new Map();
    
    // Performance metrics
    this.metrics = {
      totalMessages: 0,
      hftMessages: 0,
      avgLatency: 0,
      minLatency: Infinity,
      maxLatency: 0,
      reconnections: 0,
      lastMessageTime: 0
    };
    
    // Provider configurations
    this.providers = {
      alpaca: {
        url: 'wss://stream.data.alpaca.markets/v2/iex',
        authRequired: true,
        maxSymbols: 300,
        rateLimits: {
          perSecond: 10,
          perMinute: 200
        }
      },
      polygon: {
        url: 'wss://socket.polygon.io/stocks',
        authRequired: true,
        maxSymbols: 100,
        rateLimits: {
          perSecond: 5,
          perMinute: 100
        }
      },
      finnhub: {
        url: 'wss://ws.finnhub.io',
        authRequired: true,
        maxSymbols: 50,
        rateLimits: {
          perSecond: 3,
          perMinute: 60
        }
      }
    };
  }

  generateCorrelationId() {
    return `hft-ws-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Initialize WebSocket connections for multiple providers
   */
  async initialize(credentials) {
    try {
      this.logger.info('Initializing HFT WebSocket Manager', {
        providers: Object.keys(this.providers),
        correlationId: this.correlationId
      });

      // Initialize connections to all available providers
      const initPromises = [];
      
      for (const [provider, config] of Object.entries(this.providers)) {
        if (credentials[provider]) {
          initPromises.push(this.initializeProvider(provider, config, credentials[provider]));
        }
      }

      const results = await Promise.allSettled(initPromises);
      const successfulConnections = results.filter(r => r.status === 'fulfilled').length;

      this.logger.info('HFT WebSocket Manager initialized', {
        totalProviders: Object.keys(this.providers).length,
        successfulConnections,
        correlationId: this.correlationId
      });

      return {
        success: successfulConnections > 0,
        connectedProviders: successfulConnections,
        totalProviders: Object.keys(this.providers).length
      };

    } catch (error) {
      this.logger.error('Failed to initialize HFT WebSocket Manager', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      return { success: false, error: error.message };
    }
  }

  /**
   * Initialize connection to a specific provider
   */
  async initializeProvider(provider, config, credentials) {
    return new Promise((resolve, reject) => {
      try {
        this.logger.info('Connecting to provider', {
          provider,
          url: config.url,
          correlationId: this.correlationId
        });

        const ws = new WebSocket(config.url);
        const connection = {
          ws,
          config,
          credentials,
          connected: false,
          authenticated: false,
          subscribed: new Set(),
          lastPing: Date.now(),
          messageCount: 0
        };

        ws.on('open', () => {
          this.logger.info('WebSocket connection opened', {
            provider,
            correlationId: this.correlationId
          });

          connection.connected = true;
          
          // Authenticate if required
          if (config.authRequired) {
            this.authenticateProvider(provider, connection);
          } else {
            connection.authenticated = true;
          }
        });

        ws.on('message', (data) => {
          this.handleMessage(provider, connection, data);
        });

        ws.on('close', (code, reason) => {
          this.logger.warn('WebSocket connection closed', {
            provider,
            code,
            reason: reason.toString(),
            correlationId: this.correlationId
          });

          connection.connected = false;
          connection.authenticated = false;
          this.scheduleReconnect(provider);
        });

        ws.on('error', (error) => {
          this.logger.error('WebSocket error', {
            provider,
            error: error.message,
            correlationId: this.correlationId
          });
          
          reject(error);
        });

        // Set up ping/pong for connection health
        ws.on('pong', () => {
          connection.lastPing = Date.now();
        });

        this.connections.set(provider, connection);
        
        // Resolve after connection is established
        setTimeout(() => {
          if (connection.connected) {
            resolve({ provider, connected: true });
          } else {
            reject(new Error(`Failed to connect to ${provider}`));
          }
        }, 5000);

      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Authenticate with provider
   */
  authenticateProvider(provider, connection) {
    const { credentials } = connection;
    let authMessage;

    switch (provider) {
      case 'alpaca':
        authMessage = {
          action: 'auth',
          key: credentials.apiKey,
          secret: credentials.apiSecret
        };
        break;
      
      case 'polygon':
        authMessage = {
          action: 'auth',
          params: credentials.apiKey
        };
        break;
      
      case 'finnhub':
        authMessage = {
          type: 'subscribe',
          symbol: 'AAPL', // Initial symbol to authenticate
          token: credentials.apiKey
        };
        break;
      
      default:
        this.logger.error('Unknown provider for authentication', {
          provider,
          correlationId: this.correlationId
        });
        return;
    }

    connection.ws.send(JSON.stringify(authMessage));
    
    this.logger.info('Authentication message sent', {
      provider,
      correlationId: this.correlationId
    });
  }

  /**
   * Handle incoming WebSocket messages
   */
  handleMessage(provider, connection, data) {
    const startTime = Date.now();
    
    try {
      const message = JSON.parse(data.toString());
      connection.messageCount++;
      this.metrics.totalMessages++;
      this.metrics.lastMessageTime = startTime;

      // Handle authentication responses
      if (this.isAuthenticationMessage(provider, message)) {
        this.handleAuthentication(provider, connection, message);
        return;
      }

      // Handle market data messages
      if (this.isMarketDataMessage(provider, message)) {
        const marketData = this.parseMarketData(provider, message);
        
        if (marketData) {
          // Calculate latency for HFT symbols
          if (this.hftSymbols.has(marketData.symbol)) {
            const latency = startTime - (marketData.timestamp || startTime);
            this.updateLatencyMetrics(marketData.symbol, latency);
            this.metrics.hftMessages++;
          }

          // Emit market data event
          this.emit('marketData', {
            provider,
            ...marketData,
            receivedAt: startTime,
            isHFT: this.hftSymbols.has(marketData.symbol)
          });
        }
      }

    } catch (error) {
      this.logger.error('Error processing WebSocket message', {
        provider,
        error: error.message,
        messageLength: data.toString().length,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Check if message is authentication response
   */
  isAuthenticationMessage(provider, message) {
    switch (provider) {
      case 'alpaca':
        return message.T === 'success' && message.msg === 'authenticated';
      case 'polygon':
        return message.status === 'auth_success';
      case 'finnhub':
        return message.type === 'ping';
      default:
        return false;
    }
  }

  /**
   * Handle authentication success/failure
   */
  handleAuthentication(provider, connection, message) {
    const success = this.isAuthenticationSuccess(provider, message);
    
    if (success) {
      connection.authenticated = true;
      
      this.logger.info('Provider authenticated successfully', {
        provider,
        correlationId: this.correlationId
      });

      // Subscribe to pending symbols
      this.subscribePendingSymbols(provider);
      
    } else {
      this.logger.error('Provider authentication failed', {
        provider,
        message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Check if authentication was successful
   */
  isAuthenticationSuccess(provider, message) {
    switch (provider) {
      case 'alpaca':
        return message.T === 'success' && message.msg === 'authenticated';
      case 'polygon':
        return message.status === 'auth_success';
      case 'finnhub':
        return true; // Finnhub doesn't send explicit auth success
      default:
        return false;
    }
  }

  /**
   * Check if message contains market data
   */
  isMarketDataMessage(provider, message) {
    switch (provider) {
      case 'alpaca':
        return ['t', 'q'].includes(message.T); // trade or quote
      case 'polygon':
        return ['T', 'Q'].includes(message.ev); // trade or quote event
      case 'finnhub':
        return message.type === 'trade';
      default:
        return false;
    }
  }

  /**
   * Parse market data from provider-specific format
   */
  parseMarketData(provider, message) {
    try {
      switch (provider) {
        case 'alpaca':
          if (message.T === 't') { // Trade
            return {
              symbol: message.S,
              price: message.p,
              size: message.s,
              timestamp: new Date(message.t).getTime(),
              type: 'trade'
            };
          } else if (message.T === 'q') { // Quote
            return {
              symbol: message.S,
              bid: message.bp,
              ask: message.ap,
              bidSize: message.bs,
              askSize: message.as,
              timestamp: new Date(message.t).getTime(),
              type: 'quote'
            };
          }
          break;

        case 'polygon':
          if (message.ev === 'T') { // Trade
            return {
              symbol: message.sym,
              price: message.p,
              size: message.s,
              timestamp: message.t,
              type: 'trade'
            };
          } else if (message.ev === 'Q') { // Quote
            return {
              symbol: message.sym,
              bid: message.bp,
              ask: message.ap,
              bidSize: message.bs,
              askSize: message.as,
              timestamp: message.t,
              type: 'quote'
            };
          }
          break;

        case 'finnhub':
          if (message.type === 'trade') {
            return {
              symbol: message.s,
              price: message.data[0].p,
              size: message.data[0].v,
              timestamp: message.data[0].t,
              type: 'trade'
            };
          }
          break;
      }
    } catch (error) {
      this.logger.error('Error parsing market data', {
        provider,
        error: error.message,
        message,
        correlationId: this.correlationId
      });
    }

    return null;
  }

  /**
   * Subscribe to HFT symbols with priority
   */
  async subscribeToHFTSymbols(symbols, priority = 'high') {
    this.logger.info('Subscribing to HFT symbols', {
      symbols,
      priority,
      correlationId: this.correlationId
    });

    // Add symbols to HFT tracking
    symbols.forEach(symbol => {
      this.hftSymbols.add(symbol);
      this.latencyTracking.set(symbol, {
        samples: [],
        avg: 0,
        min: Infinity,
        max: 0
      });
    });

    // Subscribe across all connected providers
    const subscriptionPromises = [];
    
    for (const [provider, connection] of this.connections) {
      if (connection.connected && connection.authenticated) {
        subscriptionPromises.push(this.subscribeProvider(provider, symbols));
      }
    }

    const results = await Promise.allSettled(subscriptionPromises);
    const successful = results.filter(r => r.status === 'fulfilled').length;

    return {
      success: successful > 0,
      subscribedProviders: successful,
      totalProviders: this.connections.size
    };
  }

  /**
   * Subscribe to symbols on specific provider
   */
  async subscribeProvider(provider, symbols) {
    const connection = this.connections.get(provider);
    if (!connection || !connection.authenticated) {
      throw new Error(`Provider ${provider} not authenticated`);
    }

    let subscribeMessage;

    switch (provider) {
      case 'alpaca':
        subscribeMessage = {
          action: 'subscribe',
          trades: symbols,
          quotes: symbols
        };
        break;
      
      case 'polygon':
        subscribeMessage = {
          action: 'subscribe',
          params: symbols.join(',')
        };
        break;
      
      case 'finnhub':
        // Finnhub requires individual subscription per symbol
        symbols.forEach(symbol => {
          connection.ws.send(JSON.stringify({
            type: 'subscribe',
            symbol: symbol
          }));
        });
        return { success: true };
    }

    if (subscribeMessage) {
      connection.ws.send(JSON.stringify(subscribeMessage));
    }

    // Track subscriptions
    symbols.forEach(symbol => connection.subscribed.add(symbol));

    return { success: true };
  }

  /**
   * Update latency metrics for HFT analysis
   */
  updateLatencyMetrics(symbol, latency) {
    const tracking = this.latencyTracking.get(symbol);
    if (!tracking) return;

    tracking.samples.push(latency);
    
    // Keep only last 100 samples
    if (tracking.samples.length > 100) {
      tracking.samples.shift();
    }

    // Update statistics
    tracking.min = Math.min(tracking.min, latency);
    tracking.max = Math.max(tracking.max, latency);
    tracking.avg = tracking.samples.reduce((a, b) => a + b, 0) / tracking.samples.length;

    // Update global metrics
    this.metrics.minLatency = Math.min(this.metrics.minLatency, latency);
    this.metrics.maxLatency = Math.max(this.metrics.maxLatency, latency);
    
    const totalSamples = Array.from(this.latencyTracking.values())
      .reduce((sum, t) => sum + t.samples.length, 0);
    const totalLatency = Array.from(this.latencyTracking.values())
      .reduce((sum, t) => sum + t.samples.reduce((a, b) => a + b, 0), 0);
    
    this.metrics.avgLatency = totalSamples > 0 ? totalLatency / totalSamples : 0;
  }

  /**
   * Schedule reconnection with exponential backoff
   */
  scheduleReconnect(provider) {
    const attempts = this.reconnectAttempts.get(provider) || 0;
    
    if (attempts >= this.maxReconnectAttempts) {
      this.logger.error('Max reconnection attempts reached', {
        provider,
        attempts,
        correlationId: this.correlationId
      });
      return;
    }

    const delay = Math.pow(2, attempts) * 1000; // Exponential backoff
    this.reconnectAttempts.set(provider, attempts + 1);

    this.logger.info('Scheduling reconnection', {
      provider,
      attempt: attempts + 1,
      delay,
      correlationId: this.correlationId
    });

    setTimeout(() => {
      this.reconnectProvider(provider);
    }, delay);
  }

  /**
   * Reconnect to specific provider
   */
  async reconnectProvider(provider) {
    try {
      const config = this.providers[provider];
      const oldConnection = this.connections.get(provider);
      
      if (oldConnection && oldConnection.connected) {
        return; // Already reconnected
      }

      this.logger.info('Reconnecting to provider', {
        provider,
        correlationId: this.correlationId
      });

      // Get credentials from old connection
      const credentials = oldConnection ? oldConnection.credentials : null;
      
      if (!credentials) {
        this.logger.error('No credentials available for reconnection', {
          provider,
          correlationId: this.correlationId
        });
        return;
      }

      // Initialize new connection
      await this.initializeProvider(provider, config, credentials);
      this.metrics.reconnections++;

      // Reset reconnection attempts on successful connection
      this.reconnectAttempts.set(provider, 0);

    } catch (error) {
      this.logger.error('Reconnection failed', {
        provider,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Subscribe to pending symbols after authentication
   */
  subscribePendingSymbols(provider) {
    const pendingSymbols = this.subscriptions.get(provider);
    if (pendingSymbols && pendingSymbols.size > 0) {
      this.subscribeProvider(provider, Array.from(pendingSymbols))
        .then(() => {
          this.subscriptions.delete(provider);
        })
        .catch(error => {
          this.logger.error('Failed to subscribe pending symbols', {
            provider,
            error: error.message,
            correlationId: this.correlationId
          });
        });
    }
  }

  /**
   * Get performance metrics
   */
  getMetrics() {
    return {
      ...this.metrics,
      connectedProviders: Array.from(this.connections.values())
        .filter(c => c.connected).length,
      totalProviders: this.connections.size,
      hftSymbols: this.hftSymbols.size,
      latencyBySymbol: Object.fromEntries(
        Array.from(this.latencyTracking.entries()).map(([symbol, tracking]) => [
          symbol,
          {
            avg: Math.round(tracking.avg * 100) / 100,
            min: tracking.min === Infinity ? 0 : tracking.min,
            max: tracking.max,
            samples: tracking.samples.length
          }
        ])
      )
    };
  }

  /**
   * Cleanup and disconnect all providers
   */
  async disconnect() {
    this.logger.info('Disconnecting HFT WebSocket Manager', {
      correlationId: this.correlationId
    });

    const disconnectPromises = [];
    
    for (const [provider, connection] of this.connections) {
      if (connection.connected) {
        disconnectPromises.push(new Promise(resolve => {
          connection.ws.close();
          connection.ws.on('close', resolve);
          setTimeout(resolve, 1000); // Force resolve after 1 second
        }));
      }
    }

    await Promise.allSettled(disconnectPromises);
    
    this.connections.clear();
    this.subscriptions.clear();
    this.hftSymbols.clear();
    this.latencyTracking.clear();

    return { success: true };
  }
}

module.exports = HFTWebSocketManager;
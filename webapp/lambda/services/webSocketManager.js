// WebSocket Connection Manager - Real-time Market Data Streaming
// Handles multi-provider WebSocket connections with reconnection logic and failover

const EventEmitter = require('events');
const WebSocket = require('ws');

class WebSocketManager extends EventEmitter {
  constructor(options = {}) {
    super();
    
    this.options = {
      maxReconnectAttempts: options.maxReconnectAttempts || 5,
      reconnectDelay: options.reconnectDelay || 1000,
      maxReconnectDelay: options.maxReconnectDelay || 30000,
      heartbeatInterval: options.heartbeatInterval || 30000,
      connectionTimeout: options.connectionTimeout || 10000,
      ...options
    };
    
    // Connection state management
    this.connections = new Map();
    this.subscriptions = new Map();
    this.reconnectAttempts = new Map();
    this.heartbeatIntervals = new Map();
    
    // Provider configurations
    this.providers = {
      alpaca: {
        wsUrl: 'wss://stream.data.alpaca.markets/v2/iex',
        authRequired: true,
        dataTypes: ['trades', 'quotes', 'bars'],
        rateLimit: 200 // messages per second
      },
      polygon: {
        wsUrl: 'wss://socket.polygon.io/stocks',
        authRequired: true,
        dataTypes: ['T', 'Q', 'A'], // trades, quotes, aggregates
        rateLimit: 100
      },
      finnhub: {
        wsUrl: 'wss://ws.finnhub.io',
        authRequired: true,
        dataTypes: ['trade', 'quote'],
        rateLimit: 60
      }
    };
    
    // Circuit breaker for each provider
    this.circuitBreakers = new Map();
    this.initializeCircuitBreakers();
  }
  
  initializeCircuitBreakers() {
    Object.keys(this.providers).forEach(provider => {
      this.circuitBreakers.set(provider, {
        failures: 0,
        lastFailureTime: null,
        state: 'CLOSED', // CLOSED, OPEN, HALF_OPEN
        threshold: 3,
        timeout: 60000 // 1 minute
      });
    });
  }
  
  async connect(provider, apiKey, symbols = []) {
    try {
      const circuitBreaker = this.circuitBreakers.get(provider);
      
      // Check circuit breaker state
      if (circuitBreaker.state === 'OPEN') {
        const timeSinceFailure = Date.now() - circuitBreaker.lastFailureTime;
        if (timeSinceFailure < circuitBreaker.timeout) {
          throw new Error(`Circuit breaker OPEN for ${provider}. Retry in ${Math.ceil((circuitBreaker.timeout - timeSinceFailure) / 1000)}s`);
        } else {
          circuitBreaker.state = 'HALF_OPEN';
        }
      }
      
      const providerConfig = this.providers[provider];
      if (!providerConfig) {
        throw new Error(`Unknown provider: ${provider}`);
      }
      
      console.log(`🔌 Connecting to ${provider} WebSocket...`);
      
      const ws = new WebSocket(providerConfig.wsUrl);
      const connectionId = `${provider}-${Date.now()}`;
      
      // Connection timeout
      const connectionTimeout = setTimeout(() => {
        if (ws.readyState === WebSocket.CONNECTING) {
          ws.close();
          this.handleConnectionFailure(provider, new Error('Connection timeout'));
        }
      }, this.options.connectionTimeout);
      
      ws.onopen = () => {
        clearTimeout(connectionTimeout);
        console.log(`✅ Connected to ${provider} WebSocket`);
        
        // Reset circuit breaker on successful connection
        circuitBreaker.failures = 0;
        circuitBreaker.state = 'CLOSED';
        
        // Store connection
        this.connections.set(provider, {
          ws,
          connectionId,
          provider,
          connected: true,
          lastActivity: Date.now(),
          subscriptions: new Set()
        });
        
        // Authenticate if required
        if (providerConfig.authRequired) {
          this.authenticate(provider, apiKey);
        }
        
        // Subscribe to symbols if provided
        if (symbols.length > 0) {
          this.subscribe(provider, symbols);
        }
        
        // Start heartbeat
        this.startHeartbeat(provider);
        
        this.emit('connected', { provider, connectionId });
      };
      
      ws.onmessage = (event) => {
        this.handleMessage(provider, event.data);
      };
      
      ws.onclose = (event) => {
        console.log(`🔌 ${provider} WebSocket closed:`, event.code, event.reason);
        this.handleDisconnection(provider, event);
      };
      
      ws.onerror = (error) => {
        console.error(`❌ ${provider} WebSocket error:`, error);
        this.handleConnectionFailure(provider, error);
      };
      
      return connectionId;
      
    } catch (error) {
      this.handleConnectionFailure(provider, error);
      throw error;
    }
  }
  
  authenticate(provider, apiKey) {
    const connection = this.connections.get(provider);
    if (!connection || !connection.connected) {
      throw new Error(`No active connection for ${provider}`);
    }
    
    let authMessage;
    
    switch (provider) {
      case 'alpaca':
        authMessage = {
          action: 'auth',
          key: apiKey.keyId,
          secret: apiKey.secretKey
        };
        break;
        
      case 'polygon':
        authMessage = {
          action: 'auth',
          params: apiKey.keyId
        };
        break;
        
      case 'finnhub':
        authMessage = {
          type: 'subscribe',
          symbol: 'BINANCE:BTCUSDT' // Test subscription
        };
        // Finnhub uses token in URL, so no auth message needed
        return;
        
      default:
        throw new Error(`Authentication not implemented for ${provider}`);
    }
    
    connection.ws.send(JSON.stringify(authMessage));
    console.log(`🔐 Sent authentication to ${provider}`);
  }
  
  subscribe(provider, symbols) {
    const connection = this.connections.get(provider);
    if (!connection || !connection.connected) {
      throw new Error(`No active connection for ${provider}`);
    }
    
    let subscribeMessage;
    
    switch (provider) {
      case 'alpaca':
        subscribeMessage = {
          action: 'subscribe',
          trades: symbols,
          quotes: symbols,
          bars: symbols
        };
        break;
        
      case 'polygon':
        subscribeMessage = {
          action: 'subscribe',
          params: `T.${symbols.join(',T.')}`
        };
        break;
        
      case 'finnhub':
        // Finnhub requires individual symbol subscriptions
        symbols.forEach(symbol => {
          const msg = {
            type: 'subscribe',
            symbol: symbol
          };
          connection.ws.send(JSON.stringify(msg));
        });
        return;
        
      default:
        throw new Error(`Subscription not implemented for ${provider}`);
    }
    
    connection.ws.send(JSON.stringify(subscribeMessage));
    
    // Track subscriptions
    symbols.forEach(symbol => {
      connection.subscriptions.add(symbol);
      
      if (!this.subscriptions.has(symbol)) {
        this.subscriptions.set(symbol, new Set());
      }
      this.subscriptions.get(symbol).add(provider);
    });
    
    console.log(`📊 Subscribed to ${symbols.length} symbols on ${provider}`);
  }
  
  unsubscribe(provider, symbols) {
    const connection = this.connections.get(provider);
    if (!connection || !connection.connected) {
      return;
    }
    
    let unsubscribeMessage;
    
    switch (provider) {
      case 'alpaca':
        unsubscribeMessage = {
          action: 'unsubscribe',
          trades: symbols,
          quotes: symbols,
          bars: symbols
        };
        break;
        
      case 'polygon':
        unsubscribeMessage = {
          action: 'unsubscribe',
          params: `T.${symbols.join(',T.')}`
        };
        break;
        
      case 'finnhub':
        symbols.forEach(symbol => {
          const msg = {
            type: 'unsubscribe',
            symbol: symbol
          };
          connection.ws.send(JSON.stringify(msg));
        });
        return;
        
      default:
        return;
    }
    
    connection.ws.send(JSON.stringify(unsubscribeMessage));
    
    // Remove from tracking
    symbols.forEach(symbol => {
      connection.subscriptions.delete(symbol);
      
      const symbolProviders = this.subscriptions.get(symbol);
      if (symbolProviders) {
        symbolProviders.delete(provider);
        if (symbolProviders.size === 0) {
          this.subscriptions.delete(symbol);
        }
      }
    });
    
    console.log(`📊 Unsubscribed from ${symbols.length} symbols on ${provider}`);
  }
  
  handleMessage(provider, data) {
    try {
      const connection = this.connections.get(provider);
      if (connection) {
        connection.lastActivity = Date.now();
      }
      
      let message;
      try {
        message = JSON.parse(data);
      } catch (parseError) {
        console.warn(`Failed to parse message from ${provider}:`, data);
        return;
      }
      
      // Emit raw message for processing by data normalization service
      this.emit('message', {
        provider,
        data: message,
        timestamp: Date.now()
      });
      
      // Handle provider-specific messages
      this.handleProviderMessage(provider, message);
      
    } catch (error) {
      console.error(`Error handling message from ${provider}:`, error);
    }
  }
  
  handleProviderMessage(provider, message) {
    switch (provider) {
      case 'alpaca':
        if (message.T === 't') { // Trade
          this.emit('trade', {
            provider,
            symbol: message.S,
            price: message.p,
            size: message.s,
            timestamp: new Date(message.t)
          });
        } else if (message.T === 'q') { // Quote
          this.emit('quote', {
            provider,
            symbol: message.S,
            bid: message.bp,
            ask: message.ap,
            bidSize: message.bs,
            askSize: message.as,
            timestamp: new Date(message.t)
          });
        }
        break;
        
      case 'polygon':
        if (message.ev === 'T') { // Trade
          this.emit('trade', {
            provider,
            symbol: message.sym,
            price: message.p,
            size: message.s,
            timestamp: new Date(message.t)
          });
        }
        break;
        
      case 'finnhub':
        if (message.type === 'trade') {
          message.data.forEach(trade => {
            this.emit('trade', {
              provider,
              symbol: trade.s,
              price: trade.p,
              size: trade.v,
              timestamp: new Date(trade.t)
            });
          });
        }
        break;
    }
  }
  
  handleDisconnection(provider, event) {
    const connection = this.connections.get(provider);
    if (connection) {
      connection.connected = false;
      this.stopHeartbeat(provider);
    }
    
    this.emit('disconnected', { provider, code: event.code, reason: event.reason });
    
    // Attempt reconnection unless it was a clean close
    if (event.code !== 1000) {
      this.attemptReconnection(provider);
    }
  }
  
  handleConnectionFailure(provider, error) {
    const circuitBreaker = this.circuitBreakers.get(provider);
    circuitBreaker.failures++;
    circuitBreaker.lastFailureTime = Date.now();
    
    if (circuitBreaker.failures >= circuitBreaker.threshold) {
      circuitBreaker.state = 'OPEN';
      console.log(`🚨 Circuit breaker OPEN for ${provider} after ${circuitBreaker.failures} failures`);
    }
    
    this.emit('error', { provider, error });
  }
  
  async attemptReconnection(provider) {
    const attempts = this.reconnectAttempts.get(provider) || 0;
    
    if (attempts >= this.options.maxReconnectAttempts) {
      console.log(`❌ Max reconnection attempts reached for ${provider}`);
      this.emit('maxReconnectAttemptsReached', { provider });
      return;
    }
    
    const delay = Math.min(
      this.options.reconnectDelay * Math.pow(2, attempts),
      this.options.maxReconnectDelay
    );
    
    this.reconnectAttempts.set(provider, attempts + 1);
    
    console.log(`🔄 Reconnecting to ${provider} in ${delay}ms (attempt ${attempts + 1}/${this.options.maxReconnectAttempts})`);
    
    setTimeout(() => {
      // TODO: Reconnect with stored API key and subscriptions
      this.emit('reconnectAttempt', { provider, attempt: attempts + 1 });
    }, delay);
  }
  
  startHeartbeat(provider) {
    const interval = setInterval(() => {
      const connection = this.connections.get(provider);
      if (!connection || !connection.connected) {
        clearInterval(interval);
        return;
      }
      
      // Check if connection is still alive
      const timeSinceLastActivity = Date.now() - connection.lastActivity;
      if (timeSinceLastActivity > this.options.heartbeatInterval * 2) {
        console.warn(`❤️ No activity from ${provider} for ${timeSinceLastActivity}ms, closing connection`);
        connection.ws.close();
        return;
      }
      
      // Send ping if supported by provider
      if (connection.ws.readyState === WebSocket.OPEN) {
        try {
          connection.ws.ping();
        } catch (error) {
          // Ping not supported, just check connection state
        }
      }
    }, this.options.heartbeatInterval);
    
    this.heartbeatIntervals.set(provider, interval);
  }
  
  stopHeartbeat(provider) {
    const interval = this.heartbeatIntervals.get(provider);
    if (interval) {
      clearInterval(interval);
      this.heartbeatIntervals.delete(provider);
    }
  }
  
  disconnect(provider) {
    const connection = this.connections.get(provider);
    if (connection && connection.connected) {
      connection.ws.close(1000, 'Client disconnect');
      this.connections.delete(provider);
      this.stopHeartbeat(provider);
      this.reconnectAttempts.delete(provider);
    }
  }
  
  disconnectAll() {
    this.connections.forEach((connection, provider) => {
      this.disconnect(provider);
    });
  }
  
  getConnectionStatus() {
    const status = {};
    
    this.connections.forEach((connection, provider) => {
      const circuitBreaker = this.circuitBreakers.get(provider);
      status[provider] = {
        connected: connection.connected,
        lastActivity: connection.lastActivity,
        subscriptions: Array.from(connection.subscriptions),
        circuitBreakerState: circuitBreaker.state,
        failures: circuitBreaker.failures,
        reconnectAttempts: this.reconnectAttempts.get(provider) || 0
      };
    });
    
    return status;
  }
  
  getSubscriptions() {
    const subscriptions = {};
    
    this.subscriptions.forEach((providers, symbol) => {
      subscriptions[symbol] = Array.from(providers);
    });
    
    return subscriptions;
  }
}

module.exports = WebSocketManager;
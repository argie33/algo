/**
 * Enhanced WebSocket Service with Security & Performance Improvements
 * Addresses REQ-027 WebSocket Architecture Gaps:
 * - Multi-provider support (Alpaca, TD Ameritrade)
 * - Data validation and anomaly detection
 * - Message compression and optimization
 * - Connection pooling and load balancing
 * - Real-time latency monitoring
 * - Message queuing and buffering
 */

import { EventEmitter } from 'events';
import { compress, decompress } from 'lz-string';

class EnhancedWebSocketService extends EventEmitter {
  constructor() {
    super();
    this.connections = new Map(); // Multi-provider connections
    this.messageBuffers = new Map(); // Per-provider message buffers
    this.latencyTracking = new Map(); // Latency monitoring
    this.dataValidators = new Map(); // Data validation rules
    this.anomalyDetector = new AnomalyDetector();
    this.connectionPool = new ConnectionPool();
    
    // Enhanced configuration
    this.config = {
      maxConnections: 10,
      compressionThreshold: 1024, // Compress messages > 1KB
      bufferSize: 1000,
      latencyThreshold: 2000, // 2 seconds warning threshold
      reconnectStrategies: {
        exponential: { base: 1000, max: 30000, factor: 2 },
        linear: { base: 1000, increment: 1000, max: 10000 }
      },
      heartbeatInterval: 30000,
      connectionTimeout: 10000,
      dataValidation: {
        enableAnomalyDetection: true,
        priceDeviationThreshold: 0.1, // 10% price deviation alert
        volumeSpikeFactor: 5 // 5x volume spike detection
      }
    };
    
    // Provider configurations
    this.providers = {
      alpaca: {
        url: import.meta.env.VITE_ALPACA_WS_URL || 'wss://stream.data.alpaca.markets/v2/iex',
        auth: 'api_key',
        dataTypes: ['trades', 'quotes', 'bars', 'lulds', 'cancelErrors', 'corrections']
      },
      td_ameritrade: {
        url: import.meta.env.VITE_TD_WS_URL || 'wss://streamer-api.tdameritrade.com/ws',
        auth: 'oauth',
        dataTypes: ['QUOTE', 'TIMESALE', 'CHART_EQUITY', 'CHART_FUTURES', 'BOOK']
      }
    };
    
    // Statistics tracking
    this.stats = {
      totalConnections: 0,
      activeConnections: 0,
      messagesReceived: 0,
      messagesSent: 0,
      compressionRatio: 0,
      averageLatency: 0,
      anomaliesDetected: 0,
      connectionFailures: 0,
      dataValidationErrors: 0
    };
  }

  /**
   * Initialize enhanced WebSocket service
   */
  async initialize() {
    try {
      // Initialize connection pool
      await this.connectionPool.initialize();
      
      // Setup data validators
      this.setupDataValidators();
      
      // Initialize anomaly detector
      await this.anomalyDetector.initialize();
      
      console.log('Enhanced WebSocket Service initialized successfully');
      this.emit('initialized');
      
    } catch (error) {
      console.error('Failed to initialize Enhanced WebSocket Service:', error);
      this.emit('error', error);
      throw error;
    }
  }

  /**
   * Connect to multiple providers with load balancing
   */
  async connectMultiProvider(providers = ['alpaca', 'td_ameritrade']) {
    const connectionPromises = providers.map(provider => this.connectProvider(provider));
    
    try {
      const results = await Promise.allSettled(connectionPromises);
      const successful = results.filter(r => r.status === 'fulfilled').length;
      const failed = results.filter(r => r.status === 'rejected').length;
      
      console.log(`Multi-provider connection: ${successful} successful, ${failed} failed`);
      
      if (successful === 0) {
        throw new Error('All provider connections failed');
      }
      
      return { successful, failed, results };
      
    } catch (error) {
      console.error('Multi-provider connection failed:', error);
      throw error;
    }
  }

  /**
   * Connect to a specific provider
   */
  async connectProvider(providerName) {
    const provider = this.providers[providerName];
    if (!provider) {
      throw new Error(`Unknown provider: ${providerName}`);
    }

    return new Promise((resolve, reject) => {
      try {
        // Get connection from pool or create new one
        const connection = this.connectionPool.getConnection(providerName, provider.url);
        
        connection.onopen = () => {
          console.log(`✅ Connected to ${providerName}`);
          this.connections.set(providerName, connection);
          this.stats.activeConnections++;
          
          // Initialize provider-specific setup
          this.initializeProviderConnection(providerName, connection);
          
          resolve(connection);
        };

        connection.onmessage = (event) => {
          this.handleProviderMessage(providerName, event);
        };

        connection.onclose = (event) => {
          this.handleProviderDisconnect(providerName, event);
        };

        connection.onerror = (error) => {
          console.error(`❌ ${providerName} connection error:`, error);
          this.stats.connectionFailures++;
          reject(error);
        };

      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Initialize provider-specific connection setup
   */
  initializeProviderConnection(providerName, connection) {
    // Setup message buffer
    this.messageBuffers.set(providerName, []);
    
    // Setup latency tracking
    this.latencyTracking.set(providerName, {
      lastPing: null,
      samples: [],
      average: 0
    });
    
    // Start heartbeat
    this.startProviderHeartbeat(providerName);
    
    // Authenticate if required
    this.authenticateProvider(providerName, connection);
  }

  /**
   * Handle provider-specific authentication
   */
  authenticateProvider(providerName, connection) {
    const provider = this.providers[providerName];
    
    switch (provider.auth) {
      case 'api_key':
        this.authenticateApiKey(providerName, connection);
        break;
      case 'oauth':
        this.authenticateOAuth(providerName, connection);
        break;
      default:
        console.warn(`Unknown auth method for ${providerName}: ${provider.auth}`);
    }
  }

  /**
   * API Key authentication (Alpaca)
   */
  authenticateApiKey(providerName, connection) {
    const apiKey = localStorage.getItem(`${providerName}_api_key`);
    const apiSecret = localStorage.getItem(`${providerName}_api_secret`);
    
    if (!apiKey || !apiSecret) {
      console.error(`${providerName} API credentials not found`);
      return;
    }

    const authMessage = {
      action: 'auth',
      key: apiKey,
      secret: apiSecret
    };

    this.sendProviderMessage(providerName, authMessage);
  }

  /**
   * OAuth authentication (TD Ameritrade)
   */
  authenticateOAuth(providerName, connection) {
    const accessToken = localStorage.getItem(`${providerName}_access_token`);
    
    if (!accessToken) {
      console.error(`${providerName} OAuth token not found`);
      return;
    }

    const authMessage = {
      service: 'ADMIN',
      command: 'LOGIN',
      requestid: Date.now(),
      account: localStorage.getItem(`${providerName}_account_id`),
      source: localStorage.getItem(`${providerName}_source_id`),
      parameters: {
        credential: `userid=${localStorage.getItem(`${providerName}_user_id`)}&token=${accessToken}&company=${localStorage.getItem(`${providerName}_company`)}&segment=${localStorage.getItem(`${providerName}_segment`)}&cddomain=${localStorage.getItem(`${providerName}_cd_domain`)}&usergroup=${localStorage.getItem(`${providerName}_user_group`)}&accesslevel=${localStorage.getItem(`${providerName}_access_level`)}&authorized=Y&timestamp=${Date.now()}&appid=${localStorage.getItem(`${providerName}_app_id`)}&acl=${localStorage.getItem(`${providerName}_acl`)}`
      }
    };

    this.sendProviderMessage(providerName, authMessage);
  }

  /**
   * Send message to specific provider with compression
   */
  sendProviderMessage(providerName, message) {
    const connection = this.connections.get(providerName);
    if (!connection || connection.readyState !== WebSocket.OPEN) {
      // Buffer message for later
      this.bufferMessage(providerName, message);
      return false;
    }

    try {
      let messageStr = JSON.stringify(message);
      
      // Compress large messages
      if (messageStr.length > this.config.compressionThreshold) {
        messageStr = compress(messageStr);
        message._compressed = true;
      }
      
      // Track latency for ping messages
      if (message.action === 'ping' || message.service === 'ADMIN') {
        this.latencyTracking.get(providerName).lastPing = Date.now();
      }
      
      connection.send(messageStr);
      this.stats.messagesSent++;
      
      return true;
      
    } catch (error) {
      console.error(`Failed to send message to ${providerName}:`, error);
      return false;
    }
  }

  /**
   * Handle provider message with validation and anomaly detection
   */
  handleProviderMessage(providerName, event) {
    try {
      let data = event.data;
      
      // Decompress if needed
      if (data.startsWith('{"_compressed":true')) {
        data = decompress(data);
      }
      
      const message = JSON.parse(data);
      this.stats.messagesReceived++;
      
      // Update latency tracking
      this.updateLatencyTracking(providerName, message);
      
      // Validate message structure
      if (!this.validateProviderMessage(providerName, message)) {
        this.stats.dataValidationErrors++;
        console.warn(`Invalid message from ${providerName}:`, message);
        return;
      }
      
      // Anomaly detection
      if (this.config.dataValidation.enableAnomalyDetection) {
        const anomaly = this.anomalyDetector.detectAnomaly(providerName, message);
        if (anomaly) {
          this.stats.anomaliesDetected++;
          this.emit('anomaly', { provider: providerName, message, anomaly });
        }
      }
      
      // Process message based on type
      this.processProviderMessage(providerName, message);
      
    } catch (error) {
      console.error(`Error handling message from ${providerName}:`, error);
      this.stats.dataValidationErrors++;
    }
  }

  /**
   * Update latency tracking
   */
  updateLatencyTracking(providerName, message) {
    const tracking = this.latencyTracking.get(providerName);
    if (!tracking) return;
    
    // Calculate latency for pong responses
    if (message.action === 'pong' || message.service === 'ADMIN') {
      if (tracking.lastPing) {
        const latency = Date.now() - tracking.lastPing;
        tracking.samples.push(latency);
        
        // Keep only last 100 samples
        if (tracking.samples.length > 100) {
          tracking.samples.shift();
        }
        
        // Calculate average
        tracking.average = tracking.samples.reduce((a, b) => a + b, 0) / tracking.samples.length;
        
        // Alert on high latency
        if (latency > this.config.latencyThreshold) {
          this.emit('highLatency', { provider: providerName, latency });
        }
        
        tracking.lastPing = null;
      }
    }
  }

  /**
   * Validate provider message structure
   */
  validateProviderMessage(providerName, message) {
    const validator = this.dataValidators.get(providerName);
    return validator ? validator.validate(message) : true;
  }

  /**
   * Process provider message
   */
  processProviderMessage(providerName, message) {
    // Emit provider-specific event
    this.emit(`${providerName}_message`, message);
    
    // Emit data-type specific events
    if (message.type) {
      this.emit(`${providerName}_${message.type}`, message);
    }
    
    // Emit generic message event
    this.emit('message', { provider: providerName, message });
  }

  /**
   * Buffer message for later sending
   */
  bufferMessage(providerName, message) {
    const buffer = this.messageBuffers.get(providerName) || [];
    buffer.push(message);
    
    // Limit buffer size
    if (buffer.length > this.config.bufferSize) {
      buffer.shift(); // Remove oldest message
    }
    
    this.messageBuffers.set(providerName, buffer);
  }

  /**
   * Process buffered messages
   */
  processBufferedMessages(providerName) {
    const buffer = this.messageBuffers.get(providerName) || [];
    
    while (buffer.length > 0) {
      const message = buffer.shift();
      if (!this.sendProviderMessage(providerName, message)) {
        // Put it back if send failed
        buffer.unshift(message);
        break;
      }
    }
  }

  /**
   * Start heartbeat for provider
   */
  startProviderHeartbeat(providerName) {
    const interval = setInterval(() => {
      const connection = this.connections.get(providerName);
      if (!connection || connection.readyState !== WebSocket.OPEN) {
        clearInterval(interval);
        return;
      }
      
      // Send provider-specific ping
      if (providerName === 'alpaca') {
        this.sendProviderMessage(providerName, { action: 'ping', timestamp: Date.now() });
      } else if (providerName === 'td_ameritrade') {
        this.sendProviderMessage(providerName, { 
          service: 'ADMIN', 
          command: 'PING', 
          requestid: Date.now() 
        });
      }
      
    }, this.config.heartbeatInterval);
  }

  /**
   * Setup data validators for each provider
   */
  setupDataValidators() {
    // Alpaca data validator
    this.dataValidators.set('alpaca', {
      validate: (message) => {
        if (!message || typeof message !== 'object') return false;
        
        // Validate market data
        if (message.T && message.S) {
          return typeof message.S === 'string' && typeof message.p === 'number';
        }
        
        return true;
      }
    });
    
    // TD Ameritrade data validator
    this.dataValidators.set('td_ameritrade', {
      validate: (message) => {
        if (!message || typeof message !== 'object') return false;
        
        // Validate quote data
        if (message.service === 'QUOTE' && message.content) {
          return Array.isArray(message.content) && message.content.length > 0;
        }
        
        return true;
      }
    });
  }

  /**
   * Subscribe to symbols across multiple providers
   */
  subscribeMultiProvider(symbols, dataTypes = ['trades', 'quotes']) {
    const subscriptions = {};
    
    for (const [providerName, connection] of this.connections) {
      if (connection.readyState === WebSocket.OPEN) {
        subscriptions[providerName] = this.subscribeProvider(providerName, symbols, dataTypes);
      }
    }
    
    return subscriptions;
  }

  /**
   * Subscribe to provider-specific data
   */
  subscribeProvider(providerName, symbols, dataTypes) {
    const provider = this.providers[providerName];
    if (!provider) return false;
    
    let subscriptionMessage;
    
    if (providerName === 'alpaca') {
      subscriptionMessage = {
        action: 'subscribe',
        trades: dataTypes.includes('trades') ? symbols : [],
        quotes: dataTypes.includes('quotes') ? symbols : [],
        bars: dataTypes.includes('bars') ? symbols : []
      };
    } else if (providerName === 'td_ameritrade') {
      subscriptionMessage = {
        service: 'QUOTE',
        command: 'SUBS',
        requestid: Date.now(),
        account: localStorage.getItem(`${providerName}_account_id`),
        source: localStorage.getItem(`${providerName}_source_id`),
        parameters: {
          keys: symbols.join(','),
          fields: '0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52'
        }
      };
    }
    
    return this.sendProviderMessage(providerName, subscriptionMessage);
  }

  /**
   * Get enhanced statistics
   */
  getEnhancedStats() {
    const providerStats = {};
    
    for (const [providerName] of this.connections) {
      const latency = this.latencyTracking.get(providerName);
      const buffer = this.messageBuffers.get(providerName) || [];
      
      providerStats[providerName] = {
        connected: this.connections.get(providerName)?.readyState === WebSocket.OPEN,
        averageLatency: latency?.average || 0,
        bufferedMessages: buffer.length,
        latencySamples: latency?.samples.length || 0
      };
    }
    
    return {
      ...this.stats,
      providers: providerStats,
      anomalyDetector: this.anomalyDetector.getStats(),
      connectionPool: this.connectionPool.getStats()
    };
  }

  /**
   * Clean up all connections
   */
  destroy() {
    // Close all connections
    for (const [providerName, connection] of this.connections) {
      if (connection.readyState === WebSocket.OPEN) {
        connection.close(1000, 'Service shutdown');
      }
    }
    
    // Clear all data
    this.connections.clear();
    this.messageBuffers.clear();
    this.latencyTracking.clear();
    
    // Destroy connection pool
    this.connectionPool.destroy();
    
    // Destroy anomaly detector
    this.anomalyDetector.destroy();
  }
}

/**
 * Anomaly Detection System
 */
class AnomalyDetector {
  constructor() {
    this.priceHistory = new Map();
    this.volumeHistory = new Map();
    this.alertThresholds = {
      priceDeviation: 0.1, // 10%
      volumeSpike: 5, // 5x normal
      suspiciousPatterns: true
    };
    this.stats = {
      totalChecks: 0,
      anomaliesFound: 0,
      priceAnomalies: 0,
      volumeAnomalies: 0,
      patternAnomalies: 0
    };
  }

  async initialize() {
    console.log('Anomaly Detector initialized');
  }

  detectAnomaly(provider, message) {
    this.stats.totalChecks++;
    
    // Skip non-market data
    if (!message.S || !message.p) return null;
    
    const symbol = message.S;
    const price = message.p;
    const volume = message.v || 0;
    
    const anomalies = [];
    
    // Price anomaly detection
    const priceAnomaly = this.detectPriceAnomaly(symbol, price);
    if (priceAnomaly) {
      anomalies.push(priceAnomaly);
      this.stats.priceAnomalies++;
    }
    
    // Volume anomaly detection
    const volumeAnomaly = this.detectVolumeAnomaly(symbol, volume);
    if (volumeAnomaly) {
      anomalies.push(volumeAnomaly);
      this.stats.volumeAnomalies++;
    }
    
    if (anomalies.length > 0) {
      this.stats.anomaliesFound++;
      return {
        symbol,
        provider,
        anomalies,
        timestamp: Date.now()
      };
    }
    
    return null;
  }

  detectPriceAnomaly(symbol, currentPrice) {
    const history = this.priceHistory.get(symbol) || [];
    
    if (history.length < 10) {
      // Not enough data yet
      history.push(currentPrice);
      this.priceHistory.set(symbol, history);
      return null;
    }
    
    // Calculate average and standard deviation
    const avg = history.reduce((a, b) => a + b, 0) / history.length;
    const stdDev = Math.sqrt(history.reduce((sq, n) => sq + Math.pow(n - avg, 2), 0) / history.length);
    
    // Check for significant deviation
    const deviation = Math.abs(currentPrice - avg) / avg;
    
    if (deviation > this.alertThresholds.priceDeviation) {
      return {
        type: 'price_anomaly',
        severity: deviation > 0.2 ? 'high' : 'medium',
        currentPrice,
        averagePrice: avg,
        deviation: deviation * 100,
        message: `Price deviation of ${(deviation * 100).toFixed(2)}% detected`
      };
    }
    
    // Update history
    history.push(currentPrice);
    if (history.length > 100) {
      history.shift();
    }
    this.priceHistory.set(symbol, history);
    
    return null;
  }

  detectVolumeAnomaly(symbol, currentVolume) {
    const history = this.volumeHistory.get(symbol) || [];
    
    if (history.length < 10 || currentVolume === 0) {
      history.push(currentVolume);
      this.volumeHistory.set(symbol, history);
      return null;
    }
    
    // Calculate average volume
    const avgVolume = history.reduce((a, b) => a + b, 0) / history.length;
    
    // Check for volume spike
    const volumeRatio = currentVolume / avgVolume;
    
    if (volumeRatio > this.alertThresholds.volumeSpike) {
      return {
        type: 'volume_anomaly',
        severity: volumeRatio > 10 ? 'high' : 'medium',
        currentVolume,
        averageVolume: avgVolume,
        ratio: volumeRatio,
        message: `Volume spike of ${volumeRatio.toFixed(2)}x detected`
      };
    }
    
    // Update history
    history.push(currentVolume);
    if (history.length > 100) {
      history.shift();
    }
    this.volumeHistory.set(symbol, history);
    
    return null;
  }

  getStats() {
    return this.stats;
  }

  destroy() {
    this.priceHistory.clear();
    this.volumeHistory.clear();
  }
}

/**
 * Connection Pool for Load Balancing
 */
class ConnectionPool {
  constructor() {
    this.pools = new Map();
    this.stats = {
      totalConnections: 0,
      activeConnections: 0,
      failedConnections: 0
    };
  }

  async initialize() {
    console.log('Connection Pool initialized');
  }

  getConnection(provider, url) {
    const pool = this.pools.get(provider) || [];
    
    // Try to find an available connection
    for (const conn of pool) {
      if (conn.readyState === WebSocket.OPEN) {
        return conn;
      }
    }
    
    // Create new connection
    const connection = new WebSocket(url);
    pool.push(connection);
    this.pools.set(provider, pool);
    
    this.stats.totalConnections++;
    
    return connection;
  }

  getStats() {
    return this.stats;
  }

  destroy() {
    for (const [provider, pool] of this.pools) {
      pool.forEach(conn => {
        if (conn.readyState === WebSocket.OPEN) {
          conn.close();
        }
      });
    }
    this.pools.clear();
  }
}

export default EnhancedWebSocketService;
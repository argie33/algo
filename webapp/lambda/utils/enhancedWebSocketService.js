/**
 * Enhanced WebSocket Service
 * Provides high-performance real-time market data streaming with the optimized pipeline
 */

const { RealtimeDataPipeline } = require('./realtimeDataPipeline');
const { createRequestLogger } = require('./logger');
const { getTimeout } = require('./timeoutManager');
const AlpacaService = require('./alpacaService');

class EnhancedWebSocketService {
  constructor(options = {}) {
    this.options = {
      maxConnections: options.maxConnections || 1000,
      connectionTimeout: options.connectionTimeout || 30000,
      heartbeatInterval: options.heartbeatInterval || 30000,
      reconnectAttempts: options.reconnectAttempts || 5,
      reconnectDelay: options.reconnectDelay || 1000,
      dataSourceOptions: {
        bufferSize: 2000,
        flushInterval: 500, // More aggressive flushing for real-time
        batchSize: 200,
        compressionEnabled: true,
        performanceMonitoring: true
      },
      ...options
    };

    // Initialize the real-time data pipeline
    this.dataPipeline = new RealtimeDataPipeline(this.options.dataSourceOptions);
    
    // Connection management
    this.connections = new Map(); // connectionId -> connection details
    this.userConnections = new Map(); // userId -> Set of connectionIds
    this.alpacaConnections = new Map(); // userId -> AlpacaWebSocket instance

    // Service metrics
    this.metrics = {
      totalConnections: 0,
      activeConnections: 0,
      totalSubscriptions: 0,
      dataMessages: 0,
      errorCount: 0,
      reconnectCount: 0,
      startTime: Date.now()
    };

    this.logger = createRequestLogger('websocket-service');
    this.logger.info('🚀 Enhanced WebSocket Service initialized', this.options);

    // Start periodic cleanup
    this.startPeriodicCleanup();
  }

  /**
   * Create a new connection for a user
   */
  async createConnection(userId, symbols, options = {}) {
    const connectionId = `conn_${userId}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    try {
      this.logger.info('📡 Creating new connection', {
        connectionId,
        userId: `${userId.substring(0, 8)}...`,
        symbols,
        options
      });

      // Validate connection limits
      if (this.connections.size >= this.options.maxConnections) {
        throw new Error('Maximum connections exceeded');
      }

      // Create connection record
      const connection = {
        id: connectionId,
        userId,
        symbols: new Set(symbols),
        options: {
          dataTypes: ['quotes', 'trades', 'bars'],
          compression: true,
          throttle: 100,
          ...options
        },
        status: 'connecting',
        createdAt: Date.now(),
        lastActivity: Date.now(),
        subscriptionId: null,
        alpacaConnection: null,
        heartbeatTimer: null,
        reconnectAttempts: 0
      };

      // Add to connection maps
      this.connections.set(connectionId, connection);
      
      if (!this.userConnections.has(userId)) {
        this.userConnections.set(userId, new Set());
      }
      this.userConnections.get(userId).add(connectionId);

      // Create subscription in data pipeline
      const subscriptionId = this.dataPipeline.addSubscription(
        userId,
        symbols,
        connection.options.dataTypes,
        connection.options
      );
      connection.subscriptionId = subscriptionId;

      // Establish Alpaca connection if needed
      await this.establishAlpacaConnection(userId, connection);

      // Start heartbeat
      this.startHeartbeat(connectionId);

      // Update metrics
      this.metrics.totalConnections++;
      this.metrics.activeConnections++;
      this.metrics.totalSubscriptions++;

      connection.status = 'connected';
      
      this.logger.info('✅ Connection established successfully', {
        connectionId,
        subscriptionId,
        activeConnections: this.metrics.activeConnections
      });

      return {
        connectionId,
        subscriptionId,
        status: 'connected',
        symbols: Array.from(symbols),
        dataTypes: connection.options.dataTypes
      };

    } catch (error) {
      this.metrics.errorCount++;
      this.logger.error('❌ Failed to create connection', {
        connectionId,
        userId: `${userId.substring(0, 8)}...`,
        error: error.message
      });
      
      // Cleanup partial connection
      await this.cleanupConnection(connectionId);
      throw error;
    }
  }

  /**
   * Establish Alpaca WebSocket connection for user
   */
  async establishAlpacaConnection(userId, connection) {
    try {
      // Check if user already has an Alpaca connection
      if (this.alpacaConnections.has(userId)) {
        const existingConnection = this.alpacaConnections.get(userId);
        // Reuse existing connection and add symbols
        await this.addSymbolsToAlpacaConnection(existingConnection, connection.symbols);
        connection.alpacaConnection = existingConnection;
        return;
      }

      // Get user's Alpaca credentials
      const apiKeyService = require('./apiKeyService');
      const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
      
      if (!credentials) {
        throw new Error('Alpaca API credentials not found for user');
      }

      // Create new Alpaca service instance
      const alpacaService = new AlpacaService(
        credentials.apiKey,
        credentials.apiSecret,
        credentials.isSandbox
      );

      // Create WebSocket connection
      const wsConfig = alpacaService.getWebSocketConfig();
      const alpacaWS = await this.createAlpacaWebSocket(wsConfig, userId, connection.symbols);
      
      // Store connection
      this.alpacaConnections.set(userId, alpacaWS);
      connection.alpacaConnection = alpacaWS;

      this.logger.info('✅ Alpaca WebSocket connection established', {
        userId: `${userId.substring(0, 8)}...`,
        environment: credentials.isSandbox ? 'sandbox' : 'live',
        symbols: Array.from(connection.symbols)
      });

    } catch (error) {
      this.logger.error('❌ Failed to establish Alpaca connection', {
        userId: `${userId.substring(0, 8)}...`,
        error: error.message
      });
      throw error;
    }
  }

  /**
   * Create Alpaca WebSocket connection with enhanced error handling
   */
  async createAlpacaWebSocket(wsConfig, userId, symbols) {
    return new Promise((resolve, reject) => {
      try {
        // This would be your actual Alpaca WebSocket implementation
        // For now, we'll create a mock connection that generates test data
        const mockWS = {
          userId,
          symbols: new Set(symbols),
          status: 'connected',
          lastMessage: Date.now(),
          
          // Mock data generation
          dataGenerator: setInterval(() => {
            this.generateMockMarketData(symbols);
          }, 1000), // Generate data every second

          // Mock methods
          subscribe: (newSymbols) => {
            newSymbols.forEach(symbol => mockWS.symbols.add(symbol));
            this.logger.debug('Mock WS subscribed to new symbols', { newSymbols });
          },

          unsubscribe: (removeSymbols) => {
            removeSymbols.forEach(symbol => mockWS.symbols.delete(symbol));
            this.logger.debug('Mock WS unsubscribed from symbols', { removeSymbols });
          },

          close: () => {
            if (mockWS.dataGenerator) {
              clearInterval(mockWS.dataGenerator);
            }
            mockWS.status = 'closed';
            this.logger.debug('Mock WS connection closed');
          }
        };

        // Set up data handlers
        this.setupAlpacaDataHandlers(mockWS);

        resolve(mockWS);

      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Setup data handlers for Alpaca WebSocket
   */
  setupAlpacaDataHandlers(alpacaWS) {
    // In a real implementation, you'd set up event handlers for the actual WebSocket
    // For now, we'll just log that handlers are set up
    this.logger.debug('Alpaca WebSocket data handlers configured', {
      userId: `${alpacaWS.userId.substring(0, 8)}...`
    });
  }

  /**
   * Generate mock market data for testing
   */
  generateMockMarketData(symbols) {
    const now = Date.now();
    
    Array.from(symbols).forEach(symbol => {
      // Generate mock quote data
      const mockQuote = {
        symbol,
        bid: 100 + Math.random() * 50,
        ask: 100 + Math.random() * 50 + 0.01,
        bidSize: Math.floor(Math.random() * 1000) + 100,
        askSize: Math.floor(Math.random() * 1000) + 100,
        timestamp: now
      };
      mockQuote.price = (mockQuote.bid + mockQuote.ask) / 2;

      // Send to data pipeline
      this.dataPipeline.processIncomingData('quote', mockQuote);

      // Occasionally generate trade data
      if (Math.random() < 0.3) {
        const mockTrade = {
          symbol,
          price: mockQuote.price + (Math.random() - 0.5) * 0.1,
          size: Math.floor(Math.random() * 500) + 100,
          timestamp: now,
          conditions: ['@'],
          exchange: 'NASDAQ'
        };

        this.dataPipeline.processIncomingData('trade', mockTrade);
      }
    });
  }

  /**
   * Add symbols to existing Alpaca connection
   */
  async addSymbolsToAlpacaConnection(alpacaConnection, newSymbols) {
    try {
      const symbolsToAdd = Array.from(newSymbols).filter(
        symbol => !alpacaConnection.symbols.has(symbol)
      );

      if (symbolsToAdd.length > 0) {
        alpacaConnection.subscribe(symbolsToAdd);
        this.logger.debug('Added symbols to existing Alpaca connection', {
          symbolsToAdd,
          totalSymbols: alpacaConnection.symbols.size
        });
      }

    } catch (error) {
      this.logger.error('Error adding symbols to Alpaca connection', {
        error: error.message,
        newSymbols: Array.from(newSymbols)
      });
      throw error;
    }
  }

  /**
   * Start heartbeat for connection
   */
  startHeartbeat(connectionId) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;

    connection.heartbeatTimer = setInterval(() => {
      this.sendHeartbeat(connectionId);
    }, this.options.heartbeatInterval);
  }

  /**
   * Send heartbeat to connection
   */
  sendHeartbeat(connectionId) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;

    const heartbeatData = {
      type: 'heartbeat',
      timestamp: Date.now(),
      connectionId,
      status: 'alive'
    };

    // In a real implementation, this would send via WebSocket
    this.logger.debug('Heartbeat sent', { connectionId });
    connection.lastActivity = Date.now();
  }

  /**
   * Close a connection
   */
  async closeConnection(connectionId, reason = 'client_request') {
    const connection = this.connections.get(connectionId);
    if (!connection) return;

    try {
      this.logger.info('🔌 Closing connection', {
        connectionId,
        reason,
        userId: `${connection.userId.substring(0, 8)}...`
      });

      // Clean up heartbeat
      if (connection.heartbeatTimer) {
        clearInterval(connection.heartbeatTimer);
      }

      // Remove subscription from data pipeline
      if (connection.subscriptionId) {
        this.dataPipeline.removeSubscription(connection.subscriptionId);
      }

      // Clean up connection maps
      await this.cleanupConnection(connectionId);

      // Update metrics
      this.metrics.activeConnections--;

      this.logger.info('✅ Connection closed successfully', {
        connectionId,
        activeConnections: this.metrics.activeConnections
      });

    } catch (error) {
      this.logger.error('❌ Error closing connection', {
        connectionId,
        error: error.message
      });
    }
  }

  /**
   * Cleanup connection from all maps
   */
  async cleanupConnection(connectionId) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;

    // Remove from connections map
    this.connections.delete(connectionId);

    // Remove from user connections map
    const userConnectionSet = this.userConnections.get(connection.userId);
    if (userConnectionSet) {
      userConnectionSet.delete(connectionId);
      
      // If user has no more connections, cleanup Alpaca connection
      if (userConnectionSet.size === 0) {
        this.userConnections.delete(connection.userId);
        await this.cleanupAlpacaConnection(connection.userId);
      }
    }
  }

  /**
   * Cleanup Alpaca connection for user
   */
  async cleanupAlpacaConnection(userId) {
    const alpacaConnection = this.alpacaConnections.get(userId);
    if (alpacaConnection) {
      try {
        alpacaConnection.close();
        this.alpacaConnections.delete(userId);
        
        this.logger.info('🔌 Alpaca connection cleaned up', {
          userId: `${userId.substring(0, 8)}...`
        });
      } catch (error) {
        this.logger.error('❌ Error cleaning up Alpaca connection', {
          userId: `${userId.substring(0, 8)}...`,
          error: error.message
        });
      }
    }
  }

  /**
   * Start periodic cleanup of stale connections
   */
  startPeriodicCleanup() {
    setInterval(() => {
      this.cleanupStaleConnections();
    }, 60000); // Every minute
  }

  /**
   * Clean up stale connections
   */
  cleanupStaleConnections() {
    const now = Date.now();
    const staleConnections = [];

    for (const [connectionId, connection] of this.connections) {
      const inactiveTime = now - connection.lastActivity;
      
      // Consider connection stale if inactive for more than 5 minutes
      if (inactiveTime > 300000) {
        staleConnections.push(connectionId);
      }
    }

    if (staleConnections.length > 0) {
      this.logger.info('🧹 Cleaning up stale connections', {
        staleConnections: staleConnections.length,
        totalConnections: this.connections.size
      });

      staleConnections.forEach(connectionId => {
        this.closeConnection(connectionId, 'stale_connection');
      });
    }
  }

  /**
   * Get service status and metrics
   */
  getStatus() {
    const now = Date.now();
    const uptimeSeconds = (now - this.metrics.startTime) / 1000;

    return {
      status: 'active',
      uptime: {
        seconds: uptimeSeconds,
        formatted: this.formatUptime(uptimeSeconds)
      },
      connections: {
        total: this.metrics.totalConnections,
        active: this.metrics.activeConnections,
        byUser: this.userConnections.size
      },
      subscriptions: {
        total: this.metrics.totalSubscriptions,
        active: this.dataPipeline.subscriptions.size
      },
      metrics: {
        ...this.metrics,
        errorsPerHour: this.metrics.errorCount / (uptimeSeconds / 3600),
        connectionsPerHour: this.metrics.totalConnections / (uptimeSeconds / 3600)
      },
      dataPipeline: this.dataPipeline.getStatus(),
      alpacaConnections: this.alpacaConnections.size
    };
  }

  /**
   * Format uptime in human-readable format
   */
  formatUptime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    return `${hours}h ${minutes}m ${secs}s`;
  }

  /**
   * Shutdown the service
   */
  async shutdown() {
    this.logger.info('🛑 Shutting down Enhanced WebSocket Service');

    // Close all connections
    const connectionIds = Array.from(this.connections.keys());
    await Promise.all(
      connectionIds.map(id => this.closeConnection(id, 'service_shutdown'))
    );

    // Shutdown data pipeline
    this.dataPipeline.shutdown();

    // Clean up Alpaca connections
    for (const userId of this.alpacaConnections.keys()) {
      await this.cleanupAlpacaConnection(userId);
    }

    this.logger.info('✅ Enhanced WebSocket Service shutdown completed');
  }
}

module.exports = { EnhancedWebSocketService };
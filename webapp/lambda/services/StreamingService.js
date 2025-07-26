/**
 * Streaming Service for Real-time AI Responses
 * 
 * Handles WebSocket connections and real-time streaming of AI responses
 * Integrates with Enhanced Bedrock Service for streaming capabilities
 */

const { Server } = require('ws');
const enhancedBedrockService = require('./EnhancedBedrockService');
const conversationStore = require('../utils/conversationStore');
const { query } = require('../utils/database');

class StreamingService {
  constructor() {
    this.connections = new Map(); // connectionId -> connection info
    this.activeStreams = new Map(); // streamId -> stream info
    this.wsServer = null;
    
    // Configuration
    this.config = {
      heartbeatInterval: 30000, // 30 seconds
      maxConnections: 1000,
      streamTimeout: 120000, // 2 minutes
      rateLimitWindow: 60000, // 1 minute
      rateLimitRequests: 30
    };
    
    // Rate limiting
    this.rateLimits = new Map(); // connectionId -> request timestamps
    
    // Statistics
    this.stats = {
      totalConnections: 0,
      activeConnections: 0,
      totalStreams: 0,
      activeStreams: 0,
      messagesSent: 0,
      errors: 0
    };
  }

  /**
   * Initialize WebSocket server
   */
  initialize(server) {
    try {
      this.wsServer = new Server({ 
        server,
        path: '/ws/ai',
        maxPayload: 16 * 1024 * 1024, // 16MB
        perMessageDeflate: true
      });
      
      this.wsServer.on('connection', (ws, request) => {
        this.handleConnection(ws, request);
      });
      
      // Start heartbeat
      this.startHeartbeat();
      
      console.log('✅ Streaming service initialized');
      return true;
    } catch (error) {
      console.error('❌ Failed to initialize streaming service:', error);
      return false;
    }
  }

  /**
   * Handle new WebSocket connection
   */
  handleConnection(ws, request) {
    const connectionId = this.generateConnectionId();
    const userId = this.extractUserId(request); // Extract from auth headers
    const userAgent = request.headers['user-agent'] || 'unknown';
    const ipAddress = request.socket.remoteAddress;
    
    console.log(`🔌 New WebSocket connection: ${connectionId} for user ${userId}`);
    
    // Store connection info
    const connectionInfo = {
      id: connectionId,
      ws: ws,
      userId: userId,
      userAgent: userAgent,
      ipAddress: ipAddress,
      connectedAt: new Date(),
      lastActivity: new Date(),
      isAlive: true,
      messageCount: 0
    };
    
    this.connections.set(connectionId, connectionInfo);
    this.stats.totalConnections++;
    this.stats.activeConnections++;
    
    // Initialize rate limiting
    this.rateLimits.set(connectionId, []);
    
    // Set up connection event handlers
    ws.on('message', (data) => {
      this.handleMessage(connectionId, data);
    });
    
    ws.on('close', (code, reason) => {
      this.handleDisconnection(connectionId, code, reason);
    });
    
    ws.on('error', (error) => {
      this.handleConnectionError(connectionId, error);
    });
    
    ws.on('pong', () => {
      const connection = this.connections.get(connectionId);
      if (connection) {
        connection.isAlive = true;
        connection.lastActivity = new Date();
      }
    });
    
    // Send welcome message
    this.sendToConnection(connectionId, {
      type: 'connection_established',
      connectionId: connectionId,
      features: {
        streaming: true,
        realTime: true,
        rateLimitPerMinute: this.config.rateLimitRequests
      },
      timestamp: new Date().toISOString()
    });
    
    // Store connection in database
    this.storeConnectionInDB(connectionInfo);
  }

  /**
   * Handle incoming WebSocket message
   */
  async handleMessage(connectionId, data) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;
    
    connection.lastActivity = new Date();
    connection.messageCount++;
    
    try {
      const message = JSON.parse(data.toString());
      
      // Rate limiting check
      if (!this.checkRateLimit(connectionId)) {
        this.sendToConnection(connectionId, {
          type: 'error',
          error: 'Rate limit exceeded',
          retryAfter: 60,
          timestamp: new Date().toISOString()
        });
        return;
      }
      
      switch (message.type) {
        case 'ai_chat_request':
          await this.handleChatRequest(connectionId, message);
          break;
        case 'stream_stop':
          await this.handleStreamStop(connectionId, message);
          break;
        case 'ping':
          this.sendToConnection(connectionId, { type: 'pong', timestamp: new Date().toISOString() });
          break;
        default:
          this.sendToConnection(connectionId, {
            type: 'error',
            error: `Unknown message type: ${message.type}`,
            timestamp: new Date().toISOString()
          });
      }
      
    } catch (error) {
      console.error(`❌ Error handling message from ${connectionId}:`, error);
      this.sendToConnection(connectionId, {
        type: 'error',
        error: 'Invalid message format',
        timestamp: new Date().toISOString()
      });
    }
  }

  /**
   * Handle AI chat request with streaming
   */
  async handleChatRequest(connectionId, message) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;
    
    const { content, conversationId = 'default', context = {}, options = {} } = message;
    
    if (!content || !content.trim()) {
      this.sendToConnection(connectionId, {
        type: 'error',
        error: 'Message content is required',
        timestamp: new Date().toISOString()
      });
      return;
    }
    
    const streamId = this.generateStreamId();
    const messageId = Date.now();
    
    console.log(`💬 Processing chat request ${messageId} for user ${connection.userId}`);
    
    try {
      // Store user message
      await conversationStore.addMessage(connection.userId, conversationId, {
        id: messageId,
        type: 'user',
        content: content.trim(),
        context: context,
        timestamp: new Date()
      });
      
      // Send acknowledgment
      this.sendToConnection(connectionId, {
        type: 'message_received',
        messageId: messageId,
        streamId: streamId,
        conversationId: conversationId,
        timestamp: new Date().toISOString()
      });
      
      // Build enhanced context
      const enhancedContext = await this.buildStreamingContext(connection.userId, conversationId, context);
      
      // Start streaming response
      const streamInfo = {
        id: streamId,
        connectionId: connectionId,
        userId: connection.userId,
        conversationId: conversationId,
        messageId: messageId,
        startTime: Date.now(),
        status: 'active'
      };
      
      this.activeStreams.set(streamId, streamInfo);
      this.stats.totalStreams++;
      this.stats.activeStreams++;
      
      // Generate streaming response
      await this.processStreamingResponse(streamId, content, enhancedContext, options);
      
    } catch (error) {
      console.error(`❌ Error processing chat request:`, error);
      this.sendToConnection(connectionId, {
        type: 'ai_error',
        streamId: streamId,
        error: 'Failed to process chat request',
        details: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }

  /**
   * Process streaming response using Enhanced Bedrock Service
   */
  async processStreamingResponse(streamId, userMessage, context, options) {
    const streamInfo = this.activeStreams.get(streamId);
    if (!streamInfo) return;
    
    const connectionId = streamInfo.connectionId;
    let fullResponse = '';
    let suggestions = [];
    let metadata = {};
    
    try {
      // Use Enhanced Bedrock Service for streaming
      const responseGenerator = enhancedBedrockService.generateStreamingResponse(userMessage, context, options);
      
      for await (const chunk of responseGenerator) {
        // Check if stream is still active
        if (!this.activeStreams.has(streamId)) {
          console.log(`⏹️ Stream ${streamId} was stopped`);
          break;
        }
        
        // Send chunk to client
        this.sendToConnection(connectionId, {
          type: 'ai_response_chunk',
          streamId: streamId,
          ...chunk
        });
        
        this.stats.messagesSent++;
        
        // Handle different chunk types
        if (chunk.type === 'chunk') {
          fullResponse += chunk.content;
        } else if (chunk.type === 'complete') {
          fullResponse = chunk.fullContent;
          suggestions = chunk.suggestions || [];
          metadata = chunk.metadata || {};
          break;
        } else if (chunk.type === 'error') {
          throw new Error(chunk.error);
        }
      }
      
      // Store assistant response
      if (fullResponse) {
        const assistantMessageId = Date.now() + 1;
        await conversationStore.addMessage(streamInfo.userId, streamInfo.conversationId, {
          id: assistantMessageId,
          type: 'assistant',
          content: fullResponse,
          suggestions: suggestions,
          context: {
            streamId: streamId,
            responseTime: Date.now() - streamInfo.startTime,
            ...metadata
          },
          timestamp: new Date()
        });
        
        console.log(`✅ Streaming response completed for ${streamId}`);
      }
      
      // Mark stream as completed
      streamInfo.status = 'completed';
      streamInfo.endTime = Date.now();
      this.stats.activeStreams--;
      
    } catch (error) {
      console.error(`❌ Streaming error for ${streamId}:`, error);
      this.stats.errors++;
      
      // Send error to client
      this.sendToConnection(connectionId, {
        type: 'ai_stream_error',
        streamId: streamId,
        error: error.message,
        timestamp: new Date().toISOString()
      });
      
      // Mark stream as failed
      streamInfo.status = 'failed';
      streamInfo.error = error.message;
      this.stats.activeStreams--;
    } finally {
      // Clean up after delay
      setTimeout(() => {
        this.activeStreams.delete(streamId);
      }, 30000);
    }
  }

  /**
   * Handle stream stop request
   */
  async handleStreamStop(connectionId, message) {
    const { streamId } = message;
    const streamInfo = this.activeStreams.get(streamId);
    
    if (streamInfo && streamInfo.connectionId === connectionId) {
      streamInfo.status = 'stopped';
      this.stats.activeStreams--;
      
      this.sendToConnection(connectionId, {
        type: 'stream_stopped',
        streamId: streamId,
        timestamp: new Date().toISOString()
      });
      
      console.log(`⏹️ Stream ${streamId} stopped by user`);
    }
  }

  /**
   * Handle connection disconnection
   */
  handleDisconnection(connectionId, code, reason) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;
    
    console.log(`🔌 Connection ${connectionId} disconnected (code: ${code})`);
    
    // Stop any active streams for this connection
    for (const [streamId, streamInfo] of this.activeStreams.entries()) {
      if (streamInfo.connectionId === connectionId) {
        streamInfo.status = 'disconnected';
        this.stats.activeStreams--;
        this.activeStreams.delete(streamId);
      }
    }
    
    // Clean up
    this.connections.delete(connectionId);
    this.rateLimits.delete(connectionId);
    this.stats.activeConnections--;
    
    // Update database
    this.updateConnectionInDB(connectionId, { disconnectedAt: new Date() });
  }

  /**
   * Handle connection error
   */
  handleConnectionError(connectionId, error) {
    console.error(`❌ Connection error for ${connectionId}:`, error);
    this.stats.errors++;
    
    const connection = this.connections.get(connectionId);
    if (connection) {
      connection.ws.terminate();
      this.handleDisconnection(connectionId, 1011, 'Internal error');
    }
  }

  /**
   * Send message to specific connection
   */
  sendToConnection(connectionId, data) {
    const connection = this.connections.get(connectionId);
    if (!connection || connection.ws.readyState !== 1) { // WebSocket.OPEN = 1
      return false;
    }
    
    try {
      connection.ws.send(JSON.stringify(data));
      return true;
    } catch (error) {
      console.error(`❌ Failed to send message to ${connectionId}:`, error);
      return false;
    }
  }

  /**
   * Broadcast message to multiple connections
   */
  broadcast(userIds, data) {
    let successCount = 0;
    
    for (const [connectionId, connection] of this.connections.entries()) {
      if (userIds.includes(connection.userId)) {
        if (this.sendToConnection(connectionId, data)) {
          successCount++;
        }
      }
    }
    
    return successCount;
  }

  /**
   * Build streaming context with enhanced data
   */
  async buildStreamingContext(userId, conversationId, baseContext) {
    try {
      // Get recent conversation history
      const recentMessages = await conversationStore.getHistory(userId, conversationId, 10);
      
      // Get portfolio context
      let portfolioContext = null;
      try {
        const portfolioResult = await query(`
          SELECT symbol, quantity, avg_cost, current_price, market_value, unrealized_pl, unrealized_plpc
          FROM portfolio_holdings 
          WHERE user_id = $1
          ORDER BY market_value DESC
          LIMIT 10
        `, [userId]);
        
        if (portfolioResult.rows.length > 0) {
          const totalValue = portfolioResult.rows.reduce((sum, holding) => sum + parseFloat(holding.market_value || 0), 0);
          const totalGainLoss = portfolioResult.rows.reduce((sum, holding) => sum + parseFloat(holding.unrealized_pl || 0), 0);
          
          portfolioContext = {
            holdings: portfolioResult.rows,
            totalValue: totalValue,
            totalGainLoss: totalGainLoss,
            gainLossPercent: totalValue > 0 ? (totalGainLoss / totalValue) * 100 : 0
          };
        }
      } catch (dbError) {
        console.error('Error fetching portfolio context:', dbError);
      }
      
      // Get market context
      let marketContext = null;
      try {
        const marketResult = await query(`
          SELECT symbol, current_price, change_percent, volume
          FROM stocks 
          WHERE symbol IN ('SPY', 'QQQ', 'DIA')
          ORDER BY symbol
        `);
        
        if (marketResult.rows.length > 0) {
          marketContext = {
            indices: {},
            timestamp: new Date().toISOString()
          };
          
          marketResult.rows.forEach(row => {
            const indexName = row.symbol === 'SPY' ? 'sp500' : 
                             row.symbol === 'QQQ' ? 'nasdaq' : 'dow';
            marketContext.indices[indexName] = {
              symbol: row.symbol,
              price: parseFloat(row.current_price || 0),
              change: parseFloat(row.change_percent || 0),
              volume: row.volume
            };
          });
        }
      } catch (dbError) {
        console.error('Error fetching market context:', dbError);
      }
      
      return {
        ...baseContext,
        portfolioContext,
        marketContext,
        recentMessages,
        userId,
        conversationId,
        timestamp: new Date().toISOString(),
        streamingEnabled: true
      };
      
    } catch (error) {
      console.error('Error building streaming context:', error);
      return {
        ...baseContext,
        userId,
        conversationId,
        timestamp: new Date().toISOString(),
        streamingEnabled: true,
        contextError: error.message
      };
    }
  }

  /**
   * Check rate limiting
   */
  checkRateLimit(connectionId) {
    const now = Date.now();
    const requests = this.rateLimits.get(connectionId) || [];
    
    // Remove old requests outside the window
    const recentRequests = requests.filter(timestamp => now - timestamp < this.config.rateLimitWindow);
    
    // Check if under limit
    if (recentRequests.length >= this.config.rateLimitRequests) {
      return false;
    }
    
    // Add current request
    recentRequests.push(now);
    this.rateLimits.set(connectionId, recentRequests);
    
    return true;
  }

  /**
   * Start heartbeat to detect dead connections
   */
  startHeartbeat() {
    setInterval(() => {
      for (const [connectionId, connection] of this.connections.entries()) {
        if (!connection.isAlive) {
          console.log(`💀 Terminating dead connection: ${connectionId}`);
          connection.ws.terminate();
          this.handleDisconnection(connectionId, 1001, 'Heartbeat timeout');
          continue;
        }
        
        connection.isAlive = false;
        if (connection.ws.readyState === 1) { // WebSocket.OPEN
          connection.ws.ping();
        }
      }
    }, this.config.heartbeatInterval);
  }

  /**
   * Generate unique connection ID
   */
  generateConnectionId() {
    return `conn_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`;
  }

  /**
   * Generate unique stream ID
   */
  generateStreamId() {
    return `stream_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`;
  }

  /**
   * Extract user ID from request (implement based on your auth system)
   */
  extractUserId(request) {
    // Extract from JWT token in header or query parameter
    const authHeader = request.headers.authorization;
    const token = request.url?.includes('token=') ? 
      new URL(request.url, 'http://localhost').searchParams.get('token') : null;
    
    // For now, return a placeholder - implement JWT parsing
    return 'user_' + Math.random().toString(36).substring(2, 15);
  }

  /**
   * Store connection in database
   */
  async storeConnectionInDB(connectionInfo) {
    try {
      await query(`
        INSERT INTO ai_websocket_connections (
          connection_id, user_id, user_agent, ip_address, connected_at
        ) VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (connection_id) DO NOTHING
      `, [
        connectionInfo.id,
        connectionInfo.userId,
        connectionInfo.userAgent,
        connectionInfo.ipAddress,
        connectionInfo.connectedAt
      ]);
    } catch (error) {
      console.error('Error storing connection in DB:', error);
    }
  }

  /**
   * Update connection in database
   */
  async updateConnectionInDB(connectionId, updates) {
    try {
      if (updates.disconnectedAt) {
        await query(`
          UPDATE ai_websocket_connections 
          SET disconnected_at = $1 
          WHERE connection_id = $2
        `, [updates.disconnectedAt, connectionId]);
      }
    } catch (error) {
      console.error('Error updating connection in DB:', error);
    }
  }

  /**
   * Get service statistics
   */
  getStats() {
    return {
      ...this.stats,
      activeConnectionsCount: this.connections.size,
      activeStreamsCount: this.activeStreams.size,
      webSocketReady: !!this.wsServer,
      uptime: process.uptime(),
      memoryUsage: process.memoryUsage(),
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Health check
   */
  async healthCheck() {
    return {
      status: this.wsServer ? 'healthy' : 'unhealthy',
      service: 'StreamingService',
      connections: this.connections.size,
      activeStreams: this.activeStreams.size,
      stats: this.getStats(),
      webSocketReady: !!this.wsServer
    };
  }

  /**
   * Graceful shutdown
   */
  async shutdown() {
    console.log('🛑 Shutting down streaming service...');
    
    // Close all connections
    for (const [connectionId, connection] of this.connections.entries()) {
      this.sendToConnection(connectionId, {
        type: 'service_shutdown',
        message: 'Service is shutting down',
        timestamp: new Date().toISOString()
      });
      
      connection.ws.close(1001, 'Service shutdown');
    }
    
    // Close WebSocket server
    if (this.wsServer) {
      this.wsServer.close();
    }
    
    console.log('✅ Streaming service shutdown complete');
  }
}

// Export singleton instance
module.exports = new StreamingService();
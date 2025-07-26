/**
 * WebSocket Handler for AI Assistant Streaming
 * 
 * Provides real-time bidirectional communication for:
 * - AI response streaming
 * - Typing indicators
 * - Connection management
 * - Real-time portfolio updates
 */

const EnhancedBedrockService = require('../services/EnhancedBedrockService');
const aiStreamingService = require('../utils/aiStreamingService');
const conversationStore = require('../utils/conversationStore');
const { query } = require('../utils/database');

class WebSocketHandler {
  constructor() {
    this.connections = new Map(); // connectionId -> connection info
    this.userConnections = new Map(); // userId -> Set of connectionIds
    this.activeStreams = new Map(); // streamId -> stream info
    this.typingTimeouts = new Map(); // connectionId -> timeout
    
    this.enhancedBedrock = EnhancedBedrockService;
    
    // WebSocket configuration
    this.config = {
      maxConnections: 1000,
      maxStreamsPerUser: 3,
      typingIndicatorTimeout: 3000,
      heartbeatInterval: 30000,
      maxMessageSize: 50000
    };
  }

  /**
   * Handle WebSocket connection
   */
  async handleConnect(event) {
    const connectionId = event.requestContext.connectionId;
    const userId = this.extractUserId(event);
    
    try {
      console.log(`🔌 WebSocket connection established: ${connectionId} for user ${userId}`);

      // Check connection limits
      const userConnections = this.userConnections.get(userId) || new Set();
      if (userConnections.size >= 5) {
        console.warn(`⚠️ User ${userId} exceeded connection limit`);
        return { statusCode: 429, body: 'Too many connections' };
      }

      // Store connection info
      const connectionInfo = {
        connectionId,
        userId,
        connectedAt: new Date(),
        lastActivity: new Date(),
        status: 'connected'
      };

      this.connections.set(connectionId, connectionInfo);
      userConnections.add(connectionId);
      this.userConnections.set(userId, userConnections);

      // Send welcome message
      await this.sendMessage(connectionId, {
        type: 'connection_established',
        connectionId,
        timestamp: new Date().toISOString(),
        features: {
          streaming: true,
          typing: true,
          realTimeUpdates: true
        }
      });

      // Start heartbeat
      this.startHeartbeat(connectionId);

      return { statusCode: 200, body: 'Connected' };

    } catch (error) {
      console.error('❌ WebSocket connection error:', error);
      return { statusCode: 500, body: 'Connection failed' };
    }
  }

  /**
   * Handle WebSocket disconnection
   */
  async handleDisconnect(event) {
    const connectionId = event.requestContext.connectionId;
    
    try {
      console.log(`🔌 WebSocket disconnection: ${connectionId}`);

      const connectionInfo = this.connections.get(connectionId);
      if (connectionInfo) {
        const { userId } = connectionInfo;

        // Clean up user connections
        const userConnections = this.userConnections.get(userId);
        if (userConnections) {
          userConnections.delete(connectionId);
          if (userConnections.size === 0) {
            this.userConnections.delete(userId);
          }
        }

        // Cancel any active streams for this connection
        await this.cancelActiveStreams(connectionId);

        // Clean up typing timeouts
        if (this.typingTimeouts.has(connectionId)) {
          clearTimeout(this.typingTimeouts.get(connectionId));
          this.typingTimeouts.delete(connectionId);
        }
      }

      this.connections.delete(connectionId);

      return { statusCode: 200, body: 'Disconnected' };

    } catch (error) {
      console.error('❌ WebSocket disconnection error:', error);
      return { statusCode: 500, body: 'Disconnection failed' };
    }
  }

  /**
   * Handle incoming WebSocket messages
   */
  async handleMessage(event) {
    const connectionId = event.requestContext.connectionId;
    
    try {
      // Parse message
      const messageData = JSON.parse(event.body);
      const connectionInfo = this.connections.get(connectionId);
      
      if (!connectionInfo) {
        console.warn(`⚠️ Message from unknown connection: ${connectionId}`);
        return { statusCode: 404, body: 'Connection not found' };
      }

      // Update last activity
      connectionInfo.lastActivity = new Date();

      // Route message based on type
      switch (messageData.type) {
        case 'ai_chat_request':
          return await this.handleAIChatRequest(connectionId, messageData);
          
        case 'typing_start':
          return await this.handleTypingStart(connectionId, messageData);
          
        case 'typing_stop':
          return await this.handleTypingStop(connectionId, messageData);
          
        case 'stream_stop':
          return await this.handleStreamStop(connectionId, messageData);
          
        case 'ping':
          return await this.handlePing(connectionId, messageData);
          
        case 'portfolio_subscribe':
          return await this.handlePortfolioSubscribe(connectionId, messageData);
          
        case 'portfolio_unsubscribe':
          return await this.handlePortfolioUnsubscribe(connectionId, messageData);
          
        default:
          console.warn(`⚠️ Unknown message type: ${messageData.type}`);
          return { statusCode: 400, body: 'Unknown message type' };
      }

    } catch (error) {
      console.error('❌ WebSocket message handling error:', error);
      
      await this.sendMessage(connectionId, {
        type: 'error',
        error: 'Message processing failed',
        timestamp: new Date().toISOString()
      });

      return { statusCode: 500, body: 'Message processing failed' };
    }
  }

  /**
   * Handle AI chat request via WebSocket
   */
  async handleAIChatRequest(connectionId, messageData) {
    const connectionInfo = this.connections.get(connectionId);
    const { userId } = connectionInfo;
    
    try {
      const {
        content,
        conversationId = 'default',
        model = 'claude-3-haiku',
        context = {},
        options = {}
      } = messageData.data || messageData;

      // Validate message
      if (!content || typeof content !== 'string' || content.trim().length === 0) {
        await this.sendMessage(connectionId, {
          type: 'error',
          error: 'Message content is required',
          timestamp: new Date().toISOString()
        });
        return { statusCode: 400, body: 'Invalid message' };
      }

      // Check active streams limit
      const userStreams = Array.from(this.activeStreams.values())
        .filter(stream => stream.userId === userId);
      
      if (userStreams.length >= this.config.maxStreamsPerUser) {
        await this.sendMessage(connectionId, {
          type: 'error',
          error: 'Too many active streams',
          timestamp: new Date().toISOString()
        });
        return { statusCode: 429, body: 'Too many streams' };
      }

      console.log(`🤖 Processing WebSocket AI request from user ${userId}: ${content.substring(0, 100)}...`);

      // Create stream ID
      const streamId = `ws_stream_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

      // Register active stream
      this.activeStreams.set(streamId, {
        streamId,
        userId,
        connectionId,
        conversationId,
        startTime: Date.now(),
        status: 'active'
      });

      // Add user message to history
      const userMessage = {
        id: `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
        type: 'user',
        content: content.trim(),
        timestamp: new Date(),
        metadata: {
          connectionId,
          streamId,
          conversationId
        }
      };

      await conversationStore.addMessage(userId, conversationId, userMessage);

      // Build enhanced context
      const enhancedContext = await this.buildEnhancedContext(userId, conversationId, context);

      // Send stream started event
      await this.sendMessage(connectionId, {
        type: 'ai_response_start',
        streamId,
        conversationId,
        messageId: userMessage.id,
        timestamp: new Date().toISOString()
      });

      // Generate streaming response
      let fullResponse = '';
      let chunkCount = 0;
      const assistantMessageId = `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

      try {
        const streamGenerator = this.enhancedBedrock.generateStreamingResponse(
          content.trim(),
          enhancedContext,
          { model, streamId }
        );

        for await (const chunk of streamGenerator) {
          // Check if stream was cancelled
          const streamInfo = this.activeStreams.get(streamId);
          if (!streamInfo || streamInfo.status === 'cancelled') {
            console.log(`🛑 Stream ${streamId} was cancelled`);
            break;
          }

          if (chunk.type === 'chunk') {
            fullResponse += chunk.content;
            chunkCount++;
            
            await this.sendMessage(connectionId, {
              type: 'ai_response_chunk',
              streamId,
              chunkIndex: chunkCount,
              content: chunk.content,
              timestamp: chunk.timestamp
            });
          } else if (chunk.type === 'complete') {
            fullResponse = chunk.fullContent || fullResponse;
            
            // Create assistant message
            const assistantMessage = {
              id: assistantMessageId,
              type: 'assistant',
              content: fullResponse,
              timestamp: new Date(),
              suggestions: chunk.suggestions || [],
              metadata: {
                ...chunk.metadata,
                streamId,
                conversationId,
                connectionId,
                enhanced: true,
                chunkCount
              }
            };

            // Add to conversation history
            await conversationStore.addMessage(userId, conversationId, assistantMessage);

            // Send completion event
            await this.sendMessage(connectionId, {
              type: 'ai_response_complete',
              streamId,
              messageId: assistantMessageId,
              fullResponse,
              suggestions: chunk.suggestions,
              metadata: assistantMessage.metadata,
              timestamp: chunk.timestamp
            });

            console.log(`✅ WebSocket streaming completed: ${chunkCount} chunks`);
            break;
          } else if (chunk.type === 'error') {
            await this.sendMessage(connectionId, {
              type: 'ai_stream_error',
              streamId,
              error: chunk.error,
              timestamp: chunk.timestamp
            });
            break;
          }
        }

      } catch (streamError) {
        console.error('❌ Streaming generation error:', streamError);
        await this.sendMessage(connectionId, {
          type: 'ai_stream_error',
          streamId,
          error: streamError.message,
          timestamp: new Date().toISOString()
        });
      }

      // Clean up stream
      this.activeStreams.delete(streamId);

      return { statusCode: 200, body: 'Message processed' };

    } catch (error) {
      console.error('❌ AI chat request error:', error);
      await this.sendMessage(connectionId, {
        type: 'error',
        error: 'Failed to process AI request',
        timestamp: new Date().toISOString()
      });
      return { statusCode: 500, body: 'Processing failed' };
    }
  }

  /**
   * Handle typing start indicator
   */
  async handleTypingStart(connectionId, messageData) {
    const connectionInfo = this.connections.get(connectionId);
    const { userId } = connectionInfo;
    const { conversationId = 'default' } = messageData.data || {};

    try {
      // Broadcast typing indicator to other users in conversation (if multi-user)
      // For now, just acknowledge
      await this.sendMessage(connectionId, {
        type: 'typing_acknowledged',
        conversationId,
        timestamp: new Date().toISOString()
      });

      // Set timeout to auto-stop typing
      if (this.typingTimeouts.has(connectionId)) {
        clearTimeout(this.typingTimeouts.get(connectionId));
      }

      const timeout = setTimeout(async () => {
        await this.handleTypingStop(connectionId, { data: { conversationId } });
      }, this.config.typingIndicatorTimeout);

      this.typingTimeouts.set(connectionId, timeout);

      return { statusCode: 200, body: 'Typing started' };

    } catch (error) {
      console.error('❌ Typing start error:', error);
      return { statusCode: 500, body: 'Typing start failed' };
    }
  }

  /**
   * Handle typing stop indicator
   */
  async handleTypingStop(connectionId, messageData) {
    try {
      // Clear typing timeout
      if (this.typingTimeouts.has(connectionId)) {
        clearTimeout(this.typingTimeouts.get(connectionId));
        this.typingTimeouts.delete(connectionId);
      }

      return { statusCode: 200, body: 'Typing stopped' };

    } catch (error) {
      console.error('❌ Typing stop error:', error);
      return { statusCode: 500, body: 'Typing stop failed' };
    }
  }

  /**
   * Handle stream stop request
   */
  async handleStreamStop(connectionId, messageData) {
    const { streamId } = messageData.data || {};

    try {
      if (streamId && this.activeStreams.has(streamId)) {
        const streamInfo = this.activeStreams.get(streamId);
        streamInfo.status = 'cancelled';
        
        await this.sendMessage(connectionId, {
          type: 'stream_stopped',
          streamId,
          timestamp: new Date().toISOString()
        });

        console.log(`🛑 Stream ${streamId} stopped by user`);
      }

      return { statusCode: 200, body: 'Stream stopped' };

    } catch (error) {
      console.error('❌ Stream stop error:', error);
      return { statusCode: 500, body: 'Stream stop failed' };
    }
  }

  /**
   * Handle ping for keepalive
   */
  async handlePing(connectionId, messageData) {
    try {
      await this.sendMessage(connectionId, {
        type: 'pong',
        timestamp: new Date().toISOString()
      });

      return { statusCode: 200, body: 'Pong sent' };

    } catch (error) {
      console.error('❌ Ping error:', error);
      return { statusCode: 500, body: 'Ping failed' };
    }
  }

  /**
   * Handle portfolio subscription for real-time updates
   */
  async handlePortfolioSubscribe(connectionId, messageData) {
    const connectionInfo = this.connections.get(connectionId);
    
    try {
      connectionInfo.portfolioSubscribed = true;
      
      await this.sendMessage(connectionId, {
        type: 'portfolio_subscribed',
        timestamp: new Date().toISOString()
      });

      // Send initial portfolio data
      const portfolioData = await this.getPortfolioData(connectionInfo.userId);
      if (portfolioData) {
        await this.sendMessage(connectionId, {
          type: 'portfolio_update',
          data: portfolioData,
          timestamp: new Date().toISOString()
        });
      }

      return { statusCode: 200, body: 'Portfolio subscribed' };

    } catch (error) {
      console.error('❌ Portfolio subscribe error:', error);
      return { statusCode: 500, body: 'Portfolio subscribe failed' };
    }
  }

  /**
   * Handle portfolio unsubscription
   */
  async handlePortfolioUnsubscribe(connectionId, messageData) {
    const connectionInfo = this.connections.get(connectionId);
    
    try {
      connectionInfo.portfolioSubscribed = false;
      
      await this.sendMessage(connectionId, {
        type: 'portfolio_unsubscribed',
        timestamp: new Date().toISOString()
      });

      return { statusCode: 200, body: 'Portfolio unsubscribed' };

    } catch (error) {
      console.error('❌ Portfolio unsubscribe error:', error);
      return { statusCode: 500, body: 'Portfolio unsubscribe failed' };
    }
  }

  /**
   * Send message to WebSocket connection
   */
  async sendMessage(connectionId, message) {
    try {
      // In AWS Lambda WebSocket, use API Gateway Management API
      // For now, log the message (will be implemented with actual WebSocket)
      console.log(`📤 Sending to ${connectionId}:`, JSON.stringify(message, null, 2));
      
      // TODO: Implement actual WebSocket sending via API Gateway Management API
      // const apiGatewayManagementApi = new AWS.ApiGatewayManagementApi({
      //   endpoint: process.env.WEBSOCKET_API_ENDPOINT
      // });
      
      // await apiGatewayManagementApi.postToConnection({
      //   ConnectionId: connectionId,
      //   Data: JSON.stringify(message)
      // }).promise();

      return true;

    } catch (error) {
      console.error('❌ Send message error:', error);
      
      // Clean up dead connection
      if (error.statusCode === 410) {
        await this.handleDisconnect({ requestContext: { connectionId } });
      }
      
      return false;
    }
  }

  /**
   * Build enhanced context for AI
   */
  async buildEnhancedContext(userId, conversationId, additionalContext = {}) {
    try {
      // Get recent conversation history
      const recentMessages = await conversationStore.getHistory(userId, conversationId, 10);
      
      // Get portfolio context
      const portfolioContext = await this.getPortfolioData(userId);
      
      // Get market context
      const marketContext = await this.getMarketData();

      return {
        recentMessages,
        portfolioContext,
        marketContext,
        conversationId,
        userId,
        timestamp: new Date(),
        ...additionalContext
      };

    } catch (error) {
      console.error('❌ Error building enhanced context:', error);
      return additionalContext;
    }
  }

  /**
   * Get portfolio data for user
   */
  async getPortfolioData(userId) {
    try {
      const portfolioData = await query(`
        SELECT 
          symbol,
          quantity,
          avg_cost,
          current_price,
          market_value,
          unrealized_pl,
          unrealized_plpc,
          last_updated
        FROM portfolio_holdings 
        WHERE user_id = $1 AND quantity > 0
        ORDER BY market_value DESC
        LIMIT 20
      `, [userId]);

      if (portfolioData.rows.length === 0) {
        return null;
      }

      const holdings = portfolioData.rows;
      const totalValue = holdings.reduce((sum, holding) => sum + parseFloat(holding.market_value || 0), 0);
      const totalGainLoss = holdings.reduce((sum, holding) => sum + parseFloat(holding.unrealized_pl || 0), 0);

      return {
        holdings,
        totalValue,
        totalGainLoss,
        gainLossPercent: totalValue > 0 ? (totalGainLoss / totalValue) * 100 : 0,
        lastUpdated: new Date()
      };

    } catch (error) {
      console.error('❌ Error getting portfolio data:', error);
      return null;
    }
  }

  /**
   * Get market data
   */
  async getMarketData() {
    try {
      const marketData = await query(`
        SELECT symbol, current_price, change_percent, volume, updated_at
        FROM stocks 
        WHERE symbol IN ('SPY', 'QQQ', 'DIA', 'VTI')
        AND updated_at > NOW() - INTERVAL '1 hour'
        ORDER BY symbol
      `);

      return {
        indices: marketData.rows.reduce((acc, row) => {
          acc[row.symbol] = {
            price: parseFloat(row.current_price),
            change: parseFloat(row.change_percent)
          };
          return acc;
        }, {}),
        lastUpdated: new Date()
      };

    } catch (error) {
      console.error('❌ Error getting market data:', error);
      return { indices: {}, lastUpdated: new Date() };
    }
  }

  /**
   * Extract user ID from WebSocket event
   */
  extractUserId(event) {
    try {
      // Extract from query parameters, headers, or JWT token
      const queryParams = event.queryStringParameters || {};
      const headers = event.headers || {};
      
      // For now, use query parameter (production should use JWT)
      return queryParams.userId || headers['x-user-id'] || 'anonymous';

    } catch (error) {
      console.error('❌ Error extracting user ID:', error);
      return 'anonymous';
    }
  }

  /**
   * Start heartbeat for connection
   */
  startHeartbeat(connectionId) {
    const interval = setInterval(async () => {
      const connectionInfo = this.connections.get(connectionId);
      if (!connectionInfo) {
        clearInterval(interval);
        return;
      }

      // Check if connection is still active
      const timeSinceLastActivity = Date.now() - connectionInfo.lastActivity.getTime();
      if (timeSinceLastActivity > this.config.heartbeatInterval * 2) {
        console.log(`💔 Connection ${connectionId} timed out`);
        await this.handleDisconnect({ requestContext: { connectionId } });
        clearInterval(interval);
        return;
      }

      // Send heartbeat
      await this.sendMessage(connectionId, {
        type: 'heartbeat',
        timestamp: new Date().toISOString()
      });

    }, this.config.heartbeatInterval);
  }

  /**
   * Cancel active streams for connection
   */
  async cancelActiveStreams(connectionId) {
    const streamsToCancel = Array.from(this.activeStreams.entries())
      .filter(([, stream]) => stream.connectionId === connectionId);

    for (const [streamId, stream] of streamsToCancel) {
      stream.status = 'cancelled';
      this.activeStreams.delete(streamId);
      console.log(`🛑 Cancelled stream ${streamId} for disconnected connection`);
    }
  }

  /**
   * Broadcast to all connections of a user
   */
  async broadcastToUser(userId, message) {
    const userConnections = this.userConnections.get(userId);
    if (!userConnections) return;

    const promises = Array.from(userConnections).map(connectionId =>
      this.sendMessage(connectionId, message)
    );

    await Promise.allSettled(promises);
  }

  /**
   * Get connection statistics
   */
  getStats() {
    return {
      totalConnections: this.connections.size,
      totalUsers: this.userConnections.size,
      activeStreams: this.activeStreams.size,
      avgConnectionsPerUser: this.userConnections.size > 0 ? 
        this.connections.size / this.userConnections.size : 0
    };
  }
}

// Export handler instance
module.exports = new WebSocketHandler();
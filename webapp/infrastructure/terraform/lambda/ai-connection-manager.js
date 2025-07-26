/**
 * AI Connection Manager Lambda
 * Handles WebSocket connections for real-time AI chat
 */

const AWS = require('aws-sdk');
const { Client } = require('pg');

const apiGateway = new AWS.ApiGatewayManagementApi({
  endpoint: process.env.WEBSOCKET_API_ENDPOINT
});

const secretsManager = new AWS.SecretsManager();

// Connection pool for database
let dbClient = null;

/**
 * Get database client with connection pooling
 */
async function getDatabaseClient() {
  if (!dbClient) {
    try {
      // In production, get DB credentials from Secrets Manager
      dbClient = new Client({
        host: process.env.DATABASE_ENDPOINT.split(':')[0],
        port: 5432,
        database: 'stocks_db',
        user: 'stocks_user',
        // Password would come from secrets manager in real implementation
        ssl: process.env.NODE_ENV === 'production'
      });
      
      await dbClient.connect();
      console.log('✅ Database connection established');
    } catch (error) {
      console.error('❌ Database connection failed:', error);
      throw error;
    }
  }
  return dbClient;
}

/**
 * Main Lambda handler
 */
exports.handler = async (event) => {
  const { requestContext } = event;
  const { connectionId, routeKey } = requestContext;
  
  console.log(`WebSocket ${routeKey} for connection ${connectionId}`);
  
  try {
    switch (routeKey) {
      case '$connect':
        return await handleConnect(connectionId, event);
      case '$disconnect':
        return await handleDisconnect(connectionId);
      case 'ai_message':
        return await handleMessage(connectionId, JSON.parse(event.body || '{}'));
      default:
        console.warn(`Unknown route: ${routeKey}`);
        return { statusCode: 400, body: 'Unknown route' };
    }
  } catch (error) {
    console.error('WebSocket error:', error);
    
    // Try to send error to client if connection is still active
    try {
      await sendToConnection(connectionId, {
        type: 'error',
        message: 'Internal server error',
        timestamp: new Date().toISOString()
      });
    } catch (sendError) {
      console.error('Failed to send error to client:', sendError);
    }
    
    return { statusCode: 500, body: 'Internal server error' };
  }
};

/**
 * Handle new WebSocket connection
 */
async function handleConnect(connectionId, event) {
  console.log('🔌 Client connecting:', connectionId);
  
  try {
    const dbClient = await getDatabaseClient();
    
    // Extract user information from authorization context
    const userId = event.requestContext.authorizer?.principalId || 'anonymous';
    const userAgent = event.headers?.['User-Agent'] || 'unknown';
    const ipAddress = event.requestContext.identity?.sourceIp || 'unknown';
    
    // Store connection information
    await dbClient.query(`
      INSERT INTO ai_websocket_connections (
        connection_id, 
        user_id, 
        user_agent, 
        ip_address, 
        connected_at
      ) VALUES ($1, $2, $3, $4, NOW())
      ON CONFLICT (connection_id) 
      DO UPDATE SET 
        user_id = EXCLUDED.user_id,
        connected_at = EXCLUDED.connected_at
    `, [connectionId, userId, userAgent, ipAddress]);
    
    // Send welcome message
    await sendToConnection(connectionId, {
      type: 'connection_established',
      message: 'Connected to AI Assistant',
      connectionId: connectionId,
      timestamp: new Date().toISOString(),
      features: {
        streaming: true,
        conversations: true,
        context_aware: true
      }
    });
    
    console.log(`✅ Connection ${connectionId} established for user ${userId}`);
    return { statusCode: 200 };
    
  } catch (error) {
    console.error('Connection error:', error);
    return { statusCode: 500 };
  }
}

/**
 * Handle WebSocket disconnection
 */
async function handleDisconnect(connectionId) {
  console.log('🔌 Client disconnecting:', connectionId);
  
  try {
    const dbClient = await getDatabaseClient();
    
    // Update connection record
    await dbClient.query(`
      UPDATE ai_websocket_connections 
      SET disconnected_at = NOW() 
      WHERE connection_id = $1
    `, [connectionId]);
    
    // Clean up any active streaming sessions
    await dbClient.query(`
      UPDATE ai_streaming_sessions 
      SET ended_at = NOW(), status = 'disconnected'
      WHERE connection_id = $1 AND status = 'active'
    `, [connectionId]);
    
    console.log(`✅ Connection ${connectionId} cleaned up`);
    return { statusCode: 200 };
    
  } catch (error) {
    console.error('Disconnection error:', error);
    return { statusCode: 500 };
  }
}

/**
 * Handle incoming AI message
 */
async function handleMessage(connectionId, message) {
  console.log('💬 Message received:', { connectionId, messageType: message.type });
  
  try {
    const dbClient = await getDatabaseClient();
    
    // Get connection info
    const connectionResult = await dbClient.query(`
      SELECT user_id FROM ai_websocket_connections 
      WHERE connection_id = $1 AND disconnected_at IS NULL
    `, [connectionId]);
    
    if (connectionResult.rows.length === 0) {
      throw new Error('Connection not found or inactive');
    }
    
    const userId = connectionResult.rows[0].user_id;
    
    switch (message.type) {
      case 'ai_chat_message':
        return await handleChatMessage(connectionId, userId, message);
      case 'typing_start':
        return await handleTypingStatus(connectionId, userId, true);
      case 'typing_stop':
        return await handleTypingStatus(connectionId, userId, false);
      case 'conversation_history_request':
        return await handleHistoryRequest(connectionId, userId, message);
      default:
        throw new Error(`Unknown message type: ${message.type}`);
    }
    
  } catch (error) {
    console.error('Message handling error:', error);
    await sendToConnection(connectionId, {
      type: 'error',
      message: error.message,
      originalMessage: message,
      timestamp: new Date().toISOString()
    });
    return { statusCode: 200 }; // Don't disconnect on message errors
  }
}

/**
 * Handle chat message and trigger AI processing
 */
async function handleChatMessage(connectionId, userId, message) {
  const { content, conversationId = 'default', context = {} } = message;
  
  if (!content || !content.trim()) {
    throw new Error('Message content is required');
  }
  
  const dbClient = await getDatabaseClient();
  const messageId = Date.now();
  
  // Store user message
  await dbClient.query(`
    INSERT INTO ai_conversations_enhanced (
      user_id, conversation_id, message_id, message_type, 
      content, context, timestamp
    ) VALUES ($1, $2, $3, 'user', $4, $5, NOW())
  `, [userId, conversationId, messageId, content.trim(), JSON.stringify(context)]);
  
  // Send acknowledgment
  await sendToConnection(connectionId, {
    type: 'message_received',
    messageId: messageId,
    conversationId: conversationId,
    timestamp: new Date().toISOString()
  });
  
  // Create streaming session
  const streamingSessionId = `${connectionId}-${messageId}`;
  await dbClient.query(`
    INSERT INTO ai_streaming_sessions (
      session_id, connection_id, user_id, conversation_id, 
      message_id, status, started_at
    ) VALUES ($1, $2, $3, $4, $5, 'active', NOW())
  `, [streamingSessionId, connectionId, userId, conversationId, messageId]);
  
  // Invoke AI processing Lambda asynchronously
  const lambda = new AWS.Lambda();
  const aiProcessingPayload = {
    type: 'streaming_chat',
    connectionId: connectionId,
    userId: userId,
    conversationId: conversationId,
    messageId: messageId,
    content: content.trim(),
    context: context,
    streamingSessionId: streamingSessionId
  };
  
  try {
    await lambda.invoke({
      FunctionName: process.env.AI_PROCESSING_LAMBDA_NAME || `${process.env.PROJECT_NAME}-${process.env.ENVIRONMENT}-ai-processing`,
      InvocationType: 'Event', // Async invocation
      Payload: JSON.stringify(aiProcessingPayload)
    }).promise();
    
    console.log(`✅ AI processing initiated for message ${messageId}`);
  } catch (error) {
    console.error('Failed to invoke AI processing:', error);
    
    // Update streaming session status
    await dbClient.query(`
      UPDATE ai_streaming_sessions 
      SET status = 'failed', ended_at = NOW(), error_message = $1
      WHERE session_id = $2
    `, [error.message, streamingSessionId]);
    
    // Notify client of error
    await sendToConnection(connectionId, {
      type: 'ai_processing_error',
      messageId: messageId,
      error: 'Failed to start AI processing',
      timestamp: new Date().toISOString()
    });
  }
  
  return { statusCode: 200 };
}

/**
 * Handle typing status updates
 */
async function handleTypingStatus(connectionId, userId, isTyping) {
  const dbClient = await getDatabaseClient();
  
  // Update typing status in database
  await dbClient.query(`
    INSERT INTO ai_user_typing_status (
      connection_id, user_id, is_typing, updated_at
    ) VALUES ($1, $2, $3, NOW())
    ON CONFLICT (connection_id) 
    DO UPDATE SET 
      is_typing = EXCLUDED.is_typing,
      updated_at = EXCLUDED.updated_at
  `, [connectionId, userId, isTyping]);
  
  // Broadcast typing status to other participants if needed
  // (For now, just acknowledge)
  await sendToConnection(connectionId, {
    type: 'typing_status_updated',
    isTyping: isTyping,
    timestamp: new Date().toISOString()
  });
  
  return { statusCode: 200 };
}

/**
 * Handle conversation history request
 */
async function handleHistoryRequest(connectionId, userId, message) {
  const { conversationId = 'default', limit = 50, offset = 0 } = message;
  
  const dbClient = await getDatabaseClient();
  
  // Get conversation history
  const historyResult = await dbClient.query(`
    SELECT 
      message_id, message_type, content, suggestions, 
      context, metadata, timestamp
    FROM ai_conversations_enhanced 
    WHERE user_id = $1 AND conversation_id = $2
    ORDER BY timestamp DESC, message_id DESC
    LIMIT $3 OFFSET $4
  `, [userId, conversationId, limit, offset]);
  
  const history = historyResult.rows.map(row => ({
    id: row.message_id,
    type: row.message_type,
    content: row.content,
    suggestions: row.suggestions,
    context: row.context,
    metadata: row.metadata,
    timestamp: row.timestamp
  })).reverse(); // Reverse to get chronological order
  
  await sendToConnection(connectionId, {
    type: 'conversation_history',
    conversationId: conversationId,
    history: history,
    total: history.length,
    hasMore: history.length === limit,
    timestamp: new Date().toISOString()
  });
  
  return { statusCode: 200 };
}

/**
 * Send message to WebSocket connection
 */
async function sendToConnection(connectionId, data) {
  try {
    await apiGateway.postToConnection({
      ConnectionId: connectionId,
      Data: JSON.stringify(data)
    }).promise();
  } catch (error) {
    if (error.statusCode === 410) {
      console.log(`Connection ${connectionId} is gone`);
      // Clean up stale connection
      try {
        const dbClient = await getDatabaseClient();
        await dbClient.query(`
          UPDATE ai_websocket_connections 
          SET disconnected_at = NOW() 
          WHERE connection_id = $1
        `, [connectionId]);
      } catch (dbError) {
        console.error('Failed to clean up stale connection:', dbError);
      }
    } else {
      console.error('Failed to send message to connection:', error);
      throw error;
    }
  }
}

/**
 * Cleanup on Lambda shutdown
 */
process.on('SIGTERM', async () => {
  console.log('Lambda shutting down, closing database connection...');
  if (dbClient) {
    try {
      await dbClient.end();
      console.log('Database connection closed');
    } catch (error) {
      console.error('Error closing database connection:', error);
    }
  }
});
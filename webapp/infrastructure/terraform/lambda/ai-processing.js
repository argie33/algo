/**
 * AI Processing Lambda
 * Handles AI response generation using AWS Bedrock with streaming support
 */

const { BedrockRuntimeClient, InvokeModelCommand, InvokeModelWithResponseStreamCommand } = require('@aws-sdk/client-bedrock-runtime');
const AWS = require('aws-sdk');
const { Client } = require('pg');

const bedrockClient = new BedrockRuntimeClient({ region: process.env.AWS_REGION });
const secretsManager = new AWS.SecretsManager();
const apiGateway = new AWS.ApiGatewayManagementApi({
  endpoint: process.env.WEBSOCKET_API_ENDPOINT
});

// Connection pool for database
let dbClient = null;
let aiConfig = null;
let encryptionConfig = null;

/**
 * Get database client
 */
async function getDatabaseClient() {
  if (!dbClient) {
    dbClient = new Client({
      host: process.env.DATABASE_ENDPOINT.split(':')[0],
      port: 5432,
      database: 'stocks_db',
      user: 'stocks_user',
      // Password from secrets manager in production
      ssl: process.env.NODE_ENV === 'production'
    });
    await dbClient.connect();
  }
  return dbClient;
}

/**
 * Get AI configuration from Secrets Manager
 */
async function getAIConfig() {
  if (!aiConfig) {
    try {
      const secret = await secretsManager.getSecretValue({
        SecretId: process.env.AI_CONFIG_SECRET_ARN
      }).promise();
      aiConfig = JSON.parse(secret.SecretString);
    } catch (error) {
      console.error('Failed to get AI config:', error);
      // Fallback configuration
      aiConfig = {
        bedrock_model_id: 'anthropic.claude-3-haiku-20240307-v1:0',
        max_tokens: 1000,
        temperature: 0.1,
        streaming_enabled: true
      };
    }
  }
  return aiConfig;
}

/**
 * Get encryption configuration
 */
async function getEncryptionConfig() {
  if (!encryptionConfig) {
    try {
      const secret = await secretsManager.getSecretValue({
        SecretId: process.env.CONVERSATION_SECRET_ARN
      }).promise();
      encryptionConfig = JSON.parse(secret.SecretString);
    } catch (error) {
      console.error('Failed to get encryption config:', error);
      encryptionConfig = { algorithm: 'AES-256-GCM' };
    }
  }
  return encryptionConfig;
}

/**
 * Main Lambda handler
 */
exports.handler = async (event) => {
  console.log('AI Processing Event:', JSON.stringify(event, null, 2));
  
  try {
    const { type } = event;
    
    switch (type) {
      case 'streaming_chat':
        return await handleStreamingChat(event);
      case 'regular_chat':
        return await handleRegularChat(event);
      case 'context_analysis':
        return await handleContextAnalysis(event);
      default:
        throw new Error(`Unknown event type: ${type}`);
    }
    
  } catch (error) {
    console.error('AI Processing Error:', error);
    
    // Try to notify client if connection info available
    if (event.connectionId) {
      try {
        await sendToConnection(event.connectionId, {
          type: 'ai_error',
          messageId: event.messageId,
          error: 'AI processing failed',
          details: error.message,
          timestamp: new Date().toISOString()
        });
      } catch (sendError) {
        console.error('Failed to send error to client:', sendError);
      }
    }
    
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'AI processing failed' })
    };
  }
};

/**
 * Handle streaming chat response
 */
async function handleStreamingChat(event) {
  const { 
    connectionId, userId, conversationId, messageId, 
    content, context = {}, streamingSessionId 
  } = event;
  
  console.log(`🤖 Processing streaming chat for user ${userId}, message ${messageId}`);
  
  const dbClient = await getDatabaseClient();
  const config = await getAIConfig();
  
  try {
    // Build conversation context
    const conversationPrompt = await buildConversationContext(userId, conversationId, content, context);
    
    // Prepare streaming request
    const request = {
      modelId: config.bedrock_model_id,
      contentType: 'application/json',
      accept: 'application/json',
      body: JSON.stringify({
        anthropic_version: 'bedrock-2023-05-31',
        max_tokens: config.max_tokens,
        temperature: config.temperature,
        messages: [{
          role: 'user',
          content: conversationPrompt
        }]
      })
    };
    
    // Send streaming start notification
    await sendToConnection(connectionId, {
      type: 'ai_response_start',
      messageId: messageId,
      conversationId: conversationId,
      timestamp: new Date().toISOString()
    });
    
    if (config.streaming_enabled) {
      await handleStreamingResponse(connectionId, messageId, conversationId, request, dbClient);
    } else {
      await handleNonStreamingResponse(connectionId, messageId, conversationId, request, dbClient);
    }
    
    // Update streaming session
    await dbClient.query(`
      UPDATE ai_streaming_sessions 
      SET status = 'completed', ended_at = NOW()
      WHERE session_id = $1
    `, [streamingSessionId]);
    
    return { statusCode: 200 };
    
  } catch (error) {
    console.error('Streaming chat error:', error);
    
    // Update streaming session with error
    await dbClient.query(`
      UPDATE ai_streaming_sessions 
      SET status = 'failed', ended_at = NOW(), error_message = $1
      WHERE session_id = $2
    `, [error.message, streamingSessionId]);
    
    throw error;
  }
}

/**
 * Handle streaming response from Bedrock
 */
async function handleStreamingResponse(connectionId, messageId, conversationId, request, dbClient) {
  const command = new InvokeModelWithResponseStreamCommand(request);
  const response = await bedrockClient.send(command);
  
  let fullResponse = '';
  let tokenCount = 0;
  const assistantMessageId = Date.now() + 1;
  
  try {
    for await (const chunk of response.body) {
      if (chunk.chunk) {
        const chunkData = JSON.parse(new TextDecoder().decode(chunk.chunk.bytes));
        
        if (chunkData.type === 'content_block_delta' && chunkData.delta?.text) {
          const text = chunkData.delta.text;
          fullResponse += text;
          
          // Send chunk to client
          await sendToConnection(connectionId, {
            type: 'ai_response_chunk',
            messageId: assistantMessageId,
            conversationId: conversationId,
            chunk: text,
            isComplete: false,
            timestamp: new Date().toISOString()
          });
        }
        
        if (chunkData.usage) {
          tokenCount = chunkData.usage.output_tokens || 0;
        }
      }
    }
    
    // Generate suggestions
    const suggestions = generateSuggestions(fullResponse);
    
    // Send completion
    await sendToConnection(connectionId, {
      type: 'ai_response_complete',
      messageId: assistantMessageId,
      conversationId: conversationId,
      fullResponse: fullResponse,
      suggestions: suggestions,
      metadata: {
        tokensUsed: tokenCount,
        model: request.modelId
      },
      timestamp: new Date().toISOString()
    });
    
    // Store assistant response in database
    await storeAssistantMessage(
      dbClient, 
      connectionId.split('-')[0], // Extract userId from connectionId pattern
      conversationId, 
      assistantMessageId, 
      fullResponse, 
      suggestions, 
      tokenCount, 
      request.modelId
    );
    
  } catch (streamError) {
    console.error('Streaming error:', streamError);
    
    await sendToConnection(connectionId, {
      type: 'ai_response_error',
      messageId: assistantMessageId,
      conversationId: conversationId,
      error: 'Streaming interrupted',
      partialResponse: fullResponse,
      timestamp: new Date().toISOString()
    });
    
    throw streamError;
  }
}

/**
 * Handle non-streaming response from Bedrock
 */
async function handleNonStreamingResponse(connectionId, messageId, conversationId, request, dbClient) {
  const command = new InvokeModelCommand(request);
  const response = await bedrockClient.send(command);
  
  const responseBody = JSON.parse(new TextDecoder().decode(response.body));
  const aiMessage = responseBody.content[0].text;
  const tokenCount = responseBody.usage?.output_tokens || 0;
  
  const suggestions = generateSuggestions(aiMessage);
  const assistantMessageId = Date.now() + 1;
  
  // Send complete response
  await sendToConnection(connectionId, {
    type: 'ai_response_complete',
    messageId: assistantMessageId,
    conversationId: conversationId,
    fullResponse: aiMessage,
    suggestions: suggestions,
    metadata: {
      tokensUsed: tokenCount,
      model: request.modelId
    },
    timestamp: new Date().toISOString()
  });
  
  // Store in database
  await storeAssistantMessage(
    dbClient,
    connectionId.split('-')[0], // Extract userId
    conversationId,
    assistantMessageId,
    aiMessage,
    suggestions,
    tokenCount,
    request.modelId
  );
}

/**
 * Build conversation context with portfolio and market data
 */
async function buildConversationContext(userId, conversationId, userMessage, context) {
  const dbClient = await getDatabaseClient();
  
  let prompt = `You are an expert AI investment advisor with deep knowledge of financial markets, portfolio management, and investment strategies. You provide clear, actionable, and responsible investment guidance.

Key guidelines:
- Always provide balanced, well-reasoned investment advice
- Consider risk management in all recommendations
- Use specific data and metrics when available
- Suggest next steps or follow-up questions
- Avoid giving specific buy/sell recommendations for individual stocks
- Focus on education and strategy rather than predictions
- Keep responses concise but comprehensive

`;

  try {
    // Get portfolio context if available
    const portfolioResult = await dbClient.query(`
      SELECT 
        symbol, quantity, avg_cost, current_price, market_value, unrealized_pl
      FROM portfolio_holdings 
      WHERE user_id = $1
      ORDER BY market_value DESC
      LIMIT 10
    `, [userId]);
    
    if (portfolioResult.rows.length > 0) {
      const totalValue = portfolioResult.rows.reduce((sum, holding) => sum + parseFloat(holding.market_value || 0), 0);
      const totalGainLoss = portfolioResult.rows.reduce((sum, holding) => sum + parseFloat(holding.unrealized_pl || 0), 0);
      
      prompt += `
Current Portfolio Context:
- Total Value: $${totalValue.toFixed(2)}
- Total Gain/Loss: $${totalGainLoss.toFixed(2)} (${totalValue > 0 ? ((totalGainLoss / totalValue) * 100).toFixed(2) : '0.00'}%)
- Number of Holdings: ${portfolioResult.rows.length}
- Top Holdings: ${portfolioResult.rows.slice(0, 3).map(h => `${h.symbol}: $${parseFloat(h.market_value).toFixed(2)}`).join(', ')}

`;
    }
    
    // Get recent conversation history
    const historyResult = await dbClient.query(`
      SELECT message_type, content
      FROM ai_conversations_enhanced
      WHERE user_id = $1 AND conversation_id = $2
      ORDER BY timestamp DESC
      LIMIT 5
    `, [userId, conversationId]);
    
    if (historyResult.rows.length > 0) {
      prompt += `
Recent conversation context:
${historyResult.rows.reverse().map(msg => 
  `${msg.message_type === 'user' ? 'User' : 'Assistant'}: ${msg.content.substring(0, 100)}...`
).join('\n')}

`;
    }
    
    // Get market context if available
    const marketResult = await dbClient.query(`
      SELECT symbol, current_price, change_percent
      FROM stocks 
      WHERE symbol IN ('SPY', 'QQQ', 'DIA')
      ORDER BY symbol
    `);
    
    if (marketResult.rows.length > 0) {
      prompt += `
Current Market Context:
${marketResult.rows.map(stock => 
  `${stock.symbol}: $${parseFloat(stock.current_price || 0).toFixed(2)} (${parseFloat(stock.change_percent || 0).toFixed(2)}%)`
).join(', ')}

`;
    }
    
  } catch (error) {
    console.error('Error building context:', error);
    // Continue without context if there's an error
  }
  
  prompt += `
User Question: ${userMessage}

Please provide a helpful, accurate, and actionable response. Include 2-4 relevant follow-up suggestions that would help the user explore this topic further.`;
  
  return prompt;
}

/**
 * Generate contextual suggestions
 */
function generateSuggestions(aiResponse) {
  const lowerResponse = aiResponse.toLowerCase();
  
  // Portfolio-related suggestions
  if (lowerResponse.includes('portfolio') || lowerResponse.includes('allocation')) {
    return [
      'Analyze sector allocation',
      'Review risk metrics',
      'Suggest rebalancing strategy',
      'Compare to benchmarks'
    ];
  }
  
  // Market analysis suggestions
  if (lowerResponse.includes('market') || lowerResponse.includes('sector')) {
    return [
      'Sector performance trends',
      'Economic indicators impact',
      'Volatility analysis',
      'Market outlook'
    ];
  }
  
  // Stock research suggestions
  if (lowerResponse.includes('stock') || lowerResponse.includes('company')) {
    return [
      'Technical analysis',
      'Fundamental metrics',
      'Analyst consensus',
      'Risk assessment'
    ];
  }
  
  // Investment strategy suggestions
  if (lowerResponse.includes('invest') || lowerResponse.includes('strategy')) {
    return [
      'Risk tolerance assessment',
      'Asset allocation strategy',
      'Dollar-cost averaging',
      'Tax optimization'
    ];
  }
  
  // Default suggestions
  return [
    'Tell me more about this',
    'What are the key risks?',
    'Show me relevant data',
    'What should I do next?'
  ];
}

/**
 * Store assistant message in database
 */
async function storeAssistantMessage(dbClient, userId, conversationId, messageId, content, suggestions, tokenCount, modelUsed) {
  try {
    await dbClient.query(`
      INSERT INTO ai_conversations_enhanced (
        user_id, conversation_id, message_id, message_type, 
        content, suggestions, metadata, token_count, model_used, timestamp
      ) VALUES ($1, $2, $3, 'assistant', $4, $5, $6, $7, $8, NOW())
    `, [
      userId, 
      conversationId, 
      messageId, 
      content, 
      JSON.stringify(suggestions || []),
      JSON.stringify({ 
        generatedAt: new Date().toISOString(),
        processingTime: Date.now() - messageId 
      }),
      tokenCount, 
      modelUsed
    ]);
    
    // Update conversation metadata
    await dbClient.query(`
      UPDATE ai_conversation_metadata 
      SET 
        total_messages = total_messages + 1,
        total_tokens = total_tokens + $1,
        last_activity = NOW()
      WHERE user_id = $2 AND conversation_id = $3
    `, [tokenCount, userId, conversationId]);
    
  } catch (error) {
    console.error('Failed to store assistant message:', error);
    // Don't throw - message was sent successfully to user
  }
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
    } else {
      console.error('Failed to send message to connection:', error);
      throw error;
    }
  }
}

/**
 * Handle regular (non-streaming) chat
 */
async function handleRegularChat(event) {
  // Implementation for HTTP-based chat requests
  const { message, userId, conversationId, context = {} } = event;
  
  const config = await getAIConfig();
  const conversationPrompt = await buildConversationContext(userId, conversationId, message, context);
  
  const request = {
    modelId: config.bedrock_model_id,
    contentType: 'application/json',
    accept: 'application/json',
    body: JSON.stringify({
      anthropic_version: 'bedrock-2023-05-31',
      max_tokens: config.max_tokens,
      temperature: config.temperature,
      messages: [{
        role: 'user',
        content: conversationPrompt
      }]
    })
  };
  
  const command = new InvokeModelCommand(request);
  const response = await bedrockClient.send(command);
  const responseBody = JSON.parse(new TextDecoder().decode(response.body));
  
  return {
    statusCode: 200,
    body: JSON.stringify({
      success: true,
      response: responseBody.content[0].text,
      suggestions: generateSuggestions(responseBody.content[0].text),
      metadata: {
        tokensUsed: responseBody.usage?.output_tokens || 0,
        model: config.bedrock_model_id
      }
    })
  };
}

/**
 * Handle context analysis requests
 */
async function handleContextAnalysis(event) {
  // Implementation for analyzing user context
  const { userId, analysisType } = event;
  
  // Placeholder for context analysis logic
  return {
    statusCode: 200,
    body: JSON.stringify({
      success: true,
      analysis: 'Context analysis completed',
      userId: userId,
      analysisType: analysisType
    })
  };
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
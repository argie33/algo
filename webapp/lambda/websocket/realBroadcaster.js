// Real-time WebSocket API Gateway Lambda Handler
// Connects frontend liveDataService.js to Alpaca WebSocket streams
// AWS API Gateway WebSocket API compatible

const AWS = require('aws-sdk');
const WebSocket = require('ws');
const jwt = require('jsonwebtoken');
const { APIGatewayManagementApi } = AWS;

// Initialize API Gateway Management API
let apiGatewayManagementApi;

// Connection management
const connections = new Map();
const alpacaConnections = new Map();

// Alpaca WebSocket configuration
const ALPACA_WS_URL = 'wss://stream.data.alpaca.markets/v2/iex';
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY = 1000;

// Initialize API Gateway Management API
function initializeApiGateway(event) {
  if (!apiGatewayManagementApi) {
    const { domainName, stage } = event.requestContext;
    const endpoint = `https://${domainName}/${stage}`;
    
    apiGatewayManagementApi = new APIGatewayManagementApi({
      endpoint,
      region: process.env.AWS_REGION || 'us-east-1'
    });
  }
}

// Send message to WebSocket client
async function sendToClient(connectionId, data) {
  try {
    await apiGatewayManagementApi.postToConnection({
      ConnectionId: connectionId,
      Data: JSON.stringify(data)
    }).promise();
    
    console.log(`📤 Message sent to ${connectionId}:`, data.type);
    return true;
  } catch (error) {
    console.error(`❌ Failed to send to ${connectionId}:`, error);
    
    // Remove stale connection
    if (error.statusCode === 410) {
      connections.delete(connectionId);
      console.log(`🗑️ Removed stale connection: ${connectionId}`);
    }
    return false;
  }
}

// Broadcast message to all connected clients
async function broadcast(data, filter = null) {
  const promises = [];
  
  connections.forEach((connectionData, connectionId) => {
    // Apply filter if provided
    if (filter && !filter(connectionData)) {
      return;
    }
    
    promises.push(sendToClient(connectionId, data));
  });
  
  const results = await Promise.allSettled(promises);
  const successCount = results.filter(r => r.status === 'fulfilled' && r.value).length;
  
  console.log(`📡 Broadcast sent to ${successCount}/${connections.size} clients`);
}

// Get API keys from AWS Secrets Manager or database
async function getApiKeys(userId) {
  try {
    // First try to get from environment or context
    if (process.env.ALPACA_API_KEY && process.env.ALPACA_SECRET_KEY) {
      return {
        keyId: process.env.ALPACA_API_KEY,
        secretKey: process.env.ALPACA_SECRET_KEY
      };
    }
    
    // TODO: Integrate with existing apiKeyService for user-specific keys
    // For now, return null to indicate no keys available
    console.warn(`⚠️ No Alpaca API keys configured for user: ${userId}`);
    return null;
    
  } catch (error) {
    console.error('❌ Failed to get API keys:', error);
    return null;
  }
}

// Create Alpaca WebSocket connection
async function createAlpacaConnection(userId, apiKeys, symbols = []) {
  return new Promise((resolve, reject) => {
    let reconnectAttempts = 0;
    
    function connect() {
      console.log(`🔌 Connecting to Alpaca WebSocket for user: ${userId}`);
      
      const alpacaWs = new WebSocket(ALPACA_WS_URL);
      let authenticated = false;
      let subscribed = false;
      
      const connectionTimeout = setTimeout(() => {
        if (alpacaWs.readyState === WebSocket.CONNECTING) {
          alpacaWs.close();
          reject(new Error('Alpaca connection timeout'));
        }
      }, 10000);
      
      alpacaWs.onopen = () => {
        clearTimeout(connectionTimeout);
        console.log(`✅ Connected to Alpaca WebSocket for user: ${userId}`);
        
        // Authenticate immediately
        const authMessage = {
          action: 'auth',
          key: apiKeys.keyId,
          secret: apiKeys.secretKey
        };
        
        alpacaWs.send(JSON.stringify(authMessage));
        console.log(`🔐 Sent authentication to Alpaca for user: ${userId}`);
      };
      
      alpacaWs.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Handle authentication response
          if (data[0] && data[0].T === 'success' && data[0].msg === 'authenticated') {
            authenticated = true;
            console.log(`🔓 Alpaca authentication successful for user: ${userId}`);
            
            // Subscribe to symbols if provided
            if (symbols.length > 0) {
              const subscribeMessage = {
                action: 'subscribe',
                trades: symbols,
                quotes: symbols,
                bars: symbols
              };
              
              alpacaWs.send(JSON.stringify(subscribeMessage));
              console.log(`📊 Subscribed to ${symbols.length} symbols for user: ${userId}`);
            }
            
            resolve(alpacaWs);
            return;
          }
          
          // Handle subscription confirmation
          if (data[0] && data[0].T === 'subscription') {
            subscribed = true;
            console.log(`📊 Subscription confirmed for user: ${userId}`, data[0]);
            return;
          }
          
          // Handle market data
          if (authenticated && Array.isArray(data)) {
            data.forEach(message => {
              if (message.T === 't') { // Trade data
                const marketData = {
                  type: 'market_data_update',
                  symbol: message.S,
                  data: {
                    price: message.p,
                    size: message.s,
                    timestamp: message.t,
                    source: 'alpaca',
                    dataType: 'trade'
                  },
                  timestamp: Date.now() / 1000
                };
                
                // Broadcast to all clients subscribed to this symbol
                const filter = (conn) => conn.subscriptions && conn.subscriptions.has(message.S);
                broadcast(marketData, filter);
                
              } else if (message.T === 'q') { // Quote data
                const marketData = {
                  type: 'market_data_update',
                  symbol: message.S,
                  data: {
                    price: (message.bp + message.ap) / 2, // Mid price
                    bid: message.bp,
                    ask: message.ap,
                    bidSize: message.bs,
                    askSize: message.as,
                    timestamp: message.t,
                    source: 'alpaca',
                    dataType: 'quote'
                  },
                  timestamp: Date.now() / 1000
                };
                
                const filter = (conn) => conn.subscriptions && conn.subscriptions.has(message.S);
                broadcast(marketData, filter);
                
              } else if (message.T === 'b') { // Bar data
                const marketData = {
                  type: 'market_data_update',
                  symbol: message.S,
                  data: {
                    price: message.c, // Close price
                    open: message.o,
                    high: message.h,
                    low: message.l,
                    volume: message.v,
                    timestamp: message.t,
                    source: 'alpaca',
                    dataType: 'bar'
                  },
                  timestamp: Date.now() / 1000
                };
                
                const filter = (conn) => conn.subscriptions && conn.subscriptions.has(message.S);
                broadcast(marketData, filter);
              }
            });
          }
          
        } catch (parseError) {
          console.error('❌ Failed to parse Alpaca message:', parseError);
        }
      };
      
      alpacaWs.onclose = (event) => {
        console.log(`🔌 Alpaca WebSocket closed for user ${userId}:`, event.code, event.reason);
        
        // Attempt reconnection on unexpected close
        if (event.code !== 1000 && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts++;
          const delay = RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1);
          
          console.log(`🔄 Reconnecting to Alpaca in ${delay}ms (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
          
          setTimeout(() => {
            connect();
          }, delay);
        } else {
          alpacaConnections.delete(userId);
          console.log(`❌ Alpaca connection permanently closed for user: ${userId}`);
        }
      };
      
      alpacaWs.onerror = (error) => {
        console.error(`❌ Alpaca WebSocket error for user ${userId}:`, error);
        reject(error);
      };
    }
    
    connect();
  });
}

// Get real market data from Polygon
async function getRealMarketDataFromPolygon(symbols) {
  const { polygonConfig } = await getApiKeys();
  
  try {
    const response = await axios.get(`https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers`, {
      params: {
        tickers: symbols.join(','),
        apikey: polygonConfig.apiKey
      },
      timeout: 10000
    });

    const results = response.data.results || [];
    const marketData = [];

    for (const result of results) {
      if (result.value && result.lastQuote) {
        marketData.push({
          symbol: result.ticker,
          price: result.value,
          bid: result.lastQuote.bid,
          ask: result.lastQuote.ask,
          bidSize: result.lastQuote.bidSize,
          askSize: result.lastQuote.askSize,
          volume: result.day?.v || 0,
          change: result.todaysChange || 0,
          changePercent: result.todaysChangePerc || 0,
          timestamp: result.updated || Date.now(),
          source: 'polygon',
          exchange: result.lastQuote?.exchange || 'NYSE'
        });
      }
    }

    return marketData;
  } catch (error) {
    console.error('Polygon API error:', error.message);
    return [];
  }
}

// Get all active subscriptions
async function getActiveSubscriptions() {
  try {
    const result = await dynamoDB.scan({
      TableName: SUBSCRIPTIONS_TABLE,
      FilterExpression: '#status = :status',
      ExpressionAttributeNames: {
        '#status': 'status'
      },
      ExpressionAttributeValues: {
        ':status': 'active'
      }
    }).promise();

    return result.Items || [];
  } catch (error) {
    console.error('Error fetching subscriptions:', error);
    return [];
  }
}

// Get unique symbols from all subscriptions
function getUniqueSymbols(subscriptions) {
  const symbolSet = new Set();
  
  subscriptions.forEach(sub => {
    if (sub.symbols && Array.isArray(sub.symbols)) {
      sub.symbols.forEach(symbol => {
        // Filter out portfolio subscriptions and only include stock symbols
        if (!symbol.startsWith('PORTFOLIO_') && symbol.match(/^[A-Z]{1,5}$/)) {
          symbolSet.add(symbol);
        }
      });
    }
  });
  
  return Array.from(symbolSet);
}

// Store market data in DynamoDB
async function storeMarketData(marketData) {
  const timestamp = Date.now();
  const putRequests = marketData.map(data => ({
    PutRequest: {
      Item: {
        symbol: data.symbol,
        timestamp: timestamp,
        sortKey: `${timestamp}-${data.source}`,
        price: data.price,
        bid: data.bid,
        ask: data.ask,
        volume: data.volume || 0,
        change: data.change || 0,
        changePercent: data.changePercent || 0,
        source: data.source,
        exchange: data.exchange,
        rawData: data,
        ttl: Math.floor(Date.now() / 1000) + (24 * 60 * 60) // 24 hours TTL
      }
    }
  }));

  // Batch write in chunks of 25 (DynamoDB limit)
  const chunks = [];
  for (let i = 0; i < putRequests.length; i += 25) {
    chunks.push(putRequests.slice(i, i + 25));
  }

  const writePromises = chunks.map(chunk => 
    dynamoDB.batchWrite({
      RequestItems: {
        [MARKET_DATA_TABLE]: chunk
      }
    }).promise()
  );

  await Promise.allSettled(writePromises);
}

// Broadcast market data to WebSocket connections
async function broadcastMarketData(marketData, subscriptions) {
  const broadcastPromises = [];
  
  for (const data of marketData) {
    // Find connections subscribed to this symbol
    const subscribedConnections = subscriptions.filter(sub => 
      sub.symbols && sub.symbols.includes(data.symbol)
    );
    
    if (subscribedConnections.length === 0) continue;
    
    const message = JSON.stringify({
      type: 'market_data_update',
      symbol: data.symbol,
      data: {
        price: data.price,
        bid: data.bid,
        ask: data.ask,
        volume: data.volume,
        change: data.change,
        changePercent: data.changePercent,
        timestamp: data.timestamp,
        source: data.source,
        exchange: data.exchange
      },
      timestamp: new Date().toISOString()
    });
    
    // Send to all subscribed connections
    for (const subscription of subscribedConnections) {
      broadcastPromises.push(
        sendToConnection(subscription.connectionId, message)
      );
    }
  }
  
  const results = await Promise.allSettled(broadcastPromises);
  const successful = results.filter(r => r.status === 'fulfilled').length;
  const failed = results.filter(r => r.status === 'rejected').length;
  
  console.log(`Broadcast complete: ${successful} successful, ${failed} failed`);
  return { successful, failed };
}

// Send message to WebSocket connection
async function sendToConnection(connectionId, message) {
  try {
    await apigateway.postToConnection({
      ConnectionId: connectionId,
      Data: message
    }).promise();
    
    return { connectionId, success: true };
  } catch (error) {
    if (error.statusCode === 410) {
      // Connection is stale, remove it
      console.log(`Removing stale connection: ${connectionId}`);
      await cleanupStaleConnection(connectionId);
    }
    throw error;
  }
}

// Clean up stale connections
async function cleanupStaleConnection(connectionId) {
  try {
    // Remove from connections table
    await dynamoDB.delete({
      TableName: CONNECTIONS_TABLE,
      Key: { connectionId }
    }).promise();
    
    // Remove all subscriptions for this connection
    const subscriptions = await dynamoDB.query({
      TableName: SUBSCRIPTIONS_TABLE,
      IndexName: 'ConnectionIndex',
      KeyConditionExpression: 'connectionId = :connectionId',
      ExpressionAttributeValues: {
        ':connectionId': connectionId
      }
    }).promise();
    
    if (subscriptions.Items && subscriptions.Items.length > 0) {
      const deletePromises = subscriptions.Items.map(item =>
        dynamoDB.delete({
          TableName: SUBSCRIPTIONS_TABLE,
          Key: { subscriptionId: item.subscriptionId }
        }).promise()
      );
      
      await Promise.allSettled(deletePromises);
    }
    
  } catch (error) {
    console.error('Error cleaning up stale connection:', error);
  }
}

// Main Lambda handler for API Gateway WebSocket
exports.handler = async (event, context) => {
  console.log('🚀 WebSocket Lambda handler invoked:', event.requestContext.routeKey);
  
  initializeApiGateway(event);
  
  const { connectionId, routeKey } = event.requestContext;
  const body = event.body ? JSON.parse(event.body) : {};
  
  try {
    switch (routeKey) {
      case '$connect':
        return await handleConnect(connectionId, event);
        
      case '$disconnect':
        return await handleDisconnect(connectionId);
        
      case 'subscribe':
        return await handleSubscribe(connectionId, body);
        
      case 'unsubscribe':
        return await handleUnsubscribe(connectionId, body);
        
      case 'ping':
        return await handlePing(connectionId, body);
        
      default:
        console.warn('❓ Unknown route key:', routeKey);
        return { statusCode: 400, body: JSON.stringify({ error: 'Unknown route' }) };
    }
    
  } catch (error) {
    console.error('❌ Lambda handler error:', error);
    
    // Send error to client if possible
    if (connectionId && connections.has(connectionId)) {
      await sendToClient(connectionId, {
        type: 'error',
        message: error.message,
        timestamp: Date.now()
      });
    }
    
    return { statusCode: 500, body: JSON.stringify({ error: error.message }) };
  }
};

// Handle new WebSocket connection
async function handleConnect(connectionId, event) {
  console.log(`🟢 New WebSocket connection: ${connectionId}`);
  
  // Extract authentication token from query string
  const { queryStringParameters } = event;
  let userId = 'anonymous';
  let token = null;
  
  if (queryStringParameters) {
    userId = queryStringParameters.userId || 'anonymous';
    token = queryStringParameters.token;
  }
  
  // Verify JWT token if provided
  if (token) {
    try {
      // Basic token validation (in production, verify with Cognito)
      const decoded = jwt.decode(token);
      if (decoded && decoded.sub) {
        userId = decoded.sub;
      }
      console.log(`🔓 Authenticated connection for user: ${userId}`);
    } catch (tokenError) {
      console.warn('⚠️ Token validation failed:', tokenError.message);
      // Continue with anonymous access
    }
  }
  
  // Store connection info
  connections.set(connectionId, {
    userId,
    connectedAt: Date.now(),
    subscriptions: new Set(),
    lastActivity: Date.now()
  });
  
  // Send connection confirmation
  await sendToClient(connectionId, {
    type: 'connected',
    connectionId,
    userId,
    timestamp: Date.now(),
    supportedActions: ['subscribe', 'unsubscribe', 'ping']
  });
  
  console.log(`✅ Connection established: ${connectionId} (user: ${userId})`);
  console.log(`📊 Total connections: ${connections.size}`);
  
  return { statusCode: 200 };
}

// Handle WebSocket disconnection
async function handleDisconnect(connectionId) {
  console.log(`🔴 WebSocket disconnection: ${connectionId}`);
  
  const connectionData = connections.get(connectionId);
  if (connectionData) {
    // Close Alpaca connection for this user if no other connections
    const userConnections = Array.from(connections.values()).filter(
      conn => conn.userId === connectionData.userId
    );
    
    if (userConnections.length <= 1) {
      const alpacaWs = alpacaConnections.get(connectionData.userId);
      if (alpacaWs && alpacaWs.readyState === WebSocket.OPEN) {
        alpacaWs.close(1000, 'Client disconnected');
        alpacaConnections.delete(connectionData.userId);
        console.log(`🔌 Closed Alpaca connection for user: ${connectionData.userId}`);
      }
    }
    
    connections.delete(connectionId);
  }
  
  console.log(`📊 Total connections: ${connections.size}`);
  return { statusCode: 200 };
}

// Handle symbol subscription
async function handleSubscribe(connectionId, body) {
  console.log(`📊 Subscribe request from ${connectionId}:`, body);
  
  const connectionData = connections.get(connectionId);
  if (!connectionData) {
    throw new Error('Connection not found');
  }
  
  const { symbols, channels } = body;
  if (!symbols || !Array.isArray(symbols)) {
    throw new Error('Invalid symbols array');
  }
  
  // Validate symbols
  const validSymbols = symbols.filter(symbol => 
    typeof symbol === 'string' && /^[A-Z]{1,10}$/.test(symbol)
  );
  
  if (validSymbols.length === 0) {
    throw new Error('No valid symbols provided');
  }
  
  // Update connection subscriptions
  validSymbols.forEach(symbol => {
    connectionData.subscriptions.add(symbol);
  });
  connectionData.lastActivity = Date.now();
  
  // Get or create Alpaca connection for this user
  let alpacaWs = alpacaConnections.get(connectionData.userId);
  
  if (!alpacaWs || alpacaWs.readyState !== WebSocket.OPEN) {
    // Get API keys for user
    const apiKeys = await getApiKeys(connectionData.userId);
    
    if (!apiKeys) {
      await sendToClient(connectionId, {
        type: 'error',
        message: 'No Alpaca API keys configured. Please add your API keys in Settings.',
        code: 'NO_API_KEYS',
        timestamp: Date.now()
      });
      return { statusCode: 200 };
    }
    
    try {
      alpacaWs = await createAlpacaConnection(connectionData.userId, apiKeys, validSymbols);
      alpacaConnections.set(connectionData.userId, alpacaWs);
    } catch (alpacaError) {
      await sendToClient(connectionId, {
        type: 'error',
        message: `Failed to connect to Alpaca: ${alpacaError.message}`,
        code: 'ALPACA_CONNECTION_FAILED',
        timestamp: Date.now()
      });
      return { statusCode: 200 };
    }
  } else {
    // Subscribe to new symbols on existing connection
    const subscribeMessage = {
      action: 'subscribe',
      trades: validSymbols,
      quotes: validSymbols,
      bars: validSymbols
    };
    
    alpacaWs.send(JSON.stringify(subscribeMessage));
  }
  
  // Send confirmation to client
  await sendToClient(connectionId, {
    type: 'subscription_confirmed',
    symbols: validSymbols,
    channels: channels || ['trades', 'quotes', 'bars'],
    timestamp: Date.now()
  });
  
  console.log(`📊 Subscribed ${connectionId} to ${validSymbols.length} symbols`);
  return { statusCode: 200 };
}

// Handle symbol unsubscription
async function handleUnsubscribe(connectionId, body) {
  console.log(`📊 Unsubscribe request from ${connectionId}:`, body);
  
  const connectionData = connections.get(connectionId);
  if (!connectionData) {
    throw new Error('Connection not found');
  }
  
  const { symbols } = body;
  if (!symbols || !Array.isArray(symbols)) {
    throw new Error('Invalid symbols array');
  }
  
  // Remove from connection subscriptions
  symbols.forEach(symbol => {
    connectionData.subscriptions.delete(symbol);
  });
  connectionData.lastActivity = Date.now();
  
  // Unsubscribe from Alpaca if connection exists
  const alpacaWs = alpacaConnections.get(connectionData.userId);
  if (alpacaWs && alpacaWs.readyState === WebSocket.OPEN) {
    const unsubscribeMessage = {
      action: 'unsubscribe',
      trades: symbols,
      quotes: symbols,
      bars: symbols
    };
    
    alpacaWs.send(JSON.stringify(unsubscribeMessage));
  }
  
  // Send confirmation to client
  await sendToClient(connectionId, {
    type: 'unsubscribe_confirmed',
    symbols: symbols,
    timestamp: Date.now()
  });
  
  console.log(`📊 Unsubscribed ${connectionId} from ${symbols.length} symbols`);
  return { statusCode: 200 };
}

// Handle ping for latency measurement
async function handlePing(connectionId, body) {
  const connectionData = connections.get(connectionId);
  if (connectionData) {
    connectionData.lastActivity = Date.now();
  }
  
  await sendToClient(connectionId, {
    type: 'pong',
    timestamp: Date.now(),
    clientTimestamp: body.timestamp || null
  });
  
  return { statusCode: 200 };
}
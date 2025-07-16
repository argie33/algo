// WebSocket Message Handler
const AWS = require('aws-sdk');
const dynamoDB = new AWS.DynamoDB.DocumentClient();
const apiGateway = new AWS.ApiGatewayManagementApi({
  endpoint: process.env.WEBSOCKET_API_ENDPOINT
});

const CONNECTIONS_TABLE = process.env.CONNECTIONS_TABLE || 'WebSocketConnections';
const SUBSCRIPTIONS_TABLE = process.env.SUBSCRIPTIONS_TABLE || 'WebSocketSubscriptions';
const MARKET_DATA_TABLE = process.env.MARKET_DATA_TABLE || 'MarketData';

exports.handler = async (event) => {
  console.log('Message event:', JSON.stringify(event, null, 2));
  
  const connectionId = event.requestContext.connectionId;
  let message;
  
  try {
    message = JSON.parse(event.body);
  } catch (error) {
    return {
      statusCode: 400,
      body: JSON.stringify({
        message: 'Invalid message format',
        error: error.message
      })
    };
  }
  
  try {
    // Handle different message types
    switch (message.action) {
      case 'subscribe':
        return await handleSubscribe(connectionId, message);
      case 'unsubscribe':
        return await handleUnsubscribe(connectionId, message);
      case 'ping':
        return await handlePing(connectionId);
      case 'getMarketData':
        return await handleGetMarketData(connectionId, message);
      default:
        return {
          statusCode: 400,
          body: JSON.stringify({
            message: 'Unknown action',
            action: message.action
          })
        };
    }
  } catch (error) {
    console.error('Error processing message:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({
        message: 'Failed to process message',
        error: error.message
      })
    };
  }
};

async function handleSubscribe(connectionId, message) {
  const { symbols, channels } = message;
  
  if (!symbols || !Array.isArray(symbols) || symbols.length === 0) {
    return {
      statusCode: 400,
      body: JSON.stringify({
        message: 'Invalid symbols'
      })
    };
  }
  
  const subscriptionId = `${connectionId}-${Date.now()}`;
  const timestamp = new Date().toISOString();
  
  // Store subscription
  await dynamoDB.put({
    TableName: SUBSCRIPTIONS_TABLE,
    Item: {
      subscriptionId,
      connectionId,
      symbols,
      channels: channels || ['trades', 'quotes', 'bars'],
      timestamp,
      status: 'active'
    }
  }).promise();
  
  // Send confirmation to client
  await sendToConnection(connectionId, {
    type: 'subscription_confirmed',
    subscriptionId,
    symbols,
    channels: channels || ['trades', 'quotes', 'bars'],
    timestamp
  });
  
  return {
    statusCode: 200,
    body: JSON.stringify({
      message: 'Subscribed successfully',
      subscriptionId
    })
  };
}

async function handleUnsubscribe(connectionId, message) {
  const { subscriptionId, symbols } = message;
  
  if (subscriptionId) {
    // Unsubscribe by ID
    await dynamoDB.delete({
      TableName: SUBSCRIPTIONS_TABLE,
      Key: { subscriptionId }
    }).promise();
  } else if (symbols && Array.isArray(symbols)) {
    // Unsubscribe by symbols
    const subscriptions = await dynamoDB.query({
      TableName: SUBSCRIPTIONS_TABLE,
      IndexName: 'ConnectionIndex',
      KeyConditionExpression: 'connectionId = :connectionId',
      ExpressionAttributeValues: {
        ':connectionId': connectionId
      }
    }).promise();
    
    const toDelete = subscriptions.Items.filter(sub => 
      sub.symbols.some(symbol => symbols.includes(symbol))
    );
    
    await Promise.all(toDelete.map(sub =>
      dynamoDB.delete({
        TableName: SUBSCRIPTIONS_TABLE,
        Key: { subscriptionId: sub.subscriptionId }
      }).promise()
    ));
  }
  
  await sendToConnection(connectionId, {
    type: 'unsubscribe_confirmed',
    subscriptionId,
    symbols
  });
  
  return {
    statusCode: 200,
    body: JSON.stringify({
      message: 'Unsubscribed successfully'
    })
  };
}

async function handlePing(connectionId) {
  await sendToConnection(connectionId, {
    type: 'pong',
    timestamp: new Date().toISOString()
  });
  
  return {
    statusCode: 200,
    body: JSON.stringify({
      message: 'Pong'
    })
  };
}

async function handleGetMarketData(connectionId, message) {
  const { symbols, limit = 10 } = message;
  
  if (!symbols || !Array.isArray(symbols)) {
    return {
      statusCode: 400,
      body: JSON.stringify({
        message: 'Invalid symbols'
      })
    };
  }
  
  // Fetch latest market data for requested symbols
  const marketData = await Promise.all(symbols.map(async (symbol) => {
    const result = await dynamoDB.query({
      TableName: MARKET_DATA_TABLE,
      KeyConditionExpression: 'symbol = :symbol',
      ExpressionAttributeValues: {
        ':symbol': symbol
      },
      Limit: limit,
      ScanIndexForward: false // Latest first
    }).promise();
    
    return {
      symbol,
      data: result.Items || []
    };
  }));
  
  await sendToConnection(connectionId, {
    type: 'market_data',
    symbols,
    data: marketData,
    timestamp: new Date().toISOString()
  });
  
  return {
    statusCode: 200,
    body: JSON.stringify({
      message: 'Market data sent'
    })
  };
}

async function sendToConnection(connectionId, data) {
  try {
    await apiGateway.postToConnection({
      ConnectionId: connectionId,
      Data: JSON.stringify(data)
    }).promise();
  } catch (error) {
    if (error.statusCode === 410) {
      console.log(`Connection ${connectionId} is stale, removing...`);
      await dynamoDB.delete({
        TableName: CONNECTIONS_TABLE,
        Key: { connectionId }
      }).promise();
    } else {
      throw error;
    }
  }
}
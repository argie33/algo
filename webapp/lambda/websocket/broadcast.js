// WebSocket Broadcast Handler
// Receives market data from streams and broadcasts to subscribed connections
const AWS = require('aws-sdk');
const dynamoDB = new AWS.DynamoDB.DocumentClient();
const apiGateway = new AWS.ApiGatewayManagementApi({
  endpoint: process.env.WEBSOCKET_API_ENDPOINT
});

const CONNECTIONS_TABLE = process.env.CONNECTIONS_TABLE || 'WebSocketConnections';
const SUBSCRIPTIONS_TABLE = process.env.SUBSCRIPTIONS_TABLE || 'WebSocketSubscriptions';
const MARKET_DATA_TABLE = process.env.MARKET_DATA_TABLE || 'MarketData';

exports.handler = async (event) => {
  console.log('Broadcast event:', JSON.stringify(event, null, 2));
  
  try {
    // Process each record from the event (could be Kinesis, DynamoDB streams, etc.)
    for (const record of event.Records) {
      await processMarketDataRecord(record);
    }
    
    return {
      statusCode: 200,
      body: JSON.stringify({
        message: 'Broadcast completed',
        processedRecords: event.Records.length
      })
    };
  } catch (error) {
    console.error('Error broadcasting:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({
        message: 'Broadcast failed',
        error: error.message
      })
    };
  }
};

async function processMarketDataRecord(record) {
  let marketData;
  
  // Parse the record based on event source
  if (record.eventSource === 'aws:kinesis') {
    const payload = Buffer.from(record.kinesis.data, 'base64').toString('utf-8');
    marketData = JSON.parse(payload);
  } else if (record.eventSource === 'aws:dynamodb') {
    // DynamoDB stream record
    if (record.eventName === 'INSERT' || record.eventName === 'MODIFY') {
      marketData = AWS.DynamoDB.Converter.unmarshall(record.dynamodb.NewImage);
    }
  } else {
    // Direct invocation
    marketData = record;
  }
  
  if (!marketData || !marketData.symbol) {
    console.warn('Invalid market data record:', record);
    return;
  }
  
  // Store in DynamoDB for historical access
  await storeMarketData(marketData);
  
  // Find all subscriptions for this symbol
  const subscriptions = await findSubscriptionsForSymbol(marketData.symbol);
  
  if (subscriptions.length === 0) {
    console.log(`No subscriptions found for symbol ${marketData.symbol}`);
    return;
  }
  
  // Broadcast to all subscribed connections
  const broadcastPromises = subscriptions.map(subscription => 
    broadcastToConnection(subscription.connectionId, marketData)
  );
  
  const results = await Promise.allSettled(broadcastPromises);
  
  // Log results
  const successful = results.filter(r => r.status === 'fulfilled').length;
  const failed = results.filter(r => r.status === 'rejected').length;
  
  console.log(`Broadcasted ${marketData.symbol} data to ${successful} connections, ${failed} failed`);
}

async function storeMarketData(marketData) {
  const timestamp = new Date().toISOString();
  
  try {
    await dynamoDB.put({
      TableName: MARKET_DATA_TABLE,
      Item: {
        symbol: marketData.symbol,
        timestamp,
        sortKey: `${timestamp}-${marketData.type || 'trade'}`,
        price: marketData.price,
        volume: marketData.volume,
        type: marketData.type || 'trade',
        exchange: marketData.exchange,
        condition: marketData.condition,
        data: marketData,
        ttl: Math.floor(Date.now() / 1000) + (7 * 24 * 60 * 60) // 7 days TTL
      }
    }).promise();
  } catch (error) {
    console.error('Error storing market data:', error);
    // Don't throw - continue with broadcast even if storage fails
  }
}

async function findSubscriptionsForSymbol(symbol) {
  try {
    // Query subscriptions that include this symbol
    const result = await dynamoDB.scan({
      TableName: SUBSCRIPTIONS_TABLE,
      FilterExpression: 'contains(symbols, :symbol) AND #status = :status',
      ExpressionAttributeNames: {
        '#status': 'status'
      },
      ExpressionAttributeValues: {
        ':symbol': symbol,
        ':status': 'active'
      }
    }).promise();
    
    return result.Items || [];
  } catch (error) {
    console.error('Error finding subscriptions:', error);
    return [];
  }
}

async function broadcastToConnection(connectionId, marketData) {
  try {
    const message = {
      type: 'market_data_update',
      symbol: marketData.symbol,
      data: marketData,
      timestamp: new Date().toISOString()
    };
    
    await apiGateway.postToConnection({
      ConnectionId: connectionId,
      Data: JSON.stringify(message)
    }).promise();
    
    console.log(`Successfully sent data to connection ${connectionId}`);
  } catch (error) {
    if (error.statusCode === 410) {
      console.log(`Connection ${connectionId} is stale, removing...`);
      await cleanupStaleConnection(connectionId);
    } else {
      console.error(`Error sending to connection ${connectionId}:`, error);
      throw error;
    }
  }
}

async function cleanupStaleConnection(connectionId) {
  try {
    // Remove connection
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
      
      await Promise.all(deletePromises);
    }
    
    console.log(`Cleaned up stale connection ${connectionId}`);
  } catch (error) {
    console.error('Error cleaning up stale connection:', error);
  }
}
// WebSocket Connect Handler
const AWS = require('aws-sdk');
const dynamoDB = new AWS.DynamoDB.DocumentClient();

const CONNECTIONS_TABLE = process.env.CONNECTIONS_TABLE || 'WebSocketConnections';

exports.handler = async (event) => {
  console.log('Connect event:', JSON.stringify(event, null, 2));
  
  const connectionId = event.requestContext.connectionId;
  const timestamp = new Date().toISOString();
  
  try {
    // Store connection in DynamoDB
    await dynamoDB.put({
      TableName: CONNECTIONS_TABLE,
      Item: {
        connectionId,
        timestamp,
        ttl: Math.floor(Date.now() / 1000) + 86400, // 24 hours TTL
        status: 'connected',
        userAgent: event.headers['User-Agent'],
        sourceIp: event.requestContext.identity.sourceIp
      }
    }).promise();
    
    console.log(`Connection ${connectionId} stored successfully`);
    
    return {
      statusCode: 200,
      body: JSON.stringify({
        message: 'Connected successfully',
        connectionId
      })
    };
  } catch (error) {
    console.error('Error storing connection:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({
        message: 'Failed to connect',
        error: error.message
      })
    };
  }
};
// WebSocket Disconnect Handler
const AWS = require('aws-sdk');
const dynamoDB = new AWS.DynamoDB.DocumentClient();

const CONNECTIONS_TABLE = process.env.CONNECTIONS_TABLE || 'WebSocketConnections';
const SUBSCRIPTIONS_TABLE = process.env.SUBSCRIPTIONS_TABLE || 'WebSocketSubscriptions';

exports.handler = async (event) => {
  console.log('Disconnect event:', JSON.stringify(event, null, 2));
  
  const connectionId = event.requestContext.connectionId;
  
  try {
    // Remove connection from DynamoDB
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
    
    // Delete all subscriptions
    if (subscriptions.Items && subscriptions.Items.length > 0) {
      const deletePromises = subscriptions.Items.map(item =>
        dynamoDB.delete({
          TableName: SUBSCRIPTIONS_TABLE,
          Key: {
            subscriptionId: item.subscriptionId
          }
        }).promise()
      );
      
      await Promise.all(deletePromises);
      console.log(`Removed ${subscriptions.Items.length} subscriptions for connection ${connectionId}`);
    }
    
    console.log(`Connection ${connectionId} removed successfully`);
    
    return {
      statusCode: 200,
      body: JSON.stringify({
        message: 'Disconnected successfully'
      })
    };
  } catch (error) {
    console.error('Error removing connection:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({
        message: 'Failed to disconnect',
        error: error.message
      })
    };
  }
};
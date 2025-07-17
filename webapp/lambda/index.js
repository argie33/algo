// MINIMAL LAMBDA - TRIGGER WEBAPP WORKFLOW NOW
console.log('=== LAMBDA STARTUP - NO DEPENDENCIES ===');

// Test if the issue is with AWS Lambda runtime itself
console.log('Testing AWS Lambda runtime...');
console.log('Node version:', process.version);
console.log('Environment:', process.env.NODE_ENV || 'development');

// Create minimal handler without any external dependencies
exports.handler = async (event, context) => {
  console.log('=== LAMBDA HANDLER CALLED ===');
  console.log('Event:', JSON.stringify(event, null, 2));
  console.log('Context:', JSON.stringify(context, null, 2));
  
  try {
    // Get request method and path
    const method = event.httpMethod || event.requestContext?.httpMethod || 'UNKNOWN';
    const path = event.path || event.requestContext?.path || 'UNKNOWN';
    
    console.log(`Processing ${method} ${path}`);
    
    // Set CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      'Content-Type': 'application/json'
    };
    
    // Handle OPTIONS preflight requests
    if (method === 'OPTIONS') {
      console.log('Handling OPTIONS preflight request');
      return {
        statusCode: 200,
        headers: corsHeaders,
        body: JSON.stringify({
          message: 'CORS preflight handled successfully'
        })
      };
    }
    
    // Health endpoints
    if (path === '/health' || path === '/dev/health') {
      console.log('Handling health endpoint');
      return {
        statusCode: 200,
        headers: corsHeaders,
        body: JSON.stringify({
          success: true,
          message: 'Lambda is healthy (no external dependencies)',
          data: {
            status: 'healthy',
            timestamp: new Date().toISOString(),
            nodeVersion: process.version,
            method: method,
            path: path
          }
        })
      };
    }
    
    if (path === '/api/health' || path === '/dev/api/health') {
      console.log('Handling API health endpoint');
      return {
        statusCode: 200,
        headers: corsHeaders,
        body: JSON.stringify({
          success: true,
          message: 'API is healthy (no external dependencies)',
          data: {
            status: 'healthy',
            timestamp: new Date().toISOString(),
            cors: 'working',
            lambda: 'functional'
          }
        })
      };
    }
    
    // Environment diagnostic
    if (path === '/api/env' || path === '/dev/api/env') {
      console.log('Handling environment diagnostic');
      return {
        statusCode: 200,
        headers: corsHeaders,
        body: JSON.stringify({
          success: true,
          message: 'Environment diagnostic complete',
          data: {
            nodeVersion: process.version,
            awsRegion: process.env.AWS_REGION || 'not set',
            environment: process.env.NODE_ENV || 'development',
            functionName: context.functionName || 'unknown',
            functionVersion: context.functionVersion || 'unknown',
            memoryLimitInMB: context.memoryLimitInMB || 'unknown',
            remainingTimeInMillis: context.getRemainingTimeInMillis ? context.getRemainingTimeInMillis() : 'unknown'
          }
        })
      };
    }
    
    // Default 404 response
    console.log('No matching endpoint found, returning 404');
    return {
      statusCode: 404,
      headers: corsHeaders,
      body: JSON.stringify({
        success: false,
        error: 'Endpoint not found',
        message: `The requested endpoint ${method} ${path} was not found`,
        availableEndpoints: ['/health', '/api/health', '/api/env'],
        timestamp: new Date().toISOString()
      })
    };
    
  } catch (error) {
    console.error('❌ ERROR in Lambda handler:', error);
    console.error('Error stack:', error.stack);
    
    return {
      statusCode: 500,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        success: false,
        error: 'Internal server error',
        message: error.message,
        details: error.stack,
        timestamp: new Date().toISOString()
      })
    };
  }
};

console.log('=== LAMBDA INITIALIZATION COMPLETE (NO DEPENDENCIES) ===');
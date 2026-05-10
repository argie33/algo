exports.handler = async (event) => {
  console.log('API Lambda invoked:', JSON.stringify(event, null, 2));
  
  const method = event.requestContext?.http?.method || event.httpMethod || 'GET';
  const path = event.rawPath || event.path || '/';
  
  // Health check endpoint
  if (path === '/health' || path === '/api/health') {
    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'healthy', timestamp: new Date().toISOString() })
    };
  }
  
  // Default response
  return {
    statusCode: 200,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: 'API Lambda is operational',
      method: method,
      path: path,
      timestamp: new Date().toISOString()
    })
  };
};

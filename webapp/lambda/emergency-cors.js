// EMERGENCY CORS Lambda - Minimal working version
exports.handler = async (event, context) => {
    console.log('Emergency CORS handler:', event.httpMethod, event.path);
    
    // Always return CORS headers
    const corsHeaders = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
        'Access-Control-Allow-Credentials': 'true',
        'Content-Type': 'application/json'
    };
    
    // Handle OPTIONS preflight
    if (event.httpMethod === 'OPTIONS') {
        return {
            statusCode: 200,
            headers: corsHeaders,
            body: ''
        };
    }
    
    // Basic health check
    if (event.path === '/health' || event.path === '/dev/health') {
        return {
            statusCode: 200,
            headers: corsHeaders,
            body: JSON.stringify({
                status: 'ok',
                message: 'Emergency CORS Lambda working',
                timestamp: new Date().toISOString()
            })
        };
    }
    
    // Emergency API response for any endpoint
    return {
        statusCode: 200,
        headers: corsHeaders,
        body: JSON.stringify({
            status: 'emergency',
            message: 'Main Lambda deployment in progress - emergency CORS active',
            path: event.path,
            method: event.httpMethod,
            timestamp: new Date().toISOString()
        })
    };
};
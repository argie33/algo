// DIAGNOSTIC LAMBDA - COMPREHENSIVE LOGGING
console.log('=== LAMBDA STARTUP DIAGNOSTIC ===');
console.log('Node version:', process.version);
console.log('Environment:', process.env.NODE_ENV || 'development');
console.log('AWS Region:', process.env.AWS_REGION || 'not set');

// Test core dependencies
console.log('Testing core dependencies...');
try {
  console.log('1. Testing serverless-http...');
  const serverless = require('serverless-http');
  console.log('✅ serverless-http loaded successfully');
  
  console.log('2. Testing express...');
  const express = require('express');
  console.log('✅ express loaded successfully');
  
  console.log('3. Creating Express app...');
  const app = express();
  console.log('✅ Express app created successfully');
  
  console.log('4. Setting up CORS middleware...');
  app.use((req, res, next) => {
    console.log(`CORS middleware: ${req.method} ${req.path}`);
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    
    if (req.method === 'OPTIONS') {
      console.log('Handling OPTIONS preflight request');
      return res.status(200).end();
    }
    
    next();
  });
  console.log('✅ CORS middleware configured');
  
  console.log('5. Setting up JSON parsing...');
  app.use(express.json());
  console.log('✅ JSON parsing middleware configured');
  
  console.log('6. Setting up response formatter...');
  app.use((req, res, next) => {
    res.success = (data, message = 'Success') => {
      console.log(`Success response: ${message}`);
      res.json({
        success: true,
        data,
        message,
        timestamp: new Date().toISOString()
      });
    };
    
    res.error = (message, statusCode = 500, details = null) => {
      console.log(`Error response: ${statusCode} - ${message}`);
      res.status(statusCode).json({
        success: false,
        error: message,
        details,
        timestamp: new Date().toISOString()
      });
    };
    
    next();
  });
  console.log('✅ Response formatter middleware configured');
  
  console.log('7. Setting up routes...');
  
  // Health endpoint with extensive logging
  app.get('/health', (req, res) => {
    console.log('Health endpoint called');
    try {
      const healthData = {
        status: 'healthy',
        service: 'diagnostic-lambda',
        timestamp: new Date().toISOString(),
        nodeVersion: process.version,
        environment: process.env.NODE_ENV || 'development'
      };
      console.log('Health data:', JSON.stringify(healthData, null, 2));
      res.success(healthData, 'Diagnostic Lambda is healthy');
    } catch (error) {
      console.error('Health endpoint error:', error);
      res.error('Health check failed', 500, error.message);
    }
  });
  
  app.get('/api/health', (req, res) => {
    console.log('API Health endpoint called');
    try {
      const healthData = {
        status: 'healthy',
        service: 'diagnostic-lambda-api',
        timestamp: new Date().toISOString(),
        cors: 'working',
        middleware: 'loaded'
      };
      console.log('API Health data:', JSON.stringify(healthData, null, 2));
      res.success(healthData, 'API is healthy');
    } catch (error) {
      console.error('API Health endpoint error:', error);
      res.error('API health check failed', 500, error.message);
    }
  });
  
  // Environment variables diagnostic
  app.get('/api/env', (req, res) => {
    console.log('Environment diagnostic endpoint called');
    try {
      const envData = {
        nodeVersion: process.version,
        awsRegion: process.env.AWS_REGION || 'not set',
        environment: process.env.NODE_ENV || 'development',
        dbSecretArn: process.env.DB_SECRET_ARN ? 'present' : 'missing',
        apiKeySecretArn: process.env.API_KEY_ENCRYPTION_SECRET_ARN ? 'present' : 'missing',
        lambdaTaskRoot: process.env.LAMBDA_TASK_ROOT || 'not set',
        lambdaRuntimeDir: process.env.LAMBDA_RUNTIME_DIR || 'not set'
      };
      console.log('Environment data:', JSON.stringify(envData, null, 2));
      res.success(envData, 'Environment diagnostic complete');
    } catch (error) {
      console.error('Environment diagnostic error:', error);
      res.error('Environment diagnostic failed', 500, error.message);
    }
  });
  
  // Test endpoint for basic functionality
  app.get('/api/test', (req, res) => {
    console.log('Test endpoint called');
    try {
      const testData = {
        message: 'Lambda is working correctly',
        timestamp: new Date().toISOString(),
        requestInfo: {
          method: req.method,
          path: req.path,
          headers: req.headers,
          query: req.query
        }
      };
      console.log('Test data:', JSON.stringify(testData, null, 2));
      res.success(testData, 'Test endpoint working');
    } catch (error) {
      console.error('Test endpoint error:', error);
      res.error('Test endpoint failed', 500, error.message);
    }
  });
  
  console.log('✅ Routes configured successfully');
  
  // 404 handler
  app.all('*', (req, res) => {
    console.log(`404 handler: ${req.method} ${req.path}`);
    res.status(404).json({
      success: false,
      error: 'Endpoint not found',
      message: `The requested endpoint ${req.method} ${req.path} was not found`,
      availableEndpoints: ['/health', '/api/health', '/api/env', '/api/test'],
      timestamp: new Date().toISOString()
    });
  });
  
  // Error handling middleware
  app.use((error, req, res, next) => {
    console.error('Unhandled error in Lambda:', error);
    console.error('Error stack:', error.stack);
    
    res.status(500).json({
      success: false,
      error: 'Internal server error',
      message: 'An unexpected error occurred in the Lambda function',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  });
  
  console.log('✅ Error handling configured');
  
  console.log('8. Creating serverless handler...');
  const handler = serverless(app);
  console.log('✅ Serverless handler created successfully');
  
  console.log('=== LAMBDA INITIALIZATION COMPLETE ===');
  console.log('Lambda is ready to handle requests');
  
  module.exports.handler = handler;
  
} catch (error) {
  console.error('❌ CRITICAL ERROR DURING LAMBDA INITIALIZATION:', error);
  console.error('Error stack:', error.stack);
  console.error('Error details:', JSON.stringify(error, null, 2));
  
  // Create a minimal error handler
  module.exports.handler = async (event, context) => {
    console.error('Lambda handler called but initialization failed');
    console.error('Event:', JSON.stringify(event, null, 2));
    console.error('Context:', JSON.stringify(context, null, 2));
    
    return {
      statusCode: 500,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization'
      },
      body: JSON.stringify({
        success: false,
        error: 'Lambda initialization failed',
        message: error.message,
        details: error.stack,
        timestamp: new Date().toISOString()
      })
    };
  };
}
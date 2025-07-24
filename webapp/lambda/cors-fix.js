/**
 * Enhanced CORS middleware with timeout protection
 * Fixes both CORS policy blocking and Lambda timeout issues
 */

const corsMiddleware = (req, res, next) => {
  console.log(`📡 CORS: ${req.method} ${req.path} - Origin: ${req.headers.origin}`);
  
  const origin = req.headers.origin;
  const allowedOrigins = [
    'https://d1zb7knau41vl9.cloudfront.net',
    'http://localhost:3000',
    'http://localhost:5173',
    'https://localhost:3000',
    'https://localhost:5173'
  ];
  
  // Always set CORS headers for allowed origins
  if (!origin || allowedOrigins.includes(origin)) {
    res.header('Access-Control-Allow-Origin', origin || 'https://d1zb7knau41vl9.cloudfront.net');
  }
  
  res.header('Access-Control-Allow-Credentials', 'true');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma, X-Auth-Token');
  res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Type, X-Request-ID');
  
  // Handle OPTIONS preflight requests immediately
  if (req.method === 'OPTIONS') {
    console.log('✅ CORS preflight handled successfully');
    return res.status(200).end();
  }
  
  next();
};

// Timeout protection wrapper
const corsWithTimeoutHandling = () => {
  return (req, res, next) => {
    // Set timeout protection
    const timeout = setTimeout(() => {
      if (!res.headersSent) {
        console.log('⏰ Request timeout protection triggered');
        corsMiddleware(req, res, () => {
          res.status(504).json({
            success: false,
            error: 'Gateway timeout',
            message: 'Request took too long to process',
            timestamp: new Date().toISOString()
          });
        });
      }
    }, 25000); // 25 second timeout (5s before Lambda timeout)
    
    // Clear timeout when response is sent
    res.on('finish', () => {
      clearTimeout(timeout);
    });
    
    // Apply CORS middleware
    corsMiddleware(req, res, next);
  };
};

// Export the enhanced CORS middleware
module.exports = {
  corsMiddleware,
  corsWithTimeoutHandling
};

// Legacy standalone handler for backward compatibility
const serverless = require('serverless-http');
const express = require('express');
const app = express();

app.use(corsWithTimeoutHandling());

app.get('/health', (req, res) => {
  res.json({
    success: true,
    message: 'CORS fix is working',
    timestamp: new Date().toISOString()
  });
});

app.all('*', (req, res) => {
  res.json({
    success: false,
    message: 'Route not implemented, but CORS is working',
    path: req.path,
    method: req.method,
    timestamp: new Date().toISOString()
  });
});

module.exports.handler = serverless(app);
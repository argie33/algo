const serverless = require('serverless-http');
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const { initializeDatabase } = require('./utils/database');
const errorHandler = require('./middleware/errorHandler');

// Import routes
const stockRoutes = require('./routes/stocks');
const metricsRoutes = require('./routes/metrics');
const healthRoutes = require('./routes/health');

const app = express();

// Trust proxy when running behind API Gateway/CloudFront
app.set('trust proxy', true);

// Security middleware (adjusted for Lambda)
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
      fontSrc: ["'self'", "https://fonts.gstatic.com"],
      imgSrc: ["'self'", "data:", "https:"],
      scriptSrc: ["'self'"],
      connectSrc: ["'self'"],
    },
  },
}));

// Note: Rate limiting removed - API Gateway handles this

// CORS configuration (allow API Gateway origins)
app.use(cors({
  origin: (origin, callback) => {
    // Allow requests from API Gateway, CloudFront, and local development
    if (!origin || 
        origin.includes('.execute-api.') || 
        origin.includes('.cloudfront.net') || 
        origin.includes('localhost') ||
        origin === process.env.FRONTEND_URL) {
      callback(null, true);
    } else {
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true,
}));

// Request parsing
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Logging (simplified for Lambda)
if (process.env.NODE_ENV !== 'production') {
  app.use(morgan('combined'));
}

// Global database initialization promise
let dbInitPromise = null;

// Initialize database connection on cold start
const ensureDatabase = async () => {
  if (!dbInitPromise) {
    dbInitPromise = initializeDatabase().catch(err => {
      console.error('Failed to initialize database:', err);
      dbInitPromise = null; // Reset to allow retry
      throw err;
    });
  }
  return dbInitPromise;
};

// Middleware to ensure database is ready
app.use(async (req, res, next) => {
  try {
    console.log(`Processing request: ${req.method} ${req.path}`);
    await ensureDatabase();
    console.log('Database connection verified');
    next();
  } catch (error) {
    console.error('Database initialization failed:', error);
    console.error('Error details:', {
      message: error.message,
      code: error.code,
      stack: error.stack
    });
    
    if (req.path === '/health') {
      // Allow health checks even if DB is down
      next();
    } else {
      res.status(503).json({ 
        error: 'Service temporarily unavailable - database connection failed',
        details: process.env.NODE_ENV === 'development' ? error.message : undefined
      });
    }
  }
});

// Routes (note: API Gateway handles the /api prefix)
app.use('/health', healthRoutes);
app.use('/stocks', stockRoutes);
app.use('/metrics', metricsRoutes);

// Default route
app.get('/', (req, res) => {
  res.json({
    message: 'Financial Dashboard API',
    version: '1.0.0',
    status: 'operational',
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV || 'development'
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({
    error: 'Endpoint not found',
    message: `The requested endpoint ${req.originalUrl} does not exist`
  });
});

// Error handling middleware (should be last)
app.use(errorHandler);

// Export Lambda handler
module.exports.handler = serverless(app, {
  // Lambda-specific options
  request: (request, event, context) => {
    // Add AWS event/context to request if needed
    request.event = event;
    request.context = context;
  }
});

// For local testing
if (require.main === module) {
  const PORT = process.env.PORT || 3001;
  app.listen(PORT, () => {
    console.log(`Financial Dashboard API server running on port ${PORT} (local mode)`);
  });
}

/**
 * Configuration Routes
 * Provides application configuration from environment variables
 * Replaces runtime CloudFormation queries with build-time environment variable injection
 */

const express = require('express');

// Create Express router
const router = express.Router();

/**
 * Get application configuration from environment variables
 * GET /config
 */
const getConfiguration = async (req, res) => {
  try {
    console.log('📋 Serving configuration from environment variables');
    
    // Build configuration from environment variables (no CloudFormation API calls)
    const config = {
      success: true,
      source: 'environment_variables',
      environment: process.env.ENVIRONMENT || 'dev',
      region: process.env.WEBAPP_AWS_REGION || 'us-east-1',
      
      // API Gateway configuration (from CloudFormation stack output)
      api: {
        gatewayUrl: process.env.API_GATEWAY_URL,
        region: process.env.WEBAPP_AWS_REGION || 'us-east-1'
      },
      
      // Cognito configuration (from this stack)
      cognito: {
        userPoolId: process.env.COGNITO_USER_POOL_ID,
        clientId: process.env.COGNITO_CLIENT_ID,
        region: process.env.WEBAPP_AWS_REGION || 'us-east-1'
      },
      
      // Services stack configuration (from services stack outputs via env vars)
      services: {
        stackName: process.env.SERVICES_STACK_NAME,
        redis: {
          endpoint: process.env.REDIS_ENDPOINT,
          port: process.env.REDIS_PORT || '6379'
        },
        storage: {
          bucketName: process.env.STORAGE_BUCKET_NAME
        }
      },
      
      // Database configuration
      database: {
        secretArn: process.env.DB_SECRET_ARN,
        name: process.env.DB_NAME || 'stocks',
        port: process.env.DB_PORT || '5432',
        ssl: process.env.DB_SSL === 'true'
      },
      
      // Security configuration
      security: {
        apiKeyEncryptionSecretArn: process.env.API_KEY_ENCRYPTION_SECRET_ARN,
        jwtSecretArn: process.env.JWT_SECRET_ARN
      },
      
      fetchedAt: new Date().toISOString()
    };
    
    // Validate required configuration
    const validation = validateConfiguration(config);
    if (!validation.isValid) {
      console.warn('⚠️ Configuration validation warnings:', validation.warnings);
      config.validation = validation;
    }
    
    console.log('✅ Configuration served successfully from environment variables');
    res.json(config);
    
  } catch (error) {
    console.error('❌ Error serving configuration:', error);
    
    res.status(500).json({
      error: 'Failed to load configuration',
      message: error.message,
      source: 'environment_variables'
    });
  }
};

/**
 * Validate configuration completeness
 */
function validateConfiguration(config) {
  const validation = {
    isValid: true,
    warnings: [],
    critical: []
  };
  
  // Check API Gateway URL
  if (!config.api.gatewayUrl) {
    validation.warnings.push('API Gateway URL is missing');
    validation.isValid = false;
  }
  
  // Check Cognito configuration
  if (!config.cognito.userPoolId || !config.cognito.clientId) {
    validation.warnings.push('Cognito configuration is incomplete');
    validation.isValid = false;
  }
  
  // Check services configuration
  if (!config.services.redis.endpoint) {
    validation.warnings.push('Redis endpoint is missing');
  }
  
  if (!config.services.storage.bucketName) {
    validation.warnings.push('Storage bucket name is missing');
  }
  
  // Check database configuration
  if (!config.database.secretArn) {
    validation.critical.push('Database secret ARN is missing');
    validation.isValid = false;
  }
  
  return validation;
}

/**
 * Health check for configuration service
 * GET /config/health
 */
const getConfigurationHealth = async (req, res) => {
  try {
    const health = {
      status: 'healthy',
      source: 'environment_variables',
      timestamp: new Date().toISOString(),
      environment: process.env.ENVIRONMENT || 'dev',
      checks: {
        api_gateway_url: !!process.env.API_GATEWAY_URL,
        cognito_user_pool: !!process.env.COGNITO_USER_POOL_ID,
        cognito_client: !!process.env.COGNITO_CLIENT_ID,
        redis_endpoint: !!process.env.REDIS_ENDPOINT,
        storage_bucket: !!process.env.STORAGE_BUCKET_NAME,
        database_secret: !!process.env.DB_SECRET_ARN
      }
    };
    
    // Determine overall health
    const failedChecks = Object.values(health.checks).filter(check => !check).length;
    if (failedChecks > 0) {
      health.status = failedChecks > 2 ? 'unhealthy' : 'degraded';
    }
    
    const statusCode = health.status === 'healthy' ? 200 : 
                      health.status === 'degraded' ? 200 : 503;
    
    res.status(statusCode).json(health);
    
  } catch (error) {
    res.status(500).json({
      status: 'error',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
};

// Define routes
router.get('/', getConfiguration);
router.get('/health', getConfigurationHealth);

// Export router
module.exports = router;

// Also export individual functions for testing
module.exports.functions = {
  getConfiguration,
  getConfigurationHealth,
  validateConfiguration
};
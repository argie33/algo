/**
 * Diagnostic Routes - Real-time Lambda environment debugging
 * Provides detailed diagnostic information for troubleshooting
 */

const express = require('express');
const router = express.Router();
const { getDiagnostics } = require('../utils/database');

/**
 * GET /diagnostic/environment
 * Show Lambda environment configuration
 */
router.get('/environment', async (req, res) => {
  try {
    const env = {
      // Lambda metadata
      lambda: {
        functionName: process.env.AWS_LAMBDA_FUNCTION_NAME || 'Not running in Lambda',
        functionVersion: process.env.AWS_LAMBDA_FUNCTION_VERSION || 'Not available',
        region: process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION || 'Unknown',
        runtime: process.env.AWS_EXECUTION_ENV || 'Unknown',
        memorySize: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE || 'Unknown'
      },
      
      // Database configuration
      database: {
        secretArn: process.env.DB_SECRET_ARN ? 'SET' : 'MISSING',
        endpoint: process.env.DB_ENDPOINT || 'MISSING',
        port: process.env.DB_PORT || 'MISSING',
        name: process.env.DB_NAME || 'MISSING',
        ssl: process.env.DB_SSL || 'MISSING',
        // Sensitive values masked
        secretArnPrefix: process.env.DB_SECRET_ARN ? process.env.DB_SECRET_ARN.substring(0, 50) + '...' : 'MISSING'
      },
      
      // Application configuration
      app: {
        nodeEnv: process.env.NODE_ENV || 'MISSING',
        environment: process.env.ENVIRONMENT || 'MISSING',
        cognitoUserPoolId: process.env.COGNITO_USER_POOL_ID ? 'SET' : 'MISSING',
        cognitoClientId: process.env.COGNITO_CLIENT_ID ? 'SET' : 'MISSING',
        apiKeyEncryptionSecretArn: process.env.API_KEY_ENCRYPTION_SECRET_ARN ? 'SET' : 'MISSING'
      },
      
      // Network/VPC information
      network: {
        region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'Unknown'
      },
      
      // Validation checks
      validation: {
        hasSecretArn: !!process.env.DB_SECRET_ARN,
        hasEndpoint: !!process.env.DB_ENDPOINT,
        secretArnValid: process.env.DB_SECRET_ARN && !process.env.DB_SECRET_ARN.includes('${'),
        isLambda: !!process.env.AWS_LAMBDA_FUNCTION_NAME
      }
    };
    
    res.json({
      success: true,
      environment: env,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Environment diagnostic failed:', error.message);
    res.status(500).json({
      success: false,
      error: 'Environment diagnostic failed',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /diagnostic/database
 * Test database connectivity with detailed diagnostics
 */
router.get('/database', async (req, res) => {
  try {
    console.log('🔍 Starting database diagnostic...');
    
    // Get database diagnostics
    const diagnostics = await getDiagnostics();
    
    res.json({
      success: true,
      diagnostics,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Database diagnostic failed:', error.message);
    res.status(500).json({
      success: false,
      error: 'Database diagnostic failed',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /diagnostic/secrets
 * Test Secrets Manager connectivity (without revealing values)
 */
router.get('/secrets', async (req, res) => {
  try {
    console.log('🔐 Testing Secrets Manager connectivity...');
    
    if (!process.env.DB_SECRET_ARN) {
      return res.json({
        success: false,
        error: 'DB_SECRET_ARN environment variable not set',
        timestamp: new Date().toISOString()
      });
    }
    
    const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
    
    const secretsManager = new SecretsManagerClient({
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1',
      requestTimeout: 10000
    });
    
    const startTime = Date.now();
    
    try {
      const command = new GetSecretValueCommand({ 
        SecretId: process.env.DB_SECRET_ARN 
      });
      const response = await secretsManager.send(command);
      
      const duration = Date.now() - startTime;
      
      let secretInfo = { 
        retrieved: true,
        hasValue: !!response.SecretString,
        duration
      };
      
      if (response.SecretString) {
        try {
          const secret = JSON.parse(response.SecretString);
          const fields = Object.keys(secret);
          
          secretInfo.validJson = true;
          secretInfo.fieldCount = fields.length;
          secretInfo.hasUsername = !!secret.username;
          secretInfo.hasPassword = !!secret.password;
          secretInfo.hasHost = !!(secret.host || secret.endpoint);
          secretInfo.hasPort = !!secret.port;
          
        } catch (parseError) {
          secretInfo.validJson = false;
          secretInfo.parseError = parseError.message;
        }
      }
      
      res.json({
        success: true,
        secretInfo,
        timestamp: new Date().toISOString()
      });
      
    } catch (secretError) {
      const duration = Date.now() - startTime;
      
      res.json({
        success: false,
        error: secretError.message,
        errorCode: secretError.code,
        duration,
        secretArn: process.env.DB_SECRET_ARN.substring(0, 50) + '...',
        timestamp: new Date().toISOString()
      });
    }
    
  } catch (error) {
    console.error('❌ Secrets diagnostic failed:', error.message);
    res.status(500).json({
      success: false,
      error: 'Secrets diagnostic failed',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /diagnostic/complete
 * Run all diagnostics and return comprehensive report
 */
router.get('/complete', async (req, res) => {
  try {
    console.log('🔍 Running complete diagnostic suite...');
    
    const results = {
      timestamp: new Date().toISOString(),
      diagnostics: {}
    };
    
    // Test each diagnostic endpoint
    const diagnosticTests = ['environment', 'secrets', 'database'];
    
    for (const test of diagnosticTests) {
      try {
        console.log(`   Testing ${test}...`);
        
        // Create a mock request/response to call the route handler
        const mockReq = { query: {} };
        const mockRes = {
          json: (data) => { results.diagnostics[test] = data; },
          status: (code) => ({ json: (data) => { results.diagnostics[test] = { ...data, statusCode: code }; } })
        };
        
        // Call the appropriate route handler
        if (test === 'environment') {
          await router.stack.find(r => r.route.path === '/environment').route.stack[0].handle(mockReq, mockRes);
        } else if (test === 'secrets') {
          await router.stack.find(r => r.route.path === '/secrets').route.stack[0].handle(mockReq, mockRes);
        } else if (test === 'database') {
          await router.stack.find(r => r.route.path === '/database').route.stack[0].handle(mockReq, mockRes);
        }
        
      } catch (testError) {
        results.diagnostics[test] = {
          success: false,
          error: testError.message,
          timestamp: new Date().toISOString()
        };
      }
    }
    
    // Determine overall health
    const allSuccessful = Object.values(results.diagnostics).every(d => d.success);
    
    results.overall = {
      status: allSuccessful ? 'healthy' : 'unhealthy',
      testsRun: diagnosticTests.length,
      testsPassed: Object.values(results.diagnostics).filter(d => d.success).length
    };
    
    res.json(results);
    
  } catch (error) {
    console.error('❌ Complete diagnostic failed:', error.message);
    res.status(500).json({
      success: false,
      error: 'Complete diagnostic failed',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
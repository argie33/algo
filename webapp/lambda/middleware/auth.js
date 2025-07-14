const { CognitoJwtVerifier } = require('aws-jwt-verify');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

// Initialize secrets manager client
const secretsManager = new SecretsManagerClient({
  region: process.env.AWS_DEFAULT_REGION || process.env.AWS_REGION || 'us-east-1'
});

// Cache for Cognito config
let cognitoConfig = null;
let configLoadPromise = null;

// Load Cognito configuration from Secrets Manager or environment
async function loadCognitoConfig() {
  // If already loaded, return cached config
  if (cognitoConfig) {
    return cognitoConfig;
  }

  // If loading is in progress, wait for it
  if (configLoadPromise) {
    return configLoadPromise;
  }

  // Start loading config
  configLoadPromise = (async () => {
    try {
      // First try to load from Secrets Manager if ARN is provided
      if (process.env.COGNITO_SECRET_ARN) {
        console.log('Loading Cognito config from Secrets Manager...');
        const command = new GetSecretValueCommand({
          SecretId: process.env.COGNITO_SECRET_ARN
        });
        const response = await secretsManager.send(command);
        const secret = JSON.parse(response.SecretString);
        
        cognitoConfig = {
          userPoolId: secret.userPoolId,
          clientId: secret.clientId,
          domain: secret.domain,
          region: secret.region
        };
        
        console.log('Cognito config loaded from Secrets Manager');
        return cognitoConfig;
      }
      
      // Fall back to environment variables
      if (process.env.COGNITO_USER_POOL_ID && process.env.COGNITO_CLIENT_ID) {
        cognitoConfig = {
          userPoolId: process.env.COGNITO_USER_POOL_ID,
          clientId: process.env.COGNITO_CLIENT_ID,
          region: process.env.AWS_DEFAULT_REGION || process.env.AWS_REGION || 'us-east-1'
        };
        
        console.log('Cognito config loaded from environment variables');
        return cognitoConfig;
      }
      
      console.warn('No Cognito configuration found');
      return null;
    } catch (error) {
      console.error('Failed to load Cognito config:', error);
      configLoadPromise = null; // Reset to allow retry
      return null;
    }
  })();

  return configLoadPromise;
}

// Create JWT verifier
let verifier = null;
let verifierPromise = null;

async function getVerifier() {
  if (verifier) {
    return verifier;
  }

  if (verifierPromise) {
    return verifierPromise;
  }

  verifierPromise = (async () => {
    const config = await loadCognitoConfig();
    
    if (!config) {
      console.warn('Cognito configuration not available. Authentication will be disabled.');
      return null;
    }

    try {
      verifier = CognitoJwtVerifier.create({
        userPoolId: config.userPoolId,
        tokenUse: 'access',
        clientId: config.clientId,
      });
      
      console.log('Cognito JWT verifier created successfully');
      return verifier;
    } catch (error) {
      console.error('Failed to create Cognito JWT verifier:', error);
      verifierPromise = null; // Reset to allow retry
      return null;
    }
  })();

  return verifierPromise;
}

// Authentication middleware
const authenticateToken = async (req, res, next) => {
  const startTime = Date.now();
  const requestId = req.headers['x-request-id'] || 'unknown';
  
  try {
    console.log(`🔐 [${requestId}] Authentication middleware called for ${req.method} ${req.path}`);
    console.log(`🌍 [${requestId}] Environment:`, {
      NODE_ENV: process.env.NODE_ENV,
      SKIP_AUTH: process.env.SKIP_AUTH,
      hasUserPoolId: !!process.env.COGNITO_USER_POOL_ID,
      hasClientId: !!process.env.COGNITO_CLIENT_ID,
      hasSecretArn: !!process.env.COGNITO_SECRET_ARN
    });
    
    // Check for demo/development bypass
    if (process.env.SKIP_AUTH === 'true' && process.env.NODE_ENV === 'development') {
      console.log(`⚠️ [${requestId}] BYPASSING authentication in development mode`);
      req.user = {
        sub: 'dev-user-123',
        email: 'dev@example.com',
        username: 'dev-user',
        role: 'admin',
        groups: ['developers']
      };
      return next();
    }
    
    // Check for demo/development tokens first
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1]; // Bearer TOKEN
    
    console.log(`🎫 [${requestId}] Authorization header present:`, !!authHeader);
    console.log(`🎫 [${requestId}] Token extracted:`, !!token);

    // Get verifier (will load config if needed)
    console.log(`🔍 [${requestId}] Getting JWT verifier...`);
    const jwtVerifier = await getVerifier();

    // If no verifier is available, check if we should allow in development
    if (!jwtVerifier) {
      console.error(`❌ [${requestId}] JWT verifier not available`);
      console.error(`❌ [${requestId}] Config status:`, {
        cognitoConfigLoaded: !!cognitoConfig,
        userPoolId: process.env.COGNITO_USER_POOL_ID ? 'SET' : 'MISSING',
        clientId: process.env.COGNITO_CLIENT_ID ? 'SET' : 'MISSING',
        secretArn: process.env.COGNITO_SECRET_ARN ? 'SET' : 'MISSING'
      });
      
      return res.status(503).json({
        error: 'Authentication service unavailable',
        message: 'Unable to verify authentication tokens. Please check Cognito configuration.',
        details: process.env.NODE_ENV === 'development' ? {
          requestId,
          configStatus: {
            userPoolId: !!process.env.COGNITO_USER_POOL_ID,
            clientId: !!process.env.COGNITO_CLIENT_ID,
            secretArn: !!process.env.COGNITO_SECRET_ARN
          }
        } : undefined
      });
    }

    // Token already extracted above
    if (!token) {
      console.error(`❌ [${requestId}] No token found in Authorization header`);
      return res.status(401).json({
        error: 'Authentication required',
        message: 'Access token is missing from Authorization header',
        details: {
          requestId,
          authHeaderPresent: !!authHeader,
          expectedFormat: 'Bearer <token>'
        }
      });
    }

    console.log(`✅ [${requestId}] Token found, verifying with Cognito...`);
    // Verify the JWT token
    const payload = await jwtVerifier.verify(token);
    console.log(`🎯 [${requestId}] Token verified successfully`);
    
    // Add user information to request
    req.user = {
      sub: payload.sub,
      email: payload.email,
      username: payload.username,
      role: payload['custom:role'] || 'user',
      groups: payload['cognito:groups'] || []
    };

    const duration = Date.now() - startTime;
    console.log(`👤 [${requestId}] User authenticated in ${duration}ms:`, {
      sub: req.user.sub,
      email: req.user.email,
      username: req.user.username,
      role: req.user.role
    });

    next();
  } catch (error) {
    const duration = Date.now() - startTime;
    console.error(`❌ [${requestId}] Authentication error after ${duration}ms:`, {
      name: error.name,
      message: error.message,
      stack: process.env.NODE_ENV === 'development' ? error.stack : undefined
    });
    
    // Handle specific JWT errors
    if (error.name === 'TokenExpiredError') {
      console.error(`🕐 [${requestId}] Token expired`);
      return res.status(401).json({
        error: 'Token expired',
        message: 'Your session has expired. Please log in again.',
        details: { requestId, errorType: 'TOKEN_EXPIRED' }
      });
    }
    
    if (error.name === 'JsonWebTokenError') {
      console.error(`🚫 [${requestId}] Invalid token format`);
      return res.status(401).json({
        error: 'Invalid token',
        message: 'The provided token is invalid.',
        details: { requestId, errorType: 'TOKEN_INVALID' }
      });
    }

    if (error.name === 'JwtVerifyError') {
      console.error(`🚫 [${requestId}] JWT verification failed:`, error.message);
      return res.status(401).json({
        error: 'Token verification failed',
        message: 'Unable to verify the provided token.',
        details: { requestId, errorType: 'JWT_VERIFY_ERROR' }
      });
    }

    // Handle network/service errors
    if (error.code === 'ENOTFOUND' || error.code === 'ECONNREFUSED') {
      console.error(`🌐 [${requestId}] Network error during token verification`);
      return res.status(503).json({
        error: 'Authentication service unavailable',
        message: 'Unable to connect to authentication service.',
        details: { requestId, errorType: 'NETWORK_ERROR' }
      });
    }

    console.error(`🔥 [${requestId}] Generic authentication failure:`, error);
    return res.status(401).json({
      error: 'Authentication failed',
      message: 'Could not verify authentication token',
      details: { 
        requestId, 
        errorType: 'UNKNOWN_ERROR',
        errorName: error.name
      }
    });
  }
};

// Authorization middleware for role-based access
const requireRole = (roles) => {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({
        error: 'Authentication required',
        message: 'User must be authenticated to access this resource'
      });
    }

    const userRole = req.user.role;
    const userGroups = req.user.groups || [];
    
    // Check if user has required role or is in required group
    const hasRole = roles.includes(userRole);
    const hasGroup = roles.some(role => userGroups.includes(role));
    
    if (!hasRole && !hasGroup) {
      return res.status(403).json({
        error: 'Insufficient permissions',
        message: `Access denied. Required roles: ${roles.join(', ')}`
      });
    }

    next();
  };
};

// Optional authentication middleware (doesn't fail if no token)
const optionalAuth = async (req, res, next) => {
  try {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1];

    // REMOVED: Development token handling - using Cognito only

    // Get verifier
    const jwtVerifier = await getVerifier();

    if (token && jwtVerifier) {
      const payload = await jwtVerifier.verify(token);
      req.user = {
        sub: payload.sub,
        email: payload.email,
        username: payload.username,
        role: payload['custom:role'] || 'user',
        groups: payload['cognito:groups'] || []
      };
    }
    // If no token or verifier, continue without setting req.user
  } catch (error) {
    // Silently continue without authentication
    console.log('Optional auth failed:', error.message);
  }
  
  next();
};

module.exports = {
  authenticateToken,
  requireRole,
  optionalAuth
};
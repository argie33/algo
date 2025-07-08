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
  try {
    // Skip authentication in development mode
    if (process.env.NODE_ENV === 'development' && process.env.SKIP_AUTH === 'true') {
      req.user = {
        sub: 'dev-user',
        email: 'dev@example.com',
        username: 'dev-user',
        role: 'admin'
      };
      return next();
    }

    // Get verifier (will load config if needed)
    const jwtVerifier = await getVerifier();

    // If no verifier is available, skip authentication with warning
    if (!jwtVerifier) {
      console.warn('JWT verifier not available, skipping authentication');
      req.user = {
        sub: 'no-auth-user',
        email: 'no-auth@example.com',
        username: 'no-auth-user',
        role: 'user'
      };
      return next();
    }

    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1]; // Bearer TOKEN

    if (!token) {
      return res.status(401).json({
        error: 'Authentication required',
        message: 'Access token is missing from Authorization header'
      });
    }

    // Verify the JWT token
    const payload = await jwtVerifier.verify(token);
    
    // Add user information to request
    req.user = {
      sub: payload.sub,
      email: payload.email,
      username: payload.username,
      role: payload['custom:role'] || 'user',
      groups: payload['cognito:groups'] || []
    };

    next();
  } catch (error) {
    console.error('Authentication error:', error);
    
    // Handle specific JWT errors
    if (error.name === 'TokenExpiredError') {
      return res.status(401).json({
        error: 'Token expired',
        message: 'Your session has expired. Please log in again.'
      });
    }
    
    if (error.name === 'JsonWebTokenError') {
      return res.status(401).json({
        error: 'Invalid token',
        message: 'The provided token is invalid.'
      });
    }

    return res.status(401).json({
      error: 'Authentication failed',
      message: 'Could not verify authentication token'
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
    } else if (!jwtVerifier) {
      // If no verifier, create a default user
      req.user = {
        sub: 'no-auth-user',
        email: 'no-auth@example.com',
        username: 'no-auth-user',
        role: 'user',
        groups: []
      };
    }
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
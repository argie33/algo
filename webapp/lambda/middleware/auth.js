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
    console.log('🔐 Authentication middleware called');
    console.log('🌍 Environment:', process.env.NODE_ENV);
    console.log('⚙️  SKIP_AUTH:', process.env.SKIP_AUTH);
    
    // Check for demo/development tokens first
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1]; // Bearer TOKEN
    
    // Handle development tokens with CONSISTENT user info
    if (token && token.startsWith('dev-access-')) {
      console.log('🛠️  Development token detected');
      
      // Format: dev-access-{username}-{timestamp}
      const parts = token.split('-');
      if (parts.length >= 3) {
        const extractedUsername = parts[2];
        // Generate CONSISTENT user ID to match frontend devAuth service format
        const consistentUserId = `dev-${extractedUsername}`;
        const userEmail = `${extractedUsername}@example.com`;
        
        req.user = {
          sub: consistentUserId,
          email: userEmail,
          username: extractedUsername,
          role: 'user'
        };
        console.log('👤 Development user authenticated with CONSISTENT ID:', req.user);
        return next();
      }
    }

    // Get verifier (will load config if needed)
    console.log('🔍 Getting JWT verifier...');
    const jwtVerifier = await getVerifier();

    // If no verifier is available, authentication is required
    if (!jwtVerifier) {
      console.error('❌ JWT verifier not available - authentication required');
      return res.status(503).json({
        error: 'Authentication service unavailable',
        message: 'Unable to verify authentication tokens. Please try again later.'
      });
    }

    console.log('🎫 Checking authorization header...');
    // Token already extracted above
    if (!token) {
      console.error('❌ No token found in Authorization header');
      return res.status(401).json({
        error: 'Authentication required',
        message: 'Access token is missing from Authorization header'
      });
    }

    console.log('✅ Token found, verifying...');
    // Verify the JWT token
    const payload = await jwtVerifier.verify(token);
    console.log('🎯 Token verified successfully');
    
    // Add user information to request
    req.user = {
      sub: payload.sub,
      email: payload.email,
      username: payload.username,
      role: payload['custom:role'] || 'user',
      groups: payload['cognito:groups'] || []
    };

    console.log('👤 User authenticated:', {
      sub: req.user.sub,
      email: req.user.email,
      username: req.user.username,
      role: req.user.role
    });

    next();
  } catch (error) {
    console.error('❌ Authentication error:', error);
    
    // Handle specific JWT errors
    if (error.name === 'TokenExpiredError') {
      console.error('🕐 Token expired');
      return res.status(401).json({
        error: 'Token expired',
        message: 'Your session has expired. Please log in again.'
      });
    }
    
    if (error.name === 'JsonWebTokenError') {
      console.error('🚫 Invalid token');
      return res.status(401).json({
        error: 'Invalid token',
        message: 'The provided token is invalid.'
      });
    }

    console.error('🔥 Generic authentication failure');
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

    // Handle development tokens with CONSISTENT user info
    if (token && token.startsWith('dev-access-')) {
      const parts = token.split('-');
      if (parts.length >= 3) {
        const extractedUsername = parts[2];
        // Generate CONSISTENT user ID to match frontend devAuth service format
        const consistentUserId = `dev-${extractedUsername}`;
        req.user = {
          sub: consistentUserId,
          email: `${extractedUsername}@example.com`,
          username: extractedUsername,
          role: 'user',
          groups: []
        };
        return next();
      }
    }

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
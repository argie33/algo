/**
 * Enhanced Authentication Middleware with Development Mode Support
 * Handles both production Cognito authentication and development bypass
 */

const { CognitoJwtVerifier } = require('aws-jwt-verify');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const crypto = require('crypto');
const jwt = require('jsonwebtoken');

// Initialize secrets manager client
const secretsManager = new SecretsManagerClient({
  region: process.env.AWS_DEFAULT_REGION || process.env.AWS_REGION || 'us-east-1'
});

// Cache for Cognito config
let cognitoConfig = null;
let configLoadPromise = null;
let verifier = null;
let verifierPromise = null;

// Development authentication settings - check dynamically for tests
function isDevelopment() {
  return process.env.NODE_ENV === 'development' || !process.env.NODE_ENV;
}

function allowDevBypass() {
  // DISABLED: No automatic authentication bypass allowed
  // This prevents random user login and forces proper authentication
  return false;
}

/**
 * Load Cognito configuration from Secrets Manager or environment
 */
async function loadCognitoConfig() {
  if (cognitoConfig) {
    return cognitoConfig;
  }

  if (configLoadPromise) {
    return configLoadPromise;
  }

  configLoadPromise = (async () => {
    try {
      // First try to load from Secrets Manager if ARN is provided
      if (process.env.COGNITO_SECRET_ARN) {
        console.log('📡 Loading Cognito config from Secrets Manager...');
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
        
        console.log('✅ Cognito config loaded from Secrets Manager');
        return cognitoConfig;
      }
      
      // Fall back to environment variables
      if (process.env.COGNITO_USER_POOL_ID && process.env.COGNITO_CLIENT_ID) {
        cognitoConfig = {
          userPoolId: process.env.COGNITO_USER_POOL_ID,
          clientId: process.env.COGNITO_CLIENT_ID,
          region: process.env.AWS_DEFAULT_REGION || process.env.AWS_REGION || 'us-east-1'
        };
        
        console.log('✅ Cognito config loaded from environment variables');
        return cognitoConfig;
      }
      
      console.warn('⚠️ No Cognito configuration found');
      return null;
    } catch (error) {
      console.error('❌ Failed to load Cognito config:', error);
      configLoadPromise = null; // Reset to allow retry
      return null;
    }
  })();

  return configLoadPromise;
}

/**
 * Create JWT verifier for Cognito tokens
 */
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
      console.warn('⚠️ Cognito configuration not available. Production authentication will be disabled.');
      return null;
    }

    try {
      verifier = CognitoJwtVerifier.create({
        userPoolId: config.userPoolId,
        tokenUse: 'access',
        clientId: config.clientId,
      });
      
      console.log('✅ Cognito JWT verifier created successfully');
      return verifier;
    } catch (error) {
      console.error('❌ Failed to create Cognito JWT verifier:', error);
      verifierPromise = null; // Reset to allow retry
      return null;
    }
  })();

  return verifierPromise;
}

/**
 * Generate development authentication token
 */
function generateDevToken(userId = 'dev-user', email = 'dev@example.com') {
  const payload = {
    sub: userId,
    email: email,
    username: email.split('@')[0],
    'custom:role': 'admin',
    'cognito:groups': ['admin'],
    given_name: 'Dev',
    family_name: 'User',
    email_verified: true,
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + (24 * 60 * 60), // 24 hours
    aud: 'development-client',
    iss: 'https://cognito-idp.us-east-1.amazonaws.com/development'
  };

  const secret = process.env.DEV_JWT_SECRET || 'development-secret-key';
  return jwt.sign(payload, secret);
}

/**
 * Validate development token
 */
function validateDevToken(token) {
  try {
    const secret = process.env.DEV_JWT_SECRET || 'development-secret-key';
    const decoded = jwt.verify(token, secret);
    return { valid: true, payload: decoded };
  } catch (error) {
    return { valid: false, error: error.message };
  }
}

/**
 * Main authentication middleware
 */
const authenticateToken = async (req, res, next) => {
  const startTime = Date.now();
  const requestId = req.headers['x-request-id'] || crypto.randomUUID();
  const { getClientIP } = require('../utils/ipDetection');
  const clientIp = getClientIP(req);
  const userAgent = req.headers['user-agent'] || 'unknown';
  
  try {
    console.log(`🔐 [${requestId}] Authentication middleware called for ${req.method} ${req.path}`);
    
    // Get authorization header
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1]; // Bearer TOKEN
    
    console.log(`🎫 [${requestId}] Token present: ${!!token}`);
    
    // If no token provided, check if we're in development mode
    if (!token) {
      if (allowDevBypass()) {
        console.log(`🔧 [${requestId}] No token provided, using development bypass`);
        
        // Create development user
        req.user = {
          sub: 'dev-user-' + Date.now(),
          email: 'dev@example.com',
          username: 'dev-user',
          role: 'admin',
          groups: ['admin'],
          clientIp,
          userAgent,
          requestId,
          authenticatedAt: new Date().toISOString(),
          authMethod: 'dev-bypass',
          givenName: 'Dev',
          familyName: 'User',
          emailVerified: true,
          isDevelopment: true
        };
        
        console.log(`✅ [${requestId}] Development authentication successful`);
        return next();
      } else {
        console.error(`❌ [${requestId}] No token found and development bypass disabled`);
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
    }

    // Try to validate as development token first (if allowed)
    if (allowDevBypass()) {
      const devValidation = validateDevToken(token);
      if (devValidation.valid) {
        console.log(`🔧 [${requestId}] Valid development token detected`);
        
        req.user = {
          sub: devValidation.payload.sub,
          email: devValidation.payload.email,
          username: devValidation.payload.username,
          role: devValidation.payload['custom:role'] || 'user',
          groups: devValidation.payload['cognito:groups'] || [],
          clientIp,
          userAgent,
          requestId,
          authenticatedAt: new Date().toISOString(),
          authMethod: 'dev-token',
          givenName: devValidation.payload.given_name,
          familyName: devValidation.payload.family_name,
          emailVerified: devValidation.payload.email_verified,
          isDevelopment: true
        };
        
        console.log(`✅ [${requestId}] Development token authentication successful`);
        return next();
      }
    }

    // Try Cognito JWT verification
    console.log(`🔍 [${requestId}] Attempting Cognito JWT verification...`);
    const jwtVerifier = await module.exports.getVerifier();

    if (!jwtVerifier) {
      // No Cognito verifier available
      if (allowDevBypass()) {
        console.log(`🔧 [${requestId}] Cognito not available, allowing development access`);
        
        // Create development user even with invalid token
        req.user = {
          sub: 'dev-user-fallback',
          email: 'dev@example.com',
          username: 'dev-user',
          role: 'admin',
          groups: ['admin'],
          clientIp,
          userAgent,
          requestId,
          authenticatedAt: new Date().toISOString(),
          authMethod: 'dev-fallback',
          givenName: 'Dev',
          familyName: 'User',
          emailVerified: true,
          isDevelopment: true
        };
        
        console.log(`✅ [${requestId}] Development fallback authentication successful`);
        return next();
      } else {
        console.error(`❌ [${requestId}] Cognito verifier not available and development bypass disabled`);
        throw new Error('Authentication service unavailable - Cognito verifier not configured');
      }
    }

    // Verify Cognito JWT token
    const payload = await jwtVerifier.verify(token);
    console.log(`🎯 [${requestId}] Cognito token verified successfully`);
    
    // Add user information to request
    req.user = {
      sub: payload.sub,
      email: payload.email,
      username: payload.username,
      role: payload['custom:role'] || 'user',
      groups: payload['cognito:groups'] || [],
      clientIp,
      userAgent,
      requestId,
      authenticatedAt: new Date().toISOString(),
      authMethod: 'cognito',
      tokenIssuedAt: new Date(payload.iat * 1000).toISOString(),
      tokenExpiresAt: new Date(payload.exp * 1000).toISOString(),
      givenName: payload.given_name,
      familyName: payload.family_name,
      phoneNumber: payload.phone_number,
      phoneNumberVerified: payload.phone_number_verified,
      emailVerified: payload.email_verified,
      organization: payload['custom:organization'],
      jobTitle: payload['custom:job_title'],
      riskTolerance: payload['custom:risk_tolerance'],
      investmentExperience: payload['custom:investment_experience'],
      accreditedInvestor: payload['custom:accredited_investor'],
      isDevelopment: false
    };

    const duration = Date.now() - startTime;
    console.log(`✅ [${requestId}] Cognito authentication successful in ${duration}ms`);
    
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
    console.log(`🔍 DEBUG: Checking error:`, {
      code: error.code,
      message: error.message,
      name: error.name,
      hasCode: 'code' in error,
      keys: Object.keys(error)
    });
    
    if (error.code === 'ENOTFOUND' || error.code === 'ECONNREFUSED' || 
        (error.message && error.message.includes('Network error'))) {
      console.error(`🌐 [${requestId}] Network error during token verification`);
      return res.status(503).json({
        error: 'Authentication service unavailable',
        message: 'Unable to connect to authentication service.',
        details: { requestId, errorType: 'NETWORK_ERROR' }
      });
    }

    // Development fallback for authentication errors
    if (allowDevBypass()) {
      console.warn(`🔧 [${requestId}] Authentication failed, using development fallback`);
      
      req.user = {
        sub: 'dev-user-error-fallback',
        email: 'dev@example.com',
        username: 'dev-user',
        role: 'admin',
        groups: ['admin'],
        clientIp,
        userAgent,
        requestId,
        authenticatedAt: new Date().toISOString(),
        authMethod: 'dev-error-fallback',
        givenName: 'Dev',
        familyName: 'User',
        emailVerified: true,
        isDevelopment: true,
        authError: error.message
      };
      
      console.log(`✅ [${requestId}] Development error fallback successful`);
      return next();
    }

    console.error(`🔥 [${requestId}] Final authentication failure:`, error);
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

/**
 * Role-based authorization middleware
 */
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

/**
 * Optional authentication middleware (doesn't fail if no token)
 */
const optionalAuth = async (req, res, next) => {
  try {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1];

    if (!token) {
      // No token provided, continue without authentication
      return next();
    }

    // Create a mock next function to capture auth results
    let authSucceeded = false;
    const mockNext = (error) => {
      if (!error) {
        authSucceeded = true;
      }
    };

    // Try to authenticate, but don't fail if it doesn't work
    await authenticateToken(req, res, mockNext);
    
    // Only continue if auth succeeded, otherwise silently continue without user
    if (!authSucceeded) {
      // Remove any user object that might have been set
      delete req.user;
    }
    
    next();
  } catch (error) {
    // Silently continue without authentication
    console.log('Optional auth failed:', error.message);
    // Ensure no user object is set
    delete req.user;
    next();
  }
};

/**
 * Generate development authentication token for testing
 */
const generateTestToken = (userId = 'test-user', email = 'test@example.com') => {
  return generateDevToken(userId, email);
};

/**
 * Clear cached configuration (for testing)
 */
const clearConfigCache = () => {
  cognitoConfig = null;
  configLoadPromise = null;
  verifier = null;
  verifierPromise = null;
};

/**
 * Authentication status endpoint
 */
const getAuthStatus = async (req, res) => {
  try {
    const cognitoConfig = await loadCognitoConfig();
    const verifier = await getVerifier();
    
    res.json({
      status: 'healthy',
      configuration: {
        cognitoConfigured: !!cognitoConfig,
        verifierAvailable: !!verifier,
        developmentMode: isDevelopment(),
        developmentBypassAllowed: allowDevBypass()
      },
      cognito: cognitoConfig ? {
        userPoolId: cognitoConfig.userPoolId,
        region: cognitoConfig.region,
        configured: true
      } : {
        configured: false
      },
      environment: {
        NODE_ENV: process.env.NODE_ENV,
        AWS_REGION: process.env.AWS_REGION,
        hasUserPoolId: !!process.env.COGNITO_USER_POOL_ID,
        hasClientId: !!process.env.COGNITO_CLIENT_ID,
        hasSecretArn: !!process.env.COGNITO_SECRET_ARN
      }
    });
  } catch (error) {
    try {
      res.status(500).json({
        status: 'error',
        error: error.message,
        timestamp: new Date().toISOString()
      });
    } catch (responseError) {
      // If even the error response fails, log it
      console.error('Failed to send error response:', responseError);
    }
  }
};

module.exports = {
  authenticateToken,
  requireRole,
  optionalAuth,
  generateTestToken,
  getAuthStatus,
  loadCognitoConfig,
  getVerifier,
  clearConfigCache
};
/**
 * Secure Authentication Middleware - Security-First Design
 * 
 * FEATURES:
 * ✅ Zero bypasses in production (ever)
 * ✅ Clear production/development boundaries
 * ✅ Complete security audit logging
 * ✅ Fail-safe defaults to most secure mode
 * ✅ Simplified mode detection logic
 * ✅ Comprehensive error handling
 */

const { CognitoJwtVerifier } = require('aws-jwt-verify');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const crypto = require('crypto');
const jwt = require('jsonwebtoken');

// Authentication Modes (explicit and secure)
const AuthMode = {
  PRODUCTION_ONLY: 'PRODUCTION_ONLY',           // Zero bypasses, Cognito only
  DEVELOPMENT_WITH_AUDIT: 'DEVELOPMENT_WITH_AUDIT'  // Local dev only, fully audited
};

// Security Audit Logger
class SecurityAuditLogger {
  constructor() {
    this.auditLog = [];
    this.maxLogSize = 1000;
  }

  async logAuthAttempt(attempt, result, error = null) {
    const auditEntry = {
      timestamp: new Date().toISOString(),
      requestId: attempt.requestId,
      clientIp: attempt.clientIp,
      userAgent: attempt.userAgent,
      endpoint: attempt.endpoint,
      method: attempt.method,
      authMode: attempt.authMode,
      tokenPresent: attempt.tokenPresent,
      result: result, // 'SUCCESS', 'FAILURE', 'BYPASS'
      error: error?.message,
      errorType: error?.name,
      userId: result === 'SUCCESS' ? attempt.userId : null,
      authMethod: attempt.authMethod,
      duration: attempt.duration
    };

    this.auditLog.push(auditEntry);
    
    // Prevent memory leaks
    if (this.auditLog.length > this.maxLogSize) {
      this.auditLog = this.auditLog.slice(-this.maxLogSize / 2);
    }

    // Log to console with appropriate level
    if (result === 'FAILURE' || error) {
      console.error('🚨 AUTH SECURITY EVENT:', auditEntry);
    } else if (result === 'BYPASS') {
      console.warn('🔧 AUTH BYPASS EVENT:', auditEntry);
    } else {
      console.log('✅ AUTH SUCCESS EVENT:', auditEntry);
    }

    // In production, send to security monitoring system
    if (process.env.NODE_ENV === 'production') {
      await this.sendToSecurityMonitoring(auditEntry);
    }
  }

  async logFailure(attempt, error) {
    await this.logAuthAttempt(attempt, 'FAILURE', error);
  }

  async logSuccess(attempt, authMethod) {
    await this.logAuthAttempt(attempt, 'SUCCESS');
  }

  async logBypass(attempt, reason) {
    await this.logAuthAttempt(attempt, 'BYPASS', new Error(reason));
  }

  async sendToSecurityMonitoring(auditEntry) {
    // Implement CloudWatch or security system integration
    try {
      // This would integrate with your security monitoring system
      console.log('📊 SECURITY MONITOR:', auditEntry);
    } catch (error) {
      console.error('❌ Failed to send security audit:', error);
    }
  }

  getAuditStats() {
    const last24h = this.auditLog.filter(
      entry => new Date() - new Date(entry.timestamp) < 24 * 60 * 60 * 1000
    );

    return {
      totalAttempts: last24h.length,
      successful: last24h.filter(e => e.result === 'SUCCESS').length,
      failed: last24h.filter(e => e.result === 'FAILURE').length,
      bypassed: last24h.filter(e => e.result === 'BYPASS').length,
      uniqueIPs: new Set(last24h.map(e => e.clientIp)).size,
      errorTypes: [...new Set(last24h.filter(e => e.error).map(e => e.errorType))]
    };
  }
}

// Authentication Attempt Context
class AuthenticationAttempt {
  constructor(req) {
    this.startTime = Date.now();
    this.requestId = req.headers['x-request-id'] || crypto.randomUUID();
    this.clientIp = this.extractClientIP(req);
    this.userAgent = req.headers['user-agent'] || 'unknown';
    this.endpoint = req.path;
    this.method = req.method;
    this.authHeader = req.headers['authorization'];
    this.tokenPresent = !!(this.authHeader && this.authHeader.startsWith('Bearer '));
    this.token = this.tokenPresent ? this.authHeader.split(' ')[1] : null;
    this.authMode = null;
    this.authMethod = null;
    this.userId = null;
  }

  extractClientIP(req) {
    return req.headers['x-forwarded-for']?.split(',')[0] ||
           req.headers['x-real-ip'] ||
           req.connection?.remoteAddress ||
           req.socket?.remoteAddress ||
           'unknown';
  }

  get duration() {
    return Date.now() - this.startTime;
  }
}

// Secure Authentication Manager
class SecureAuthenticationManager {
  constructor() {
    this.mode = this.determineAuthMode();
    this.cognitoConfig = null;
    this.cognitoVerifier = null;
    this.auditLogger = new SecurityAuditLogger();
    this.secretsManager = new SecretsManagerClient({
      region: process.env.AWS_REGION || 'us-east-1'
    });

    console.log(`🔐 Authentication Manager initialized in ${this.mode} mode`);
  }

  // CRITICAL: Simplified, secure mode detection
  determineAuthMode() {
    // ABSOLUTE RULE: No bypasses in production, ever
    if (process.env.NODE_ENV === 'production') {
      console.log('🛡️ PRODUCTION MODE: Zero bypasses enabled');
      return AuthMode.PRODUCTION_ONLY;
    }

    // Only allow development mode in true local development
    if (this.isLocalDevelopment()) {
      console.log('🔧 DEVELOPMENT MODE: Local development with audit logging');
      return AuthMode.DEVELOPMENT_WITH_AUDIT;
    }

    // FAIL-SAFE: Default to production mode for security
    console.warn('⚠️ FAIL-SAFE: Defaulting to production mode for security');
    return AuthMode.PRODUCTION_ONLY;
  }

  // CRITICAL: True local development detection
  isLocalDevelopment() {
    // Must NOT be running in AWS Lambda
    if (process.env.AWS_LAMBDA_FUNCTION_NAME || process.env.AWS_EXECUTION_ENV) {
      return false;
    }

    // Must be explicitly set to development
    if (process.env.NODE_ENV !== 'development') {
      return false;
    }

    // Must have local development flag
    if (process.env.LOCAL_DEVELOPMENT !== 'true') {
      return false;
    }

    return true;
  }

  async authenticate(req, res, next) {
    const attempt = new AuthenticationAttempt(req);
    attempt.authMode = this.mode;

    try {
      switch (this.mode) {
        case AuthMode.PRODUCTION_ONLY:
          await this.productionAuth(attempt, req, res, next);
          break;
          
        case AuthMode.DEVELOPMENT_WITH_AUDIT:
          await this.developmentAuth(attempt, req, res, next);
          break;
          
        default:
          throw new SecurityError(`Invalid authentication mode: ${this.mode}`);
      }
    } catch (error) {
      await this.auditLogger.logFailure(attempt, error);
      this.sendErrorResponse(res, error, attempt);
    }
  }

  // PRODUCTION AUTHENTICATION: Cognito only, zero bypasses
  async productionAuth(attempt, req, res, next) {
    console.log(`🛡️ [${attempt.requestId}] Production authentication for ${attempt.endpoint}`);

    // CRITICAL: Token is absolutely required in production
    if (!attempt.tokenPresent) {
      throw new AuthenticationError('Authentication token required', 'TOKEN_MISSING');
    }

    // Get Cognito verifier
    const verifier = await this.getCognitoVerifier();
    if (!verifier) {
      throw new AuthenticationError('Authentication service unavailable', 'COGNITO_UNAVAILABLE');
    }

    // Verify token with Cognito
    const payload = await verifier.verify(attempt.token);
    
    // Create secure user context
    req.user = this.createUserContext(payload, attempt, 'cognito');
    attempt.userId = payload.sub;
    attempt.authMethod = 'cognito';

    await this.auditLogger.logSuccess(attempt, 'cognito');
    console.log(`✅ [${attempt.requestId}] Production authentication successful in ${attempt.duration}ms`);
    
    next();
  }

  // DEVELOPMENT AUTHENTICATION: Local only with full audit
  async developmentAuth(attempt, req, res, next) {
    console.log(`🔧 [${attempt.requestId}] Development authentication for ${attempt.endpoint}`);

    // Try Cognito first (preferred even in development)
    if (attempt.tokenPresent) {
      try {
        const verifier = await this.getCognitoVerifier();
        if (verifier) {
          const payload = await verifier.verify(attempt.token);
          req.user = this.createUserContext(payload, attempt, 'cognito');
          attempt.userId = payload.sub;
          attempt.authMethod = 'cognito';
          
          await this.auditLogger.logSuccess(attempt, 'cognito');
          console.log(`✅ [${attempt.requestId}] Development Cognito auth successful`);
          return next();
        }
      } catch (error) {
        console.warn(`⚠️ [${attempt.requestId}] Cognito auth failed in development:`, error.message);
      }
    }

    // DEVELOPMENT BYPASS: Only in local development with full audit
    console.warn(`🔧 [${attempt.requestId}] Using development bypass - LOCAL DEVELOPMENT ONLY`);
    
    req.user = this.createDevelopmentUserContext(attempt);
    attempt.userId = 'dev-user';
    attempt.authMethod = 'development-bypass';

    await this.auditLogger.logBypass(attempt, 'Local development bypass');
    
    next();
  }

  async getCognitoVerifier() {
    if (this.cognitoVerifier) {
      return this.cognitoVerifier;
    }

    const config = await this.loadCognitoConfig();
    if (!config) {
      return null;
    }

    try {
      this.cognitoVerifier = CognitoJwtVerifier.create({
        userPoolId: config.userPoolId,
        tokenUse: 'access',
        clientId: config.clientId,
      });
      
      console.log('✅ Cognito JWT verifier created');
      return this.cognitoVerifier;
    } catch (error) {
      console.error('❌ Failed to create Cognito verifier:', error);
      return null;
    }
  }

  async loadCognitoConfig() {
    if (this.cognitoConfig) {
      return this.cognitoConfig;
    }

    try {
      // Try Secrets Manager first
      if (process.env.COGNITO_SECRET_ARN) {
        const command = new GetSecretValueCommand({
          SecretId: process.env.COGNITO_SECRET_ARN
        });
        const response = await this.secretsManager.send(command);
        const secret = JSON.parse(response.SecretString);
        
        this.cognitoConfig = {
          userPoolId: secret.userPoolId,
          clientId: secret.clientId,
          domain: secret.domain,
          region: secret.region
        };
        
        console.log('✅ Cognito config loaded from Secrets Manager');
        return this.cognitoConfig;
      }
      
      // Fallback to environment variables
      if (process.env.COGNITO_USER_POOL_ID && process.env.COGNITO_CLIENT_ID) {
        this.cognitoConfig = {
          userPoolId: process.env.COGNITO_USER_POOL_ID,
          clientId: process.env.COGNITO_CLIENT_ID,
          region: process.env.AWS_REGION || 'us-east-1'
        };
        
        console.log('✅ Cognito config loaded from environment');
        return this.cognitoConfig;
      }
      
      console.warn('⚠️ No Cognito configuration found');
      return null;
    } catch (error) {
      console.error('❌ Failed to load Cognito config:', error);
      return null;
    }
  }

  createUserContext(payload, attempt, authMethod) {
    return {
      sub: payload.sub,
      email: payload.email,
      username: payload.username,
      role: payload['custom:role'] || 'user',
      groups: payload['cognito:groups'] || [],
      givenName: payload.given_name,
      familyName: payload.family_name,
      emailVerified: payload.email_verified,
      
      // Security context
      clientIp: attempt.clientIp,
      userAgent: attempt.userAgent,
      requestId: attempt.requestId,
      authenticatedAt: new Date().toISOString(),
      authMethod: authMethod,
      tokenIssuedAt: new Date(payload.iat * 1000).toISOString(),
      tokenExpiresAt: new Date(payload.exp * 1000).toISOString(),
      
      // Security flags
      isDevelopment: false,
      isProduction: true
    };
  }

  createDevelopmentUserContext(attempt) {
    return {
      sub: 'dev-user-' + Date.now(),
      email: 'dev@localhost.com',
      username: 'dev-user',
      role: 'admin',
      groups: ['admin', 'developer'],
      givenName: 'Development',
      familyName: 'User',
      emailVerified: true,
      
      // Security context
      clientIp: attempt.clientIp,
      userAgent: attempt.userAgent,
      requestId: attempt.requestId,
      authenticatedAt: new Date().toISOString(),
      authMethod: 'development-bypass',
      
      // Security flags
      isDevelopment: true,
      isProduction: false,
      
      // Development metadata
      developmentWarning: 'This is a development user - not for production use'
    };
  }

  sendErrorResponse(res, error, attempt) {
    let status = 401;
    let errorType = 'AUTHENTICATION_FAILED';
    let message = 'Authentication failed';

    // Handle specific error types
    if (error.name === 'TokenExpiredError') {
      errorType = 'TOKEN_EXPIRED';
      message = 'Authentication token has expired';
    } else if (error.name === 'JsonWebTokenError') {
      errorType = 'TOKEN_INVALID';
      message = 'Invalid authentication token';
    } else if (error.name === 'JwtVerifyError') {
      errorType = 'TOKEN_VERIFICATION_FAILED';
      message = 'Token verification failed';
    } else if (error.code === 'ENOTFOUND' || error.code === 'ECONNREFUSED') {
      status = 503;
      errorType = 'SERVICE_UNAVAILABLE';
      message = 'Authentication service unavailable';
    }

    const response = {
      error: {
        type: errorType,
        message: message,
        timestamp: new Date().toISOString(),
        requestId: attempt.requestId
      }
    };

    // Add debug info in development
    if (process.env.NODE_ENV === 'development') {
      response.error.debug = {
        originalError: error.message,
        authMode: attempt.authMode,
        tokenPresent: attempt.tokenPresent
      };
    }

    console.error(`❌ [${attempt.requestId}] Auth error: ${message} (${error.message})`);
    
    res.status(status).json(response);
  }

  // Role-based authorization
  requireRole(roles) {
    return (req, res, next) => {
      if (!req.user) {
        return res.status(401).json({
          error: {
            type: 'AUTHENTICATION_REQUIRED',
            message: 'Authentication required to access this resource'
          }
        });
      }

      const userRole = req.user.role;
      const userGroups = req.user.groups || [];
      
      const hasRole = roles.includes(userRole);
      const hasGroup = roles.some(role => userGroups.includes(role));
      
      if (!hasRole && !hasGroup) {
        return res.status(403).json({
          error: {
            type: 'INSUFFICIENT_PERMISSIONS',
            message: `Access denied. Required roles: ${roles.join(', ')}`
          }
        });
      }

      next();
    };
  }

  // Get authentication status for monitoring
  getStatus() {
    return {
      mode: this.mode,
      cognitoConfigured: !!this.cognitoConfig,
      verifierAvailable: !!this.cognitoVerifier,
      auditStats: this.auditLogger.getAuditStats(),
      environment: {
        nodeEnv: process.env.NODE_ENV,
        awsLambda: !!process.env.AWS_LAMBDA_FUNCTION_NAME,
        localDev: process.env.LOCAL_DEVELOPMENT === 'true'
      }
    };
  }

  // Development token generation (only in development mode)
  generateDevToken(userId = 'dev-user', email = 'dev@localhost.com') {
    if (this.mode !== AuthMode.DEVELOPMENT_WITH_AUDIT) {
      throw new Error('Development tokens can only be generated in development mode');
    }

    const payload = {
      sub: userId,
      email: email,
      username: email.split('@')[0],
      'custom:role': 'admin',
      'cognito:groups': ['admin', 'developer'],
      given_name: 'Dev',
      family_name: 'User',
      email_verified: true,
      iat: Math.floor(Date.now() / 1000),
      exp: Math.floor(Date.now() / 1000) + (24 * 60 * 60),
      aud: 'development-client',
      iss: 'https://localhost:3000/development'
    };

    const secret = process.env.DEV_JWT_SECRET || 'development-secret-key';
    return jwt.sign(payload, secret);
  }
}

// Custom Error Classes
class AuthenticationError extends Error {
  constructor(message, type = 'AUTHENTICATION_ERROR') {
    super(message);
    this.name = 'AuthenticationError';
    this.type = type;
  }
}

class SecurityError extends Error {
  constructor(message) {
    super(message);
    this.name = 'SecurityError';
  }
}

// Create singleton instance
const secureAuthManager = new SecureAuthenticationManager();

// Export middleware functions
const authenticateToken = (req, res, next) => {
  return secureAuthManager.authenticate(req, res, next);
};

const requireRole = (roles) => {
  return secureAuthManager.requireRole(roles);
};

const getAuthStatus = (req, res) => {
  try {
    res.json({
      status: 'healthy',
      ...secureAuthManager.getStatus()
    });
  } catch (error) {
    res.status(500).json({
      status: 'error',
      error: error.message
    });
  }
};

const generateTestToken = (userId, email) => {
  try {
    return secureAuthManager.generateDevToken(userId, email);
  } catch (error) {
    throw new Error(`Cannot generate test token: ${error.message}`);
  }
};

module.exports = {
  authenticateToken,
  requireRole,
  getAuthStatus,
  generateTestToken,
  AuthMode,
  SecurityAuditLogger
};
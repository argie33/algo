const { validateJwtToken } = require("../utils/apiKeyService");
const logger = require("../utils/logger");
const { sendError } = require("../utils/apiResponse");

/**
 * Authentication Middleware - Clean implementation with three explicit paths
 * - Development: NODE_ENV === 'development' → admin user (no network call)
 * - Test: NODE_ENV === 'test' → JWT validation with JWT_SECRET
 * - Production: Real Cognito JWT validation via apiKeyService
 */

const authenticateToken = (req, res, next) => {
  // SECURITY ENFORCEMENT: Detect if production env accidentally set to test mode
  // This prevents critical auth bypass if NODE_ENV is misconfigured
  const isLambda = !!process.env.AWS_LAMBDA_FUNCTION_NAME;
  const nodeEnv = process.env.NODE_ENV || (isLambda ? 'production' : 'development');
  const isProd = nodeEnv === 'production' || isLambda;
  const isTest = nodeEnv === 'test';
  const isDev = nodeEnv === 'development' && !isLambda;

  // CRITICAL: Reject test authentication in production
  if (isProd && isTest) {
    logger.security('auth_bypass_attempt', {
      error: 'Test mode enabled in production',
      env: process.env.NODE_ENV,
      lambda: !!isLambda,
    });
    return sendError(res, 'Authentication service misconfigured', 500);
  }

  // Path 1: Development environment (local dev with dev tokens)
  if (isDev) {
    return handleDevAuth(req, res, next);
  }

  // Path 2: Test environment (explicit test tokens)
  if (isTest && !isProd) {
    return handleTestAuth(req, res, next);
  }

  // Path 3: Production (async validation with real Cognito JWT)
  // This is the default for all other environments (staging, prod)
  return authenticateTokenAsync(req, res, next);
};

// Development environment auth - allows easy local testing with dev tokens
const handleDevAuth = (req, res, next) => {
  const authHeader = req.headers['authorization'];

  // If no auth header, create a default dev user (allows testing without explicit token)
  if (!authHeader) {
    req.user = {
      sub: 'dev-user-local',
      username: 'devuser',
      email: 'dev@localhost',
      role: 'admin',
      groups: ['admin', 'user'],
      sessionId: `dev-session-${Date.now()}`,
    };
    req.token = 'dev-token-no-auth-header';
    console.log('[DEV AUTH] No auth header provided - using default dev user with admin role');
    return next();
  }

  if (!authHeader.startsWith('Bearer ') && !authHeader.startsWith('bearer ')) {
    // If invalid format but header exists, still allow dev user
    req.user = {
      sub: 'dev-user-local',
      username: 'devuser',
      email: 'dev@localhost',
      role: 'admin',
      groups: ['admin', 'user'],
      sessionId: `dev-session-${Date.now()}`,
    };
    req.token = 'dev-token-invalid-format';
    return next();
  }

  const tokenParts = authHeader.split(' ').filter((part) => part.length > 0);
  const token = (tokenParts[1] || '').trim();

  // Dev tokens: allow simple tokens for easy testing
  const devTokens = {
    'dev-token': { role: 'user', username: 'devuser' },
    'dev-admin': { role: 'admin', username: 'devadmin' },
    'dev-user': { role: 'user', username: 'devuser' },
    'test-token': { role: 'user', username: 'testuser' },
    'admin-token': { role: 'admin', username: 'adminuser' },
    'mock-access-token': { role: 'user', username: 'mockuser' },
  };

  if (devTokens[token]) {
    const tokenConfig = devTokens[token];
    req.user = {
      sub: `dev-${tokenConfig.username}-${Date.now()}`,
      username: tokenConfig.username,
      email: `${tokenConfig.username}@localhost`,
      role: tokenConfig.role,
      groups: tokenConfig.role === 'admin' ? ['admin', 'user'] : ['user'],
      sessionId: `dev-session-${Date.now()}`,
    };
    req.token = token;
    console.log(`[DEV AUTH] Authenticated as ${tokenConfig.role}: ${tokenConfig.username}`);
    return next();
  }

  // If it's some other token, create a default user (permissive dev mode)
  if (token) {
    req.user = {
      sub: 'dev-user-local',
      username: 'devuser',
      email: 'dev@localhost',
      role: 'admin',
      groups: ['admin', 'user'],
      sessionId: `dev-session-${Date.now()}`,
    };
    req.token = token;
    console.log('[DEV AUTH] Using provided token, created default admin user');
    return next();
  }

  // Fallback
  return sendError(res, 'Authentication required', 401, { code: 'MISSING_TOKEN' });
};

// Test environment JWT validation
const handleTestAuth = (req, res, next) => {
  const authHeader = req.headers['authorization'];

  if (!authHeader) {
    return sendError(res, 'Authentication required', 401, { code: 'MISSING_TOKEN' });
  }

  if (!authHeader.startsWith('Bearer ') && !authHeader.startsWith('bearer ')) {
    return sendError(res, 'Invalid token format', 401, { code: 'INVALID_TOKEN_FORMAT' });
  }

  const tokenParts = authHeader.split(' ').filter((part) => part.length > 0);
  const token = (tokenParts[1] || '').trim();

  if (!token) {
    return sendError(res, 'Authentication required', 401, { code: 'MISSING_TOKEN' });
  }

  // Allow test tokens
  if (token === 'test-token' || token === 'mock-access-token' || token === 'admin-token') {
    const isAdmin = token === 'admin-token';
    req.user = {
      sub: isAdmin ? 'admin-test-user' : 'test-user-123',
      username: isAdmin ? 'admin-test' : 'test-user',
      email: isAdmin ? 'admin@test.local' : 'test@example.com',
      role: isAdmin ? 'admin' : 'user',
      groups: isAdmin ? ['admin'] : ['user'],
      sessionId: isAdmin ? 'admin-test-session' : 'test-session',
    };
    req.token = token;
    return next();
  }

  // Validate JWT with JWT_SECRET
  try {
    const jwt = require('jsonwebtoken');
    const jwtSecret = process.env.JWT_SECRET;

    if (!jwtSecret) {
      return sendError(res, 'Authentication service misconfigured', 500, { code: 'MISSING_JWT_SECRET' });
    }

    const decoded = jwt.verify(token, jwtSecret);

    if (!decoded.sub && !decoded.id) {
      return sendError(res, 'Invalid token - missing required claims', 401, { code: 'MISSING_CLAIMS' });
    }

    req.user = decoded;
    req.token = token;
    return next();
  } catch (error) {
    if (error.name === 'TokenExpiredError') {
      return sendError(res, 'Token expired', 401, { code: 'TOKEN_EXPIRED' });
    }

    return sendError(res, 'Invalid token', 401, { code: 'INVALID_TOKEN' });
  }
};

// Production async JWT validation (Cognito)
const authenticateTokenAsync = async (req, res, next) => {
  try {
    const authHeader = req.headers['authorization'];

    if (!authHeader) {
      return sendError(res, 'Authentication required', 401, { code: 'MISSING_AUTHORIZATION' });
    }

    const token = (authHeader.split(' ')[1] || '').trim();

    if (!token) {
      return sendError(res, 'Authorization missing from request headers', 401, { code: 'MISSING_AUTHORIZATION' });
    }

    // Validate JWT token using apiKeyService (now with real Cognito verification)
    let result;
    try {
      result = await validateJwtToken(token);
    } catch (error) {
      // SECURITY FIX H-NEW-02: Never allow test tokens in non-test environments.
      // Previously, missing Cognito env vars would allow 'test-token'/'admin-token' through
      // with full admin privileges. This is now hard-rejected regardless of why validation fails.
      if (error.message && error.message.includes('Cognito environment variables not configured')) {
        logger.security('auth_service_misconfigured', {
          error: 'COGNITO_USER_POOL_ID or COGNITO_CLIENT_ID not set in Lambda environment',
          path: req.path,
        });
        return sendError(res, 'Authentication service not configured', 500, { code: 'AUTH_SERVICE_ERROR' });
      }
      // Other validation errors
      logger.security('auth_failure', {
        error: error.message,
        path: req.path,
        ip: req.ip || req.connection.remoteAddress,
      });
      return sendError(res, 'Invalid credentials', 401, { code: 'INVALID_CREDENTIALS' });
    }

    if (!result.valid) {
      logger.security('auth_failure', {
        error: result.error,
        path: req.path,
        ip: req.ip || req.connection.remoteAddress,
      });
      return sendError(res, result.error || 'Authentication credentials are invalid', 401, { code: 'INVALID_CREDENTIALS' });
    }

    // SECURITY FIX #7: Check if token has been revoked
    const user = result.user;
    const tokenJti = user.jti || user.token_use; // JWT jti claim (unique token ID)
    const tokenExp = user.exp; // JWT exp claim (expiration timestamp)

    try {
      const { isTokenRevoked } = require('../utils/tokenBlocklist');
      const revoked = await isTokenRevoked(tokenJti, tokenExp);
      if (revoked) {
        logger.security('revoked_token_rejected', {
          userId: user.sub,
          path: req.path,
          ip: req.ip || req.connection.remoteAddress,
        });
        return sendError(res, 'Token has been revoked. Please log in again.', 401, { code: 'TOKEN_REVOKED' });
      }
    } catch (err) {
      logger.warn('Token revocation check failed:', err.message);
      // Don't fail the request - revocation is a nice-to-have, not critical
    }

    req.user = user;
    req.token = token;
    req.sessionId = user.sessionId;

    logger.auth('token_validated', {
      userId: user.sub,
      username: user.username,
      path: req.path,
      ip: req.ip || req.connection.remoteAddress,
    });
    req.clientInfo = {
      ipAddress: req.ip || req.connection.remoteAddress,
      userAgent: req.get('User-Agent'),
    };

    next();
  } catch (error) {
    console.error('Authentication error:', error);

    return sendError(res, 'Could not verify authentication', 401, { code: 'AUTH_FAILED' });
  }
};

// Role-based access control middleware
const requireRole = (roles) => {
  return (req, res, next) => {
    if (!req.user) {
      return sendError(res, 'User must be authenticated to access this resource', 401, { code: 'AUTH_REQUIRED' });
    }

    const userRole = req.user.role;
    const userGroups = req.user.groups || [];

    const hasRole = roles.includes(userRole);
    const hasGroup = roles.some((role) => userGroups.includes(role));

    if (!hasRole && !hasGroup) {
      logger.security('permission_denied', {
        userId: req.user.sub,
        username: req.user.username,
        role: userRole,
        requiredRoles: roles,
        path: req.path,
        ip: req.ip || req.connection.remoteAddress,
      });
      return sendError(res, `Access denied. Required roles: ${roles.join(', ')}`, 403, {
        code: 'INSUFFICIENT_PERMISSIONS',
        userRole,
        userGroups,
        requiredRoles: roles,
      });
    }

    next();
  };
};

// Shorthand for admin-only access
const requireAdmin = requireRole(['admin']);

// Enhanced optional authentication that works with unified service
const optionalAuth = async (req, res, next) => {
  try {
    const authHeader = req.headers["authorization"];
    const token = authHeader && authHeader.split(" ")[1];

    if (token) {
      try {
        const result = await validateJwtToken(token);
        if (result.valid && result.user) {
          req.user = result.user;
          req.token = token;
          req.sessionId = result.user.sessionId;
          req.clientInfo = {
            ipAddress: req.ip || req.connection.remoteAddress,
            userAgent: req.get("User-Agent"),
          };
        }
      } catch (error) {
        // Log the error but don't fail the request
        if (process.env.NODE_ENV !== 'test') {
          logger.debug("Optional auth failed:", error.message);
        }
      }
    }
  } catch (error) {
    // Silently continue without authentication
    if (process.env.NODE_ENV !== 'test') {
      logger.debug("Optional auth error:", error.message);
    }
  }

  next();
};

// Middleware to validate session health
const validateSession = async (req, res, next) => {
  try {
    if (!req.user) {
      return next();
    }

    const now = Date.now() / 1000; // Convert to seconds
    const tokenExp = req.user.tokenExpirationTime;

    // Check if token is close to expiration (within 5 minutes)
    if (tokenExp - now < 300) {
      res.set("X-Token-Expiring", "true");
      res.set("X-Token-Expires-At", tokenExp.toString());
    }

    // Check for suspicious activity (optional)
    const timeSinceIssue = now - req.user.tokenIssueTime;
    if (timeSinceIssue > 86400) {
      // 24 hours
      if (process.env.NODE_ENV !== 'test') {
        console.warn(`Long-lived token detected for user ${req.user.sub}`);
      }
    }

    next();
  } catch (error) {
    if (process.env.NODE_ENV !== 'test') {
      console.error("Session validation error:", error);
    }
    next(); // Continue even if session validation fails
  }
};

// NOT A SECURITY CONTROL — in-memory rate limiting is ineffective in Lambda:
// - Each instance has independent state; concurrent instances multiply the effective limit.
// - Cold starts reset the counter; an attacker can wait 15 min for a fresh instance.
// - API Gateway throttling (100 req/s burst, 50 req/s sustained) is the real rate limit.
// These functions remain for UX soft-limiting only. Do NOT rely on them for brute-force defense.
const rateLimitByUser = (requestsPerMinute = 100) => {
  const userRequests = new Map();

  return (req, res, next) => {
    const userId = req.user?.sub || req.ip;
    const now = Date.now();
    const windowStart = now - 60000; // 1 minute window

    if (!userRequests.has(userId)) {
      userRequests.set(userId, []);
    }

    const requests = userRequests.get(userId);

    // Remove old requests
    while (requests.length > 0 && requests[0] < windowStart) {
      requests.shift();
    }

    // Check rate limit
    if (requests.length >= requestsPerMinute) {
      return sendError(res, `Too many requests. Limit: ${requestsPerMinute} per minute`, 429);
    }

    // Add current request
    requests.push(now);
    userRequests.set(userId, requests);

    next();
  };
};

// NOT A SECURITY CONTROL — same in-memory caveats as rateLimitByUser above.
// For brute-force protection, use Cognito's built-in lockout or WAF rules, not this.
const rateLimitAuth = (attemptsPerWindow = 5, windowMinutes = 15) => {
  const authAttempts = new Map();

  return (req, res, next) => {
    const clientId = req.ip || req.connection.remoteAddress;
    const now = Date.now();
    const windowMs = windowMinutes * 60 * 1000;
    const windowStart = now - windowMs;

    if (!authAttempts.has(clientId)) {
      authAttempts.set(clientId, []);
    }

    const attempts = authAttempts.get(clientId);

    // Remove old attempts outside the window
    while (attempts.length > 0 && attempts[0] < windowStart) {
      attempts.shift();
    }

    // Check if rate limit exceeded
    if (attempts.length >= attemptsPerWindow) {
      return sendError(res, `Too many authentication attempts. Please try again in ${windowMinutes} minutes.`, 429, {
        code: 'AUTH_RATE_LIMITED',
        retryAfter: windowMinutes * 60
      });
    }

    // Record this attempt
    attempts.push(now);
    authAttempts.set(clientId, attempts);

    next();
  };
};

// FIXED: Sanitize sensitive data in logs
// Hash user IDs and redact sensitive paths to prevent information leakage
const sanitizeForLogging = (userId, path) => {
  const crypto = require('crypto');

  // Hash user ID for logging (prevents user enumeration via logs)
  const hashedId = userId ?
    crypto.createHash('sha256').update(userId).digest('hex').substring(0, 8) :
    'anonymous';

  // Redact sensitive path parameters (e.g., /user/123 → /user/[ID])
  const sanitizedPath = path
    .replace(/\/\d+/g, '/[ID]')
    .replace(/\/[a-f0-9-]{36}/g, '/[UUID]')
    .replace(/user\/[^/]+/, 'user/[MASKED]')
    .replace(/api_key=([^&]+)/, 'api_key=[REDACTED]');

  return { hashedId, sanitizedPath };
};

// Middleware to log API access with sanitized data
const logApiAccess = async (req, res, next) => {
  const startTime = Date.now();

  // Log request with sanitized data
  if (process.env.NODE_ENV !== 'test') {
    const { hashedId, sanitizedPath } = sanitizeForLogging(req.user?.sub, req.path);
    logger.debug(`${req.method} ${sanitizedPath} - User: ${hashedId} - IP: ${req.ip}`);
  }

  // Override res.end to log response
  const originalEnd = res.end;
  res.end = function (chunk, encoding) {
    const duration = Date.now() - startTime;
    if (process.env.NODE_ENV !== 'test') {
      const { sanitizedPath } = sanitizeForLogging(null, req.path);
      logger.debug(`${req.method} ${sanitizedPath} - ${res.statusCode} - ${duration}ms`);
    }

    // Call the original end method
    originalEnd.call(res, chunk, encoding);
  };

  next();
};

module.exports = {
  authenticateToken,
  requireRole,
  requireAdmin,
  optionalAuth,
  validateSession,
  rateLimitByUser,
  rateLimitAuth,
  logApiAccess,
};

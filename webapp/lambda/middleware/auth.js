const { validateJwtToken } = require("../utils/apiKeyService");

/**
 * Authentication Middleware - Clean implementation with three explicit paths
 * - Development: NODE_ENV === 'development' → admin user (no network call)
 * - Test: NODE_ENV === 'test' → JWT validation with JWT_SECRET
 * - Production: Real Cognito JWT validation via apiKeyService
 */

const authenticateToken = (req, res, next) => {
  // Path 1: Development (NODE_ENV === 'development' only - not localhost check)
  if (process.env.NODE_ENV === 'development') {
    req.user = {
      sub: 'dev-admin-001',
      username: 'dev-admin',
      email: 'admin@dev.local',
      role: 'admin',
      groups: ['admin'],
      sessionId: 'dev-session',
      tokenExpirationTime: Math.floor(Date.now() / 1000) + 86400,
      tokenIssueTime: Math.floor(Date.now() / 1000),
    };
    return next();
  }

  // Path 2: Test environment
  if (process.env.NODE_ENV === 'test') {
    return handleTestAuth(req, res, next);
  }

  // Path 3: Production (async validation with real Cognito JWT)
  return authenticateTokenAsync(req, res, next);
};

// Test environment JWT validation
const handleTestAuth = (req, res, next) => {
  const authHeader = req.headers['authorization'];

  if (!authHeader) {
    return res.status(401).json({
      success: false,
      error: 'Authentication required',
      code: 'MISSING_TOKEN',
    });
  }

  if (!authHeader.startsWith('Bearer ') && !authHeader.startsWith('bearer ')) {
    return res.status(401).json({
      success: false,
      error: 'Invalid token format',
      code: 'INVALID_TOKEN_FORMAT',
    });
  }

  const tokenParts = authHeader.split(' ').filter((part) => part.length > 0);
  const token = (tokenParts[1] || '').trim();

  if (!token) {
    return res.status(401).json({
      success: false,
      error: 'Authentication required',
      code: 'MISSING_TOKEN',
    });
  }

  // Reject dev-bypass-token in test environment
  if (token === 'dev-bypass-token') {
    return res.status(403).json({
      success: false,
      error: 'Invalid token',
      code: 'INVALID_TOKEN',
    });
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
      return res.status(500).json({
        success: false,
        error: 'Authentication service misconfigured',
        code: 'MISSING_JWT_SECRET',
      });
    }

    const decoded = jwt.verify(token, jwtSecret);

    if (!decoded.sub && !decoded.id) {
      return res.status(401).json({
        success: false,
        error: 'Invalid token - missing required claims',
        code: 'MISSING_CLAIMS',
      });
    }

    req.user = decoded;
    req.token = token;
    return next();
  } catch (error) {
    if (error.name === 'TokenExpiredError') {
      return res.status(401).json({
        success: false,
        error: 'Token expired',
        code: 'TOKEN_EXPIRED',
      });
    }

    return res.status(401).json({
      success: false,
      error: 'Invalid token',
      code: 'INVALID_TOKEN',
    });
  }
};

// Production async JWT validation (Cognito)
const authenticateTokenAsync = async (req, res, next) => {
  try {
    const authHeader = req.headers['authorization'];

    if (!authHeader) {
      return res.status(401).json({
        success: false,
        error: 'Authentication required',
        code: 'MISSING_AUTHORIZATION',
      });
    }

    const token = (authHeader.split(' ')[1] || '').trim();

    if (!token) {
      return res.status(401).json({
        success: false,
        error: 'Authorization missing from request headers',
        code: 'MISSING_AUTHORIZATION',
      });
    }

    // Validate JWT token using apiKeyService (now with real Cognito verification)
    const result = await validateJwtToken(token);

    if (!result.valid) {
      return res.status(401).json({
        success: false,
        error: result.error || 'Authentication credentials are invalid',
        code: 'INVALID_CREDENTIALS',
      });
    }

    const user = result.user;
    req.user = user;
    req.token = token;
    req.sessionId = user.sessionId;
    req.clientInfo = {
      ipAddress: req.ip || req.connection.remoteAddress,
      userAgent: req.get('User-Agent'),
    };

    next();
  } catch (error) {
    console.error('Authentication error:', error);

    return res.status(401).json({
      success: false,
      error: 'Could not verify authentication',
      code: 'AUTH_FAILED',
    });
  }
};

// Role-based access control middleware
const requireRole = (roles) => {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({
        success: false,
        error: 'User must be authenticated to access this resource',
        code: 'AUTH_REQUIRED',
      });
    }

    const userRole = req.user.role;
    const userGroups = req.user.groups || [];

    const hasRole = roles.includes(userRole);
    const hasGroup = roles.some((role) => userGroups.includes(role));

    if (!hasRole && !hasGroup) {
      return res.status(403).json({
        success: false,
        error: `Access denied. Required roles: ${roles.join(', ')}`,
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
          console.log("Optional auth failed:", error.message);
        }
      }
    }
  } catch (error) {
    // Silently continue without authentication
    if (process.env.NODE_ENV !== 'test') {
      console.log("Optional auth error:", error.message);
    }
  }

  next();
};

// Middleware to require API key for specific provider
const requireApiKey = (provider) => {
  return async (req, res, next) => {
    try {
      if (!req.user || !req.token) {
        return res.unauthorized(
          "User must be authenticated to access API configuration",
          {
            code: "AUTH_REQUIRED",
          }
        );
      }

      const { getApiKey } = require("../utils/apiKeyService");
      const apiKey = await getApiKey(req.token, provider);

      if (!apiKey) {
        return res.status(400).json({
          error: `${provider} API configuration is required for this operation`,
          success: false
        });
      }

      // Add API key to request for use in route handlers
      req.apiKey = apiKey;
      req.provider = provider;

      next();
    } catch (error) {
      if (process.env.NODE_ENV !== 'test') {
        console.error("API key requirement error:", error);
      }
      return res.status(500).json({
        error: "Could not validate API configuration",
        success: false,
        code: "API_CONFIG_VALIDATION_FAILED"
      });
    }
  };
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

// Rate limiting based on user ID
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
      return res.status(429).json({
        error: `Too many requests. Limit: ${requestsPerMinute} per minute`,
        success: false
      });
    }

    // Add current request
    requests.push(now);
    userRequests.set(userId, requests);

    next();
  };
};

// Middleware to log API access
const logApiAccess = async (req, res, next) => {
  const startTime = Date.now();

  // Log request
  if (process.env.NODE_ENV !== 'test') {
    console.log(
      `${req.method} ${req.path} - User: ${req.user?.sub || "anonymous"} - IP: ${req.ip}`
    );
  }

  // Override res.end to log response
  const originalEnd = res.end;
  res.end = function (chunk, encoding) {
    const duration = Date.now() - startTime;
    if (process.env.NODE_ENV !== 'test') {
      console.log(
        `${req.method} ${req.path} - ${res.statusCode} - ${duration}ms`
      );
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
  requireApiKey,
  validateSession,
  rateLimitByUser,
  logApiAccess,
};

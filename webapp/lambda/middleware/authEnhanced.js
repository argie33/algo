const { validateJwtToken } = require("../utils/apiKeyService");

/**
 * Enhanced Authentication Middleware with JWT validation and session management
 * Uses the unified API key service for comprehensive authentication
 */

// Enhanced authentication middleware with session management
const authenticateToken = async (req, res, next) => {
  try {
    // Skip authentication in development mode
    if (
      process.env.NODE_ENV === "development" &&
      process.env.SKIP_AUTH === "true"
    ) {
      req.user = {
        sub: "dev-user",
        email: "dev@example.com",
        username: "dev-user",
        role: "admin",
        sessionId: "dev-session",
      };
      return next();
    }

    const authHeader = req.headers["authorization"];
    const token = authHeader && authHeader.split(" ")[1]; // Bearer TOKEN

    if (!token) {
      return res.status(401).json({
        error: "Authentication required",
        message: "Access token is missing from Authorization header",
        code: "MISSING_TOKEN",
      });
    }

    // Validate JWT token using unified service
    const user = await validateJwtToken(token);

    // Add user information and token to request
    req.user = user;
    req.token = token;
    req.sessionId = user.sessionId;

    // Add IP address and user agent for audit logging
    req.clientInfo = {
      ipAddress: req.ip || req.connection.remoteAddress,
      userAgent: req.get("User-Agent"),
    };

    next();
  } catch (error) {
    console.error("Authentication error:", error);

    // Handle specific error types
    if (error.message.includes("circuit breaker")) {
      return res.status(503).json({
        error: "Service temporarily unavailable",
        message:
          "Authentication service is experiencing issues. Please try again shortly.",
        code: "AUTH_SERVICE_UNAVAILABLE",
      });
    }

    if (
      error.name === "TokenExpiredError" ||
      error.message.includes("expired")
    ) {
      return res.status(401).json({
        error: "Token expired",
        message: "Your session has expired. Please log in again.",
        code: "TOKEN_EXPIRED",
      });
    }

    if (
      error.name === "JsonWebTokenError" ||
      error.message.includes("invalid")
    ) {
      return res.status(401).json({
        error: "Invalid token",
        message: "The provided token is invalid.",
        code: "INVALID_TOKEN",
      });
    }

    // Generic authentication failure
    return res.status(401).json({
      error: "Authentication failed",
      message: "Could not verify authentication token",
      code: "AUTH_FAILED",
    });
  }
};

// Enhanced authorization middleware with detailed role checking
const requireRole = (roles) => {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({
        error: "Authentication required",
        message: "User must be authenticated to access this resource",
        code: "AUTH_REQUIRED",
      });
    }

    const userRole = req.user.role;
    const userGroups = req.user.groups || [];

    // Check if user has required role or is in required group
    const hasRole = roles.includes(userRole);
    const hasGroup = roles.some((role) => userGroups.includes(role));

    if (!hasRole && !hasGroup) {
      return res.status(403).json({
        error: "Insufficient permissions",
        message: `Access denied. Required roles: ${roles.join(", ")}`,
        code: "INSUFFICIENT_PERMISSIONS",
        userRole: userRole,
        userGroups: userGroups,
        requiredRoles: roles,
      });
    }

    next();
  };
};

// Enhanced optional authentication that works with unified service
const optionalAuth = async (req, res, next) => {
  try {
    const authHeader = req.headers["authorization"];
    const token = authHeader && authHeader.split(" ")[1];

    if (token) {
      try {
        const user = await validateJwtToken(token);
        req.user = user;
        req.token = token;
        req.sessionId = user.sessionId;
        req.clientInfo = {
          ipAddress: req.ip || req.connection.remoteAddress,
          userAgent: req.get("User-Agent"),
        };
      } catch (error) {
        // Log the error but don't fail the request
        console.log("Optional auth failed:", error.message);
      }
    }
  } catch (error) {
    // Silently continue without authentication
    console.log("Optional auth error:", error.message);
  }

  next();
};

// Middleware to require API key for specific provider
const requireApiKey = (provider) => {
  return async (req, res, next) => {
    try {
      if (!req.user || !req.token) {
        return res.status(401).json({
          error: "Authentication required",
          message: "User must be authenticated to access API keys",
          code: "AUTH_REQUIRED",
        });
      }

      const { getApiKey } = require("../utils/apiKeyService");
      const apiKey = await getApiKey(req.token, provider);

      if (!apiKey) {
        return res.status(400).json({
          error: "API key required",
          message: `${provider} API key is required for this operation`,
          code: "API_KEY_REQUIRED",
          provider: provider,
        });
      }

      // Add API key to request for use in route handlers
      req.apiKey = apiKey;
      req.provider = provider;

      next();
    } catch (error) {
      console.error("API key requirement error:", error);
      return res.status(500).json({
        error: "API key validation failed",
        message: "Could not validate API key configuration",
        code: "API_KEY_VALIDATION_FAILED",
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
      console.warn(`Long-lived token detected for user ${req.user.sub}`);
    }

    next();
  } catch (error) {
    console.error("Session validation error:", error);
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
        error: "Rate limit exceeded",
        message: `Too many requests. Limit: ${requestsPerMinute} per minute`,
        code: "RATE_LIMIT_EXCEEDED",
        retryAfter: Math.ceil((requests[0] - windowStart) / 1000),
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
  console.log(
    `${req.method} ${req.path} - User: ${req.user?.sub || "anonymous"} - IP: ${req.ip}`
  );

  // Override res.end to log response
  const originalEnd = res.end;
  res.end = function (chunk, encoding) {
    const duration = Date.now() - startTime;
    console.log(
      `${req.method} ${req.path} - ${res.statusCode} - ${duration}ms`
    );

    // Call the original end method
    originalEnd.call(res, chunk, encoding);
  };

  next();
};

module.exports = {
  authenticateToken,
  requireRole,
  optionalAuth,
  requireApiKey,
  validateSession,
  rateLimitByUser,
  logApiAccess,
};

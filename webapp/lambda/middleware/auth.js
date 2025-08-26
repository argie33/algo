const { validateJwtToken } = require("../utils/apiKeyService");

/**
 * Enhanced Authentication Middleware with JWT validation and session management
 * Uses the unified API key service for comprehensive authentication
 * Consolidated from auth.js and authEnhanced.js for unified authentication system
 */

// Enhanced authentication middleware with session management
const authenticateToken = async (req, res, next) => {
  try {
    // Skip authentication only when explicitly enabled (not in tests)
    if (
      process.env.NODE_ENV === "development" &&
      process.env.SKIP_AUTH === "true" &&
      process.env.NODE_ENV !== "test"
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
      return res.unauthorized("Access token is missing from Authorization header", {
        code: "MISSING_TOKEN",
        suggestion: "Include a valid JWT token in the Authorization header",
        requirements: "Authorization header must be present with format: Bearer <jwt-token>",
        steps: [
          "1. Log in to the application to obtain a valid JWT token",
          "2. Include the token in the Authorization header: 'Bearer your-jwt-token'",
          "3. Ensure your session hasn't expired - tokens are valid for a limited time",
          "4. Check that you're using the correct API endpoint"
        ]
      });
    }

    // Validate JWT token using unified service
    const result = await validateJwtToken(token);

    // Check if token validation failed
    if (!result.valid) {
      // Handle specific token error types
      if (result.error && result.error.includes("expired")) {
        return res.unauthorized("Your session has expired. Please log in again.", {
          code: "TOKEN_EXPIRED",
          suggestion: "Your authentication token has expired and needs to be renewed",
          requirements: "Active session with unexpired JWT token",
          steps: [
            "1. Log out of the application completely",
            "2. Log back in with your credentials",
            "3. Try your request again with the new token",
            "4. Consider enabling 'Keep me logged in' if available"
          ]
        });
      }
      
      return res.unauthorized(result.error || "Authentication token is invalid", {
        code: "INVALID_TOKEN",
        suggestion: "The provided authentication token could not be validated",
        requirements: "Valid, properly formatted JWT token from successful login",
        steps: [
          "1. Verify you're using the most recent token from login",
          "2. Check that the token hasn't been corrupted during transmission",
          "3. Log out and log back in to get a fresh token",
          "4. Ensure you're accessing the correct API environment"
        ]
      });
    }

    const user = result.user;

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
      return res.error("Authentication service is experiencing issues. Please try again shortly.", 500, {
        type: "service_unavailable",
        code: "AUTH_SERVICE_UNAVAILABLE",
        service: "financial-platform-auth-circuit-breaker",
        troubleshooting: {
          suggestion: "The authentication service is temporarily unavailable due to high load or errors",
          requirements: "Authentication service must be operational and responsive",
          steps: [
            "1. Wait 30-60 seconds for the service to recover automatically",
            "2. Try logging in again after the brief wait",
            "3. Check system status page if available",
            "4. Contact technical support if issues persist beyond 5 minutes"
          ]
        }
      });
    }

    if (
      error.name === "TokenExpiredError" ||
      error.message.includes("expired")
    ) {
      return res.unauthorized("Your session has expired. Please log in again.", {
        code: "TOKEN_EXPIRED",
        suggestion: "Your authentication token has expired and needs to be renewed",
        requirements: "Active session with unexpired JWT token",
        steps: [
          "1. Log out of the application completely",
          "2. Log back in with your credentials",
          "3. Try your request again with the new token",
          "4. Consider enabling 'Keep me logged in' if available"
        ]
      });
    }

    if (
      error.name === "JsonWebTokenError" ||
      error.message.includes("invalid")
    ) {
      return res.unauthorized("The provided token is invalid.", {
        code: "INVALID_TOKEN",
        suggestion: "The authentication token format is incorrect or corrupted",
        requirements: "Valid, properly formatted JWT token from successful login",
        steps: [
          "1. Verify the token was copied correctly if manually entered",
          "2. Check that you're using the most recent token from login",
          "3. Log out and log back in to get a fresh token",
          "4. Clear browser cache if the issue persists"
        ]
      });
    }

    // Generic authentication failure
    return res.unauthorized("Could not verify authentication token", {
      code: "AUTH_FAILED",
      suggestion: "Authentication verification failed due to an unexpected error",
      requirements: "Valid authentication token and operational auth service",
      steps: [
        "1. Try logging out and back in to refresh your authentication",
        "2. Check your network connection and try again",
        "3. Clear browser cache and cookies for this site",
        "4. Contact technical support if the error continues"
      ]
    });
  }
};

// Enhanced authorization middleware with detailed role checking
const requireRole = (roles) => {
  return (req, res, next) => {
    if (!req.user) {
      return res.unauthorized("User must be authenticated to access this resource", {
        code: "AUTH_REQUIRED",
      });
    }

    const userRole = req.user.role;
    const userGroups = req.user.groups || [];

    // Check if user has required role or is in required group
    const hasRole = roles.includes(userRole);
    const hasGroup = roles.some((role) => userGroups.includes(role));

    if (!hasRole && !hasGroup) {
      return res.forbidden(`Access denied. Required roles: ${roles.join(", ")}`, {
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
        return res.unauthorized("User must be authenticated to access API keys", {
          code: "AUTH_REQUIRED",
        });
      }

      const { getApiKey } = require("../utils/apiKeyService");
      const apiKey = await getApiKey(req.token, provider);

      if (!apiKey) {
        return res.error(`${provider} API key is required for this operation`, 400, {
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
      return res.error("Could not validate API key configuration", 500, {
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
      return res.error(`Too many requests. Limit: ${requestsPerMinute} per minute`, 429, {
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

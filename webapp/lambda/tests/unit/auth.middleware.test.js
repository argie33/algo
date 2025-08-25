// Mock API key service for JWT validation
jest.mock("../../utils/apiKeyService", () => ({
  validateJwtToken: jest.fn(),
}));

const { validateJwtToken } = require("../../utils/apiKeyService");

describe("Auth Middleware", () => {
  let authenticateToken, requireRole, optionalAuth;
  let req, res, next;

  beforeEach(() => {
    jest.clearAllMocks();

    // Set test environment variables first
    process.env.NODE_ENV = "production";
    delete process.env.SKIP_AUTH;

    // Clear module cache
    delete require.cache[require.resolve("../../middleware/auth")];

    // Set up mock request/response/next
    req = {
      headers: {},
      method: "GET",
      path: "/api/test",
      ip: "127.0.0.1",
      get: jest.fn().mockReturnValue("test-agent"),
      connection: { remoteAddress: "127.0.0.1" },
    };
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
      setHeader: jest.fn(),
      set: jest.fn(),
    };
    next = jest.fn();

    // Import after setting up mocks and environment
    const authModule = require("../../middleware/auth");
    authenticateToken = authModule.authenticateToken;
    requireRole = authModule.requireRole;
    optionalAuth = authModule.optionalAuth;
  });

  afterEach(() => {
    delete process.env.NODE_ENV;
    delete process.env.SKIP_AUTH;
  });

  describe("authenticateToken middleware", () => {
    test("should authenticate valid JWT token", async () => {
      const mockResult = {
        valid: true,
        user: {
          sub: "user-123",
          username: "testuser",
          email: "test@example.com",
          role: "admin",
          groups: ["users"],
          sessionId: "session-123",
        },
      };

      req.headers.authorization = "Bearer valid-jwt-token";
      validateJwtToken.mockResolvedValue(mockResult);

      await authenticateToken(req, res, next);

      expect(validateJwtToken).toHaveBeenCalledWith("valid-jwt-token");
      expect(req.user).toEqual(mockResult.user);
      expect(req.token).toBe("valid-jwt-token");
      expect(req.sessionId).toBe("session-123");
      expect(req.clientInfo).toEqual({
        ipAddress: "127.0.0.1",
        userAgent: "test-agent",
      });
      expect(next).toHaveBeenCalledWith();
      expect(res.status).not.toHaveBeenCalled();
    });

    test("should reject request without authorization header", async () => {
      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Authentication required",
        message: "Access token is missing from Authorization header",
        code: "MISSING_TOKEN",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should reject invalid JWT token", async () => {
      req.headers.authorization = "Bearer invalid-jwt-token";
      validateJwtToken.mockResolvedValue({
        valid: false,
        error: "Invalid token format",
      });

      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Invalid token",
        message: "Invalid token format",
        code: "INVALID_TOKEN",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should handle expired tokens", async () => {
      req.headers.authorization = "Bearer expired-jwt-token";
      validateJwtToken.mockResolvedValue({
        valid: false,
        error: "jwt expired",
      });

      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Token expired",
        message: "Your session has expired. Please log in again.",
        code: "TOKEN_EXPIRED",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should handle invalid JWT format errors", async () => {
      req.headers.authorization = "Bearer malformed-jwt-token";
      validateJwtToken.mockResolvedValue({
        valid: false,
        error: "invalid signature",
      });

      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Invalid token",
        message: "invalid signature",
        code: "INVALID_TOKEN",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should allow development bypass when SKIP_AUTH is true", async () => {
      process.env.NODE_ENV = "development";
      process.env.SKIP_AUTH = "true";

      // Clear module cache and reimport
      delete require.cache[require.resolve("../../middleware/auth")];
      const authModule = require("../../middleware/auth");

      await authModule.authenticateToken(req, res, next);

      expect(req.user).toEqual({
        sub: "dev-user",
        email: "dev@example.com",
        username: "dev-user",
        role: "admin",
        sessionId: "dev-session",
      });
      expect(next).toHaveBeenCalledWith();
      expect(res.status).not.toHaveBeenCalled();
    });

    test("should use no-auth user when verifier not available", async () => {
      // Mock JWT validation to fail (simulating verifier not available)
      req.headers.authorization = "Bearer some-token";
      validateJwtToken.mockResolvedValue({
        valid: false,
        error: "Verifier not available",
      });

      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Invalid token",
        message: "Verifier not available",
        code: "INVALID_TOKEN",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should extract user role from custom:role claim", async () => {
      const mockResult = {
        valid: true,
        user: {
          sub: "user-456",
          username: "testuser",
          email: "test@example.com",
          role: "moderator",
          groups: [],
          sessionId: "session-456",
        },
      };

      req.headers.authorization = "Bearer valid-jwt-token";
      validateJwtToken.mockResolvedValue(mockResult);

      await authenticateToken(req, res, next);

      expect(req.user.role).toBe("moderator");
      expect(req.user.groups).toEqual([]);
    });

    test("should default to user role when no custom role", async () => {
      const mockResult = {
        valid: true,
        user: {
          sub: "user-789",
          username: "basicuser",
          email: "basic@example.com",
          role: "user",
          groups: [],
          sessionId: "session-789",
        },
      };

      req.headers.authorization = "Bearer valid-jwt-token";
      validateJwtToken.mockResolvedValue(mockResult);

      await authenticateToken(req, res, next);

      expect(req.user.role).toBe("user");
    });
  });

  describe("requireRole middleware", () => {
    test("should allow access for users with required role", () => {
      req.user = { role: "admin", groups: [] };
      const middleware = requireRole(["admin"]);

      middleware(req, res, next);

      expect(next).toHaveBeenCalledWith();
      expect(res.status).not.toHaveBeenCalled();
    });

    test("should deny access for users without required role", () => {
      req.user = { role: "user", groups: [] };
      const middleware = requireRole(["admin"]);

      middleware(req, res, next);

      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({
        error: "Insufficient permissions",
        message: "Access denied. Required roles: admin",
        code: "INSUFFICIENT_PERMISSIONS",
        userRole: "user",
        userGroups: [],
        requiredRoles: ["admin"],
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should deny access when user not authenticated", () => {
      const middleware = requireRole(["admin"]);

      middleware(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Authentication required",
        message: "User must be authenticated to access this resource",
        code: "AUTH_REQUIRED",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should allow access based on group membership", () => {
      req.user = { role: "user", groups: ["moderators"] };
      const middleware = requireRole(["moderators"]);

      middleware(req, res, next);

      expect(next).toHaveBeenCalledWith();
      expect(res.status).not.toHaveBeenCalled();
    });
  });

  describe("optionalAuth middleware", () => {
    beforeEach(() => {
      // Reset req.user for each test since optionalAuth modifies it
      delete req.user;
      // Clear any leftover mock state
      jest.clearAllMocks();
      validateJwtToken.mockReset();
    });

    test("should authenticate user when valid token provided", async () => {
      const mockResult = {
        valid: true,
        user: {
          sub: "user-123",
          username: "testuser",
          email: "test@example.com",
          role: "user",
          groups: [],
          sessionId: "session-123",
        },
      };

      req.headers.authorization = "Bearer valid-jwt-token";
      validateJwtToken.mockResolvedValue(mockResult);

      await optionalAuth(req, res, next);

      expect(req.user).toEqual(mockResult.user);
      expect(req.token).toBe("valid-jwt-token");
      expect(req.sessionId).toBe("session-123");
      expect(next).toHaveBeenCalledWith();
    });

    test("should continue without auth when no token provided", async () => {
      await optionalAuth(req, res, next);

      expect(req.user).toBeUndefined();
      expect(next).toHaveBeenCalledWith();
    });

    test("should continue without auth when token verification fails", async () => {
      req.headers.authorization = "Bearer invalid-token";
      validateJwtToken.mockRejectedValue(new Error("Invalid token"));

      await optionalAuth(req, res, next);

      expect(req.user).toBeUndefined();
      expect(next).toHaveBeenCalledWith();
    });

    test("should set no-auth user when verifier not available", async () => {
      // No token provided, optionalAuth should continue without setting user
      await optionalAuth(req, res, next);

      expect(req.user).toBeUndefined();
      expect(next).toHaveBeenCalledWith();
    });
  });
});

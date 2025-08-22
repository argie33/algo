// Mock aws-jwt-verify
jest.mock("aws-jwt-verify", () => ({
  CognitoJwtVerifier: {
    create: jest.fn(),
  },
}));

const { CognitoJwtVerifier } = require("aws-jwt-verify");

describe("Auth Middleware", () => {
  let authenticateToken, requireRole, optionalAuth;
  let mockVerifier;
  let req, res, next;

  beforeEach(() => {
    jest.clearAllMocks();

    // Set test environment variables first
    process.env.COGNITO_USER_POOL_ID = "test-user-pool";
    process.env.COGNITO_CLIENT_ID = "test-client-id";
    process.env.NODE_ENV = "production";
    delete process.env.SKIP_AUTH;

    // Clear module cache
    delete require.cache[require.resolve("../../middleware/auth")];

    // Mock JWT verifier with fresh mock for each test
    mockVerifier = {
      verify: jest.fn(),
    };
    CognitoJwtVerifier.create.mockClear();
    CognitoJwtVerifier.create.mockReturnValue(mockVerifier);

    // Set up mock request/response/next
    req = {
      headers: {},
      method: "GET",
      path: "/api/test",
    };
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
      setHeader: jest.fn(),
    };
    next = jest.fn();

    // Import after setting up mocks and environment
    const authModule = require("../../middleware/auth");
    authenticateToken = authModule.authenticateToken;
    requireRole = authModule.requireRole;
    optionalAuth = authModule.optionalAuth;
  });

  afterEach(() => {
    delete process.env.COGNITO_USER_POOL_ID;
    delete process.env.COGNITO_CLIENT_ID;
    delete process.env.NODE_ENV;
    delete process.env.SKIP_AUTH;
  });

  describe("authenticateToken middleware", () => {
    test("should authenticate valid JWT token", async () => {
      const mockPayload = {
        sub: "user-123",
        username: "testuser",
        email: "test@example.com",
        "custom:role": "admin",
        "cognito:groups": ["users"],
      };

      req.headers.authorization = "Bearer valid-jwt-token";
      mockVerifier.verify.mockResolvedValue(mockPayload);

      await authenticateToken(req, res, next);

      expect(mockVerifier.verify).toHaveBeenCalledWith("valid-jwt-token");
      expect(req.user).toEqual({
        sub: "user-123",
        username: "testuser",
        email: "test@example.com",
        role: "admin",
        groups: ["users"],
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
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should reject invalid JWT token", async () => {
      req.headers.authorization = "Bearer invalid-jwt-token";
      mockVerifier.verify.mockRejectedValue(new Error("Invalid token"));

      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Authentication failed",
        message: "Could not verify authentication token",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should handle expired tokens", async () => {
      req.headers.authorization = "Bearer expired-jwt-token";
      const expiredError = new Error("Token expired");
      expiredError.name = "TokenExpiredError";
      mockVerifier.verify.mockRejectedValue(expiredError);

      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Token expired",
        message: "Your session has expired. Please log in again.",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should handle invalid JWT format errors", async () => {
      req.headers.authorization = "Bearer malformed-jwt-token";
      const jwtError = new Error("Invalid JWT format");
      jwtError.name = "JsonWebTokenError";
      mockVerifier.verify.mockRejectedValue(jwtError);

      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Invalid token",
        message: "The provided token is invalid.",
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
      });
      expect(next).toHaveBeenCalledWith();
      expect(res.status).not.toHaveBeenCalled();
    });

    test("should use no-auth user when verifier not available", async () => {
      // Clear environment to disable verifier
      delete process.env.COGNITO_USER_POOL_ID;
      delete process.env.COGNITO_CLIENT_ID;

      // Clear module cache and reimport
      delete require.cache[require.resolve("../../middleware/auth")];
      const authModule = require("../../middleware/auth");

      await authModule.authenticateToken(req, res, next);

      expect(req.user).toEqual({
        sub: "no-auth-user",
        email: "no-auth@example.com",
        username: "no-auth-user",
        role: "user",
      });
      expect(next).toHaveBeenCalledWith();
      expect(res.status).not.toHaveBeenCalled();
    });

    test("should extract user role from custom:role claim", async () => {
      const mockPayload = {
        sub: "user-456",
        username: "testuser",
        email: "test@example.com",
        "custom:role": "moderator",
      };

      req.headers.authorization = "Bearer valid-jwt-token";
      mockVerifier.verify.mockResolvedValue(mockPayload);

      await authenticateToken(req, res, next);

      expect(req.user.role).toBe("moderator");
      expect(req.user.groups).toEqual([]);
    });

    test("should default to user role when no custom role", async () => {
      const mockPayload = {
        sub: "user-789",
        username: "basicuser",
        email: "basic@example.com",
      };

      req.headers.authorization = "Bearer valid-jwt-token";
      mockVerifier.verify.mockResolvedValue(mockPayload);

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
      mockVerifier.verify.mockReset();
    });

    test("should authenticate user when valid token provided", async () => {
      const mockPayload = {
        sub: "user-123",
        username: "testuser",
        email: "test@example.com",
      };

      req.headers.authorization = "Bearer valid-jwt-token";
      mockVerifier.verify.mockResolvedValue(mockPayload);

      await optionalAuth(req, res, next);

      expect(req.user).toEqual({
        sub: "user-123",
        username: "testuser",
        email: "test@example.com",
        role: "user",
        groups: [],
      });
      expect(next).toHaveBeenCalledWith();
    });

    test("should continue without auth when no token provided", async () => {
      await optionalAuth(req, res, next);

      expect(req.user).toBeUndefined();
      expect(next).toHaveBeenCalledWith();
    });

    test("should continue without auth when token verification fails", async () => {
      req.headers.authorization = "Bearer invalid-token";
      mockVerifier.verify.mockRejectedValue(new Error("Invalid token"));

      await optionalAuth(req, res, next);

      expect(req.user).toBeUndefined();
      expect(next).toHaveBeenCalledWith();
    });

    test("should set no-auth user when verifier not available", async () => {
      // Clear environment to disable verifier
      delete process.env.COGNITO_USER_POOL_ID;
      delete process.env.COGNITO_CLIENT_ID;

      // Clear module cache and reimport
      delete require.cache[require.resolve("../../middleware/auth")];
      const authModule = require("../../middleware/auth");

      await authModule.optionalAuth(req, res, next);

      expect(req.user).toEqual({
        sub: "no-auth-user",
        email: "no-auth@example.com",
        username: "no-auth-user",
        role: "user",
        groups: [],
      });
      expect(next).toHaveBeenCalledWith();
    });
  });
});

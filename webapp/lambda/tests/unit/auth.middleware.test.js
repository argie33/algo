// Jest globals are automatically available

// Mock aws-jwt-verify
jest.mock("aws-jwt-verify", () => ({
  CognitoJwtVerifier: {
    create: jest.fn(),
  },
}));

const { CognitoJwtVerifier } = require("aws-jwt-verify");

describe("Auth Middleware", () => {
  let authenticateToken;
  let mockVerifier;
  let req, res, next;

  beforeEach(() => {
    jest.clearAllMocks();

    // Clear module cache
    delete require.cache[require.resolve("../../middleware/auth")];

    // Mock JWT verifier
    mockVerifier = {
      verify: jest.fn(),
    };
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

    // Set test environment variables
    process.env.COGNITO_USER_POOL_ID = "test-user-pool";
    process.env.COGNITO_CLIENT_ID = "test-client-id";
    process.env.NODE_ENV = "production";

    // Import after setting up mocks
    const authModule = require("../../middleware/auth");
    authenticateToken = authModule.authenticateToken;
  });

  afterEach(() => {
    delete process.env.COGNITO_USER_POOL_ID;
    delete process.env.COGNITO_CLIENT_ID;
    delete process.env.NODE_ENV;
    delete process.env.ALLOW_DEV_BYPASS;
  });

  describe("authenticateToken middleware", () => {
    test("should authenticate valid JWT token", async () => {
      const mockPayload = {
        sub: "user-123",
        username: "testuser",
        token_use: "access",
      };

      req.headers.authorization = "Bearer valid-jwt-token";
      mockVerifier.verify.mockResolvedValue(mockPayload);

      await authenticateToken(req, res, next);

      expect(mockVerifier.verify).toHaveBeenCalledWith("valid-jwt-token");
      expect(req.user).toEqual(mockPayload);
      expect(next).toHaveBeenCalledWith();
      expect(res.status).not.toHaveBeenCalled();
    });

    test("should reject request without authorization header", async () => {
      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Access denied",
        message: "Authorization header is required",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should reject request with malformed authorization header", async () => {
      req.headers.authorization = "InvalidFormat token";

      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Access denied",
        message:
          "Invalid authorization header format. Expected: Bearer <token>",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should reject invalid JWT token", async () => {
      req.headers.authorization = "Bearer invalid-jwt-token";
      mockVerifier.verify.mockRejectedValue(new Error("Invalid token"));

      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Access denied",
        message: "Invalid or expired token",
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
        error: "Access denied",
        message: "Invalid or expired token",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should allow development bypass when environment variables not set", async () => {
      delete process.env.COGNITO_USER_POOL_ID;
      delete process.env.COGNITO_CLIENT_ID;
      process.env.NODE_ENV = "development";

      // Clear module cache and reimport
      delete require.cache[require.resolve("../../middleware/auth")];
      const authModule = require("../../middleware/auth");

      await authModule.authenticateToken(req, res, next);

      expect(req.user).toEqual({
        sub: "dev-user",
        username: "development-user",
      });
      expect(next).toHaveBeenCalledWith();
      expect(res.status).not.toHaveBeenCalled();
    });

    test("should allow explicit development bypass", async () => {
      process.env.ALLOW_DEV_BYPASS = "true";

      // Clear module cache and reimport
      delete require.cache[require.resolve("../../middleware/auth")];
      const authModule = require("../../middleware/auth");

      await authModule.authenticateToken(req, res, next);

      expect(req.user).toEqual({
        sub: "dev-user",
        username: "development-user",
      });
      expect(next).toHaveBeenCalledWith();
      expect(res.status).not.toHaveBeenCalled();
    });

    test("should handle verifier creation failure", async () => {
      // Clear environment to force verifier creation failure
      delete process.env.COGNITO_USER_POOL_ID;
      delete process.env.COGNITO_CLIENT_ID;
      process.env.NODE_ENV = "production";

      // Clear module cache and reimport
      delete require.cache[require.resolve("../../middleware/auth")];
      const authModule = require("../../middleware/auth");

      await authModule.authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(503);
      expect(res.json).toHaveBeenCalledWith({
        error: "Service unavailable",
        message: "Authentication service is not properly configured",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should handle JWT verification timeout", async () => {
      req.headers.authorization = "Bearer valid-jwt-token";
      mockVerifier.verify.mockImplementation(
        () =>
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error("Timeout")), 100)
          )
      );

      await authenticateToken(req, res, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Access denied",
        message: "Invalid or expired token",
      });
      expect(next).not.toHaveBeenCalled();
    });

    test("should set CORS headers in response", async () => {
      req.headers.authorization = "Bearer valid-jwt-token";
      req.headers.origin = "https://example.com";

      const mockPayload = {
        sub: "user-123",
        username: "testuser",
      };

      mockVerifier.verify.mockResolvedValue(mockPayload);

      await authenticateToken(req, res, next);

      expect(next).toHaveBeenCalledWith();
    });

    test("should handle OPTIONS requests without token", async () => {
      req.method = "OPTIONS";

      await authenticateToken(req, res, next);

      expect(next).toHaveBeenCalledWith();
      expect(res.status).not.toHaveBeenCalled();
    });

    test("should extract user information from valid token", async () => {
      const mockPayload = {
        sub: "user-123",
        username: "testuser",
        email: "test@example.com",
        token_use: "access",
        client_id: "test-client-id",
      };

      req.headers.authorization = "Bearer valid-jwt-token";
      mockVerifier.verify.mockResolvedValue(mockPayload);

      await authenticateToken(req, res, next);

      expect(req.user).toEqual(mockPayload);
      expect(req.user.sub).toBe("user-123");
      expect(req.user.username).toBe("testuser");
      expect(req.user.email).toBe("test@example.com");
      expect(next).toHaveBeenCalledWith();
    });
  });
});

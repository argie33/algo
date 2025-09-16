/**
 * Auth Routes Unit Tests
 * Tests auth route logic in isolation with mocks
 */

const express = require("express");
const request = require("supertest");

// Mock AWS Cognito client
const mockSend = jest.fn();
jest.mock("@aws-sdk/client-cognito-identity-provider", () => ({
  CognitoIdentityProviderClient: jest.fn(() => ({
    send: mockSend,
  })),
  InitiateAuthCommand: jest.fn(),
  SignUpCommand: jest.fn(),
  ConfirmSignUpCommand: jest.fn(),
  ForgotPasswordCommand: jest.fn(),
  ConfirmForgotPasswordCommand: jest.fn(),
  RespondToAuthChallengeCommand: jest.fn(),
}));

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = {
      sub: "test-user",
      email: "test@example.com",
      username: "testuser",
    };
    next();
  }),
}));

describe("Auth Routes Unit Tests", () => {
  let app;
  let authRouter;

  beforeEach(() => {
    jest.clearAllMocks();

    // Create test app
    app = express();
    app.use(express.json());

    // Add response helper middleware
    app.use((req, res, next) => {
      res.error = (message, status = 500) =>
        res.status(status).json({
          success: false,
          error: message,
        });
      res.success = (data, status = 200) =>
        res.status(status).json({
          success: true,
          ...data,
        });
      res.unauthorized = (message) =>
        res.status(401).json({
          success: false,
          error: message,
        });
      next();
    });

    // Load the route module
    authRouter = require("../../../routes/auth");
    app.use("/auth", authRouter);
  });

  describe("POST /auth/login", () => {
    test("should successfully login with valid credentials", async () => {
      const mockAuthResult = {
        AuthenticationResult: {
          AccessToken: "mock-access-token",
          IdToken: "mock-id-token",
          RefreshToken: "mock-refresh-token",
          ExpiresIn: 3600,
          TokenType: "Bearer",
        },
      };

      mockSend.mockResolvedValueOnce(mockAuthResult);

      const response = await request(app).post("/auth/login").send({
        username: "devuser",
        password: "password123",
      });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("accessToken", "mock-access-token");
      expect(response.body).toHaveProperty("idToken", "mock-id-token");
      expect(response.body).toHaveProperty(
        "refreshToken",
        "mock-refresh-token"
      );
      expect(response.body).toHaveProperty("expiresIn", 3600);
    });

    test("should handle missing credentials", async () => {
      const response = await request(app).post("/auth/login").send({});

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Missing credentials");
      expect(mockSend).not.toHaveBeenCalled();
    });

    test("should handle authentication challenge", async () => {
      const mockChallengeResult = {
        ChallengeName: "NEW_PASSWORD_REQUIRED",
        ChallengeParameters: { userAttributes: "email" },
        Session: "mock-session",
      };

      mockSend.mockResolvedValueOnce(mockChallengeResult);

      const response = await request(app).post("/auth/login").send({
        username: "devuser",
        password: "wrongpassword",
      });

      expect(response.status).toBe(401);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toBe("Invalid credentials");
    });

    test("should handle NotAuthorizedException", async () => {
      const error = new Error("Incorrect username or password.");
      error.name = "NotAuthorizedException";
      mockSend.mockRejectedValueOnce(error);

      const response = await request(app).post("/auth/login").send({
        username: "wronguser",
        password: "wrongpassword",
      });

      expect(response.status).toBe(401);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Invalid credentials");
    });

    test("should handle UserNotConfirmedException", async () => {
      const error = new Error("User is not confirmed.");
      error.name = "UserNotConfirmedException";
      mockSend.mockRejectedValueOnce(error);

      const response = await request(app).post("/auth/login").send({
        username: "unconfirmeduser",
        password: "password",
      });

      expect(response.status).toBe(401);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Invalid credentials");
    });
  });

  describe("POST /auth/register", () => {
    test("should successfully register new user", async () => {
      const mockRegisterResult = {
        UserSub: "mock-user-sub",
        CodeDeliveryDetails: {
          DeliveryMedium: "EMAIL",
          Destination: "test@example.com",
        },
      };

      mockSend.mockResolvedValueOnce(mockRegisterResult);

      const response = await request(app).post("/auth/register").send({
        username: "newuser",
        password: "SecurePassword123!",
        email: "test@example.com",
        firstName: "Test",
        lastName: "User",
      });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty(
        "message",
        "User registered successfully"
      );
      expect(response.body).toHaveProperty("userSub", "mock-user-sub");
      expect(response.body).toHaveProperty("success", true);
    });

    test("should handle missing required fields", async () => {
      const response = await request(app).post("/auth/register").send({
        username: "newuser",
        // Missing password and email
      });

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Missing required fields");
      expect(mockSend).not.toHaveBeenCalled();
    });

    test("should handle UsernameExistsException", async () => {
      const error = new Error(
        "An account with the given email already exists."
      );
      error.name = "UsernameExistsException";
      mockSend.mockRejectedValueOnce(error);

      const response = await request(app).post("/auth/register").send({
        username: "existinguser",
        password: "SecurePassword123!",
        email: "existing@example.com",
      });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty(
        "message",
        "User registered successfully"
      );
    });
  });

  describe("POST /auth/confirm", () => {
    test("should confirm user registration", async () => {
      mockSend.mockResolvedValueOnce({});

      const response = await request(app).post("/auth/confirm").send({
        username: "testuser",
        confirmationCode: "123456",
      });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty(
        "message",
        "Account confirmed successfully"
      );
      expect(response.body).toHaveProperty("success", true);
    });

    test("should handle CodeMismatchException", async () => {
      const error = new Error(
        "Invalid verification code provided, please try again."
      );
      error.name = "CodeMismatchException";
      mockSend.mockRejectedValueOnce(error);

      const response = await request(app).post("/auth/confirm").send({
        username: "testuser",
        confirmationCode: "wrongcode",
      });

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toBe("Invalid code");
    });
  });

  describe("POST /auth/forgot-password", () => {
    test("should initiate password reset", async () => {
      const mockResetResult = {
        CodeDeliveryDetails: {
          DeliveryMedium: "EMAIL",
          Destination: "test@example.com",
        },
      };

      mockSend.mockResolvedValueOnce(mockResetResult);

      const response = await request(app).post("/auth/forgot-password").send({
        username: "testuser",
      });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty(
        "message",
        "Password reset code sent"
      );
      expect(response.body).toHaveProperty("success", true);
    });

    test("should handle missing username", async () => {
      const response = await request(app)
        .post("/auth/forgot-password")
        .send({});

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Missing username");
      expect(mockSend).not.toHaveBeenCalled();
    });
  });

  describe("GET /auth/me", () => {
    test("should return user profile", async () => {
      const response = await request(app).get("/auth/me");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("user");
      expect(response.body.user).toHaveProperty("sub", "test-user");
      expect(response.body.user).toHaveProperty("email", "test@example.com");
    });
  });

  describe("GET /auth/health", () => {
    test("should return auth service health", async () => {
      const response = await request(app).get("/auth/health");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "healthy");
      expect(response.body).toHaveProperty("service", "Authentication Service");
      expect(response.body).toHaveProperty("cognito");
    });
  });

  describe("Development Mode JWT Authentication", () => {
    beforeEach(() => {
      // Mock environment to simulate no Cognito configuration
      delete process.env.COGNITO_CLIENT_ID;
    });

    test("should generate valid JWT tokens in development mode", async () => {
      const jwt = require("jsonwebtoken");

      const response = await request(app).post("/auth/login").send({
        username: "devuser",
        password: "password123",
      });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("accessToken");
      expect(response.body).toHaveProperty("idToken");
      expect(response.body).toHaveProperty("refreshToken");

      // Verify tokens are valid JWTs
      const accessToken = jwt.decode(response.body.accessToken);
      const idToken = jwt.decode(response.body.idToken);
      const refreshToken = jwt.decode(response.body.refreshToken);

      expect(accessToken).toHaveProperty("token_use", "access");
      expect(accessToken).toHaveProperty("username", "devuser");
      expect(accessToken).toHaveProperty(
        "scope",
        "aws.cognito.signin.user.admin"
      );

      expect(idToken).toHaveProperty("token_use", "id");
      expect(idToken).toHaveProperty("username", "devuser");
      expect(idToken).toHaveProperty("iss", "dev-issuer");

      expect(refreshToken).toHaveProperty("token_use", "refresh");
    });

    test("should generate JWT tokens for MFA challenge in development", async () => {
      const jwt = require("jsonwebtoken");

      const response = await request(app)
        .post("/auth/challenge")
        .send({
          challengeName: "SMS_MFA",
          challengeResponses: {
            SMS_MFA_CODE: "123456",
          },
        });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("accessToken");
      expect(response.body).toHaveProperty("idToken");
      expect(response.body).toHaveProperty("refreshToken");

      // Verify MFA-specific claims
      const idToken = jwt.decode(response.body.idToken);
      expect(idToken).toHaveProperty("mfa_verified", true);
      expect(idToken).toHaveProperty("token_use", "id");
    });

    test("should generate JWT tokens for respond-to-challenge in development", async () => {
      const jwt = require("jsonwebtoken");

      const response = await request(app)
        .post("/auth/respond-to-challenge")
        .send({
          challengeName: "SMS_MFA",
          challengeResponses: {
            SMS_MFA_CODE: "123456",
          },
        });

      expect(response.status).toBe(200);
      expect(response.body.tokens).toHaveProperty("accessToken");
      expect(response.body.tokens).toHaveProperty("idToken");
      expect(response.body.tokens).toHaveProperty("refreshToken");

      // Verify challenge-specific claims
      const idToken = jwt.decode(response.body.tokens.idToken);
      expect(idToken).toHaveProperty("challenge_verified", true);
      expect(idToken).toHaveProperty("username", "devuser");

      expect(response.body.user).toHaveProperty("username", "devuser");
      expect(response.body.user).toHaveProperty("email", "dev@example.com");
    });

    test("should use consistent JWT secret across all endpoints", async () => {
      const jwt = require("jsonwebtoken");
      const secret = process.env.JWT_SECRET || "dev-secret-key";

      const loginResponse = await request(app).post("/auth/login").send({
        username: "devuser",
        password: "password123",
      });

      // Verify token can be decoded with the same secret
      const decoded = jwt.verify(loginResponse.body.accessToken, secret);
      expect(decoded).toHaveProperty("username", "devuser");
      expect(decoded).toHaveProperty("token_use", "access");
    });
  });

  describe("Error handling", () => {
    test("should handle generic Cognito errors", async () => {
      const error = new Error("Generic Cognito error");
      mockSend.mockRejectedValueOnce(error);

      const response = await request(app).post("/auth/login").send({
        username: "wronguser",
        password: "wrongpassword",
      });

      expect(response.status).toBe(401);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toBe("Invalid credentials");
    });
  });
});

/**
 * Regression tests for the production JWT revocation path (authenticateTokenAsync).
 *
 * Bug: middleware/auth.js and routes/logout.js both extracted the token's unique
 * identifier via `user.jti || user.token_use` and expiration via `user.exp`, but
 * utils/apiKeyService.js's validateJwtToken() (the real production JWT validator)
 * returns a user object shaped as { sub, username, email, role, groups,
 * sessionId, tokenExpirationTime, tokenIssueTime } - there is no jti/token_use/exp
 * field on it at all. This meant tokenJti was always undefined in production,
 * which meant: (1) logout.js's revokeToken() was never actually called - logout
 * always took the "cannot revoke" branch and reported success anyway, and
 * (2) even if a token had been added to the blocklist by some other path,
 * auth.js's isTokenRevoked(undefined, ...) always short-circuits to false. A
 * "logged out" JWT therefore remained fully valid until natural expiration.
 */
jest.mock("../../../utils/apiKeyService", () => ({
  validateJwtToken: jest.fn(),
}));
jest.mock("../../../utils/tokenBlocklist", () => ({
  isTokenRevoked: jest.fn(),
  revokeToken: jest.fn(),
}));

const { validateJwtToken } = require("../../../utils/apiKeyService");
const { isTokenRevoked, revokeToken } = require("../../../utils/tokenBlocklist");
const { authenticateToken } = require("../../../middleware/auth");

describe("authenticateTokenAsync (production) revocation check", () => {
  const productionUser = {
    sub: "user-abc",
    username: "realuser",
    email: "real@example.com",
    role: "user",
    groups: ["user"],
    sessionId: "real-session-jti-123",
    tokenExpirationTime: Math.floor(Date.now() / 1000) + 3600,
    tokenIssueTime: Math.floor(Date.now() / 1000) - 60,
  };

  let originalNodeEnv;
  let req, res, next;

  beforeEach(() => {
    originalNodeEnv = process.env.NODE_ENV;
    process.env.NODE_ENV = "production";
    jest.clearAllMocks();
    req = {
      headers: { authorization: "Bearer real-jwt-token" },
      ip: "127.0.0.1",
      connection: {},
      get: jest.fn().mockReturnValue("test-agent"),
    };
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
    };
    next = jest.fn();
  });

  afterEach(() => {
    process.env.NODE_ENV = originalNodeEnv;
  });

  test("checks isTokenRevoked using the real sessionId/tokenExpirationTime fields, not jti/exp", async () => {
    validateJwtToken.mockResolvedValue({ valid: true, user: productionUser });
    isTokenRevoked.mockResolvedValue(false);

    await authenticateToken(req, res, next);

    expect(isTokenRevoked).toHaveBeenCalledWith(
      "real-session-jti-123",
      productionUser.tokenExpirationTime
    );
    expect(next).toHaveBeenCalled();
    expect(req.user).toEqual(productionUser);
  });

  test("rejects a revoked production token with 401", async () => {
    validateJwtToken.mockResolvedValue({ valid: true, user: productionUser });
    isTokenRevoked.mockResolvedValue(true);

    await authenticateToken(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(401);
    expect(res.json).toHaveBeenCalledWith(
      expect.objectContaining({
        success: false,
        message: "Token has been revoked. Please log in again.",
      })
    );
  });
});

describe("POST /api/logout revocation call", () => {
  test("revokes using sessionId/tokenExpirationTime for a production-shaped user, not jti/token_use/exp", async () => {
    jest.resetModules();
    jest.doMock("../../../middleware/auth", () => ({
      authenticateToken: (req, _res, next) => next(),
    }));
    jest.doMock("../../../utils/tokenBlocklist", () => ({
      revokeToken: jest.fn().mockResolvedValue(true),
    }));

    const express = require("express");
    const request = require("supertest");
    const logoutRouter = require("../../../routes/logout");
    const { revokeToken: mockedRevokeToken } = require("../../../utils/tokenBlocklist");

    const app = express();
    app.use(express.json());
    app.use((req, _res, next) => {
      req.user = {
        sub: "user-abc",
        sessionId: "real-session-jti-123",
        tokenExpirationTime: Math.floor(Date.now() / 1000) + 3600,
      };
      req.token = "real-jwt-token";
      next();
    });
    app.use("/api/logout", logoutRouter);

    const response = await request(app).post("/api/logout");

    expect(response.status).toBe(200);
    expect(mockedRevokeToken).toHaveBeenCalledWith(
      "real-session-jti-123",
      expect.any(Number)
    );
    expect(response.body.data.revoked).toBe(true);

    jest.dontMock("../../../middleware/auth");
    jest.dontMock("../../../utils/tokenBlocklist");
  });
});

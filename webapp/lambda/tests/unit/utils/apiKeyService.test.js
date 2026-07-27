/**
 * API Key Service Unit Tests
 *
 * utils/apiKeyService.js was rewritten down to a single Cognito JWT validator
 * (validateJwtToken) - the storeApiKey/getApiKey/validateApiKey/deleteApiKey/
 * listProviders/getDecryptedApiKey/cache/circuit-breaker/encryption surface this file
 * used to cover no longer exists (grep confirms zero other exports). Replaced with
 * coverage of what's actually there.
 *
 * Note: apiKeyService.js memoizes its CognitoJwtVerifier in a module-level `verifier`
 * variable, created lazily on first use and reused thereafter - so these tests share one
 * verifier/mockVerify across cases rather than re-mocking per test.
 */
jest.mock("aws-jwt-verify");

const { CognitoJwtVerifier } = require("aws-jwt-verify");

describe("API Key Service - validateJwtToken", () => {
  const mockVerify = jest.fn();
  let validateJwtToken;

  beforeAll(() => {
    process.env.COGNITO_USER_POOL_ID = "test-pool-id";
    process.env.COGNITO_CLIENT_ID = "test-client-id";
    CognitoJwtVerifier.create = jest.fn().mockReturnValue({ verify: mockVerify });
    validateJwtToken = require("../../../utils/apiKeyService").validateJwtToken;
  });

  beforeEach(() => {
    mockVerify.mockReset();
  });

  test("should validate a token and extract user info", async () => {
    mockVerify.mockResolvedValue({
      sub: "user-123",
      "cognito:username": "jdoe",
      email: "jdoe@example.com",
      "cognito:groups": [],
      jti: "session-abc",
      exp: 1234567890,
      iat: 1234560000,
    });

    const result = await validateJwtToken("valid-token");

    expect(result.valid).toBe(true);
    expect(result.user).toEqual({
      sub: "user-123",
      username: "jdoe",
      email: "jdoe@example.com",
      role: "user",
      groups: [],
      sessionId: "session-abc",
      tokenExpirationTime: 1234567890,
      tokenIssueTime: 1234560000,
    });
  });

  test("should map the admin cognito group to role 'admin'", async () => {
    mockVerify.mockResolvedValue({
      sub: "user-456",
      "cognito:groups": ["admin"],
    });

    const result = await validateJwtToken("admin-token");

    expect(result.valid).toBe(true);
    expect(result.user.role).toBe("admin");
    expect(result.user.groups).toEqual(["admin"]);
  });

  test("should fall back to sub for username/email when claims are missing", async () => {
    mockVerify.mockResolvedValue({ sub: "user-789" });

    const result = await validateJwtToken("bare-token");

    expect(result.user.username).toBe("user-789");
    expect(result.user.email).toBeNull();
  });

  test("should return valid:false with the error message when verification fails", async () => {
    mockVerify.mockRejectedValue(new Error("Token expired"));

    const result = await validateJwtToken("expired-token");

    expect(result).toEqual({ valid: false, error: "Token expired" });
  });
});

describe("API Key Service - validateJwtToken without Cognito env vars", () => {
  const originalEnv = { ...process.env };

  afterEach(() => {
    process.env = { ...originalEnv };
  });

  test("should return valid:false with a helpful error", async () => {
    jest.resetModules();
    delete process.env.COGNITO_USER_POOL_ID;
    delete process.env.COGNITO_CLIENT_ID;
    jest.doMock("aws-jwt-verify", () => ({
      CognitoJwtVerifier: { create: jest.fn() },
    }));

    const { validateJwtToken: validateWithoutEnv } = require("../../../utils/apiKeyService");

    const result = await validateWithoutEnv("any-token");

    expect(result.valid).toBe(false);
    expect(result.error).toMatch(/COGNITO_USER_POOL_ID/);
  });
});

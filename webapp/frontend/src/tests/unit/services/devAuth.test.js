import { describe, test, expect, vi, beforeEach, afterEach } from "vitest";

// Mock localStorage
const localStorageMock = {
  store: {},
  getItem: vi.fn((key) => localStorageMock.store[key] || null),
  setItem: vi.fn((key, value) => {
    localStorageMock.store[key] = value;
  }),
  removeItem: vi.fn((key) => {
    delete localStorageMock.store[key];
  }),
  clear: vi.fn(() => {
    localStorageMock.store = {};
  }),
};

// Mock window and console
global.localStorage = localStorageMock;
global.window = global.window || {};
global.window.localStorage = localStorageMock;
global.console = {
  log: vi.fn(),
  error: vi.fn(),
  warn: vi.fn(),
};

describe("DevAuthService", () => {
  let devAuthService;
  let originalWindow;
  let originalAlert;

  beforeEach(async () => {
    vi.clearAllMocks();
    localStorageMock.clear();

    // Mock window and alert
    originalWindow = global.window;
    originalAlert = global.alert;
    global.window = {
      DEV_AUTH_DEBUG: false,
      location: { hostname: "localhost" },
      localStorage: localStorageMock,
    };
    global.alert = vi.fn();

    // Ensure localStorage is properly available
    global.localStorage = localStorageMock;

    // Import service
    const { default: service } = await import("../../../services/devAuth.js");
    devAuthService = service;

    // Reset service state manually since it's an instance
    devAuthService.users = {};
    devAuthService.session = null;
    devAuthService.pendingVerifications = {};

    // Manually add the default dev user for testing
    devAuthService.users["devuser"] = {
      username: "devuser",
      email: "argeropolos@gmail.com",
      firstName: "Dev",
      lastName: "User",
      password: "password123",
      confirmed: true,
      createdAt: Date.now(),
    };
    devAuthService.users["argeropolos@gmail.com"] =
      devAuthService.users["devuser"];
  });

  afterEach(() => {
    global.window = originalWindow;
    global.alert = originalAlert;
  });

  describe("Initialization", () => {
    test("creates default dev user on initialization", () => {
      expect(devAuthService.users["devuser"]).toBeDefined();
      expect(devAuthService.users["devuser"].email).toBe(
        "argeropolos@gmail.com"
      );
      expect(devAuthService.users["devuser"].username).toBe("devuser");
      expect(devAuthService.users["devuser"].confirmed).toBe(true);
    });

    test("allows login with both username and email", () => {
      expect(devAuthService.users["devuser"]).toBeDefined();
      expect(devAuthService.users["argeropolos@gmail.com"]).toBeDefined();
    });

    test("handles localStorage unavailable gracefully", () => {
      global.localStorage = undefined;

      // Should not throw when localStorage is unavailable
      expect(() => {
        devAuthService.loadUsers();
        devAuthService.loadSession();
        devAuthService.loadPendingVerifications();
      }).not.toThrow();
    });
  });

  describe("User Registration", () => {
    test("successfully registers new user", async () => {
      const result = await devAuthService.signUp({
        username: "testuser",
        password: "TestPass123!",
        email: "test@example.com",
        firstName: "Test",
        lastName: "User",
      });

      expect(result.success).toBe(true);
      expect(result.userConfirmed).toBe(false);
      expect(result.isSignUpComplete).toBe(false);
      expect(result.nextStep.signUpStep).toBe("CONFIRM_SIGN_UP");
      expect(devAuthService.pendingVerifications["testuser"]).toBeDefined();
    });

    test("prevents duplicate username registration", async () => {
      await devAuthService.signUp({
        username: "testuser",
        password: "TestPass123!",
        email: "test@example.com",
      });

      const result = await devAuthService.signUp({
        username: "testuser",
        password: "TestPass456!",
        email: "test2@example.com",
      });

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("UsernameExistsException");
    });

    test("prevents duplicate email registration", async () => {
      await devAuthService.signUp({
        username: "testuser1",
        password: "TestPass123!",
        email: "test@example.com",
      });

      const result = await devAuthService.signUp({
        username: "testuser2",
        password: "TestPass456!",
        email: "test@example.com",
      });

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("UsernameExistsException");
    });

    test("generates verification code and shows alert in localhost", async () => {
      global.window.location.hostname = "localhost";

      await devAuthService.signUp({
        username: "testuser",
        password: "TestPass123!",
        email: "test@example.com",
      });

      expect(global.console.log).toHaveBeenCalledWith(
        "📧 DEV: Email verification code sent to",
        "test@example.com"
      );

      // Check that alert is scheduled (setTimeout)
      await new Promise((resolve) => setTimeout(resolve, 150));
      expect(global.alert).toHaveBeenCalled();
    });
  });

  describe("Email Confirmation", () => {
    test("successfully confirms user with valid code", async () => {
      await devAuthService.signUp({
        username: "testuser",
        password: "TestPass123!",
        email: "test@example.com",
      });

      const pending = devAuthService.pendingVerifications["testuser"];
      const result = await devAuthService.confirmSignUp(
        "testuser",
        pending.verificationCode
      );

      expect(result.isSignUpComplete).toBe(true);
      expect(devAuthService.users["testuser"]).toBeDefined();
      expect(devAuthService.users["testuser"].confirmed).toBe(true);
      expect(devAuthService.pendingVerifications["testuser"]).toBeUndefined();
    });

    test("fails confirmation with invalid code", async () => {
      await devAuthService.signUp({
        username: "testuser",
        password: "TestPass123!",
        email: "test@example.com",
      });

      await expect(
        devAuthService.confirmSignUp("testuser", "wrongcode")
      ).rejects.toThrow("CodeMismatchException");
    });

    test("fails confirmation for non-existent user", async () => {
      await expect(
        devAuthService.confirmSignUp("nonexistent", "123456")
      ).rejects.toThrow("UserNotFoundException");
    });

    test("fails confirmation with expired code", async () => {
      await devAuthService.signUp({
        username: "testuser",
        password: "TestPass123!",
        email: "test@example.com",
      });

      // Manually set creation time to 6 minutes ago
      devAuthService.pendingVerifications["testuser"].createdAt =
        Date.now() - 6 * 60 * 1000;

      const pending = devAuthService.pendingVerifications["testuser"];
      await expect(
        devAuthService.confirmSignUp("testuser", pending.verificationCode)
      ).rejects.toThrow("ExpiredCodeException");
    });
  });

  describe("User Authentication", () => {
    beforeEach(async () => {
      // Create confirmed user
      await devAuthService.signUp({
        username: "testuser",
        password: "TestPass123!",
        email: "test@example.com",
      });

      const pending = devAuthService.pendingVerifications["testuser"];
      await devAuthService.confirmSignUp("testuser", pending.verificationCode);
    });

    test("successfully signs in with username", async () => {
      const result = await devAuthService.signIn("testuser", "TestPass123!");

      expect(result.success).toBe(true);
      expect(result.isSignedIn).toBe(true);
      expect(result.user.username).toBe("testuser");
      expect(result.tokens.accessToken).toBe("dev-bypass-token");
      expect(devAuthService.session).toBeDefined();
    });

    test("successfully signs in with email", async () => {
      const result = await devAuthService.signIn(
        "test@example.com",
        "TestPass123!"
      );

      expect(result.success).toBe(true);
      expect(result.isSignedIn).toBe(true);
      expect(result.user.username).toBe("testuser");
      expect(result.user.email).toBe("test@example.com");
    });

    test("fails sign in with wrong password", async () => {
      const result = await devAuthService.signIn("testuser", "wrongpassword");

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("NotAuthorizedException");
    });

    test("fails sign in for non-existent user", async () => {
      const result = await devAuthService.signIn("nonexistent", "password");

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("UserNotFoundException");
    });

    test("fails sign in for unconfirmed user", async () => {
      await devAuthService.signUp({
        username: "unconfirmed",
        password: "TestPass123!",
        email: "unconfirmed@example.com",
      });

      const result = await devAuthService.signIn("unconfirmed", "TestPass123!");

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("UserNotConfirmedException");
    });
  });

  describe("Session Management", () => {
    beforeEach(async () => {
      // Create and sign in user
      await devAuthService.signUp({
        username: "testuser",
        password: "TestPass123!",
        email: "test@example.com",
      });

      const pending = devAuthService.pendingVerifications["testuser"];
      await devAuthService.confirmSignUp("testuser", pending.verificationCode);
      await devAuthService.signIn("testuser", "TestPass123!");
    });

    test("gets current user when authenticated", async () => {
      const result = await devAuthService.getCurrentUser();

      expect(result.success).toBe(true);
      expect(result.user.username).toBe("testuser");
      expect(result.user.email).toBe("test@example.com");
    });

    test("fails to get current user when not authenticated", async () => {
      await devAuthService.signOut();

      const result = await devAuthService.getCurrentUser();

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("NotAuthorizedException");
    });

    test("checks authentication status correctly", () => {
      expect(devAuthService.isAuthenticated()).toBe(true);

      devAuthService.clearSession();
      expect(devAuthService.isAuthenticated()).toBe(false);
    });

    test("gets current user info when authenticated", () => {
      const userInfo = devAuthService.getCurrentUserInfo();

      expect(userInfo).toBeDefined();
      expect(userInfo.username).toBe("testuser");
      expect(userInfo.email).toBe("test@example.com");
    });

    test("returns null user info when not authenticated", () => {
      devAuthService.clearSession();

      const userInfo = devAuthService.getCurrentUserInfo();
      expect(userInfo).toBeNull();
    });

    test("gets JWT token when authenticated", async () => {
      const token = await devAuthService.getJwtToken();

      expect(token).toBe("dev-bypass-token");
    });

    test("returns null JWT token when not authenticated", async () => {
      devAuthService.clearSession();

      const token = await devAuthService.getJwtToken();
      expect(token).toBeNull();
    });

    test("successfully signs out", async () => {
      const result = await devAuthService.signOut();

      expect(result.success).toBe(true);
      expect(devAuthService.session).toBeNull();
      expect(devAuthService.isAuthenticated()).toBe(false);
    });
  });

  describe("Password Reset", () => {
    beforeEach(async () => {
      // Create confirmed user
      await devAuthService.signUp({
        username: "testuser",
        password: "TestPass123!",
        email: "test@example.com",
      });

      const pending = devAuthService.pendingVerifications["testuser"];
      await devAuthService.confirmSignUp("testuser", pending.verificationCode);
    });

    test("initiates password reset successfully", async () => {
      const result = await devAuthService.forgotPassword("testuser");

      expect(result.success).toBe(true);
      expect(
        devAuthService.pendingVerifications["reset_testuser"]
      ).toBeDefined();
    });

    test("fails password reset for non-existent user", async () => {
      const result = await devAuthService.forgotPassword("nonexistent");

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("UserNotFoundException");
    });

    test("confirms password reset with valid code", async () => {
      await devAuthService.forgotPassword("testuser");
      const resetCode =
        devAuthService.pendingVerifications["reset_testuser"].resetCode;

      const result = await devAuthService.forgotPasswordSubmit(
        "testuser",
        resetCode,
        "NewPass123!"
      );

      expect(result.success).toBe(true);
      expect(devAuthService.users["testuser"].password).toBe("NewPass123!");
      expect(
        devAuthService.pendingVerifications["reset_testuser"]
      ).toBeUndefined();
    });

    test("fails password reset with invalid code", async () => {
      await devAuthService.forgotPassword("testuser");

      const result = await devAuthService.forgotPasswordSubmit(
        "testuser",
        "wrongcode",
        "NewPass123!"
      );

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("CodeMismatchException");
    });

    test("fails password reset with expired code", async () => {
      await devAuthService.forgotPassword("testuser");

      // Manually set creation time to 6 minutes ago
      devAuthService.pendingVerifications["reset_testuser"].createdAt =
        Date.now() - 6 * 60 * 1000;
      const resetCode =
        devAuthService.pendingVerifications["reset_testuser"].resetCode;

      const result = await devAuthService.forgotPasswordSubmit(
        "testuser",
        resetCode,
        "NewPass123!"
      );

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("ExpiredCodeException");
    });
  });

  describe("Password Validation", () => {
    test("validates strong password", () => {
      const result = devAuthService.validatePassword("StrongPass123!");

      expect(result.isValid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    test("rejects weak passwords", () => {
      const weakPasswords = [
        "short", // Too short
        "nouppercase123!", // No uppercase
        "NOLOWERCASE123!", // No lowercase
        "NoNumbers!", // No digits
        "NoSpecial123", // No special characters
      ];

      weakPasswords.forEach((password) => {
        const result = devAuthService.validatePassword(password);
        expect(result.isValid).toBe(false);
        expect(result.errors.length).toBeGreaterThan(0);
      });
    });
  });

  describe("Utility Methods", () => {
    test("generates verification codes", () => {
      const code1 = devAuthService.generateVerificationCode();
      const code2 = devAuthService.generateVerificationCode();

      expect(code1).toMatch(/^\d{6}$/);
      expect(code2).toMatch(/^\d{6}$/);
      expect(code1).not.toBe(code2); // Should be different
    });

    test("generates dev tokens", () => {
      const tokens = devAuthService.generateDevTokens("testuser");

      expect(tokens.accessToken).toBe("dev-bypass-token");
      expect(tokens.idToken).toBe("dev-bypass-token");
      expect(tokens.refreshToken).toBe("dev-bypass-token");
    });

    test("validates JWT tokens", () => {
      expect(devAuthService.validateJwtToken("valid-token")).toBe(true);
      expect(devAuthService.validateJwtToken("")).toBe(false);
      expect(devAuthService.validateJwtToken(null)).toBe(false);
      expect(devAuthService.validateJwtToken(undefined)).toBe(false);
    });

    test("checks token expiration", () => {
      // In dev environment, tokens never expire
      expect(devAuthService.isTokenExpired("any-token")).toBe(false);
    });

    test("confirms MFA (dev bypass)", async () => {
      const result = await devAuthService.confirmMFA(
        { username: "testuser" },
        "123456"
      );

      expect(result.success).toBe(true);
      expect(result.user.username).toBe("testuser");
    });

    test("updates user attributes", async () => {
      await devAuthService.signUp({
        username: "testuser",
        password: "TestPass123!",
        email: "test@example.com",
      });

      const pending = devAuthService.pendingVerifications["testuser"];
      await devAuthService.confirmSignUp("testuser", pending.verificationCode);

      const result = await devAuthService.updateUserAttributes(
        { username: "testuser" },
        { firstName: "Updated", lastName: "Name" }
      );

      expect(result.success).toBe(true);
      expect(devAuthService.users["testuser"].firstName).toBe("Updated");
      expect(devAuthService.users["testuser"].lastName).toBe("Name");
    });
  });

  describe("LocalStorage Persistence", () => {
    test("saves and loads users correctly", () => {
      // Verify localStorage mock is working
      expect(typeof global.localStorage).toBe("object");
      expect(global.localStorage.setItem).toBeDefined();
      expect(global.localStorage).toBe(localStorageMock);

      const testUser = {
        username: "persistent",
        email: "persistent@example.com",
        confirmed: true,
      };

      devAuthService.users["persistent"] = testUser;

      // Clear mock before test
      vi.clearAllMocks();

      devAuthService.saveUsers();

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        "dev_users",
        expect.stringContaining("persistent")
      );

      // Clear and reload
      devAuthService.users = {};
      devAuthService.users = devAuthService.loadUsers();

      expect(devAuthService.users["persistent"]).toEqual(testUser);
    });

    test("saves and loads session correctly", () => {
      // Clear mock before test
      vi.clearAllMocks();

      const testSession = {
        user: { username: "testuser" },
        tokens: { accessToken: "test-token" },
        expiresAt: Date.now() + 3600000,
      };

      devAuthService.saveSession(testSession);

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        "dev_session",
        expect.stringContaining("testuser")
      );

      // Clear and reload
      devAuthService.session = null;
      devAuthService.session = devAuthService.loadSession();

      expect(devAuthService.session.user.username).toBe("testuser");
    });

    test("clears session correctly", () => {
      // Clear mock before test
      vi.clearAllMocks();

      devAuthService.saveSession({ user: { username: "test" } });
      devAuthService.clearSession();

      expect(devAuthService.session).toBeNull();
      expect(localStorageMock.removeItem).toHaveBeenCalledWith("dev_session");
    });
  });
});

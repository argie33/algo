import { vi, describe, test, beforeEach, expect, afterEach } from "vitest";

// Unmock the devAuth service for this test file
vi.unmock("../../../services/devAuth.js");
import authService from "../../../services/devAuth";

// Mock localStorage for testing
const mockLocalStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
globalThis.localStorage = mockLocalStorage;
Object.defineProperty(window, "localStorage", {
  value: mockLocalStorage,
});

describe("DevAuthService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocalStorage.getItem.mockReturnValue(null);
    // Clear auth service session to start fresh each test
    authService.session = null;
    authService.users = {};
    authService.pendingVerifications = {};
    // Ensure default dev user exists for tests that need it
    authService.ensureDevUser();
    console.log(
      "Auth service methods:",
      Object.getOwnPropertyNames(authService)
    );
    console.log("signUp type:", typeof authService.signUp);
    console.log("signUpWrapper type:", typeof authService.signUpWrapper);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("User Registration", () => {
    test("should register new user successfully", async () => {
      const userData = {
        username: "testuser",
        password: "TestPassword123!",
        email: "test@example.com",
        firstName: "Test",
        lastName: "User",
      };

      const result = await authService.signUp(userData);

      expect(result.success).toBe(true);
      expect(result.user.username).toBe("testuser");
      expect(result.user.email).toBe("test@example.com");
      expect(result.userConfirmed).toBe(false);
    });

    test("should handle registration errors for existing user", async () => {
      // Register user first - this goes to pendingVerifications, not users
      const firstResult = await authService.signUp({
        username: "existinguser",
        password: "TestPassword123!",
        email: "existing@example.com",
        firstName: "Existing",
        lastName: "User",
      });

      expect(firstResult.success).toBe(true);

      // Try to register same user again - should get error
      const secondResult = await authService.signUp({
        username: "existinguser",
        password: "TestPassword123!",
        email: "different@example.com",
        firstName: "Test",
        lastName: "User",
      });

      expect(secondResult.success).toBe(false);
      expect(secondResult.error.code).toBe("UsernameExistsException");
      expect(secondResult.error.message).toContain("Username already exists");
    });

    test("should validate password strength", () => {
      const weakPasswords = [
        "short",
        "12345678",
        "password",
        "PASSWORD",
        "Password",
        "Pass123",
      ];

      weakPasswords.forEach((password) => {
        const validation = authService.validatePassword(password);
        expect(validation.isValid).toBe(false);
        expect(validation.errors.length).toBeGreaterThan(0);
      });
    });

    test("should accept strong passwords", () => {
      const strongPasswords = [
        "TestPassword123!",
        "MySecure@Pass2024",
        "Complex#Password99",
        "Str0ng&Password$",
      ];

      strongPasswords.forEach((password) => {
        const validation = authService.validatePassword(password);
        expect(validation.isValid).toBe(true);
        expect(validation.errors.length).toBe(0);
      });
    });
  });

  describe("User Authentication", () => {
    test("should sign in default dev user successfully", async () => {
      const result = await authService.signIn("devuser", "password123");

      expect(result.success).toBe(true);
      expect(result.user.username).toBe("devuser");
      expect(result.user.email).toBe("argeropolos@gmail.com");
      expect(result.tokens.accessToken).toBe("dev-bypass-token");
    });

    test("should sign in with email successfully", async () => {
      const result = await authService.signIn(
        "argeropolos@gmail.com",
        "password123"
      );

      expect(result.success).toBe(true);
      expect(result.user.username).toBe("devuser");
      expect(result.user.email).toBe("argeropolos@gmail.com");
    });

    test("should handle sign in errors", async () => {
      const result = await authService.signIn("wronguser", "wrongpass");

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("UserNotFoundException");
      expect(result.error.message).toContain("User not found");
    });

    test("should handle wrong password", async () => {
      const result = await authService.signIn("devuser", "wrongpass");

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("NotAuthorizedException");
      expect(result.error.message).toContain("Invalid password");
    });
  });

  describe("Session Management", () => {
    test("should get current authenticated user", async () => {
      // Sign in first
      await authService.signIn("devuser", "password123");

      const result = await authService.getCurrentUser();

      expect(result.success).toBe(true);
      expect(result.user.username).toBe("devuser");
      expect(result.user.email).toBe("argeropolos@gmail.com");
    });

    test("should handle no current user", async () => {
      // Ensure no session exists
      authService.session = null;

      const result = await authService.getCurrentUser();

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("NotAuthorizedException");
      expect(result.error.message).toContain("No authenticated user");
    });

    test("should get JWT token", async () => {
      // Sign in first
      await authService.signIn("devuser", "password123");

      const token = await authService.getJwtToken();

      expect(token).toBe("dev-bypass-token");
    });

    test("should return null for JWT token when not signed in", async () => {
      // Ensure no session exists
      authService.session = null;

      const token = await authService.getJwtToken();

      expect(token).toBeNull();
    });
  });

  describe("User Sign Out", () => {
    test("should sign out user successfully", async () => {
      // Sign in first
      await authService.signIn("devuser", "password123");

      const result = await authService.signOut();

      expect(result.success).toBe(true);

      // Verify user is signed out
      const currentUserResult = await authService.getCurrentUser();
      expect(currentUserResult.success).toBe(false);
    });
  });

  describe("Password Management", () => {
    test("should initiate password reset", async () => {
      const result = await authService.forgotPassword("devuser");

      expect(result.success).toBe(true);
    });

    test("should handle password reset for non-existent user", async () => {
      const result = await authService.forgotPassword("nonexistent");

      expect(result.success).toBe(false);
      expect(result.error.code).toBe("UserNotFoundException");
    });

    test("should confirm password reset", async () => {
      // Initiate reset first
      await authService.forgotPassword("devuser");

      // Get the generated reset code from pending verifications
      const resetKey = `reset_devuser`;
      const pending = authService.pendingVerifications[resetKey];
      const resetCode = pending ? pending.resetCode : "123456";

      // Use the actual reset code
      const result = await authService.forgotPasswordSubmit(
        "devuser",
        resetCode,
        "NewPassword123!"
      );

      expect(result.success).toBe(true);
    });
  });

  describe("Token Validation", () => {
    test("should validate JWT token format", () => {
      expect(authService.validateJwtToken("dev-bypass-token")).toBe(true);
      expect(authService.validateJwtToken("")).toBe(false);
      expect(authService.validateJwtToken(null)).toBe(false);
      expect(authService.validateJwtToken(undefined)).toBe(false);
    });

    test("should check token expiration", () => {
      // Dev tokens don't expire
      expect(authService.isTokenExpired("dev-bypass-token")).toBe(false);
    });
  });

  describe("User Attributes Management", () => {
    test("should update user attributes", async () => {
      const user = { username: "devuser" };
      const attributes = {
        firstName: "Updated",
        lastName: "Name",
      };

      const result = await authService.updateUserAttributes(user, attributes);

      expect(result.success).toBe(true);
    });
  });

  describe("MFA Support", () => {
    test("should confirm MFA code successfully", async () => {
      const cognitoUser = { username: "testuser" };
      const result = await authService.confirmMFA(cognitoUser, "123456");

      expect(result.success).toBe(true);
      expect(result.user.username).toBe("testuser");
    });
  });

  describe("Helper Methods", () => {
    test("should check if user is authenticated", async () => {
      // Not authenticated initially - session is null
      authService.session = null;
      expect(authService.isAuthenticated()).toBe(false);

      // Sign in
      await authService.signIn("devuser", "password123");
      expect(authService.isAuthenticated()).toBe(true);

      // Sign out
      await authService.signOut();
      expect(authService.isAuthenticated()).toBe(false);
    });

    test("should get current user info", async () => {
      // No user initially
      expect(authService.getCurrentUserInfo()).toBeNull();

      // Sign in
      await authService.signIn("devuser", "password123");
      const userInfo = authService.getCurrentUserInfo();
      expect(userInfo).not.toBeNull();
      expect(userInfo.username).toBe("devuser");
    });
  });
});

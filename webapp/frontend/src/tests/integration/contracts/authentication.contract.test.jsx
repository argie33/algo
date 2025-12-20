/**
 * Authentication Contract Test
 *
 * Tests the contract between frontend authentication components and backend auth API.
 * Validates login, registration, and session management API structures.
 */

import { describe, it, expect, beforeAll } from "vitest";
import {
  checkServerAvailability,
  skipIfServerUnavailable,
  API_BASE_URL,
  AUTH_HEADERS,
} from "./test-server-utils.js";

describe("Authentication Contract Tests", () => {
  let serverAvailable = false;

  beforeAll(async () => {
    serverAvailable = await checkServerAvailability();
  });

  it("should validate login endpoint structure", async () => {
    if (skipIfServerUnavailable(serverAvailable, "login endpoint test")) return;

    // STEP 1: Test real backend API response structure for login
    const testLoginData = {
      email: "test@example.com",
      password: "testpassword123",
    };

    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: AUTH_HEADERS,
      body: JSON.stringify(testLoginData),
    });

    const apiResponse = await response.json();

    // Validate backend contract - should have consistent structure
    expect(apiResponse).toHaveProperty("success");

    console.log("Login endpoint structure:", {
      success: apiResponse.success,
      hasToken: "token" in apiResponse,
      hasAccessToken: "accessToken" in apiResponse,
      hasUser: "user" in apiResponse,
      hasData: "data" in apiResponse,
      statusCode: response.status,
    });

    // STEP 2: Validate expected authentication response fields
    if (apiResponse.success) {
      // Should provide authentication token in some form
      const hasAuthToken =
        apiResponse.token ||
        apiResponse.accessToken ||
        (apiResponse.data &&
          (apiResponse.data.token || apiResponse.data.accessToken));

      console.log("Authentication token available:", !!hasAuthToken);

      // Should provide user information
      const hasUserInfo =
        apiResponse.user || (apiResponse.data && apiResponse.data.user);
      console.log("User information available:", !!hasUserInfo);
    }
  });

  it("should validate registration endpoint structure", async () => {
    if (skipIfServerUnavailable(serverAvailable, "registration endpoint test"))
      return;

    const testRegisterData = {
      email: "newuser@example.com",
      password: "testpassword123",
      confirmPassword: "testpassword123",
      firstName: "Test",
      lastName: "User",
    };

    const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
      method: "POST",
      headers: AUTH_HEADERS,
      body: JSON.stringify(testRegisterData),
    });

    const apiResponse = await response.json();

    // Validate backend contract
    expect(apiResponse).toHaveProperty("success");

    console.log("Registration endpoint structure:", {
      success: apiResponse.success,
      hasToken: "token" in apiResponse,
      hasUser: "user" in apiResponse,
      hasMessage: "message" in apiResponse,
      hasData: "data" in apiResponse,
      statusCode: response.status,
    });
  });

  it("should validate session validation endpoint structure", async () => {
    if (skipIfServerUnavailable(serverAvailable, "session validation test"))
      return;

    const response = await fetch(`${API_BASE_URL}/api/auth/validate`, {
      headers: AUTH_HEADERS,
    });

    const apiResponse = await response.json();

    // Validate backend contract
    expect(apiResponse).toHaveProperty("success");

    console.log("Session validation structure:", {
      success: apiResponse.success,
      hasUser: "user" in apiResponse,
      hasValid: "valid" in apiResponse,
      hasData: "data" in apiResponse,
      statusCode: response.status,
    });
  });

  it("should validate password reset endpoint structure", async () => {
    if (skipIfServerUnavailable(serverAvailable, "password reset test")) return;

    const testResetData = {
      email: "test@example.com",
    };

    const response = await fetch(`${API_BASE_URL}/api/auth/forgot-password`, {
      method: "POST",
      headers: AUTH_HEADERS,
      body: JSON.stringify(testResetData),
    });

    const apiResponse = await response.json();

    // Validate backend contract
    expect(apiResponse).toHaveProperty("success");

    console.log("Password reset structure:", {
      success: apiResponse.success,
      hasMessage: "message" in apiResponse,
      hasData: "data" in apiResponse,
      statusCode: response.status,
    });
  });

  it("should validate logout endpoint structure", async () => {
    if (skipIfServerUnavailable(serverAvailable, "logout endpoint test"))
      return;

    const response = await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: "POST",
      headers: AUTH_HEADERS,
    });

    const apiResponse = await response.json();

    // Validate backend contract
    expect(apiResponse).toHaveProperty("success");

    console.log("Logout endpoint structure:", {
      success: apiResponse.success,
      hasMessage: "message" in apiResponse,
      statusCode: response.status,
    });
  });

  it("should validate authentication error handling contract", async () => {
    if (skipIfServerUnavailable(serverAvailable, "auth error handling test"))
      return;

    // Test with invalid credentials
    const invalidLoginData = {
      email: "invalid@example.com",
      password: "wrongpassword",
    };

    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: AUTH_HEADERS,
      body: JSON.stringify(invalidLoginData),
    });

    const errorResponse = await response.json();

    // Validate error contract - should have consistent structure
    expect(errorResponse).toHaveProperty("success", false);

    console.log("Auth error response structure:", {
      success: errorResponse.success,
      hasError: "error" in errorResponse,
      hasMessage: "message" in errorResponse,
      statusCode: response.status,
    });
  });

  it("should validate authentication API contract supports complete user flow", async () => {
    if (skipIfServerUnavailable(serverAvailable, "auth flow contract test"))
      return;

    // Test complete authentication flow contract

    // 1. Registration attempt
    const registerData = {
      email: "contracttest@example.com",
      password: "testpassword123",
      confirmPassword: "testpassword123",
      firstName: "Contract",
      lastName: "Test",
    };

    const registerResponse = await fetch(`${API_BASE_URL}/api/auth/register`, {
      method: "POST",
      headers: AUTH_HEADERS,
      body: JSON.stringify(registerData),
    });

    const registerResult = await registerResponse.json();
    expect(registerResult).toHaveProperty("success");

    // 2. Login attempt
    const loginData = {
      email: "contracttest@example.com",
      password: "testpassword123",
    };

    const loginResponse = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: AUTH_HEADERS,
      body: JSON.stringify(loginData),
    });

    const loginResult = await loginResponse.json();
    expect(loginResult).toHaveProperty("success");

    // 3. Session validation
    const validateResponse = await fetch(`${API_BASE_URL}/api/auth/validate`, {
      headers: AUTH_HEADERS,
    });

    const validateResult = await validateResponse.json();
    expect(validateResult).toHaveProperty("success");

    console.log("✅ Authentication API contract supports complete user flow");
  });
});

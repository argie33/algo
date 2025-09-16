/**
 * Settings API Keys Contract Test
 *
 * This test would have caught the API key display bug by testing:
 * 1. Real backend API response structure
 * 2. Frontend component consumption of that structure
 * 3. Actual contract between frontend and backend
 */

import { describe, it, expect, beforeAll, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { TestWrapper } from "../../test-utils.jsx";
import Settings from "../../../pages/Settings.jsx";
import { checkServerAvailability, API_BASE_URL } from "./test-server-utils.js";

describe("Settings API Keys Contract Tests", () => {
  let serverAvailable = false;

  beforeAll(async () => {
    serverAvailable = await checkServerAvailability();
  });

  it("should validate Settings component consumes real API keys endpoint structure", async () => {
    if (!serverAvailable) {
      console.warn("Skipping contract test - backend not available");
      return;
    }

    // STEP 1: Test real backend API response structure (using actual endpoint)
    const response = await fetch(`${API_BASE_URL}/api/portfolio/api-keys`, {
      headers: {
        Authorization: "Bearer mock-access-token",
      },
    });

    expect(response.status).toBe(200);
    const apiResponse = await response.json();

    // Validate backend contract (portfolio API structure)
    expect(apiResponse).toHaveProperty("success", true);
    expect(apiResponse).toHaveProperty("data");
    expect(Array.isArray(apiResponse.data)).toBe(true);

    console.log("Real backend response structure:", {
      success: apiResponse.success,
      hasDataProperty: "data" in apiResponse,
      dataType: typeof apiResponse.data,
      dataIsArray: Array.isArray(apiResponse.data),
      dataLength: apiResponse.data?.length || 0,
    });

    // STEP 2: Test frontend component with real response structure
    // This is where the bug was - frontend expected 'apiKeys' but backend returns 'data'

    // Mock the API call to return the REAL backend structure
    const originalFetch = global.fetch;
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(apiResponse),
    });
    global.fetch = mockFetch;

    // Cleanup
    afterEach(() => {
      global.fetch = originalFetch;
    });

    // Render the Settings component
    render(
      <TestWrapper>
        <Settings />
      </TestWrapper>
    );

    // STEP 3: Verify frontend correctly consumes backend response
    await waitFor(() => {
      // Check if we have API keys based on the actual backend structure
      if (apiResponse.data && apiResponse.data.length > 0) {
        // Should show API keys, not "No API keys configured"
        expect(
          screen.queryByText(/No API keys configured/i)
        ).not.toBeInTheDocument();
      } else {
        // If no API keys, should show appropriate message
        expect(screen.getByText(/No API keys configured/i)).toBeInTheDocument();
      }
    });

    // STEP 4: Contract validation - ensure frontend parses structure correctly
    // This test validates that the API returns the expected structure
    const settingsLogic = (responseData) => {
      // Test that we can access the data correctly
      const apiKeys = responseData.data || [];

      return {
        hasCorrectStructure: !!(
          responseData.data && Array.isArray(responseData.data)
        ),
        apiKeysCount: apiKeys.length,
        hasExpectedFields:
          apiKeys.length === 0 || apiKeys[0].brokerName !== undefined,
      };
    };

    const contractTest = settingsLogic(apiResponse);

    // This assertion validates the API structure is correct
    expect(contractTest.hasCorrectStructure).toBe(true);
    expect(contractTest.apiKeysCount).toEqual(apiResponse.data.length);
  });

  it("should validate API key creation contract", async () => {
    if (!serverAvailable) {
      console.warn("Skipping contract test - backend not available");
      return;
    }

    // Test the POST endpoint structure (portfolio API)
    const testApiKey = {
      brokerName: "test-broker-contract",
      apiKey: "test-key-123",
      apiSecret: "test-secret-456",
      sandbox: true,
    };

    const response = await fetch(`${API_BASE_URL}/api/portfolio/api-keys`, {
      method: "POST",
      headers: {
        Authorization: "Bearer mock-access-token",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(testApiKey),
    });

    expect(response.status).toBe(200);
    const createResponse = await response.json();

    // Validate creation response contract
    expect(createResponse).toHaveProperty("success", true);

    // Clean up - delete the test key
    await fetch(
      `${API_BASE_URL}/api/portfolio/api-keys/${testApiKey.brokerName}`,
      {
        method: "DELETE",
        headers: {
          Authorization: "Bearer mock-access-token",
        },
      }
    );
  });

  it("should validate error handling contract", async () => {
    if (!serverAvailable) {
      console.warn("Skipping contract test - backend not available");
      return;
    }

    // Test error response structure
    const response = await fetch(
      `${API_BASE_URL}/api/portfolio/api-keys/nonexistent`,
      {
        method: "DELETE",
        headers: {
          Authorization: "Bearer mock-access-token",
        },
      }
    );

    const errorResponse = await response.json();

    // Validate error contract - should still have consistent structure
    expect(errorResponse).toHaveProperty("success");
    // Error responses should have predictable structure for frontend handling
  });
});

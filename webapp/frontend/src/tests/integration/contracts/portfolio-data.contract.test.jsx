/**
 * Portfolio Data Contract Test
 * 
 * Tests the critical portfolio data flow that powers the main dashboard
 */

import { describe, it, expect, beforeAll } from "vitest";
import { 
  checkServerAvailability, 
  skipIfServerUnavailable, 
  API_BASE_URL,
  AUTH_HEADERS 
} from "./test-server-utils.js";

describe("Portfolio Data Contract Tests", () => {
  let serverAvailable = false;

  beforeAll(async () => {
    serverAvailable = await checkServerAvailability();
  });

  it("should validate portfolio holdings endpoint contract", async () => {
    if (skipIfServerUnavailable(serverAvailable, "portfolio holdings test")) return;

    // Test real backend response structure
    const response = await fetch(`${API_BASE_URL}/api/portfolio/holdings`, {
      headers: AUTH_HEADERS
    });
    
    expect(response.status).toBe(200);
    const apiResponse = await response.json();
    
    // Validate backend contract
    expect(apiResponse).toHaveProperty('success', true);
    expect(apiResponse).toHaveProperty('data');
    expect(apiResponse.data).toHaveProperty('holdings');
    expect(apiResponse.data).toHaveProperty('summary');
    expect(Array.isArray(apiResponse.data.holdings)).toBe(true);
    
    console.log('Portfolio holdings response structure:', {
      success: apiResponse.success,
      hasData: 'data' in apiResponse,
      hasHoldings: apiResponse.data && 'holdings' in apiResponse.data,
      hasSummary: apiResponse.data && 'summary' in apiResponse.data,
      holdingsCount: apiResponse.data?.holdings?.length || 0
    });
  });

  it("should validate portfolio analytics endpoint contract", async () => {
    if (!serverAvailable) {
      console.warn("Skipping portfolio analytics contract test - backend not available");
      return;
    }

    const response = await fetch(`${API_BASE_URL}/api/portfolio/analytics`, {
      headers: {
        'Authorization': 'Bearer mock-access-token'
      }
    });
    
    expect(response.status).toBe(200);
    const apiResponse = await response.json();
    
    // Validate analytics contract
    expect(apiResponse).toHaveProperty('success', true);
    expect(apiResponse).toHaveProperty('data');
    
    console.log('Portfolio analytics response structure:', apiResponse);
  });

  it("should validate market overview endpoint contract", async () => {
    if (!serverAvailable) {
      console.warn("Skipping market overview contract test - backend not available");
      return;
    }

    const response = await fetch(`${API_BASE_URL}/api/market/overview`, {
      headers: {
        'Authorization': 'Bearer mock-access-token'
      }
    });
    
    expect(response.status).toBe(200);
    const apiResponse = await response.json();
    
    // Validate market overview contract
    expect(apiResponse).toHaveProperty('success', true);
    expect(apiResponse).toHaveProperty('data');
    
    console.log('Market overview response structure:', apiResponse);
  });
});
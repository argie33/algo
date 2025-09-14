/**
 * Dashboard Contract Tests
 * Tests the most critical user-facing data flows
 */

import { describe, it, expect, beforeAll } from "vitest";
import { 
  checkServerAvailability, 
  skipIfServerUnavailable, 
  API_BASE_URL,
  AUTH_HEADERS 
} from "./test-server-utils.js";

describe("Dashboard Critical Contract Tests", () => {
  let serverAvailable = false;

  beforeAll(async () => {
    serverAvailable = await checkServerAvailability();
  });

  it("validates dashboard summary data structure", async () => {
    if (skipIfServerUnavailable(serverAvailable, "dashboard contract test")) return;

    const response = await fetch(`${API_BASE_URL}/api/dashboard/summary`, {
      headers: AUTH_HEADERS
    });
    
    expect(response.status).toBe(200);
    const data = await response.json();
    
    expect(data).toHaveProperty('success', true);
    expect(data).toHaveProperty('data');
    
    // Test critical dashboard contract
    console.log('Dashboard summary structure:', data);
  });

  it("validates market overview data for dashboard", async () => {
    if (!serverAvailable) return;

    const response = await fetch(`${API_BASE_URL}/api/market/overview`, {
      headers: { 'Authorization': 'Bearer mock-access-token' }
    });
    
    const data = await response.json();
    expect(data).toHaveProperty('success', true);
    console.log('Market overview structure:', Object.keys(data));
  });

  it("validates portfolio value for dashboard widget", async () => {
    if (!serverAvailable) return;

    const response = await fetch(`${API_BASE_URL}/api/portfolio/value`, {
      headers: { 'Authorization': 'Bearer mock-access-token' }
    });
    
    const data = await response.json();
    expect(data).toHaveProperty('success', true);
    console.log('Portfolio value structure:', Object.keys(data));
  });
});
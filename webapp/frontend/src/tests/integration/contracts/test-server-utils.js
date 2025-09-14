/**
 * Shared utilities for contract tests to reduce duplication
 */

import { vi } from 'vitest';

const API_BASE_URL = "http://localhost:3001";

/**
 * Check if the backend server is available for contract testing
 * @returns {Promise<boolean>} true if server is available
 */
export async function checkServerAvailability() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/health`);
    return response.ok;
  } catch (error) {
    console.warn("Backend server not available for contract tests:", error.message);
    return false;
  }
}

/**
 * Skip test if server is not available with consistent message
 * @param {boolean} serverAvailable - result from checkServerAvailability
 * @param {string} testName - name of the test for logging
 */
export function skipIfServerUnavailable(serverAvailable, testName = "contract test") {
  if (!serverAvailable) {
    console.warn(`Skipping ${testName} - backend not available`);
    return true;
  }
  return false;
}

/**
 * Standard headers for authenticated API calls
 */
export const AUTH_HEADERS = {
  'Authorization': 'Bearer mock-access-token',
  'Content-Type': 'application/json'
};

/**
 * Create mock fetch for testing component-API integration
 * @param {object} mockResponse - the response to mock
 * @returns {object} - object with mockFetch and cleanup function
 */
export function createMockFetch(mockResponse) {
  const originalFetch = global.fetch;
  const mockFetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(mockResponse)
  });
  
  global.fetch = mockFetch;
  
  return {
    mockFetch,
    cleanup: () => {
      global.fetch = originalFetch;
    }
  };
}

export { API_BASE_URL };
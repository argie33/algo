/**
 * Shared utilities for contract tests to reduce duplication
 */

import { vi } from "vitest";

const API_BASE_URL = "http://localhost:3001";

/**
 * Check if the backend server is available for contract testing
 * @returns {Promise<boolean>} true if server is available
 */
export async function checkServerAvailability() {
  try {
    // For integration tests, we need real fetch
    let realFetch = global.fetch;

    // If fetch is mocked, use node-fetch or a real implementation
    if (!realFetch || realFetch.mock) {
      // Try to use node's fetch or import node-fetch
      try {
        // Use dynamic import to get real fetch
        if (typeof globalThis !== 'undefined' && globalThis.fetch) {
          realFetch = globalThis.fetch;
        } else {
          // Fallback: create a minimal working fetch for health check
          realFetch = async (url, options = {}) => {
            const http = await import('http');
            const { URL } = await import('url');

            return new Promise((resolve, reject) => {
              const parsedUrl = new URL(url);
              const req = http.request({
                hostname: parsedUrl.hostname,
                port: parsedUrl.port,
                path: parsedUrl.pathname,
                method: options.method || 'GET',
                headers: options.headers || {},
              }, (res) => {
                resolve({
                  ok: res.statusCode >= 200 && res.statusCode < 300,
                  status: res.statusCode,
                  json: async () => {
                    let data = '';
                    res.on('data', chunk => data += chunk);
                    return new Promise(resolve => {
                      res.on('end', () => resolve(JSON.parse(data)));
                    });
                  }
                });
              });

              req.on('error', reject);
              req.setTimeout(3000, () => {
                req.destroy();
                reject(new Error('Request timeout'));
              });
              req.end();
            });
          };
        }
      } catch (importError) {
        console.warn("Could not import real fetch implementation");
        return false;
      }
    }

    const response = await realFetch(`${API_BASE_URL}/api/health`, {
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response) {
      console.warn("No response received from health endpoint");
      return false;
    }

    return response.ok;
  } catch (error) {
    console.warn(
      "Backend server not available for contract tests:",
      error.message
    );
    return false;
  }
}

/**
 * Skip test if server is not available with consistent message
 * @param {boolean} serverAvailable - result from checkServerAvailability
 * @param {string} testName - name of the test for logging
 */
export function skipIfServerUnavailable(
  serverAvailable,
  testName = "contract test"
) {
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
  Authorization: "Bearer mock-access-token",
  "Content-Type": "application/json",
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
    json: () => Promise.resolve(mockResponse),
  });

  global.fetch = mockFetch;

  return {
    mockFetch,
    cleanup: () => {
      global.fetch = originalFetch;
    },
  };
}

export { API_BASE_URL };

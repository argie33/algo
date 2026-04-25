import axios from "axios";

// Get API configuration
export const getApiConfig = () => {
  // STRICT 3-LEVEL URL RESOLUTION - no hardcoded production URLs
  // 1. Runtime injection (AWS deployment)
  if (typeof window !== "undefined" && window.__CONFIG__?.API_URL) {
    const apiUrl = window.__CONFIG__.API_URL;
    return { baseURL: apiUrl, apiUrl, isServerless: !apiUrl.includes("localhost"), isDev: false, isDevelopment: false, isProduction: true };
  }

  // 2. Build-time env var
  if (import.meta.env?.VITE_API_URL) {
    const apiUrl = import.meta.env.VITE_API_URL;
    return { baseURL: apiUrl, apiUrl, isServerless: !apiUrl.includes("localhost"), isDev: false, isDevelopment: true, isProduction: false };
  }

  // 3. Dev: relative path, Vite proxy handles it
  const isDev = import.meta.env?.DEV;
  const apiUrl = "/";

  return {
    baseURL: apiUrl,
    apiUrl: apiUrl,
    isServerless: false,
    isDev: isDev,
    isDevelopment: isDev,
    isProduction: false,
  };
};

// Create API instance that can be updated
let currentConfig = getApiConfig();

// Simple health check state
let apiHealthy = true;
let lastHealthCheck = 0;
const HEALTH_CHECK_INTERVAL = 30000;

const _checkApiHealth = async () => {
  const now = Date.now();
  if (now - lastHealthCheck < HEALTH_CHECK_INTERVAL) {
    return apiHealthy;
  }

  try {
    const response = await fetch(`${currentConfig.baseURL}/health`, {
      method: "GET",
      signal: AbortSignal.timeout(3000),
    });
    apiHealthy = response?.ok;
    lastHealthCheck = now;
  } catch (error) {
    apiHealthy = false;
    lastHealthCheck = now;
  }

  return apiHealthy;
};

// Log config in development only
if (typeof process === "undefined" || process.env.NODE_ENV !== "test") {
  if (!currentConfig.apiUrl || currentConfig.apiUrl.includes("localhost")) {
    console.warn(
      "[API CONFIG] Using fallback API URL:",
      currentConfig.baseURL +
        "\nSet window.__CONFIG__.API_URL at runtime or VITE_API_URL at build time to override."
    );
  }
}

// Create axios instance
let api = axios.create({
  baseURL: currentConfig.baseURL,
  timeout: currentConfig.isServerless ? 45000 : 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor - add auth token and track timing
try {
  if (api && api.interceptors) {
    api.interceptors.request.use(
      (config) => {
        config.metadata = { startTime: new Date() };
        if (typeof window !== "undefined") {
          const token = localStorage.getItem("authToken") || localStorage.getItem("accessToken");
          if (token) {
            config.headers.Authorization = `Bearer ${token}`;
          }
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor - handle errors
    api.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          localStorage.removeItem("authToken");
          localStorage.removeItem("accessToken");
          if (typeof window !== "undefined" && window.location) {
            window.location.href = "/login";
          }
        }
        return Promise.reject(error);
      }
    );
  }
} catch (error) {
  console.warn("[API] Interceptor setup failed:", error.message);
}

// ============================================
// RESPONSE NORMALIZATION HELPERS
// ============================================
// Standardize all API response handling across the app
// Instead of 14 different extraction patterns, use these 3 helpers

/**
 * Extract data from ANY API response format
 * Handles: items arrays, data objects, nested data.data, direct arrays
 */
export const extractData = (response) => {
  // Handle paginated responses: {success, items, pagination}
  if (response?.data?.items) {
    return response.data.items;
  }
  // Handle double-nested responses: {success, data: {data: [...]}}
  if (response?.data?.data?.items) {
    return response.data.data.items;
  }
  if (Array.isArray(response?.data?.data)) {
    return response.data.data;
  }
  // Handle direct array responses: {success, data: [...]}
  if (Array.isArray(response?.data)) {
    return response.data;
  }
  // Handle object responses: {success, data: {...}}
  if (response?.data?.data) {
    return response.data.data;
  }
  // Fallback
  return response?.data || null;
};

/**
 * Extract pagination info from paginated responses
 */
export const extractPagination = (response) => {
  return response?.data?.pagination || response?.data?.data?.pagination || null;
};

/**
 * Check if response indicates success
 */
export const isResponseSuccess = (response) => {
  return response?.data?.success !== false && response?.status >= 200 && response?.status < 300;
};

/**
 * Backward compatibility - old name still works
 */
export const extractResponseData = extractData;

// Export the axios instance for direct use
export default api;

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

// Extract response data - used by pages
export const extractResponseData = (response) => {
  if (response?.data?.items) {
    return response.data.items;
  }
  if (response?.data?.data) {
    return response.data.data;
  }
  if (Array.isArray(response?.data)) {
    return response.data;
  }
  return response?.data || null;
};

// Export the axios instance for direct use
export default api;
